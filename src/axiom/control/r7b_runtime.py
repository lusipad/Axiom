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
from .r7b_models import (
    R7B_DOMAIN_PACK_ID,
    R7B_EVALUATOR_ID,
    R7B_RUNNER_ID,
    R7BEvaluationRequest,
)
from .r7b_scenarios import assess_r7b_deployment_shadow

R7B_CONTRACT_METRIC_ID = "control.deployment-shadow-contract-ready@1"
R7B_EXTERNAL_EVIDENCE_METRIC_ID = "control.deployment-shadow-external-evidence@1"
R7B_VENDOR_ADAPTER_METRIC_ID = "control.deployment-shadow-vendor-adapter@1"
R7B_AUTHORITY_METRIC_ID = "control.deployment-shadow-read-only-authority@1"
R7B_CAPTURE_METRIC_ID = "control.deployment-shadow-capture-integrity@1"
R7B_CLOCK_SIGNAL_METRIC_ID = "control.deployment-shadow-clock-signal-coverage@1"
R7B_REALITY_METRIC_ID = "control.deployment-shadow-reality@1"

R7B_CONTRACT_CLAIM_ID = "control.deployment-shadow-contract-ready-claim@1"
R7B_REALITY_CLAIM_ID = "control.deployment-shadow-reality-claim@1"

CAP_R7B_CONTRACT = "control.deployment-shadow.contract@1"
CAP_R7B_EXTERNAL_EVIDENCE = "control.deployment-shadow.external-evidence@1"
CAP_R7B_AUTHORITY = "control.deployment-shadow.controller-authority@1"
CAP_R7B_CAPTURE = "control.deployment-shadow.capture@1"
CAP_R7B_CLOCK_SIGNAL = "control.deployment-shadow.clock-signal@1"
CAP_R7B_VENDOR_ADAPTER = "control.deployment-shadow.vendor-adapter@1"

_METRIC_IDS = (
    R7B_CONTRACT_METRIC_ID,
    R7B_EXTERNAL_EVIDENCE_METRIC_ID,
    R7B_VENDOR_ADAPTER_METRIC_ID,
    R7B_AUTHORITY_METRIC_ID,
    R7B_CAPTURE_METRIC_ID,
    R7B_CLOCK_SIGNAL_METRIC_ID,
    R7B_REALITY_METRIC_ID,
)


def _definition(
    metric_id: str,
    *,
    requires: tuple[str, ...],
    claim_id: str | None = None,
    predicate: str | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=requires,
        claimDefinitionId=claim_id,
        claimPredicate=predicate,
    )


R7B_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R7B_DOMAIN_PACK_ID,
        artifactType="axiom.control.deployment-shadow-readiness",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.control.deployment-shadow-readiness",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.deployment-shadow-evidence-set",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.deployment-shadow-capture",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R7B_EVALUATOR_ID,
        runnerId=R7B_RUNNER_ID,
        runnerIds=(R7B_RUNNER_ID,),
        importRunnerIds=(R7B_RUNNER_ID,),
        capabilityIds=(
            CAP_R7B_CONTRACT,
            CAP_R7B_EXTERNAL_EVIDENCE,
            CAP_R7B_AUTHORITY,
            CAP_R7B_CAPTURE,
            CAP_R7B_CLOCK_SIGNAL,
            CAP_R7B_VENDOR_ADAPTER,
        ),
        metricDefinitions=(
            _definition(
                R7B_CONTRACT_METRIC_ID,
                requires=(CAP_R7B_CONTRACT,),
                claim_id=R7B_CONTRACT_CLAIM_ID,
                predicate="The R7-B Deployment Shadow readiness contract is internally valid.",
            ),
            _definition(
                R7B_EXTERNAL_EVIDENCE_METRIC_ID,
                requires=(CAP_R7B_EXTERNAL_EVIDENCE,),
            ),
            _definition(
                R7B_VENDOR_ADAPTER_METRIC_ID,
                requires=(CAP_R7B_VENDOR_ADAPTER,),
            ),
            _definition(
                R7B_AUTHORITY_METRIC_ID,
                requires=(CAP_R7B_AUTHORITY,),
            ),
            _definition(
                R7B_CAPTURE_METRIC_ID,
                requires=(CAP_R7B_CAPTURE,),
            ),
            _definition(
                R7B_CLOCK_SIGNAL_METRIC_ID,
                requires=(CAP_R7B_CLOCK_SIGNAL,),
            ),
            _definition(
                R7B_REALITY_METRIC_ID,
                requires=(CAP_R7B_VENDOR_ADAPTER, CAP_R7B_EXTERNAL_EVIDENCE),
                claim_id=R7B_REALITY_CLAIM_ID,
                predicate="A selected controller deployment has independently verified real Shadow evidence.",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            R7B_CONTRACT_CLAIM_ID,
            R7B_REALITY_CLAIM_ID,
        ),
        failureMappings=(
            FailureMapping(
                code="MalformedEvaluationRequest",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
            FailureMapping(
                code="DeploymentShadowAuditMismatch",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
        ),
    )
)

_DEFINITIONS = {
    definition.metric_id: definition for definition in R7B_DOMAIN_PACK.metric_definitions
}


def _parse_request(request: CoreEvaluationRequest) -> R7BEvaluationRequest:
    payload = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return R7BEvaluationRequest.model_validate(payload)


def _result(
    metric_id: str,
    *,
    status: MetricStatus,
    value: Any = None,
    reason_code: str | None = None,
    details: dict[str, Any] | None = None,
    evidence: Evidence | None = None,
) -> MetricResult:
    definition = _DEFINITIONS[metric_id]
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=list(definition.requires),
        status=status,
        value=value,
        reasonCode=reason_code,
        details=details or {},
        evidence=evidence,
    )


