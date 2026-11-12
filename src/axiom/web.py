from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from .adapters import list_artifact_adapters
from .benchmark import (
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncBenchmarkReport,
    CncBenchmarkRequest,
    CncQualityReport,
    CncSingleEvaluationRequest,
    benchmark_case_hash,
    cnc_benchmark_example,
    compare_cnc_exports,
    evaluate_cnc_export,
)
from .controller_profile import (
    ControllerProfile,
    get_controller_profile,
    list_controller_profiles,
)
from .parameter_diagnoser import CncSingleRunDiagnosticReport, diagnose_single_run
from .prediction_ledger import (
    PredictionVerificationLedger,
    append_prediction_verification_entry,
    build_prediction_verification_ledger,
    record_prediction_verification,
)
from .machine.models import MachineTelemetryTrace
from .parameter_learner import (
    LearnedParameterSurrogate,
    ParameterLearningRequest,
    learn_parameter_surrogate,
)
from .cnc_governance import CncGovernanceAssessmentReport, assess_cnc_greybox_governance
from .parameter_recommender import (
    CncParameterClosedLoopDemo,
    ParameterRecommendationReport,
    ParameterRecommendationRequest,
    build_cnc_parameter_closed_loop_demo,
    recommend_parameters,
)
from .parameter_space import (
    CncParameterRegistry,
    ParameterDoePlan,
    default_cnc_parameter_registry,
    generate_parameter_doe,
)
from .control import (
    BECKHOFF_WITNESS_PLC_TEMPLATE_FILE,
    BeckhoffWitnessDeploymentReport,
    BeckhoffWitnessDeploymentRequest,
    R7BAssessmentRequest,
    R7BExamplePayload,
    R7BManifest,
    R7BScenarioSummary,
    R7CAssessmentRequest,
    R7CExamplePayload,
    R7CManifest,
    R7CScenarioSummary,
    R7DAssessmentRequest,
    R7DExamplePayload,
    R7DManifest,
    R7DScenarioSummary,
    R7EAssessmentRequest,
    R7EExamplePayload,
    R7EManifest,
    R7EScenarioSummary,
    R7ExamplePayload,
    R7Manifest,
    R7ReplayRequest,
    R7ScenarioSummary,
    assess_beckhoff_witness_deployment,
    build_default_beckhoff_witness_deployment_request,
    read_beckhoff_witness_plc_template,
)
from .domain import list_domain_packs
from .experiment import contour_ab_example, run_experiment
from .field_evidence import (
    FieldEvidenceAssessmentReport,
    FieldEvidenceAssessmentRequest,
    assess_field_evidence,
)
from .five_axis import (
    F1ExamplePayload,
    F1MathStageManifest,
    F2ExamplePayload,
    F2MathStageManifest,
    F3ExamplePayload,
    F3MathStageManifest,
    F4ExamplePayload,
    F4MathStageManifest,
    MathStageManifest,
    build_f1_manifest,
    build_f2_manifest,
    build_f3_manifest,
    build_f4_manifest,
    f0_example_run_spec,
    f1_example_payload,
    f2_example_payload,
    f3_example_payload,
    f4_example_payload,
    list_f1_scenarios,
    list_f2_scenarios,
    list_f3_scenarios,
    list_f4_scenarios,
    load_f0_manifest,
)
from .intelligence import (
    R5BExamplePayload,
    R5BManifest,
    R5BScenarioSummary,
    R5ExamplePayload,
    R5Manifest,
    R5ScenarioSummary,
    RealHoldoutIntakeReport,
    RealHoldoutIntakeRequest,
    assess_real_holdout_intake,
)
from .machine import (
    list_machine_r3_scenarios,
    load_machine_r3_manifest,
    machine_r3_example_payload,
)
from .models import ExperimentReport, ExperimentSpec, RunBundle, RunSpec
from .optimization import (
    OptimizationSearchRequest,
    R6ExamplePayload,
    R6Manifest,
    R6ScenarioSummary,
)
from .physical import (
    PhysicalR4ExamplePayload,
    PhysicalR4Manifest,
    PhysicalR4ScenarioSummaryPayload,
    R41AssessmentRequest,
    R41ExamplePayload,
    R41Manifest,
    R41ScenarioSummary,
)
from .run import evaluate_run
from .runtime import find_domain_runtime_binding
from .subjects import list_subjects


def _package_version() -> str:
    try:
        return version("axiom-evaluator")
    except PackageNotFoundError:
        return "0.0.0"


def _load_physical_r4_api() -> Any:
    try:
        return import_module("axiom.physical")
    except ModuleNotFoundError as exc:
        if exc.name != "axiom.physical":
            raise
        raise HTTPException(
            status_code=503,
            detail="Physical R4 API is unavailable.",
        ) from exc


def _load_intelligence_r5_api() -> Any:
    try:
        return import_module("axiom.intelligence")
    except ModuleNotFoundError as exc:
        if exc.name != "axiom.intelligence":
            raise
        raise HTTPException(
            status_code=503,
            detail="Intelligence R5 API is unavailable.",
        ) from exc


def _load_optimization_r6_api() -> Any:
    try:
        return import_module("axiom.optimization")
    except ModuleNotFoundError as exc:
        if exc.name != "axiom.optimization":
            raise
        raise HTTPException(
            status_code=503,
            detail="Optimization R6 API is unavailable.",
        ) from exc


def _load_control_r7_api() -> Any:
    try:
        return import_module("axiom.control")
    except ModuleNotFoundError as exc:
        if exc.name != "axiom.control":
            raise
        raise HTTPException(
            status_code=503, detail="Control R7 API is unavailable."
        ) from exc


