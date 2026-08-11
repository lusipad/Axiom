from __future__ import annotations

from dataclasses import dataclass
import math
import os
import platform
from importlib.metadata import version as package_version
from typing import Annotated, Any, Literal

from pydantic import Field

from ..domain import (
    ARTIFACT_IMPORT_RUNNER_ID,
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    ArtifactTypeDescriptor,
    DomainPack,
    FailureMapping,
    MetricDefinition,
    NumericTolerance as DomainNumericTolerance,
    register_domain_pack,
)
from ..evaluator import _aggregate_outcome, _apply_threshold, _content_hash, _seal_evaluation_report
from ..models import (
    AxiomModel,
    CapabilityResolution,
    CaseOutcome,
    CoreEvaluationRequest,
    DomainFailure,
    Evidence,
    EvaluationCase,
    EvaluationReport,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Provenance,
)
from ..runtime import DomainRuntimeBinding, register_domain_runtime_binding
from .f1_models import (
    ConstantOrientationSegment,
    LinePositionSegment,
    M1ReferencePath,
    M2CandidateTaskGeometry,
    NormalizedProgram,
)
from .f2_collision import (
    ConfigurationCollisionEvaluation,
    ConfigurationCollisionModel,
    evaluate_configuration_path_collision,
)
from .f2_kinematics import forward_kinematics, jacobian_evidence, normalize_numeric_identity
from .f2_models import M3CandidateAxisPath


FIVE_AXIS_F2_DOMAIN_PACK_ID = "five-axis.domain-pack@3"
F2_EVALUATOR_ID = "five-axis-f2-evaluator@1"
F2_RUNNER_ID = ARTIFACT_IMPORT_RUNNER_ID

POSITION_RESIDUAL_MAX_METRIC_ID = "five-axis.position-residual.max@1"
ORIENTATION_RESIDUAL_MAX_METRIC_ID = "five-axis.orientation-residual.max@1"
AXIS_LIMIT_MARGIN_MIN_METRIC_ID = "five-axis.axis-limit-margin.min@1"
SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID = "five-axis.singularity.minimum-singular-value@1"
KINEMATICALLY_FEASIBLE_METRIC_ID = "five-axis.kinematically-feasible@1"
CONFIGURATION_COLLISION_FREE_METRIC_ID = "five-axis.configuration-collision-free@1"

KINEMATICALLY_FEASIBLE_CLAIM_ID = "five-axis.kinematically-feasible-claim@1"
CONFIGURATION_COLLISION_FREE_CLAIM_ID = "five-axis.configuration-collision-free-claim@1"

CAP_PATH_PROGRESS = "five-axis.path-progress.bound@1"
CAP_REGULARITY = "five-axis.regularity.certified@1"
CAP_MACHINE_PROFILE = "five-axis.machine-profile.bound@1"
CAP_CONFIGURATION_COLLISION = "five-axis.configuration.collision.checked@1"

_SELECTED_LIFT_SCOPE = "selected-continuous-lift"
_EXACT_EVIDENCE_LEVELS = frozenset({"Exact", "Certified"})
_REQUIRED_CONTINUOUS_METHOD = "five-axis.linear-fixed-branch-lift@1"
_REQUIRED_POLICY_IDS = frozenset(
    {
        "five-axis.closed-form-ik-policy@1",
        "five-axis.branch-wrap-continuity.strict@1",
        "five-axis.selected-branch.lexicographic@1",
    }
)
_EPSILON = 1e-12
_JOINT_CONTINUITY_TOLERANCE = 1e-9
_REPLAY_METHOD = "five-axis.f2.endpoint-midpoint-fk-replay@1"
_CLAIM_METHOD = "five-axis.f2.linear-fixed-branch-lift-closure@1"

F2Artifact = Annotated[
    NormalizedProgram | M1ReferencePath | M2CandidateTaskGeometry | M3CandidateAxisPath,
    Field(discriminator="artifact_type"),
]


class FiveAxisF2EvaluationBindingRequest(AxiomModel):
    artifact: F2Artifact
    case: EvaluationCase
    collision_model: ConfigurationCollisionModel | None = Field(default=None, alias="collisionModel")


@dataclass(frozen=True)
class _ReplaySample:
    sigma: float
    position_residual: float
    orientation_residual: float
    normalized_axis_margin: float
    minimum_singular_value: float
    singular: bool


@dataclass(frozen=True)
class _LiftReplayResult:
    samples: tuple[_ReplaySample, ...]
    position_residual_max: float
    orientation_residual_max: float
    normalized_axis_margin_min: float
    minimum_singular_value_min: float


_FAILURE_MAPPINGS = (
    FailureMapping(
        code="MalformedEvaluationRequest",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="ArtifactTypeMismatch",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="ArtifactSchemaVersionMismatch",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="DomainEvaluatorFailed",
        executionStatus=ExecutionStatus.EXECUTION_FAILED,
        metricStatus=MetricStatus.NUMERICAL_FAILURE,
        caseOutcome=CaseOutcome.INCONCLUSIVE,
    ),
)


