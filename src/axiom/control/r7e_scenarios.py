from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from itertools import pairwise
from typing import Any

from ..models import AxiomModel, RunSpec
from .models import canonical_hash
from .r7b_models import DeploymentControllerProfile, ReadOnlyAuthorityEvidence
from .r7d_models import BeckhoffRuntimeEvidence, BeckhoffTwinCatVendorProfile
from .r7d_scenarios import build_default_beckhoff_profile
from .r7e_models import (
    R7E_DEFAULT_CASE_ID,
    R7E_DEFAULT_SCENARIO_ID,
    R7E_DOMAIN_PACK_ID,
    R7E_EVALUATOR_ID,
    R7E_RUNNER_ID,
    R7E_SCENARIO_IDS,
    BeckhoffShadowCaptureAuthorization,
    BeckhoffShadowRunEvidence,
    BeckhoffShadowRunReadinessAudit,
    BeckhoffShadowWitnessProfile,
    R7EAssessmentRequest,
    R7EExamplePayload,
    R7EManifest,
    R7EReadinessCheck,
    R7EScenario,
    R7EScenarioSummary,
)


def _sealed[ModelT: AxiomModel](
    model_type: type[ModelT], payload: dict[str, Any]
) -> ModelT:
    return model_type.model_validate({**payload, "contentHash": canonical_hash(payload)})


def build_default_beckhoff_shadow_witness_profile(
    vendor_profile: BeckhoffTwinCatVendorProfile | None = None,
) -> BeckhoffShadowWitnessProfile:
    profile = vendor_profile or build_default_beckhoff_profile()
    return _sealed(
        BeckhoffShadowWitnessProfile,
        {
            "schemaId": "axiom.control.beckhoff-shadow-witness-profile@1",
            "profileId": "axiom.control.beckhoff-shadow-witness-default@1",
            "vendorProfileContentHash": profile.content_hash,
            "bindingStatus": "Open",
            "platform": "Windows",
            "protocol": "opc-ua",
            "capturePolicy": "sample-index-triggered-batch-read",
            "intervalPolicy": "exact-sample-index-no-interpolation",
            "maximumTimestampUncertaintyMs": 20.0,
            "maximumSampleIndexGap": 0,
            "nodes": [],
            "permissionCeiling": "Shadow",
            "deviceWriteAllowed": False,
            "methodCallAllowed": False,
        },
    )


def build_r7e_manifest() -> R7EManifest:
    return R7EManifest(
        manifestId="control.r7e-manifest@1",
        domainPackId=R7E_DOMAIN_PACK_ID,
        evaluatorVersion=R7E_EVALUATOR_ID,
        runnerId=R7E_RUNNER_ID,
        adapterId="axiom.control.beckhoff-shadow-witness-adapter@1",
        targetVendor="Beckhoff Automation",
        targetControllerFamily="TwinCAT 3",
        minimumTwinCatBuild=4026,
        targetInterface="TF6100 OPC UA Server",
        supportedPlatforms=("Windows",),
        capturePolicy="sample-index-triggered-batch-read",
        defaultScenarioId=R7E_DEFAULT_SCENARIO_ID,
        scenarioIds=R7E_SCENARIO_IDS,
        permissionCeiling="Shadow",
        deviceWriteAllowed=False,
        deploymentShadowStatus="Open",
        realityValidationStatus="Open",
        deviceSafetyStatus="NotAssessed",
        processSafetyStatus="NotAssessed",
    )


def _open(check_id: str, title: str, reason: str, **details: Any) -> R7EReadinessCheck:
    return R7EReadinessCheck(
        checkId=check_id,
        title=title,
        status="Open",
        reasonCode=reason,
        details=details,
    )


def _blocked(
    check_id: str, title: str, reason: str, **details: Any
) -> R7EReadinessCheck:
    return R7EReadinessCheck(
        checkId=check_id,
        title=title,
        status="Blocked",
        reasonCode=reason,
        details=details,
    )


