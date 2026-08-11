from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, Literal

from pydantic import Field, model_validator

from ..evaluator import _content_hash
from ..models import AxiomModel, RunSpec
from .f1_models import ExpectedMetric, M1ReferencePath, NormalizedProgram, StageDecision
from .f2_models import M3CandidateAxisPath
from .f2_scenarios import load_f2_scenario
from .f3_models import (
    ArtifactDescriptor,
    AxisMotionConstraint,
    BoundaryState,
    ExpectedClaim,
    ExpectedEvidence,
    F3MathStageManifest,
    M4ContinuousTrajectory,
    MotionConstraintProfile,
    NodeMotionConstraint,
    NumericTolerance,
    ProvenanceRef,
    ToleranceBinding,
)
from .f3_sampling import (
    FOH_POLICY_ID,
    POLYNOMIAL_POLICY_ID,
    REFERENCE_M4_POLICY_ID,
    ZOH_POLICY_ID,
    M5DiscreteCommand,
    M5SampledTrajectory,
    _canonical_content_id as _canonical_m5_content_id,
    sample_continuous_trajectory,
)


_DEFAULT_SCENARIO_ID = "canonical-table-table-jerk"
FIVE_AXIS_F3_DOMAIN_PACK_ID = "five-axis.domain-pack@4"
F3_EVALUATOR_ID = "five-axis-f3-evaluator@1"
F3_RUNNER_ID = "artifact-import@1"

CONTINUOUSLY_FEASIBLE_METRIC_ID = "five-axis.continuously-feasible@1"
TRAJECTORY_DURATION_METRIC_ID = "five-axis.trajectory-duration@1"
AXIS_VELOCITY_UTILIZATION_MAX_METRIC_ID = "five-axis.axis-velocity-utilization.max@1"
AXIS_ACCELERATION_UTILIZATION_MAX_METRIC_ID = "five-axis.axis-acceleration-utilization.max@1"
AXIS_JERK_UTILIZATION_MAX_METRIC_ID = "five-axis.axis-jerk-utilization.max@1"
INTERVAL_CERTIFIED_METRIC_ID = "five-axis.interval-certified@1"
SAMPLE_COUNT_METRIC_ID = "five-axis.sample-count@1"
SAMPLE_PERIOD_METRIC_ID = "five-axis.sample-period@1"
RECONSTRUCTION_POSITION_ERROR_MAX_METRIC_ID = "five-axis.reconstruction-position-error.max@1"
RECONSTRUCTION_ORIENTATION_ERROR_MAX_METRIC_ID = "five-axis.reconstruction-orientation-error.max@1"

CONTINUOUSLY_FEASIBLE_CLAIM_ID = "five-axis.continuously-feasible-claim@1"
INTERVAL_CERTIFIED_CLAIM_ID = "five-axis.interval-certified-claim@1"

CAP_PATH_PROGRESS = "five-axis.path-progress.bound@1"
CAP_REGULARITY = "five-axis.regularity.certified@1"
CAP_MOTION_CONSTRAINT_PROFILE = "five-axis.motion-constraint-profile.bound@1"
CAP_TIME_LAW = "five-axis.time-law.bound@1"
CAP_RECONSTRUCTION = "five-axis.reconstruction.policy-bound@1"


def _canonical_content_id(model: Any) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return _content_hash(json.loads(canonical))


def _safe_package_version(distribution: str) -> str:
    try:
        return package_version(distribution)
    except PackageNotFoundError:
        return "unavailable"


def current_f3_numeric_environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": _safe_package_version("numpy"),
        "scipy": _safe_package_version("scipy"),
        "pydantic": _safe_package_version("pydantic"),
    }


@dataclass(frozen=True, slots=True)
class F3ScenarioSummary:
    scenarioId: str
    title: str
    description: str
    topology: str
    timingMode: str
    reconstructionPolicyId: str
    expectedClaimStatusById: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenarioId,
            "title": self.title,
            "description": self.description,
            "topology": self.topology,
            "timingMode": self.timingMode,
            "reconstructionPolicyId": self.reconstructionPolicyId,
            "expectedClaimStatusById": dict(self.expectedClaimStatusById),
        }


@dataclass(frozen=True, slots=True)
class FiveAxisF3Scenario:
    summary: F3ScenarioSummary
    sourceText: str
    normalizedProgram: NormalizedProgram
    referencePath: M1ReferencePath
    axisPath: M3CandidateAxisPath
    motionConstraintProfile: MotionConstraintProfile
    continuousTrajectory: M4ContinuousTrajectory
    sampledTrajectory: M5SampledTrajectory | None
    discreteCommand: M5DiscreteCommand | None
    manifest: F3MathStageManifest
    runSpec: dict[str, Any]


