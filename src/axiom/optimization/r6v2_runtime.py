from __future__ import annotations

import platform
from importlib.metadata import version as package_version
from typing import Any

from ..domain import (
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    ArtifactTypeDescriptor,
    DomainPack,
    FailureMapping,
    MetricDefinition,
    NumericTolerance,
    register_domain_pack,
)
from ..evaluator import (
    _aggregate_outcome,
    _apply_threshold,
    _content_hash,
    _seal_evaluation_report,
)
from ..models import (
    CapabilityResolution,
    CaseOutcome,
    CoreEvaluationRequest,
    DomainFailure,
    EvaluationReport,
    Evidence,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Provenance,
)
from ..runtime import DomainRuntimeBinding, register_domain_runtime_binding
from .r6v2_models import (
    R6V2_DOMAIN_PACK_ID,
    R6V2_EVALUATOR_ID,
    R6V2_RUNNER_ID,
    R6V2EvaluationRequest,
)
from .r6v2_search import search_r6v2_recommendations

SCREENING_CONTRACT_METRIC_ID = "optimization.surrogate-screening-contract@1"
EXACT_INTEGRITY_METRIC_ID = "optimization.exact-recommendation-integrity@2"
EXACT_VALIDATION_COUNT_METRIC_ID = "optimization.exact-validation-count@2"
EXACT_FEASIBLE_COUNT_METRIC_ID = "optimization.exact-feasible-candidate-count@2"
OFFLINE_BOUNDARY_METRIC_ID = "optimization.offline-permission-boundary@2"
REALITY_VALIDATION_METRIC_ID = "optimization.reality-validation@2"

SCREENING_CONTRACT_CLAIM_ID = (
    "optimization.surrogate-screening-contract-claim@1"
)
EXACT_INTEGRITY_CLAIM_ID = (
    "optimization.exact-recommendation-integrity-claim@2"
)
OFFLINE_BOUNDARY_CLAIM_ID = (
    "optimization.offline-permission-boundary-claim@2"
)
REALITY_VALIDATION_CLAIM_ID = "optimization.reality-validation-claim@2"

SURROGATE_SCREENING_CAPABILITY_ID = "optimization.r5c-surrogate-screening@1"
EXACT_REPLAY_CAPABILITY_ID = "optimization.f3-f4-r4-exact-replay@2"
TARGET_CONSTRAINT_CAPABILITY_ID = "optimization.explicit-epsilon-constraints@1"
OFFLINE_PERMISSION_CAPABILITY_ID = "optimization.offline-permission@2"


def _metric(
    metric_id: str,
    *,
    requires: tuple[str, ...],
    claim_id: str | None = None,
    predicate: str | None = None,
    direction: str | None = None,
    unit: str | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=requires,
        claimDefinitionId=claim_id,
        claimPredicate=predicate,
        direction=direction,
        numericTolerance=(
            NumericTolerance(absolute=0.0, relative=0.0, unit=unit)
            if direction is not None
            else None
        ),
    )


