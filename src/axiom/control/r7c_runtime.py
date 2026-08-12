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
from .r7c_models import (
    R7CEvaluationRequest,
    R7C_DOMAIN_PACK_ID,
    R7C_EVALUATOR_ID,
    R7C_RUNNER_ID,
)
from .r7c_scenarios import assess_r7c_opcua_transport

R7C_CONTRACT_METRIC_ID = "control.opcua-adapter-contract-ready@1"
R7C_VIRTUAL_TRANSPORT_METRIC_ID = "control.opcua-virtual-transport@1"
R7C_SECURE_CHANNEL_METRIC_ID = "control.opcua-secure-channel@1"
R7C_SUBSCRIPTION_METRIC_ID = "control.opcua-subscription-integrity@1"
R7C_ZERO_WRITE_METRIC_ID = "control.opcua-zero-write@1"
R7C_VENDOR_ADAPTER_METRIC_ID = "control.opcua-vendor-adapter@1"
R7C_REALITY_METRIC_ID = "control.opcua-real-deployment@1"

R7C_CONTRACT_CLAIM_ID = "control.opcua-adapter-contract-ready-claim@1"
R7C_VIRTUAL_TRANSPORT_CLAIM_ID = "control.opcua-virtual-transport-claim@1"
R7C_REALITY_CLAIM_ID = "control.opcua-real-deployment-claim@1"

CAP_R7C_CONTRACT = "control.opcua.adapter-contract@1"
CAP_R7C_TRANSPORT_EVIDENCE = "control.opcua.transport-evidence@1"
CAP_R7C_SECURE_CHANNEL = "control.opcua.secure-channel@1"
CAP_R7C_SUBSCRIPTION = "control.opcua.subscription@1"
CAP_R7C_ZERO_WRITE = "control.opcua.zero-write@1"
CAP_R7C_VENDOR_ADAPTER = "control.opcua.vendor-adapter@1"