def _passed(check_id: str, title: str, **details: Any) -> R7EReadinessCheck:
    return R7EReadinessCheck(
        checkId=check_id, title=title, status="Passed", details=details
    )


def _runtime_check(
    vendor_profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
) -> R7EReadinessCheck:
    title = "Bound TwinCAT 3 / TF6100 vendor runtime"
    if runtime_evidence is None:
        return _open("r7e.vendor-runtime", title, "BeckhoffRuntimeEvidenceMissing")
    if runtime_evidence.profile_content_hash != vendor_profile.content_hash:
        return _blocked(
            "r7e.vendor-runtime", title, "RuntimeEvidenceProfileMismatch"
        )
    if runtime_evidence.source_kind != "vendor-runtime":
        return _blocked("r7e.vendor-runtime", title, "ContractFixtureNotVendorRuntime")
    complete = (
        vendor_profile.binding_status == "Bound"
        and runtime_evidence.installation.status == "Passed"
        and runtime_evidence.license.state == "Full"
        and runtime_evidence.server_identity is not None
        and runtime_evidence.channel_access is not None
        and runtime_evidence.write_rejection.status == "Rejected"
        and runtime_evidence.transport_evidence_content_hash is not None
    )
    if not complete:
        return _blocked(
            "r7e.vendor-runtime", title, "BeckhoffVendorRuntimeNotDeploymentReady"
        )
    return _passed(
        "r7e.vendor-runtime",
        title,
        runtimeEvidenceContentHash=runtime_evidence.content_hash,
        licenseState=runtime_evidence.license.state,
    )


def _witness_profile_check(
    vendor_profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    witness_profile: BeckhoffShadowWitnessProfile,
    command_content_hash: str | None,
) -> R7EReadinessCheck:
    title = "Sample-index-triggered Beckhoff witness profile"
    if witness_profile.vendor_profile_content_hash != vendor_profile.content_hash:
        return _blocked("r7e.witness-profile", title, "WitnessVendorProfileMismatch")
    if witness_profile.binding_status == "Open":
        return _open("r7e.witness-profile", title, "WitnessNodeBindingsOpen")
    if runtime_evidence is None or command_content_hash is None:
        return _blocked("r7e.witness-profile", title, "WitnessSupportMissing")
    if (
        witness_profile.runtime_evidence_content_hash != runtime_evidence.content_hash
        or witness_profile.expected_command_content_hash != command_content_hash
    ):
        return _blocked("r7e.witness-profile", title, "WitnessSupportHashMismatch")
    return _passed(
        "r7e.witness-profile",
        title,
        capturePolicy=witness_profile.capture_policy,
        nodeCount=len(witness_profile.nodes),
    )


def _authority_check(
    controller_profile: DeploymentControllerProfile | None,
    authority: ReadOnlyAuthorityEvidence | None,
) -> R7EReadinessCheck:
    title = "Controller-enforced read and subscribe authority"
    if controller_profile is None or authority is None:
        return _open("r7e.authority", title, "ReadOnlyAuthorityEvidenceMissing")
    if authority.controller_profile_content_hash != controller_profile.content_hash:
        return _blocked("r7e.authority", title, "AuthorityControllerProfileMismatch")
    if controller_profile.target_status != "Selected":
        return _blocked("r7e.authority", title, "ControllerTargetNotSelected")
    if (
        authority.verification_status != "Verified"
        or authority.attestation_kind == "unverified-contract-fixture"
        or set(authority.granted_operations) != {"read", "subscribe"}
    ):
        return _blocked("r7e.authority", title, "ReadOnlyAuthorityNotVerified")
    return _passed(
        "r7e.authority",
        title,
        principalId=authority.principal_id,
        enforcementPoint=authority.enforcement_point,
    )


