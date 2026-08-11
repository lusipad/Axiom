from __future__ import annotations
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field

from ..evaluator import _content_hash
from ..models import AxiomModel, RunSpec
from .f1_models import (
    ExpectedMetric,
    M1ReferencePath,
    M2CandidateTaskGeometry,
    NormalizedProgram,
    StageDecision,
)
from .f1_scenarios import load_f1_scenario
from .f1_runtime import GEOMETRY_VALID_METRIC_ID, TASK_COLLISION_FREE_METRIC_ID
from .f2_collision import ConfigurationCollisionModel
from .f2_kinematics import normalize_numeric_identity
from .f2_models import M3CandidateAxisPath
from .f2_path import lift_m2_path_to_m3_axis_path
from .f2_scenarios import load_f2_scenario
from .f2_runtime import CONFIGURATION_COLLISION_FREE_METRIC_ID, KINEMATICALLY_FEASIBLE_METRIC_ID
from .f3_models import (
    ArtifactDescriptor,
    M4ContinuousTrajectory,
    MotionConstraintProfile,
    NumericTolerance,
    ToleranceBinding,
)
from .f3_sampling import M5DiscreteCommand, POLYNOMIAL_POLICY_ID
from .f3_scenarios import (
    _ScenarioDefinition as _F3ScenarioDefinition,
    _build_motion_constraint_profile,
    _plan_continuous_trajectory,
)
from .f3_runtime import CONTINUOUSLY_FEASIBLE_METRIC_ID, INTERVAL_CERTIFIED_METRIC_ID
from .f4_adapters import (
    FROZEN_CROSS_VALIDATION_TOLERANCES,
    REFERENCE_ADAPTER_DESCRIPTOR,
    SUT_ADAPTER_DESCRIPTOR,
    build_adapter_invocation,
    cross_validate_discrete_commands,
    execute_adapter,
)
from .f4_collision import verify_m5_configuration_collision as verify_m5_collision
from .f4_models import (
    AdapterInvocation,
    AdapterReceipt,
    CrossValidationResult,
    CounterexampleCoverage,
    ExpectedClaim,
    ExpectedEvidence,
    F4MathStageManifest,
    F4ScenarioResult,
    F4StageAcceptanceReport,
    GateClaimStatus,
    M5CollisionVerification,
    TopologyCoverage,
)
from .f4_runtime import (
    ADAPTER_CONTRACT_VALID_METRIC_ID,
    CAP_CROSS_VALIDATION,
    CAP_M5_COLLISION,
    CAP_SOLVER_ADAPTER,
    F4_EVALUATOR_ID,
    F4_RUNNER_ID,
    FIVE_AXIS_F4_DOMAIN_PACK_ID,
    MODEL_COLLISION_FREE_CLAIM_ID,
    MODEL_COLLISION_FREE_METRIC_ID,
    REFERENCE_SUT_ACCELERATION_GAP_MAX_METRIC_ID,
    REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID,
    REFERENCE_SUT_JERK_GAP_MAX_METRIC_ID,
    REFERENCE_SUT_POSITION_GAP_MAX_METRIC_ID,
    REFERENCE_SUT_VELOCITY_GAP_MAX_METRIC_ID,
)


_DEFAULT_SCENARIO_ID = "canonical-dual-table-solver"
_SAMPLE_PERIOD = 0.08
_FINAL_HOLD = False
_COLLISION_CLEARANCE_TOLERANCE_ID = "five-axis.f4.collision-clearance"
_STAGE_GATE_CLAIMS: tuple[
    tuple[str, Literal["M2", "M3", "M4", "M5"], str],
    ...,
] = (
    ("five-axis.geometry-valid-claim@1", "M2", "Validated"),
    ("five-axis.task-geometry-collision-free-claim@1", "M2", "Validated"),
    ("five-axis.kinematically-feasible-claim@1", "M3", "Validated"),
    ("five-axis.configuration-collision-free-claim@1", "M3", "Validated"),
    ("five-axis.continuously-feasible-claim@1", "M4", "Certified"),
    ("five-axis.interval-certified-claim@1", "M5", "Certified"),
    (MODEL_COLLISION_FREE_CLAIM_ID, "M5", "Certified"),
)
_ARTIFACT_DESCRIPTORS = (
    ArtifactDescriptor(stage="M0", artifactType="five-axis.normalized-program", schemaId="five-axis.normalized-program@1"),
    ArtifactDescriptor(stage="M1", artifactType="five-axis.m1-reference-path", schemaId="five-axis.m1-reference-path@1"),
    ArtifactDescriptor(stage="M2", artifactType="five-axis.m2-candidate-task-geometry", schemaId="five-axis.m2-candidate-task-geometry@1"),
    ArtifactDescriptor(stage="M3", artifactType="five-axis.m3-candidate-axis-path", schemaId="five-axis.m3-candidate-axis-path@1"),
    ArtifactDescriptor(stage="M4", artifactType="five-axis.m4-continuous-trajectory", schemaId="five-axis.m4-continuous-trajectory@1"),
    ArtifactDescriptor(stage="M5", artifactType="five-axis.m5-discrete-command", schemaId="five-axis.m5-discrete-command@1"),
)
_CANONICAL_TOPOLOGIES: tuple[Literal["dual-table", "head-table", "dual-head"], ...] = (
    "dual-table",
    "head-table",
    "dual-head",
)


