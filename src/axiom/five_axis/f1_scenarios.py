from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from ..evaluator import _content_hash
from ..models import AxiomModel, RunSpec
from .f1_collision import hash_state_geometry
from .f1_geometry import build_provenance_progress_correspondence
from .f1_models import (
    AllowedRemoval,
    ArtifactDescriptor,
    AxisAlignedBoundingBox,
    CollisionContext,
    ContactPolicy,
    ContactRule,
    ExpectedClaim,
    ExpectedEvidence,
    ExpectedMetric,
    F1MathStageManifest,
    FailureStateSemantics,
    M1ReferencePath,
    M2CandidateTaskGeometry,
    NumericTolerance,
    NormalizedProgram,
    ProcessStateInterval,
    ProcessStateTimeline,
    ProvenanceProgressPolicy,
    StageDecision,
    StockFixtureAABB,
    StockStateRef,
    StockUpdatePolicy,
    ToleranceBinding,
    ToolComponent,
)
from .f1_parser import parse_axiom_cl_subset
from .f1_pipeline import build_m1_reference_path
from .f1_runtime import (
    CAP_COLLISION_CONTEXT,
    CAP_CONTINUOUS_ERROR,
    CAP_CORRESPONDENCE,
    CAP_FRONTEND,
    CAP_PATH_PROGRESS,
    CAP_PROCESS_STATE,
    CAP_REGULARITY,
    CAP_TASK_COLLISION,
    F1_EVALUATOR_ID,
    F1_RUNNER_ID,
    FIVE_AXIS_F1_DOMAIN_PACK_ID,
    GEOMETRY_VALID_METRIC_ID,
    MINIMUM_CLEARANCE_METRIC_ID,
    ORIENTATION_MAX_ERROR_METRIC_ID,
    POSITION_MAX_ERROR_METRIC_ID,
    TASK_COLLISION_FREE_METRIC_ID,
    TASK_OVERCUT_FREE_METRIC_ID,
    current_f1_numeric_environment,
)


_DEFAULT_SCENARIO_ID = "nominal-certified"
_SOURCE_TEXT = (
    "UNITS/MM\n"
    "FROM/-0.8,0,0,0,0,1\n"
    "FEDRAT/1200\n"
    "GOTO/0.8,0,0\n"
    "END\n"
)


@dataclass(frozen=True, slots=True)
class F1ScenarioSummary:
    scenarioId: str
    title: str
    description: str
    expectedClaimStatusById: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenarioId,
            "title": self.title,
            "description": self.description,
            "expectedClaimStatusById": dict(self.expectedClaimStatusById),
        }


@dataclass(frozen=True, slots=True)
class FiveAxisF1Scenario:
    summary: F1ScenarioSummary
    sourceText: str
    normalizedProgram: NormalizedProgram
    referencePath: M1ReferencePath
    candidateGeometry: M2CandidateTaskGeometry
    stockStateGeometries: dict[str, dict[str, Any]]
    manifest: F1MathStageManifest
    runSpec: dict[str, Any]


class F1ExampleSource(AxiomModel):
    source_text: str = Field(alias="sourceText")
    normalized_program: NormalizedProgram = Field(alias="normalizedProgram")
    reference_path: M1ReferencePath = Field(alias="referencePath")


class F1ExampleArtifacts(AxiomModel):
    candidate_geometry: M2CandidateTaskGeometry = Field(alias="candidateGeometry")
    stock_state_geometries: dict[str, dict[str, tuple[AxisAlignedBoundingBox, ...]]] = Field(
        alias="stockStateGeometries"
    )


class F1ExamplePayload(AxiomModel):
    manifest: F1MathStageManifest
    scenario: F1ScenarioSummary
    source: F1ExampleSource
    artifacts: F1ExampleArtifacts
    run_spec: RunSpec = Field(alias="runSpec")


def _box(min_corner: tuple[float, float, float], max_corner: tuple[float, float, float]) -> AxisAlignedBoundingBox:
    return AxisAlignedBoundingBox(min_corner=min_corner, max_corner=max_corner)


def _shift_box(
    box: AxisAlignedBoundingBox,
    delta: tuple[float, float, float],
) -> AxisAlignedBoundingBox:
    return AxisAlignedBoundingBox(
        min_corner=tuple(value + offset for value, offset in zip(box.min_corner, delta)),
        max_corner=tuple(value + offset for value, offset in zip(box.max_corner, delta)),
    )


def _fixture_hash(stock_fixtures: tuple[StockFixtureAABB, ...]) -> tuple[str, ...]:
    fixture_hashes = [
        hash_state_geometry({item.stock_fixture_id: (item.aabb,)})
        for item in stock_fixtures
        if item.category == "fixture"
    ]
    return tuple(sorted(fixture_hashes))