def _bind_boolean_gate(result: MetricResult) -> MetricResult:
    if result.status is MetricStatus.COMPUTED and isinstance(result.value, bool):
        return result.model_copy(update={"threshold_passed": result.value})
    return result


def _unsupported(metric_id: str, *, current_platform: str) -> MetricResult:
    return _result(
        metric_id,
        status=MetricStatus.UNSUPPORTED_CAPABILITY,
        reason_code="UnsupportedRuntimePlatform",
        details={"supportedPlatforms": ["Windows"], "currentPlatform": current_platform},
    )


def _provenance(request: R7BEvaluationRequest) -> Provenance:
    context_hashes: dict[str, str] | None = None
    if request.evidence_set is not None:
        evidence = request.evidence_set
        context_hashes = {
            "evidenceSet": evidence.content_hash,
            "controllerProfile": evidence.controller_profile.content_hash,
            "authority": evidence.authority.content_hash,
            "adapterReceipt": evidence.adapter_receipt.content_hash,
            "capture": evidence.capture.content_hash,
            "clockSignalBinding": evidence.clock_signal_binding.content_hash,
            "externalProvenance": evidence.provenance.content_hash,
        }
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=R7B_RUNNER_ID,
        evaluatorVersion=R7B_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment={
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "pydantic": package_version("pydantic"),
        },
        contextHashes=context_hashes,
    )


def _invalid_report(
    request: R7BEvaluationRequest, *, reason_code: str, message: str
) -> EvaluationReport:
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SKIPPED,
            caseOutcome=CaseOutcome.INVALID,
            metricResults=[
                _result(
                    metric_id,
                    status=MetricStatus.INVALID_OBSERVATION,
                    reason_code=reason_code,
                )
                for metric_id in _METRIC_IDS
            ],
            domainFailures=[
                DomainFailure(code=reason_code, message=message, path="request.artifact")
            ],
            contentHash="",
            evaluatorVersion=R7B_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


def _check_result(
    metric_id: str, *, check: Any, evidence_level: str = "Validated"
) -> MetricResult:
    if check.status == "Passed":
        return _result(
            metric_id,
            status=MetricStatus.COMPUTED,
            value=True,
            details=check.details,
            evidence=Evidence(level=evidence_level, method=f"{metric_id}.contract-check@1"),
        )
    if check.status == "Blocked":
        return _result(
            metric_id,
            status=MetricStatus.COMPUTED,
            value=False,
            reason_code=check.reason_code,
            details=check.details,
            evidence=Evidence(level="Validated", method=f"{metric_id}.contract-check@1"),
        )
    return _result(
        metric_id,
        status=MetricStatus.INSUFFICIENT_CONTEXT,
        reason_code=check.reason_code,
        details=check.details,
    )