class F3ExampleSource(AxiomModel):
    source_text: str = Field(alias="sourceText")
    normalized_program: NormalizedProgram = Field(alias="normalizedProgram")
    reference_path: M1ReferencePath = Field(alias="referencePath")


class F3ExampleArtifacts(AxiomModel):
    axis_path: M3CandidateAxisPath = Field(alias="axisPath")
    motion_constraint_profile: MotionConstraintProfile = Field(alias="motionConstraintProfile")
    continuous_trajectory: M4ContinuousTrajectory = Field(alias="continuousTrajectory")
    sampled_trajectory: M5SampledTrajectory | None = Field(default=None, alias="sampledTrajectory")
    discrete_command: M5DiscreteCommand | None = Field(default=None, alias="discreteCommand")

    @model_validator(mode="after")
    def require_exactly_one_discrete_artifact(self) -> "F3ExampleArtifacts":
        if (self.sampled_trajectory is None) == (self.discrete_command is None):
            raise ValueError("exactly one of sampledTrajectory or discreteCommand must be present")
        return self


class F3ExamplePayload(AxiomModel):
    manifest: F3MathStageManifest
    scenario: F3ScenarioSummary
    source: F3ExampleSource
    artifacts: F3ExampleArtifacts
    run_spec: RunSpec = Field(alias="runSpec")


@dataclass(frozen=True, slots=True)
class _ScenarioDefinition:
    scenario_id: str
    title: str
    description: str
    base_f2_scenario_id: str
    timing_mode: Literal["smoothstep7-feasible", "second-order-optimal"]
    reconstruction_policy_id: str
    supported_interval_claim: Literal["Supported", "Unsupported", "Refuted"]
    sample_period: float
    request_jerk: bool
    time_law_policy_id: str
    split_for_dwell: bool = False
    final_hold: bool = False
    dwell_seconds: float = 0.0
    topology: str = "dual-table"

    def expected_interval_claim_status(self) -> Literal["Supported", "Inconclusive", "Refuted"]:
        if self.supported_interval_claim == "Unsupported":
            return "Inconclusive"
        return self.supported_interval_claim

    def expected_claim_status_by_id(self) -> dict[str, str]:
        return {
            CONTINUOUSLY_FEASIBLE_CLAIM_ID: "Supported",
            INTERVAL_CERTIFIED_CLAIM_ID: self.expected_interval_claim_status(),
        }


