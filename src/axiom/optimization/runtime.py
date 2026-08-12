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
from .models import (
    R6_DOMAIN_PACK_ID,
    R6_EVALUATOR_ID,
    R6_RUNNER_ID,
    OptimizationEvaluationRequest,
)
from .search import search_recommendations

INTEGRITY_METRIC_ID = "optimization.recommendation-integrity@1"
HARD_CONSTRAINT_METRIC_ID = "optimization.hard-constraints-respected@1"
PARETO_COUNT_METRIC_ID = "optimization.pareto-candidate-count@1"
OFFLINE_BOUNDARY_METRIC_ID = "optimization.offline-permission-boundary@1"
REALITY_VALIDATION_METRIC_ID = "optimization.reality-validation@1"

INTEGRITY_CLAIM_ID = "optimization.recommendation-integrity-claim@1"
HARD_CONSTRAINT_CLAIM_ID = "optimization.hard-constraints-respected-claim@1"
RECOMMENDATION_AVAILABLE_CLAIM_ID = "optimization.recommendation-available-claim@1"
OFFLINE_BOUNDARY_CLAIM_ID = "optimization.offline-permission-boundary-claim@1"
REALITY_VALIDATION_CLAIM_ID = "optimization.reality-validation-claim@1"

SEARCH_CAPABILITY_ID = "optimization.deterministic-grid-search@1"
PARETO_CAPABILITY_ID = "optimization.unweighted-pareto@1"
MATH_GATE_CAPABILITY_ID = "optimization.f4-math-gate-replay@1"
PHYSICAL_CAPABILITY_ID = "optimization.r4-multirate-applicability@1"
EPISTEMIC_CAPABILITY_ID = "optimization.r5-ood-annotation@1"
OFFLINE_PERMISSION_CAPABILITY_ID = "optimization.offline-permission@1"


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


R6_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R6_DOMAIN_PACK_ID,
        artifactType="axiom.optimization.recommendation-set",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.optimization.recommendation-set",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.physical-multirate-applicability-evidence",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R6_EVALUATOR_ID,
        runnerId=R6_RUNNER_ID,
        runnerIds=(R6_RUNNER_ID,),
        capabilityIds=(
            SEARCH_CAPABILITY_ID,
            PARETO_CAPABILITY_ID,
            MATH_GATE_CAPABILITY_ID,
            PHYSICAL_CAPABILITY_ID,
            EPISTEMIC_CAPABILITY_ID,
            OFFLINE_PERMISSION_CAPABILITY_ID,
        ),
        metricDefinitions=(
            _metric(
                INTEGRITY_METRIC_ID,
                requires=(
                    SEARCH_CAPABILITY_ID,
                    MATH_GATE_CAPABILITY_ID,
                    PHYSICAL_CAPABILITY_ID,
                ),
                claim_id=INTEGRITY_CLAIM_ID,
                predicate="RecommendationSet content and deterministic replay identities match.",
            ),
            _metric(
                HARD_CONSTRAINT_METRIC_ID,
                requires=(MATH_GATE_CAPABILITY_ID, PHYSICAL_CAPABILITY_ID),
                claim_id=HARD_CONSTRAINT_CLAIM_ID,
                predicate="Every emitted R6 candidate satisfies the seven math gates and physical applicability.",
            ),
            _metric(
                PARETO_COUNT_METRIC_ID,
                requires=(SEARCH_CAPABILITY_ID, PARETO_CAPABILITY_ID),
                claim_id=RECOMMENDATION_AVAILABLE_CLAIM_ID,
                predicate="At least one hard-safe goal-feasible Pareto candidate is available.",
                direction="higher-is-better",
                unit="count",
            ),
            _metric(
                OFFLINE_BOUNDARY_METRIC_ID,
                requires=(OFFLINE_PERMISSION_CAPABILITY_ID,),
                claim_id=OFFLINE_BOUNDARY_CLAIM_ID,
                predicate="Recommendation permissions remain Offline with no device write or automatic acceptance.",
            ),
            _metric(
                REALITY_VALIDATION_METRIC_ID,
                requires=("optimization.real-device-holdout@1",),
                claim_id=REALITY_VALIDATION_CLAIM_ID,
                predicate="Recommendation is validated by independent real-device holdout evidence.",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            INTEGRITY_CLAIM_ID,
            HARD_CONSTRAINT_CLAIM_ID,
            RECOMMENDATION_AVAILABLE_CLAIM_ID,
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


def _parse_request(request: CoreEvaluationRequest) -> OptimizationEvaluationRequest:
    return OptimizationEvaluationRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _computed(
    metric_id: str,
    value: Any,
    *,
    unit: str | None = None,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    definition = R6_DOMAIN_PACK.metric_definition(metric_id)
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
    definition = R6_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=status,
        reasonCode=reason_code,
        details=details,
        evidence=Evidence(level="Observed", method=f"{metric_id}.boundary@1"),
    )


def _provenance(request: OptimizationEvaluationRequest) -> Provenance:
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=R6_RUNNER_ID,
        evaluatorVersion=R6_EVALUATOR_ID,
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
            "physicalApplicabilityEvidence": request.artifact.physical_applicability_evidence.content_hash,
        },
    )