_METRIC_IDS = (
    R7C_CONTRACT_METRIC_ID,
    R7C_VIRTUAL_TRANSPORT_METRIC_ID,
    R7C_SECURE_CHANNEL_METRIC_ID,
    R7C_SUBSCRIPTION_METRIC_ID,
    R7C_ZERO_WRITE_METRIC_ID,
    R7C_VENDOR_ADAPTER_METRIC_ID,
    R7C_REALITY_METRIC_ID,
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


R7C_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R7C_DOMAIN_PACK_ID,
        artifactType="axiom.control.opcua-transport-readiness",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.control.opcua-transport-readiness",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.opcua-transport-evidence",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R7C_EVALUATOR_ID,
        runnerId=R7C_RUNNER_ID,
        runnerIds=(R7C_RUNNER_ID,),
        importRunnerIds=(R7C_RUNNER_ID,),
        capabilityIds=(
            CAP_R7C_CONTRACT,
            CAP_R7C_TRANSPORT_EVIDENCE,
            CAP_R7C_SECURE_CHANNEL,
            CAP_R7C_SUBSCRIPTION,
            CAP_R7C_ZERO_WRITE,
            CAP_R7C_VENDOR_ADAPTER,
        ),
        metricDefinitions=(
            _definition(
                R7C_CONTRACT_METRIC_ID,
                requires=(CAP_R7C_CONTRACT,),
                claim_id=R7C_CONTRACT_CLAIM_ID,
                predicate="The Windows read-only OPC UA Adapter contract is valid.",
            ),
            _definition(
                R7C_VIRTUAL_TRANSPORT_METRIC_ID,
                requires=(CAP_R7C_TRANSPORT_EVIDENCE,),
                claim_id=R7C_VIRTUAL_TRANSPORT_CLAIM_ID,
                predicate=(
                    "A Windows virtual OPC UA session used a pinned encrypted channel, "
                    "complete five-axis subscription, and zero writes."
                ),
            ),
            _definition(
                R7C_SECURE_CHANNEL_METRIC_ID,
                requires=(CAP_R7C_SECURE_CHANNEL,),
            ),
            _definition(
                R7C_SUBSCRIPTION_METRIC_ID,
                requires=(CAP_R7C_SUBSCRIPTION,),
            ),
            _definition(
                R7C_ZERO_WRITE_METRIC_ID,
                requires=(CAP_R7C_ZERO_WRITE,),
            ),
            _definition(
                R7C_VENDOR_ADAPTER_METRIC_ID,
                requires=(CAP_R7C_VENDOR_ADAPTER,),
            ),
            _definition(
                R7C_REALITY_METRIC_ID,
                requires=(CAP_R7C_VENDOR_ADAPTER, CAP_R7C_TRANSPORT_EVIDENCE),
                claim_id=R7C_REALITY_CLAIM_ID,
                predicate=(
                    "A selected controller has independently verified real deployment "
                    "Shadow evidence."
                ),
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            R7C_CONTRACT_CLAIM_ID,
            R7C_VIRTUAL_TRANSPORT_CLAIM_ID,
            R7C_REALITY_CLAIM_ID,
        ),
        failureMappings=(
            FailureMapping(
                code="MalformedEvaluationRequest",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
            FailureMapping(
                code="OpcUaTransportAuditMismatch",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
        ),
    )
)

_DEFINITIONS = {
    definition.metric_id: definition for definition in R7C_DOMAIN_PACK.metric_definitions
}


def _parse_request(request: CoreEvaluationRequest) -> R7CEvaluationRequest:
    payload = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return R7CEvaluationRequest.model_validate(payload)


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


def _provenance(request: R7CEvaluationRequest) -> Provenance:
    context_hashes: dict[str, str] | None = None
    if request.transport_evidence is not None:
        transport = request.transport_evidence
        context_hashes = {
            "transportEvidence": transport.content_hash,
            "configFile": transport.config_file_sha256,
            "serverCertificate": transport.endpoint.server_certificate_sha256,
            "clientCertificate": transport.endpoint.client_certificate_sha256,
            "transcript": transport.receipt.transcript_content_hash,
        }
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=R7C_RUNNER_ID,
        evaluatorVersion=R7C_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment={
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "pydantic": package_version("pydantic"),
        },
        contextHashes=context_hashes,
    )


def _unsupported(metric_id: str, *, current_platform: str) -> MetricResult:
    return _result(
        metric_id,
        status=MetricStatus.UNSUPPORTED_CAPABILITY,
        reason_code="UnsupportedRuntimePlatform",
        details={"supportedPlatforms": ["Windows"], "currentPlatform": current_platform},
    )


def _check_result(
    metric_id: str,
    *,
    check: Any,
    evidence_level: str = "Validated",
) -> MetricResult:
    if check.status == "Passed":
        return _result(
            metric_id,
            status=MetricStatus.COMPUTED,
            value=True,
            details=check.details,
            evidence=Evidence(
                level=evidence_level,
                method=f"{metric_id}.typed-evidence-check@1",
            ),
        )
    if check.status == "Blocked":
        return _result(
            metric_id,
            status=MetricStatus.COMPUTED,
            value=False,
            reason_code=check.reason_code,
            details=check.details,
            evidence=Evidence(
                level="Validated", method=f"{metric_id}.typed-evidence-check@1"
            ),
        )
    return _result(
        metric_id,
        status=MetricStatus.INSUFFICIENT_CONTEXT,
        reason_code=check.reason_code,
        details=check.details,
    )


def _invalid_report(
    request: R7CEvaluationRequest, *, reason_code: str, message: str
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
            evaluatorVersion=R7C_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


def evaluate_r7c_opcua_transport(request: R7CEvaluationRequest) -> EvaluationReport:
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
                evaluatorVersion=R7C_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay = assess_r7c_opcua_transport(request.transport_evidence)
    if replay.content_hash != request.artifact.content_hash or replay != request.artifact:
        return _invalid_report(
            request,
            reason_code="OpcUaTransportAuditMismatch",
            message=(
                "The submitted R7-C readiness audit does not match deterministic "
                "transport evidence assessment."
            ),
        )

    checks = {check.check_id: check for check in replay.checks}
    evaluated = {
        R7C_CONTRACT_METRIC_ID: _check_result(
            R7C_CONTRACT_METRIC_ID, check=checks["r7c.contract"]
        ),
        R7C_VIRTUAL_TRANSPORT_METRIC_ID: _check_result(
            R7C_VIRTUAL_TRANSPORT_METRIC_ID,
            check=checks["r7c.transport-evidence"],
            evidence_level="Observed",
        ),
        R7C_SECURE_CHANNEL_METRIC_ID: _check_result(
            R7C_SECURE_CHANNEL_METRIC_ID,
            check=checks["r7c.secure-channel"],
            evidence_level="Observed",
        ),
        R7C_SUBSCRIPTION_METRIC_ID: _check_result(
            R7C_SUBSCRIPTION_METRIC_ID,
            check=checks["r7c.subscription-integrity"],
            evidence_level="Observed",
        ),
        R7C_ZERO_WRITE_METRIC_ID: _check_result(
            R7C_ZERO_WRITE_METRIC_ID,
            check=checks["r7c.zero-write"],
            evidence_level="Observed",
        ),
        R7C_VENDOR_ADAPTER_METRIC_ID: _check_result(
            R7C_VENDOR_ADAPTER_METRIC_ID, check=checks["r7c.vendor-adapter"]
        ),
        R7C_REALITY_METRIC_ID: _result(
            R7C_REALITY_METRIC_ID,
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
        CapabilityResolution(capabilityId=CAP_R7C_CONTRACT, source="Evaluator")
    ]
    if request.transport_evidence is not None:
        capabilities.extend(
            (
                CapabilityResolution(
                    capabilityId=CAP_R7C_TRANSPORT_EVIDENCE, source="Artifact"
                ),
                CapabilityResolution(
                    capabilityId=CAP_R7C_SECURE_CHANNEL, source="Adapter"
                ),
                CapabilityResolution(
                    capabilityId=CAP_R7C_SUBSCRIPTION, source="Adapter"
                ),
                CapabilityResolution(capabilityId=CAP_R7C_ZERO_WRITE, source="Adapter"),
            )
        )
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(results[:required_count]),
            metricResults=results,
            capabilities=capabilities,
            contentHash="",
            evaluatorVersion=R7C_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R7C_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R7C_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_r7c_opcua_transport,
    )
)


__all__ = [
    "R7C_CONTRACT_CLAIM_ID",
    "R7C_CONTRACT_METRIC_ID",
    "R7C_DOMAIN_PACK",
    "R7C_REALITY_CLAIM_ID",
    "R7C_REALITY_METRIC_ID",
    "R7C_RUNTIME_BINDING",
    "R7C_SECURE_CHANNEL_METRIC_ID",
    "R7C_SUBSCRIPTION_METRIC_ID",
    "R7C_VENDOR_ADAPTER_METRIC_ID",
    "R7C_VIRTUAL_TRANSPORT_CLAIM_ID",
    "R7C_VIRTUAL_TRANSPORT_METRIC_ID",
    "R7C_ZERO_WRITE_METRIC_ID",
    "evaluate_r7c_opcua_transport",
]
