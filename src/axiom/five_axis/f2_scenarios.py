from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import Field

from ..evaluator import _content_hash
from ..models import AxiomModel, RunSpec
from .f1_geometry import build_provenance_progress_correspondence
from .f1_models import (
    AxisAlignedBoundingBox,
    ExpectedMetric,
    M1ReferencePath,
    M2CandidateTaskGeometry,
    NumericTolerance,
    NormalizedProgram,
    ProvenanceProgressPolicy,
    ProvenanceRef,
    StageDecision,
    ToleranceBinding,
)
from .f1_parser import parse_axiom_cl_subset
from .f1_pipeline import build_m1_reference_path
from .f1_scenarios import _actual_path
from .f2_collision import (
    CollisionEntity,
    CollisionPair,
    CollisionTolerance,
    ConfigurationCollisionModel,
    hash_configuration_collision_model,
)
from .f2_kinematics import (
    build_canonical_head_head_cb_profile,
    build_canonical_head_table_bc_profile,
    build_canonical_table_table_ac_profile,
)
from .f2_models import (
    ArtifactDescriptor,
    ExpectedClaim,
    ExpectedEvidence,
    F2MathStageManifest,
    M3CandidateAxisPath,
    MachineProfile,
)
from .f2_path import lift_m2_path_to_m3_axis_path
from .f2_runtime import (
    AXIS_LIMIT_MARGIN_MIN_METRIC_ID,
    CAP_CONFIGURATION_COLLISION,
    CAP_MACHINE_PROFILE,
    CAP_PATH_PROGRESS,
    CAP_REGULARITY,
    CONFIGURATION_COLLISION_FREE_CLAIM_ID,
    CONFIGURATION_COLLISION_FREE_METRIC_ID,
    F2_EVALUATOR_ID,
    F2_RUNNER_ID,
    FIVE_AXIS_F2_DOMAIN_PACK_ID,
    KINEMATICALLY_FEASIBLE_CLAIM_ID,
    KINEMATICALLY_FEASIBLE_METRIC_ID,
    ORIENTATION_RESIDUAL_MAX_METRIC_ID,
    POSITION_RESIDUAL_MAX_METRIC_ID,
    SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID,
    current_f2_numeric_environment,
)


_DEFAULT_SCENARIO_ID = "canonical-table-table"
_SOURCE_TEXT = (
    "UNITS/MM\n"
    "FROM/-0.8,0,0,0.2,0.1,0.9746794344808963\n"
    "FEDRAT/1200\n"
    "GOTO/0.8,0,0\n"
    "END\n"
)

_ProfileBuilder = Callable[[], MachineProfile]


@dataclass(frozen=True, slots=True)
class F2ScenarioSummary:
    scenarioId: str
    title: str
    description: str
    topology: str
    expectedClaimStatusById: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenarioId,
            "title": self.title,
            "description": self.description,
            "topology": self.topology,
            "expectedClaimStatusById": dict(self.expectedClaimStatusById),
        }


@dataclass(frozen=True, slots=True)
class FiveAxisF2Scenario:
    summary: F2ScenarioSummary
    sourceText: str
    normalizedProgram: NormalizedProgram
    referencePath: M1ReferencePath
    candidateGeometry: M2CandidateTaskGeometry
    axisPath: M3CandidateAxisPath
    collisionModel: ConfigurationCollisionModel
    manifest: F2MathStageManifest
    runSpec: dict[str, Any]


class F2ExampleSource(AxiomModel):
    source_text: str = Field(alias="sourceText")
    normalized_program: NormalizedProgram = Field(alias="normalizedProgram")
    reference_path: M1ReferencePath = Field(alias="referencePath")


class F2ExampleArtifacts(AxiomModel):
    candidate_geometry: M2CandidateTaskGeometry = Field(alias="candidateGeometry")
    axis_path: M3CandidateAxisPath = Field(alias="axisPath")
    machine_profile: MachineProfile = Field(alias="machineProfile")
    collision_model: ConfigurationCollisionModel = Field(alias="collisionModel")


