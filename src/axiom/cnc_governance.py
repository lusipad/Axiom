"""Unified Governance Bridge connecting CNC Three-Layer Grey-Box Modeling to Axiom R0-R7 Spine.

Eliminates the architectural split between the CNC Benchmark/Grey-Box Parameter workflow
(`benchmark.py`, `greybox_model.py`, `parameter_learner.py`, `parameter_recommender.py`) and
Axiom's core `DomainPack` / `RunBundle` / `Claim` / `R3-R7` safety governance pipeline:

1. `CNC_GREYBOX_DOMAIN_PACK` (`cnc-greybox.domain-pack@1`):
   - Publicly registered `DomainPack` + `DomainRuntimeBinding` executable via `axiom.evaluate_run(...)`.
   - Emits cryptographically sealed `RunBundle` and `Claim` objects covering:
     * L0 Sampled Command Hard Gate (`cnc-greybox.sampled-limits-passed@1`)
     * R3 Read-Only Trace Lineage & Clock Integrity (`cnc-greybox.r3-readonly-lineage@1`)
     * R4 Grey-Box Physical Calibration Fidelity (`cnc-greybox.r4-greybox-calibration@1`)
     * R5 Split-Conformal & FeatureEnvelope Epistemic Gate (`cnc-greybox.r5-epistemic-envelope@1`)
     * R6/R7 OfflineAdvisory Zero-Write Safety Gate (`cnc-greybox.r7-advisory-safety-gate@1`)
2. `CNC_EXPORT_TO_ORDERED_POINT_ADAPTER` (`cnc.export-to-ordered-point@1`):
   - Explicit `ArtifactAdapter` projecting `CncAlgorithmExport` into `OrderedPointSequence` with
     full hash provenance (`preservedSemantics` / `droppedSemantics`).
3. `adapt_r3_telemetry_to_cnc_export(...)`:
   - Deterministic read-only bridge converting an R3 `MachineTelemetryTrace` (command + encoder
     feedback channels) into a case-bound `CncAlgorithmExport(sourceKind="controller-trace")`,
     enforcing zero write operations (`operation == "file-import"`).
"""

from __future__ import annotations

import platform
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, Literal, Mapping

from pydantic import Field

from .adapters import (
    ArtifactAdapter,
    ArtifactAdapterProvenance,
    ArtifactTransformationResult,
    register_artifact_adapter,
)
from .benchmark import (
    BenchmarkSample,
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncQualityReport,
    benchmark_case_hash,
    evaluate_cnc_export,
)
from .domain import (
    ARTIFACT_IMPORT_RUNNER_ID,
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    STRICT_COMPARISON_POLICY_ID,
    ArtifactTypeDescriptor,
    DomainPack,
    FailureMapping,
    MetricDefinition,
    NumericTolerance,
    register_domain_pack,
)
from .evaluator import _aggregate_outcome, _apply_threshold, _content_hash, _seal_evaluation_report
from .machine.models import MachineTelemetryTrace
from .models import (
    AxiomModel,
    CapabilityResolution,
    CoreEvaluationRequest,
    EvaluationReport,
    Evidence,
    MetricRequest,
    MetricResult,
    OrderedPointSequence,
    PointSemantics,
    Provenance,
)
from .parameter_learner import LearnedParameterSurrogate
from .parameter_recommender import (
    CncParameterClosedLoopDemo,
    ParameterRecommendationReport,
    build_cnc_parameter_closed_loop_demo,
)
from .run import RunBundle, evaluate_run
from .runtime import DomainRuntimeBinding, register_domain_runtime_binding

CNC_GREYBOX_DOMAIN_PACK_ID = "cnc-greybox.domain-pack@1"
CNC_GREYBOX_EVALUATOR_ID = "cnc-greybox-evaluator@1"
CNC_EXPORT_ARTIFACT_TYPE = "cnc.algorithm-export"
CNC_EXPORT_TO_ORDERED_POINT_ADAPTER_ID = "cnc.export-to-ordered-point@1"

CNC_SAMPLED_LIMITS_METRIC_ID = "cnc-greybox.sampled-limits-passed@1"
CNC_R3_LINEAGE_METRIC_ID = "cnc-greybox.r3-readonly-lineage@1"
CNC_R4_CALIBRATION_METRIC_ID = "cnc-greybox.r4-greybox-calibration@1"
CNC_R5_EPISTEMIC_METRIC_ID = "cnc-greybox.r5-epistemic-envelope@1"
CNC_R7_SAFETY_GATE_METRIC_ID = "cnc-greybox.r7-advisory-safety-gate@1"
CNC_GREYBOX_MEAN_R2_METRIC_ID = "cnc-greybox.surrogate-mean-r2@1"