def _command_check(
    command_content_hash: str | None,
    witness_profile: BeckhoffShadowWitnessProfile,
    evidence: BeckhoffShadowRunEvidence | None,
) -> R7EReadinessCheck:
    title = "M5 command content identity"
    if command_content_hash is None:
        return _open("r7e.command-binding", title, "M5DiscreteCommandMissing")
    observed = evidence.command_content_hash if evidence is not None else None
    if (
        witness_profile.expected_command_content_hash != command_content_hash
        or (observed is not None and observed != command_content_hash)
    ):
        return _blocked("r7e.command-binding", title, "CommandContentHashMismatch")
    return _passed(
        "r7e.command-binding", title, commandContentHash=command_content_hash
    )


def _provenance_check(
    evidence: BeckhoffShadowRunEvidence | None,
    capture_authorization: BeckhoffShadowCaptureAuthorization | None,
    controller_profile: DeploymentControllerProfile | None,
    command_content_hash: str | None,
) -> R7EReadinessCheck:
    title = "Independent external controller capture provenance"
    if evidence is None:
        return _open("r7e.external-provenance", title, "ShadowRunEvidenceMissing")
    if evidence.source_kind != "controller-live-read" or not evidence.declared_real:
        return _blocked(
            "r7e.external-provenance", title, "ContractFixtureNotRealControllerCapture"
        )
    if capture_authorization is None:
        return _open(
            "r7e.external-provenance", title, "CaptureAuthorizationMissing"
        )
    if (
        controller_profile is None
        or command_content_hash is None
        or capture_authorization.controller_profile_content_hash
        != controller_profile.content_hash
        or capture_authorization.command_content_hash != command_content_hash
        or evidence.capture_authorization_content_hash
        != capture_authorization.content_hash
    ):
        return _blocked(
            "r7e.external-provenance", title, "CaptureAuthorizationBindingMismatch"
        )
    authorized_from = datetime.fromisoformat(capture_authorization.authorized_from)
    authorized_until = datetime.fromisoformat(capture_authorization.authorized_until)
    capture_times = (
        datetime.fromisoformat(evidence.receipt.opened_at),
        datetime.fromisoformat(evidence.receipt.closed_at),
        datetime.fromisoformat(evidence.captured_at),
    )
    if min(capture_times) < authorized_from or max(capture_times) > authorized_until:
        return _blocked(
            "r7e.external-provenance",
            title,
            "CaptureOutsideAuthorizationWindow",
            authorizedFrom=capture_authorization.authorized_from,
            authorizedUntil=capture_authorization.authorized_until,
            openedAt=evidence.receipt.opened_at,
            closedAt=evidence.receipt.closed_at,
        )
    return _passed(
        "r7e.external-provenance",
        title,
        sourceKind=evidence.source_kind,
        capturedAt=evidence.captured_at,
    )


def _evidence_identity_matches(
    evidence: BeckhoffShadowRunEvidence,
    vendor_profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    witness_profile: BeckhoffShadowWitnessProfile,
    controller_profile: DeploymentControllerProfile | None,
    authority: ReadOnlyAuthorityEvidence | None,
    capture_authorization: BeckhoffShadowCaptureAuthorization | None,
    command_content_hash: str | None,
) -> bool:
    return all(
        (
            evidence.vendor_profile_content_hash == vendor_profile.content_hash,
            runtime_evidence is not None
            and evidence.runtime_evidence_content_hash == runtime_evidence.content_hash,
            evidence.witness_profile_content_hash == witness_profile.content_hash,
            controller_profile is not None
            and evidence.controller_profile_content_hash
            == controller_profile.content_hash,
            authority is not None
            and evidence.authority_content_hash == authority.content_hash,
            capture_authorization is not None
            and evidence.capture_authorization_content_hash
            == capture_authorization.content_hash,
            command_content_hash is not None
            and evidence.command_content_hash == command_content_hash,
        )
    )