def _snapshot_payload(
    geometry: dict[str, tuple[AxisAlignedBoundingBox, ...]],
) -> tuple[dict[str, Any], str]:
    content_id = hash_state_geometry(geometry)
    return (
        {
            stock_fixture_id: [
                box.model_dump(mode="json", by_alias=True)
                for box in boxes
            ]
            for stock_fixture_id, boxes in geometry.items()
        },
        content_id,
    )


def _explicit_snapshots(
    scenario_id: str,
    stock_geometry: dict[str, tuple[AxisAlignedBoundingBox, ...]],
) -> tuple[dict[str, dict[str, Any]], str, str, str]:
    input_state_id = f"{scenario_id}.stock.in"
    output_state_id = f"{scenario_id}.stock.out"
    snapshot, content_id = _snapshot_payload(stock_geometry)
    return {input_state_id: snapshot, output_state_id: snapshot}, input_state_id, output_state_id, content_id


def _tool_components() -> tuple[ToolComponent, ...]:
    return (
        ToolComponent(
            componentId="tool.cutter",
            componentKind="cutter",
            shapeType="sphere",
            radius=0.1,
            axisStartOffset=0.0,
            axisEndOffset=0.0,
        ),
        ToolComponent(
            componentId="tool.shaft",
            componentKind="shaft",
            shapeType="capsule",
            radius=0.05,
            axisStartOffset=0.28,
            axisEndOffset=0.42,
        ),
        ToolComponent(
            componentId="tool.holder",
            componentKind="holder",
            shapeType="capsule",
            radius=0.12,
            axisStartOffset=0.45,
            axisEndOffset=0.65,
        ),
    )


def _collision_context(
    *,
    stock_box: AxisAlignedBoundingBox,
    fixture_box: AxisAlignedBoundingBox,
) -> CollisionContext:
    return CollisionContext(
        contextId="five-axis.f1.scenario.collision-context",
        toolComponents=_tool_components(),
        stockFixtures=(
            StockFixtureAABB(stockFixtureId="stock.body", category="stock", aabb=stock_box),
            StockFixtureAABB(stockFixtureId="fixture.body", category="fixture", aabb=fixture_box),
        ),
        allowedRemoval=(
            AllowedRemoval(
                removalId="allowed-removal.cutter.stock",
                toolComponentId="tool.cutter",
                stockFixtureId="stock.body",
                region=stock_box,
            ),
        ),
        minimumClearance=NumericTolerance(absolute=0.0, unit="MM"),
        solverTolerance=NumericTolerance(absolute=1e-6, unit="MM"),
        envelopeTolerance=NumericTolerance(absolute=1e-6, unit="MM"),
        contactPolicy=ContactPolicy(
            policyId="five-axis.contact-policy.explicit@1",
            rules=(
                ContactRule(ruleId="cutter-stock", leftCategory="cutter", rightCategory="stock", contactPolicy="allowed"),
                ContactRule(ruleId="cutter-fixture", leftCategory="cutter", rightCategory="fixture", contactPolicy="forbidden"),
                ContactRule(ruleId="shaft-stock", leftCategory="shaft", rightCategory="stock", contactPolicy="forbidden"),
                ContactRule(ruleId="shaft-fixture", leftCategory="shaft", rightCategory="fixture", contactPolicy="forbidden"),
                ContactRule(ruleId="holder-stock", leftCategory="holder", rightCategory="stock", contactPolicy="forbidden"),
                ContactRule(ruleId="holder-fixture", leftCategory="holder", rightCategory="fixture", contactPolicy="forbidden"),
            ),
        ),
    )


def _process_state_timeline(
    *,
    scenario_id: str,
    input_state_id: str,
    input_content_id: str,
    output_state_id: str,
    output_content_id: str,
) -> ProcessStateTimeline:
    return ProcessStateTimeline(
        timelineId=f"{scenario_id}.process-state",
        stockUpdatePolicy=StockUpdatePolicy(policyId="five-axis.stock-update.explicit-snapshot@1"),
        failureStateSemantics=FailureStateSemantics(
            policyId="five-axis.process-state.failure-terminal@1",
            failedStateMeaning="last-input-state-persists",
        ),
        intervals=(
            ProcessStateInterval(
                intervalId=f"{scenario_id}.interval.0001",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                motionMode="cut",
                spindleState="cw",
                toolComponentId="tool.cutter",
                coolantOn=False,
                inputStockState=StockStateRef(stateId=input_state_id, contentId=input_content_id),
                outputStockState=StockStateRef(stateId=output_state_id, contentId=output_content_id),
            ),
        ),
    )