_SCENARIO_DEFINITIONS: dict[str, _ScenarioDefinition] = {
    "canonical-table-table-jerk": _ScenarioDefinition(
        scenario_id="canonical-table-table-jerk",
        title="双转台 jerk 可行基准",
        description="canonical dual-table 线性轴路径，使用 smoothstep7 连续时间律与 reference-M4 区间证书。",
        base_f2_scenario_id="canonical-table-table",
        timing_mode="smoothstep7-feasible",
        reconstruction_policy_id=REFERENCE_M4_POLICY_ID,
        supported_interval_claim="Supported",
        sample_period=0.25,
        request_jerk=True,
        time_law_policy_id="five-axis.time-law.smoothstep7-feasible@1",
        topology="dual-table",
    ),
    "canonical-head-table-jerk": _ScenarioDefinition(
        scenario_id="canonical-head-table-jerk",
        title="摆头转台 jerk 可行基准",
        description="canonical head-table 线性轴路径，使用 smoothstep7 连续时间律与 reference-M4 区间证书。",
        base_f2_scenario_id="canonical-head-table",
        timing_mode="smoothstep7-feasible",
        reconstruction_policy_id=REFERENCE_M4_POLICY_ID,
        supported_interval_claim="Supported",
        sample_period=0.25,
        request_jerk=True,
        time_law_policy_id="five-axis.time-law.smoothstep7-feasible@1",
        topology="head-table",
    ),
    "canonical-head-head-jerk": _ScenarioDefinition(
        scenario_id="canonical-head-head-jerk",
        title="双摆头 jerk 可行基准",
        description="canonical dual-head 线性轴路径，使用 smoothstep7 连续时间律与 reference-M4 区间证书。",
        base_f2_scenario_id="canonical-head-head",
        timing_mode="smoothstep7-feasible",
        reconstruction_policy_id=REFERENCE_M4_POLICY_ID,
        supported_interval_claim="Supported",
        sample_period=0.25,
        request_jerk=True,
        time_law_policy_id="five-axis.time-law.smoothstep7-feasible@1",
        topology="dual-head",
    ),
    "second-order-proven-optimal": _ScenarioDefinition(
        scenario_id="second-order-proven-optimal",
        title="二阶已证最优时间律",
        description="不请求 jerk 上限，只要求二阶固定路径最优时间参数化；采样使用 FOH，区间验证为 Unsupported，标准 Claim 为 Inconclusive。",
        base_f2_scenario_id="canonical-table-table",
        timing_mode="second-order-optimal",
        reconstruction_policy_id=FOH_POLICY_ID,
        supported_interval_claim="Unsupported",
        sample_period=0.2,
        request_jerk=False,
        time_law_policy_id="five-axis.time-law.second-order-optimal@1",
        topology="dual-table",
    ),
    "dwell-mandatory-stop": _ScenarioDefinition(
        scenario_id="dwell-mandatory-stop",
        title="中途驻留与强制停启",
        description="将单段 deterministic M3 路径拆成两段，在中间节点插入真实 dwell 约束，并在起点声明 mandatory-stop。",
        base_f2_scenario_id="canonical-table-table",
        timing_mode="smoothstep7-feasible",
        reconstruction_policy_id=REFERENCE_M4_POLICY_ID,
        supported_interval_claim="Supported",
        sample_period=0.25,
        request_jerk=True,
        time_law_policy_id="five-axis.time-law.smoothstep7-feasible@1",
        split_for_dwell=True,
        dwell_seconds=0.4,
        topology="dual-table",
    ),
    "zoh-moving-unsupported": _ScenarioDefinition(
        scenario_id="zoh-moving-unsupported",
        title="移动 ZOH 区间不支持",
        description="连续源轨迹仍然 Supported，但移动段使用 ZOH 只能保持 position 能力；区间验证为 Unsupported，标准 Claim 为 Inconclusive。",
        base_f2_scenario_id="canonical-table-table",
        timing_mode="smoothstep7-feasible",
        reconstruction_policy_id=ZOH_POLICY_ID,
        supported_interval_claim="Unsupported",
        sample_period=0.25,
        request_jerk=True,
        time_law_policy_id="five-axis.time-law.smoothstep7-feasible@1",
        topology="dual-table",
    ),
    "polynomial-interior-violation": _ScenarioDefinition(
        scenario_id="polynomial-interior-violation",
        title="多项式区间内部超限反例",
        description="连续轨迹本身 Supported；M5 绑定更严格的命令速度上限，端点速度为零，但 polynomial 重建在采样点之间超限，因此 IntervalCertified 必须 Refuted。",
        base_f2_scenario_id="canonical-table-table",
        timing_mode="smoothstep7-feasible",
        reconstruction_policy_id=POLYNOMIAL_POLICY_ID,
        supported_interval_claim="Refuted",
        sample_period=1.0,
        request_jerk=True,
        time_law_policy_id="five-axis.time-law.smoothstep7-feasible@1",
        topology="dual-table",
    ),
}


def _summary(definition: _ScenarioDefinition) -> F3ScenarioSummary:
    return F3ScenarioSummary(
        scenarioId=definition.scenario_id,
        title=definition.title,
        description=definition.description,
        topology=definition.topology,
        timingMode=definition.timing_mode,
        reconstructionPolicyId=definition.reconstruction_policy_id,
        expectedClaimStatusById=definition.expected_claim_status_by_id(),
    )


def _resolve_timing_api() -> Any:
    try:
        timing = import_module(".f3_timing", package=__package__)
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch in scenario tests
        raise RuntimeError("f3_timing is unavailable; cannot materialize F3 scenario artifacts") from exc
    required = (
        "plan_second_order_time_law",
        "plan_jerk_feasible_time_law",
        "evaluate_continuous_state",
        "verify_continuous_trajectory",
    )
    missing = tuple(name for name in required if not hasattr(timing, name))
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"f3_timing is missing required exports: {joined}")
    return timing


def _unit_limits(unit: str, *, request_jerk: bool) -> tuple[float, float, float | None]:
    if unit == "mm":
        return 120.0, 240.0, 960.0 if request_jerk else None
    return 1.5, 3.0, 12.0 if request_jerk else None


def _upstream_provenance(axis_path: M3CandidateAxisPath, *, method: str) -> ProvenanceRef:
    return ProvenanceRef(
        sourceStage="M3",
        sourceId=axis_path.axis_path_id,
        sourceContentId=_canonical_content_id(axis_path),
        method=method,
    )