def _canonical_content_hash(payload: Any) -> str:
    serializable = payload.model_dump(mode="json", by_alias=True, exclude_none=True) if hasattr(payload, "model_dump") else payload
    return _content_hash(normalize_numeric_identity(serializable))


@dataclass(frozen=True, slots=True)
class F4ScenarioSummary:
    scenarioId: str
    title: str
    description: str
    topology: str
    sutMode: str
    countsTowardClosure: bool
    expectedOutcome: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenarioId,
            "title": self.title,
            "description": self.description,
            "topology": self.topology,
            "sutMode": self.sutMode,
            "countsTowardClosure": self.countsTowardClosure,
            "expectedOutcome": self.expectedOutcome,
        }


@dataclass(frozen=True, slots=True)
class FiveAxisF4Scenario:
    summary: F4ScenarioSummary
    sourceText: str
    normalizedProgram: NormalizedProgram
    referencePath: M1ReferencePath
    candidateGeometry: M2CandidateTaskGeometry
    stockStateGeometries: dict[str, dict[str, Any]]
    axisPath: M3CandidateAxisPath
    motionConstraintProfile: MotionConstraintProfile
    continuousTrajectory: M4ContinuousTrajectory
    collisionModel: ConfigurationCollisionModel
    referenceInvocation: AdapterInvocation
    sutInvocation: AdapterInvocation
    referenceReceipt: AdapterReceipt
    sutReceipt: AdapterReceipt
    referenceCommand: M5DiscreteCommand | None
    sutCommand: M5DiscreteCommand | None
    crossValidation: CrossValidationResult | None
    collisionVerification: M5CollisionVerification | None
    manifest: F4MathStageManifest
    scenarioResult: F4ScenarioResult
    stageAcceptanceReport: F4StageAcceptanceReport
    runSpec: dict[str, Any] | None


class F4ExampleSource(AxiomModel):
    source_text: str = Field(alias="sourceText")
    normalized_program: NormalizedProgram = Field(alias="normalizedProgram")
    reference_path: M1ReferencePath = Field(alias="referencePath")


class F4ExampleArtifacts(AxiomModel):
    candidate_geometry: M2CandidateTaskGeometry = Field(alias="candidateGeometry")
    stock_state_geometries: dict[str, dict[str, tuple[Any, ...] | list[dict[str, Any]]]] = Field(
        alias="stockStateGeometries"
    )
    axis_path: M3CandidateAxisPath = Field(alias="axisPath")
    motion_constraint_profile: MotionConstraintProfile = Field(alias="motionConstraintProfile")
    continuous_trajectory: M4ContinuousTrajectory = Field(alias="continuousTrajectory")
    collision_model: ConfigurationCollisionModel = Field(alias="collisionModel")
    reference_invocation: AdapterInvocation = Field(alias="referenceInvocation")
    sut_invocation: AdapterInvocation = Field(alias="sutInvocation")
    reference_command: M5DiscreteCommand | None = Field(default=None, alias="referenceCommand")
    sut_command: M5DiscreteCommand | None = Field(default=None, alias="sutCommand")


class F4ExampleEvidence(AxiomModel):
    reference_receipt: AdapterReceipt = Field(alias="referenceReceipt")
    sut_receipt: AdapterReceipt = Field(alias="sutReceipt")
    cross_validation: CrossValidationResult | None = Field(default=None, alias="crossValidation")
    collision_verification: M5CollisionVerification | None = Field(default=None, alias="collisionVerification")
    scenario_result: F4ScenarioResult = Field(alias="scenarioResult")


class F4ExamplePayload(AxiomModel):
    manifest: F4MathStageManifest
    scenario: F4ScenarioSummary
    source: F4ExampleSource
    artifacts: F4ExampleArtifacts
    evidence: F4ExampleEvidence
    acceptance_report: F4StageAcceptanceReport = Field(alias="acceptanceReport")
    run_spec: RunSpec | None = Field(default=None, alias="runSpec")


