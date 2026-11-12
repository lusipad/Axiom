"""Comprehensive verification suite for the Three-Layer CNC Grey-Box Evaluation, Calibration, Transfer & R0-R7 Governance System."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

import axiom
from axiom.benchmark import (
    AXES,
    BenchmarkArc,
    BenchmarkAxisLimits,
    BenchmarkSample,
    CncAlgorithmExport,
    CncBenchmarkCase,
    benchmark_case_hash,
    evaluate_cnc_export,
)
from axiom.benchmark_standard import StandardCaseSettings, standard_case, standard_cases
from axiom.cli import main
from axiom.cnc_governance import (
    CNC_EXPORT_TO_ORDERED_POINT_ADAPTER_ID,
    CNC_GREYBOX_DOMAIN_PACK_ID,
    adapt_r3_telemetry_to_cnc_export,
    assess_cnc_greybox_governance,
)
from axiom.greybox_model import extract_case_geometry_profile, simulate_realistic_cnc_controller
from axiom.parameter_learner import (
    EXTENDED_TARGET_METRICS,
    learn_parameter_surrogate,
    predict_metric_for_parameters,
    render_parameter_impact_table,
)
from axiom.parameter_recommender import (
    ParameterRecommendationRequest,
    build_cnc_parameter_closed_loop_demo,
    recommend_parameters,
)
from axiom.parameter_space import default_cnc_parameter_registry, default_parameter_values, generate_parameter_doe
from axiom.web import create_app


class CncGreyBoxModelingTests(unittest.TestCase):
    def test_frenet_decomposition_separates_tangential_lag_from_normal_error_and_detects_resonance(self) -> None:
        settings = StandardCaseSettings(sample_period_seconds=0.001)
        line_case = standard_case("line", settings)
        samples = tuple(
            BenchmarkSample(
                sampleIndex=i,
                t=round(i * 0.001, 9),
                positionMm=(round(min(50.0, i * 0.05), 7), 0.0, 0.0),
                actualPositionMm=(round(max(0.0, min(50.0, i * 0.05) - (0.025 if 0 < i < 1000 else 0.0)), 7), 0.0, 0.0),
            )
            for i in range(1001)
        )
        line_exp = CncAlgorithmExport(
            algorithmId="test.frenet",
            algorithmVersion="v1",
            sourceKind="controller-trace",
            caseContentHash=benchmark_case_hash(line_case),
            coordinateFrame=line_case.coordinate_frame,
            unit="mm",
            samplePeriodSeconds=line_case.sample_period_seconds,
            samples=samples,
        )
        rep_line = evaluate_cnc_export(line_case, line_exp)
        assert rep_line.servo_metrics is not None
        self.assertAlmostEqual(rep_line.servo_metrics["tangentialLagMaxMm"].value or 0.0, 0.025, places=4)
        self.assertAlmostEqual(rep_line.servo_metrics["normalServoErrorMaxMm"].value or 0.0, 0.0, places=6)
        self.assertAlmostEqual(rep_line.servo_metrics["actualPathDeviationMaxMm"].value or 0.0, 0.0, places=6)

        circle_case = standard_case("circle", StandardCaseSettings(sample_period_seconds=0.001))
        reg = default_cnc_parameter_registry()
        p_res = default_parameter_values(reg)
        p_res["g3.notch_filter_freq_hz"] = 280.0
        p_res["g2.fir_moving_avg_time_ms"] = 2.0
        p_res["g2.path_tangential_jerk_mm_s3"] = 750_000.0
        circle_exp = simulate_realistic_cnc_controller(
            circle_case,
            p_res,
            source_kind="controller-trace",
            registry=reg,
            machine_resonance_hz=115.0,
        )
        rep_circle = evaluate_cnc_export(circle_case, circle_exp)
        assert rep_circle.servo_metrics is not None
        dom_f = rep_circle.servo_metrics["dominantResonanceFreqHz"].value or 0.0
        self.assertTrue(95.0 <= dom_f <= 135.0, f"Expected resonance near 115 Hz, got {dom_f}")
        self.assertLess(rep_circle.servo_metrics["signedRadialOffsetMeanMm"].value or 0.0, 0.0)

    def test_greybox_eliminates_z_axis_hallucination_on_2d_and_activates_z_on_3d_helix(self) -> None:
        reg = default_cnc_parameter_registry()
        settings = StandardCaseSettings(
            feed_mm_min=12000.0,
            maximum_acceleration_mm_s2=3000.0,
            sample_period_seconds=0.002,
            maximum_path_deviation_mm=0.06,
        )
        micro_case = standard_case("small-segments", settings)

        doe = generate_parameter_doe(reg, offline_count=12, controller_count=0, seed=19, mode="orthogonal-greybox")
        exports = [
            simulate_realistic_cnc_controller(micro_case, s.parameters, source_kind="algorithm-export", registry=reg)
            for s in doe.offline_samples
        ]
        surrogate = learn_parameter_surrogate(micro_case, exports, registry=reg)

        # 1. Pure XY toolpath must NOT hallucinate Z-axis limits as Active!
        self.assertNotIn("g2.axis_vel_limit_z", surrogate.global_active_parameter_ids)
        self.assertNotIn("g2.axis_acc_limit_z", surrogate.global_active_parameter_ids)

        # 2. Hard min-clipping dead-zone plateau check on lookahead_block_count
        base_p = default_parameter_values(reg)
        t_starved, _, _ = predict_metric_for_parameters(
            surrogate, "durationSeconds", {**base_p, "g1.lookahead_block_count": 20.0}
        )
        t_240, _, _ = predict_metric_for_parameters(
            surrogate, "durationSeconds", {**base_p, "g1.lookahead_block_count": 240.0}
        )
        t_480, _, _ = predict_metric_for_parameters(
            surrogate, "durationSeconds", {**base_p, "g1.lookahead_block_count": 480.0}
        )
        self.assertGreater(t_starved, t_240 + 0.02)
        self.assertLessEqual(abs(t_480 - t_240) / max(t_240, 1e-6), 0.03)

        # 3. 3D helical ramp MUST recognize Z-axis motion and clamp Z-axis speed bottleneck accurately
        helix_case = CncBenchmarkCase(
            caseId="test.3d-helix",
            coordinateFrame="workpiece",
            unit="mm",
            samplePeriodSeconds=0.002,
            programmedFeedMmMin=9000.0,
            referencePath=((0.0, 0.0, 0.0), (20.0, 0.0, 30.0), (40.0, 20.0, 60.0)),
            axisLimits=tuple(
                BenchmarkAxisLimits(
                    axis=ax,
                    minimumPositionMm=-200.0,
                    maximumPositionMm=200.0,
                    maximumVelocityMmS=500.0,
                    maximumAccelerationMmS2=5000.0,
                    maximumJerkMmS3=500_000.0,
                )
                for ax in AXES
            ),
            maximumPathDeviationMm=0.08,
            maximumEndpointErrorMm=0.002,
        )
        prof_helix = extract_case_geometry_profile(helix_case)
        self.assertTrue(prof_helix.has_z_motion)
        t_fast_z, _, _ = predict_metric_for_parameters(
            surrogate, "durationSeconds", {**base_p, "g2.axis_vel_limit_z": 350.0}, target_case=helix_case
        )
        t_slow_z, _, _ = predict_metric_for_parameters(
            surrogate, "durationSeconds", {**base_p, "g2.axis_vel_limit_z": 40.0}, target_case=helix_case
        )
        self.assertGreater(t_slow_z, t_fast_z + 0.25)

    def test_small_sample_multicase_calibration_loco_and_zeroshot_unseen_part_transfer(self) -> None:
        reg = default_cnc_parameter_registry()
        settings = StandardCaseSettings(sample_period_seconds=0.002, maximum_path_deviation_mm=0.06)
        suite_cases = standard_cases(settings)
        suite_map = {c.case_id: c for c in suite_cases}

        doe = generate_parameter_doe(reg, offline_count=10, controller_count=6, seed=101, mode="orthogonal-greybox")
        exports = []
        for s in doe.offline_samples:
            c_use = suite_map[s.recommended_case_id or "axiom.v1.corner90"]
            exports.append(simulate_realistic_cnc_controller(c_use, s.parameters, source_kind="algorithm-export", registry=reg))
        for s in doe.controller_samples:
            c_use = suite_map[s.recommended_case_id or "axiom.v1.circle"]
            exports.append(simulate_realistic_cnc_controller(c_use, s.parameters, source_kind="controller-trace", registry=reg))

        surrogate = learn_parameter_surrogate(
            suite_cases,
            exports,
            registry=reg,
            target_metrics=EXTENDED_TARGET_METRICS,
        )
        self.assertEqual(len(surrogate.calibrated_case_ids), 5)
        self.assertIsNotNone(surrogate.cross_toolpath_validation)
        assert surrogate.cross_toolpath_validation is not None
        self.assertEqual(surrogate.cross_toolpath_validation.evaluated_case_count, 5)
        self.assertLess(surrogate.cross_toolpath_validation.mean_duration_mape_pct, 8.0)
        table_txt = render_parameter_impact_table(surrogate)
        self.assertIn("物理辨识", table_txt)
        self.assertIn("跨刀路留一验证 LOCO", table_txt)
        self.assertIn("normalServoErrorMaxMm", surrogate.metric_heads)

        unseen_part = CncBenchmarkCase(
            caseId="customer.pocket-contour-part-v1",
            coordinateFrame="workpiece",
            unit="mm",
            samplePeriodSeconds=0.002,
            programmedFeedMmMin=3600.0,
            referencePath=(
                (0.0, 0.0, 0.0),
                (35.0, 0.0, 0.0),
                (35.0, 25.0, 0.0),
                (23.0, 37.0, 0.0),
                (0.0, 37.0, 0.0),
            ),
            referenceArcs=(BenchmarkArc(segmentIndex=2, centerMm=(23.0, 25.0), direction="ccw"),),
            axisLimits=tuple(
                BenchmarkAxisLimits(
                    axis=ax,
                    minimumPositionMm=-500.0,
                    maximumPositionMm=500.0,
                    maximumVelocityMmS=500.0,
                    maximumAccelerationMmS2=6000.0,
                    maximumJerkMmS3=600_000.0,
                )
                for ax in AXES
            ),
            maximumPathDeviationMm=0.05,
            maximumEndpointErrorMm=0.002,
        )

        probe_params = default_parameter_values(reg)
        probe_params["g1.corner_tolerance_mm"] = 0.030
        probe_params["g2.fir_moving_avg_time_ms"] = 18.0
        probe_params["g3.servo_kp_x"] = 50.0
        probe_params["g3.servo_kp_y"] = 80.0

        pred_dur, _, _ = predict_metric_for_parameters(surrogate, "durationSeconds", probe_params, target_case=unseen_part)
        pred_act_err, _, _ = predict_metric_for_parameters(
            surrogate, "actualPathDeviationMaxMm", probe_params, target_case=unseen_part
        )

        gt_export = simulate_realistic_cnc_controller(unseen_part, probe_params, source_kind="controller-trace", registry=reg)
        gt_rep = evaluate_cnc_export(unseen_part, gt_export)
        assert gt_rep.servo_metrics is not None
        gt_dur = gt_rep.kinematic_summary["durationSeconds"]
        gt_act_err = gt_rep.servo_metrics["actualPathDeviationMaxMm"].value or 0.0

        self.assertLess(abs(pred_dur - gt_dur) / max(gt_dur, 1e-6), 0.15)
        self.assertLess(abs(pred_act_err - gt_act_err), 0.012)

        rec_unseen = recommend_parameters(
            surrogate,
            ParameterRecommendationRequest(
                baselineParameters=probe_params,
                maxChangedParameters=4,
                maximumPathDeviationMm=0.040,
                maximumActualPathDeviationMm=0.045,
                seed=77,
            ),
            target_case=unseen_part,
        )
        self.assertEqual(rec_unseen.case_id, "customer.pocket-contour-part-v1")
        preset_ids = {p.candidate_id for p in rec_unseen.presets}
        self.assertGreaterEqual(len(preset_ids), 2)
        prec_preset = next(p for p in rec_unseen.presets if p.preset_role == "PrecisionOptimal")
        verified_exp = simulate_realistic_cnc_controller(
            unseen_part, prec_preset.full_parameters, source_kind="controller-trace", registry=reg
        )
        verified_rep = evaluate_cnc_export(unseen_part, verified_exp)
        assert verified_rep.servo_metrics is not None
        verified_err = verified_rep.servo_metrics["actualPathDeviationMaxMm"].value or 0.0
        self.assertLess(verified_err, gt_act_err)

    def test_r0_to_r7_governance_bridge_r3_adapter_cli_and_web_api(self) -> None:
        # 1. DomainPack & ArtifactAdapter registration in core Axiom catalog
        pack_ids = {p.domain_pack_id for p in axiom.list_domain_packs()}
        adapter_ids = {a.adapter_id for a in axiom.list_artifact_adapters()}
        self.assertIn(CNC_GREYBOX_DOMAIN_PACK_ID, pack_ids)
        self.assertIn(CNC_EXPORT_TO_ORDERED_POINT_ADAPTER_ID, adapter_ids)

        # 2. Closed-loop demo produces 3 distinct presets & passes all sealed R0-R7 governance claims
        demo = build_cnc_parameter_closed_loop_demo(offline_count=16, controller_count=8, seed=42, multi_case_calibration=True)
        preset_cands = [p.candidate_id for p in demo.recommendation_report.presets]
        self.assertEqual(len(set(preset_cands)), 3, f"Expected 3 distinct Pareto presets, got {preset_cands}")
        eff_p, prec_p, _ = demo.recommendation_report.presets
        self.assertLess(
            eff_p.predicted_metrics["durationSeconds"].predicted_mean,
            prec_p.predicted_metrics["durationSeconds"].predicted_mean,
        )
        self.assertLessEqual(
            prec_p.predicted_metrics["actualPathDeviationMaxMm"].predicted_mean,
            eff_p.predicted_metrics["actualPathDeviationMaxMm"].predicted_mean,
        )

        gov = assess_cnc_greybox_governance(demo)
        self.assertEqual(gov.permission_ceiling, "OfflineAdvisory")
        self.assertFalse(gov.device_write_allowed)
        self.assertEqual(gov.deployment_shadow_status, "Open")
        self.assertEqual(gov.device_safety_status, "NotAssessed")
        self.assertEqual(gov.run_bundle.report.case_outcome.value, "Passed")
        claim_map = {c.claim_definition_id: c.status.value for c in gov.run_bundle.claims}
        self.assertEqual(claim_map["cnc-greybox.sampled-limits-claim@1"], "Supported")
        self.assertEqual(claim_map["cnc-greybox.r4-calibration-claim@1"], "Supported")
        self.assertEqual(claim_map["cnc-greybox.r5-epistemic-claim@1"], "Supported")
        self.assertEqual(claim_map["cnc-greybox.r7-zero-write-advisory-claim@1"], "Supported")

        # 3. ArtifactAdapter provenance check (CncAlgorithmExport -> OrderedPointSequence)
        adapter = axiom.get_artifact_adapter("cnc.algorithm-export", "ordered-point-sequence")
        transformed = adapter.adapt(demo.sample_quality_report.analysis.sample_count and simulate_realistic_cnc_controller(demo.case, demo.surrogate.baseline_parameters))
        self.assertEqual(transformed.artifact.artifact_type, "ordered-point-sequence")
        self.assertIn("positionMm", transformed.provenance.preserved_semantics)

        # 4. R3 telemetry -> CNC controller-trace bridge & write-operation blocking
        line_case = standard_case("line", StandardCaseSettings(sample_period_seconds=0.002))
        r3_payload = {
            "schemaVersion": 1,
            "artifactType": "machine.telemetry-trace",
            "traceId": "r3.cnc.bridge.01",
            "sourceKind": "controller-export",
            "deviceIdentity": {
                "deviceId": "mch-01",
                "controllerFamily": "TwinCAT-3",
                "machineModel": "VMC-850",
            },
            "captureReceipt": {
                "receiptId": "rcpt-01",
                "sourceId": "axiom.windows-file-telemetry-source@1",
                "operation": "file-import",
                "transport": "windows-file-json",
                "capturedAt": "2026-11-11T12:00:00Z",
                "traceContentHash": "a" * 64,
            },
            "frames": [
                {
                    "sequenceId": k,
                    "deviceTimestamp": f"2026-11-11T12:00:00.{k * 2:03d}Z",
                    "samples": [
                        {"channelId": "cmd_x", "value": k * 0.1, "quality": "good"},
                        {"channelId": "cmd_y", "value": 0.0, "quality": "good"},
                        {"channelId": "cmd_z", "value": 0.0, "quality": "good"},
                        {"channelId": "act_x", "value": max(0.0, k * 0.1 - 0.005), "quality": "good"},
                        {"channelId": "act_y", "value": 0.0, "quality": "good"},
                        {"channelId": "act_z", "value": 0.0, "quality": "good"},
                    ],
                }
                for k in range(6)
            ],
        }
        cnc_from_r3 = adapt_r3_telemetry_to_cnc_export(r3_payload, line_case)
        self.assertEqual(cnc_from_r3.source_kind, "controller-trace")
        self.assertEqual(len(cnc_from_r3.samples), 6)

        # CLI & FastAPI governance endpoint check
        client = TestClient(create_app(serve_frontend=False))
        resp = client.get("/api/v1/benchmarks/cnc/param-governance?offlineCount=12&controllerCount=6&multiCase=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["runBundle"]["report"]["caseOutcome"], "Passed")
        with TemporaryDirectory() as td:
            rc = main(["param-governance", "--offline-count", "12", "--controller-count", "6", "--multi-case"])
            self.assertEqual(rc, 0)
            _ = Path(td)
            _ = json


if __name__ == "__main__":
    unittest.main()
