from __future__ import annotations

import platform
from importlib.metadata import version as package_version
from typing import Annotated, Any

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
from ..evaluator import _aggregate_outcome, _apply_threshold, _content_hash
from ..models import (
    AxiomModel,
    CapabilityResolution,
    CoreEvaluationRequest,
    DomainFailure,
    EvaluationCase,
    EvaluationReport,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Provenance,
)
from ..runtime import DomainRuntimeBinding, register_domain_runtime_binding
from .f1_collision import TaskCollisionEvaluation, evaluate_task_collision
from .f1_geometry import ContinuousErrorCertificate, compute_continuous_error_certificate
from .f1_models import (
    AxisAlignedBoundingBox,
    F1MathStageManifest,
    M1ReferencePath,
    M2CandidateTaskGeometry,
    NormalizedProgram,
    ToleranceBinding,
)


FIVE_AXIS_F1_DOMAIN_PACK_ID = "five-axis.domain-pack@2"
F1_EVALUATOR_ID = "five-axis-f1-evaluator@1"
F1_RUNNER_ID = ARTIFACT_IMPORT_RUNNER_ID

M0_VALID_METRIC_ID = "five-axis.normalized-program.valid@1"
M1_VALID_METRIC_ID = "five-axis.reference-path.valid@1"
POSITION_MAX_ERROR_METRIC_ID = "five-axis.position.max-error@1"
ORIENTATION_MAX_ERROR_METRIC_ID = "five-axis.orientation.max-error@1"
GEOMETRY_VALID_METRIC_ID = "five-axis.geometry.valid@1"
TASK_COLLISION_FREE_METRIC_ID = "five-axis.task-geometry.collision-free@1"
TASK_OVERCUT_FREE_METRIC_ID = "five-axis.task-geometry.overcut-free@1"
MINIMUM_CLEARANCE_METRIC_ID = "five-axis.task-geometry.minimum-clearance@1"

GEOMETRY_VALID_CLAIM_ID = "five-axis.geometry-valid-claim@1"
TASK_COLLISION_FREE_CLAIM_ID = "five-axis.task-geometry-collision-free-claim@1"

CAP_FRONTEND = "five-axis.frontend.axiom-cl-subset@1"
CAP_PATH_PROGRESS = "five-axis.path-progress.bound@1"
CAP_REGULARITY = "five-axis.regularity.certified@1"
CAP_CORRESPONDENCE = "five-axis.correspondence.policy-bound@1"
CAP_CONTINUOUS_ERROR = "five-axis.continuous-error.bound@1"
CAP_COLLISION_CONTEXT = "five-axis.collision-context.complete@1"
CAP_PROCESS_STATE = "five-axis.process-state.bound@1"
CAP_TASK_COLLISION = "five-axis.task-geometry.collision.checked@1"


F1Artifact = Annotated[
    NormalizedProgram | M1ReferencePath | M2CandidateTaskGeometry,
    Field(discriminator="artifact_type"),
]


class FiveAxisF1EvaluationBindingRequest(AxiomModel):
    artifact: F1Artifact
    case: EvaluationCase
    reference_path: M1ReferencePath | None = Field(default=None, alias="referencePath")
    manifest: F1MathStageManifest | None = None
    stock_state_geometries: dict[str, dict[str, tuple[AxisAlignedBoundingBox, ...]]] | None = Field(
        default=None,
        alias="stockStateGeometries",
    )


_FAILURE_MAPPINGS = (
    FailureMapping(
        code="MalformedEvaluationRequest",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="ArtifactTypeMismatch",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="ArtifactSchemaVersionMismatch",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="DomainEvaluatorFailed",
        executionStatus="ExecutionFailed",
        metricStatus="NumericalFailure",
        caseOutcome="Inconclusive",
    ),
)