R6V2_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R6V2_DOMAIN_PACK_ID,
        artifactType="axiom.optimization.recommendation-set",
        artifactSchemaVersions=(2,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.optimization.recommendation-set",
                schemaVersion=2,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.optimization.surrogate-screening-receipt",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.conditional-effect-model-bundle",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.physical-multirate-applicability-evidence",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R6V2_EVALUATOR_ID,
        runnerId=R6V2_RUNNER_ID,
        runnerIds=(R6V2_RUNNER_ID,),
        capabilityIds=(
            SURROGATE_SCREENING_CAPABILITY_ID,
            EXACT_REPLAY_CAPABILITY_ID,
            TARGET_CONSTRAINT_CAPABILITY_ID,
            OFFLINE_PERMISSION_CAPABILITY_ID,
        ),
        metricDefinitions=(
            _metric(
                SCREENING_CONTRACT_METRIC_ID,
                requires=(SURROGATE_SCREENING_CAPABILITY_ID,),
                claim_id=SCREENING_CONTRACT_CLAIM_ID,
                predicate=(
                    "The R5-C surrogate screens the frozen 135-point grid and "
                    "selects no more than 27 candidates without making a final "
                    "recommendation."
                ),
            ),
            _metric(
                EXACT_INTEGRITY_METRIC_ID,
                requires=(EXACT_REPLAY_CAPABILITY_ID,),
                claim_id=EXACT_INTEGRITY_CLAIM_ID,
                predicate=(
                    "Every recommendation is backed by exact F3/F4/R4 replay and "
                    "satisfies the declared target constraints."
                ),
            ),
            _metric(
                EXACT_VALIDATION_COUNT_METRIC_ID,
                requires=(EXACT_REPLAY_CAPABILITY_ID,),
                direction="lower-is-better",
                unit="count",
            ),
            _metric(
                EXACT_FEASIBLE_COUNT_METRIC_ID,
                requires=(
                    EXACT_REPLAY_CAPABILITY_ID,
                    TARGET_CONSTRAINT_CAPABILITY_ID,
                ),
                direction="higher-is-better",
                unit="count",
            ),
            _metric(
                OFFLINE_BOUNDARY_METRIC_ID,
                requires=(OFFLINE_PERMISSION_CAPABILITY_ID,),
                claim_id=OFFLINE_BOUNDARY_CLAIM_ID,
                predicate=(
                    "Search and validation remain Offline with no device write, "
                    "automatic acceptance, or promotion permission."
                ),
            ),
            _metric(
                REALITY_VALIDATION_METRIC_ID,
                requires=("optimization.real-device-holdout@2",),
                claim_id=REALITY_VALIDATION_CLAIM_ID,
                predicate=(
                    "The recommendation is validated by an independent real-device "
                    "holdout for this case."
                ),
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            SCREENING_CONTRACT_CLAIM_ID,
            EXACT_INTEGRITY_CLAIM_ID,
            OFFLINE_BOUNDARY_CLAIM_ID,
            REALITY_VALIDATION_CLAIM_ID,
        ),
        comparisonPolicyIds=(),
        failureMappings=(
            FailureMapping(
                code="MalformedEvaluationRequest",
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
        ),
    )
)


_METRIC_IDS = (
    SCREENING_CONTRACT_METRIC_ID,
    EXACT_INTEGRITY_METRIC_ID,
    EXACT_VALIDATION_COUNT_METRIC_ID,
    EXACT_FEASIBLE_COUNT_METRIC_ID,
    OFFLINE_BOUNDARY_METRIC_ID,
    REALITY_VALIDATION_METRIC_ID,
)


def _parse_request(request: CoreEvaluationRequest) -> R6V2EvaluationRequest:
    return R6V2EvaluationRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _computed(
    metric_id: str,
    value: Any,
    *,
    unit: str | None = None,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    definition = R6V2_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=MetricStatus.COMPUTED,
        value=value,
        unit=unit,
        details=details or {},
        evidence=Evidence(
            level="Observed", method=f"{metric_id}.deterministic-windows-replay@1"
        ),
    )


def _unavailable(
    metric_id: str, status: MetricStatus, reason_code: str, **details: Any
) -> MetricResult:
    definition = R6V2_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=status,
        reasonCode=reason_code,
        details=details,
        evidence=Evidence(level="Observed", method=f"{metric_id}.boundary@1"),
    )


def _provenance(request: R6V2EvaluationRequest) -> Provenance:
    artifact = request.artifact
    surrogate = request.search_spec.surrogate_context
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(artifact),
        caseHash=_content_hash(request.case),
        runnerId=R6V2_RUNNER_ID,
        evaluatorVersion=R6V2_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment={
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "pydantic": package_version("pydantic"),
        },
        contextHashes={
            "searchSpec": _content_hash(request.search_spec),
            "surrogateContext": surrogate.context_hash,
            "r5cModelBundle": surrogate.model_bundle.content_hash,
            "r5cTrainingReceipt": surrogate.training_receipt.content_hash,
            "r5cParityReceipt": surrogate.parity_receipt.content_hash,
            "screeningReceipt": artifact.screening_receipt.content_hash,
            "physicalApplicabilityEvidence": (
                artifact.physical_applicability_evidence.content_hash
            ),
        },
    )


def _invalid_report(
    request: R6V2EvaluationRequest, reason_code: str
) -> EvaluationReport:
    results = [
        _unavailable(metric_id, MetricStatus.INVALID_OBSERVATION, reason_code)
        for metric_id in _METRIC_IDS
    ]
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SKIPPED,
            caseOutcome=CaseOutcome.INVALID,
            metricResults=results,
            domainFailures=[
                DomainFailure(
                    code=reason_code,
                    message="R6 v2 RecommendationSet failed deterministic replay.",
                    path="request.artifact",
                )
            ],
            contentHash="",
            evaluatorVersion=R6V2_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


