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
from ..evaluator import _aggregate_outcome, _apply_threshold, _content_hash, _seal_evaluation_report
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
from .models import IntelligenceEvaluationRequest, R5_DOMAIN_PACK_ID, R5_EVALUATOR_ID, R5_RUNNER_ID
from .training import train_r5_bundle

INTEGRITY_VALID_METRIC_ID = "intelligence.integrity-valid@1"
SYNTHETIC_LEARNING_METRIC_ID = "intelligence.synthetic-learning-contract@1"
IN_DOMAIN_IMPROVEMENT_METRIC_ID = "intelligence.x.in-domain-improvement-ratio@1"
CONFORMAL_COVERAGE_METRIC_ID = "intelligence.x.conformal-coverage@1"
OOD_DETECTION_METRIC_ID = "intelligence.x.ood-detection-rate@1"
TARGET_PARITY_METRIC_ID = "intelligence.x.target-parity-max-abs-gap@1"
REAL_WORLD_GENERALIZATION_METRIC_ID = "intelligence.real-world-generalization@1"
SYNTHETIC_LEARNING_CLAIM_ID = "intelligence.synthetic-learning-contract-claim@1"
REAL_WORLD_GENERALIZATION_CLAIM_ID = "intelligence.real-world-generalization-claim@1"
DATASET_CAPABILITY_ID = "intelligence.synthetic-dataset@1"
SPLIT_CONTRACT_CAPABILITY_ID = "intelligence.split-contract@1"
TRAINING_RECEIPT_CAPABILITY_ID = "intelligence.training-receipt@1"
MODEL_BUNDLE_CAPABILITY_ID = "intelligence.model-bundle@1"
OOD_ABSTENTION_CAPABILITY_ID = "intelligence.ood-abstention@1"
SPLIT_CONFORMAL_CAPABILITY_ID = "intelligence.split-conformal@1"
TARGET_PARITY_CAPABILITY_ID = "intelligence.target-parity@1"
REAL_PAIRED_HOLDOUT_CAPABILITY_ID = "intelligence.real-paired-holdout@1"


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
            NumericTolerance(absolute=1e-12, relative=1e-12, unit=unit) if direction is not None else None
        ),
    )


