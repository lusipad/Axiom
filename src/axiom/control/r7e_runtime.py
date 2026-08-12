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
from .r7e_models import (
    R7E_DOMAIN_PACK_ID,
    R7E_EVALUATOR_ID,
    R7E_RUNNER_ID,
    R7EEvaluationRequest,
)
from .r7e_scenarios import assess_r7e_shadow

R7E_CONTRACT_METRIC_ID = "control.beckhoff-shadow-contract@1"
R7E_VENDOR_RUNTIME_METRIC_ID = "control.beckhoff-shadow-vendor-runtime@1"
R7E_WITNESS_PROFILE_METRIC_ID = "control.beckhoff-shadow-witness-profile@1"
R7E_AUTHORITY_METRIC_ID = "control.beckhoff-shadow-readonly-authority@1"
R7E_COVERAGE_METRIC_ID = "control.beckhoff-shadow-sample-index-coverage@1"
R7E_TIMESTAMP_METRIC_ID = "control.beckhoff-shadow-timestamp-integrity@1"
R7E_ZERO_WRITE_METRIC_ID = "control.beckhoff-shadow-zero-write@1"
R7E_DEPLOYMENT_SHADOW_METRIC_ID = "control.beckhoff-deployment-shadow@1"
R7E_REALITY_METRIC_ID = "control.beckhoff-deployment-reality@2"

R7E_CONTRACT_CLAIM_ID = "control.beckhoff-shadow-contract-claim@1"
R7E_DEPLOYMENT_SHADOW_CLAIM_ID = "control.beckhoff-deployment-shadow-claim@1"
R7E_REALITY_CLAIM_ID = "control.beckhoff-deployment-reality-claim@2"

CAP_R7E_CONTRACT = "control.beckhoff.shadow-witness-contract@1"
CAP_R7E_VENDOR_RUNTIME = "control.beckhoff.vendor-runtime@1"
CAP_R7E_WITNESS_PROFILE = "control.beckhoff.shadow-witness-profile@1"
CAP_R7E_AUTHORITY = "control.beckhoff.readonly-authority@1"
CAP_R7E_COMMAND = "five-axis.m5-discrete-command@1"
CAP_R7E_SHADOW_EVIDENCE = "control.beckhoff.shadow-run-evidence@1"

