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
from .r5c_models import (
    R5C_DOMAIN_PACK_ID,
    R5C_EVALUATOR_ID,
    R5C_RUNNER_ID,
    ConditionalEffectEvaluationRequest,
)
from .r5c_training import train_r5c_bundle

R5C_INTEGRITY_METRIC_ID = "intelligence.r5c.integrity-valid@1"
R5C_SYNTHETIC_CONTRACT_METRIC_ID = "intelligence.r5c.synthetic-contract@1"
R5C_CYCLE_NRMSE_METRIC_ID = (
    "intelligence.r5c.cycle-time-normalized-rmse@1"
)
R5C_LINEAR_ERROR_NRMSE_METRIC_ID = (
    "intelligence.r5c.linear-error-normalized-rmse@1"
)
R5C_CONFORMAL_COVERAGE_METRIC_ID = (
    "intelligence.r5c.minimum-conformal-coverage@1"
)
R5C_OOD_ABSTENTION_METRIC_ID = "intelligence.r5c.ood-abstention-rate@1"
R5C_TARGET_PARITY_METRIC_ID = (
    "intelligence.r5c.target-parity-max-abs-gap@1"
)
R5C_REAL_GENERALIZATION_METRIC_ID = (
    "intelligence.r5c.real-world-generalization@1"
)
R5C_SYNTHETIC_CLAIM_ID = "intelligence.synthetic-conditional-effect-claim@1"
R5C_REAL_GENERALIZATION_CLAIM_ID = (
    "intelligence.real-world-generalization-claim@1"
)

R5C_DATASET_CAPABILITY_ID = "intelligence.r5c.synthetic-parameter-study@1"
R5C_SPLIT_CAPABILITY_ID = "intelligence.r5c.spatial-split@1"
R5C_TRAINING_CAPABILITY_ID = "intelligence.r5c.training-replay@1"
R5C_MODEL_CAPABILITY_ID = "intelligence.r5c.two-head-surrogate@1"
R5C_INTERVAL_CAPABILITY_ID = "intelligence.r5c.split-conformal@1"
R5C_ABSTENTION_CAPABILITY_ID = "intelligence.r5c.domain-abstention@1"
R5C_PARITY_CAPABILITY_ID = "intelligence.r5c.target-parity@1"
R5C_REAL_HOLDOUT_CAPABILITY_ID = "intelligence.real-paired-holdout@1"

_METRIC_IDS = (
    R5C_INTEGRITY_METRIC_ID,
    R5C_SYNTHETIC_CONTRACT_METRIC_ID,
    R5C_CYCLE_NRMSE_METRIC_ID,
    R5C_LINEAR_ERROR_NRMSE_METRIC_ID,
    R5C_CONFORMAL_COVERAGE_METRIC_ID,
    R5C_OOD_ABSTENTION_METRIC_ID,
    R5C_TARGET_PARITY_METRIC_ID,
    R5C_REAL_GENERALIZATION_METRIC_ID,
)


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
            NumericTolerance(absolute=1e-12, relative=1e-12, unit=unit)
            if direction is not None
            else None
        ),
    )


