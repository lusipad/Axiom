from __future__ import annotations

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
from .f3_models import ContinuousTrajectoryVerification, M4ContinuousTrajectory
from .f3_sampling import (
    M5DiscreteCommand,
    M5SampledTrajectory,
    M5VerificationResult,
    verify_interval_reconstruction,
)
from .f3_timing import verify_continuous_trajectory


FIVE_AXIS_F3_DOMAIN_PACK_ID = "five-axis.domain-pack@4"
F3_EVALUATOR_ID = "five-axis-f3-evaluator@1"
F3_RUNNER_ID = ARTIFACT_IMPORT_RUNNER_ID

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


F3Artifact = Annotated[
    M4ContinuousTrajectory | M5SampledTrajectory | M5DiscreteCommand,
    Field(discriminator="artifact_type"),
]


class FiveAxisF3EvaluationBindingRequest(AxiomModel):
    artifact: F3Artifact
    case: EvaluationCase


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


FIVE_AXIS_F3_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=FIVE_AXIS_F3_DOMAIN_PACK_ID,
        artifactType="five-axis.m5-sampled-trajectory",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="five-axis.m4-continuous-trajectory",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m5-sampled-trajectory",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m5-discrete-command",
                schemaVersion=1,
                role="run-input",
            ),
        ),
        evaluatorVersion=F3_EVALUATOR_ID,
        runnerId=F3_RUNNER_ID,
        runnerIds=(F3_RUNNER_ID,),
        capabilityIds=(
            CAP_PATH_PROGRESS,
            CAP_REGULARITY,
            CAP_MOTION_CONSTRAINT_PROFILE,
            CAP_TIME_LAW,
            CAP_RECONSTRUCTION,
        ),
        metricDefinitions=(
            MetricDefinition(
                metricId=CONTINUOUSLY_FEASIBLE_METRIC_ID,
                metricDefinitionId=CONTINUOUSLY_FEASIBLE_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MOTION_CONSTRAINT_PROFILE, CAP_TIME_LAW),
                claimDefinitionId=CONTINUOUSLY_FEASIBLE_CLAIM_ID,
                claimPredicate="five-axis.ContinuouslyFeasible is true",
            ),
            MetricDefinition(
                metricId=TRAJECTORY_DURATION_METRIC_ID,
                metricDefinitionId=TRAJECTORY_DURATION_METRIC_ID,
                requires=(CAP_TIME_LAW,),
                direction="lower-is-better",
                numericTolerance=DomainNumericTolerance(absolute=1e-12, relative=1e-12, unit="s"),
            ),
            MetricDefinition(
                metricId=AXIS_VELOCITY_UTILIZATION_MAX_METRIC_ID,
                metricDefinitionId=AXIS_VELOCITY_UTILIZATION_MAX_METRIC_ID,
                requires=(CAP_MOTION_CONSTRAINT_PROFILE, CAP_TIME_LAW),
                direction="lower-is-better",
            ),
            MetricDefinition(
                metricId=AXIS_ACCELERATION_UTILIZATION_MAX_METRIC_ID,
                metricDefinitionId=AXIS_ACCELERATION_UTILIZATION_MAX_METRIC_ID,
                requires=(CAP_MOTION_CONSTRAINT_PROFILE, CAP_TIME_LAW),
                direction="lower-is-better",
            ),
            MetricDefinition(
                metricId=AXIS_JERK_UTILIZATION_MAX_METRIC_ID,
                metricDefinitionId=AXIS_JERK_UTILIZATION_MAX_METRIC_ID,
                requires=(CAP_MOTION_CONSTRAINT_PROFILE, CAP_TIME_LAW),
                direction="lower-is-better",
            ),
            MetricDefinition(
                metricId=INTERVAL_CERTIFIED_METRIC_ID,
                metricDefinitionId=INTERVAL_CERTIFIED_METRIC_ID,
                requires=(CAP_TIME_LAW, CAP_RECONSTRUCTION),
                claimDefinitionId=INTERVAL_CERTIFIED_CLAIM_ID,
                claimPredicate="five-axis.IntervalCertified is true",
            ),
            MetricDefinition(
                metricId=SAMPLE_COUNT_METRIC_ID,
                metricDefinitionId=SAMPLE_COUNT_METRIC_ID,
                requires=(CAP_RECONSTRUCTION,),
                direction="lower-is-better",
            ),
            MetricDefinition(
                metricId=SAMPLE_PERIOD_METRIC_ID,
                metricDefinitionId=SAMPLE_PERIOD_METRIC_ID,
                requires=(CAP_RECONSTRUCTION,),
                numericTolerance=DomainNumericTolerance(absolute=1e-15, relative=1e-12, unit="s"),
            ),
            MetricDefinition(
                metricId=RECONSTRUCTION_POSITION_ERROR_MAX_METRIC_ID,
                metricDefinitionId=RECONSTRUCTION_POSITION_ERROR_MAX_METRIC_ID,
                requires=(CAP_RECONSTRUCTION,),
                direction="lower-is-better",
                numericTolerance=DomainNumericTolerance(absolute=1e-12, relative=1e-12, unit="mm"),
            ),
            MetricDefinition(
                metricId=RECONSTRUCTION_ORIENTATION_ERROR_MAX_METRIC_ID,
                metricDefinitionId=RECONSTRUCTION_ORIENTATION_ERROR_MAX_METRIC_ID,
                requires=(CAP_RECONSTRUCTION,),
                direction="lower-is-better",
                numericTolerance=DomainNumericTolerance(absolute=1e-15, relative=1e-12, unit="rad"),
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            CONTINUOUSLY_FEASIBLE_CLAIM_ID,
            INTERVAL_CERTIFIED_CLAIM_ID,
        ),
        comparisonPolicyIds=(),
        failureMappings=_FAILURE_MAPPINGS,
    )
)