def _build_motion_constraint_profile(
    definition: _ScenarioDefinition,
    axis_path: M3CandidateAxisPath,
) -> MotionConstraintProfile:
    axis_constraints = []
    for axis in sorted(axis_path.machine_profile.axes, key=lambda item: item.axis_order):
        velocity, acceleration, jerk = _unit_limits(axis.limits.unit, request_jerk=definition.request_jerk)
        axis_constraints.append(
            AxisMotionConstraint(
                axisId=axis.axis_id,
                unit=axis.limits.unit,
                maximumVelocity=velocity,
                maximumAcceleration=acceleration,
                maximumJerk=jerk,
            )
        )
    node_constraints = []
    if definition.split_for_dwell:
        node_constraints.extend(
            (
                NodeMotionConstraint(
                    nodeId=f"{axis_path.axis_path_id}.node.start",
                    sigma=0.0,
                    boundaryMode="mandatory-stop",
                    rationale="Deterministic stop before the first motion span.",
                ),
                NodeMotionConstraint(
                    nodeId=f"{axis_path.axis_path_id}.node.dwell",
                    sigma=0.5,
                    boundaryMode="dwell",
                    dwellSeconds=definition.dwell_seconds,
                    rationale="Explicit dwell inserted between the two deterministic motion spans.",
                ),
            )
        )
    profile = MotionConstraintProfile(
        artifactType="five-axis.motion-constraint-profile",
        schemaId="five-axis.motion-constraint-profile@1",
        schemaVersion=1,
        profileId=f"five-axis.motion-constraint-profile.{definition.scenario_id}@1",
        machineProfileId=axis_path.machine_profile.profile_id,
        machineProfileContentId=axis_path.machine_profile_content_id,
        axisConstraints=tuple(axis_constraints),
        startBoundary=BoundaryState(sigmaVelocity=0.0, sigmaAcceleration=0.0),
        endBoundary=BoundaryState(sigmaVelocity=0.0, sigmaAcceleration=0.0),
        feedSource="FEDRAT/1200",
        nodeConstraints=tuple(node_constraints),
        policyIds=(
            "five-axis.motion-constraint-profile.strict@1",
            "five-axis.motion-constraint-profile.stop-boundaries@1",
        ),
        provenance=(
            _upstream_provenance(axis_path, method="five-axis.f3.bind-motion-constraints@1"),
        ),
    )
    return profile


def _linear_coefficients(start: tuple[float, ...], end: tuple[float, ...]) -> list[list[float]]:
    return [list(start), [end[index] - start[index] for index in range(5)]]