def _seal_r3_trace_for_workbench(
    case: CncBenchmarkCase,
    export: CncAlgorithmExport,
    *,
    trace_id: str,
    receipt_id: str,
    actual_y_bias_mm: float = 0.0,
) -> MachineTelemetryTrace:
    from .machine.runtime import machine_trace_content_hash

    t0 = datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc)
    dt = case.sample_period_seconds
    frames = []
    for k, s in enumerate(export.samples):
        act = s.actual_position_mm or s.position_mm
        ts = (t0 + timedelta(seconds=round(k * dt, 6))).isoformat().replace("+00:00", "Z")
        frames.append(
            {
                "sequenceId": k,
                "deviceTimestamp": ts,
                "samples": [
                    {"channelId": "cmd_x", "value": float(s.position_mm[0]), "quality": "good"},
                    {"channelId": "cmd_y", "value": float(s.position_mm[1]), "quality": "good"},
                    {"channelId": "cmd_z", "value": float(s.position_mm[2]), "quality": "good"},
                    {"channelId": "act_x", "value": float(act[0]), "quality": "good"},
                    {"channelId": "act_y", "value": float(act[1]) + actual_y_bias_mm, "quality": "good"},
                    {"channelId": "act_z", "value": float(act[2]), "quality": "good"},
                ],
            }
        )
    raw = {
        "schemaVersion": 1,
        "artifactType": "machine.telemetry-trace",
        "traceId": trace_id,
        "sourceKind": "controller-export",
        "deviceIdentity": {
            "deviceId": "vmc-850-shopfloor-01",
            "controllerFamily": "SINUMERIK-840D-sl",
            "machineModel": "VMC-850",
        },
        "captureReceipt": {
            "receiptId": receipt_id,
            "sourceId": "axiom.windows-file-telemetry-source@1",
            "operation": "file-import",
            "transport": "windows-file-json",
            "capturedAt": "2026-11-12T10:05:00Z",
            "traceContentHash": "0" * 64,
        },
        "frames": frames,
    }
    unsigned = MachineTelemetryTrace.model_validate(raw)
    raw["captureReceipt"]["traceContentHash"] = machine_trace_content_hash(unsigned)
    return MachineTelemetryTrace.model_validate(raw)