FIVE_AXIS_F2_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=FIVE_AXIS_F2_DOMAIN_PACK_ID,
        artifactType="five-axis.m3-candidate-axis-path",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="five-axis.normalized-program",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m1-reference-path",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m2-candidate-task-geometry",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m3-candidate-axis-path",
                schemaVersion=1,
                role="run-input",
            ),
        ),
        evaluatorVersion=F2_EVALUATOR_ID,
        runnerId=F2_RUNNER_ID,
        runnerIds=(F2_RUNNER_ID,),
        capabilityIds=(
            CAP_PATH_PROGRESS,
            CAP_REGULARITY,
            CAP_MACHINE_PROFILE,
            CAP_CONFIGURATION_COLLISION,
        ),
        metricDefinitions=(
            MetricDefinition(
                metricId=POSITION_RESIDUAL_MAX_METRIC_ID,
                metricDefinitionId=POSITION_RESIDUAL_MAX_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MACHINE_PROFILE),
                direction="lower-is-better",
                numericTolerance=DomainNumericTolerance(absolute=1e-9, relative=1e-12, unit="mm"),
            ),
            MetricDefinition(
                metricId=ORIENTATION_RESIDUAL_MAX_METRIC_ID,
                metricDefinitionId=ORIENTATION_RESIDUAL_MAX_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MACHINE_PROFILE),
                direction="lower-is-better",
                numericTolerance=DomainNumericTolerance(absolute=1e-12, relative=1e-12, unit="rad"),
            ),
            MetricDefinition(
                metricId=AXIS_LIMIT_MARGIN_MIN_METRIC_ID,
                metricDefinitionId=AXIS_LIMIT_MARGIN_MIN_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MACHINE_PROFILE),
                direction="higher-is-better",
            ),
            MetricDefinition(
                metricId=SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID,
                metricDefinitionId=SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MACHINE_PROFILE),
                direction="higher-is-better",
            ),
            MetricDefinition(
                metricId=KINEMATICALLY_FEASIBLE_METRIC_ID,
                metricDefinitionId=KINEMATICALLY_FEASIBLE_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MACHINE_PROFILE),
                claimDefinitionId=KINEMATICALLY_FEASIBLE_CLAIM_ID,
                claimPredicate="five-axis.KinematicallyFeasible is true",
            ),
            MetricDefinition(
                metricId=CONFIGURATION_COLLISION_FREE_METRIC_ID,
                metricDefinitionId=CONFIGURATION_COLLISION_FREE_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MACHINE_PROFILE, CAP_CONFIGURATION_COLLISION),
                claimDefinitionId=CONFIGURATION_COLLISION_FREE_CLAIM_ID,
                claimPredicate="five-axis.ConfigurationCollisionFree is true",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            KINEMATICALLY_FEASIBLE_CLAIM_ID,
            CONFIGURATION_COLLISION_FREE_CLAIM_ID,
        ),
        comparisonPolicyIds=(),
        failureMappings=_FAILURE_MAPPINGS,
    )
)


def current_f2_numeric_environment() -> dict[str, str]:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "numpy": package_version("numpy"),
        "scipy": package_version("scipy"),
        "pint": package_version("pint"),
        "pydantic": package_version("pydantic"),
        "openblasCoreType": os.environ.get("OPENBLAS_CORETYPE", "auto"),
        "openblasNumThreads": os.environ.get("OPENBLAS_NUM_THREADS", "auto"),
        "ompNumThreads": os.environ.get("OMP_NUM_THREADS", "auto"),
    }


def _parse_f2_request(request: CoreEvaluationRequest) -> FiveAxisF2EvaluationBindingRequest:
    return FiveAxisF2EvaluationBindingRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _definition(metric_id: str) -> MetricDefinition | None:
    try:
        return FIVE_AXIS_F2_DOMAIN_PACK.metric_definition(metric_id)
    except KeyError:
        return None


def _unavailable(metric_id: str, status: MetricStatus, reason_code: str, **details: Any) -> MetricResult:
    definition = _definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id if definition else metric_id,
        requires=list(definition.requires) if definition else [],
        status=status,
        reasonCode=reason_code,
        details=details,
    )


def _computed(
    metric_id: str,
    value: Any,
    *,
    level: Literal["Exact", "Certified", "Validated", "Observed"],
    method: str,
    unit: str | None = None,
    reason_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    definition = _definition(metric_id)
    assert definition is not None
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=list(definition.requires),
        status=MetricStatus.COMPUTED,
        value=value,
        unit=unit,
        reasonCode=reason_code,
        details=details or {},
        evidence=Evidence(level=level, method=method),
    )


def _selected_branch_node(artifact: M3CandidateAxisPath):
    branch_id = artifact.kinematics_certificate.selected_branch_id
    return next((branch for branch in artifact.branch_graph.branches if branch.branch_id == branch_id), None)


def _selected_branch_segments(artifact: M3CandidateAxisPath) -> tuple[Any, ...]:
    branch_id = artifact.kinematics_certificate.selected_branch_id
    return tuple(segment for segment in artifact.joint_segments if segment.branch_id == branch_id)