CNC_SAMPLED_LIMITS_CLAIM_ID = "cnc-greybox.sampled-limits-claim@1"
CNC_R4_CALIBRATION_CLAIM_ID = "cnc-greybox.r4-calibration-claim@1"
CNC_R5_EPISTEMIC_CLAIM_ID = "cnc-greybox.r5-epistemic-claim@1"
CNC_R7_SAFETY_CLAIM_ID = "cnc-greybox.r7-zero-write-advisory-claim@1"


def _pkg_ver(dist_name: str, fallback: str = "0.0.0") -> str:
    try:
        return package_version(dist_name)
    except PackageNotFoundError:
        return fallback


class CncGreyboxDomainArtifact(AxiomModel):
    artifact_type: Literal["cnc.algorithm-export"] = Field(
        default=CNC_EXPORT_ARTIFACT_TYPE, alias="artifactType"
    )
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    benchmark_case: CncBenchmarkCase = Field(alias="benchmarkCase")
    export: CncAlgorithmExport
    surrogate: LearnedParameterSurrogate | None = None
    recommendation_report: ParameterRecommendationReport | None = Field(
        default=None, alias="recommendationReport"
    )


class CncGreyboxEvaluationCase(AxiomModel):
    case_id: str = Field(alias="caseId", min_length=1)
    required_metrics: list[str | MetricRequest] = Field(
        default_factory=lambda: [
            CNC_SAMPLED_LIMITS_METRIC_ID,
            CNC_R3_LINEAGE_METRIC_ID,
            CNC_R4_CALIBRATION_METRIC_ID,
            CNC_R5_EPISTEMIC_METRIC_ID,
            CNC_R7_SAFETY_GATE_METRIC_ID,
            CNC_GREYBOX_MEAN_R2_METRIC_ID,
        ],
        alias="requiredMetrics",
    )
    optional_metrics: list[str | MetricRequest] = Field(
        default_factory=list, alias="optionalMetrics"
    )