def evaluate_optimization_r6v2(
    request: R6V2EvaluationRequest,
) -> EvaluationReport:
    if platform.system() != "Windows":
        results = [
            _unavailable(
                metric_id,
                MetricStatus.UNSUPPORTED_CAPABILITY,
                "UnsupportedRuntimePlatform",
                currentPlatform=platform.system(),
                supportedPlatforms=["Windows"],
            )
            for metric_id in _METRIC_IDS
        ]
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.UNSUPPORTED,
                metricResults=results,
                contentHash="",
                evaluatorVersion=R6V2_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay = search_r6v2_recommendations(request.search_spec)
    if replay != request.artifact:
        return _invalid_report(request, "RecommendationReplayMismatch")

    screening = replay.screening_receipt
    exact = replay.exact_candidates
    eligible = [item for item in exact if item.recommendation_eligible]
    exact_integrity = (
        len(exact) == screening.selected_count
        and len(exact) <= replay.exact_validation_budget
        and all(
            item.hard_constraints_satisfied and item.exact_constraints_satisfied
            for item in exact
            if item.recommendation_eligible
        )
        and bool(replay.best_observed_candidate_ids)
    )
    permission_boundary = (
        replay.permission_level == "Offline"
        and not replay.device_write_allowed
        and not replay.automatic_acceptance_allowed
        and replay.global_optimality_status == "NotClaimed"
        and all(not item.device_write_allowed for item in exact)
        and all(not item.promotion_eligible for item in exact)
    )
    feasible_metric = (
        _computed(
            EXACT_FEASIBLE_COUNT_METRIC_ID,
            len(eligible),
            unit="count",
            details={"bestObservedCandidateIds": list(replay.best_observed_candidate_ids)},
        )
        if eligible
        else _unavailable(
            EXACT_FEASIBLE_COUNT_METRIC_ID,
            MetricStatus.INSUFFICIENT_CONTEXT,
            "NoExactlyValidatedFeasibleCandidate",
            exactValidationCount=len(exact),
        )
    )
    evaluated = {
        SCREENING_CONTRACT_METRIC_ID: _computed(
            SCREENING_CONTRACT_METRIC_ID,
            (
                screening.candidate_count == replay.screening_candidate_count
                and screening.selected_count <= replay.exact_validation_budget
                and screening.model_bundle_hash
                == request.search_spec.surrogate_context.model_bundle.content_hash
            ),
            details={
                "screeningCandidateCount": screening.candidate_count,
                "possiblyFeasibleCount": screening.possibly_feasible_count,
                "selectedForExactValidationCount": screening.selected_count,
                "exactValidationBudget": replay.exact_validation_budget,
            },
        ),
        EXACT_INTEGRITY_METRIC_ID: _computed(
            EXACT_INTEGRITY_METRIC_ID,
            exact_integrity,
            details={
                "exactValidationCount": len(exact),
                "exactFeasibleCount": len(eligible),
                "optimalityScope": replay.optimality_scope,
                "globalOptimalityStatus": replay.global_optimality_status,
            },
        ),
        EXACT_VALIDATION_COUNT_METRIC_ID: _computed(
            EXACT_VALIDATION_COUNT_METRIC_ID,
            len(exact),
            unit="count",
            details={"exactValidationBudget": replay.exact_validation_budget},
        ),
        EXACT_FEASIBLE_COUNT_METRIC_ID: feasible_metric,
        OFFLINE_BOUNDARY_METRIC_ID: _computed(
            OFFLINE_BOUNDARY_METRIC_ID,
            permission_boundary,
            details={
                "permissionLevel": replay.permission_level,
                "deviceWriteAllowed": replay.device_write_allowed,
                "automaticAcceptanceAllowed": replay.automatic_acceptance_allowed,
                "realityValidationStatus": replay.reality_validation_status,
            },
        ),
        REALITY_VALIDATION_METRIC_ID: _unavailable(
            REALITY_VALIDATION_METRIC_ID,
            MetricStatus.INSUFFICIENT_CONTEXT,
            "RealDeviceHoldoutMissing",
            realityValidationStatus="Open",
        ),
    }
    requested = request.case.required_metrics + request.case.optional_metrics
    results = [
        _apply_threshold(evaluated[item.metric_id], item.threshold)
        for item in requested
    ]
    required = results[: len(request.case.required_metrics)]
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(required),
            metricResults=results,
            capabilities=(
                CapabilityResolution(
                    capabilityId=SURROGATE_SCREENING_CAPABILITY_ID,
                    source="Evaluator",
                ),
                CapabilityResolution(
                    capabilityId=EXACT_REPLAY_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=TARGET_CONSTRAINT_CAPABILITY_ID, source="Profile"
                ),
                CapabilityResolution(
                    capabilityId=OFFLINE_PERMISSION_CAPABILITY_ID, source="Profile"
                ),
            ),
            contentHash="",
            evaluatorVersion=R6V2_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R6V2_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R6V2_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_optimization_r6v2,
    )
)


__all__ = [
    "EXACT_FEASIBLE_COUNT_METRIC_ID",
    "EXACT_INTEGRITY_CLAIM_ID",
    "EXACT_INTEGRITY_METRIC_ID",
    "EXACT_VALIDATION_COUNT_METRIC_ID",
    "OFFLINE_BOUNDARY_CLAIM_ID",
    "OFFLINE_BOUNDARY_METRIC_ID",
    "R6V2_DOMAIN_PACK",
    "R6V2_RUNTIME_BINDING",
    "REALITY_VALIDATION_CLAIM_ID",
    "REALITY_VALIDATION_METRIC_ID",
    "SCREENING_CONTRACT_CLAIM_ID",
    "SCREENING_CONTRACT_METRIC_ID",
    "evaluate_optimization_r6v2",
]