def current_f3_numeric_environment() -> dict[str, str]:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "numpy": package_version("numpy"),
        "scipy": package_version("scipy"),
        "pydantic": package_version("pydantic"),
    }


def _parse_f3_request(request: CoreEvaluationRequest) -> FiveAxisF3EvaluationBindingRequest:
    return FiveAxisF3EvaluationBindingRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _definition(metric_id: str) -> MetricDefinition | None:
    try:
        return FIVE_AXIS_F3_DOMAIN_PACK.metric_definition(metric_id)
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


def _m4_from_artifact(artifact: F3Artifact) -> M4ContinuousTrajectory:
    if isinstance(artifact, M4ContinuousTrajectory):
        return artifact
    return artifact.source_m4


def _m5_verification(artifact: F3Artifact) -> M5VerificationResult | None:
    if isinstance(artifact, M4ContinuousTrajectory):
        return None
    return verify_interval_reconstruction(artifact)


def _evaluation_verifications(
    artifact: F3Artifact,
) -> tuple[ContinuousTrajectoryVerification, M5VerificationResult | None]:
    return verify_continuous_trajectory(_m4_from_artifact(artifact)), _m5_verification(artifact)


def _continuous_metric(verification: ContinuousTrajectoryVerification) -> MetricResult:
    details = {"verification": verification.model_dump(mode="json", by_alias=True, exclude_none=True)}
    if verification.overall_status == "Supported":
        return _computed(
            CONTINUOUSLY_FEASIBLE_METRIC_ID,
            True,
            level=verification.evidence_level,
            method=verification.solver_id,
            details=details,
        )
    if verification.overall_status == "Refuted":
        return _computed(
            CONTINUOUSLY_FEASIBLE_METRIC_ID,
            False,
            level=verification.evidence_level,
            method=verification.solver_id,
            reason_code="ContinuousTrajectoryConstraintRefuted",
            details=details,
        )
    return _unavailable(
        CONTINUOUSLY_FEASIBLE_METRIC_ID,
        MetricStatus.UNSUPPORTED_CAPABILITY,
        "ContinuousTrajectoryVerificationUnsupported",
        **details,
    )


def _duration_metric(verification: ContinuousTrajectoryVerification) -> MetricResult:
    return _computed(
        TRAJECTORY_DURATION_METRIC_ID,
        verification.total_duration_seconds,
        unit="s",
        level=verification.evidence_level,
        method=verification.solver_id,
        details={"optimality": verification.optimality.model_dump(mode="json", by_alias=True, exclude_none=True)},
    )


def _utilization_metric(
    verification: ContinuousTrajectoryVerification,
    metric_id: str,
) -> MetricResult:
    usage = verification.axis_constraint_usage
    if metric_id == AXIS_VELOCITY_UTILIZATION_MAX_METRIC_ID:
        ratios = [item.maximum_velocity / item.velocity_limit for item in usage]
        quantity = "velocity"
    elif metric_id == AXIS_ACCELERATION_UTILIZATION_MAX_METRIC_ID:
        ratios = [item.maximum_acceleration / item.acceleration_limit for item in usage]
        quantity = "acceleration"
    else:
        pairs = [
            (item.maximum_jerk, item.jerk_limit)
            for item in usage
            if item.maximum_jerk is not None and item.jerk_limit is not None
        ]
        if not pairs:
            return _unavailable(
                metric_id,
                MetricStatus.NOT_APPLICABLE,
                "JerkNotRequestedByMotionConstraintProfile",
            )
        ratios = [observed / limit for observed, limit in pairs]
        quantity = "jerk"
    if not ratios:
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "AxisConstraintUsageMissing")
    return _computed(
        metric_id,
        max(ratios),
        unit="dimensionless",
        level=verification.evidence_level,
        method=verification.solver_id,
        details={
            "quantity": quantity,
            "axisConstraintUsage": [
                item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in usage
            ],
        },
    )


