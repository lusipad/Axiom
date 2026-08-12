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
from .r7d_models import (
    R7DEvaluationRequest,
    R7D_DOMAIN_PACK_ID,
    R7D_EVALUATOR_ID,
    R7D_RUNNER_ID,
)
from .r7d_scenarios import assess_r7d_beckhoff

R7D_PROFILE_METRIC_ID = "control.beckhoff-profile-contract@1"
R7D_RUNTIME_METRIC_ID = "control.beckhoff-runtime-conformance@1"
R7D_INSTALLATION_METRIC_ID = "control.beckhoff-installation@1"
R7D_LICENSE_METRIC_ID = "control.beckhoff-license@1"
R7D_SERVER_IDENTITY_METRIC_ID = "control.beckhoff-server-identity@1"
R7D_NODE_MAPPING_METRIC_ID = "control.beckhoff-node-mapping@1"
R7D_READONLY_METRIC_ID = "control.beckhoff-readonly-enforcement@1"
R7D_TRANSPORT_METRIC_ID = "control.beckhoff-transport@1"
R7D_REALITY_METRIC_ID = "control.beckhoff-deployment-reality@1"

R7D_PROFILE_CLAIM_ID = "control.beckhoff-profile-contract-claim@1"
R7D_RUNTIME_CLAIM_ID = "control.beckhoff-runtime-conformance-claim@1"
R7D_REALITY_CLAIM_ID = "control.beckhoff-deployment-reality-claim@1"

CAP_R7D_PROFILE = "control.beckhoff.vendor-profile@1"
CAP_R7D_INSTALLATION = "control.beckhoff.installation-receipt@1"
CAP_R7D_LICENSE = "control.beckhoff.license-receipt@1"
CAP_R7D_SERVER_IDENTITY = "control.beckhoff.server-identity@1"
CAP_R7D_NODE_MAPPING = "control.beckhoff.node-mapping@1"
CAP_R7D_READONLY = "control.beckhoff.readonly-enforcement@1"
CAP_R7D_TRANSPORT = "control.beckhoff.transport-evidence@1"