class F2ExamplePayload(AxiomModel):
    manifest: F2MathStageManifest
    scenario: F2ScenarioSummary
    source: F2ExampleSource
    artifacts: F2ExampleArtifacts
    run_spec: RunSpec = Field(alias="runSpec")


def _box(
    min_corner: tuple[float, float, float],
    max_corner: tuple[float, float, float],
) -> AxisAlignedBoundingBox:
    return AxisAlignedBoundingBox(minCorner=min_corner, maxCorner=max_corner)


def _candidate_geometry(
    scenario_id: str,
) -> tuple[NormalizedProgram, M1ReferencePath, M2CandidateTaskGeometry]:
    normalized_program = parse_axiom_cl_subset(_SOURCE_TEXT)
    reference_path = build_m1_reference_path(normalized_program)
    candidate_id = f"five-axis.f2.scenario.{scenario_id}.candidate"
    actual_path = _actual_path(
        reference_path,
        geometry_id=candidate_id,
        position_delta=(0.0, 0.0, 0.0),
    )
    correspondence = build_provenance_progress_correspondence(
        actual_path,
        reference_path,
        policy=ProvenanceProgressPolicy(
            strategyId="five-axis.correspondence.provenance-progress@1",
            allowedSourceInterval=(0.0, 1.0),
            allowedTargetInterval=(0.0, 1.0),
            objective="preserve-source-lineage",
            deterministicTieBreak="lowest-source-segment-id",
            numericTolerance=NumericTolerance(
                absolute=0.0,
                relative=0.0,
                unit="dimensionless",
            ),
        ),
        certificate_id=f"five-axis.f2.scenario.{scenario_id}.correspondence",
    )
    candidate = M2CandidateTaskGeometry(
        artifactType="five-axis.m2-candidate-task-geometry",
        schemaVersion=1,
        candidateGeometryId=candidate_id,
        sourceReferencePathId=reference_path.reference_path_id,
        sourceReferencePathContentId=_content_hash(
            reference_path.model_dump(mode="json", by_alias=True, exclude_none=True)
        ),
        coordinateContext=reference_path.coordinate_context,
        pathProgress=actual_path.path_progress,
        positionSemantics=actual_path.position_semantics,
        staticPosition=actual_path.static_position,
        positionSegments=actual_path.position_segments,
        orientationSegments=actual_path.orientation_segments,
        nodeEvents=actual_path.node_events,
        regularityCertificate=actual_path.regularity_certificate,
        tolerances=(
            ToleranceBinding(
                toleranceId="five-axis.f2.position-tolerance",
                target="position",
                tolerance=NumericTolerance(absolute=1e-6, relative=0.0, unit="mm"),
            ),
            ToleranceBinding(
                toleranceId="five-axis.f2.orientation-tolerance",
                target="orientation",
                tolerance=NumericTolerance(absolute=1e-9, relative=0.0, unit="rad"),
            ),
        ),
        correspondence=correspondence,
        provenance=(
            ProvenanceRef(
                sourceStage="M1",
                sourceId=reference_path.reference_path_id,
                sourceContentId=_content_hash(
                    reference_path.model_dump(mode="json", by_alias=True, exclude_none=True)
                ),
                method="five-axis.f2.identity-task-geometry@1",
            ),
        ),
    )
    return normalized_program, reference_path, candidate