def _coverage_check(
    command: Any,
    evidence: BeckhoffShadowRunEvidence | None,
    identities_match: bool,
) -> R7EReadinessCheck:
    title = "Exact M5 sample-index coverage without interpolation"
    if command is None or evidence is None:
        return _open("r7e.frame-coverage", title, "CommandOrShadowEvidenceMissing")
    if not identities_match:
        return _blocked("r7e.frame-coverage", title, "ShadowEvidenceIdentityMismatch")
    frames = evidence.frames
    expected_indexes = tuple(sample.sample_index for sample in command.samples)
    observed_indexes = tuple(frame.read_sample_index for frame in frames)
    notified_indexes = tuple(frame.notified_sample_index for frame in frames)
    sequences = tuple(frame.sequence for frame in frames)
    complete = (
        evidence.receipt.status == "Succeeded"
        and sequences == tuple(range(len(frames)))
        and observed_indexes == expected_indexes
        and notified_indexes == expected_indexes
        and all(frame.command_content_hash == command.content_id for frame in frames)
        and evidence.receipt.accepted_frame_count == len(command.samples)
        and evidence.receipt.rejected_frame_count == 0
        and evidence.receipt.dropped_sample_index_count == 0
        and evidence.receipt.read_operation_count >= len(command.samples)
    )
    if not complete:
        return _blocked(
            "r7e.frame-coverage",
            title,
            "IncompleteOrMismatchedSampleIndexCoverage",
            expectedSampleCount=len(command.samples),
            observedSampleCount=len(frames),
        )
    return _passed(
        "r7e.frame-coverage",
        title,
        expectedSampleCount=len(command.samples),
        observedSampleCount=len(frames),
        coverageFraction=1.0,
    )


def _timestamp_check(
    witness_profile: BeckhoffShadowWitnessProfile,
    evidence: BeckhoffShadowRunEvidence | None,
) -> R7EReadinessCheck:
    title = "Good-quality source/server/host timestamp integrity"
    if evidence is None:
        return _open("r7e.timestamp-integrity", title, "ShadowRunEvidenceMissing")
    if not evidence.frames:
        return _blocked("r7e.timestamp-integrity", title, "ShadowFramesMissing")
    host_times = [datetime.fromisoformat(frame.host_timestamp) for frame in evidence.frames]
    protocol_sequences = [frame.protocol_sequence_number for frame in evidence.frames]
    if any(right <= left for left, right in pairwise(host_times)) or any(
        right <= left for left, right in pairwise(protocol_sequences)
    ):
        return _blocked("r7e.timestamp-integrity", title, "NonMonotonicCaptureOrder")
    maximum_skew_ms = 0.0
    for frame in evidence.frames:
        timestamps = [datetime.fromisoformat(frame.host_timestamp)]
        for sample in frame.samples:
            if sample.quality != "good" or sample.status_code != "Good":
                return _blocked(
                    "r7e.timestamp-integrity", title, "BadOrSuspectAxisSample"
                )
            timestamps.extend(
                (
                    datetime.fromisoformat(sample.source_timestamp),
                    datetime.fromisoformat(sample.server_timestamp),
                )
            )
        skew = (max(timestamps) - min(timestamps)).total_seconds() * 1000.0
        maximum_skew_ms = max(maximum_skew_ms, skew)
    if maximum_skew_ms > witness_profile.maximum_timestamp_uncertainty_ms:
        return _blocked(
            "r7e.timestamp-integrity",
            title,
            "TimestampUncertaintyExceeded",
            maximumObservedSkewMs=maximum_skew_ms,
            allowedSkewMs=witness_profile.maximum_timestamp_uncertainty_ms,
        )
    return _passed(
        "r7e.timestamp-integrity",
        title,
        maximumObservedSkewMs=maximum_skew_ms,
        allowedSkewMs=witness_profile.maximum_timestamp_uncertainty_ms,
    )


def _zero_write_check(
    evidence: BeckhoffShadowRunEvidence | None,
) -> R7EReadinessCheck:
    title = "Zero write and zero method-call capture"
    if evidence is None:
        return _open("r7e.zero-write", title, "ShadowRunEvidenceMissing")
    receipt = evidence.receipt
    if receipt.write_operation_count != 0 or receipt.method_call_operation_count != 0:
        return _blocked("r7e.zero-write", title, "ForbiddenDeviceOperationObserved")
    return _passed(
        "r7e.zero-write",
        title,
        writeOperationCount=0,
        methodCallOperationCount=0,
    )