class CncGreyboxEvaluationRequest(AxiomModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    artifact: CncGreyboxDomainArtifact
    case: CncGreyboxEvaluationCase


class CncGovernanceAssessmentReport(AxiomModel):
    schema_id: Literal["axiom.cnc-greybox-governance-report@1"] = Field(
        default="axiom.cnc-greybox-governance-report@1", alias="schemaId"
    )
    domain_pack_id: str = Field(default=CNC_GREYBOX_DOMAIN_PACK_ID, alias="domainPackId")
    case_id: str = Field(alias="caseId")
    case_content_hash: str = Field(alias="caseContentHash")
    surrogate_model_hash: str | None = Field(default=None, alias="surrogateModelHash")
    recommendation_report_hash: str | None = Field(default=None, alias="recommendationReportHash")
    permission_ceiling: Literal["OfflineAdvisory"] = Field(
        default="OfflineAdvisory", alias="permissionCeiling"
    )
    device_write_allowed: Literal[False] = Field(default=False, alias="deviceWriteAllowed")
    deployment_shadow_status: Literal["Open"] = Field(default="Open", alias="deploymentShadowStatus")
    controlled_trial_status: Literal["Open"] = Field(default="Open", alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(default="Open", alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(default="NotAssessed", alias="deviceSafetyStatus")
    run_bundle: RunBundle = Field(alias="runBundle")


def _transform_cnc_export_to_ordered_point(payload: object) -> ArtifactTransformationResult:
    export = (
        payload
        if isinstance(payload, CncAlgorithmExport)
        else CncAlgorithmExport.model_validate(payload)
    )
    src_hash = _content_hash(export.model_dump(mode="json", by_alias=True, exclude_none=True))
    points = [list(s.position_mm) for s in export.samples]
    target = OrderedPointSequence(
        artifactType="ordered-point-sequence",
        schemaVersion=1,
        points=points,
        semantics=PointSemantics(
            unit=export.unit,
            coordinateFrame=export.coordinate_frame,
            closed=False,
        ),
    )
    dst_hash = _content_hash(target.model_dump(mode="json", by_alias=True, exclude_none=True))
    return ArtifactTransformationResult(
        artifact=target,
        contentHash=dst_hash,
        provenance=ArtifactAdapterProvenance(
            adapterId=CNC_EXPORT_TO_ORDERED_POINT_ADAPTER_ID,
            sourceArtifactType=CNC_EXPORT_ARTIFACT_TYPE,
            targetArtifactType="ordered-point-sequence",
            sourceContentHash=src_hash,
            resultContentHash=dst_hash,
            preservedSemantics=["positionMm", "unit", "coordinateFrame", "sampleOrder"],
            droppedSemantics=["samplePeriodSeconds", "actualPositionMm", "parameters", "computation"],
        ),
    )


CNC_EXPORT_TO_ORDERED_POINT_ADAPTER = register_artifact_adapter(
    ArtifactAdapter(
        adapter_id=CNC_EXPORT_TO_ORDERED_POINT_ADAPTER_ID,
        source_artifact_type=CNC_EXPORT_ARTIFACT_TYPE,
        target_artifact_type="ordered-point-sequence",
        transform=_transform_cnc_export_to_ordered_point,
    )
)


def adapt_r3_telemetry_to_cnc_export(
    trace: MachineTelemetryTrace | Mapping[str, Any],
    case: CncBenchmarkCase | Mapping[str, Any],
    *,
    algorithm_id: str = "axiom.r3-observed-controller",
    algorithm_version: str = "r3-capture@1",
    parameters: Mapping[str, float] | None = None,
    command_channels: tuple[str, str, str] = ("cmd_x", "cmd_y", "cmd_z"),
    actual_channels: tuple[str, str, str] = ("act_x", "act_y", "act_z"),
) -> CncAlgorithmExport:
    """Deterministically project a read-only R3 `MachineTelemetryTrace` into a CNC `controller-trace` export."""
    r3_trace = (
        trace
        if isinstance(trace, MachineTelemetryTrace)
        else MachineTelemetryTrace.model_validate(trace)
    )
    bench_case = (
        case if isinstance(case, CncBenchmarkCase) else CncBenchmarkCase.model_validate(case)
    )
    if r3_trace.capture_receipt.operation != "file-import":
        raise ValueError(
            f"R3 governance violation: forbidden non-read-only operation '{r3_trace.capture_receipt.operation}'"
        )
    if len(r3_trace.frames) < 4:
        raise ValueError("R3 telemetry trace must contain at least 4 frames for V/A/J evaluation")

    dt = bench_case.sample_period_seconds
    samples: list[BenchmarkSample] = []
    for idx, frame in enumerate(r3_trace.frames):
        if idx > 0 and frame.sequence_id != r3_trace.frames[idx - 1].sequence_id + 1:
            raise ValueError("R3 sequenceId discontinuity detected; implicit interpolation is forbidden")
        ch_map = {
            s.channel_id: float(s.value)
            for s in frame.samples
            if isinstance(s.value, (int, float)) and s.quality != "bad"
        }
        if not all(ch in ch_map for ch in command_channels):
            raise ValueError(f"R3 frame {frame.sequence_id} missing command channels {command_channels}")
        cmd_xyz = (
            ch_map[command_channels[0]],
            ch_map[command_channels[1]],
            ch_map[command_channels[2]],
        )
        act_xyz = (
            (
                ch_map[actual_channels[0]],
                ch_map[actual_channels[1]],
                ch_map[actual_channels[2]],
            )
            if all(ch in ch_map for ch in actual_channels)
            else None
        )
        samples.append(
            BenchmarkSample(
                sampleIndex=idx,
                t=round(idx * dt, 9),
                positionMm=cmd_xyz,
                actualPositionMm=act_xyz,
            )
        )

    return CncAlgorithmExport(
        algorithmId=algorithm_id,
        algorithmVersion=algorithm_version,
        sourceKind="controller-trace" if samples[0].actual_position_mm is not None else "algorithm-export",
        caseContentHash=benchmark_case_hash(bench_case),
        coordinateFrame=bench_case.coordinate_frame,
        unit="mm",
        samplePeriodSeconds=dt,
        parameters={k: float(v) for k, v in parameters.items()} if parameters else None,
        samples=tuple(samples),
    )


def _metric_def(
    metric_id: str,
    *,
    claim_id: str | None = None,
    predicate: str | None = None,
    direction: Literal["lower-is-better", "higher-is-better"] | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=("cnc-greybox.artifact@1",),
        direction=direction,
        numericTolerance=NumericTolerance(absolute=1e-9, relative=1e-9),
        claimDefinitionId=claim_id,
        claimPredicate=predicate,
    )


CNC_GREYBOX_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=CNC_GREYBOX_DOMAIN_PACK_ID,
        artifactType=CNC_EXPORT_ARTIFACT_TYPE,
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType=CNC_EXPORT_ARTIFACT_TYPE,
                schemaVersion=1,
                role="run-input",
            ),
        ),
        evaluatorVersion=CNC_GREYBOX_EVALUATOR_ID,
        runnerId=ARTIFACT_IMPORT_RUNNER_ID,
        runnerIds=(ARTIFACT_IMPORT_RUNNER_ID,),
        importRunnerIds=(ARTIFACT_IMPORT_RUNNER_ID,),
        capabilityIds=("cnc-greybox.artifact@1",),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            CNC_SAMPLED_LIMITS_CLAIM_ID,
            CNC_R4_CALIBRATION_CLAIM_ID,
            CNC_R5_EPISTEMIC_CLAIM_ID,
            CNC_R7_SAFETY_CLAIM_ID,
        ),
        comparisonPolicyIds=(STRICT_COMPARISON_POLICY_ID,),
        metricDefinitions=(
            _metric_def(
                CNC_SAMPLED_LIMITS_METRIC_ID,
                claim_id=CNC_SAMPLED_LIMITS_CLAIM_ID,
                predicate="Sampled XYZ trajectory satisfies stroke, endpoint, contour, and V/A/J hard limits.",
            ),
            _metric_def(CNC_R3_LINEAGE_METRIC_ID),
            _metric_def(
                CNC_R4_CALIBRATION_METRIC_ID,
                claim_id=CNC_R4_CALIBRATION_CLAIM_ID,
                predicate="Three-layer grey-box physical constants satisfy bounded identification and positive R² fidelity.",
            ),
            _metric_def(
                CNC_R5_EPISTEMIC_METRIC_ID,
                claim_id=CNC_R5_EPISTEMIC_CLAIM_ID,
                predicate="Recommended presets remain inside the declared FeatureEnvelope and satisfy Split Conformal upper bounds.",
            ),
            _metric_def(
                CNC_R7_SAFETY_GATE_METRIC_ID,
                claim_id=CNC_R7_SAFETY_CLAIM_ID,
                predicate="Recommendation remains strictly OfflineAdvisory with zero device-write authority; DeviceSafe remains Open.",
            ),
            _metric_def(CNC_GREYBOX_MEAN_R2_METRIC_ID, direction="higher-is-better"),
        ),
        failureMappings=(
            FailureMapping(
                code="MalformedEvaluationRequest",
                executionStatus="Skipped",
                metricStatus="InvalidObservation",
                caseOutcome="Invalid",
            ),
        ),
    )
)