def _selected_branch_solutions(artifact: M3CandidateAxisPath) -> tuple[Any, ...]:
    branch_id = artifact.kinematics_certificate.selected_branch_id
    solution_ids = {
        segment.start_solution_id for segment in artifact.joint_segments if segment.branch_id == branch_id
    } | {
        segment.end_solution_id for segment in artifact.joint_segments if segment.branch_id == branch_id
    }
    return tuple(
        solution
        for solution in artifact.ik_solutions
        if solution.branch_id == branch_id and solution.solution_id in solution_ids
    )


def _model_content_hash(model: AxiomModel) -> str:
    return _content_hash(normalize_numeric_identity(model.model_dump(mode="json", by_alias=True, exclude_none=True)))


def _position_tolerance_absolute(artifact: M3CandidateAxisPath) -> float:
    for tolerance in artifact.source_candidate_geometry.tolerances:
        if tolerance.target == "position":
            return tolerance.tolerance.absolute
    return artifact.kinematics_certificate.position_tolerance.tolerance.absolute


def _orientation_tolerance_absolute(artifact: M3CandidateAxisPath) -> float:
    for tolerance in artifact.source_candidate_geometry.tolerances:
        if tolerance.target == "orientation":
            return tolerance.tolerance.absolute
    return artifact.kinematics_certificate.orientation_tolerance.tolerance.absolute


def _selected_branch_segments_sorted(artifact: M3CandidateAxisPath) -> tuple[Any, ...]:
    return tuple(
        sorted(
            _selected_branch_segments(artifact),
            key=lambda segment: (segment.sigma_start, segment.sigma_end, segment.segment_id),
        )
    )


def _source_partitions_match_joint_segments(artifact: M3CandidateAxisPath) -> bool:
    joint_boundaries = tuple(
        value
        for segment in _selected_branch_segments_sorted(artifact)
        for value in (segment.sigma_start, segment.sigma_end)
    )
    source_boundaries = tuple(
        value
        for segment in (
            *artifact.source_candidate_geometry.position_segments,
            *artifact.source_candidate_geometry.orientation_segments,
        )
        for value in (segment.sigma_start, segment.sigma_end)
    )
    return all(
        any(math.isclose(source, joint, abs_tol=_EPSILON) for joint in joint_boundaries)
        for source in source_boundaries
    )


def _rotary_axes_are_fixed(artifact: M3CandidateAxisPath) -> bool:
    rotary_indices = tuple(
        index
        for index, axis in enumerate(artifact.machine_profile.axes)
        if axis.joint_type == "revolute"
    )
    return all(
        all(abs(segment.coefficients[1][index]) <= _JOINT_CONTINUITY_TOLERANCE for index in rotary_indices)
        for segment in _selected_branch_segments_sorted(artifact)
    )


def _continuous_lift_support_failure(artifact: M3CandidateAxisPath) -> tuple[str, dict[str, Any]] | None:
    certificate = artifact.kinematics_certificate
    actual_machine_profile_content_id = _model_content_hash(artifact.machine_profile)
    if artifact.machine_profile_content_id != actual_machine_profile_content_id:
        return (
            "MachineProfileContentHashMismatch",
            {
                "expectedMachineProfileContentId": artifact.machine_profile_content_id,
                "actualMachineProfileContentId": actual_machine_profile_content_id,
            },
        )
    if certificate.machine_profile_content_id != actual_machine_profile_content_id:
        return (
            "KinematicsCertificateMachineProfileContentHashMismatch",
            {
                "expectedMachineProfileContentId": certificate.machine_profile_content_id,
                "actualMachineProfileContentId": actual_machine_profile_content_id,
            },
        )
    actual_source_geometry_content_id = _model_content_hash(artifact.source_candidate_geometry)
    if artifact.source_candidate_geometry_content_id != actual_source_geometry_content_id:
        return (
            "SourceCandidateGeometryContentHashMismatch",
            {
                "expectedSourceCandidateGeometryContentId": artifact.source_candidate_geometry_content_id,
                "actualSourceCandidateGeometryContentId": actual_source_geometry_content_id,
            },
        )
    if certificate.source_candidate_geometry_content_id != actual_source_geometry_content_id:
        return (
            "KinematicsCertificateSourceCandidateGeometryContentHashMismatch",
            {
                "expectedSourceCandidateGeometryContentId": certificate.source_candidate_geometry_content_id,
                "actualSourceCandidateGeometryContentId": actual_source_geometry_content_id,
            },
        )
    if certificate.claim_scope != _SELECTED_LIFT_SCOPE:
        return ("KinematicsClaimScopeUnsupported", {"claimScope": certificate.claim_scope})
    branch = _selected_branch_node(artifact)
    if branch is None:
        return (
            "SelectedBranchMissing",
            {"selectedBranchId": certificate.selected_branch_id},
        )
    if branch.status != "active":
        return (
            "SelectedBranchInactive",
            {"selectedBranchId": branch.branch_id, "branchStatus": branch.status},
        )
    segments = _selected_branch_segments(artifact)
    if len(segments) != len(artifact.joint_segments):
        return (
            "SelectedBranchDoesNotCoverWholePath",
            {
                "selectedBranchId": certificate.selected_branch_id,
                "selectedSegmentCount": len(segments),
                "totalSegmentCount": len(artifact.joint_segments),
            },
        )
    if certificate.interval_count != len(segments):
        return (
            "KinematicsIntervalCountMismatch",
            {
                "intervalCount": certificate.interval_count,
                "selectedSegmentCount": len(segments),
            },
        )
    if not math.isclose(branch.sigma_start, 0.0, abs_tol=_EPSILON) or not math.isclose(
        branch.sigma_end,
        1.0,
        abs_tol=_EPSILON,
    ):
        return (
            "SelectedBranchDoesNotCoverWholePath",
            {
                "selectedBranchId": branch.branch_id,
                "sigmaStart": branch.sigma_start,
                "sigmaEnd": branch.sigma_end,
            },
        )
    if not artifact.source_candidate_geometry.position_segments or any(
        not isinstance(segment, LinePositionSegment) for segment in artifact.source_candidate_geometry.position_segments
    ):
        return ("SourceGeometryLineSegmentsRequired", {})
    if not artifact.source_candidate_geometry.orientation_segments or any(
        not isinstance(segment, ConstantOrientationSegment) for segment in artifact.source_candidate_geometry.orientation_segments
    ):
        return ("SourceGeometryConstantOrientationRequired", {})
    if any(segment.interpolation != "linear" for segment in segments):
        return (
            "JointSegmentInterpolationUnsupported",
            {"interpolations": sorted({segment.interpolation for segment in segments})},
        )
    if not _source_partitions_match_joint_segments(artifact):
        return ("SourceGeometryPartitionNotRepresentedByJointSegments", {})
    if not _rotary_axes_are_fixed(artifact):
        return ("RotaryMotionUnsupportedByLinearFixedBranchProof", {})
    return None