_METRIC_IDS = (
    R7D_PROFILE_METRIC_ID,
    R7D_RUNTIME_METRIC_ID,
    R7D_INSTALLATION_METRIC_ID,
    R7D_LICENSE_METRIC_ID,
    R7D_SERVER_IDENTITY_METRIC_ID,
    R7D_NODE_MAPPING_METRIC_ID,
    R7D_READONLY_METRIC_ID,
    R7D_TRANSPORT_METRIC_ID,
    R7D_REALITY_METRIC_ID,
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


R7D_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R7D_DOMAIN_PACK_ID,
        artifactType="axiom.control.beckhoff-vendor-readiness",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.control.beckhoff-vendor-readiness",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.beckhoff-twincat-profile",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.beckhoff-runtime-evidence",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.opcua-transport-evidence",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R7D_EVALUATOR_ID,
        runnerId=R7D_RUNNER_ID,
        runnerIds=(R7D_RUNNER_ID,),
        importRunnerIds=(R7D_RUNNER_ID,),
        capabilityIds=(
            CAP_R7D_PROFILE,
            CAP_R7D_INSTALLATION,
            CAP_R7D_LICENSE,
            CAP_R7D_SERVER_IDENTITY,
            CAP_R7D_NODE_MAPPING,
            CAP_R7D_READONLY,
            CAP_R7D_TRANSPORT,
        ),
        metricDefinitions=(
            _definition(
                R7D_PROFILE_METRIC_ID,
                requires=(CAP_R7D_PROFILE,),
                claim_id=R7D_PROFILE_CLAIM_ID,
                predicate=(
                    "The Windows-only Beckhoff TwinCAT 3 Build 4026+ / TF6100 "
                    "Vendor Profile contract is valid."
                ),
            ),
            _definition(
                R7D_RUNTIME_METRIC_ID,
                requires=(
                    CAP_R7D_INSTALLATION,
                    CAP_R7D_LICENSE,
                    CAP_R7D_SERVER_IDENTITY,
                    CAP_R7D_NODE_MAPPING,
                    CAP_R7D_READONLY,
                    CAP_R7D_TRANSPORT,
                ),
                claim_id=R7D_RUNTIME_CLAIM_ID,
                predicate=(
                    "One bound Beckhoff TwinCAT runtime passed installation, license, "
                    "server identity, node mapping, read-only and transport checks."
                ),
            ),
            _definition(
                R7D_INSTALLATION_METRIC_ID, requires=(CAP_R7D_INSTALLATION,)
            ),
            _definition(R7D_LICENSE_METRIC_ID, requires=(CAP_R7D_LICENSE,)),
            _definition(
                R7D_SERVER_IDENTITY_METRIC_ID,
                requires=(CAP_R7D_SERVER_IDENTITY,),
            ),
            _definition(
                R7D_NODE_MAPPING_METRIC_ID, requires=(CAP_R7D_NODE_MAPPING,)
            ),
            _definition(R7D_READONLY_METRIC_ID, requires=(CAP_R7D_READONLY,)),
            _definition(R7D_TRANSPORT_METRIC_ID, requires=(CAP_R7D_TRANSPORT,)),
            _definition(
                R7D_REALITY_METRIC_ID,
                requires=(CAP_R7D_TRANSPORT,),
                claim_id=R7D_REALITY_CLAIM_ID,
                predicate=(
                    "A bound Beckhoff deployment has independent case-scoped real "
                    "Shadow capture evidence."
                ),
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            R7D_PROFILE_CLAIM_ID,
            R7D_RUNTIME_CLAIM_ID,
            R7D_REALITY_CLAIM_ID,
        ),
        failureMappings=(
            FailureMapping(
                code="MalformedEvaluationRequest",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
            FailureMapping(
                code="BeckhoffReadinessAuditMismatch",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
        ),
    )
)

_DEFINITIONS = {
    definition.metric_id: definition for definition in R7D_DOMAIN_PACK.metric_definitions
}


def _parse_request(request: CoreEvaluationRequest) -> R7DEvaluationRequest:
    payload = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return R7DEvaluationRequest.model_validate(payload)


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


def _provenance(request: R7DEvaluationRequest) -> Provenance:
    context_hashes = {"vendorProfile": request.profile.content_hash}
    if request.runtime_evidence is not None:
        evidence = request.runtime_evidence
        context_hashes.update(
            {
                "runtimeEvidence": evidence.content_hash,
                "profileFile": evidence.profile_file_sha256,
                "verifierBinary": evidence.verifier_binary_sha256,
            }
        )
        if evidence.server_identity is not None:
            context_hashes["serverCertificate"] = (
                evidence.server_identity.server_certificate_sha256
            )
    if request.transport_evidence is not None:
        context_hashes.update(
            {
                "transportEvidence": request.transport_evidence.content_hash,
                "transportTranscript": (
                    request.transport_evidence.receipt.transcript_content_hash
                ),
            }
        )
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=R7D_RUNNER_ID,
        evaluatorVersion=R7D_EVALUATOR_ID,
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
    metric_id: str, *, check: Any, evidence_level: str = "Validated"
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
                level=evidence_level,
                method=f"{metric_id}.typed-evidence-check@1",
            ),
        )
    return _result(
        metric_id,
        status=MetricStatus.INSUFFICIENT_CONTEXT,
        reason_code=check.reason_code,
        details=check.details,
    )


def _runtime_result(request: R7DEvaluationRequest) -> MetricResult:
    audit = request.artifact
    details = {
        "vendorRuntimeStatus": audit.vendor_runtime_status,
        "profileContentHash": audit.profile_content_hash,
        "runtimeEvidenceContentHash": audit.runtime_evidence_content_hash,
        "countsTowardReality": False,
    }
    if audit.vendor_runtime_status == "Passed":
        return _result(
            R7D_RUNTIME_METRIC_ID,
            status=MetricStatus.COMPUTED,
            value=True,
            details=details,
            evidence=Evidence(
                level="Observed",
                method="control.beckhoff-runtime-conformance@1.imported-verifier-receipt",
            ),
        )
    if audit.vendor_runtime_status == "Blocked":
        return _result(
            R7D_RUNTIME_METRIC_ID,
            status=MetricStatus.COMPUTED,
            value=False,
            reason_code="BeckhoffVendorRuntimeBlocked",
            details=details,
            evidence=Evidence(
                level="Observed",
                method="control.beckhoff-runtime-conformance@1.imported-verifier-receipt",
            ),
        )
    return _result(
        R7D_RUNTIME_METRIC_ID,
        status=MetricStatus.INSUFFICIENT_CONTEXT,
        reason_code="BeckhoffVendorRuntimeEvidenceOpen",
        details=details,
    )