def _split_axis_path_for_dwell(axis_path: M3CandidateAxisPath) -> M3CandidateAxisPath:
    payload = axis_path.model_dump(mode="json", by_alias=True, exclude_none=True)
    if len(payload["jointSegments"]) != 1:
        raise RuntimeError("dwell-mandatory-stop expects a single deterministic M3 joint segment")
    original_segment = payload["jointSegments"][0]
    selected_branch_id = original_segment["branchId"]
    branch_solutions = [item for item in payload["ikSolutions"] if item["branchId"] == selected_branch_id]
    if len(branch_solutions) < 2:
        raise RuntimeError("dwell-mandatory-stop requires at least two IK solutions on the selected branch")
    branch_solutions.sort(key=lambda item: (float(item["sigma"]), item["solutionId"]))
    start_solution = branch_solutions[0]
    end_solution = branch_solutions[-1]
    midpoint_values = tuple(
        (float(start) + float(end)) * 0.5
        for start, end in zip(start_solution["jointValues"], end_solution["jointValues"], strict=True)
    )
    midpoint_solution_id = f"{payload['axisPathId']}.ik.mid"
    payload["ikSolutions"].append(
        {
            **start_solution,
            "solutionId": midpoint_solution_id,
            "branchId": selected_branch_id,
            "sigma": 0.5,
            "jointValues": midpoint_values,
        }
    )
    payload["ikSolutions"].sort(key=lambda item: (float(item["sigma"]), item["solutionId"]))
    for branch in payload["branchGraph"]["branches"]:
        if branch["branchId"] == selected_branch_id:
            branch["solutionIds"] = tuple(
                item["solutionId"]
                for item in payload["ikSolutions"]
                if item["branchId"] == selected_branch_id
            )
            break
    left_segment_id = f"{payload['axisPathId']}.seg.0"
    right_segment_id = f"{payload['axisPathId']}.seg.1"
    payload["jointSegments"] = [
        {
            **original_segment,
            "segmentId": left_segment_id,
            "sigmaStart": 0.0,
            "sigmaEnd": 0.5,
            "startSolutionId": start_solution["solutionId"],
            "endSolutionId": midpoint_solution_id,
            "coefficients": _linear_coefficients(tuple(start_solution["jointValues"]), midpoint_values),
        },
        {
            **original_segment,
            "segmentId": right_segment_id,
            "sigmaStart": 0.5,
            "sigmaEnd": 1.0,
            "startSolutionId": midpoint_solution_id,
            "endSolutionId": end_solution["solutionId"],
            "coefficients": _linear_coefficients(midpoint_values, tuple(end_solution["jointValues"])),
        },
    ]
    base_mapping = payload["pathProgress"]["mappings"][0]
    payload["pathProgress"]["mappings"] = [
        {
            **base_mapping,
            "mappingId": f"{payload['axisPathId']}.map.0",
            "sourceSegmentId": left_segment_id,
            "sourceLocalStart": 0.0,
            "sourceLocalEnd": 1.0,
            "sigmaStart": 0.0,
            "sigmaEnd": 0.5,
        },
        {
            **base_mapping,
            "mappingId": f"{payload['axisPathId']}.map.1",
            "sourceSegmentId": right_segment_id,
            "sourceLocalStart": 0.0,
            "sourceLocalEnd": 1.0,
            "sigmaStart": 0.5,
            "sigmaEnd": 1.0,
        },
    ]
    payload["nodeEvents"] = [
        {
            "nodeId": f"{payload['axisPathId']}.node.start",
            "sigma": 0.0,
            "eventType": "mandatory-stop",
            "rightSegmentId": left_segment_id,
        },
        {
            "nodeId": f"{payload['axisPathId']}.node.dwell",
            "sigma": 0.5,
            "eventType": "dwell",
            "leftSegmentId": left_segment_id,
            "rightSegmentId": right_segment_id,
        },
    ]
    segment_evidence = payload["regularityCertificate"]["segmentEvidence"][0]
    payload["regularityCertificate"]["segmentEvidence"] = [
        {**segment_evidence, "segmentId": left_segment_id},
        {**segment_evidence, "segmentId": right_segment_id},
    ]
    node_evidence = payload["regularityCertificate"].get("nodeEvidence", [])
    prototype_node_evidence = node_evidence[0] if node_evidence else {
        "continuityClass": "C0",
        "leftDerivatives": [{"order": 0, "components": list(midpoint_values)}],
        "rightDerivatives": [{"order": 0, "components": list(midpoint_values)}],
        "verificationMethod": "analytic-split",
    }
    payload["regularityCertificate"]["nodeEvidence"] = [
        {
            **prototype_node_evidence,
            "nodeId": f"{payload['axisPathId']}.node.start",
            "leftDerivatives": [{"order": 0, "components": list(start_solution["jointValues"])}],
            "rightDerivatives": [{"order": 0, "components": list(start_solution["jointValues"])}],
        },
        {
            **prototype_node_evidence,
            "nodeId": f"{payload['axisPathId']}.node.dwell",
        },
    ]
    payload["kinematicsCertificate"]["intervalCount"] = 2
    return M3CandidateAxisPath.model_validate(payload)


def _normalize_trajectory_identity(
    m4: M4ContinuousTrajectory,
    *,
    trajectory_id: str,
) -> M4ContinuousTrajectory:
    spans = tuple(
        span.model_copy(update={"span_id": f"{trajectory_id}.span.{index}"})
        for index, span in enumerate(m4.spans)
    )
    verification = m4.verification.model_copy(update={"verification_id": f"{trajectory_id}.verification"})
    return m4.model_copy(update={"trajectory_id": trajectory_id, "spans": spans, "verification": verification}, deep=True)


def _plan_continuous_trajectory(
    definition: _ScenarioDefinition,
    axis_path: M3CandidateAxisPath,
    profile: MotionConstraintProfile,
) -> M4ContinuousTrajectory:
    timing = _resolve_timing_api()
    planner_name = (
        "plan_second_order_time_law"
        if definition.timing_mode == "second-order-optimal"
        else "plan_jerk_feasible_time_law"
    )
    planner = getattr(timing, planner_name)
    planned = planner(axis_path, profile)
    m4 = planned if isinstance(planned, M4ContinuousTrajectory) else M4ContinuousTrajectory.model_validate(planned)
    return _normalize_trajectory_identity(
        m4,
        trajectory_id=f"five-axis.m4.{definition.scenario_id}",
    )


def _build_tolerances(axis_path: M3CandidateAxisPath) -> tuple[ToleranceBinding, ...]:
    inherited = tuple(
        ToleranceBinding.model_validate(item.model_dump(mode="json", by_alias=True, exclude_none=True))
        for item in axis_path.source_candidate_geometry.tolerances
    )
    extras = (
        ToleranceBinding(
            toleranceId="five-axis.f3.time-tolerance",
            target="time",
            tolerance=NumericTolerance(absolute=1e-12, unit="s"),
        ),
        ToleranceBinding(
            toleranceId="five-axis.f3.quantization-tolerance",
            target="quantization",
            tolerance=NumericTolerance(absolute=1e-12, unit="dimensionless"),
        ),
    )
    return (*inherited, *extras)