FIVE_AXIS_F1_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=FIVE_AXIS_F1_DOMAIN_PACK_ID,
        artifactType="five-axis.m2-candidate-task-geometry",
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
        ),
        evaluatorVersion=F1_EVALUATOR_ID,
        runnerId=F1_RUNNER_ID,
        runnerIds=(F1_RUNNER_ID,),
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
        metricDefinitions=(
            MetricDefinition(
                metricId=M0_VALID_METRIC_ID,
                metricDefinitionId=M0_VALID_METRIC_ID,
                requires=(CAP_FRONTEND,),
            ),
            MetricDefinition(
                metricId=M1_VALID_METRIC_ID,
                metricDefinitionId=M1_VALID_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY),
            ),
            MetricDefinition(
                metricId=POSITION_MAX_ERROR_METRIC_ID,
                metricDefinitionId=POSITION_MAX_ERROR_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_CORRESPONDENCE, CAP_CONTINUOUS_ERROR),
                direction="lower-is-better",
                numericTolerance=DomainNumericTolerance(absolute=1e-9, relative=1e-12),
            ),
            MetricDefinition(
                metricId=ORIENTATION_MAX_ERROR_METRIC_ID,
                metricDefinitionId=ORIENTATION_MAX_ERROR_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_CORRESPONDENCE, CAP_CONTINUOUS_ERROR),
                direction="lower-is-better",
                numericTolerance=DomainNumericTolerance(absolute=1e-12, relative=1e-12, unit="rad"),
            ),
            MetricDefinition(
                metricId=GEOMETRY_VALID_METRIC_ID,
                metricDefinitionId=GEOMETRY_VALID_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_CORRESPONDENCE, CAP_CONTINUOUS_ERROR),
                claimDefinitionId=GEOMETRY_VALID_CLAIM_ID,
                claimPredicate="five-axis.GeometryValid is true",
            ),
            MetricDefinition(
                metricId=TASK_COLLISION_FREE_METRIC_ID,
                metricDefinitionId=TASK_COLLISION_FREE_METRIC_ID,
                requires=(CAP_COLLISION_CONTEXT, CAP_PROCESS_STATE, CAP_PATH_PROGRESS, CAP_TASK_COLLISION),
                claimDefinitionId=TASK_COLLISION_FREE_CLAIM_ID,
                claimPredicate="five-axis.TaskGeometryCollisionFree is true",
            ),
            MetricDefinition(
                metricId=TASK_OVERCUT_FREE_METRIC_ID,
                metricDefinitionId=TASK_OVERCUT_FREE_METRIC_ID,
                requires=(CAP_COLLISION_CONTEXT, CAP_PROCESS_STATE, CAP_PATH_PROGRESS, CAP_TASK_COLLISION),
            ),
            MetricDefinition(
                metricId=MINIMUM_CLEARANCE_METRIC_ID,
                metricDefinitionId=MINIMUM_CLEARANCE_METRIC_ID,
                requires=(CAP_COLLISION_CONTEXT, CAP_PROCESS_STATE, CAP_PATH_PROGRESS, CAP_TASK_COLLISION),
                direction="higher-is-better",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            GEOMETRY_VALID_CLAIM_ID,
            TASK_COLLISION_FREE_CLAIM_ID,
        ),
        comparisonPolicyIds=(),
        failureMappings=_FAILURE_MAPPINGS,
    )
)


def current_f1_numeric_environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": package_version("numpy"),
        "scipy": package_version("scipy"),
        "pydantic": package_version("pydantic"),
    }


def _parse_f1_request(request: CoreEvaluationRequest) -> FiveAxisF1EvaluationBindingRequest:
    return FiveAxisF1EvaluationBindingRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _definition(metric_id: str) -> MetricDefinition | None:
    try:
        return FIVE_AXIS_F1_DOMAIN_PACK.metric_definition(metric_id)
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
    level: str,
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
        evidence={"level": level, "method": method},
    )


def _tolerance(artifact: M2CandidateTaskGeometry, target: str) -> ToleranceBinding | None:
    return next((item for item in artifact.tolerances if item.target == target), None)


def _reference_failure(request: FiveAxisF1EvaluationBindingRequest) -> tuple[str, dict[str, Any]] | None:
    artifact = request.artifact
    if not isinstance(artifact, M2CandidateTaskGeometry):
        return ("MetricOutsideArtifactDomain", {})
    reference = request.reference_path
    if reference is None:
        return ("ReferencePathRequired", {})
    if artifact.source_reference_path_id != reference.reference_path_id:
        return (
            "ReferencePathIdentityMismatch",
            {"expectedReferencePathId": artifact.source_reference_path_id, "actualReferencePathId": reference.reference_path_id},
        )
    reference_hash = _content_hash(reference.model_dump(mode="json", by_alias=True, exclude_none=True))
    if artifact.source_reference_path_content_id is None:
        return ("ReferencePathContentIdentityRequired", {"actualReferencePathContentId": reference_hash})
    if artifact.source_reference_path_content_id != reference_hash:
        return (
            "ReferencePathContentIdentityMismatch",
            {
                "expectedReferencePathContentId": artifact.source_reference_path_content_id,
                "actualReferencePathContentId": reference_hash,
            },
        )
    if artifact.coordinate_context != reference.coordinate_context:
        return ("ReferenceCoordinateContextMismatch", {})
    return None