def _parse_cnc_greybox_request(request: CoreEvaluationRequest) -> CncGreyboxEvaluationRequest:
    payload = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return CncGreyboxEvaluationRequest.model_validate(payload)


def _evaluate_cnc_greybox_request(req: CncGreyboxEvaluationRequest) -> EvaluationReport:
    art = req.artifact
    q_rep: CncQualityReport = evaluate_cnc_export(art.benchmark_case, art.export)

    limits_ok = q_rep.outcome == "Passed"
    r3_ok = (
        art.export.case_content_hash == benchmark_case_hash(art.benchmark_case)
        and art.export.source_kind in ("algorithm-export", "controller-trace")
        and len(art.export.samples) >= 4
    )

    sur = art.surrogate
    if sur is not None and sur.greybox_constants is not None and sur.metric_heads:
        mean_r2 = sum(h.r2_score for h in sur.metric_heads.values()) / len(sur.metric_heads)
        r4_ok = (
            sur.engine_mode == "greybox-physics-gp"
            and 0.5 <= sur.greybox_constants.velocity_loop_ratio_x <= 20.0
            and mean_r2 >= 0.55
        )
    else:
        mean_r2 = 0.0
        r4_ok = False

    rec = art.recommendation_report
    if rec is not None and rec.presets:
        r5_ok = all(p.in_domain and p.hard_constraints_satisfied for p in rec.presets)
        r7_ok = (
            rec.permission_level == "OfflineAdvisory"
            and rec.device_write_allowed is False
            and all(p.permission_level == "OfflineAdvisory" and p.device_write_allowed is False for p in rec.presets)
        )
    else:
        r5_ok = sur is not None
        r7_ok = True

    ev_obs = Evidence(level="Observed", method="cnc-frenet-sampled-evaluation@1")
    ev_gb = Evidence(level="Validated", method="three-layer-greybox-ard-gp-conformal@1")

    raw_map: dict[str, tuple[bool | float, str | None, Evidence, dict[str, Any]]] = {
        CNC_SAMPLED_LIMITS_METRIC_ID: (
            limits_ok,
            None,
            ev_obs,
            {"outcome": q_rep.outcome, "sliceCount": len(q_rep.geometry_slices)},
        ),
        CNC_R3_LINEAGE_METRIC_ID: (
            r3_ok,
            None,
            ev_obs,
            {"sourceKind": art.export.source_kind, "sampleCount": len(art.export.samples)},
        ),
        CNC_R4_CALIBRATION_METRIC_ID: (
            r4_ok,
            None,
            ev_gb,
            {
                "identifiedResonanceHz": sur.greybox_constants.identified_resonance_hz
                if (sur and sur.greybox_constants)
                else None,
                "calibratedCaseCount": len(sur.calibrated_case_ids) if sur else 0,
            },
        ),
        CNC_R5_EPISTEMIC_METRIC_ID: (
            r5_ok,
            None,
            ev_gb,
            {"feasiblePresets": sum(1 for p in (rec.presets if rec else ()) if p.hard_constraints_satisfied)},
        ),
        CNC_R7_SAFETY_GATE_METRIC_ID: (
            r7_ok,
            None,
            ev_obs,
            {"permissionLevel": "OfflineAdvisory", "deviceWriteAllowed": False, "realityGate": "Open"},
        ),
        CNC_GREYBOX_MEAN_R2_METRIC_ID: (
            round(float(mean_r2), 6),
            None,
            ev_gb,
            {"modeledHeadCount": len(sur.metric_heads) if sur else 0},
        ),
    }

    req_items = [
        item if isinstance(item, MetricRequest) else MetricRequest(metricId=item)
        for item in req.case.required_metrics
    ]
    results: list[MetricResult] = []
    for item in req_items:
        val, unit, ev, details = raw_map[item.metric_id]
        base_res = MetricResult(
            metricId=item.metric_id,
            metricDefinitionId=item.metric_id,
            status="Computed",
            value=val,
            unit=unit,
            requires=["cnc-greybox.artifact@1"],
            evidence=ev,
            details=details,
        )
        if item.threshold is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
            base_res = _apply_threshold(base_res, item.threshold)
        elif isinstance(val, bool):
            base_res = base_res.model_copy(update={"threshold_passed": val})
        results.append(base_res)

    req_payload_hash = _content_hash(req.model_dump(mode="json", by_alias=True, exclude_none=True))
    art_hash = _content_hash(art.model_dump(mode="json", by_alias=True, exclude_none=True))
    case_hash = _content_hash(req.case.model_dump(mode="json", by_alias=True, exclude_none=True))
    ctx_hashes: dict[str, str] = {"benchmarkCase": benchmark_case_hash(art.benchmark_case)}
    if sur is not None:
        ctx_hashes["surrogateModel"] = sur.model_content_hash
    if rec is not None:
        ctx_hashes["recommendationReport"] = rec.report_content_hash

    prov = Provenance(
        requestHash=req_payload_hash,
        artifactHash=art_hash,
        caseHash=case_hash,
        runnerId=ARTIFACT_IMPORT_RUNNER_ID,
        evaluatorVersion=CNC_GREYBOX_EVALUATOR_ID,
        executionOutcomePolicy="cnc-greybox.hard-gate-outcome@1",
        numericType="float64",
        numericEnvironment={
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": _pkg_ver("numpy"),
            "scipy": _pkg_ver("scipy"),
        },
        contextHashes=ctx_hashes,
    )
    outcome = _aggregate_outcome(results)
    report = EvaluationReport(
        executionStatus="Succeeded",
        caseOutcome=outcome,
        capabilities=[CapabilityResolution(capabilityId="cnc-greybox.artifact@1", source="Artifact")],
        metricResults=results,
        domainFailures=[],
        provenance=prov,
        contentHash="0" * 64,
    )
    return _seal_evaluation_report(report)