def evaluate_r7b_deployment_shadow(
    request: R7BEvaluationRequest,
) -> EvaluationReport:
    current_platform = platform.system()
    if current_platform != "Windows":
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.UNSUPPORTED,
                metricResults=[
                    _unsupported(metric_id, current_platform=current_platform)
                    for metric_id in _METRIC_IDS
                ],
                contentHash="",
                evaluatorVersion=R7B_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay = assess_r7b_deployment_shadow(request.evidence_set)
    if replay.content_hash != request.artifact.content_hash or replay != request.artifact:
        return _invalid_report(
            request,
            reason_code="DeploymentShadowAuditMismatch",
            message="The submitted R7-B readiness audit does not match deterministic evidence assessment.",
        )

    checks = {check.check_id: check for check in replay.checks}
    evaluated = {
        R7B_CONTRACT_METRIC_ID: _check_result(
            R7B_CONTRACT_METRIC_ID, check=checks["r7b.contract"]
        ),
        R7B_EXTERNAL_EVIDENCE_METRIC_ID: _check_result(
            R7B_EXTERNAL_EVIDENCE_METRIC_ID, check=checks["r7b.external-evidence"]
        ),
        R7B_VENDOR_ADAPTER_METRIC_ID: _check_result(
            R7B_VENDOR_ADAPTER_METRIC_ID, check=checks["r7b.vendor-adapter"]
        ),
        R7B_AUTHORITY_METRIC_ID: _check_result(
            R7B_AUTHORITY_METRIC_ID, check=checks["r7b.authority"]
        ),
        R7B_CAPTURE_METRIC_ID: _check_result(
            R7B_CAPTURE_METRIC_ID, check=checks["r7b.capture-integrity"]
        ),
        R7B_CLOCK_SIGNAL_METRIC_ID: _check_result(
            R7B_CLOCK_SIGNAL_METRIC_ID, check=checks["r7b.clock-signal-coverage"]
        ),
        R7B_REALITY_METRIC_ID: _result(
            R7B_REALITY_METRIC_ID,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reason_code="RealDeploymentValidationOpen",
            details={
                "vendorAdapterStatus": replay.vendor_adapter_status,
                "deploymentShadowStatus": replay.deployment_shadow_status,
                "countsTowardReality": False,
            },
        ),
    }
    requested = request.case.required_metrics + request.case.optional_metrics
    results = [
        _bind_boolean_gate(
            _apply_threshold(evaluated[metric.metric_id], metric.threshold)
        )
        for metric in requested
    ]
    required_count = len(request.case.required_metrics)
    capabilities = [
        CapabilityResolution(capabilityId=CAP_R7B_CONTRACT, source="Evaluator")
    ]
    if request.evidence_set is not None:
        capabilities.extend(
            (
                CapabilityResolution(
                    capabilityId=CAP_R7B_EXTERNAL_EVIDENCE, source="Artifact"
                ),
                CapabilityResolution(capabilityId=CAP_R7B_AUTHORITY, source="Profile"),
                CapabilityResolution(capabilityId=CAP_R7B_CAPTURE, source="Artifact"),
                CapabilityResolution(
                    capabilityId=CAP_R7B_CLOCK_SIGNAL, source="Adapter"
                ),
            )
        )
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(results[:required_count]),
            metricResults=results,
            capabilities=capabilities,
            contentHash="",
            evaluatorVersion=R7B_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R7B_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R7B_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_r7b_deployment_shadow,
    )
)


__all__ = [
    "R7B_AUTHORITY_METRIC_ID",
    "R7B_CAPTURE_METRIC_ID",
    "R7B_CLOCK_SIGNAL_METRIC_ID",
    "R7B_CONTRACT_CLAIM_ID",
    "R7B_CONTRACT_METRIC_ID",
    "R7B_DOMAIN_PACK",
    "R7B_EXTERNAL_EVIDENCE_METRIC_ID",
    "R7B_REALITY_CLAIM_ID",
    "R7B_REALITY_METRIC_ID",
    "R7B_RUNTIME_BINDING",
    "R7B_VENDOR_ADAPTER_METRIC_ID",
    "evaluate_r7b_deployment_shadow",
]