def _actual_path(
    reference_path: M1ReferencePath,
    *,
    geometry_id: str,
    position_delta: tuple[float, float, float],
) -> M1ReferencePath:
    position_segments = tuple(
        segment.model_copy(
            update={
                "start_point": tuple(value + delta for value, delta in zip(segment.start_point, position_delta)),
                "end_point": tuple(value + delta for value, delta in zip(segment.end_point, position_delta)),
            }
        )
        for segment in reference_path.position_segments
    )
    regularity_certificate = reference_path.regularity_certificate
    if regularity_certificate is not None and regularity_certificate.node_evidence:
        regularity_certificate = regularity_certificate.model_copy(
            update={"node_evidence": tuple()}
        )
    return M1ReferencePath(
        artifactType="five-axis.m1-reference-path",
        schemaVersion=1,
        referencePathId=geometry_id,
        coordinateContext=reference_path.coordinate_context,
        pathProgress=reference_path.path_progress,
        positionSemantics=reference_path.position_semantics,
        staticPosition=reference_path.static_position,
        positionSegments=position_segments,
        orientationSegments=reference_path.orientation_segments,
        nodeEvents=tuple(),
        regularityCertificate=regularity_certificate,
        provenance=reference_path.provenance,
    )


def _tolerances(position_absolute: float) -> tuple[ToleranceBinding, ...]:
    return (
        ToleranceBinding(
            toleranceId="tol.position",
            target="position",
            tolerance=NumericTolerance(absolute=position_absolute, relative=0.0, unit="MM"),
        ),
        ToleranceBinding(
            toleranceId="tol.orientation",
            target="orientation",
            tolerance=NumericTolerance(absolute=1e-9, relative=0.0, unit="rad"),
        ),
        ToleranceBinding(
            toleranceId="tol.clearance",
            target="collision-clearance",
            tolerance=NumericTolerance(absolute=0.0, relative=0.0, unit="MM"),
        ),
    )


def _candidate_geometry(
    *,
    scenario_id: str,
    reference_path: M1ReferencePath,
    position_delta: tuple[float, float, float],
    collision_context: CollisionContext,
    process_state_timeline: ProcessStateTimeline,
    position_tolerance_absolute: float,
) -> M2CandidateTaskGeometry:
    candidate_geometry_id = f"five-axis.f1.scenario.{scenario_id}.candidate"
    actual_path = _actual_path(
        reference_path,
        geometry_id=candidate_geometry_id,
        position_delta=position_delta,
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
            numericTolerance=NumericTolerance(absolute=0.0, relative=0.0, unit="dimensionless"),
        ),
        certificate_id=f"five-axis.f1.scenario.{scenario_id}.correspondence",
    )
    return M2CandidateTaskGeometry(
        artifactType="five-axis.m2-candidate-task-geometry",
        schemaVersion=1,
        candidateGeometryId=candidate_geometry_id,
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
        tolerances=_tolerances(position_tolerance_absolute),
        correspondence=correspondence,
        collisionContext=collision_context,
        processStateTimeline=process_state_timeline,
    )


def _expected_claims(scenario_id: str) -> tuple[ExpectedClaim, ...]:
    if scenario_id == "nominal-certified":
        geometry_status = ("Supported", "Exact")
        collision_status = ("Supported", "Certified")
    elif scenario_id == "geometry-tolerance-violation":
        geometry_status = ("Refuted", "Observed")
        collision_status = ("Supported", "Certified")
    else:
        geometry_status = ("Supported", "Exact")
        collision_status = ("Refuted", "Observed")
    return (
        ExpectedClaim(
            claimId="five-axis.geometry-valid-claim@1",
            claimClass="M2",
            expectedStatus=geometry_status[0],
            evidenceLevel=geometry_status[1],
        ),
        ExpectedClaim(
            claimId="five-axis.task-geometry-collision-free-claim@1",
            claimClass="M2",
            expectedStatus=collision_status[0],
            evidenceLevel=collision_status[1],
        ),
    )


def _expected_metrics(scenario_id: str) -> tuple[ExpectedMetric, ...]:
    if scenario_id == "geometry-tolerance-violation":
        geometry_value = False
        collision_value = True
    elif scenario_id == "fixture-collision":
        geometry_value = True
        collision_value = False
    else:
        geometry_value = True
        collision_value = True
    return (
        ExpectedMetric(metricId=GEOMETRY_VALID_METRIC_ID, expectedStatus="Computed", expectedValue=geometry_value),
        ExpectedMetric(metricId=TASK_COLLISION_FREE_METRIC_ID, expectedStatus="Computed", expectedValue=collision_value),
    )