def _claim_support_failure(artifact: M3CandidateAxisPath) -> tuple[str, dict[str, Any]] | None:
    support_failure = _continuous_lift_support_failure(artifact)
    if support_failure is not None:
        return support_failure
    certificate = artifact.kinematics_certificate
    if certificate.evidence_level not in _EXACT_EVIDENCE_LEVELS:
        return (
            "KinematicsCertificateRequiresExactOrCertifiedEvidence",
            {"evidenceLevel": certificate.evidence_level},
        )
    if certificate.continuous_method != _REQUIRED_CONTINUOUS_METHOD:
        return (
            "KinematicsContinuousMethodUnsupported",
            {"continuousMethod": certificate.continuous_method},
        )
    missing_policy_ids = sorted(_REQUIRED_POLICY_IDS.difference(certificate.policy_ids))
    if missing_policy_ids:
        return (
            "KinematicsPolicyIdsIncomplete",
            {"missingPolicyIds": missing_policy_ids, "policyIds": list(certificate.policy_ids)},
        )
    return None


def _dot3(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _norm3(vector: tuple[float, float, float]) -> float:
    return math.sqrt(_dot3(vector, vector))


def _sub3(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _lerp3(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    ratio: float,
) -> tuple[float, float, float]:
    return tuple(start[index] + (end[index] - start[index]) * ratio for index in range(3))  # type: ignore[return-value]


def _orientation_error(actual: tuple[float, float, float], target: tuple[float, float, float]) -> float:
    actual_norm = _norm3(actual)
    target_norm = _norm3(target)
    if actual_norm <= _EPSILON or target_norm <= _EPSILON:
        return math.inf
    actual_unit = (
        actual[0] / actual_norm,
        actual[1] / actual_norm,
        actual[2] / actual_norm,
    )
    target_unit = (
        target[0] / target_norm,
        target[1] / target_norm,
        target[2] / target_norm,
    )
    return math.acos(max(-1.0, min(1.0, _dot3(actual_unit, target_unit))))


def _matching_line_segments(artifact: M3CandidateAxisPath, sigma: float) -> tuple[LinePositionSegment, ...]:
    return tuple(
        segment
        for segment in artifact.source_candidate_geometry.position_segments
        if isinstance(segment, LinePositionSegment)
        and segment.sigma_start - _EPSILON <= sigma <= segment.sigma_end + _EPSILON
    )


def _matching_orientation_segments(artifact: M3CandidateAxisPath, sigma: float) -> tuple[ConstantOrientationSegment, ...]:
    return tuple(
        segment
        for segment in artifact.source_candidate_geometry.orientation_segments
        if isinstance(segment, ConstantOrientationSegment)
        and segment.sigma_start - _EPSILON <= sigma <= segment.sigma_end + _EPSILON
    )


def _expected_position(segment: LinePositionSegment, sigma: float) -> tuple[float, float, float]:
    span = segment.sigma_end - segment.sigma_start
    ratio = 0.0 if math.isclose(span, 0.0, abs_tol=_EPSILON) else (sigma - segment.sigma_start) / span
    return _lerp3(segment.start_point, segment.end_point, ratio)


def _joint_values_at_sigma(artifact: M3CandidateAxisPath, sigma: float) -> tuple[float, ...]:
    matching_segments = [
        segment
        for segment in _selected_branch_segments_sorted(artifact)
        if segment.sigma_start - _EPSILON <= sigma <= segment.sigma_end + _EPSILON
    ]
    if not matching_segments:
        raise ValueError("SelectedLiftSigmaOutsideSegmentCoverage")
    return tuple(float(value) for value in matching_segments[0].evaluate(sigma))


def _joint_mapping(artifact: M3CandidateAxisPath, joint_values: tuple[float, ...]) -> dict[str, float]:
    return {
        axis.axis_id: float(value)
        for axis, value in zip(artifact.machine_profile.axes, joint_values, strict=True)
    }


def _normalized_axis_limit_margin(
    artifact: M3CandidateAxisPath,
    joint_values: tuple[float, ...],
) -> float:
    normalized_margins: list[float] = []
    for axis, value in zip(artifact.machine_profile.axes, joint_values, strict=True):
        axis_range = axis.limits.upper - axis.limits.lower
        normalized_margins.append(
            min(value - axis.limits.lower, axis.limits.upper - value) / axis_range
        )
    return min(normalized_margins)


def _unique_sample_sigmas(artifact: M3CandidateAxisPath) -> tuple[float, ...]:
    sigmas: list[float] = []
    for segment in _selected_branch_segments_sorted(artifact):
        midpoint = (segment.sigma_start + segment.sigma_end) * 0.5
        for sigma in (segment.sigma_start, midpoint, segment.sigma_end):
            if not any(math.isclose(sigma, existing, abs_tol=_EPSILON) for existing in sigmas):
                sigmas.append(sigma)
    return tuple(sigmas)


def _line_boundary_consistency_failure(artifact: M3CandidateAxisPath) -> tuple[str, dict[str, Any]] | None:
    position_tolerance = _position_tolerance_absolute(artifact)
    orientation_tolerance = _orientation_tolerance_absolute(artifact)
    for sigma in _unique_sample_sigmas(artifact):
        matching_lines = _matching_line_segments(artifact, sigma)
        if not matching_lines:
            return ("SourceLineSegmentCoverageIncomplete", {"sigma": sigma})
        matching_orientations = _matching_orientation_segments(artifact, sigma)
        if not matching_orientations:
            return ("SourceOrientationSegmentCoverageIncomplete", {"sigma": sigma})
        expected_positions = tuple(_expected_position(segment, sigma) for segment in matching_lines)
        canonical_position = expected_positions[0]
        if any(_norm3(_sub3(position, canonical_position)) > position_tolerance + _EPSILON for position in expected_positions[1:]):
            return ("SourceGeometryBoundaryDiscontinuous", {"sigma": sigma})
        canonical_axis = matching_orientations[0].axis
        if any(
            _orientation_error(segment.axis, canonical_axis) > orientation_tolerance + _EPSILON
            for segment in matching_orientations[1:]
        ):
            return ("SourceOrientationBoundaryDiscontinuous", {"sigma": sigma})
    return None


def _replay_lift(artifact: M3CandidateAxisPath) -> tuple[_LiftReplayResult | None, tuple[str, dict[str, Any]] | None]:
    support_failure = _continuous_lift_support_failure(artifact)
    if support_failure is not None:
        return (None, support_failure)
    boundary_failure = _line_boundary_consistency_failure(artifact)
    if boundary_failure is not None:
        return (None, boundary_failure)
    samples: list[_ReplaySample] = []
    for sigma in _unique_sample_sigmas(artifact):
        joint_values = _joint_values_at_sigma(artifact, sigma)
        pose = forward_kinematics(artifact.machine_profile, _joint_mapping(artifact, joint_values))
        expected_position = _expected_position(_matching_line_segments(artifact, sigma)[0], sigma)
        expected_axis = _matching_orientation_segments(artifact, sigma)[0].axis
        singularity = jacobian_evidence(
            artifact.machine_profile,
            _joint_mapping(artifact, joint_values),
        )
        samples.append(
            _ReplaySample(
                sigma=sigma,
                position_residual=_norm3(_sub3(pose.position, expected_position)),
                orientation_residual=_orientation_error(pose.tool_axis, expected_axis),
                normalized_axis_margin=_normalized_axis_limit_margin(artifact, joint_values),
                minimum_singular_value=singularity.minimum_singular_value,
                singular=singularity.singular,
            )
        )
    return (
        _LiftReplayResult(
            samples=tuple(samples),
            position_residual_max=max(sample.position_residual for sample in samples),
            orientation_residual_max=max(sample.orientation_residual for sample in samples),
            normalized_axis_margin_min=min(sample.normalized_axis_margin for sample in samples),
            minimum_singular_value_min=min(sample.minimum_singular_value for sample in samples),
        ),
        None,
    )


def _replay_refutation(artifact: M3CandidateAxisPath) -> tuple[str, dict[str, Any]] | None:
    replay, failure = _replay_lift(artifact)
    if replay is None:
        return failure
    position_tolerance = _position_tolerance_absolute(artifact)
    orientation_tolerance = _orientation_tolerance_absolute(artifact)
    if replay.position_residual_max > position_tolerance + _EPSILON or replay.orientation_residual_max > orientation_tolerance + _EPSILON:
        return (
            "SelectedLiftReplayResidualExceeded",
            {
                "positionResidualMax": replay.position_residual_max,
                "orientationResidualMax": replay.orientation_residual_max,
                "positionTolerance": position_tolerance,
                "orientationTolerance": orientation_tolerance,
            },
        )
    if replay.normalized_axis_margin_min < -_EPSILON:
        return (
            "SelectedLiftViolatesAxisLimits",
            {"normalizedAxisLimitMarginMin": replay.normalized_axis_margin_min},
        )
    if (
        artifact.kinematics_certificate.singularity_handling == "regular-only"
        and any(sample.singular for sample in replay.samples)
    ):
        return (
            "SelectedLiftTouchesSingularity",
            {"minimumSingularValueMin": replay.minimum_singular_value_min},
        )
    segments = _selected_branch_segments_sorted(artifact)
    for left, right in zip(segments[:-1], segments[1:], strict=True):
        left_joints = tuple(float(value) for value in left.evaluate(left.sigma_end))
        right_joints = tuple(float(value) for value in right.evaluate(right.sigma_start))
        if any(abs(left_value - right_value) > _JOINT_CONTINUITY_TOLERANCE for left_value, right_value in zip(left_joints, right_joints, strict=True)):
            return (
                "SelectedLiftDiscontinuous",
                {"leftSegmentId": left.segment_id, "rightSegmentId": right.segment_id},
            )
        left_pose = forward_kinematics(artifact.machine_profile, _joint_mapping(artifact, left_joints))
        right_pose = forward_kinematics(artifact.machine_profile, _joint_mapping(artifact, right_joints))
        if _norm3(_sub3(left_pose.position, right_pose.position)) > _position_tolerance_absolute(artifact) + _EPSILON or _orientation_error(
            left_pose.tool_axis,
            right_pose.tool_axis,
        ) > _orientation_tolerance_absolute(artifact) + _EPSILON:
            return (
                "SelectedLiftDiscontinuous",
                {"leftSegmentId": left.segment_id, "rightSegmentId": right.segment_id},
            )
    return None


def _residual_metric(artifact: M3CandidateAxisPath, metric_id: str) -> MetricResult:
    replay, failure = _replay_lift(artifact)
    if replay is None:
        reason_code, details = failure or ("SelectedLiftReplayUnavailable", {})
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, reason_code, **details)
    value = (
        replay.position_residual_max
        if metric_id == POSITION_RESIDUAL_MAX_METRIC_ID
        else replay.orientation_residual_max
    )
    unit = "mm" if metric_id == POSITION_RESIDUAL_MAX_METRIC_ID else "rad"
    return _computed(
        metric_id,
        value,
        unit=unit,
        level="Validated",
        method=_REPLAY_METHOD,
        details={
            "replaySampleSigmas": [sample.sigma for sample in replay.samples],
            "selectedBranchId": artifact.kinematics_certificate.selected_branch_id,
        },
    )


def _kinematics_metric(artifact: M3CandidateAxisPath, metric_id: str) -> MetricResult:
    replay, failure = _replay_lift(artifact)
    if replay is None:
        reason_code, details = failure or ("SelectedLiftReplayUnavailable", {})
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, reason_code, **details)
    if metric_id == AXIS_LIMIT_MARGIN_MIN_METRIC_ID:
        return _computed(
            metric_id,
            replay.normalized_axis_margin_min,
            unit="dimensionless",
            level="Validated",
            method=_REPLAY_METHOD,
            details={
                "replaySampleSigmas": [sample.sigma for sample in replay.samples],
                "selectedBranchId": artifact.kinematics_certificate.selected_branch_id,
            },
        )
    return _computed(
        metric_id,
        replay.minimum_singular_value_min,
        unit="dimensionless",
        level="Validated",
        method=_REPLAY_METHOD,
        details={
            "replaySampleSigmas": [sample.sigma for sample in replay.samples],
            "selectedBranchId": artifact.kinematics_certificate.selected_branch_id,
        },
    )