def _downsample_preview(
    case: CncBenchmarkCase,
    export: CncAlgorithmExport,
    *,
    magnification: float = 80.0,
    max_points: int = 220,
) -> dict[str, Any]:
    ref_pts = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in case.reference_path]
    n = len(export.samples)
    stride = max(1, n // max_points)
    cmd_pts: list[list[float]] = []
    act_mag_pts: list[list[float]] = []
    for idx in range(0, n, stride):
        s = export.samples[idx]
        cx, cy = float(s.position_mm[0]), float(s.position_mm[1])
        ax, ay = (
            (float(s.actual_position_mm[0]), float(s.actual_position_mm[1]))
            if s.actual_position_mm is not None
            else (cx, cy)
        )
        cmd_pts.append([round(cx, 4), round(cy, 4)])
        act_mag_pts.append(
            [
                round(cx + (ax - cx) * magnification, 4),
                round(cy + (ay - cy) * magnification, 4),
            ]
        )
    if (n - 1) % stride != 0 and n > 0:
        s = export.samples[-1]
        cx, cy = float(s.position_mm[0]), float(s.position_mm[1])
        ax, ay = (
            (float(s.actual_position_mm[0]), float(s.actual_position_mm[1]))
            if s.actual_position_mm is not None
            else (cx, cy)
        )
        cmd_pts.append([round(cx, 4), round(cy, 4)])
        act_mag_pts.append(
            [
                round(cx + (ax - cx) * magnification, 4),
                round(cy + (ay - cy) * magnification, 4),
            ]
        )
    return {
        "magnification": magnification,
        "reference": ref_pts,
        "command": cmd_pts,
        "actualMagnified": act_mag_pts,
    }


@lru_cache(maxsize=1)
def _build_cnc_param_workbench_bundle() -> dict[str, Any]:
    from .benchmark_standard import standard_case
    from .greybox_model import simulate_realistic_cnc_controller
    from .parameter_space import default_parameter_values

    preferred_order = {
        "siemens-sinumerik-840d@1": 0,
        "beckhoff-twincat-nc@1": 1,
        "generic-fir-biquad@1": 2,
    }
    profiles = sorted(
        list_controller_profiles(),
        key=lambda p: preferred_order.get(p.profile_id, 99),
    )

    scenario_specs = (
        {
            "scenarioId": "resonance-circle",
            "title": "整圆精铣 · 142 Hz 导轨共振与过象限突起",
            "subtitle": "典型精加工故障：圆弧表面高频振纹 + 90°/180° 换向静摩擦尖峰",
            "caseName": "circle",
            "badgeTone": "danger",
            "resonanceHz": 142.0,
            "magnification": 120.0,
            "overrides": {
                "siemens-sinumerik-840d@1": {
                    "sinumerik.md32410_ax_jerk_time_s": 0.002,
                    "sinumerik.sinamics_p1417_notch_hz": 290.0,
                    "sinumerik.md32520_quad_fric_mm": 0.0,
                    "sinumerik.md32200_posctrl_gain_x": 4.8,
                    "sinumerik.md32200_posctrl_gain_y": 2.6,
                },
                "beckhoff-twincat-nc@1": {
                    "tc.moving_avg_filter_s": 0.002,
                    "tc.ax5000_notch_hz": 290.0,
                    "tc.quadrant_comp_um_xy": 0.0,
                    "tc.kv_factor_x_m_min_mm": 4.8,
                    "tc.kv_factor_y_m_min_mm": 2.6,
                },
                "generic-fir-biquad@1": {
                    "g2.fir_moving_avg_time_ms": 2.0,
                    "g3.notch_filter_freq_hz": 290.0,
                    "g3.friction_comp_amp_x": 0.0,
                    "g3.friction_comp_amp_y": 0.0,
                    "g3.servo_kp_x": 80.0,
                    "g3.servo_kp_y": 44.0,
                },
            },
        },
        {
            "scenarioId": "corner-overshoot",
            "title": "90° 直角轮廓 · 拐角内缩超差",
            "subtitle": "典型开粗转半精问题：连续路径平滑公差与滤波窗口过大导致清根圆化",
            "caseName": "corner90",
            "badgeTone": "warning",
            "resonanceHz": 185.0,
            "magnification": 40.0,
            "overrides": {
                "siemens-sinumerik-840d@1": {
                    "sinumerik.cycle832_contour_tol_mm": 0.065,
                    "sinumerik.md32410_ax_jerk_time_s": 0.022,
                },
                "beckhoff-twincat-nc@1": {
                    "tc.contour_blend_tol_um": 65.0,
                    "tc.moving_avg_filter_s": 0.022,
                },
                "generic-fir-biquad@1": {
                    "g1.corner_tolerance_mm": 0.065,
                    "g2.fir_moving_avg_time_ms": 22.0,
                },
            },
        },
        {
            "scenarioId": "headroom-scurve",
            "title": "S 型自由曲面 · 精度充裕挖掘节拍裕量",
            "subtitle": "典型保守加工优化：轮廓偏差远低于工艺门限，可安全提升加速度缩短单件周期",
            "caseName": "s-curve",
            "badgeTone": "info",
            "resonanceHz": 190.0,
            "magnification": 60.0,
            "overrides": {
                "siemens-sinumerik-840d@1": {
                    "sinumerik.cycle832_contour_tol_mm": 0.006,
                    "sinumerik.md32300_max_ax_acc_m_s2": 2.2,
                    "sinumerik.md32410_ax_jerk_time_s": 0.005,
                },
                "beckhoff-twincat-nc@1": {
                    "tc.contour_blend_tol_um": 6.0,
                    "tc.path_acc_m_s2": 2.2,
                    "tc.moving_avg_filter_s": 0.005,
                },
                "generic-fir-biquad@1": {
                    "g1.corner_tolerance_mm": 0.006,
                    "g2.path_tangential_acc_mm_s2": 2200.0,
                    "g2.fir_moving_avg_time_ms": 5.0,
                },
            },
        },
    )

    diagnostic_scenarios = []
    for spec in scenario_specs:
        case_obj = standard_case(str(spec["caseName"]))
        reports_by_profile: dict[str, Any] = {}
        preview_payload: dict[str, Any] | None = None
        for prof in profiles:
            params = default_parameter_values(prof.registry)
            params.update(spec["overrides"].get(prof.profile_id, {}))
            exp = simulate_realistic_cnc_controller(
                case_obj,
                params,
                source_kind="controller-trace",
                machine_resonance_hz=float(spec["resonanceHz"]),
                controller_profile=prof,
                algorithm_version="trace@1",
            ).model_copy(update={"algorithm_id": "shopfloor.captured-trace"})
            if preview_payload is None:
                preview_payload = _downsample_preview(
                    case_obj, exp, magnification=float(spec["magnification"])
                )
            diag_full = diagnose_single_run(
                case_obj, exp, parameters=params, controller_profile=prof, include_drive_side=True
            )
            diag_nc = diagnose_single_run(
                case_obj, exp, parameters=params, controller_profile=prof, include_drive_side=False
            )
            reports_by_profile[prof.profile_id] = {
                "full": diag_full.model_dump(mode="json", by_alias=True, exclude_none=True),
                "ncOnly": diag_nc.model_dump(mode="json", by_alias=True, exclude_none=True),
            }
        diagnostic_scenarios.append(
            {
                "scenarioId": spec["scenarioId"],
                "title": spec["title"],
                "subtitle": spec["subtitle"],
                "caseId": case_obj.case_id,
                "badgeTone": spec["badgeTone"],
                "preview": preview_payload,
                "reportsByProfile": reports_by_profile,
            }
        )

    def _compact_governance(gov: CncGovernanceAssessmentReport) -> dict[str, Any]:
        raw = gov.model_dump(mode="json", by_alias=True, exclude_none=True)
        rb = raw.get("runBundle")
        if isinstance(rb, dict):
            rb = dict(rb)
            rb.pop("runSpec", None)
            if "observation" in rb and isinstance(rb["observation"], dict):
                obs = dict(rb["observation"])
                obs.pop("artifact", None)
                rb["observation"] = obs
            raw["runBundle"] = rb
        return raw

    # Build 3 governance & prediction-ledger states
    gov_demo = build_cnc_parameter_closed_loop_demo(
        offline_count=18, controller_count=10, seed=42, multi_case_calibration=True
    )
    sur = gov_demo.surrogate

    gov_unverified = assess_cnc_greybox_governance(gov_demo)

    ok_entries = []
    drift_entries = []
    for idx, cname in enumerate(("corner90", "circle", "s-curve"), 1):
        c = standard_case(cname)
        rec_c = recommend_parameters(
            sur,
            ParameterRecommendationRequest(
                targetCase=c,
                maximumPathDeviationMm=0.055,
                maximumActualPathDeviationMm=0.065,
                seed=10 + idx,
            ),
        )
        chosen = rec_c.presets[0]
        base_exp = simulate_realistic_cnc_controller(
            c,
            sur.baseline_parameters,
            source_kind="controller-trace",
            registry=sur.registry,
            controller_profile=sur.controller_profile,
        )
        ver_raw = simulate_realistic_cnc_controller(
            c,
            chosen.full_parameters,
            source_kind="controller-trace",
            registry=sur.registry,
            controller_profile=sur.controller_profile,
        )
        r3_ok = _seal_r3_trace_for_workbench(
            c, ver_raw, trace_id=f"r3.ok.{idx}", receipt_id=f"rcpt.ok.{idx}", actual_y_bias_mm=0.0
        )
        ok_entries.append(
            record_prediction_verification(
                c,
                sur,
                r3_ok,
                recommendation_report=rec_c,
                candidate_id=chosen.candidate_id,
                baseline_trace_or_report=base_exp,
                entry_id=f"cut.00{idx}.{cname}",
            )
        )
        r3_drift = _seal_r3_trace_for_workbench(
            c,
            ver_raw,
            trace_id=f"r3.drift.{idx}",
            receipt_id=f"rcpt.drift.{idx}",
            actual_y_bias_mm=0.085,
        )
        drift_entries.append(
            record_prediction_verification(
                c,
                sur,
                r3_drift,
                recommendation_report=rec_c,
                candidate_id=chosen.candidate_id,
                baseline_trace_or_report=base_exp,
                entry_id=f"drift.00{idx}.{cname}",
            )
        )

    ledger_ok = build_prediction_verification_ledger(
        tuple(ok_entries), surrogate=sur, ledger_id="cnc.ledger.r3-verified@1"
    )
    ledger_drift = build_prediction_verification_ledger(
        tuple(drift_entries), surrogate=sur, ledger_id="cnc.ledger.thermal-drift@1"
    )
    gov_promoted = assess_cnc_greybox_governance(gov_demo, verification_ledger=ledger_ok)
    gov_refuted = assess_cnc_greybox_governance(gov_demo, verification_ledger=ledger_drift)

    return {
        "controllerProfiles": [
            p.model_dump(mode="json", by_alias=True, exclude_none=True) for p in profiles
        ],
        "diagnosticScenarios": diagnostic_scenarios,
        "governanceScenarios": [
            {
                "stateId": "synthetic-only",
                "title": "阶段 A · 仅离线/合成建模（0/3 刀真机对账）",
                "subtitle": "尚未导入真机复切 R3 遥测，R4/R5 诚实保持 Inconclusive，拒绝合成自证",
                "badgeTone": "warning",
                "governance": _compact_governance(gov_unverified),
                "ledger": None,
            },
            {
                "stateId": "r3-promoted",
                "title": "阶段 B · 满 3 刀独立 R3 真机复切对账达标",
                "subtitle": "直角、整圆、S 曲线三刀独立复切误差均落在 95% 保守区间内，R4/R5 自动晋升 Supported",
                "badgeTone": "pass",
                "governance": _compact_governance(gov_promoted),
                "ledger": ledger_ok.model_dump(mode="json", by_alias=True, exclude_none=True),
            },
            {
                "stateId": "drift-refuted",
                "title": "阶段 C · 现场导轨热漂移失准预警（+0.085 mm 偏移）",
                "subtitle": "真机复切实测超出灰盒保守上限，台账自动捕获模型失准并将 R4/R5 判为 Refuted",
                "badgeTone": "danger",
                "governance": _compact_governance(gov_refuted),
                "ledger": ledger_drift.model_dump(mode="json", by_alias=True, exclude_none=True),
            },
        ],
    }


def create_app(*, serve_frontend: bool = True, frontend_dir: Path | None = None) -> FastAPI:
    package_version = _package_version()
    app = FastAPI(
        title="Axiom Experiment Workbench API",
        version=package_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": package_version}

    @app.get("/api/v1/catalog")
    def catalog() -> dict[str, Any]:
        return {
            "subjects": [
                subject.model_dump(mode="json", by_alias=True) for subject in list_subjects()
            ],
            "domainPacks": [
                {
                    **pack.model_dump(mode="json", by_alias=True),
                    "runtimeBound": find_domain_runtime_binding(pack.domain_pack_id) is not None,
                }
                for pack in list_domain_packs()
            ],
            "artifactAdapters": [
                {
                    "adapterId": adapter.adapter_id,
                    "sourceArtifactType": adapter.source_artifact_type,
                    "targetArtifactType": adapter.target_artifact_type,
                }
                for adapter in list_artifact_adapters()
            ],
        }

    @app.post(
        "/api/v1/runs/evaluate",
        response_model=RunBundle,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def execute_run(spec: RunSpec) -> RunBundle:
        return evaluate_run(spec)

    @app.get("/api/v1/examples/contour-ab", response_model=ExperimentSpec, response_model_by_alias=True)
    def contour_example() -> ExperimentSpec:
        return contour_ab_example()

    @app.get(
        "/api/v1/five-axis/f0/manifest",
        response_model=MathStageManifest,
        response_model_by_alias=True,
    )
    def five_axis_f0_manifest() -> MathStageManifest:
        return load_f0_manifest()

    @app.get(
        "/api/v1/examples/five-axis-f0",
        response_model=RunSpec,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f0_example() -> RunSpec:
        return RunSpec.model_validate(f0_example_run_spec())

    @app.get(
        "/api/v1/five-axis/f1/manifest",
        response_model=F1MathStageManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f1_manifest(scenarioId: str = "nominal-certified") -> F1MathStageManifest:
        try:
            return build_f1_manifest(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/five-axis/f1/scenarios")
    def five_axis_f1_scenarios() -> Any:
        return [scenario.to_dict() for scenario in list_f1_scenarios()]

    @app.get(
        "/api/v1/examples/five-axis-f1",
        response_model=F1ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def five_axis_f1_example(scenarioId: str = "nominal-certified") -> dict[str, Any]:
        try:
            return f1_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/five-axis/f2/manifest",
        response_model=F2MathStageManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f2_manifest(scenarioId: str = "canonical-table-table") -> F2MathStageManifest:
        try:
            return build_f2_manifest(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/five-axis/f2/scenarios")
    def five_axis_f2_scenarios() -> Any:
        return [scenario.to_dict() for scenario in list_f2_scenarios()]

    @app.get(
        "/api/v1/examples/five-axis-f2",
        response_model=F2ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def five_axis_f2_example(scenarioId: str = "canonical-table-table") -> dict[str, Any]:
        try:
            return f2_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/five-axis/f3/manifest",
        response_model=F3MathStageManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f3_manifest(
        scenarioId: str = "canonical-table-table-jerk",
    ) -> F3MathStageManifest:
        try:
            return build_f3_manifest(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/five-axis/f3/scenarios")
    def five_axis_f3_scenarios() -> Any:
        return [scenario.to_dict() for scenario in list_f3_scenarios()]

    @app.get(
        "/api/v1/examples/five-axis-f3",
        response_model=F3ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def five_axis_f3_example(
        scenarioId: str = "canonical-table-table-jerk",
    ) -> dict[str, Any]:
        try:
            return f3_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/five-axis/f4/manifest",
        response_model=F4MathStageManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def five_axis_f4_manifest(
        scenarioId: str = "canonical-dual-table-solver",
    ) -> F4MathStageManifest:
        try:
            return build_f4_manifest(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/five-axis/f4/scenarios")
    def five_axis_f4_scenarios() -> Any:
        return [scenario.to_dict() for scenario in list_f4_scenarios()]

    @app.get(
        "/api/v1/examples/five-axis-f4",
        response_model=F4ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def five_axis_f4_example(
        scenarioId: str = "canonical-dual-table-solver",
    ) -> dict[str, Any]:
        try:
            return f4_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/machine/r3/manifest")
    def machine_r3_manifest() -> dict[str, Any]:
        return load_machine_r3_manifest()

    @app.get("/api/v1/machine/r3/scenarios")
    def machine_r3_scenarios() -> Any:
        return list_machine_r3_scenarios()

    @app.get("/api/v1/examples/machine-r3")
    def machine_r3_example(
        scenarioId: str = "read-only-paired-pass",
    ) -> dict[str, Any]:
        try:
            return machine_r3_example_payload(scenarioId)
        except (FileNotFoundError, KeyError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/physical/r4/manifest",
        response_model=PhysicalR4Manifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def physical_r4_manifest() -> PhysicalR4Manifest:
        physical_api = _load_physical_r4_api()
        try:
            return physical_api.load_r4_manifest()
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Physical R4 manifest loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/physical/r4/scenarios",
        response_model=list[PhysicalR4ScenarioSummaryPayload],
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def physical_r4_scenarios() -> list[PhysicalR4ScenarioSummaryPayload]:
        physical_api = _load_physical_r4_api()
        try:
            return physical_api.list_r4_scenarios()
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Physical R4 scenario catalog is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/examples/physical-r4",
        response_model=PhysicalR4ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def physical_r4_example(
        scenarioId: str = "in-domain-synthetic-sil",
    ) -> PhysicalR4ExamplePayload:
        physical_api = _load_physical_r4_api()
        try:
            return physical_api.r4_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Physical R4 example payload loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/physical/r41/manifest",
        response_model=R41Manifest,
        response_model_by_alias=True,
    )
    def physical_r41_manifest() -> R41Manifest:
        return _load_physical_r4_api().build_r41_manifest()

    @app.get(
        "/api/v1/physical/r41/scenarios",
        response_model=list[R41ScenarioSummary],
        response_model_by_alias=True,
    )
    def physical_r41_scenarios() -> list[R41ScenarioSummary]:
        return list(_load_physical_r4_api().list_r41_scenarios())

    @app.get(
        "/api/v1/examples/physical-r41",
        response_model=R41ExamplePayload,
        response_model_by_alias=True,
    )
    def physical_r41_example(
        scenarioId: str = "physical-reality-evidence-open",
    ) -> R41ExamplePayload:
        try:
            return _load_physical_r4_api().r41_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/physical/r41/assess",
        response_model=R41ExamplePayload,
        response_model_by_alias=True,
    )
    def physical_r41_assess(request: R41AssessmentRequest) -> R41ExamplePayload:
        return _load_physical_r4_api().assess_r41_payload(request)

    @app.get(
        "/api/v1/intelligence/r5/manifest",
        response_model=R5Manifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5_manifest() -> R5Manifest:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return R5Manifest.model_validate(intelligence_api.build_r5_manifest())
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5 manifest loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/intelligence/r5/scenarios",
        response_model=list[R5ScenarioSummary],
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5_scenarios() -> list[R5ScenarioSummary]:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return list(intelligence_api.list_r5_scenarios())
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5 scenario catalog is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/examples/intelligence-r5",
        response_model=R5ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def intelligence_r5_example(
        scenarioId: str = "synthetic-residual-contract",
    ) -> R5ExamplePayload:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return R5ExamplePayload.model_validate(intelligence_api.r5_example_payload(scenarioId))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5 example payload loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/intelligence/r5b/manifest",
        response_model=R5BManifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5b_manifest() -> R5BManifest:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return R5BManifest.model_validate(intelligence_api.build_r5b_manifest())
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5-B manifest loader is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/intelligence/r5b/scenarios",
        response_model=list[R5BScenarioSummary],
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5b_scenarios() -> list[R5BScenarioSummary]:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return list(intelligence_api.list_r5b_scenarios())
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5-B scenario catalog is unavailable.",
            ) from exc

    @app.get(
        "/api/v1/examples/intelligence-r5b",
        response_model=R5BExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        response_model_exclude_unset=True,
    )
    def intelligence_r5b_example(
        scenarioId: str = "real-holdout-readiness-open",
    ) -> R5BExamplePayload:
        intelligence_api = _load_intelligence_r5_api()
        try:
            return R5BExamplePayload.model_validate(intelligence_api.r5b_example_payload(scenarioId))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AttributeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Intelligence R5-B example payload loader is unavailable.",
            ) from exc

    @app.post(
        "/api/v1/intelligence/r5b/intake/assess",
        response_model=RealHoldoutIntakeReport,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def intelligence_r5b_intake_assess(
        request: RealHoldoutIntakeRequest,
    ) -> RealHoldoutIntakeReport:
        return assess_real_holdout_intake(request)

    @app.get(
        "/api/v1/optimization/r6/manifest",
        response_model=R6Manifest,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def optimization_r6_manifest() -> R6Manifest:
        optimization_api = _load_optimization_r6_api()
        return optimization_api.build_r6_manifest()

    @app.get(
        "/api/v1/optimization/r6/scenarios",
        response_model=list[R6ScenarioSummary],
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def optimization_r6_scenarios() -> list[R6ScenarioSummary]:
        optimization_api = _load_optimization_r6_api()
        return list(optimization_api.list_r6_scenarios())

    @app.get(
        "/api/v1/examples/optimization-r6",
        response_model=R6ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def optimization_r6_example(
        scenarioId: str = "canonical-head-table-offline-pareto",
    ) -> R6ExamplePayload:
        optimization_api = _load_optimization_r6_api()
        try:
            return optimization_api.r6_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/optimization/r6/search",
        response_model=R6ExamplePayload,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def optimization_r6_search(search_request: OptimizationSearchRequest) -> R6ExamplePayload:
        optimization_api = _load_optimization_r6_api()
        recommendations = optimization_api.search_recommendations(search_request)
        scenario = optimization_api.list_r6_scenarios()[0]
        run_spec = optimization_api.build_r6_run_spec(search_request)
        return R6ExamplePayload(
            manifest=optimization_api.build_r6_manifest(),
            scenario=scenario,
            searchRequest=search_request,
            recommendationSet=recommendations,
            runSpec=run_spec.model_dump(mode="json", by_alias=True, exclude_none=True),
        )

    @app.get(
        "/api/v1/control/r7/manifest",
        response_model=R7Manifest,
        response_model_by_alias=True,
    )
    def control_r7_manifest() -> R7Manifest:
        return _load_control_r7_api().build_r7_manifest()

    @app.get(
        "/api/v1/control/r7/scenarios",
        response_model=list[R7ScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7_scenarios() -> list[R7ScenarioSummary]:
        return list(_load_control_r7_api().list_r7_scenarios())

    @app.get(
        "/api/v1/examples/control-r7",
        response_model=R7ExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7_example(
        scenarioId: str = "synthetic-shadow-nominal",
    ) -> R7ExamplePayload:
        try:
            return _load_control_r7_api().r7_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7/replay",
        response_model=R7ExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7_replay(request: R7ReplayRequest) -> R7ExamplePayload:
        try:
            return _load_control_r7_api().r7_example_payload(request.scenario_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/api/v1/control/r7b/manifest",
        response_model=R7BManifest,
        response_model_by_alias=True,
    )
    def control_r7b_manifest() -> R7BManifest:
        return _load_control_r7_api().build_r7b_manifest()

    @app.get(
        "/api/v1/control/r7b/scenarios",
        response_model=list[R7BScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7b_scenarios() -> list[R7BScenarioSummary]:
        return list(_load_control_r7_api().list_r7b_scenarios())

    @app.get(
        "/api/v1/examples/control-r7b",
        response_model=R7BExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7b_example(
        scenarioId: str = "deployment-shadow-readiness-open",
    ) -> R7BExamplePayload:
        try:
            return _load_control_r7_api().r7b_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7b/assess",
        response_model=R7BExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7b_assess(request: R7BAssessmentRequest) -> R7BExamplePayload:
        return _load_control_r7_api().assess_r7b_payload(request)

    @app.get(
        "/api/v1/control/r7c/manifest",
        response_model=R7CManifest,
        response_model_by_alias=True,
    )
    def control_r7c_manifest() -> R7CManifest:
        return _load_control_r7_api().build_r7c_manifest()

    @app.get(
        "/api/v1/control/r7c/scenarios",
        response_model=list[R7CScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7c_scenarios() -> list[R7CScenarioSummary]:
        return list(_load_control_r7_api().list_r7c_scenarios())

    @app.get(
        "/api/v1/examples/control-r7c",
        response_model=R7CExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7c_example(
        scenarioId: str = "opcua-transport-evidence-open",
    ) -> R7CExamplePayload:
        try:
            return _load_control_r7_api().r7c_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7c/assess",
        response_model=R7CExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7c_assess(request: R7CAssessmentRequest) -> R7CExamplePayload:
        return _load_control_r7_api().assess_r7c_payload(request)

    @app.get(
        "/api/v1/control/r7d/manifest",
        response_model=R7DManifest,
        response_model_by_alias=True,
    )
    def control_r7d_manifest() -> R7DManifest:
        return _load_control_r7_api().build_r7d_manifest()

    @app.get(
        "/api/v1/control/r7d/scenarios",
        response_model=list[R7DScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7d_scenarios() -> list[R7DScenarioSummary]:
        return list(_load_control_r7_api().list_r7d_scenarios())

    @app.get(
        "/api/v1/examples/control-r7d",
        response_model=R7DExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7d_example(
        scenarioId: str = "beckhoff-twincat-runtime-open",
    ) -> R7DExamplePayload:
        try:
            return _load_control_r7_api().r7d_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7d/assess",
        response_model=R7DExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7d_assess(request: R7DAssessmentRequest) -> R7DExamplePayload:
        return _load_control_r7_api().assess_r7d_payload(request)

    @app.get(
        "/api/v1/control/r7e/manifest",
        response_model=R7EManifest,
        response_model_by_alias=True,
    )
    def control_r7e_manifest() -> R7EManifest:
        return _load_control_r7_api().build_r7e_manifest()

    @app.get(
        "/api/v1/control/r7e/scenarios",
        response_model=list[R7EScenarioSummary],
        response_model_by_alias=True,
    )
    def control_r7e_scenarios() -> list[R7EScenarioSummary]:
        return list(_load_control_r7_api().list_r7e_scenarios())

    @app.get(
        "/api/v1/examples/control-r7e",
        response_model=R7EExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7e_example(
        scenarioId: str = "beckhoff-shadow-witness-open",
    ) -> R7EExamplePayload:
        try:
            return _load_control_r7_api().r7e_example_payload(scenarioId)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/control/r7e/assess",
        response_model=R7EExamplePayload,
        response_model_by_alias=True,
    )
    def control_r7e_assess(request: R7EAssessmentRequest) -> R7EExamplePayload:
        return _load_control_r7_api().assess_r7e_payload(request)

    @app.get(
        "/api/v1/examples/control-r7e/deployment",
        response_model=BeckhoffWitnessDeploymentReport,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def control_r7e_deployment_example() -> BeckhoffWitnessDeploymentReport:
        return assess_beckhoff_witness_deployment(
            build_default_beckhoff_witness_deployment_request()
        )

    @app.post(
        "/api/v1/control/r7e/deployment/assess",
        response_model=BeckhoffWitnessDeploymentReport,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def control_r7e_deployment_assess(
        request: BeckhoffWitnessDeploymentRequest,
    ) -> BeckhoffWitnessDeploymentReport:
        return assess_beckhoff_witness_deployment(request)

    @app.get("/api/v1/control/r7e/deployment/template")
    def control_r7e_deployment_template() -> Response:
        return Response(
            content=read_beckhoff_witness_plc_template(),
            media_type="application/xml",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{BECKHOFF_WITNESS_PLC_TEMPLATE_FILE}"'
                )
            },
        )

    @app.post(
        "/api/v1/field-evidence/assess",
        response_model=FieldEvidenceAssessmentReport,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def field_evidence_assess(
        request: FieldEvidenceAssessmentRequest,
    ) -> FieldEvidenceAssessmentReport:
        return assess_field_evidence(request)

    @app.get("/api/v1/benchmarks/cnc/example", response_model=CncBenchmarkRequest, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_example() -> CncBenchmarkRequest:
        return cnc_benchmark_example()

    @app.post("/api/v1/benchmarks/cnc/case-hash")
    def cnc_case_hash(case: CncBenchmarkCase) -> dict[str, str]:
        return {"caseContentHash": benchmark_case_hash(case)}

    @app.post("/api/v1/benchmarks/cnc/compare", response_model=CncBenchmarkReport, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_compare(request: CncBenchmarkRequest) -> CncBenchmarkReport:
        return compare_cnc_exports(request)

    @app.post("/api/v1/benchmarks/cnc/evaluate", response_model=CncQualityReport, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_evaluate_single(request: CncSingleEvaluationRequest) -> CncQualityReport:
        return evaluate_cnc_export(request)

    @app.get("/api/v1/benchmarks/cnc/parameter-registry", response_model=CncParameterRegistry, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_registry() -> CncParameterRegistry:
        return default_cnc_parameter_registry()

    @app.get("/api/v1/benchmarks/cnc/controller-profiles", response_model=list[ControllerProfile], response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_controller_profiles() -> list[ControllerProfile]:
        return list(list_controller_profiles())

    @app.post("/api/v1/benchmarks/cnc/param-diagnose", response_model=CncSingleRunDiagnosticReport, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_diagnose(payload: dict[str, Any]) -> CncSingleRunDiagnosticReport:
        case_obj = CncBenchmarkCase.model_validate(payload["case"])
        exp_or_rep = (
            CncAlgorithmExport.model_validate(payload["export"])
            if "export" in payload and payload["export"] is not None
            else CncQualityReport.model_validate(payload["qualityReport"])
        )
        prof: ControllerProfile | None = None
        if payload.get("controllerProfile") is not None:
            prof = ControllerProfile.model_validate(payload["controllerProfile"])
        elif payload.get("profileId") is not None:
            try:
                prof = get_controller_profile(str(payload["profileId"]))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        return diagnose_single_run(
            case_obj,
            exp_or_rep,
            parameters=payload.get("parameters"),
            controller_profile=prof,
            include_drive_side=bool(payload.get("includeDriveSide", True)),
        )

    @app.get("/api/v1/benchmarks/cnc/param-doe", response_model=ParameterDoePlan, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_doe(
        offlineCount: int = 36,
        controllerCount: int = 12,
        seed: int = 42,
        mode: str = "orthogonal-greybox",
        profileId: str | None = None,
    ) -> ParameterDoePlan:
        doe_mode = "lhs" if mode == "lhs" else "orthogonal-greybox"
        prof: ControllerProfile | None = None
        if profileId is not None:
            try:
                prof = get_controller_profile(profileId)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        return generate_parameter_doe(
            controller_profile=prof,
            offline_count=offlineCount,
            controller_count=controllerCount,
            seed=seed,
            mode=doe_mode,
        )

    @app.post("/api/v1/benchmarks/cnc/param-learn", response_model=LearnedParameterSurrogate, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_learn(request: ParameterLearningRequest) -> LearnedParameterSurrogate:
        return learn_parameter_surrogate(request)

    @app.post("/api/v1/benchmarks/cnc/param-recommend", response_model=ParameterRecommendationReport, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_recommend(payload: dict[str, Any]) -> ParameterRecommendationReport:
        surrogate = LearnedParameterSurrogate.model_validate(payload["surrogate"])
        req = ParameterRecommendationRequest.model_validate(payload.get("request") or {})
        tgt = CncBenchmarkCase.model_validate(payload["targetCase"]) if "targetCase" in payload and payload["targetCase"] is not None else None
        return recommend_parameters(surrogate, req, target_case=tgt)

    @app.get("/api/v1/benchmarks/cnc/param-demo", response_model=CncParameterClosedLoopDemo, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_demo(offlineCount: int = 24, controllerCount: int = 10, seed: int = 42, multiCase: bool = False) -> CncParameterClosedLoopDemo:
        return build_cnc_parameter_closed_loop_demo(offline_count=offlineCount, controller_count=controllerCount, seed=seed, multi_case_calibration=multiCase)

    @app.get("/api/v1/benchmarks/cnc/param-workbench")
    def cnc_parameter_workbench() -> dict[str, Any]:
        return _build_cnc_param_workbench_bundle()


    @app.post("/api/v1/benchmarks/cnc/param-ledger", response_model=PredictionVerificationLedger, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_ledger_post(payload: dict[str, Any]) -> PredictionVerificationLedger:
        case_obj = CncBenchmarkCase.model_validate(payload["case"])
        sur_obj = LearnedParameterSurrogate.model_validate(payload["surrogate"])
        rec_obj = ParameterRecommendationReport.model_validate(payload["recommendationReport"]) if payload.get("recommendationReport") else None
        raw_trace = payload["verificationTrace"]
        if isinstance(raw_trace, dict) and raw_trace.get("artifactType") == "machine.telemetry-trace":
            ver_trace: CncAlgorithmExport | MachineTelemetryTrace = MachineTelemetryTrace.model_validate(raw_trace)
        else:
            ver_trace = CncAlgorithmExport.model_validate(raw_trace)
        base_exp = CncAlgorithmExport.model_validate(payload["baselineExport"]) if payload.get("baselineExport") else None
        entry = record_prediction_verification(
            case_obj,
            sur_obj,
            ver_trace,
            recommendation_report=rec_obj,
            candidate_id=payload.get("candidateId"),
            applied_parameters=payload.get("appliedParameters"),
            baseline_trace_or_report=base_exp,
            entry_id=str(payload.get("entryId", "verify.001")),
        )
        if payload.get("existingLedger") is not None:
            existing = PredictionVerificationLedger.model_validate(payload["existingLedger"])
            return append_prediction_verification_entry(existing, entry)
        return build_prediction_verification_ledger(
            (entry,),
            surrogate=sur_obj,
            ledger_id=str(payload.get("ledgerId", "cnc.prediction-ledger@1")),
        )

    @app.get("/api/v1/benchmarks/cnc/param-governance", response_model=CncGovernanceAssessmentReport, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_governance(offlineCount: int = 14, controllerCount: int = 8, seed: int = 42, multiCase: bool = True) -> CncGovernanceAssessmentReport:
        demo = build_cnc_parameter_closed_loop_demo(offline_count=offlineCount, controller_count=controllerCount, seed=seed, multi_case_calibration=multiCase)
        return assess_cnc_greybox_governance(demo)

    @app.post("/api/v1/benchmarks/cnc/param-governance", response_model=CncGovernanceAssessmentReport, response_model_by_alias=True, response_model_exclude_none=True)
    def cnc_parameter_governance_post(payload: dict[str, Any]) -> CncGovernanceAssessmentReport:
        ledger_obj = (
            PredictionVerificationLedger.model_validate(payload["verificationLedger"])
            if payload.get("verificationLedger") is not None
            else None
        )
        if "case" in payload and "surrogate" in payload and "recommendationReport" in payload:
            demo_payload = dict(payload)
            demo_payload.pop("verificationLedger", None)
            demo = CncParameterClosedLoopDemo.model_validate(demo_payload)
            return assess_cnc_greybox_governance(demo, verification_ledger=ledger_obj)
        case_obj = CncBenchmarkCase.model_validate(payload["benchmarkCase"])
        exp_obj = CncAlgorithmExport.model_validate(payload["export"])
        sur_obj = LearnedParameterSurrogate.model_validate(payload["surrogate"]) if payload.get("surrogate") else None
        rec_obj = ParameterRecommendationReport.model_validate(payload["recommendationReport"]) if payload.get("recommendationReport") else None
        return assess_cnc_greybox_governance(
            case_obj,
            export=exp_obj,
            surrogate=sur_obj,
            recommendation_report=rec_obj,
            verification_ledger=ledger_obj,
        )

    @app.post(
        "/api/v1/experiments/run",
        response_model=ExperimentReport,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def execute_experiment(spec: ExperimentSpec) -> ExperimentReport:
        return run_experiment(spec)

    if serve_frontend:
        static_dir = frontend_dir or Path(__file__).with_name("web_dist")
        index_path = static_dir / "index.html"
        if not index_path.is_file():
            raise RuntimeError(
                f"Axiom web assets are missing at {static_dir}. Run the frontend build before starting the server."
            )
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app