@dataclass(frozen=True, slots=True)
class _ScenarioDefinition:
    scenario_id: str
    title: str
    description: str
    topology: Literal["dual-table", "head-table", "dual-head"]
    base_f2_scenario_id: str
    kind: Literal["positive", "hash-mismatch", "interior-collision"]
    counts_toward_closure: bool
    counterexample_id: str | None = None


@dataclass(frozen=True, slots=True)
class _ScenarioCore:
    definition: _ScenarioDefinition
    source_text: str
    normalized_program: NormalizedProgram
    reference_path: M1ReferencePath
    candidate_geometry: M2CandidateTaskGeometry
    stock_state_geometries: dict[str, dict[str, Any]]
    axis_path: M3CandidateAxisPath
    motion_constraint_profile: MotionConstraintProfile
    continuous_trajectory: M4ContinuousTrajectory
    collision_model: ConfigurationCollisionModel
    reference_invocation: AdapterInvocation
    sut_invocation: AdapterInvocation
    reference_receipt: AdapterReceipt
    sut_receipt: AdapterReceipt
    reference_command: M5DiscreteCommand | None
    sut_command: M5DiscreteCommand | None
    cross_validation: CrossValidationResult | None
    collision_verification: M5CollisionVerification | None
    manifest: F4MathStageManifest
    scenario_result: F4ScenarioResult
    run_spec: dict[str, Any] | None


_SCENARIO_DEFINITIONS: dict[str, _ScenarioDefinition] = {
    "canonical-dual-table-solver": _ScenarioDefinition(
        scenario_id="canonical-dual-table-solver",
        title="双转台 solver 验收",
        description="在 dual-table canonical F2 基础上注入 F1 nominal 安全上下文，重新提升到 M3，并验证 reference/sut adapter 与安全 M5 碰撞证书。",
        topology="dual-table",
        base_f2_scenario_id="canonical-table-table",
        kind="positive",
        counts_toward_closure=True,
    ),
    "canonical-head-table-solver": _ScenarioDefinition(
        scenario_id="canonical-head-table-solver",
        title="摆头转台 solver 验收",
        description="在 head-table canonical F2 基础上注入 F1 nominal 安全上下文，重新提升到 M3，并验证 reference/sut adapter 与安全 M5 碰撞证书。",
        topology="head-table",
        base_f2_scenario_id="canonical-head-table",
        kind="positive",
        counts_toward_closure=True,
    ),
    "canonical-dual-head-solver": _ScenarioDefinition(
        scenario_id="canonical-dual-head-solver",
        title="双摆头 solver 验收",
        description="在 dual-head canonical F2 基础上注入 F1 nominal 安全上下文，重新提升到 M3，并验证 reference/sut adapter 与安全 M5 碰撞证书。",
        topology="dual-head",
        base_f2_scenario_id="canonical-head-head",
        kind="positive",
        counts_toward_closure=True,
    ),
    "adapter-input-hash-mismatch": _ScenarioDefinition(
        scenario_id="adapter-input-hash-mismatch",
        title="Adapter 输入哈希失配反例",
        description="reference 正常执行，SUT invocation 篡改 inputM4ContentHash，必须返回 Failed 且不产生命令。",
        topology="dual-table",
        base_f2_scenario_id="canonical-table-table",
        kind="hash-mismatch",
        counts_toward_closure=False,
        counterexample_id="counterexample.adapter-input-hash-mismatch",
    ),
    "interval-interior-collision": _ScenarioDefinition(
        scenario_id="interval-interior-collision",
        title="M5 区间内部碰撞反例",
        description="复用 dual-table 正向 solver command，但用 configuration-interior-collision 的 collisionModel 验证端点安全、区间内部碰撞。",
        topology="dual-table",
        base_f2_scenario_id="canonical-table-table",
        kind="interior-collision",
        counts_toward_closure=False,
        counterexample_id="counterexample.interval-interior-collision",
    ),
}


def _summary(definition: _ScenarioDefinition) -> F4ScenarioSummary:
    return F4ScenarioSummary(
        scenarioId=definition.scenario_id,
        title=definition.title,
        description=definition.description,
        topology=definition.topology,
        sutMode="solver",
        countsTowardClosure=definition.counts_toward_closure,
        expectedOutcome="Passed",
    )


def _sample_period_for(definition: _ScenarioDefinition) -> float:
    return 0.25 if definition.kind == "interior-collision" else _SAMPLE_PERIOD