def _build_expected_metrics(
    definition: _ScenarioDefinition,
) -> tuple[ExpectedMetric, ...]:
    metrics: list[ExpectedMetric] = [
        ExpectedMetric(
            metricId=CONTINUOUSLY_FEASIBLE_METRIC_ID,
            expectedStatus="Computed",
            expectedValue=True,
        ),
        ExpectedMetric(
            metricId=TRAJECTORY_DURATION_METRIC_ID,
            expectedStatus="Computed",
            unit="s",
        ),
        ExpectedMetric(
            metricId=AXIS_VELOCITY_UTILIZATION_MAX_METRIC_ID,
            expectedStatus="Computed",
            unit="dimensionless",
        ),
        ExpectedMetric(
            metricId=AXIS_ACCELERATION_UTILIZATION_MAX_METRIC_ID,
            expectedStatus="Computed",
            unit="dimensionless",
        ),
    ]
    if definition.request_jerk:
        metrics.append(
            ExpectedMetric(
                metricId=AXIS_JERK_UTILIZATION_MAX_METRIC_ID,
                expectedStatus="Computed",
                unit="dimensionless",
            )
        )
    metrics.extend(
        (
            ExpectedMetric(
                metricId=INTERVAL_CERTIFIED_METRIC_ID,
                expectedStatus="Computed"
                if definition.supported_interval_claim != "Unsupported"
                else "UnsupportedCapability",
                expectedValue=None
                if definition.supported_interval_claim == "Unsupported"
                else definition.supported_interval_claim == "Supported",
            ),
            ExpectedMetric(
                metricId=SAMPLE_COUNT_METRIC_ID,
                expectedStatus="Computed",
                unit="count",
            ),
            ExpectedMetric(
                metricId=SAMPLE_PERIOD_METRIC_ID,
                expectedStatus="Computed",
                expectedValue=definition.sample_period,
                unit="s",
            ),
            ExpectedMetric(
                metricId=RECONSTRUCTION_POSITION_ERROR_MAX_METRIC_ID,
                expectedStatus="Computed",
                unit="mm",
            ),
            ExpectedMetric(
                metricId=RECONSTRUCTION_ORIENTATION_ERROR_MAX_METRIC_ID,
                expectedStatus="Computed",
                unit="rad",
            ),
        )
    )
    return tuple(metrics)