def _interval_reason(verification: M5VerificationResult) -> str:
    result = next(
        (item for item in verification.quantities if item.quantity == "interval-certified"),
        None,
    )
    return result.reason_code if result and result.reason_code else "IntervalReconstructionVerificationUnsupported"


def _interval_metric(
    verification: M5VerificationResult | None,
    continuous: ContinuousTrajectoryVerification,
) -> MetricResult:
    if verification is None:
        return _unavailable(
            INTERVAL_CERTIFIED_METRIC_ID,
            MetricStatus.NOT_APPLICABLE,
            "MetricOutsideArtifactDomain",
        )
    details = {
        "continuousVerification": continuous.model_dump(mode="json", by_alias=True, exclude_none=True),
        "reconstructionVerification": verification.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    if continuous.overall_status != "Supported":
        return _unavailable(
            INTERVAL_CERTIFIED_METRIC_ID,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            "SourceContinuousTrajectoryNotSupported",
            **details,
        )
    if verification.status == "Supported":
        return _computed(
            INTERVAL_CERTIFIED_METRIC_ID,
            True,
            level=verification.evidence_level,
            method=verification.method,
            details=details,
        )
    if verification.status == "Refuted":
        return _computed(
            INTERVAL_CERTIFIED_METRIC_ID,
            False,
            level=verification.evidence_level,
            method=verification.method,
            reason_code=_interval_reason(verification),
            details=details,
        )
    return _unavailable(
        INTERVAL_CERTIFIED_METRIC_ID,
        MetricStatus.UNSUPPORTED_CAPABILITY,
        _interval_reason(verification),
        **details,
    )


def _sample_metric(artifact: F3Artifact, metric_id: str) -> MetricResult:
    if isinstance(artifact, M4ContinuousTrajectory):
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MetricOutsideArtifactDomain")
    if metric_id == SAMPLE_COUNT_METRIC_ID:
        return _computed(
            metric_id,
            len(artifact.samples),
            unit="count",
            level="Exact",
            method="five-axis.f3.fixed-period-schedule-replay@1",
        )
    return _computed(
        metric_id,
        artifact.sample_period,
        unit="s",
        level="Exact",
        method="five-axis.f3.fixed-period-schedule-replay@1",
        details={
            "remainderDuration": artifact.remainder_duration,
            "terminalSampleIncluded": artifact.terminal_sample_included,
            "finalHold": artifact.final_hold,
        },
    )


def _reconstruction_error_metric(
    verification: M5VerificationResult | None,
    metric_id: str,
) -> MetricResult:
    if verification is None:
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MetricOutsideArtifactDomain")
    quantity = "position" if metric_id == RECONSTRUCTION_POSITION_ERROR_MAX_METRIC_ID else "orientation"
    matches = [item for item in verification.error_ledger if item.quantity == quantity]
    if not matches:
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "ReconstructionErrorQuantityUnavailable")
    unit = "mm" if quantity == "position" else "rad"
    return _computed(
        metric_id,
        max(item.bound for item in matches),
        unit=unit,
        level="Validated",
        method="five-axis.f3.reconstruction-midpoint-cross-check@1",
        details={
            "entries": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in matches]
        },
    )


def _metric_result(
    request: FiveAxisF3EvaluationBindingRequest,
    metric_id: str,
    *,
    continuous_verification: ContinuousTrajectoryVerification,
    reconstruction_verification: M5VerificationResult | None,
) -> MetricResult:
    artifact = request.artifact
    if metric_id == CONTINUOUSLY_FEASIBLE_METRIC_ID:
        return _continuous_metric(continuous_verification)
    if metric_id == TRAJECTORY_DURATION_METRIC_ID:
        return _duration_metric(continuous_verification)
    if metric_id in {
        AXIS_VELOCITY_UTILIZATION_MAX_METRIC_ID,
        AXIS_ACCELERATION_UTILIZATION_MAX_METRIC_ID,
        AXIS_JERK_UTILIZATION_MAX_METRIC_ID,
    }:
        return _utilization_metric(continuous_verification, metric_id)
    if metric_id == INTERVAL_CERTIFIED_METRIC_ID:
        return _interval_metric(reconstruction_verification, continuous_verification)
    if metric_id in {SAMPLE_COUNT_METRIC_ID, SAMPLE_PERIOD_METRIC_ID}:
        return _sample_metric(artifact, metric_id)
    if metric_id in {
        RECONSTRUCTION_POSITION_ERROR_MAX_METRIC_ID,
        RECONSTRUCTION_ORIENTATION_ERROR_MAX_METRIC_ID,
    }:
        return _reconstruction_error_metric(reconstruction_verification, metric_id)
    return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "MetricNotImplementedInF3")