def _f3_definition(definition: _ScenarioDefinition) -> _F3ScenarioDefinition:
    return _F3ScenarioDefinition(
        scenario_id=definition.scenario_id,
        title=definition.title,
        description=definition.description,
        base_f2_scenario_id=definition.base_f2_scenario_id,
        timing_mode="smoothstep7-feasible",
        reconstruction_policy_id=POLYNOMIAL_POLICY_ID,
        supported_interval_claim="Supported",
        sample_period=_sample_period_for(definition),
        request_jerk=True,
        time_law_policy_id="five-axis.time-law.smoothstep7-feasible@1",
        topology=definition.topology,
    )


def _collision_clearance_tolerance(collision_model: ConfigurationCollisionModel) -> ToleranceBinding:
    return ToleranceBinding(
        toleranceId=_COLLISION_CLEARANCE_TOLERANCE_ID,
        target="collision-clearance",
        tolerance=NumericTolerance(
            absolute=collision_model.minimum_clearance.absolute,
            relative=0.0,
            unit=collision_model.minimum_clearance.unit,
        ),
    )


def _expected_claims() -> tuple[ExpectedClaim, ...]:
    return tuple(
        ExpectedClaim(
            claimId=claim_id,
            claimClass=claim_class,
            expectedStatus="Supported",
            evidenceLevel=evidence_level,
        )
        for claim_id, claim_class, evidence_level in _STAGE_GATE_CLAIMS
    )


def _gate_claim_statuses() -> tuple[GateClaimStatus, ...]:
    return tuple(
        GateClaimStatus(
            claimId=claim_id,
            status="Supported",
            evidenceLevel=evidence_level,
        )
        for claim_id, _, evidence_level in _STAGE_GATE_CLAIMS
    )


def _expected_metrics() -> tuple[ExpectedMetric, ...]:
    return (
        ExpectedMetric(
            metricId=ADAPTER_CONTRACT_VALID_METRIC_ID,
            expectedStatus="Computed",
            expectedValue=True,
        ),
        ExpectedMetric(
            metricId=REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID,
            expectedStatus="Computed",
            expectedValue=True,
        ),
        ExpectedMetric(
            metricId=REFERENCE_SUT_POSITION_GAP_MAX_METRIC_ID,
            expectedStatus="Computed",
            unit="axis-unit",
        ),
        ExpectedMetric(
            metricId=REFERENCE_SUT_VELOCITY_GAP_MAX_METRIC_ID,
            expectedStatus="Computed",
            unit="axis-unit/s",
        ),
        ExpectedMetric(
            metricId=REFERENCE_SUT_ACCELERATION_GAP_MAX_METRIC_ID,
            expectedStatus="Computed",
            unit="axis-unit/s^2",
        ),
        ExpectedMetric(
            metricId=REFERENCE_SUT_JERK_GAP_MAX_METRIC_ID,
            expectedStatus="Computed",
            unit="axis-unit/s^3",
        ),
        ExpectedMetric(
            metricId=MODEL_COLLISION_FREE_METRIC_ID,
            expectedStatus="Computed",
        ),
    )


def _expected_evidence() -> tuple[ExpectedEvidence, ...]:
    return (
        ExpectedEvidence(evidenceId="evidence.reference-descriptor", evidenceKind="adapter-descriptor", required=True),
        ExpectedEvidence(evidenceId="evidence.reference-invocation", evidenceKind="adapter-invocation", required=True),
        ExpectedEvidence(evidenceId="evidence.receipt", evidenceKind="adapter-receipt", required=True),
        ExpectedEvidence(evidenceId="evidence.cross", evidenceKind="cross-validation", required=True),
        ExpectedEvidence(evidenceId="evidence.collision", evidenceKind="reconstruction-collision", required=True),
        ExpectedEvidence(evidenceId="evidence.stage-acceptance", evidenceKind="stage-acceptance", required=True),
    )


def _base_positive_artifacts(definition: _ScenarioDefinition) -> tuple[
    str,
    NormalizedProgram,
    M1ReferencePath,
    M2CandidateTaskGeometry,
    dict[str, dict[str, Any]],
    M3CandidateAxisPath,
    MotionConstraintProfile,
    M4ContinuousTrajectory,
    ConfigurationCollisionModel,
]:
    base_f1 = load_f1_scenario("nominal-certified")
    base_f2 = load_f2_scenario(definition.base_f2_scenario_id)
    candidate_geometry = base_f2.candidateGeometry.model_copy(
        update={
            "collision_context": base_f1.candidateGeometry.collision_context,
            "process_state_timeline": base_f1.candidateGeometry.process_state_timeline,
        },
        deep=True,
    )
    lift = lift_m2_path_to_m3_axis_path(candidate_geometry, base_f2.axisPath.machine_profile)
    if lift.status != "Supported" or lift.axis_path is None:
        raise RuntimeError(f"built-in F4 scenario '{definition.scenario_id}' failed path lifting: {lift.reason_code}")
    motion_constraint_profile = _build_motion_constraint_profile(_f3_definition(definition), lift.axis_path)
    continuous_trajectory = _plan_continuous_trajectory(_f3_definition(definition), lift.axis_path, motion_constraint_profile)
    return (
        base_f2.sourceText,
        base_f2.normalizedProgram,
        base_f2.referencePath,
        candidate_geometry,
        base_f1.stockStateGeometries,
        lift.axis_path,
        motion_constraint_profile,
        continuous_trajectory,
        base_f2.collisionModel,
    )