R5_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R5_DOMAIN_PACK_ID,
        artifactType="axiom.intelligence.model-bundle",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(artifactType="axiom.intelligence.model-bundle", schemaVersion=1, role="run-input"),
            ArtifactTypeDescriptor(artifactType="axiom.intelligence.dataset-snapshot", schemaVersion=1, role="context"),
            ArtifactTypeDescriptor(artifactType="axiom.intelligence.split-manifest", schemaVersion=1, role="context"),
            ArtifactTypeDescriptor(artifactType="axiom.intelligence.training-receipt", schemaVersion=1, role="context"),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.target-parity-receipt",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R5_EVALUATOR_ID,
        runnerId=R5_RUNNER_ID,
        runnerIds=(R5_RUNNER_ID,),
        capabilityIds=(
            DATASET_CAPABILITY_ID,
            SPLIT_CONTRACT_CAPABILITY_ID,
            TRAINING_RECEIPT_CAPABILITY_ID,
            MODEL_BUNDLE_CAPABILITY_ID,
            OOD_ABSTENTION_CAPABILITY_ID,
            SPLIT_CONFORMAL_CAPABILITY_ID,
            TARGET_PARITY_CAPABILITY_ID,
        ),
        metricDefinitions=(
            _metric(
                INTEGRITY_VALID_METRIC_ID,
                requires=(
                    DATASET_CAPABILITY_ID,
                    SPLIT_CONTRACT_CAPABILITY_ID,
                    TRAINING_RECEIPT_CAPABILITY_ID,
                    MODEL_BUNDLE_CAPABILITY_ID,
                    TARGET_PARITY_CAPABILITY_ID,
                ),
            ),
            _metric(
                SYNTHETIC_LEARNING_METRIC_ID,
                requires=(
                    DATASET_CAPABILITY_ID,
                    SPLIT_CONTRACT_CAPABILITY_ID,
                    TRAINING_RECEIPT_CAPABILITY_ID,
                    MODEL_BUNDLE_CAPABILITY_ID,
                    OOD_ABSTENTION_CAPABILITY_ID,
                    SPLIT_CONFORMAL_CAPABILITY_ID,
                    TARGET_PARITY_CAPABILITY_ID,
                ),
                claim_id=SYNTHETIC_LEARNING_CLAIM_ID,
                predicate="Synthetic intelligence learning contract is passed for the X-axis only.",
            ),
            _metric(
                IN_DOMAIN_IMPROVEMENT_METRIC_ID,
                requires=(DATASET_CAPABILITY_ID, SPLIT_CONTRACT_CAPABILITY_ID, MODEL_BUNDLE_CAPABILITY_ID),
                direction="higher-is-better",
                unit="ratio",
            ),
            _metric(
                CONFORMAL_COVERAGE_METRIC_ID,
                requires=(
                    DATASET_CAPABILITY_ID,
                    SPLIT_CONTRACT_CAPABILITY_ID,
                    MODEL_BUNDLE_CAPABILITY_ID,
                    SPLIT_CONFORMAL_CAPABILITY_ID,
                ),
                direction="higher-is-better",
                unit="ratio",
            ),
            _metric(
                OOD_DETECTION_METRIC_ID,
                requires=(DATASET_CAPABILITY_ID, MODEL_BUNDLE_CAPABILITY_ID, OOD_ABSTENTION_CAPABILITY_ID),
                direction="higher-is-better",
                unit="ratio",
            ),
            _metric(
                TARGET_PARITY_METRIC_ID,
                requires=(MODEL_BUNDLE_CAPABILITY_ID, TARGET_PARITY_CAPABILITY_ID),
                direction="lower-is-better",
                unit="ratio",
            ),
            _metric(
                REAL_WORLD_GENERALIZATION_METRIC_ID,
                requires=(REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
                claim_id=REAL_WORLD_GENERALIZATION_CLAIM_ID,
                predicate="Real-world generalization is supported by independent paired device holdout evidence.",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            SYNTHETIC_LEARNING_CLAIM_ID,
            REAL_WORLD_GENERALIZATION_CLAIM_ID,
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


def _parse_request(request: CoreEvaluationRequest) -> IntelligenceEvaluationRequest:
    return IntelligenceEvaluationRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _computed(metric_id: str, value: Any, *, unit: str | None = None, details: dict[str, Any] | None = None) -> MetricResult:
    definition = R5_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=MetricStatus.COMPUTED,
        value=value,
        unit=unit,
        details=details or {},
        evidence=Evidence(level="Observed", method=f"{metric_id}.synthetic-replay@1"),
    )


def _unsupported(metric_id: str, *, current_platform: str) -> MetricResult:
    definition = R5_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=MetricStatus.UNSUPPORTED_CAPABILITY,
        reasonCode="UnsupportedRuntimePlatform",
        details={
            "currentPlatform": current_platform,
            "supportedPlatforms": ["Windows"],
        },
        evidence=Evidence(level="Observed", method=f"{metric_id}.runtime-gate@1"),
    )


def _invalid_results(reason_code: str) -> list[MetricResult]:
    return [
        MetricResult(
            metricId=metric_id,
            metricDefinitionId=R5_DOMAIN_PACK.metric_definition(metric_id).metric_definition_id,
            requires=R5_DOMAIN_PACK.metric_definition(metric_id).requires,
            status=MetricStatus.INVALID_OBSERVATION,
            reasonCode=reason_code,
        )
        for metric_id in (
            INTEGRITY_VALID_METRIC_ID,
            SYNTHETIC_LEARNING_METRIC_ID,
            IN_DOMAIN_IMPROVEMENT_METRIC_ID,
            CONFORMAL_COVERAGE_METRIC_ID,
            OOD_DETECTION_METRIC_ID,
            TARGET_PARITY_METRIC_ID,
            REAL_WORLD_GENERALIZATION_METRIC_ID,
        )
    ]


def _provenance(request: IntelligenceEvaluationRequest) -> Provenance:
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=R5_RUNNER_ID,
        evaluatorVersion=R5_EVALUATOR_ID,
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


def evaluate_intelligence(request: IntelligenceEvaluationRequest) -> EvaluationReport:
    current_platform = platform.system()
    if current_platform != "Windows":
        results = [
            _unsupported(metric_id, current_platform=current_platform)
            for metric_id in (
                INTEGRITY_VALID_METRIC_ID,
                SYNTHETIC_LEARNING_METRIC_ID,
                IN_DOMAIN_IMPROVEMENT_METRIC_ID,
                CONFORMAL_COVERAGE_METRIC_ID,
                OOD_DETECTION_METRIC_ID,
                TARGET_PARITY_METRIC_ID,
                REAL_WORLD_GENERALIZATION_METRIC_ID,
            )
        ]
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.UNSUPPORTED,
                metricResults=results,
                contentHash="",
                evaluatorVersion=R5_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay_bundle, replay_training_receipt, replay_parity_receipt, replay_evaluation = train_r5_bundle(
        request.dataset,
        request.split_manifest,
    )
    if (
        replay_bundle.content_hash != request.artifact.content_hash
        or replay_training_receipt.content_hash != request.training_receipt.content_hash
        or replay_parity_receipt.content_hash != request.parity_receipt.content_hash
    ):
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.INVALID,
                metricResults=_invalid_results("IntegrityReplayMismatch"),
                domainFailures=[
                    DomainFailure(
                        code="IntegrityReplayMismatch",
                        message="Dataset, split, bundle, training receipt, or parity receipt failed deterministic replay.",
                        path="request",
                    )
                ],
                contentHash="",
                evaluatorVersion=R5_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    x_axis = replay_evaluation.axis_results[0]
    evaluated = {
        INTEGRITY_VALID_METRIC_ID: _computed(
            INTEGRITY_VALID_METRIC_ID,
            True,
            details={"bundleHash": replay_bundle.content_hash},
        ),
        SYNTHETIC_LEARNING_METRIC_ID: _computed(
            SYNTHETIC_LEARNING_METRIC_ID,
            replay_evaluation.synthetic_learning_contract_status == "Passed",
            details={"axisStatus": x_axis.status},
        ),
        IN_DOMAIN_IMPROVEMENT_METRIC_ID: _computed(
            IN_DOMAIN_IMPROVEMENT_METRIC_ID,
            x_axis.improvement_ratio,
        ),
        CONFORMAL_COVERAGE_METRIC_ID: _computed(
            CONFORMAL_COVERAGE_METRIC_ID,
            replay_evaluation.conformal_coverage,
        ),
        OOD_DETECTION_METRIC_ID: _computed(
            OOD_DETECTION_METRIC_ID,
            replay_evaluation.ood_detection_rate,
        ),
        TARGET_PARITY_METRIC_ID: _computed(
            TARGET_PARITY_METRIC_ID,
            replay_evaluation.target_parity_max_abs_gap,
        ),
        REAL_WORLD_GENERALIZATION_METRIC_ID: MetricResult(
            metricId=REAL_WORLD_GENERALIZATION_METRIC_ID,
            metricDefinitionId=R5_DOMAIN_PACK.metric_definition(
                REAL_WORLD_GENERALIZATION_METRIC_ID
            ).metric_definition_id,
            requires=R5_DOMAIN_PACK.metric_definition(REAL_WORLD_GENERALIZATION_METRIC_ID).requires,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reasonCode="RealPairedHoldoutMissing",
            details={"realWorldGeneralizationStatus": "Open"},
            evidence=Evidence(
                level="Observed",
                method="intelligence.synthetic-only-boundary@1",
            ),
        ),
    }
    requested = request.case.required_metrics + request.case.optional_metrics
    results = [_apply_threshold(evaluated[item.metric_id], item.threshold) for item in requested]
    required = results[: len(request.case.required_metrics)]
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(required),
            metricResults=results,
            capabilities=(
                CapabilityResolution(capabilityId=DATASET_CAPABILITY_ID, source="Artifact"),
                CapabilityResolution(capabilityId=SPLIT_CONTRACT_CAPABILITY_ID, source="Artifact"),
                CapabilityResolution(capabilityId=TRAINING_RECEIPT_CAPABILITY_ID, source="Artifact"),
                CapabilityResolution(capabilityId=MODEL_BUNDLE_CAPABILITY_ID, source="Artifact"),
                CapabilityResolution(capabilityId=OOD_ABSTENTION_CAPABILITY_ID, source="Evaluator"),
                CapabilityResolution(capabilityId=SPLIT_CONFORMAL_CAPABILITY_ID, source="Evaluator"),
                CapabilityResolution(capabilityId=TARGET_PARITY_CAPABILITY_ID, source="Evaluator"),
            ),
            contentHash="",
            evaluatorVersion=R5_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R5_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R5_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_intelligence,
    )
)


__all__ = [
    "CONFORMAL_COVERAGE_METRIC_ID",
    "IN_DOMAIN_IMPROVEMENT_METRIC_ID",
    "INTEGRITY_VALID_METRIC_ID",
    "OOD_DETECTION_METRIC_ID",
    "REAL_WORLD_GENERALIZATION_CLAIM_ID",
    "REAL_WORLD_GENERALIZATION_METRIC_ID",
    "R5_DOMAIN_PACK",
    "R5_RUNTIME_BINDING",
    "SYNTHETIC_LEARNING_CLAIM_ID",
    "SYNTHETIC_LEARNING_METRIC_ID",
    "TARGET_PARITY_METRIC_ID",
    "evaluate_intelligence",
]