def _error_certificate(request: FiveAxisF1EvaluationBindingRequest) -> ContinuousErrorCertificate | None:
    if _reference_failure(request) is not None:
        return None
    assert isinstance(request.artifact, M2CandidateTaskGeometry)
    assert request.reference_path is not None
    return compute_continuous_error_certificate(
        request.artifact,
        request.reference_path,
        request.artifact.correspondence,
    )


def _error_metric(
    request: FiveAxisF1EvaluationBindingRequest,
    metric_id: str,
    certificate: ContinuousErrorCertificate | None,
) -> MetricResult:
    failure = _reference_failure(request)
    if failure is not None:
        reason, details = failure
        status = MetricStatus.NOT_APPLICABLE if reason == "MetricOutsideArtifactDomain" else MetricStatus.INSUFFICIENT_CONTEXT
        return _unavailable(metric_id, status, reason, **details)
    assert isinstance(request.artifact, M2CandidateTaskGeometry)
    assert certificate is not None
    bound = certificate.position if metric_id == POSITION_MAX_ERROR_METRIC_ID else certificate.tool_axis_angle
    target = "position" if metric_id == POSITION_MAX_ERROR_METRIC_ID else "orientation"
    tolerance = _tolerance(request.artifact, target)
    if tolerance is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, f"{target.title()}ToleranceRequired")
    if bound is None:
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, f"{target.title()}GeometryUnavailable")
    rigorous = bound.level in {"Exact", "Certified"} and bound.bound_semantics == "rigorous-continuous"
    value = bound.upper if rigorous else bound.lower
    return _computed(
        metric_id,
        value,
        unit=tolerance.tolerance.unit,
        level=bound.level,
        method=bound.method,
        reason_code=None if rigorous else "ObservedMaximumOnly",
        details={
            "certificate": certificate.model_dump(mode="json", by_alias=True, exclude_none=True),
            "continuousUpperBound": rigorous,
            "tolerance": tolerance.model_dump(mode="json", by_alias=True),
        },
    )


def _geometry_valid_metric(
    request: FiveAxisF1EvaluationBindingRequest,
    certificate: ContinuousErrorCertificate | None,
) -> MetricResult:
    metric_id = GEOMETRY_VALID_METRIC_ID
    failure = _reference_failure(request)
    if failure is not None:
        reason, details = failure
        status = MetricStatus.NOT_APPLICABLE if reason == "MetricOutsideArtifactDomain" else MetricStatus.INSUFFICIENT_CONTEXT
        return _unavailable(metric_id, status, reason, **details)
    assert isinstance(request.artifact, M2CandidateTaskGeometry)
    assert certificate is not None
    artifact = request.artifact
    if artifact.regularity_certificate is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "RegularityCertificateRequired")
    if artifact.correspondence.objective_domain != "continuous":
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "ContinuousCorrespondenceProofUnavailable")
    position_tolerance = _tolerance(artifact, "position")
    orientation_tolerance = _tolerance(artifact, "orientation")
    if position_tolerance is None or orientation_tolerance is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "PositionAndOrientationTolerancesRequired")
    if certificate.position is None or certificate.tool_axis_angle is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "PositionAndOrientationEvidenceRequired")
    bounds = (
        (certificate.position, position_tolerance),
        (certificate.tool_axis_angle, orientation_tolerance),
    )
    if any(bound.lower > tolerance.tolerance.absolute for bound, tolerance in bounds):
        return _computed(
            metric_id,
            False,
            level="Observed",
            method="five-axis.f1.geometry-tolerance-gate@1",
            reason_code="GeometryToleranceExceeded",
            details={"certificate": certificate.model_dump(mode="json", by_alias=True, exclude_none=True)},
        )
    if not all(
        bound.level in {"Exact", "Certified"}
        and bound.bound_semantics == "rigorous-continuous"
        and bound.upper is not None
        and bound.upper <= tolerance.tolerance.absolute
        for bound, tolerance in bounds
    ):
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "ContinuousErrorBoundNotClosed")
    return _computed(
        metric_id,
        True,
        level="Certified" if any(bound.level == "Certified" for bound, _ in bounds) else "Exact",
        method="five-axis.f1.geometry-tolerance-gate@1",
        details={"certificate": certificate.model_dump(mode="json", by_alias=True, exclude_none=True)},
    )