R5C_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R5C_DOMAIN_PACK_ID,
        artifactType="axiom.intelligence.conditional-effect-model-bundle",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.conditional-effect-model-bundle",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.conditional-effect-dataset",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.conditional-effect-split-manifest",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.conditional-effect-training-receipt",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.conditional-effect-parity-receipt",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R5C_EVALUATOR_ID,
        runnerId=R5C_RUNNER_ID,
        runnerIds=(R5C_RUNNER_ID,),
        capabilityIds=(
            R5C_DATASET_CAPABILITY_ID,
            R5C_SPLIT_CAPABILITY_ID,
            R5C_TRAINING_CAPABILITY_ID,
            R5C_MODEL_CAPABILITY_ID,
            R5C_INTERVAL_CAPABILITY_ID,
            R5C_ABSTENTION_CAPABILITY_ID,
            R5C_PARITY_CAPABILITY_ID,
        ),
        metricDefinitions=(
            _metric(
                R5C_INTEGRITY_METRIC_ID,
                requires=(
                    R5C_DATASET_CAPABILITY_ID,
                    R5C_SPLIT_CAPABILITY_ID,
                    R5C_TRAINING_CAPABILITY_ID,
                    R5C_MODEL_CAPABILITY_ID,
                    R5C_PARITY_CAPABILITY_ID,
                ),
            ),
            _metric(
                R5C_SYNTHETIC_CONTRACT_METRIC_ID,
                requires=(
                    R5C_DATASET_CAPABILITY_ID,
                    R5C_SPLIT_CAPABILITY_ID,
                    R5C_TRAINING_CAPABILITY_ID,
                    R5C_MODEL_CAPABILITY_ID,
                    R5C_INTERVAL_CAPABILITY_ID,
                    R5C_ABSTENTION_CAPABILITY_ID,
                    R5C_PARITY_CAPABILITY_ID,
                ),
                claim_id=R5C_SYNTHETIC_CLAIM_ID,
                predicate=(
                    "Synthetic SIL conditional-effect gates pass inside the declared "
                    "feed-override and sample-period domain."
                ),
            ),
            _metric(
                R5C_CYCLE_NRMSE_METRIC_ID,
                requires=(R5C_DATASET_CAPABILITY_ID, R5C_MODEL_CAPABILITY_ID),
                direction="lower-is-better",
                unit="ratio",
            ),
            _metric(
                R5C_LINEAR_ERROR_NRMSE_METRIC_ID,
                requires=(R5C_DATASET_CAPABILITY_ID, R5C_MODEL_CAPABILITY_ID),
                direction="lower-is-better",
                unit="ratio",
            ),
            _metric(
                R5C_CONFORMAL_COVERAGE_METRIC_ID,
                requires=(R5C_INTERVAL_CAPABILITY_ID,),
                direction="higher-is-better",
                unit="ratio",
            ),
            _metric(
                R5C_OOD_ABSTENTION_METRIC_ID,
                requires=(R5C_ABSTENTION_CAPABILITY_ID,),
                direction="higher-is-better",
                unit="ratio",
            ),
            _metric(
                R5C_TARGET_PARITY_METRIC_ID,
                requires=(R5C_PARITY_CAPABILITY_ID,),
                direction="lower-is-better",
                unit="ratio",
            ),
            _metric(
                R5C_REAL_GENERALIZATION_METRIC_ID,
                requires=(R5C_REAL_HOLDOUT_CAPABILITY_ID,),
                claim_id=R5C_REAL_GENERALIZATION_CLAIM_ID,
                predicate=(
                    "Independent real-device holdout supports case-scoped generalization."
                ),
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            R5C_SYNTHETIC_CLAIM_ID,
            R5C_REAL_GENERALIZATION_CLAIM_ID,
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


def _parse_request(
    request: CoreEvaluationRequest,
) -> ConditionalEffectEvaluationRequest:
    return ConditionalEffectEvaluationRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _provenance(request: ConditionalEffectEvaluationRequest) -> Provenance:
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=request.artifact.content_hash,
        caseHash=_content_hash(request.case),
        runnerId=R5C_RUNNER_ID,
        evaluatorVersion=R5C_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment={
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "pydantic": package_version("pydantic"),
        },
        contextHashes={
            "dataset": request.dataset.content_hash,
            "splitManifest": request.split_manifest.content_hash,
            "trainingReceipt": request.training_receipt.content_hash,
            "parityReceipt": request.parity_receipt.content_hash,
        },
    )


def _computed(
    metric_id: str,
    value: Any,
    *,
    unit: str | None = None,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    definition = R5C_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=MetricStatus.COMPUTED,
        value=value,
        unit=unit,
        details=details or {},
        evidence=Evidence(
            level="Observed", method=f"{metric_id}.synthetic-sil-replay@1"
        ),
    )


def _results_with_status(
    status: MetricStatus,
    *,
    reason_code: str,
    details: dict[str, Any] | None = None,
) -> list[MetricResult]:
    return [
        MetricResult(
            metricId=metric_id,
            metricDefinitionId=R5C_DOMAIN_PACK.metric_definition(
                metric_id
            ).metric_definition_id,
            requires=R5C_DOMAIN_PACK.metric_definition(metric_id).requires,
            status=status,
            reasonCode=reason_code,
            details=details or {},
        )
        for metric_id in _METRIC_IDS
    ]


def evaluate_conditional_effect(
    request: ConditionalEffectEvaluationRequest,
) -> EvaluationReport:
    current_platform = platform.system()
    if current_platform != "Windows":
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.UNSUPPORTED,
                metricResults=_results_with_status(
                    MetricStatus.UNSUPPORTED_CAPABILITY,
                    reason_code="UnsupportedRuntimePlatform",
                    details={
                        "currentPlatform": current_platform,
                        "supportedPlatforms": ["Windows"],
                    },
                ),
                contentHash="",
                evaluatorVersion=R5C_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay_bundle, replay_receipt, replay_parity, replay_evaluation = (
        train_r5c_bundle(request.dataset, request.split_manifest)
    )
    if (
        replay_bundle.content_hash != request.artifact.content_hash
        or replay_receipt.content_hash != request.training_receipt.content_hash
        or replay_parity.content_hash != request.parity_receipt.content_hash
    ):
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.INVALID,
                metricResults=_results_with_status(
                    MetricStatus.INVALID_OBSERVATION,
                    reason_code="IntegrityReplayMismatch",
                ),
                domainFailures=(
                    DomainFailure(
                        code="IntegrityReplayMismatch",
                        message=(
                            "Dataset, split, training receipt, two-head bundle, or parity "
                            "receipt failed deterministic replay."
                        ),
                        path="request",
                    ),
                ),
                contentHash="",
                evaluatorVersion=R5C_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    by_target = {
        result.target_id: result for result in replay_evaluation.head_results
    }
    cycle = by_target["cycleTimeSeconds"]
    linear_error = by_target["linearFollowingErrorMaxMm"]
    evaluated = {
        R5C_INTEGRITY_METRIC_ID: _computed(
            R5C_INTEGRITY_METRIC_ID,
            True,
            details={"modelBundleHash": replay_bundle.content_hash},
        ),
        R5C_SYNTHETIC_CONTRACT_METRIC_ID: _computed(
            R5C_SYNTHETIC_CONTRACT_METRIC_ID,
            replay_evaluation.synthetic_conditional_effect_contract_status
            == "Passed",
            details={
                "scope": "synthetic-sil",
                "realWorldGeneralizationStatus": "Open",
            },
        ),
        R5C_CYCLE_NRMSE_METRIC_ID: _computed(
            R5C_CYCLE_NRMSE_METRIC_ID,
            cycle.normalized_rmse,
            unit="ratio",
            details={"targetId": cycle.target_id, "nativeUnit": cycle.unit},
        ),
        R5C_LINEAR_ERROR_NRMSE_METRIC_ID: _computed(
            R5C_LINEAR_ERROR_NRMSE_METRIC_ID,
            linear_error.normalized_rmse,
            unit="ratio",
            details={
                "targetId": linear_error.target_id,
                "nativeUnit": linear_error.unit,
            },
        ),
        R5C_CONFORMAL_COVERAGE_METRIC_ID: _computed(
            R5C_CONFORMAL_COVERAGE_METRIC_ID,
            min(item.conformal_coverage for item in replay_evaluation.head_results),
            unit="ratio",
            details={
                "cycleTimeCoverage": cycle.conformal_coverage,
                "linearErrorCoverage": linear_error.conformal_coverage,
            },
        ),
        R5C_OOD_ABSTENTION_METRIC_ID: _computed(
            R5C_OOD_ABSTENTION_METRIC_ID,
            replay_evaluation.ood_abstention_rate,
            unit="ratio",
        ),
        R5C_TARGET_PARITY_METRIC_ID: _computed(
            R5C_TARGET_PARITY_METRIC_ID,
            replay_evaluation.target_parity_max_abs_gap,
            unit="ratio",
        ),
        R5C_REAL_GENERALIZATION_METRIC_ID: MetricResult(
            metricId=R5C_REAL_GENERALIZATION_METRIC_ID,
            metricDefinitionId=R5C_DOMAIN_PACK.metric_definition(
                R5C_REAL_GENERALIZATION_METRIC_ID
            ).metric_definition_id,
            requires=R5C_DOMAIN_PACK.metric_definition(
                R5C_REAL_GENERALIZATION_METRIC_ID
            ).requires,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reasonCode="RealPairedHoldoutMissing",
            details={"realWorldGeneralizationStatus": "Open"},
            evidence=Evidence(
                level="Observed",
                method="intelligence.r5c.synthetic-only-boundary@1",
            ),
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
                    capabilityId=R5C_DATASET_CAPABILITY_ID, source="Artifact"
                ),
                CapabilityResolution(
                    capabilityId=R5C_SPLIT_CAPABILITY_ID, source="Artifact"
                ),
                CapabilityResolution(
                    capabilityId=R5C_TRAINING_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=R5C_MODEL_CAPABILITY_ID, source="Artifact"
                ),
                CapabilityResolution(
                    capabilityId=R5C_INTERVAL_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=R5C_ABSTENTION_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=R5C_PARITY_CAPABILITY_ID, source="Evaluator"
                ),
            ),
            contentHash="",
            evaluatorVersion=R5C_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R5C_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R5C_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_conditional_effect,
    )
)


__all__ = [
    "R5C_CONFORMAL_COVERAGE_METRIC_ID",
    "R5C_CYCLE_NRMSE_METRIC_ID",
    "R5C_DOMAIN_PACK",
    "R5C_INTEGRITY_METRIC_ID",
    "R5C_LINEAR_ERROR_NRMSE_METRIC_ID",
    "R5C_OOD_ABSTENTION_METRIC_ID",
    "R5C_REAL_GENERALIZATION_METRIC_ID",
    "R5C_RUNTIME_BINDING",
    "R5C_SYNTHETIC_CONTRACT_METRIC_ID",
    "R5C_TARGET_PARITY_METRIC_ID",
    "evaluate_conditional_effect",
]
