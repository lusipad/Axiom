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
    R7_DOMAIN_PACK_ID,
    R7_EVALUATOR_ID,
    R7_RUNNER_ID,
    ControlEvaluationRequest,
)
from .runner import run_shadow

INTEGRITY_METRIC_ID = "control.runtime-audit-integrity@1"
ADMISSION_METRIC_ID = "control.admission-policy-enforced@1"
NO_WRITE_METRIC_ID = "control.no-device-write-boundary@1"
STOP_METRIC_ID = "control.shadow-stop-path@1"
ROLLBACK_METRIC_ID = "control.shadow-rollback-boundary@1"
DEPLOYMENT_METRIC_ID = "control.deployment-readiness@1"

INTEGRITY_CLAIM_ID = "control.runtime-audit-integrity-claim@1"
ADMISSION_CLAIM_ID = "control.admission-policy-enforced-claim@1"
NO_WRITE_CLAIM_ID = "control.no-device-write-boundary-claim@1"
STOP_CLAIM_ID = "control.shadow-stop-path-claim@1"
ROLLBACK_CLAIM_ID = "control.shadow-rollback-boundary-claim@1"
DEPLOYMENT_CLAIM_ID = "control.deployment-readiness-claim@1"

AUDIT_CAPABILITY_ID = "control.deterministic-shadow-replay@1"
POLICY_CAPABILITY_ID = "control.fail-closed-admission@1"
MONITOR_CAPABILITY_ID = "control.envelope-monitor@1"
ROLLBACK_CAPABILITY_ID = "control.baseline-retention@1"


def _definition(
    metric_id: str, claim_id: str, requires: tuple[str, ...], predicate: str
) -> MetricDefinition:
    return MetricDefinition(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=requires,
        claimDefinitionId=claim_id,
        claimPredicate=predicate,
    )


R7_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R7_DOMAIN_PACK_ID,
        artifactType="axiom.control.runtime-audit",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.control.runtime-audit",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.optimization.recommendation-set",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R7_EVALUATOR_ID,
        runnerId=R7_RUNNER_ID,
        runnerIds=(R7_RUNNER_ID,),
        capabilityIds=(
            AUDIT_CAPABILITY_ID,
            POLICY_CAPABILITY_ID,
            MONITOR_CAPABILITY_ID,
            ROLLBACK_CAPABILITY_ID,
        ),
        metricDefinitions=(
            _definition(
                INTEGRITY_METRIC_ID,
                INTEGRITY_CLAIM_ID,
                (AUDIT_CAPABILITY_ID,),
                "Runtime audit content matches a deterministic replay.",
            ),
            _definition(
                ADMISSION_METRIC_ID,
                ADMISSION_CLAIM_ID,
                (POLICY_CAPABILITY_ID,),
                "The requested permission was admitted or blocked by the frozen fail-closed policy.",
            ),
            _definition(
                NO_WRITE_METRIC_ID,
                NO_WRITE_CLAIM_ID,
                (POLICY_CAPABILITY_ID,),
                "The R7-A shadow runtime exposed and performed no device write.",
            ),
            _definition(
                STOP_METRIC_ID,
                STOP_CLAIM_ID,
                (MONITOR_CAPABILITY_ID,),
                "A detected shadow envelope breach followed the frozen stop path.",
            ),
            _definition(
                ROLLBACK_METRIC_ID,
                ROLLBACK_CLAIM_ID,
                (ROLLBACK_CAPABILITY_ID,),
                "The offline baseline remained unchanged after a shadow breach.",
            ),
            _definition(
                DEPLOYMENT_METRIC_ID,
                DEPLOYMENT_CLAIM_ID,
                ("control.real-deployment-evidence@1",),
                "A concrete deployment provides real shadow, device stop and responsibility evidence.",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            INTEGRITY_CLAIM_ID,
            ADMISSION_CLAIM_ID,
            NO_WRITE_CLAIM_ID,
            STOP_CLAIM_ID,
            ROLLBACK_CLAIM_ID,
            DEPLOYMENT_CLAIM_ID,
        ),
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


def _parse_request(request: CoreEvaluationRequest) -> ControlEvaluationRequest:
    return ControlEvaluationRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _computed(metric_id: str, value: Any, **details: Any) -> MetricResult:
    definition = R7_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=MetricStatus.COMPUTED,
        value=value,
        details=details,
        evidence=Evidence(
            level="Observed", method=f"{metric_id}.deterministic-shadow-replay@1"
        ),
    )