def _collision_metric(
    request: FiveAxisF1EvaluationBindingRequest,
    metric_id: str,
    evaluation: TaskCollisionEvaluation | None,
) -> MetricResult:
    if not isinstance(request.artifact, M2CandidateTaskGeometry):
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MetricOutsideArtifactDomain")
    if request.artifact.collision_context is None or request.artifact.process_state_timeline is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "CollisionContextRequired")
    assert evaluation is not None
    details = {"collisionEvaluation": evaluation.model_dump(mode="json", by_alias=True, exclude_none=True)}
    if metric_id == MINIMUM_CLEARANCE_METRIC_ID:
        if evaluation.minimum_clearance_lower_bound is None:
            return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, evaluation.reason_code or "ClearanceUnresolved", **details)
        return _computed(
            metric_id,
            evaluation.minimum_clearance_lower_bound,
            unit=evaluation.clearance_unit,
            level=evaluation.evidence_level,
            method=evaluation.continuous_method,
            details=details,
        )
    value = evaluation.overcut_free if metric_id == TASK_OVERCUT_FREE_METRIC_ID else (
        evaluation.collision_free is True and evaluation.overcut_free is True
        if evaluation.collision_free is not None and evaluation.overcut_free is not None
        else None
    )
    if value is False:
        return _computed(
            metric_id,
            False,
            level="Observed",
            method=evaluation.continuous_method,
            reason_code=evaluation.reason_code,
            details=details,
        )
    if value is True and evaluation.evidence_level == "Certified":
        return _computed(
            metric_id,
            True,
            level="Certified",
            method=evaluation.continuous_method,
            reason_code=evaluation.reason_code,
            details=details,
        )
    return _unavailable(
        metric_id,
        MetricStatus.UNSUPPORTED_CAPABILITY,
        evaluation.reason_code or "ContinuousCollisionProofUnavailable",
        **details,
    )


def _metric_result(
    request: FiveAxisF1EvaluationBindingRequest,
    metric_id: str,
    error_certificate: ContinuousErrorCertificate | None,
    collision_evaluation: TaskCollisionEvaluation | None,
) -> MetricResult:
    artifact = request.artifact
    if metric_id == M0_VALID_METRIC_ID:
        if not isinstance(artifact, NormalizedProgram):
            return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MetricOutsideArtifactDomain")
        return _computed(metric_id, True, level="Certified", method="five-axis.f1.normalized-program-schema@1")
    if metric_id == M1_VALID_METRIC_ID:
        if not isinstance(artifact, M1ReferencePath):
            return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MetricOutsideArtifactDomain")
        if artifact.regularity_certificate is None:
            return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "RegularityCertificateRequired")
        return _computed(metric_id, True, level="Certified", method="five-axis.f1.reference-path-contract@1")
    if metric_id in {POSITION_MAX_ERROR_METRIC_ID, ORIENTATION_MAX_ERROR_METRIC_ID}:
        return _error_metric(request, metric_id, error_certificate)
    if metric_id == GEOMETRY_VALID_METRIC_ID:
        return _geometry_valid_metric(request, error_certificate)
    if metric_id in {TASK_COLLISION_FREE_METRIC_ID, TASK_OVERCUT_FREE_METRIC_ID, MINIMUM_CLEARANCE_METRIC_ID}:
        return _collision_metric(request, metric_id, collision_evaluation)
    return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "MetricNotImplementedInF1")


def _capabilities(request: FiveAxisF1EvaluationBindingRequest) -> list[CapabilityResolution]:
    artifact = request.artifact
    resolved: list[CapabilityResolution] = []
    if isinstance(artifact, NormalizedProgram):
        resolved.append(CapabilityResolution(capabilityId=CAP_FRONTEND, source="Artifact"))
    if isinstance(artifact, M1ReferencePath | M2CandidateTaskGeometry):
        resolved.append(CapabilityResolution(capabilityId=CAP_PATH_PROGRESS, source="Artifact"))
        if artifact.regularity_certificate is not None:
            resolved.append(CapabilityResolution(capabilityId=CAP_REGULARITY, source="Artifact"))
    if isinstance(artifact, M2CandidateTaskGeometry):
        resolved.extend(
            [
                CapabilityResolution(capabilityId=CAP_CORRESPONDENCE, source="Artifact"),
                CapabilityResolution(capabilityId=CAP_CONTINUOUS_ERROR, source="Evaluator"),
            ]
        )
        if artifact.collision_context is not None:
            resolved.append(CapabilityResolution(capabilityId=CAP_COLLISION_CONTEXT, source="Profile"))
            resolved.append(CapabilityResolution(capabilityId=CAP_PROCESS_STATE, source="Artifact"))
            resolved.append(CapabilityResolution(capabilityId=CAP_TASK_COLLISION, source="Evaluator"))
    if request.reference_path is not None:
        resolved.append(CapabilityResolution(capabilityId=CAP_CORRESPONDENCE, source="ReferenceBinding"))
    return resolved