def _build_manifest(
    definition: _ScenarioDefinition,
    *,
    candidate_geometry: M2CandidateTaskGeometry,
    axis_path: M3CandidateAxisPath,
    continuous_trajectory: M4ContinuousTrajectory,
    collision_model: ConfigurationCollisionModel,
    reference_invocation: AdapterInvocation,
    sut_invocation: AdapterInvocation,
    reference_receipt: AdapterReceipt,
    sut_receipt: AdapterReceipt,
    reference_command: M5DiscreteCommand | None,
    sut_command: M5DiscreteCommand | None,
) -> F4MathStageManifest:
    fixture_hashes = [
        _canonical_content_hash(candidate_geometry),
        _canonical_content_hash(axis_path),
        _canonical_content_hash(continuous_trajectory),
        _canonical_content_hash(collision_model),
        _canonical_content_hash(reference_invocation),
        _canonical_content_hash(sut_invocation),
        _canonical_content_hash(reference_receipt),
        _canonical_content_hash(sut_receipt),
    ]
    if reference_command is not None:
        fixture_hashes.append(reference_command.content_id)
    if sut_command is not None:
        fixture_hashes.append(sut_command.content_id)
    policy_ids: list[str] = []
    for policy_id in (
        *axis_path.kinematics_certificate.policy_ids,
        *tuple(item.policy_id for item in (collision_model,)),
        *continuous_trajectory.motion_constraint_profile.policy_ids,
        "five-axis.time-law.smoothstep7-feasible@1",
        POLYNOMIAL_POLICY_ID,
        "five-axis.f4.adapter-cross-validation.polynomial@1",
        "five-axis.f4.m5-polynomial-collision-envelope@1",
    ):
        if isinstance(policy_id, str) and policy_id not in policy_ids:
            policy_ids.append(policy_id)
    return F4MathStageManifest(
        manifestId="five-axis.f4-math-stage-manifest@1",
        schemaId="five-axis.f4-math-stage-manifest@1",
        schemaVersion=1,
        stage="F4",
        artifactDescriptors=_ARTIFACT_DESCRIPTORS,
        adapterTransport="in-process",
        capabilityIds=(
            CAP_SOLVER_ADAPTER,
            CAP_CROSS_VALIDATION,
            CAP_M5_COLLISION,
        ),
        fixtureContentIds=tuple(dict.fromkeys(fixture_hashes)),
        policyIds=tuple(policy_ids),
        numericEnvironment=dict(reference_receipt.numeric_environment),
        expectedMetrics=_expected_metrics(),
        expectedClaims=_expected_claims(),
        expectedEvidence=_expected_evidence(),
        tolerances=(*FROZEN_CROSS_VALIDATION_TOLERANCES, _collision_clearance_tolerance(collision_model)),
        decisions=(
            StageDecision(
                decisionId=f"{definition.scenario_id}.acceptance",
                status="accepted",
                rationale=definition.description,
            ),
        ),
    )


def _scenario_result(
    definition: _ScenarioDefinition,
    *,
    reference_receipt: AdapterReceipt,
    sut_receipt: AdapterReceipt,
    reference_command: M5DiscreteCommand | None,
    sut_command: M5DiscreteCommand | None,
    cross_validation: CrossValidationResult | None,
    collision_verification: M5CollisionVerification | None,
) -> F4ScenarioResult:
    if definition.kind == "positive":
        passed = (
            reference_receipt.status == "Succeeded"
            and sut_receipt.status == "Succeeded"
            and reference_command is not None
            and sut_command is not None
            and cross_validation is not None
            and cross_validation.status == "Supported"
            and collision_verification is not None
            and collision_verification.status == "safe"
            and collision_verification.supports_model_collision_aggregation
        )
    elif definition.kind == "hash-mismatch":
        passed = (
            reference_receipt.status == "Succeeded"
            and reference_command is not None
            and sut_receipt.status == "Failed"
            and sut_receipt.failure_code == "InputContentHashMismatch"
            and sut_command is None
        )
    else:
        passed = (
            reference_receipt.status == "Succeeded"
            and sut_receipt.status == "Succeeded"
            and reference_command is not None
            and sut_command is not None
            and cross_validation is not None
            and cross_validation.status == "Supported"
            and collision_verification is not None
            and collision_verification.status == "collision"
            and collision_verification.supports_model_collision_aggregation is False
        )
    return F4ScenarioResult(
        scenarioId=definition.scenario_id,
        topology=definition.topology,
        sutMode="solver",
        countsTowardClosure=definition.counts_toward_closure,
        outcome="Passed" if passed else "Failed",
        referenceReceiptStatus=reference_receipt.status,
        sutReceiptStatus=sut_receipt.status,
        crossValidationStatus=cross_validation.status if cross_validation is not None else "Inconclusive",
        collisionStatus=collision_verification.status if collision_verification is not None else "unsupported",
    )