def _kinematically_feasible_metric(artifact: M3CandidateAxisPath) -> MetricResult:
    replay, replay_failure = _replay_lift(artifact)
    if replay is None:
        reason_code, details = replay_failure or ("SelectedLiftReplayUnavailable", {})
        return _unavailable(
            KINEMATICALLY_FEASIBLE_METRIC_ID,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            reason_code,
            **details,
        )
    support_failure = _claim_support_failure(artifact)
    if support_failure is not None:
        reason_code, details = support_failure
        return _unavailable(
            KINEMATICALLY_FEASIBLE_METRIC_ID,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            reason_code,
            **details,
        )
    refutation = _replay_refutation(artifact)
    certificate = artifact.kinematics_certificate
    details = {
        "certificate": certificate.model_dump(mode="json", by_alias=True, exclude_none=True),
        "selectedBranchId": certificate.selected_branch_id,
        "replaySampleSigmas": [sample.sigma for sample in replay.samples],
        "positionResidualMax": replay.position_residual_max,
        "orientationResidualMax": replay.orientation_residual_max,
        "normalizedAxisLimitMarginMin": replay.normalized_axis_margin_min,
        "minimumSingularValueMin": replay.minimum_singular_value_min,
    }
    if refutation is not None:
        reason_code, extra = refutation
        details.update(extra)
        return _computed(
            KINEMATICALLY_FEASIBLE_METRIC_ID,
            False,
            level="Observed",
            method=_CLAIM_METHOD,
            reason_code=reason_code,
            details=details,
        )
    return _computed(
        KINEMATICALLY_FEASIBLE_METRIC_ID,
        True,
        level="Certified",
        method=_CLAIM_METHOD,
        details=details,
    )