def evaluate_five_axis_f1(
    request: FiveAxisF1EvaluationBindingRequest | dict[str, Any],
) -> EvaluationReport:
    resolved = request if isinstance(request, FiveAxisF1EvaluationBindingRequest) else FiveAxisF1EvaluationBindingRequest.model_validate(request)
    metric_ids = [item.metric_id for item in resolved.case.required_metrics + resolved.case.optional_metrics]
    needs_error = any(
        metric_id in {POSITION_MAX_ERROR_METRIC_ID, ORIENTATION_MAX_ERROR_METRIC_ID, GEOMETRY_VALID_METRIC_ID}
        for metric_id in metric_ids
    )
    needs_collision = any(
        metric_id in {TASK_COLLISION_FREE_METRIC_ID, TASK_OVERCUT_FREE_METRIC_ID, MINIMUM_CLEARANCE_METRIC_ID}
        for metric_id in metric_ids
    )
    error_certificate = _error_certificate(resolved) if needs_error else None
    collision_evaluation = None
    if needs_collision and isinstance(resolved.artifact, M2CandidateTaskGeometry):
        collision_evaluation = evaluate_task_collision(
            resolved.artifact,
            stock_state_geometries=resolved.stock_state_geometries,
        )

    raw_results = [
        _metric_result(resolved, metric_id, error_certificate, collision_evaluation)
        for metric_id in metric_ids
    ]
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
    reference_hash = (
        _content_hash(resolved.reference_path.model_dump(mode="json", by_alias=True, exclude_none=True))
        if resolved.reference_path is not None
        else None
    )
    provenance = Provenance(
        requestHash=_content_hash(request_payload),
        artifactHash=_content_hash(artifact_payload),
        caseHash=_content_hash(case_payload),
        referenceHash=reference_hash,
        referenceBindingHash=reference_hash,
        runnerId=F1_RUNNER_ID,
        evaluatorVersion=F1_EVALUATOR_ID,
        executionOutcomePolicy=resolved.case.execution_outcome_policy,
        numericEnvironment=current_f1_numeric_environment(),
    )
    failures = [
        DomainFailure(
            code=result.reason_code,
            message=f"F1 metric {result.metric_id} did not produce a closed positive result.",
            path=f"case.requiredMetrics[{index}]",
            severity="finding",
        )
        for index, result in enumerate(results[:required_count])
        if result.status is not MetricStatus.COMPUTED and result.reason_code is not None
    ]
    report_payload = {
        "executionStatus": ExecutionStatus.SUCCEEDED.value,
        "caseOutcome": case_outcome.value,
        "metricResults": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in results],
        "capabilities": [item.model_dump(mode="json", by_alias=True) for item in _capabilities(resolved)],
        "domainFailures": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in failures],
        "evaluatorVersion": F1_EVALUATOR_ID,
        "provenance": provenance.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    return EvaluationReport(**report_payload, contentHash=_content_hash(report_payload))


FIVE_AXIS_F1_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=FIVE_AXIS_F1_DOMAIN_PACK_ID,
        parse_request=_parse_f1_request,
        evaluate=evaluate_five_axis_f1,
    )
)


__all__ = [
    "F1_EVALUATOR_ID",
    "F1_RUNNER_ID",
    "FIVE_AXIS_F1_DOMAIN_PACK",
    "FIVE_AXIS_F1_DOMAIN_PACK_ID",
    "FIVE_AXIS_F1_RUNTIME_BINDING",
    "FiveAxisF1EvaluationBindingRequest",
    "GEOMETRY_VALID_CLAIM_ID",
    "GEOMETRY_VALID_METRIC_ID",
    "MINIMUM_CLEARANCE_METRIC_ID",
    "M0_VALID_METRIC_ID",
    "M1_VALID_METRIC_ID",
    "ORIENTATION_MAX_ERROR_METRIC_ID",
    "POSITION_MAX_ERROR_METRIC_ID",
    "TASK_COLLISION_FREE_CLAIM_ID",
    "TASK_COLLISION_FREE_METRIC_ID",
    "TASK_OVERCUT_FREE_METRIC_ID",
    "current_f1_numeric_environment",
    "evaluate_five_axis_f1",
]