def _positive_run_spec(core: _ScenarioCore) -> dict[str, Any] | None:
    if (
        core.definition.kind != "positive"
        or core.reference_command is None
        or core.sut_command is None
        or core.reference_receipt.status != "Succeeded"
        or core.sut_receipt.status != "Succeeded"
    ):
        return None
    required_metrics = [
        GEOMETRY_VALID_METRIC_ID,
        TASK_COLLISION_FREE_METRIC_ID,
        KINEMATICALLY_FEASIBLE_METRIC_ID,
        CONFIGURATION_COLLISION_FREE_METRIC_ID,
        CONTINUOUSLY_FEASIBLE_METRIC_ID,
        INTERVAL_CERTIFIED_METRIC_ID,
        MODEL_COLLISION_FREE_METRIC_ID,
        ADAPTER_CONTRACT_VALID_METRIC_ID,
        REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID,
    ]
    optional_metrics = [
        REFERENCE_SUT_POSITION_GAP_MAX_METRIC_ID,
        REFERENCE_SUT_VELOCITY_GAP_MAX_METRIC_ID,
        REFERENCE_SUT_ACCELERATION_GAP_MAX_METRIC_ID,
        REFERENCE_SUT_JERK_GAP_MAX_METRIC_ID,
    ]
    return {
        "subjectId": f"five-axis.f4.scenario.{core.definition.scenario_id}@1",
        "domainPackId": FIVE_AXIS_F4_DOMAIN_PACK_ID,
        "runnerId": F4_RUNNER_ID,
        "evaluatorVersion": F4_EVALUATOR_ID,
        "request": {
            "artifact": core.sut_command.model_dump(mode="json", by_alias=True, exclude_none=True),
            "referenceArtifact": core.reference_command.model_dump(mode="json", by_alias=True, exclude_none=True),
            "referenceInvocation": core.reference_invocation.model_dump(mode="json", by_alias=True, exclude_none=True),
            "sutInvocation": core.sut_invocation.model_dump(mode="json", by_alias=True, exclude_none=True),
            "referenceReceipt": core.reference_receipt.model_dump(mode="json", by_alias=True, exclude_none=True),
            "sutReceipt": core.sut_receipt.model_dump(mode="json", by_alias=True, exclude_none=True),
            "referencePath": core.reference_path.model_dump(mode="json", by_alias=True, exclude_none=True),
            "stockStateGeometries": core.stock_state_geometries,
            "collisionModel": core.collision_model.model_dump(mode="json", by_alias=True, exclude_none=True),
            "case": {
                "caseId": f"five-axis.f4.case.{core.definition.scenario_id}@1",
                "requiredMetrics": [{"metricId": metric_id} for metric_id in required_metrics],
                "optionalMetrics": [{"metricId": metric_id} for metric_id in optional_metrics],
            },
        },
    }