def assess_r7e_shadow(
    vendor_profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    witness_profile: BeckhoffShadowWitnessProfile,
    controller_profile: DeploymentControllerProfile | None,
    authority: ReadOnlyAuthorityEvidence | None,
    capture_authorization: BeckhoffShadowCaptureAuthorization | None,
    command: Any,
    shadow_evidence: BeckhoffShadowRunEvidence | None,
) -> BeckhoffShadowRunReadinessAudit:
    command_hash = command.content_id if command is not None else None
    identities_match = (
        shadow_evidence is not None
        and _evidence_identity_matches(
            shadow_evidence,
            vendor_profile,
            runtime_evidence,
            witness_profile,
            controller_profile,
            authority,
            capture_authorization,
            command_hash,
        )
    )
    checks = [
        _passed(
            "r7e.contract",
            "Windows Beckhoff read-only shadow witness contract",
            platform="Windows",
            capturePolicy="sample-index-triggered-batch-read",
        ),
        _runtime_check(vendor_profile, runtime_evidence),
        _witness_profile_check(
            vendor_profile, runtime_evidence, witness_profile, command_hash
        ),
        _authority_check(controller_profile, authority),
        _command_check(command_hash, witness_profile, shadow_evidence),
        _provenance_check(
            shadow_evidence,
            capture_authorization,
            controller_profile,
            command_hash,
        ),
        _coverage_check(command, shadow_evidence, identities_match),
        _timestamp_check(witness_profile, shadow_evidence),
        _zero_write_check(shadow_evidence),
    ]
    deployment_dependencies = checks[1:9]
    if any(check.status == "Blocked" for check in deployment_dependencies):
        deployment = _blocked(
            "r7e.deployment-shadow",
            "Case-scoped real deployment Shadow gate",
            "DeploymentShadowDependencyBlocked",
        )
        deployment_status = "Blocked"
    elif all(check.status == "Passed" for check in deployment_dependencies):
        deployment = _passed(
            "r7e.deployment-shadow",
            "Case-scoped real deployment Shadow gate",
            scope="single-controller-single-command-capture",
            countsTowardDeploymentShadow=True,
        )
        deployment_status = "Passed"
    else:
        deployment = _open(
            "r7e.deployment-shadow",
            "Case-scoped real deployment Shadow gate",
            "DeploymentShadowEvidenceOpen",
        )
        deployment_status = "Open"
    checks.extend(
        (
            deployment,
            _open(
                "r7e.reality-gate",
                "Physical-model reality validation gate",
                "R4RealityAlignmentRequired",
                requiredIndependentRuns=2,
                countsTowardReality=False,
            ),
        )
    )
    runtime_status = checks[1].status
    readiness_outcome = (
        "Blocked"
        if any(check.status == "Blocked" for check in checks)
        else "Passed"
        if deployment_status == "Passed"
        else "Open"
    )
    payload: dict[str, Any] = {
        "artifactType": "axiom.control.beckhoff-shadow-run-readiness",
        "schemaVersion": 1,
        "auditId": "control.r7e.beckhoff-shadow-run-readiness-audit@1",
        "vendorProfileContentHash": vendor_profile.content_hash,
        "witnessProfileContentHash": witness_profile.content_hash,
        "checks": checks,
        "readinessOutcome": readiness_outcome,
        "permissionCeiling": "Shadow",
        "deviceWriteAllowed": False,
        "contractStatus": "Passed",
        "vendorRuntimeStatus": runtime_status,
        "deploymentShadowStatus": deployment_status,
        "realityValidationStatus": "Open",
        "controlledTrialStatus": "Open",
        "closedLoopStatus": "Open",
        "countsTowardDeploymentShadow": deployment_status == "Passed",
        "countsTowardReality": False,
        "deviceSafetyStatus": "NotAssessed",
        "processSafetyStatus": "NotAssessed",
    }
    optional_hashes = {
        "runtimeEvidenceContentHash": (
            runtime_evidence.content_hash if runtime_evidence else None
        ),
        "controllerProfileContentHash": (
            controller_profile.content_hash if controller_profile else None
        ),
        "authorityContentHash": authority.content_hash if authority else None,
        "captureAuthorizationContentHash": (
            capture_authorization.content_hash if capture_authorization else None
        ),
        "commandContentHash": command_hash,
        "shadowEvidenceContentHash": (
            shadow_evidence.content_hash if shadow_evidence else None
        ),
    }
    payload.update({key: value for key, value in optional_hashes.items() if value})
    return _sealed(BeckhoffShadowRunReadinessAudit, payload)