def _invalid_report(
    request: OptimizationEvaluationRequest, reason_code: str
) -> EvaluationReport:
    results = [
        _unavailable(metric_id, MetricStatus.INVALID_OBSERVATION, reason_code)
        for metric_id in (
            INTEGRITY_METRIC_ID,
            HARD_CONSTRAINT_METRIC_ID,
            PARETO_COUNT_METRIC_ID,
            OFFLINE_BOUNDARY_METRIC_ID,
            REALITY_VALIDATION_METRIC_ID,
        )
    ]
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SKIPPED,
            caseOutcome=CaseOutcome.INVALID,
            metricResults=results,
            domainFailures=[
                DomainFailure(
                    code=reason_code,
                    message="RecommendationSet failed deterministic replay.",
                    path="request.artifact",
                )
            ],
            contentHash="",
            evaluatorVersion=R6_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


def evaluate_optimization(request: OptimizationEvaluationRequest) -> EvaluationReport:
    if platform.system() != "Windows":
        results = [
            _unavailable(
                metric_id,
                MetricStatus.UNSUPPORTED_CAPABILITY,
                "UnsupportedRuntimePlatform",
                currentPlatform=platform.system(),
                supportedPlatforms=["Windows"],
            )
            for metric_id in (
                INTEGRITY_METRIC_ID,
                HARD_CONSTRAINT_METRIC_ID,
                PARETO_COUNT_METRIC_ID,
                OFFLINE_BOUNDARY_METRIC_ID,
                REALITY_VALIDATION_METRIC_ID,
            )
        ]
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.UNSUPPORTED,
                metricResults=results,
                contentHash="",
                evaluatorVersion=R6_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay = search_recommendations(request.search_spec)
    if replay != request.artifact:
        return _invalid_report(request, "RecommendationReplayMismatch")

    permission_boundary = (
        replay.permission_level == "Offline"
        and not replay.device_write_allowed
        and not replay.automatic_acceptance_allowed
        and all(not candidate.device_write_allowed for candidate in replay.candidates)
        and all(not candidate.promotion_eligible for candidate in replay.candidates)
    )
    evaluated = {
        INTEGRITY_METRIC_ID: _computed(
            INTEGRITY_METRIC_ID,
            True,
            details={"recommendationSetContentHash": replay.content_hash},
        ),
        HARD_CONSTRAINT_METRIC_ID: _computed(
            HARD_CONSTRAINT_METRIC_ID,
            all(
                candidate.hard_constraints_satisfied for candidate in replay.candidates
            ),
            details={
                "candidateCount": len(replay.candidates),
                "gateCountPerCandidate": 7,
            },
        ),
        PARETO_COUNT_METRIC_ID: _computed(
            PARETO_COUNT_METRIC_ID,
            len(replay.pareto_candidate_ids),
            unit="count",
        ),
        OFFLINE_BOUNDARY_METRIC_ID: _computed(
            OFFLINE_BOUNDARY_METRIC_ID,
            permission_boundary,
            details={"permissionLevel": "Offline", "deviceWriteAllowed": False},
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
                    capabilityId=SEARCH_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=PARETO_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=MATH_GATE_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=PHYSICAL_CAPABILITY_ID, source="Profile"
                ),
                CapabilityResolution(
                    capabilityId=EPISTEMIC_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=OFFLINE_PERMISSION_CAPABILITY_ID, source="Profile"
                ),
            ),
            contentHash="",
            evaluatorVersion=R6_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R6_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R6_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_optimization,
    )
)


__all__ = [
    "HARD_CONSTRAINT_CLAIM_ID",
    "HARD_CONSTRAINT_METRIC_ID",
    "INTEGRITY_CLAIM_ID",
    "INTEGRITY_METRIC_ID",
    "OFFLINE_BOUNDARY_CLAIM_ID",
    "OFFLINE_BOUNDARY_METRIC_ID",
    "PARETO_COUNT_METRIC_ID",
    "R6_DOMAIN_PACK",
    "R6_RUNTIME_BINDING",
    "REALITY_VALIDATION_CLAIM_ID",
    "REALITY_VALIDATION_METRIC_ID",
    "RECOMMENDATION_AVAILABLE_CLAIM_ID",
    "evaluate_optimization",
]