def _invalid_report(
    request: R7DEvaluationRequest, *, reason_code: str, message: str
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
            evaluatorVersion=R7D_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


def evaluate_r7d_beckhoff(request: R7DEvaluationRequest) -> EvaluationReport:
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
                evaluatorVersion=R7D_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay = assess_r7d_beckhoff(
        request.profile, request.runtime_evidence, request.transport_evidence
    )
    if replay.content_hash != request.artifact.content_hash or replay != request.artifact:
        return _invalid_report(
            request,
            reason_code="BeckhoffReadinessAuditMismatch",
            message=(
                "The submitted R7-D readiness audit does not match deterministic "
                "Beckhoff evidence assessment."
            ),
        )

    checks = {check.check_id: check for check in replay.checks}
    evaluated = {
        R7D_PROFILE_METRIC_ID: _check_result(
            R7D_PROFILE_METRIC_ID, check=checks["r7d.profile"]
        ),
        R7D_RUNTIME_METRIC_ID: _runtime_result(request),
        R7D_INSTALLATION_METRIC_ID: _check_result(
            R7D_INSTALLATION_METRIC_ID,
            check=checks["r7d.installation"],
            evidence_level="Observed",
        ),
        R7D_LICENSE_METRIC_ID: _check_result(
            R7D_LICENSE_METRIC_ID,
            check=checks["r7d.license"],
            evidence_level="Observed",
        ),
        R7D_SERVER_IDENTITY_METRIC_ID: _check_result(
            R7D_SERVER_IDENTITY_METRIC_ID,
            check=checks["r7d.server-identity"],
            evidence_level="Observed",
        ),
        R7D_NODE_MAPPING_METRIC_ID: _check_result(
            R7D_NODE_MAPPING_METRIC_ID,
            check=checks["r7d.node-mapping"],
            evidence_level="Observed",
        ),
        R7D_READONLY_METRIC_ID: _check_result(
            R7D_READONLY_METRIC_ID,
            check=checks["r7d.readonly-enforcement"],
            evidence_level="Observed",
        ),
        R7D_TRANSPORT_METRIC_ID: _check_result(
            R7D_TRANSPORT_METRIC_ID,
            check=checks["r7d.transport"],
            evidence_level="Observed",
        ),
        R7D_REALITY_METRIC_ID: _result(
            R7D_REALITY_METRIC_ID,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reason_code="RealDeploymentCaptureMissing",
            details={
                "vendorRuntimeStatus": replay.vendor_runtime_status,
                "deploymentShadowStatus": replay.deployment_shadow_status,
                "realityValidationStatus": replay.reality_validation_status,
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
        CapabilityResolution(capabilityId=CAP_R7D_PROFILE, source="Profile")
    ]
    if request.runtime_evidence is not None:
        capabilities.extend(
            (
                CapabilityResolution(
                    capabilityId=CAP_R7D_INSTALLATION, source="Artifact"
                ),
                CapabilityResolution(capabilityId=CAP_R7D_LICENSE, source="Profile"),
                CapabilityResolution(
                    capabilityId=CAP_R7D_READONLY, source="Adapter"
                ),
            )
        )
        if request.runtime_evidence.server_identity is not None:
            capabilities.append(
                CapabilityResolution(
                    capabilityId=CAP_R7D_SERVER_IDENTITY, source="Adapter"
                )
            )
        if request.runtime_evidence.channel_access is not None:
            capabilities.append(
                CapabilityResolution(
                    capabilityId=CAP_R7D_NODE_MAPPING, source="Adapter"
                )
            )
    if request.transport_evidence is not None:
        capabilities.append(
            CapabilityResolution(capabilityId=CAP_R7D_TRANSPORT, source="Artifact")
        )
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(results[:required_count]),
            metricResults=results,
            capabilities=capabilities,
            contentHash="",
            evaluatorVersion=R7D_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R7D_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R7D_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_r7d_beckhoff,
    )
)


__all__ = [
    "R7D_DOMAIN_PACK",
    "R7D_PROFILE_CLAIM_ID",
    "R7D_PROFILE_METRIC_ID",
    "R7D_REALITY_CLAIM_ID",
    "R7D_REALITY_METRIC_ID",
    "R7D_RUNTIME_BINDING",
    "R7D_RUNTIME_CLAIM_ID",
    "R7D_RUNTIME_METRIC_ID",
    "evaluate_r7d_beckhoff",
]