def _run_spec(
    vendor_profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    witness_profile: BeckhoffShadowWitnessProfile,
    controller_profile: DeploymentControllerProfile | None,
    authority: ReadOnlyAuthorityEvidence | None,
    capture_authorization: BeckhoffShadowCaptureAuthorization | None,
    command: Any,
    shadow_evidence: BeckhoffShadowRunEvidence | None,
    audit: BeckhoffShadowRunReadinessAudit,
    *,
    case_id: str = R7E_DEFAULT_CASE_ID,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "artifact": audit.model_dump(mode="json", by_alias=True, exclude_none=True),
        "vendorProfile": vendor_profile.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "witnessProfile": witness_profile.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "case": {
            "caseId": case_id,
            "requiredMetrics": [
                "control.beckhoff-shadow-contract@1",
                "control.beckhoff-deployment-shadow@1",
            ],
            "optionalMetrics": [
                "control.beckhoff-shadow-vendor-runtime@1",
                "control.beckhoff-shadow-witness-profile@1",
                "control.beckhoff-shadow-readonly-authority@1",
                "control.beckhoff-shadow-sample-index-coverage@1",
                "control.beckhoff-shadow-timestamp-integrity@1",
                "control.beckhoff-shadow-zero-write@1",
                "control.beckhoff-deployment-reality@2",
            ],
        },
    }
    support = {
        "runtimeEvidence": runtime_evidence,
        "controllerProfile": controller_profile,
        "authority": authority,
        "captureAuthorization": capture_authorization,
        "command": command,
        "shadowEvidence": shadow_evidence,
    }
    for key, value in support.items():
        if value is not None:
            request[key] = value.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
    return {
        "subjectId": "axiom.control.beckhoff-shadow-run-readiness@1",
        "subjectVersion": "1",
        "domainPackId": R7E_DOMAIN_PACK_ID,
        "runnerId": R7E_RUNNER_ID,
        "evaluatorVersion": R7E_EVALUATOR_ID,
        "request": request,
    }


def _payload(
    summary: R7EScenarioSummary,
    vendor_profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    witness_profile: BeckhoffShadowWitnessProfile,
    controller_profile: DeploymentControllerProfile | None,
    authority: ReadOnlyAuthorityEvidence | None,
    capture_authorization: BeckhoffShadowCaptureAuthorization | None,
    command: Any,
    shadow_evidence: BeckhoffShadowRunEvidence | None,
    *,
    case_id: str = R7E_DEFAULT_CASE_ID,
) -> R7EExamplePayload:
    audit = assess_r7e_shadow(
        vendor_profile,
        runtime_evidence,
        witness_profile,
        controller_profile,
        authority,
        capture_authorization,
        command,
        shadow_evidence,
    )
    run_spec = _run_spec(
        vendor_profile,
        runtime_evidence,
        witness_profile,
        controller_profile,
        authority,
        capture_authorization,
        command,
        shadow_evidence,
        audit,
        case_id=case_id,
    )
    RunSpec.model_validate(run_spec)
    return R7EExamplePayload(
        manifest=build_r7e_manifest(),
        scenario=summary,
        vendorProfile=vendor_profile,
        runtimeEvidence=runtime_evidence,
        witnessProfile=witness_profile,
        controllerProfile=controller_profile,
        authority=authority,
        captureAuthorization=capture_authorization,
        command=command,
        shadowEvidence=shadow_evidence,
        readinessAudit=audit,
        runSpec=run_spec,
    )