_METRIC_IDS = (
    R7E_CONTRACT_METRIC_ID,
    R7E_VENDOR_RUNTIME_METRIC_ID,
    R7E_WITNESS_PROFILE_METRIC_ID,
    R7E_AUTHORITY_METRIC_ID,
    R7E_COVERAGE_METRIC_ID,
    R7E_TIMESTAMP_METRIC_ID,
    R7E_ZERO_WRITE_METRIC_ID,
    R7E_DEPLOYMENT_SHADOW_METRIC_ID,
    R7E_REALITY_METRIC_ID,
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


R7E_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R7E_DOMAIN_PACK_ID,
        artifactType="axiom.control.beckhoff-shadow-run-readiness",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.control.beckhoff-shadow-run-readiness",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.beckhoff-shadow-witness-profile",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.beckhoff-shadow-run-evidence",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m5-discrete-command",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R7E_EVALUATOR_ID,
        runnerId=R7E_RUNNER_ID,
        runnerIds=(R7E_RUNNER_ID,),
        importRunnerIds=(R7E_RUNNER_ID,),
        capabilityIds=(
            CAP_R7E_CONTRACT,
            CAP_R7E_VENDOR_RUNTIME,
            CAP_R7E_WITNESS_PROFILE,
            CAP_R7E_AUTHORITY,
            CAP_R7E_COMMAND,
            CAP_R7E_SHADOW_EVIDENCE,
        ),
        metricDefinitions=(
            _definition(
                R7E_CONTRACT_METRIC_ID,
                requires=(CAP_R7E_CONTRACT,),
                claim_id=R7E_CONTRACT_CLAIM_ID,
                predicate=(
                    "The Windows Beckhoff sample-index-triggered read-only Shadow "
                    "witness contract is valid."
                ),
            ),
            _definition(
                R7E_VENDOR_RUNTIME_METRIC_ID,
                requires=(CAP_R7E_VENDOR_RUNTIME,),
            ),
            _definition(
                R7E_WITNESS_PROFILE_METRIC_ID,
                requires=(CAP_R7E_WITNESS_PROFILE,),
            ),
            _definition(R7E_AUTHORITY_METRIC_ID, requires=(CAP_R7E_AUTHORITY,)),
            _definition(
                R7E_COVERAGE_METRIC_ID,
                requires=(CAP_R7E_COMMAND, CAP_R7E_SHADOW_EVIDENCE),
            ),
            _definition(
                R7E_TIMESTAMP_METRIC_ID,
                requires=(CAP_R7E_SHADOW_EVIDENCE,),
            ),
            _definition(
                R7E_ZERO_WRITE_METRIC_ID,
                requires=(CAP_R7E_SHADOW_EVIDENCE,),
            ),
            _definition(
                R7E_DEPLOYMENT_SHADOW_METRIC_ID,
                requires=(
                    CAP_R7E_VENDOR_RUNTIME,
                    CAP_R7E_WITNESS_PROFILE,
                    CAP_R7E_AUTHORITY,
                    CAP_R7E_COMMAND,
                    CAP_R7E_SHADOW_EVIDENCE,
                ),
                claim_id=R7E_DEPLOYMENT_SHADOW_CLAIM_ID,
                predicate=(
                    "One bound controller and M5 command have complete, authorized, "
                    "read-only real Shadow capture evidence."
                ),
            ),
            _definition(
                R7E_REALITY_METRIC_ID,
                requires=(CAP_R7E_SHADOW_EVIDENCE,),
                claim_id=R7E_REALITY_CLAIM_ID,
                predicate=(
                    "An independently calibrated physical model passed a disjoint real "
                    "controller holdout run."
                ),
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            R7E_CONTRACT_CLAIM_ID,
            R7E_DEPLOYMENT_SHADOW_CLAIM_ID,
            R7E_REALITY_CLAIM_ID,
        ),
        failureMappings=(
            FailureMapping(
                code="MalformedEvaluationRequest",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
            FailureMapping(
                code="BeckhoffShadowReadinessAuditMismatch",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
        ),
    )
)

_DEFINITIONS = {
    definition.metric_id: definition for definition in R7E_DOMAIN_PACK.metric_definitions
}


def _parse_request(request: CoreEvaluationRequest) -> R7EEvaluationRequest:
    payload = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return R7EEvaluationRequest.model_validate(payload)


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


def _provenance(request: R7EEvaluationRequest) -> Provenance:
    context_hashes = {
        "vendorProfile": request.vendor_profile.content_hash,
        "witnessProfile": request.witness_profile.content_hash,
    }
    support = {
        "runtimeEvidence": request.runtime_evidence,
        "controllerProfile": request.controller_profile,
        "authority": request.authority,
        "captureAuthorization": request.capture_authorization,
        "shadowEvidence": request.shadow_evidence,
    }
    for key, value in support.items():
        if value is not None:
            context_hashes[key] = value.content_hash
    if request.command is not None:
        context_hashes["m5Command"] = request.command.content_id
    if request.shadow_evidence is not None:
        context_hashes["captureTranscript"] = (
            request.shadow_evidence.receipt.transcript_content_hash
        )
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=R7E_RUNNER_ID,
        evaluatorVersion=R7E_EVALUATOR_ID,
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
    metric_id: str, *, check: Any, evidence_level: str = "Observed"
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


def _invalid_report(
    request: R7EEvaluationRequest, *, reason_code: str, message: str
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
            evaluatorVersion=R7E_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


def evaluate_r7e_shadow(request: R7EEvaluationRequest) -> EvaluationReport:
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
                evaluatorVersion=R7E_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay = assess_r7e_shadow(
        request.vendor_profile,
        request.runtime_evidence,
        request.witness_profile,
        request.controller_profile,
        request.authority,
        request.capture_authorization,
        request.command,
        request.shadow_evidence,
    )
    if replay.content_hash != request.artifact.content_hash or replay != request.artifact:
        return _invalid_report(
            request,
            reason_code="BeckhoffShadowReadinessAuditMismatch",
            message=(
                "The submitted R7-E audit does not match deterministic Beckhoff "
                "Shadow evidence assessment."
            ),
        )

    checks = {check.check_id: check for check in replay.checks}
    evaluated = {
        R7E_CONTRACT_METRIC_ID: _check_result(
            R7E_CONTRACT_METRIC_ID,
            check=checks["r7e.contract"],
            evidence_level="Validated",
        ),
        R7E_VENDOR_RUNTIME_METRIC_ID: _check_result(
            R7E_VENDOR_RUNTIME_METRIC_ID, check=checks["r7e.vendor-runtime"]
        ),
        R7E_WITNESS_PROFILE_METRIC_ID: _check_result(
            R7E_WITNESS_PROFILE_METRIC_ID, check=checks["r7e.witness-profile"]
        ),
        R7E_AUTHORITY_METRIC_ID: _check_result(
            R7E_AUTHORITY_METRIC_ID, check=checks["r7e.authority"]
        ),
        R7E_COVERAGE_METRIC_ID: _check_result(
            R7E_COVERAGE_METRIC_ID, check=checks["r7e.frame-coverage"]
        ),
        R7E_TIMESTAMP_METRIC_ID: _check_result(
            R7E_TIMESTAMP_METRIC_ID, check=checks["r7e.timestamp-integrity"]
        ),
        R7E_ZERO_WRITE_METRIC_ID: _check_result(
            R7E_ZERO_WRITE_METRIC_ID, check=checks["r7e.zero-write"]
        ),
        R7E_DEPLOYMENT_SHADOW_METRIC_ID: _check_result(
            R7E_DEPLOYMENT_SHADOW_METRIC_ID,
            check=checks["r7e.deployment-shadow"],
        ),
        R7E_REALITY_METRIC_ID: _result(
            R7E_REALITY_METRIC_ID,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reason_code="R4RealityAlignmentRequired",
            details={
                "deploymentShadowStatus": replay.deployment_shadow_status,
                "realityValidationStatus": "Open",
                "requiredIndependentRuns": 2,
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
        CapabilityResolution(capabilityId=CAP_R7E_CONTRACT, source="Evaluator"),
        CapabilityResolution(capabilityId=CAP_R7E_WITNESS_PROFILE, source="Profile"),
    ]
    if request.runtime_evidence is not None:
        capabilities.append(
            CapabilityResolution(capabilityId=CAP_R7E_VENDOR_RUNTIME, source="Artifact")
        )
    if request.authority is not None:
        capabilities.append(
            CapabilityResolution(capabilityId=CAP_R7E_AUTHORITY, source="Profile")
        )
    if request.command is not None:
        capabilities.append(
            CapabilityResolution(capabilityId=CAP_R7E_COMMAND, source="Artifact")
        )
    if request.shadow_evidence is not None:
        capabilities.append(
            CapabilityResolution(capabilityId=CAP_R7E_SHADOW_EVIDENCE, source="Artifact")
        )
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(results[:required_count]),
            metricResults=results,
            capabilities=capabilities,
            contentHash="",
            evaluatorVersion=R7E_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R7E_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R7E_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_r7e_shadow,
    )
)


__all__ = [
    "R7E_CONTRACT_CLAIM_ID",
    "R7E_CONTRACT_METRIC_ID",
    "R7E_DEPLOYMENT_SHADOW_CLAIM_ID",
    "R7E_DEPLOYMENT_SHADOW_METRIC_ID",
    "R7E_DOMAIN_PACK",
    "R7E_REALITY_CLAIM_ID",
    "R7E_REALITY_METRIC_ID",
    "R7E_RUNTIME_BINDING",
    "evaluate_r7e_shadow",
]
