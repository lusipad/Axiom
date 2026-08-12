from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

from ..models import AxiomModel, RunSpec
from .models import canonical_hash
from .r7b_models import (
    R7B_DEFAULT_SCENARIO_ID,
    R7B_DOMAIN_PACK_ID,
    R7B_EVALUATOR_ID,
    R7B_RUNNER_ID,
    R7B_SCENARIO_IDS,
    ClockSignalBinding,
    DeploymentAdapterReceipt,
    DeploymentControllerProfile,
    DeploymentShadowCapture,
    DeploymentShadowEvidenceSet,
    DeploymentShadowReadinessAudit,
    ExternalEvidenceProvenance,
    R7BAssessmentRequest,
    R7BExamplePayload,
    R7BManifest,
    R7BReadinessCheck,
    R7BScenario,
    R7BScenarioSummary,
    ReadOnlyAuthorityEvidence,
)


def _sealed[ModelT: AxiomModel](
    model_type: type[ModelT], payload: dict[str, Any]
) -> ModelT:
    sealed = {**payload, "contentHash": canonical_hash(payload)}
    return model_type.model_validate(sealed)


def build_r7b_manifest() -> R7BManifest:
    return R7BManifest(
        manifestId="control.r7b-manifest@1",
        domainPackId=R7B_DOMAIN_PACK_ID,
        evaluatorVersion=R7B_EVALUATOR_ID,
        runnerId=R7B_RUNNER_ID,
        supportedPlatforms=("Windows",),
        defaultScenarioId=R7B_DEFAULT_SCENARIO_ID,
        scenarioIds=R7B_SCENARIO_IDS,
        permissionCeiling="Shadow",
        deviceWriteAllowed=False,
        contractReadinessStatus="Passed",
        vendorAdapterStatus="Open",
        deploymentShadowStatus="Open",
        controlledTrialStatus="Open",
        closedLoopStatus="Open",
    )


def r7b_contract_fixture_evidence() -> DeploymentShadowEvidenceSet:
    profile = _sealed(
        DeploymentControllerProfile,
        {
            "profileId": "control.r7b.contract-controller-profile@1",
            "vendor": "ContractFixture",
            "controllerFamily": "unselected",
            "controllerModel": "unselected",
            "softwareVersion": "unselected",
            "machineId": "contract-fixture-machine",
            "interfaceType": "controller-export",
            "targetStatus": "Unselected",
        },
    )
    authority = _sealed(
        ReadOnlyAuthorityEvidence,
        {
            "evidenceId": "control.r7b.contract-authority@1",
            "controllerProfileContentHash": profile.content_hash,
            "principalId": "contract-fixture-principal",
            "enforcementPoint": "controller",
            "grantedOperations": ["read", "subscribe"],
            "deniedOperations": [
                "parameter-write",
                "program-transfer",
                "cycle-start",
                "feed-hold",
                "reset",
                "jog",
                "safety-bypass",
            ],
            "attestationKind": "unverified-contract-fixture",
            "attestationContentHash": "1" * 64,
            "verificationStatus": "Unverified",
        },
    )
    capture = _sealed(
        DeploymentShadowCapture,
        {
            "artifactType": "axiom.control.deployment-shadow-capture",
            "schemaVersion": 1,
            "captureId": "control.r7b.contract-capture@1",
            "sourceKind": "contract-fixture",
            "declaredReal": False,
            "controllerProfileContentHash": profile.content_hash,
            "frames": [
                {
                    "sequence": 0,
                    "controllerTimestamp": "2026-08-12T00:00:00+00:00",
                    "hostTimestamp": "2026-08-12T00:00:00.001000+00:00",
                    "samples": [
                        {
                            "channelId": "axis.X.actual",
                            "value": 0.0,
                            "unit": "mm",
                            "quality": "good",
                        },
                        {
                            "channelId": "controller.state",
                            "value": "Idle",
                            "quality": "good",
                        },
                    ],
                },
                {
                    "sequence": 1,
                    "controllerTimestamp": "2026-08-12T00:00:00.010000+00:00",
                    "hostTimestamp": "2026-08-12T00:00:00.011000+00:00",
                    "samples": [
                        {
                            "channelId": "axis.X.actual",
                            "value": 0.1,
                            "unit": "mm",
                            "quality": "good",
                        },
                        {
                            "channelId": "controller.state",
                            "value": "Idle",
                            "quality": "good",
                        },
                    ],
                },
            ],
        },
    )
    binding = _sealed(
        ClockSignalBinding,
        {
            "bindingId": "control.r7b.contract-clock-signal@1",
            "controllerProfileContentHash": profile.content_hash,
            "clockMethod": "contract-fixture",
            "maximumTimestampUncertaintyMs": 1.0,
            "maximumObservedGapMs": 10.0,
            "requiredMaximumGapMs": 20.0,
            "coverageFraction": 1.0,
            "signalMappings": [
                {
                    "sourceChannelId": "axis.X.actual",
                    "canonicalSignalId": "machine.axis.X.position.actual",
                    "quantity": "axis-position",
                    "axisId": "X",
                    "unit": "mm",
                },
                {
                    "sourceChannelId": "controller.state",
                    "canonicalSignalId": "machine.controller.state",
                    "quantity": "controller-state",
                },
            ],
        },
    )
    receipt = _sealed(
        DeploymentAdapterReceipt,
        {
            "receiptId": "control.r7b.contract-adapter-receipt@1",
            "adapterId": "control.r7b.unselected-adapter@1",
            "adapterVersion": "1",
            "platform": "Windows",
            "protocol": "controller-export",
            "accessMode": "read-subscribe-only",
            "controllerProfileContentHash": profile.content_hash,
            "captureContentHash": capture.content_hash,
            "status": "Succeeded",
            "openedAt": "2026-08-12T00:00:00+00:00",
            "closedAt": "2026-08-12T00:00:00.011000+00:00",
            "readOperationCount": 4,
            "writeOperationCount": 0,
            "receivedSampleCount": 4,
            "droppedSampleCount": 0,
            "transcriptContentHash": "2" * 64,
        },
    )
    provenance = _sealed(
        ExternalEvidenceProvenance,
        {
            "provenanceId": "control.r7b.contract-provenance@1",
            "dataOwnerId": "contract-fixture",
            "acquisitionPurpose": "deployment-shadow-validation",
            "capturedOutsideRepository": False,
            "evaluationAuthorized": True,
            "sourceContentHash": capture.content_hash,
        },
    )
    return _sealed(
        DeploymentShadowEvidenceSet,
        {
            "schemaId": "axiom.control.deployment-shadow-evidence-set@1",
            "evidenceSetId": "control.r7b.contract-evidence-set@1",
            "controllerProfile": profile,
            "authority": authority,
            "capture": capture,
            "adapterReceipt": receipt,
            "clockSignalBinding": binding,
            "provenance": provenance,
        },
    )