def _manifest(
    *,
    scenario_id: str,
    description: str,
    candidate_geometry: M2CandidateTaskGeometry,
) -> F1MathStageManifest:
    return F1MathStageManifest(
        manifestId="five-axis.f1-math-stage-manifest@1",
        schemaId="five-axis.f1-math-stage-manifest@1",
        schemaVersion=1,
        stage="F1",
        artifactDescriptors=(
            ArtifactDescriptor(stage="M0", artifactType="five-axis.normalized-program", schemaId="five-axis.normalized-program@1"),
            ArtifactDescriptor(stage="M1", artifactType="five-axis.m1-reference-path", schemaId="five-axis.m1-reference-path@1"),
            ArtifactDescriptor(stage="M2", artifactType="five-axis.m2-candidate-task-geometry", schemaId="five-axis.m2-candidate-task-geometry@1"),
        ),
        capabilityIds=(
            CAP_FRONTEND,
            CAP_PATH_PROGRESS,
            CAP_REGULARITY,
            CAP_CORRESPONDENCE,
            CAP_CONTINUOUS_ERROR,
            CAP_COLLISION_CONTEXT,
            CAP_PROCESS_STATE,
            CAP_TASK_COLLISION,
        ),
        fixtureContentIds=_fixture_hash(candidate_geometry.collision_context.stock_fixtures),
        policyIds=(
            candidate_geometry.correspondence.policy.strategy_id,
            candidate_geometry.collision_context.contact_policy.policy_id,
            candidate_geometry.process_state_timeline.stock_update_policy.policy_id,
            candidate_geometry.process_state_timeline.failure_state_semantics.policy_id,
        ),
        numericEnvironment=current_f1_numeric_environment(),
        expectedMetrics=_expected_metrics(scenario_id),
        expectedClaims=_expected_claims(scenario_id),
        expectedEvidence=(
            ExpectedEvidence(evidenceId="lineage", evidenceKind="lineage", required=True),
            ExpectedEvidence(evidenceId="regularity", evidenceKind="regularity", required=True),
            ExpectedEvidence(evidenceId="correspondence", evidenceKind="correspondence", required=True),
            ExpectedEvidence(evidenceId="collision", evidenceKind="collision", required=True),
            ExpectedEvidence(evidenceId="process-state", evidenceKind="process-state", required=True),
        ),
        tolerances=candidate_geometry.tolerances,
        decisions=(
            StageDecision(
                decisionId=f"{scenario_id}.acceptance",
                status="accepted",
                rationale=description,
            ),
        ),
    )


def _run_spec(
    *,
    scenario_id: str,
    candidate_geometry: M2CandidateTaskGeometry,
    reference_path: M1ReferencePath,
    stock_state_geometries: dict[str, dict[str, Any]],
    manifest: F1MathStageManifest,
) -> dict[str, Any]:
    return {
        "subjectId": f"five-axis.f1.scenario.{scenario_id}@1",
        "domainPackId": FIVE_AXIS_F1_DOMAIN_PACK_ID,
        "runnerId": F1_RUNNER_ID,
        "evaluatorVersion": F1_EVALUATOR_ID,
        "request": {
            "artifact": candidate_geometry.model_dump(mode="json", by_alias=True, exclude_none=True),
            "referencePath": reference_path.model_dump(mode="json", by_alias=True, exclude_none=True),
            "stockStateGeometries": stock_state_geometries,
            "manifest": manifest.model_dump(mode="json", by_alias=True, exclude_none=True),
            "case": {
                "caseId": f"five-axis.f1.case.{scenario_id}@1",
                "requiredMetrics": [
                    {"metricId": GEOMETRY_VALID_METRIC_ID},
                    {"metricId": TASK_COLLISION_FREE_METRIC_ID},
                ],
                "optionalMetrics": [
                    {"metricId": POSITION_MAX_ERROR_METRIC_ID},
                    {"metricId": ORIENTATION_MAX_ERROR_METRIC_ID},
                    {"metricId": TASK_OVERCUT_FREE_METRIC_ID},
                    {"metricId": MINIMUM_CLEARANCE_METRIC_ID},
                ],
            },
        },
    }