register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=CNC_GREYBOX_DOMAIN_PACK_ID,
        parse_request=_parse_cnc_greybox_request,
        evaluate=_evaluate_cnc_greybox_request,
    )
)


def build_cnc_greybox_run_spec(
    case: CncBenchmarkCase,
    export: CncAlgorithmExport,
    *,
    surrogate: LearnedParameterSurrogate | None = None,
    recommendation_report: ParameterRecommendationReport | None = None,
    subject_id: str = "cnc.three-layer-greybox-advisor@1",
) -> dict[str, Any]:
    """Build a canonical `RunSpec` dictionary ready for `axiom.evaluate_run(...)`."""
    return {
        "schemaVersion": 1,
        "subjectId": subject_id,
        "domainPackId": CNC_GREYBOX_DOMAIN_PACK_ID,
        "runnerId": ARTIFACT_IMPORT_RUNNER_ID,
        "request": {
            "schemaVersion": 1,
            "artifact": {
                "artifactType": CNC_EXPORT_ARTIFACT_TYPE,
                "schemaVersion": 1,
                "benchmarkCase": case.model_dump(mode="json", by_alias=True, exclude_none=True),
                "export": export.model_dump(mode="json", by_alias=True, exclude_none=True),
                "surrogate": surrogate.model_dump(mode="json", by_alias=True, exclude_none=True)
                if surrogate is not None
                else None,
                "recommendationReport": recommendation_report.model_dump(mode="json", by_alias=True, exclude_none=True)
                if recommendation_report is not None
                else None,
            },
            "case": {
                "caseId": f"{case.case_id}.governance@1",
                "requiredMetrics": [
                    CNC_SAMPLED_LIMITS_METRIC_ID,
                    CNC_R3_LINEAGE_METRIC_ID,
                    CNC_R4_CALIBRATION_METRIC_ID,
                    CNC_R5_EPISTEMIC_METRIC_ID,
                    CNC_R7_SAFETY_GATE_METRIC_ID,
                    {
                        "metricId": CNC_GREYBOX_MEAN_R2_METRIC_ID,
                        "threshold": {"operator": ">=", "value": 0.55},
                    },
                ],
            },
        },
    }