def _collision_model_binding_failure(
    request: FiveAxisF2EvaluationBindingRequest,
) -> tuple[str, dict[str, Any]] | None:
    if request.collision_model is None:
        return ("CollisionModelRequired", {})
    return None


def _artifact_content_hash(artifact: M3CandidateAxisPath) -> str:
    return _content_hash(
        normalize_numeric_identity(artifact.model_dump(mode="json", by_alias=True, exclude_none=True))
    )


def _collision_path_evaluation(
    request: FiveAxisF2EvaluationBindingRequest,
    artifact: M3CandidateAxisPath,
) -> tuple[ConfigurationCollisionEvaluation | None, tuple[str, dict[str, Any]] | None]:
    binding_failure = _collision_model_binding_failure(request)
    if binding_failure is not None:
        return (None, binding_failure)
    support_failure = _claim_support_failure(artifact)
    if support_failure is not None:
        return (None, support_failure)
    replay_refutation = _replay_refutation(artifact)
    if replay_refutation is not None:
        return (None, replay_refutation)
    assert request.collision_model is not None
    return (
        evaluate_configuration_path_collision(
            artifact,
            collision_model=request.collision_model,
        ),
        None,
    )


def _collision_metric(
    request: FiveAxisF2EvaluationBindingRequest,
    artifact: M3CandidateAxisPath,
) -> MetricResult:
    evaluation, failure = _collision_path_evaluation(request, artifact)
    if failure is not None:
        reason_code, details = failure
        status = (
            MetricStatus.INSUFFICIENT_CONTEXT
            if reason_code == "CollisionModelRequired"
            else MetricStatus.UNSUPPORTED_CAPABILITY
        )
        return _unavailable(CONFIGURATION_COLLISION_FREE_METRIC_ID, status, reason_code, **details)
    assert evaluation is not None
    expected_axis_path_content_id = _artifact_content_hash(artifact)
    details = {
        "selectedBranchId": artifact.kinematics_certificate.selected_branch_id,
        "collisionEvaluation": evaluation.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    if (
        evaluation.query_kind == "path"
        and evaluation.status == "collision"
        and math.isclose(evaluation.sigma_start, 0.0, abs_tol=_EPSILON)
        and math.isclose(evaluation.sigma_end, 1.0, abs_tol=_EPSILON)
    ):
        return _computed(
            CONFIGURATION_COLLISION_FREE_METRIC_ID,
            False,
            level="Observed",
            method="five-axis.f2.configuration-collision-closure@1",
            reason_code=evaluation.reason_code,
            details=details,
        )
    if (
        evaluation.query_kind == "path"
        and evaluation.status == "safe"
        and evaluation.certificate_kind == "proof"
        and evaluation.evidence_level == "Certified"
        and evaluation.collision_free is True
        and evaluation.claim_id == CONFIGURATION_COLLISION_FREE_CLAIM_ID
        and evaluation.axis_path_id == artifact.axis_path_id
        and evaluation.axis_path_content_id == expected_axis_path_content_id
        and evaluation.machine_profile_id == artifact.machine_profile.profile_id
        and evaluation.machine_profile_content_id == artifact.machine_profile_content_id
        and math.isclose(evaluation.sigma_start, 0.0, abs_tol=_EPSILON)
        and math.isclose(evaluation.sigma_end, 1.0, abs_tol=_EPSILON)
    ):
        return _computed(
            CONFIGURATION_COLLISION_FREE_METRIC_ID,
            True,
            level="Certified",
            method="five-axis.f2.configuration-collision-closure@1",
            details=details,
        )
    if evaluation.status == "unsupported":
        return _unavailable(
            CONFIGURATION_COLLISION_FREE_METRIC_ID,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            evaluation.reason_code,
            **details,
        )
    if evaluation.status == "unresolved":
        return _unavailable(
            CONFIGURATION_COLLISION_FREE_METRIC_ID,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            evaluation.reason_code,
            **details,
        )
    if evaluation.status == "safe":
        return _unavailable(
            CONFIGURATION_COLLISION_FREE_METRIC_ID,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            "ConfigurationCollisionClaimUnavailable",
            **details,
        )
    return _unavailable(
        CONFIGURATION_COLLISION_FREE_METRIC_ID,
        MetricStatus.UNSUPPORTED_CAPABILITY,
        evaluation.reason_code,
        **details,
    )


def _metric_result(
    request: FiveAxisF2EvaluationBindingRequest,
    metric_id: str,
) -> MetricResult:
    artifact = request.artifact
    if metric_id in {
        POSITION_RESIDUAL_MAX_METRIC_ID,
        ORIENTATION_RESIDUAL_MAX_METRIC_ID,
        AXIS_LIMIT_MARGIN_MIN_METRIC_ID,
        SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID,
        KINEMATICALLY_FEASIBLE_METRIC_ID,
        CONFIGURATION_COLLISION_FREE_METRIC_ID,
    } and not isinstance(artifact, M3CandidateAxisPath):
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MetricOutsideArtifactDomain")
    if not isinstance(artifact, M3CandidateAxisPath):
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "MetricNotImplementedInF2")
    if metric_id in {POSITION_RESIDUAL_MAX_METRIC_ID, ORIENTATION_RESIDUAL_MAX_METRIC_ID}:
        return _residual_metric(artifact, metric_id)
    if metric_id in {AXIS_LIMIT_MARGIN_MIN_METRIC_ID, SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID}:
        return _kinematics_metric(artifact, metric_id)
    if metric_id == KINEMATICALLY_FEASIBLE_METRIC_ID:
        return _kinematically_feasible_metric(artifact)
    if metric_id == CONFIGURATION_COLLISION_FREE_METRIC_ID:
        return _collision_metric(request, artifact)
    return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "MetricNotImplementedInF2")