def _build_scenario(
    *,
    scenario_id: str,
    title: str,
    description: str,
    position_delta: tuple[float, float, float],
    position_tolerance_absolute: float,
    stock_box: AxisAlignedBoundingBox,
    fixture_box: AxisAlignedBoundingBox,
) -> FiveAxisF1Scenario:
    normalized_program = parse_axiom_cl_subset(_SOURCE_TEXT)
    reference_path = build_m1_reference_path(normalized_program)
    stock_state_geometries, input_state_id, output_state_id, content_id = _explicit_snapshots(
        scenario_id,
        {"stock.body": (stock_box,)},
    )
    collision_context = _collision_context(stock_box=stock_box, fixture_box=fixture_box)
    process_state_timeline = _process_state_timeline(
        scenario_id=scenario_id,
        input_state_id=input_state_id,
        input_content_id=content_id,
        output_state_id=output_state_id,
        output_content_id=content_id,
    )
    candidate_geometry = _candidate_geometry(
        scenario_id=scenario_id,
        reference_path=reference_path,
        position_delta=position_delta,
        collision_context=collision_context,
        process_state_timeline=process_state_timeline,
        position_tolerance_absolute=position_tolerance_absolute,
    )
    manifest = _manifest(
        scenario_id=scenario_id,
        description=description,
        candidate_geometry=candidate_geometry,
    )
    run_spec = _run_spec(
        scenario_id=scenario_id,
        candidate_geometry=candidate_geometry,
        reference_path=reference_path,
        stock_state_geometries=stock_state_geometries,
        manifest=manifest,
    )
    return FiveAxisF1Scenario(
        summary=F1ScenarioSummary(
            scenarioId=scenario_id,
            title=title,
            description=description,
            expectedClaimStatusById={
                claim.claim_id: claim.expected_status
                for claim in manifest.expected_claims
            },
        ),
        sourceText=_SOURCE_TEXT,
        normalizedProgram=normalized_program,
        referencePath=reference_path,
        candidateGeometry=candidate_geometry,
        stockStateGeometries=stock_state_geometries,
        manifest=manifest,
        runSpec=run_spec,
    )


def _scenario_registry() -> dict[str, FiveAxisF1Scenario]:
    nominal_stock = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    far_stock = _box((2.0, 2.0, 2.0), (3.0, 3.0, 3.0))
    return {
        "nominal-certified": _build_scenario(
            scenario_id="nominal-certified",
            title="Nominal Certified",
            description="Identity candidate with allowed cutter-stock removal and no forbidden contact.",
            position_delta=(0.0, 0.0, 0.0),
            position_tolerance_absolute=1e-6,
            stock_box=nominal_stock,
            fixture_box=_box((3.0, 3.0, 0.45), (3.3, 3.3, 0.75)),
        ),
        "geometry-tolerance-violation": _build_scenario(
            scenario_id="geometry-tolerance-violation",
            title="Geometry Tolerance Violation",
            description="Candidate stays collision-free but shifts outside the bound position tolerance.",
            position_delta=(0.0, 0.01, 0.0),
            position_tolerance_absolute=0.001,
            stock_box=far_stock,
            fixture_box=_box((4.0, 4.0, 0.45), (4.3, 4.3, 0.75)),
        ),
        "fixture-collision": _build_scenario(
            scenario_id="fixture-collision",
            title="Fixture Collision",
            description="Identity candidate remains geometrically valid while the holder collides with fixture stock context.",
            position_delta=(0.0, 0.0, 0.0),
            position_tolerance_absolute=1e-6,
            stock_box=far_stock,
            fixture_box=_box((-0.08, -0.08, 0.45), (0.08, 0.08, 0.65)),
        ),
    }


def list_f1_scenarios() -> tuple[F1ScenarioSummary, ...]:
    return tuple(_scenario_registry()[scenario_id].summary for scenario_id in sorted(_scenario_registry()))


def load_f1_scenario(id: str) -> FiveAxisF1Scenario:
    registry = _scenario_registry()
    try:
        return registry[id]
    except KeyError as exc:
        available = ", ".join(sorted(registry))
        raise KeyError(f"unknown F1 scenario '{id}'; expected one of: {available}") from exc


def build_f1_manifest(id: str = _DEFAULT_SCENARIO_ID) -> F1MathStageManifest:
    return load_f1_scenario(id).manifest


def f1_example_run_spec(id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    return load_f1_scenario(id).runSpec


def f1_example_payload(id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    scenario = load_f1_scenario(id)
    return {
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
        },
        "runSpec": scenario.runSpec,
    }


__all__ = [
    "F1ExamplePayload",
    "FiveAxisF1Scenario",
    "F1ScenarioSummary",
    "build_f1_manifest",
    "f1_example_payload",
    "f1_example_run_spec",
    "list_f1_scenarios",
    "load_f1_scenario",
]