def _collision_model(
    profile: MachineProfile,
    *,
    collide_inside_interval: bool,
) -> ConfigurationCollisionModel:
    profile_content_id = _content_hash(
        profile.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    column_box = (
        _box((-0.08, -0.25, -0.25), (0.08, 0.25, 0.25))
        if collide_inside_interval
        else _box((100.0, -0.25, -0.25), (100.4, 0.25, 0.25))
    )
    model = ConfigurationCollisionModel(
        modelId=(
            "five-axis.configuration-collision.interior-counterexample@1"
            if collide_inside_interval
            else "five-axis.configuration-collision.canonical-safe@1"
        ),
        machineProfileId=profile.profile_id,
        machineProfileContentId=profile_content_id,
        policyId="five-axis.configuration-collision.explicit-pairs@1",
        coverageStatus="complete",
        coveredPairKinds=("machine-self", "environment"),
        minimumClearance=CollisionTolerance(absolute=0.0, unit="mm"),
        solverTolerance=CollisionTolerance(absolute=1e-6, unit="mm"),
        entities=(
            CollisionEntity(
                entityId="machine.x-carriage",
                entityKind="machine-component",
                anchorType="axis",
                anchorAxisId="X",
                localAabb=_box((-0.05, -0.05, -0.05), (0.05, 0.05, 0.05)),
            ),
            CollisionEntity(
                entityId="machine.column",
                entityKind="machine-component",
                anchorType="base",
                localAabb=column_box,
            ),
            CollisionEntity(
                entityId="fixture.remote",
                entityKind="environment",
                anchorType="base",
                localAabb=_box((150.0, -0.5, -0.5), (151.0, 0.5, 0.5)),
            ),
        ),
        pairs=(
            CollisionPair(
                pairId="machine-self.x-carriage-column",
                pairKind="machine-self",
                leftEntityId="machine.x-carriage",
                rightEntityId="machine.column",
            ),
            CollisionPair(
                pairId="environment.x-carriage-fixture",
                pairKind="environment",
                leftEntityId="machine.x-carriage",
                rightEntityId="fixture.remote",
            ),
        ),
    )
    return model.model_copy(update={"content_id": hash_configuration_collision_model(model)})


def _manifest(
    scenario_id: str,
    description: str,
    axis_path: M3CandidateAxisPath,
    collision_model: ConfigurationCollisionModel,
    *,
    collision_free: bool,
) -> F2MathStageManifest:
    certificate = axis_path.kinematics_certificate
    assert collision_model.content_id is not None
    return F2MathStageManifest(
        manifestId="five-axis.f2-math-stage-manifest@1",
        schemaId="five-axis.f2-math-stage-manifest@1",
        schemaVersion=1,
        stage="F2",
        artifactDescriptors=(
            ArtifactDescriptor(
                stage="M0",
                artifactType="five-axis.normalized-program",
                schemaId="five-axis.normalized-program@1",
            ),
            ArtifactDescriptor(
                stage="M1",
                artifactType="five-axis.m1-reference-path",
                schemaId="five-axis.m1-reference-path@1",
            ),
            ArtifactDescriptor(
                stage="M2",
                artifactType="five-axis.m2-candidate-task-geometry",
                schemaId="five-axis.m2-candidate-task-geometry@1",
            ),
            ArtifactDescriptor(
                stage="M3",
                artifactType="five-axis.m3-candidate-axis-path",
                schemaId="five-axis.m3-candidate-axis-path@1",
            ),
        ),
        machineProfileSchemaId="five-axis.machine-profile@1",
        machineProfileId=axis_path.machine_profile.profile_id,
        machineProfileContentId=axis_path.machine_profile_content_id,
        capabilityIds=(
            CAP_PATH_PROGRESS,
            CAP_REGULARITY,
            CAP_MACHINE_PROFILE,
            CAP_CONFIGURATION_COLLISION,
        ),
        fixtureContentIds=(collision_model.content_id,),
        policyIds=tuple((*certificate.policy_ids, collision_model.policy_id)),
        numericEnvironment=current_f2_numeric_environment(),
        expectedMetrics=(
            ExpectedMetric(metricId=POSITION_RESIDUAL_MAX_METRIC_ID, expectedStatus="Computed", unit="mm"),
            ExpectedMetric(metricId=ORIENTATION_RESIDUAL_MAX_METRIC_ID, expectedStatus="Computed", unit="rad"),
            ExpectedMetric(
                metricId=AXIS_LIMIT_MARGIN_MIN_METRIC_ID,
                expectedStatus="Computed",
                unit="dimensionless",
            ),
            ExpectedMetric(
                metricId=SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID,
                expectedStatus="Computed",
                unit="dimensionless",
            ),
            ExpectedMetric(
                metricId=KINEMATICALLY_FEASIBLE_METRIC_ID,
                expectedStatus="Computed",
                expectedValue=True,
            ),
            ExpectedMetric(
                metricId=CONFIGURATION_COLLISION_FREE_METRIC_ID,
                expectedStatus="Computed",
                expectedValue=collision_free,
            ),
        ),
        expectedClaims=(
            ExpectedClaim(
                claimId=KINEMATICALLY_FEASIBLE_CLAIM_ID,
                claimClass="M3",
                expectedStatus="Supported",
                evidenceLevel="Exact",
            ),
            ExpectedClaim(
                claimId=CONFIGURATION_COLLISION_FREE_CLAIM_ID,
                claimClass="M3",
                expectedStatus="Supported" if collision_free else "Refuted",
                evidenceLevel="Certified" if collision_free else "Observed",
            ),
        ),
        expectedEvidence=(
            ExpectedEvidence(evidenceId="lineage", evidenceKind="lineage", required=True),
            ExpectedEvidence(evidenceId="regularity", evidenceKind="regularity", required=True),
            ExpectedEvidence(evidenceId="ik-branch", evidenceKind="ik-branch", required=True),
            ExpectedEvidence(evidenceId="wrap", evidenceKind="wrap", required=True),
            ExpectedEvidence(evidenceId="kinematics", evidenceKind="kinematics", required=True),
            ExpectedEvidence(evidenceId="singularity", evidenceKind="singularity", required=True),
            ExpectedEvidence(
                evidenceId="configuration-collision",
                evidenceKind="configuration-collision",
                required=True,
            ),
        ),
        tolerances=axis_path.source_candidate_geometry.tolerances,
        decisions=(
            StageDecision(
                decisionId=f"{scenario_id}.acceptance",
                status="accepted",
                rationale=description,
            ),
        ),
    )


def _run_spec(
    scenario_id: str,
    axis_path: M3CandidateAxisPath,
    collision_model: ConfigurationCollisionModel,
) -> dict[str, Any]:
    return {
        "subjectId": f"five-axis.f2.scenario.{scenario_id}@1",
        "domainPackId": FIVE_AXIS_F2_DOMAIN_PACK_ID,
        "runnerId": F2_RUNNER_ID,
        "evaluatorVersion": F2_EVALUATOR_ID,
        "request": {
            "artifact": axis_path.model_dump(mode="json", by_alias=True, exclude_none=True),
            "collisionModel": collision_model.model_dump(mode="json", by_alias=True, exclude_none=True),
            "case": {
                "caseId": f"five-axis.f2.case.{scenario_id}@1",
                "requiredMetrics": [
                    {"metricId": KINEMATICALLY_FEASIBLE_METRIC_ID},
                    {"metricId": CONFIGURATION_COLLISION_FREE_METRIC_ID},
                ],
                "optionalMetrics": [
                    {"metricId": POSITION_RESIDUAL_MAX_METRIC_ID},
                    {"metricId": ORIENTATION_RESIDUAL_MAX_METRIC_ID},
                    {"metricId": AXIS_LIMIT_MARGIN_MIN_METRIC_ID},
                    {"metricId": SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID},
                ],
            },
        },
    }


def _build_scenario(
    *,
    scenario_id: str,
    title: str,
    description: str,
    profile_builder: _ProfileBuilder,
    collide_inside_interval: bool = False,
) -> FiveAxisF2Scenario:
    normalized_program, reference_path, candidate_geometry = _candidate_geometry(scenario_id)
    machine_profile = profile_builder()
    lift = lift_m2_path_to_m3_axis_path(candidate_geometry, machine_profile)
    if lift.status != "Supported" or lift.axis_path is None:
        raise RuntimeError(f"built-in F2 scenario '{scenario_id}' failed path lifting: {lift.reason_code}")
    collision_model = _collision_model(
        machine_profile,
        collide_inside_interval=collide_inside_interval,
    )
    collision_free = not collide_inside_interval
    manifest = _manifest(
        scenario_id,
        description,
        lift.axis_path,
        collision_model,
        collision_free=collision_free,
    )
    return FiveAxisF2Scenario(
        summary=F2ScenarioSummary(
            scenarioId=scenario_id,
            title=title,
            description=description,
            topology=machine_profile.topology,
            expectedClaimStatusById={
                claim.claim_id: claim.expected_status for claim in manifest.expected_claims
            },
        ),
        sourceText=_SOURCE_TEXT,
        normalizedProgram=normalized_program,
        referencePath=reference_path,
        candidateGeometry=candidate_geometry,
        axisPath=lift.axis_path,
        collisionModel=collision_model,
        manifest=manifest,
        runSpec=_run_spec(scenario_id, lift.axis_path, collision_model),
    )


def _scenario_registry() -> dict[str, FiveAxisF2Scenario]:
    return {
        "canonical-table-table": _build_scenario(
            scenario_id="canonical-table-table",
            title="双转台 AC：连续提升",
            description="正交相交 A/C 转台的闭式 IK、固定分支提升和完整 Q_free 区间证书。",
            profile_builder=build_canonical_table_table_ac_profile,
        ),
        "canonical-head-table": _build_scenario(
            scenario_id="canonical-head-table",
            title="摆头转台 BC：连续提升",
            description="工件侧 C 转台与刀具侧 B 摆头的闭式 IK、wrap 和连续限位证明。",
            profile_builder=build_canonical_head_table_bc_profile,
        ),
        "canonical-head-head": _build_scenario(
            scenario_id="canonical-head-head",
            title="双摆头 CB：连续提升",
            description="刀具侧 C/B 双摆头的闭式 IK、分支图、奇异裕量和路径回代证书。",
            profile_builder=build_canonical_head_head_cb_profile,
        ),
        "configuration-interior-collision": _build_scenario(
            scenario_id="configuration-interior-collision",
            title="区间内部机构碰撞",
            description="两个端点均分离，但 X 滑台在区间内部与立柱相交，用反例证书拒绝 Q_free。",
            profile_builder=build_canonical_table_table_ac_profile,
            collide_inside_interval=True,
        ),
    }


def list_f2_scenarios() -> tuple[F2ScenarioSummary, ...]:
    registry = _scenario_registry()
    return tuple(registry[scenario_id].summary for scenario_id in sorted(registry))


def load_f2_scenario(id: str) -> FiveAxisF2Scenario:
    registry = _scenario_registry()
    try:
        return registry[id]
    except KeyError as exc:
        available = ", ".join(sorted(registry))
        raise KeyError(f"unknown F2 scenario '{id}'; expected one of: {available}") from exc


def build_f2_manifest(id: str = _DEFAULT_SCENARIO_ID) -> F2MathStageManifest:
    return load_f2_scenario(id).manifest


def f2_example_run_spec(id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    return load_f2_scenario(id).runSpec


def f2_example_payload(id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    scenario = load_f2_scenario(id)
    payload = {
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
        "artifacts": {
            "candidateGeometry": scenario.candidateGeometry.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "axisPath": scenario.axisPath.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "machineProfile": scenario.axisPath.machine_profile.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "collisionModel": scenario.collisionModel.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
        },
        "runSpec": scenario.runSpec,
    }
    return payload


def validate_f2_example_run_spec(id: str = _DEFAULT_SCENARIO_ID) -> RunSpec:
    return RunSpec.model_validate(f2_example_run_spec(id))


__all__ = [
    "F2ExampleArtifacts",
    "F2ExamplePayload",
    "F2ExampleSource",
    "F2ScenarioSummary",
    "FiveAxisF2Scenario",
    "build_f2_manifest",
    "f2_example_payload",
    "f2_example_run_spec",
    "list_f2_scenarios",
    "load_f2_scenario",
    "validate_f2_example_run_spec",
]