def _build_manifest(
    definition: _ScenarioDefinition,
    axis_path: M3CandidateAxisPath,
    profile: MotionConstraintProfile,
    continuous: M4ContinuousTrajectory,
    sampled: M5SampledTrajectory | M5DiscreteCommand,
) -> F3MathStageManifest:
    profile_content_id = _canonical_content_id(profile)
    continuous_content_id = _canonical_content_id(continuous)
    sampled_content_id = sampled.content_id
    m5_descriptor = ArtifactDescriptor(
        stage="M5",
        artifactType=sampled.artifact_type,
        schemaId=sampled.schema_id,
    )
    policy_ids = []
    for policy_id in (
        *axis_path.kinematics_certificate.policy_ids,
        *profile.policy_ids,
        definition.time_law_policy_id,
        definition.reconstruction_policy_id,
    ):
        if policy_id not in policy_ids:
            policy_ids.append(policy_id)
    return F3MathStageManifest(
        manifestId="five-axis.f3-math-stage-manifest@1",
        schemaId="five-axis.f3-math-stage-manifest@1",
        schemaVersion=1,
        stage="F3",
        artifactDescriptors=(
            ArtifactDescriptor(stage="M0", artifactType="five-axis.normalized-program", schemaId="five-axis.normalized-program@1"),
            ArtifactDescriptor(stage="M1", artifactType="five-axis.m1-reference-path", schemaId="five-axis.m1-reference-path@1"),
            ArtifactDescriptor(stage="M2", artifactType="five-axis.m2-candidate-task-geometry", schemaId="five-axis.m2-candidate-task-geometry@1"),
            ArtifactDescriptor(stage="M3", artifactType="five-axis.m3-candidate-axis-path", schemaId="five-axis.m3-candidate-axis-path@1"),
            ArtifactDescriptor(stage="M4", artifactType="five-axis.m4-continuous-trajectory", schemaId="five-axis.m4-continuous-trajectory@1"),
            m5_descriptor,
        ),
        motionConstraintProfileSchemaId="five-axis.motion-constraint-profile@1",
        motionConstraintProfileId=profile.profile_id,
        motionConstraintProfileContentId=profile_content_id,
        capabilityIds=(
            CAP_PATH_PROGRESS,
            CAP_REGULARITY,
            CAP_MOTION_CONSTRAINT_PROFILE,
            CAP_TIME_LAW,
            CAP_RECONSTRUCTION,
        ),
        fixtureContentIds=(
            _canonical_content_id(axis_path),
            continuous_content_id,
            sampled_content_id,
        ),
        policyIds=tuple(policy_ids),
        numericEnvironment=current_f3_numeric_environment(),
        expectedMetrics=_build_expected_metrics(definition),
        expectedClaims=(
            ExpectedClaim(
                claimId=CONTINUOUSLY_FEASIBLE_CLAIM_ID,
                claimClass="M4",
                expectedStatus="Supported",
                evidenceLevel="Certified",
            ),
            ExpectedClaim(
                claimId=INTERVAL_CERTIFIED_CLAIM_ID,
                claimClass="M5",
                expectedStatus=definition.expected_interval_claim_status(),
                evidenceLevel=(
                    "Certified"
                    if definition.supported_interval_claim == "Supported"
                    else "Validated"
                    if definition.supported_interval_claim == "Refuted"
                    else None
                ),
            ),
        ),
        expectedEvidence=(
            ExpectedEvidence(evidenceId="lineage", evidenceKind="lineage", required=True),
            ExpectedEvidence(evidenceId="regularity", evidenceKind="regularity", required=True),
            ExpectedEvidence(evidenceId="time-law", evidenceKind="time-law", required=True),
            ExpectedEvidence(evidenceId="node-contract", evidenceKind="node-contract", required=definition.split_for_dwell),
            ExpectedEvidence(evidenceId="reconstruction", evidenceKind="reconstruction", required=True),
            ExpectedEvidence(evidenceId="error-ledger", evidenceKind="error-ledger", required=True),
        ),
        tolerances=_build_tolerances(axis_path),
        decisions=(
            StageDecision(
                decisionId=f"{definition.scenario_id}.acceptance",
                status="accepted",
                rationale=definition.description,
            ),
        ),
    )


def _sample_artifact(
    definition: _ScenarioDefinition,
    continuous: M4ContinuousTrajectory,
) -> M5SampledTrajectory | M5DiscreteCommand:
    artifact = sample_continuous_trajectory(
        continuous,
        sample_period=definition.sample_period,
        policy=definition.reconstruction_policy_id,
        final_hold=definition.final_hold,
    )
    if definition.scenario_id != "polynomial-interior-violation":
        return artifact
    if not isinstance(artifact, M5SampledTrajectory):
        raise RuntimeError("polynomial-interior-violation requires a sampled trajectory")
    usage_by_id = {
        item.axis_id: item for item in continuous.verification.axis_constraint_usage
    }
    ordered_constraints = continuous.motion_constraint_profile.axis_constraints
    moving_axis = max(
        range(len(ordered_constraints)),
        key=lambda index: usage_by_id[ordered_constraints[index].axis_id].maximum_velocity,
    )
    moving_usage = usage_by_id[ordered_constraints[moving_axis].axis_id]
    velocity_limits = list(artifact.limits.velocity_limits or ())
    velocity_limits[moving_axis] = moving_usage.maximum_velocity * 0.5
    limits = artifact.limits.model_copy(
        update={"velocity_limits": tuple(velocity_limits)},
        deep=True,
    )
    draft = artifact.model_copy(
        update={"content_id": "0" * 64, "limits": limits},
        deep=True,
    )
    content_id = _canonical_m5_content_id(draft)
    return M5SampledTrajectory.model_validate(
        draft.model_copy(update={"content_id": content_id}).model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    )