@lru_cache(maxsize=1)
def _scenario() -> R7EScenario:
    vendor_profile = build_default_beckhoff_profile()
    witness_profile = build_default_beckhoff_shadow_witness_profile(vendor_profile)
    summary = R7EScenarioSummary(
        scenarioId=R7E_DEFAULT_SCENARIO_ID,
        title="Beckhoff real Shadow witness evidence (open)",
        description=(
            "The Windows-only sample-index witness contract is frozen without "
            "inventing controller node IDs, runtime receipts or real capture data."
        ),
        expectedOutcome="Inconclusive",
        expectedReadinessOutcome="Open",
        countsTowardDeploymentShadow=False,
        countsTowardReality=False,
    )
    payload = _payload(
        summary,
        vendor_profile,
        None,
        witness_profile,
        None,
        None,
        None,
        None,
        None,
    )
    return R7EScenario(
        summary=summary,
        vendor_profile=vendor_profile,
        runtime_evidence=None,
        witness_profile=witness_profile,
        controller_profile=None,
        authority=None,
        capture_authorization=None,
        command=None,
        shadow_evidence=None,
        readiness_audit=payload.readiness_audit,
        run_spec=payload.run_spec,
    )


def list_r7e_scenarios() -> tuple[R7EScenarioSummary, ...]:
    return (_scenario().summary,)


def load_r7e_scenario(
    scenario_id: str = R7E_DEFAULT_SCENARIO_ID,
) -> R7EScenario:
    if scenario_id != R7E_DEFAULT_SCENARIO_ID:
        raise KeyError(
            f"unknown R7-E scenario '{scenario_id}'; expected: {R7E_DEFAULT_SCENARIO_ID}"
        )
    return _scenario()


def r7e_example_payload(
    scenario_id: str = R7E_DEFAULT_SCENARIO_ID,
) -> R7EExamplePayload:
    scenario = load_r7e_scenario(scenario_id)
    return _payload(
        scenario.summary,
        scenario.vendor_profile,
        scenario.runtime_evidence,
        scenario.witness_profile,
        scenario.controller_profile,
        scenario.authority,
        scenario.capture_authorization,
        scenario.command,
        scenario.shadow_evidence,
    )


def assess_r7e_payload(request: R7EAssessmentRequest) -> R7EExamplePayload:
    vendor_profile = request.vendor_profile or build_default_beckhoff_profile()
    witness_profile = request.witness_profile or build_default_beckhoff_shadow_witness_profile(
        vendor_profile
    )
    summary = R7EScenarioSummary(
        scenarioId="external-beckhoff-shadow-run-assessment",
        title="External Beckhoff Shadow witness assessment",
        description=(
            "Imported evidence is checked for exact command identity, sample-index "
            "coverage and read-only authority. Reality validation remains a separate gate."
        ),
        expectedOutcome="Inconclusive",
        expectedReadinessOutcome="Open",
        countsTowardDeploymentShadow=False,
        countsTowardReality=False,
    )
    return _payload(
        summary,
        vendor_profile,
        request.runtime_evidence,
        witness_profile,
        request.controller_profile,
        request.authority,
        request.capture_authorization,
        request.command,
        request.shadow_evidence,
        case_id=request.case_id or R7E_DEFAULT_CASE_ID,
    )


def r7e_example_run_spec(
    scenario_id: str = R7E_DEFAULT_SCENARIO_ID,
) -> dict[str, Any]:
    return deepcopy(load_r7e_scenario(scenario_id).run_spec)


def validate_r7e_example_run_spec(
    scenario_id: str = R7E_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r7e_example_run_spec(scenario_id))


__all__ = [
    "assess_r7e_payload",
    "assess_r7e_shadow",
    "build_default_beckhoff_shadow_witness_profile",
    "build_r7e_manifest",
    "list_r7e_scenarios",
    "load_r7e_scenario",
    "r7e_example_payload",
    "r7e_example_run_spec",
    "validate_r7e_example_run_spec",
]