def assess_r7b_deployment_shadow(
    evidence_set: DeploymentShadowEvidenceSet | None,
) -> DeploymentShadowReadinessAudit:
    checks: list[R7BReadinessCheck] = [
        R7BReadinessCheck(
            checkId="r7b.contract",
            title="R7-B typed contract",
            status="Passed",
            details={"vendorNeutral": True, "deviceWriteAllowed": False},
        )
    ]
    if evidence_set is None:
        checks.extend(
            (
                R7BReadinessCheck(
                    checkId="r7b.external-evidence",
                    title="External real evidence",
                    status="Open",
                    reasonCode="DeploymentShadowEvidenceMissing",
                ),
                R7BReadinessCheck(
                    checkId="r7b.vendor-adapter",
                    title="Versioned vendor adapter",
                    status="Open",
                    reasonCode="VendorAdapterUnselected",
                ),
                R7BReadinessCheck(
                    checkId="r7b.authority",
                    title="Controller-enforced read-only authority",
                    status="Open",
                    reasonCode="AuthorityEvidenceMissing",
                ),
                R7BReadinessCheck(
                    checkId="r7b.capture-integrity",
                    title="Capture and receipt integrity",
                    status="Open",
                    reasonCode="DeploymentShadowCaptureMissing",
                ),
                R7BReadinessCheck(
                    checkId="r7b.clock-signal-coverage",
                    title="Clock and signal coverage",
                    status="Open",
                    reasonCode="ClockSignalBindingMissing",
                ),
            )
        )
    else:
        real_source = (
            evidence_set.capture.source_kind
            in {"controller-live-read", "controller-export"}
            and evidence_set.capture.declared_real
            and evidence_set.provenance.captured_outside_repository
            and evidence_set.provenance.evaluation_authorized
        )
        checks.append(
            R7BReadinessCheck(
                checkId="r7b.external-evidence",
                title="External real evidence",
                status="Passed" if real_source else "Blocked",
                reasonCode=None if real_source else "NonRealEvidenceSource",
                details={"sourceKind": evidence_set.capture.source_kind},
            )
        )
        checks.append(
            R7BReadinessCheck(
                checkId="r7b.vendor-adapter",
                title="Versioned vendor adapter",
                status="Open",
                reasonCode=(
                    "VendorAdapterUnselected"
                    if evidence_set.controller_profile.target_status == "Unselected"
                    else "VendorAdapterVerifierUnavailable"
                ),
                details={
                    "vendor": evidence_set.controller_profile.vendor,
                    "interfaceType": evidence_set.controller_profile.interface_type,
                },
            )
        )
        verified_authority = evidence_set.authority.verification_status == "Verified"
        checks.append(
            R7BReadinessCheck(
                checkId="r7b.authority",
                title="Controller-enforced read-only authority",
                status="Open",
                reasonCode=(
                    "AuthorityVerifierUnavailable"
                    if verified_authority
                    else "AuthorityEvidenceUnverified"
                ),
                details={
                    "enforcementPoint": evidence_set.authority.enforcement_point,
                    "verificationStatus": evidence_set.authority.verification_status,
                },
            )
        )
        capture_ok = (
            evidence_set.adapter_receipt.status == "Succeeded"
            and evidence_set.adapter_receipt.write_operation_count == 0
            and evidence_set.adapter_receipt.dropped_sample_count == 0
            and all(
                sample.quality == "good"
                for frame in evidence_set.capture.frames
                for sample in frame.samples
            )
        )
        checks.append(
            R7BReadinessCheck(
                checkId="r7b.capture-integrity",
                title="Capture and receipt integrity",
                status="Passed" if capture_ok else "Blocked",
                reasonCode=None if capture_ok else "CaptureIntegrityIncomplete",
                details={
                    "receivedSampleCount": evidence_set.adapter_receipt.received_sample_count,
                    "droppedSampleCount": evidence_set.adapter_receipt.dropped_sample_count,
                    "writeOperationCount": evidence_set.adapter_receipt.write_operation_count,
                },
            )
        )
        binding = evidence_set.clock_signal_binding
        clock_signal_ok = (
            binding.coverage_fraction == 1.0
            and binding.maximum_observed_gap_ms <= binding.required_maximum_gap_ms
            and binding.clock_method != "contract-fixture"
        )
        checks.append(
            R7BReadinessCheck(
                checkId="r7b.clock-signal-coverage",
                title="Clock and signal coverage",
                status="Passed" if clock_signal_ok else "Blocked",
                reasonCode=None if clock_signal_ok else "ClockSignalCoverageIncomplete",
                details={
                    "coverageFraction": binding.coverage_fraction,
                    "maximumObservedGapMs": binding.maximum_observed_gap_ms,
                    "requiredMaximumGapMs": binding.required_maximum_gap_ms,
                    "clockMethod": binding.clock_method,
                },
            )
        )

    checks.append(
        R7BReadinessCheck(
            checkId="r7b.reality-gate",
            title="Case-scoped deployment shadow reality gate",
            status="Open",
            reasonCode="RealDeploymentValidationOpen",
            details={
                "requiresVendorVerifier": True,
                "countsTowardReality": False,
            },
        )
    )
    outcome = "Blocked" if any(check.status == "Blocked" for check in checks) else "Open"
    payload: dict[str, Any] = {
        "artifactType": "axiom.control.deployment-shadow-readiness",
        "schemaVersion": 1,
        "auditId": "control.r7b.deployment-shadow-readiness-audit@1",
        "checks": checks,
        "readinessOutcome": outcome,
        "permissionCeiling": "Shadow",
        "deviceWriteAllowed": False,
        "contractReadinessStatus": "Passed",
        "vendorAdapterStatus": "Open",
        "deploymentShadowStatus": "Open",
        "controlledTrialStatus": "Open",
        "closedLoopStatus": "Open",
        "standardsComplianceStatus": "NotAssessed",
        "realityEvidenceLevel": "None",
    }
    if evidence_set is not None:
        payload["evidenceSetContentHash"] = evidence_set.content_hash
    return _sealed(DeploymentShadowReadinessAudit, payload)


