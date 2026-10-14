"""End-to-end tests for Sprint 1 (Single-Run Quality & Slicing), Sprint 2 (32D Parameter Learning), and Sprint 3 (Sparse Recommendation & Active DoE)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from axiom import (
    CncQualityReport,
    LearnedParameterSurrogate,
    ParameterRecommendationReport,
    ParameterRecommendationRequest,
    StandardCaseSettings,
    TraceColumns,
    TraceImportOptions,
    build_cnc_parameter_closed_loop_demo,
    causal_mask_for_metric,
    cnc_benchmark_example,
    default_cnc_parameter_registry,
    default_parameter_values,
    evaluate_cnc_export,
    generate_parameter_doe,
    import_controller_trace,
    learn_parameter_surrogate,
    predict_metric_for_parameters,
    recommend_parameters,
    render_parameter_impact_table,
    render_quality_report_table,
    render_recommendation_table,
    simulate_parametric_cnc_export,
    standard_case,
)
from axiom.cli import main
from axiom.web import create_app


class CncParameterIntelligenceTests(unittest.TestCase):
    def test_sprint1_single_run_quality_evaluation_and_geometry_slicing(self) -> None:
        reg = default_cnc_parameter_registry()
        self.assertEqual(len(reg.parameters), 32)

        # Evaluate corner90 with dual-trace controller feedback
        corner_case = standard_case("corner90", StandardCaseSettings(sample_period_seconds=0.005))
        params = default_parameter_values(reg)
        params["g1.corner_tolerance_mm"] = 0.025
        params["g3.servo_kp_x"] = 55.0
        params["g3.servo_kp_y"] = 70.0
        export = simulate_parametric_cnc_export(
            corner_case,
            params,
            source_kind="controller-trace",
            registry=reg,
        )
        report = evaluate_cnc_export(corner_case, export)
        self.assertIsInstance(report, CncQualityReport)
        self.assertEqual(report.scope, "sampled-xyz-command-and-servo-feedback")
        self.assertIsNotNone(report.servo_metrics)
        assert report.servo_metrics is not None
        self.assertGreater(report.servo_metrics["followingErrorMaxMm"].value or 0.0, 0.0)
        self.assertGreater(report.servo_metrics["actualPathDeviationMaxMm"].value or 0.0, 0.0)

        # Check geometric primitive slices (lines + 90-deg corner)
        kinds = {s.primitive_kind for s in report.geometry_slices}
        self.assertIn("line", kinds)
        self.assertIn("corner", kinds)
        table_text = render_quality_report_table(report)
        self.assertIn("伺服物理层指标", table_text)
        self.assertIn("几何基元切片", table_text)

        # Evaluate circle case for arc slicing and micro-segments case for cluster slicing
        circle_case = standard_case("circle", StandardCaseSettings(sample_period_seconds=0.005))
        circle_exp = simulate_parametric_cnc_export(circle_case, params, source_kind="algorithm-export", registry=reg)
        circle_rep = evaluate_cnc_export(circle_case, circle_exp)
        self.assertIn("arc", {s.primitive_kind for s in circle_rep.geometry_slices})

        micro_case = standard_case("small-segments", StandardCaseSettings(sample_period_seconds=0.005))
        micro_exp = simulate_parametric_cnc_export(micro_case, params, source_kind="algorithm-export", registry=reg)
        micro_rep = evaluate_cnc_export(micro_case, micro_exp)
        self.assertIn("micro-segment-cluster", {s.primitive_kind for s in micro_rep.geometry_slices})

    def test_sprint1_csv_import_with_actual_positions_and_parameters(self) -> None:
        case = standard_case("line", StandardCaseSettings(sample_period_seconds=0.01))
        csv_text = "\n".join(
            [
                "Cycle,X,Y,Z,ActX,ActY,ActZ",
                "0,0.0,0.0,0.0,0.0,0.0,0.0",
                "1,10.0,0.0,0.0,9.985,0.002,0.0",
                "2,25.0,0.0,0.0,24.980,-0.003,0.0",
                "3,40.0,0.0,0.0,39.988,0.001,0.0",
                "4,50.0,0.0,0.0,50.0,0.0,0.0",
            ]
        )
        opts = TraceImportOptions(
            columns=TraceColumns(
                x="X",
                y="Y",
                z="Z",
                actual_x="ActX",
                actual_y="ActY",
                actual_z="ActZ",
                cycle="Cycle",
            ),
            parameter_registry_id="cnc.planner-and-servo.32d@1",
            parameters={"g1.corner_tolerance_mm": 0.015, "g3.servo_kp_x": 65.0},
        )
        export = import_controller_trace(
            csv_text,
            case,
            algorithm_id="planner",
            algorithm_version="v1",
            options=opts,
        )
        self.assertEqual(export.parameters, {"g1.corner_tolerance_mm": 0.015, "g3.servo_kp_x": 65.0})
        self.assertIsNotNone(export.samples[1].actual_position_mm)
        rep = evaluate_cnc_export(case, export)
        assert rep.servo_metrics is not None
        self.assertAlmostEqual(rep.servo_metrics["followingErrorMaxMm"].value or 0.0, (0.02**2 + 0.003**2) ** 0.5, places=5)

    def test_sprint2_causal_mask_and_32d_active_parameter_discovery(self) -> None:
        reg = default_cnc_parameter_registry()
        mask_dur = causal_mask_for_metric(reg, "durationSeconds", has_controller_traces=True)
        self.assertTrue(mask_dur["g1.corner_tolerance_mm"])
        self.assertTrue(mask_dur["g2.path_tangential_acc_mm_s2"])
        self.assertFalse(mask_dur["g3.servo_kp_x"])

        demo = build_cnc_parameter_closed_loop_demo(offline_count=24, controller_count=10, seed=42)
        surrogate = demo.surrogate
        self.assertIsInstance(surrogate, LearnedParameterSurrogate)
        self.assertEqual(surrogate.offline_run_count, 24)
        self.assertEqual(surrogate.controller_run_count, 10)

        # Verify G3 servo parameters are strictly CausalMasked (0 contribution) on planning metrics
        dur_head = surrogate.metric_heads["durationSeconds"]
        g3_items = [s for s in dur_head.sensitivities if s.group == "G3_ServoControl"]
        self.assertTrue(all(s.status == "CausalMasked" and s.contribution_ratio == 0.0 for s in g3_items))

        # Verify true planted dominant parameters are recovered as Active
        dev_head = surrogate.metric_heads["sampledPathDeviationMaxMm"]
        dev_active_ids = {s.parameter_id for s in dev_head.sensitivities if s.status == "Active"}
        self.assertTrue(
            {"g1.corner_tolerance_mm", "g2.fir_moving_avg_time_ms"} & dev_active_ids,
            f"Expected corner_tolerance or fir_moving_avg in {dev_active_ids}",
        )

        # Verify multi-fidelity residual fusion head is active for actualPathDeviationMaxMm
        act_head = surrogate.metric_heads["actualPathDeviationMaxMm"]
        self.assertEqual(act_head.modeling_mode, "multi-fidelity-residual-fusion")
        self.assertEqual(act_head.base_metric_id, "sampledPathDeviationMaxMm")

        impact_table = render_parameter_impact_table(surrogate)
        self.assertIn("30+ 参数自动学习与敏感度归因报告", impact_table)

    def test_sprint3_sparse_top_k_recommendation_and_active_doe(self) -> None:
        demo = build_cnc_parameter_closed_loop_demo(offline_count=20, controller_count=8, seed=7)
        rec = demo.recommendation_report
        self.assertIsInstance(rec, ParameterRecommendationReport)
        self.assertEqual(len(rec.presets), 3)
        roles = [p.preset_role for p in rec.presets]
        self.assertEqual(roles, ["EfficiencyOptimal", "PrecisionOptimal", "BalancedKneePoint"])

        for preset in rec.presets:
            self.assertLessEqual(preset.changed_parameter_count, rec.max_changed_parameters)
            self.assertFalse(preset.device_write_allowed)
            self.assertEqual(preset.permission_level, "OfflineAdvisory")

        # EfficiencyOptimal should have durationSeconds <= PrecisionOptimal
        eff_dur = rec.presets[0].predicted_metrics["durationSeconds"].predicted_mean
        prec_dur = rec.presets[1].predicted_metrics["durationSeconds"].predicted_mean
        self.assertLessEqual(eff_dur, prec_dur + 1e-6)

        # PrecisionOptimal should have contour error <= EfficiencyOptimal
        acc_metric = rec.primary_accuracy_metric_id
        prec_err = rec.presets[1].predicted_metrics[acc_metric].predicted_mean
        eff_err = rec.presets[0].predicted_metrics[acc_metric].predicted_mean
        self.assertLessEqual(prec_err, eff_err + 1e-6)

        # Active DoE suggestions must be populated
        self.assertEqual(len(rec.active_doe_suggestions), 3)
        rec_table = render_recommendation_table(rec)
        self.assertIn("高速效率优先档", rec_table)
        self.assertIn("高精轮廓优先档", rec_table)
        self.assertIn("柔顺均衡拐点档", rec_table)

    def test_cli_and_web_api_endpoints(self) -> None:
        client = TestClient(create_app(serve_frontend=False))

        # 1. GET parameter registry
        reg_resp = client.get("/api/v1/benchmarks/cnc/parameter-registry")
        self.assertEqual(reg_resp.status_code, 200)
        self.assertEqual(len(reg_resp.json()["parameters"]), 32)

        # 2. GET DoE plan
        doe_resp = client.get("/api/v1/benchmarks/cnc/param-doe?offlineCount=8&controllerCount=4&seed=11")
        self.assertEqual(doe_resp.status_code, 200)
        self.assertEqual(len(doe_resp.json()["offlineSamples"]), 8)
        self.assertEqual(len(doe_resp.json()["controllerSamples"]), 4)

        # 3. POST single evaluation
        ex = cnc_benchmark_example()
        eval_resp = client.post(
            "/api/v1/benchmarks/cnc/evaluate",
            json={
                "case": ex.case.model_dump(mode="json", by_alias=True, exclude_none=True),
                "export": ex.baseline.model_dump(mode="json", by_alias=True, exclude_none=True),
            },
        )
        self.assertEqual(eval_resp.status_code, 200)
        self.assertEqual(eval_resp.json()["outcome"], "Passed")

        # 4. GET closed-loop demo
        demo_resp = client.get("/api/v1/benchmarks/cnc/param-demo?offlineCount=12&controllerCount=6&seed=21")
        self.assertEqual(demo_resp.status_code, 200)
        demo_json = demo_resp.json()
        self.assertEqual(len(demo_json["recommendationReport"]["presets"]), 3)

        # 5. CLI param-demo command
        exit_code = main(["param-demo", "--offline-count", "10", "--controller-count", "5", "--format", "table"])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