def _capabilities(request: FiveAxisF2EvaluationBindingRequest) -> list[CapabilityResolution]:
    artifact = request.artifact
    resolved: list[CapabilityResolution] = []
    if isinstance(artifact, M1ReferencePath | M2CandidateTaskGeometry | M3CandidateAxisPath):
        resolved.append(CapabilityResolution(capabilityId=CAP_PATH_PROGRESS, source="Artifact"))
        resolved.append(CapabilityResolution(capabilityId=CAP_REGULARITY, source="Artifact"))
    if isinstance(artifact, M3CandidateAxisPath):
        resolved.append(CapabilityResolution(capabilityId=CAP_MACHINE_PROFILE, source="Profile"))
        evaluation, failure = _collision_path_evaluation(request, artifact)
        if (
            failure is None
            and evaluation is not None
            and evaluation.claim_id == CONFIGURATION_COLLISION_FREE_CLAIM_ID
            and evaluation.query_kind == "path"
        ):
            resolved.append(CapabilityResolution(capabilityId=CAP_CONFIGURATION_COLLISION, source="Evaluator"))
    return resolved


def evaluate_five_axis_f2(
    request: FiveAxisF2EvaluationBindingRequest | dict[str, Any],
) -> EvaluationReport:
    resolved = request if isinstance(request, FiveAxisF2EvaluationBindingRequest) else FiveAxisF2EvaluationBindingRequest.model_validate(request)
    metric_ids = [item.metric_id for item in resolved.case.required_metrics + resolved.case.optional_metrics]
    raw_results = [_metric_result(resolved, metric_id) for metric_id in metric_ids]
    thresholds = {
        item.metric_id: item.threshold
        for item in resolved.case.required_metrics + resolved.case.optional_metrics
    }
    results = [_apply_threshold(result, thresholds.get(result.metric_id)) for result in raw_results]
    required_count = len(resolved.case.required_metrics)
    case_outcome = _aggregate_outcome(results[:required_count])
    artifact_payload = resolved.artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    request_payload = resolved.model_dump(mode="json", by_alias=True, exclude_none=True)
    case_payload = resolved.case.model_dump(mode="json", by_alias=True, exclude_none=True)
    provenance = Provenance(
        requestHash=_content_hash(request_payload),
        artifactHash=_content_hash(artifact_payload),
        caseHash=_content_hash(case_payload),
        runnerId=F2_RUNNER_ID,
        evaluatorVersion=F2_EVALUATOR_ID,
        executionOutcomePolicy=resolved.case.execution_outcome_policy,
        numericEnvironment=current_f2_numeric_environment(),
    )
    failures = [
        DomainFailure(
            code=result.reason_code,
            message=f"F2 metric {result.metric_id} did not produce a closed positive result.",
            path=f"case.requiredMetrics[{index}]",
            severity="finding",
        )
        for index, result in enumerate(results[:required_count])
        if result.status is not MetricStatus.COMPUTED and result.reason_code is not None
    ]
    report = EvaluationReport(
        executionStatus=ExecutionStatus.SUCCEEDED,
        caseOutcome=case_outcome,
        metricResults=results,
        capabilities=_capabilities(resolved),
        domainFailures=failures,
        evaluatorVersion=F2_EVALUATOR_ID,
        provenance=provenance,
        contentHash="",
    )
    return _seal_evaluation_report(report)


FIVE_AXIS_F2_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=FIVE_AXIS_F2_DOMAIN_PACK_ID,
        parse_request=_parse_f2_request,
        evaluate=evaluate_five_axis_f2,
    )
)


__all__ = [
    "AXIS_LIMIT_MARGIN_MIN_METRIC_ID",
    "CONFIGURATION_COLLISION_FREE_CLAIM_ID",
    "CONFIGURATION_COLLISION_FREE_METRIC_ID",
    "F2_EVALUATOR_ID",
    "F2_RUNNER_ID",
    "FIVE_AXIS_F2_DOMAIN_PACK",
    "FIVE_AXIS_F2_DOMAIN_PACK_ID",
    "FIVE_AXIS_F2_RUNTIME_BINDING",
    "FiveAxisF2EvaluationBindingRequest",
    "KINEMATICALLY_FEASIBLE_CLAIM_ID",
    "KINEMATICALLY_FEASIBLE_METRIC_ID",
    "ORIENTATION_RESIDUAL_MAX_METRIC_ID",
    "POSITION_RESIDUAL_MAX_METRIC_ID",
    "SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID",
    "current_f2_numeric_environment",
    "evaluate_five_axis_f2",
]