def _capabilities(
    request: FiveAxisF3EvaluationBindingRequest,
    *,
    continuous_verification: ContinuousTrajectoryVerification,
) -> list[CapabilityResolution]:
    artifact = request.artifact
    resolved = [
        CapabilityResolution(capabilityId=CAP_PATH_PROGRESS, source="Artifact"),
        CapabilityResolution(capabilityId=CAP_REGULARITY, source="Artifact"),
        CapabilityResolution(capabilityId=CAP_MOTION_CONSTRAINT_PROFILE, source="Profile"),
    ]
    if continuous_verification.overall_status == "Supported":
        resolved.append(CapabilityResolution(capabilityId=CAP_TIME_LAW, source="Evaluator"))
    if not isinstance(artifact, M4ContinuousTrajectory):
        resolved.append(CapabilityResolution(capabilityId=CAP_RECONSTRUCTION, source="Evaluator"))
    return resolved


def evaluate_five_axis_f3(
    request: FiveAxisF3EvaluationBindingRequest | dict[str, Any],
) -> EvaluationReport:
    resolved = (
        request
        if isinstance(request, FiveAxisF3EvaluationBindingRequest)
        else FiveAxisF3EvaluationBindingRequest.model_validate(request)
    )
    continuous_verification, reconstruction_verification = _evaluation_verifications(resolved.artifact)
    metric_ids = [item.metric_id for item in resolved.case.required_metrics + resolved.case.optional_metrics]
    raw_results = [
        _metric_result(
            resolved,
            metric_id,
            continuous_verification=continuous_verification,
            reconstruction_verification=reconstruction_verification,
        )
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
    provenance = Provenance(
        requestHash=_content_hash(request_payload),
        artifactHash=_content_hash(artifact_payload),
        caseHash=_content_hash(case_payload),
        runnerId=F3_RUNNER_ID,
        evaluatorVersion=F3_EVALUATOR_ID,
        executionOutcomePolicy=resolved.case.execution_outcome_policy,
        numericEnvironment=current_f3_numeric_environment(),
    )
    failures = [
        DomainFailure(
            code=result.reason_code,
            message=f"F3 metric {result.metric_id} did not produce a closed result.",
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
        capabilities=_capabilities(
            resolved,
            continuous_verification=continuous_verification,
        ),
        domainFailures=failures,
        evaluatorVersion=F3_EVALUATOR_ID,
        provenance=provenance,
        contentHash="",
    )
    return _seal_evaluation_report(report)


FIVE_AXIS_F3_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=FIVE_AXIS_F3_DOMAIN_PACK_ID,
        parse_request=_parse_f3_request,
        evaluate=evaluate_five_axis_f3,
    )
)


__all__ = [
    "AXIS_ACCELERATION_UTILIZATION_MAX_METRIC_ID",
    "AXIS_JERK_UTILIZATION_MAX_METRIC_ID",
    "AXIS_VELOCITY_UTILIZATION_MAX_METRIC_ID",
    "CAP_MOTION_CONSTRAINT_PROFILE",
    "CAP_RECONSTRUCTION",
    "CAP_TIME_LAW",
    "CONTINUOUSLY_FEASIBLE_CLAIM_ID",
    "CONTINUOUSLY_FEASIBLE_METRIC_ID",
    "F3_EVALUATOR_ID",
    "F3_RUNNER_ID",
    "FIVE_AXIS_F3_DOMAIN_PACK",
    "FIVE_AXIS_F3_DOMAIN_PACK_ID",
    "FIVE_AXIS_F3_RUNTIME_BINDING",
    "FiveAxisF3EvaluationBindingRequest",
    "INTERVAL_CERTIFIED_CLAIM_ID",
    "INTERVAL_CERTIFIED_METRIC_ID",
    "RECONSTRUCTION_ORIENTATION_ERROR_MAX_METRIC_ID",
    "RECONSTRUCTION_POSITION_ERROR_MAX_METRIC_ID",
    "SAMPLE_COUNT_METRIC_ID",
    "SAMPLE_PERIOD_METRIC_ID",
    "TRAJECTORY_DURATION_METRIC_ID",
    "current_f3_numeric_environment",
    "evaluate_five_axis_f3",
]