def _run_spec(
    audit: DeploymentShadowReadinessAudit,
    evidence_set: DeploymentShadowEvidenceSet | None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "artifact": audit.model_dump(mode="json", by_alias=True, exclude_none=True),
        "case": {
            "caseId": "control.r7b.deployment-shadow-readiness.case@1",
            "requiredMetrics": [
                "control.deployment-shadow-contract-ready@1",
                "control.deployment-shadow-reality@1",
            ],
            "optionalMetrics": [
                "control.deployment-shadow-external-evidence@1",
                "control.deployment-shadow-vendor-adapter@1",
                "control.deployment-shadow-read-only-authority@1",
                "control.deployment-shadow-capture-integrity@1",
                "control.deployment-shadow-clock-signal-coverage@1",
            ],
        },
    }
    if evidence_set is not None:
        request["evidenceSet"] = evidence_set.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    return {
        "subjectId": "axiom.control.deployment-shadow-readiness@1",
        "subjectVersion": "1",
        "domainPackId": R7B_DOMAIN_PACK_ID,
        "runnerId": R7B_RUNNER_ID,
        "evaluatorVersion": R7B_EVALUATOR_ID,
        "request": request,
    }


def _build_scenario(scenario_id: str) -> R7BScenario:
    evidence = (
        None
        if scenario_id == R7B_DEFAULT_SCENARIO_ID
        else r7b_contract_fixture_evidence()
    )
    audit = assess_r7b_deployment_shadow(evidence)
    summary = R7BScenarioSummary(
        scenarioId=scenario_id,
        title=(
            "Deployment Shadow readiness (open)"
            if evidence is None
            else "Contract fixture is blocked from reality promotion"
        ),
        description=(
            "No vendor, controller authority, or external real capture has been supplied."
            if evidence is None
            else "A deterministic contract fixture exercises the schema but cannot count as real deployment evidence."
        ),
        expectedOutcome="Inconclusive",
        expectedReadinessOutcome=audit.readiness_outcome,
        countsTowardReality=False,
    )
    return R7BScenario(
        summary=summary,
        readiness_audit=audit,
        evidence_set=evidence,
        run_spec=_run_spec(audit, evidence),
    )