def _unavailable(
    metric_id: str, status: MetricStatus, reason_code: str, **details: Any
) -> MetricResult:
    definition = R7_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=status,
        reasonCode=reason_code,
        details=details,
        evidence=Evidence(level="Observed", method=f"{metric_id}.boundary@1"),
    )


def _provenance(request: ControlEvaluationRequest) -> Provenance:
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=R7_RUNNER_ID,
        evaluatorVersion=R7_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment={
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "pydantic": package_version("pydantic"),
        },
        contextHashes={
            "runtimeSpec": _content_hash(request.runtime_spec),
            "recommendationSet": request.recommendation_set.content_hash,
            "acceptanceRecord": request.artifact.acceptance_record.content_hash,
        },
    )


def evaluate_control(request: ControlEvaluationRequest) -> EvaluationReport:
    metric_ids = (
        INTEGRITY_METRIC_ID,
        ADMISSION_METRIC_ID,
        NO_WRITE_METRIC_ID,
        STOP_METRIC_ID,
        ROLLBACK_METRIC_ID,
        DEPLOYMENT_METRIC_ID,
    )
    if platform.system() != "Windows":
        results = [
            _unavailable(
                metric_id,
                MetricStatus.UNSUPPORTED_CAPABILITY,
                "UnsupportedRuntimePlatform",
                currentPlatform=platform.system(),
                supportedPlatforms=["Windows"],
            )
            for metric_id in metric_ids
        ]
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.UNSUPPORTED,
                metricResults=results,
                contentHash="",
                evaluatorVersion=R7_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )
    replay = run_shadow(request.runtime_spec, request.recommendation_set)
    if replay != request.artifact:
        results = [
            _unavailable(
                metric_id,
                MetricStatus.INVALID_OBSERVATION,
                "RuntimeAuditReplayMismatch",
            )
            for metric_id in metric_ids
        ]
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.INVALID,
                metricResults=results,
                domainFailures=[
                    DomainFailure(
                        code="RuntimeAuditReplayMismatch",
                        message="ControlledRuntimeAudit failed deterministic replay.",
                        path="request.artifact",
                    )
                ],
                contentHash="",
                evaluatorVersion=R7_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )
    stopped = replay.final_state == "RollbackVerified"
    evaluated = {
        INTEGRITY_METRIC_ID: _computed(
            INTEGRITY_METRIC_ID, True, auditContentHash=replay.content_hash
        ),
        ADMISSION_METRIC_ID: _computed(
            ADMISSION_METRIC_ID,
            True,
            admissionStatus=replay.admission_decision.status,
            reasonCodes=replay.admission_decision.reason_codes,
        ),
        NO_WRITE_METRIC_ID: _computed(
            NO_WRITE_METRIC_ID,
            not replay.device_write_allowed and not replay.device_write_performed,
        ),
        STOP_METRIC_ID: _computed(
            STOP_METRIC_ID,
            stopped and replay.stop_receipt.requested,
            finalState=replay.final_state,
        ),
        ROLLBACK_METRIC_ID: _computed(
            ROLLBACK_METRIC_ID,
            stopped and replay.rollback_receipt.status == "BaselineRetained",
            rollbackStatus=replay.rollback_receipt.status,
        ),
        DEPLOYMENT_METRIC_ID: _unavailable(
            DEPLOYMENT_METRIC_ID,
            MetricStatus.INSUFFICIENT_CONTEXT,
            "RealDeploymentEvidenceMissing",
            deploymentShadowStatus="Open",
            controlledTrialStatus="Open",
            closedLoopStatus="Open",
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
                    capabilityId=AUDIT_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=POLICY_CAPABILITY_ID, source="Profile"
                ),
                CapabilityResolution(
                    capabilityId=MONITOR_CAPABILITY_ID, source="Evaluator"
                ),
                CapabilityResolution(
                    capabilityId=ROLLBACK_CAPABILITY_ID, source="Evaluator"
                ),
            ),
            contentHash="",
            evaluatorVersion=R7_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R7_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R7_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_control,
    )
)