def _run_spec(
    definition: _ScenarioDefinition,
    artifact: M5SampledTrajectory | M5DiscreteCommand,
) -> dict[str, Any]:
    optional_metrics = [
        {"metricId": TRAJECTORY_DURATION_METRIC_ID},
        {"metricId": AXIS_VELOCITY_UTILIZATION_MAX_METRIC_ID},
        {"metricId": AXIS_ACCELERATION_UTILIZATION_MAX_METRIC_ID},
        {"metricId": SAMPLE_COUNT_METRIC_ID},
        {"metricId": SAMPLE_PERIOD_METRIC_ID},
        {"metricId": RECONSTRUCTION_POSITION_ERROR_MAX_METRIC_ID},
        {"metricId": RECONSTRUCTION_ORIENTATION_ERROR_MAX_METRIC_ID},
    ]
    if definition.request_jerk:
        optional_metrics.insert(3, {"metricId": AXIS_JERK_UTILIZATION_MAX_METRIC_ID})
    return {
        "subjectId": f"five-axis.f3.scenario.{definition.scenario_id}@1",
        "domainPackId": FIVE_AXIS_F3_DOMAIN_PACK_ID,
        "runnerId": F3_RUNNER_ID,
        "evaluatorVersion": F3_EVALUATOR_ID,
        "request": {
            "artifact": artifact.model_dump(mode="json", by_alias=True, exclude_none=True),
            "case": {
                "caseId": f"five-axis.f3.case.{definition.scenario_id}@1",
                "requiredMetrics": [
                    {"metricId": CONTINUOUSLY_FEASIBLE_METRIC_ID},
                    {"metricId": INTERVAL_CERTIFIED_METRIC_ID},
                ],
                "optionalMetrics": optional_metrics,
            },
        },
    }


def _build_scenario(definition: _ScenarioDefinition) -> FiveAxisF3Scenario:
    base = load_f2_scenario(definition.base_f2_scenario_id)
    axis_path = _split_axis_path_for_dwell(base.axisPath) if definition.split_for_dwell else base.axisPath
    profile = _build_motion_constraint_profile(definition, axis_path)
    continuous = _plan_continuous_trajectory(definition, axis_path, profile)
    sampled = _sample_artifact(definition, continuous)
    manifest = _build_manifest(definition, axis_path, profile, continuous, sampled)
    return FiveAxisF3Scenario(
        summary=_summary(definition),
        sourceText=base.sourceText,
        normalizedProgram=base.normalizedProgram,
        referencePath=base.referencePath,
        axisPath=axis_path,
        motionConstraintProfile=profile,
        continuousTrajectory=continuous,
        sampledTrajectory=sampled if isinstance(sampled, M5SampledTrajectory) else None,
        discreteCommand=sampled if isinstance(sampled, M5DiscreteCommand) else None,
        manifest=manifest,
        runSpec=_run_spec(definition, sampled),
    )


def list_f3_scenarios() -> tuple[F3ScenarioSummary, ...]:
    return tuple(_summary(_SCENARIO_DEFINITIONS[scenario_id]) for scenario_id in sorted(_SCENARIO_DEFINITIONS))


def load_f3_scenario(id: str) -> FiveAxisF3Scenario:
    try:
        definition = _SCENARIO_DEFINITIONS[id]
    except KeyError as exc:
        available = ", ".join(sorted(_SCENARIO_DEFINITIONS))
        raise KeyError(f"unknown F3 scenario '{id}'; expected one of: {available}") from exc
    return _build_scenario(definition)


def build_f3_manifest(id: str = _DEFAULT_SCENARIO_ID) -> F3MathStageManifest:
    return load_f3_scenario(id).manifest


def f3_example_run_spec(id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    return load_f3_scenario(id).runSpec


def f3_example_payload(id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    scenario = load_f3_scenario(id)
    artifacts = {
        "axisPath": scenario.axisPath.model_dump(mode="json", by_alias=True, exclude_none=True),
        "motionConstraintProfile": scenario.motionConstraintProfile.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "continuousTrajectory": scenario.continuousTrajectory.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
    }
    if scenario.sampledTrajectory is not None:
        artifacts["sampledTrajectory"] = scenario.sampledTrajectory.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    if scenario.discreteCommand is not None:
        artifacts["discreteCommand"] = scenario.discreteCommand.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    return {
        "manifest": scenario.manifest.model_dump(mode="json", by_alias=True, exclude_none=True),
        "scenario": scenario.summary.to_dict(),
        "source": {
            "sourceText": scenario.sourceText,
            "normalizedProgram": scenario.normalizedProgram.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "referencePath": scenario.referencePath.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
        },
        "artifacts": artifacts,
        "runSpec": scenario.runSpec,
    }


def validate_f3_example_run_spec(id: str = _DEFAULT_SCENARIO_ID) -> RunSpec:
    return RunSpec.model_validate(f3_example_run_spec(id))


__all__ = [
    "F3ExampleArtifacts",
    "F3ExamplePayload",
    "F3ExampleSource",
    "F3ScenarioSummary",
    "FiveAxisF3Scenario",
    "build_f3_manifest",
    "current_f3_numeric_environment",
    "f3_example_payload",
    "f3_example_run_spec",
    "list_f3_scenarios",
    "load_f3_scenario",
    "validate_f3_example_run_spec",
]