@lru_cache(maxsize=1)
def _scenarios() -> dict[str, R7BScenario]:
    return {scenario_id: _build_scenario(scenario_id) for scenario_id in R7B_SCENARIO_IDS}


def list_r7b_scenarios() -> tuple[R7BScenarioSummary, ...]:
    return tuple(_scenarios()[scenario_id].summary for scenario_id in R7B_SCENARIO_IDS)


def load_r7b_scenario(
    scenario_id: str = R7B_DEFAULT_SCENARIO_ID,
) -> R7BScenario:
    try:
        return _scenarios()[scenario_id]
    except KeyError as exc:
        expected = ", ".join(R7B_SCENARIO_IDS)
        raise KeyError(f"unknown R7-B scenario '{scenario_id}'; expected: {expected}") from exc


def _payload(
    summary: R7BScenarioSummary,
    evidence_set: DeploymentShadowEvidenceSet | None,
) -> R7BExamplePayload:
    audit = assess_r7b_deployment_shadow(evidence_set)
    run_spec = _run_spec(audit, evidence_set)
    RunSpec.model_validate(run_spec)
    return R7BExamplePayload(
        manifest=build_r7b_manifest(),
        scenario=summary,
        readinessAudit=audit,
        evidenceSet=evidence_set,
        runSpec=run_spec,
    )


def r7b_example_payload(
    scenario_id: str = R7B_DEFAULT_SCENARIO_ID,
) -> R7BExamplePayload:
    scenario = load_r7b_scenario(scenario_id)
    return _payload(scenario.summary, scenario.evidence_set)


def assess_r7b_payload(request: R7BAssessmentRequest) -> R7BExamplePayload:
    summary = R7BScenarioSummary(
        scenarioId="external-evidence-assessment",
        title="External Deployment Shadow evidence assessment",
        description="Submitted evidence is checked without granting device authority or closing the reality gate.",
        expectedOutcome="Inconclusive",
        expectedReadinessOutcome=assess_r7b_deployment_shadow(
            request.evidence_set
        ).readiness_outcome,
        countsTowardReality=False,
    )
    return _payload(summary, request.evidence_set)


def r7b_example_run_spec(
    scenario_id: str = R7B_DEFAULT_SCENARIO_ID,
) -> dict[str, Any]:
    return deepcopy(load_r7b_scenario(scenario_id).run_spec)


def validate_r7b_example_run_spec(
    scenario_id: str = R7B_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r7b_example_run_spec(scenario_id))


__all__ = [
    "assess_r7b_deployment_shadow",
    "assess_r7b_payload",
    "build_r7b_manifest",
    "list_r7b_scenarios",
    "load_r7b_scenario",
    "r7b_contract_fixture_evidence",
    "r7b_example_payload",
    "r7b_example_run_spec",
    "validate_r7b_example_run_spec",
]