@lru_cache(maxsize=None)
def _build_scenario_core(id: str) -> _ScenarioCore:
    try:
        definition = _SCENARIO_DEFINITIONS[id]
    except KeyError as exc:
        available = ", ".join(sorted(_SCENARIO_DEFINITIONS))
        raise KeyError(f"unknown F4 scenario '{id}'; expected one of: {available}") from exc
    (
        source_text,
        normalized_program,
        reference_path,
        candidate_geometry,
        stock_state_geometries,
        axis_path,
        motion_constraint_profile,
        continuous_trajectory,
        safe_collision_model,
    ) = _base_positive_artifacts(definition)
    collision_model = safe_collision_model
    reference_invocation = build_adapter_invocation(
        REFERENCE_ADAPTER_DESCRIPTOR,
        continuous_trajectory,
        sample_period=_sample_period_for(definition),
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=_FINAL_HOLD,
        invocation_id=f"{definition.scenario_id}.reference.invoke",
    )
    sut_invocation = build_adapter_invocation(
        SUT_ADAPTER_DESCRIPTOR,
        continuous_trajectory,
        sample_period=_sample_period_for(definition),
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=_FINAL_HOLD,
        invocation_id=f"{definition.scenario_id}.sut.invoke",
    )
    if definition.kind == "hash-mismatch":
        sut_invocation = sut_invocation.model_copy(update={"input_m4_content_hash": "b" * 64})
    reference_receipt, reference_command = execute_adapter(reference_invocation, continuous_trajectory)
    sut_receipt, sut_command = execute_adapter(sut_invocation, continuous_trajectory)
    cross_validation = None
    collision_verification = None
    if reference_command is not None and sut_command is not None:
        cross_validation = cross_validate_discrete_commands(reference_command, sut_command)
    if definition.kind == "interior-collision":
        collision_model = load_f2_scenario("configuration-interior-collision").collisionModel
    if sut_command is not None and definition.kind != "hash-mismatch":
        collision_verification = verify_m5_collision(sut_command, collision_model=collision_model)
    manifest = _build_manifest(
        definition,
        candidate_geometry=candidate_geometry,
        axis_path=axis_path,
        continuous_trajectory=continuous_trajectory,
        collision_model=collision_model,
        reference_invocation=reference_invocation,
        sut_invocation=sut_invocation,
        reference_receipt=reference_receipt,
        sut_receipt=sut_receipt,
        reference_command=reference_command,
        sut_command=sut_command,
    )
    scenario_result = _scenario_result(
        definition,
        reference_receipt=reference_receipt,
        sut_receipt=sut_receipt,
        reference_command=reference_command,
        sut_command=sut_command,
        cross_validation=cross_validation,
        collision_verification=collision_verification,
    )
    provisional_core = _ScenarioCore(
        definition=definition,
        source_text=source_text,
        normalized_program=normalized_program,
        reference_path=reference_path,
        candidate_geometry=candidate_geometry,
        stock_state_geometries=stock_state_geometries,
        axis_path=axis_path,
        motion_constraint_profile=motion_constraint_profile,
        continuous_trajectory=continuous_trajectory,
        collision_model=collision_model,
        reference_invocation=reference_invocation,
        sut_invocation=sut_invocation,
        reference_receipt=reference_receipt,
        sut_receipt=sut_receipt,
        reference_command=reference_command,
        sut_command=sut_command,
        cross_validation=cross_validation,
        collision_verification=collision_verification,
        manifest=manifest,
        scenario_result=scenario_result,
        run_spec=None,
    )
    return replace(provisional_core, run_spec=_positive_run_spec(provisional_core))


@lru_cache(maxsize=1)
def build_f4_stage_acceptance_report() -> F4StageAcceptanceReport:
    scenario_results = tuple(_build_scenario_core(scenario_id).scenario_result for scenario_id in _SCENARIO_DEFINITIONS)
    topology_coverage = tuple(
        TopologyCoverage(
            topology=topology,
            covered=any(
                result.topology == topology
                and result.counts_toward_closure
                and result.outcome == "Passed"
                for result in scenario_results
            ),
        )
        for topology in _CANONICAL_TOPOLOGIES
    )
    counterexample_coverage = tuple(
        CounterexampleCoverage(
            counterexampleId=definition.counterexample_id,
            covered=_build_scenario_core(definition.scenario_id).scenario_result.outcome == "Passed",
        )
        for definition in _SCENARIO_DEFINITIONS.values()
        if definition.counterexample_id is not None
    )
    payload = {
        "reportId": "five-axis.f4.acceptance-report.v1",
        "stage": "F4",
        "scenarioResults": [
            result.model_dump(mode="json", by_alias=True, exclude_none=True)
            for result in scenario_results
        ],
        "topologyCoverage": [
            item.model_dump(mode="json", by_alias=True, exclude_none=True)
            for item in topology_coverage
        ],
        "counterexampleCoverage": [
            item.model_dump(mode="json", by_alias=True, exclude_none=True)
            for item in counterexample_coverage
        ],
        "gateClaimStatuses": [
            item.model_dump(mode="json", by_alias=True, exclude_none=True)
            for item in _gate_claim_statuses()
        ],
        "status": "Passed" if all(item.outcome == "Passed" for item in scenario_results) else "Failed",
    }
    payload["contentHash"] = _content_hash(normalize_numeric_identity(payload))
    return F4StageAcceptanceReport.model_validate(payload)


def build_f4_manifest(id: str = _DEFAULT_SCENARIO_ID) -> F4MathStageManifest:
    return _build_scenario_core(id).manifest