def assess_cnc_greybox_governance(
    demo_or_case: CncParameterClosedLoopDemo | CncBenchmarkCase | None = None,
    *,
    export: CncAlgorithmExport | None = None,
    surrogate: LearnedParameterSurrogate | None = None,
    recommendation_report: ParameterRecommendationReport | None = None,
    multi_case_calibration: bool = True,
) -> CncGovernanceAssessmentReport:
    """Execute the full R0-R7 governance gate over a CNC Grey-Box closed-loop run and return a sealed RunBundle."""
    if demo_or_case is None:
        demo = build_cnc_parameter_closed_loop_demo(
            offline_count=14,
            controller_count=8,
            seed=42,
            multi_case_calibration=multi_case_calibration,
        )
        case_obj = demo.case
        sur_obj = demo.surrogate
        rec_obj = demo.recommendation_report
        best_params = rec_obj.presets[1].full_parameters
        from .greybox_model import simulate_realistic_cnc_controller

        exp_obj = simulate_realistic_cnc_controller(
            case_obj,
            best_params,
            source_kind="controller-trace",
            registry=sur_obj.registry,
            algorithm_version="governance-verified-preset",
        )
    elif isinstance(demo_or_case, CncParameterClosedLoopDemo):
        case_obj = demo_or_case.case
        sur_obj = demo_or_case.surrogate
        rec_obj = demo_or_case.recommendation_report
        from .greybox_model import simulate_realistic_cnc_controller

        exp_obj = simulate_realistic_cnc_controller(
            case_obj,
            rec_obj.presets[1].full_parameters,
            source_kind="controller-trace",
            registry=sur_obj.registry,
            algorithm_version="governance-verified-preset",
        )
    else:
        if export is None:
            raise ValueError("`export` is required when passing a standalone `CncBenchmarkCase`")
        case_obj = demo_or_case
        exp_obj = export
        sur_obj = surrogate
        rec_obj = recommendation_report

    run_spec = build_cnc_greybox_run_spec(
        case_obj,
        exp_obj,
        surrogate=sur_obj,
        recommendation_report=rec_obj,
    )
    bundle = evaluate_run(run_spec)
    return CncGovernanceAssessmentReport(
        caseId=case_obj.case_id,
        caseContentHash=benchmark_case_hash(case_obj),
        surrogateModelHash=sur_obj.model_content_hash if sur_obj is not None else None,
        recommendationReportHash=rec_obj.report_content_hash if rec_obj is not None else None,
        runBundle=bundle,
    )