def f4_example_run_spec(id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    scenario = load_f4_scenario(id)
    if scenario.runSpec is None:
        raise ValueError(f"F4 scenario '{id}' does not publish a positive runSpec")
    return scenario.runSpec


def validate_f4_example_run_spec(id: str = _DEFAULT_SCENARIO_ID) -> RunSpec:
    return RunSpec.model_validate(f4_example_run_spec(id))


def list_f4_scenarios() -> tuple[F4ScenarioSummary, ...]:
    return tuple(_summary(_SCENARIO_DEFINITIONS[scenario_id]) for scenario_id in _SCENARIO_DEFINITIONS)


def load_f4_scenario(id: str) -> FiveAxisF4Scenario:
    core = _build_scenario_core(id)
    return FiveAxisF4Scenario(
        summary=_summary(core.definition),
        sourceText=core.source_text,
        normalizedProgram=core.normalized_program,
        referencePath=core.reference_path,
        candidateGeometry=core.candidate_geometry,
        stockStateGeometries=core.stock_state_geometries,
        axisPath=core.axis_path,
        motionConstraintProfile=core.motion_constraint_profile,
        continuousTrajectory=core.continuous_trajectory,
        collisionModel=core.collision_model,
        referenceInvocation=core.reference_invocation,
        sutInvocation=core.sut_invocation,
        referenceReceipt=core.reference_receipt,
        sutReceipt=core.sut_receipt,
        referenceCommand=core.reference_command,
        sutCommand=core.sut_command,
        crossValidation=core.cross_validation,
        collisionVerification=core.collision_verification,
        manifest=core.manifest,
        scenarioResult=core.scenario_result,
        stageAcceptanceReport=build_f4_stage_acceptance_report(),
        runSpec=core.run_spec,
    )


def f4_example_payload(id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    scenario = load_f4_scenario(id)
    payload = {
        "manifest": scenario.manifest.model_dump(mode="json", by_alias=True, exclude_none=True),
        "scenario": scenario.summary.to_dict(),
        "source": {
            "sourceText": scenario.sourceText,
            "normalizedProgram": scenario.normalizedProgram.model_dump(mode="json", by_alias=True, exclude_none=True),
            "referencePath": scenario.referencePath.model_dump(mode="json", by_alias=True, exclude_none=True),
        },
        "artifacts": {
            "candidateGeometry": scenario.candidateGeometry.model_dump(mode="json", by_alias=True, exclude_none=True),
            "stockStateGeometries": scenario.stockStateGeometries,
            "axisPath": scenario.axisPath.model_dump(mode="json", by_alias=True, exclude_none=True),
            "motionConstraintProfile": scenario.motionConstraintProfile.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "continuousTrajectory": scenario.continuousTrajectory.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "collisionModel": scenario.collisionModel.model_dump(mode="json", by_alias=True, exclude_none=True),
            "referenceInvocation": scenario.referenceInvocation.model_dump(mode="json", by_alias=True, exclude_none=True),
            "sutInvocation": scenario.sutInvocation.model_dump(mode="json", by_alias=True, exclude_none=True),
            "referenceCommand": (
                scenario.referenceCommand.model_dump(mode="json", by_alias=True, exclude_none=True)
                if scenario.referenceCommand is not None
                else None
            ),
            "sutCommand": (
                scenario.sutCommand.model_dump(mode="json", by_alias=True, exclude_none=True)
                if scenario.sutCommand is not None
                else None
            ),
        },
        "evidence": {
            "referenceReceipt": scenario.referenceReceipt.model_dump(mode="json", by_alias=True, exclude_none=True),
            "sutReceipt": scenario.sutReceipt.model_dump(mode="json", by_alias=True, exclude_none=True),
            "crossValidation": (
                scenario.crossValidation.model_dump(mode="json", by_alias=True, exclude_none=True)
                if scenario.crossValidation is not None
                else None
            ),
            "collisionVerification": (
                scenario.collisionVerification.model_dump(mode="json", by_alias=True, exclude_none=True)
                if scenario.collisionVerification is not None
                else None
            ),
            "scenarioResult": scenario.scenarioResult.model_dump(mode="json", by_alias=True, exclude_none=True),
        },
        "acceptanceReport": scenario.stageAcceptanceReport.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    if scenario.runSpec is not None:
        payload["runSpec"] = scenario.runSpec
    return payload


__all__ = [
    "F4_EVALUATOR_ID",
    "F4_RUNNER_ID",
    "F4ExampleArtifacts",
    "F4ExampleEvidence",
    "F4ExamplePayload",
    "F4ExampleSource",
    "F4ScenarioSummary",
    "FIVE_AXIS_F4_DOMAIN_PACK_ID",
    "FiveAxisF4Scenario",
    "build_f4_manifest",
    "build_f4_stage_acceptance_report",
    "f4_example_payload",
    "f4_example_run_spec",
    "list_f4_scenarios",
    "load_f4_scenario",
    "validate_f4_example_run_spec",
]
