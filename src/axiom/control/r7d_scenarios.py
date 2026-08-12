from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

from ..models import AxiomModel, RunSpec
from .models import canonical_hash
from .r7d_models import (
    BeckhoffAxisSignal,
    BeckhoffRuntimeEvidence,
    BeckhoffTwinCatVendorProfile,
    BeckhoffVendorReadinessAudit,
    R7DAssessmentRequest,
    R7DExamplePayload,
    R7DManifest,
    R7DReadinessCheck,
    R7DScenario,
    R7DScenarioSummary,
    R7D_DEFAULT_SCENARIO_ID,
    R7D_DOMAIN_PACK_ID,
    R7D_EVALUATOR_ID,
    R7D_RUNNER_ID,
    R7D_SCENARIO_IDS,
)
from .r7c_models import OpcUaTransportEvidence


def _sealed[ModelT: AxiomModel](
    model_type: type[ModelT], payload: dict[str, Any]
) -> ModelT:
    return model_type.model_validate({**payload, "contentHash": canonical_hash(payload)})


@lru_cache(maxsize=1)
def build_default_beckhoff_profile() -> BeckhoffTwinCatVendorProfile:
    channels = [
        BeckhoffAxisSignal(
            axisId=axis,
            canonicalSignalId=f"machine.axis.{axis}.position",
            quantity="axis-position",
            unit="mm" if axis in {"X", "Y", "Z"} else "rad",
        )
        for axis in ("X", "Y", "Z", "B", "C")
    ]
    payload: dict[str, Any] = {
        "schemaId": "axiom.control.beckhoff-twincat-profile@1",
        "profileId": "axiom.control.beckhoff-twincat-default-profile@1",
        "vendorId": "beckhoff",
        "vendorName": "Beckhoff Automation",
        "controllerFamily": "TwinCAT 3",
        "minimumTwinCatBuild": 4026,
        "opcUaServerProduct": "TF6100 OPC UA Server",
        "requiredLicenseId": "TF6100",
        "acceptedRuntimeLicenseStates": ["Full", "Trial"],
        "deploymentRequiredLicenseState": "Full",
        "requiredPackages": ["TwinCAT.Standard.XAR", "TF6100.OpcUaServer.XAR"],
        "optionalEngineeringPackage": "TF6100.OpcUaServer.XAE",
        "supportedPlatforms": ["Windows"],
        "protocol": "opc-ua",
        "defaultEndpointUrl": "opc.tcp://localhost:4840",
        "messageSecurityMode": "SignAndEncrypt",
        "identityType": "username",
        "accessMode": "read-subscribe-only",
        "bindingStatus": "Open",
        "channels": channels,
        "permissionCeiling": "Shadow",
        "deviceWriteAllowed": False,
    }
    return _sealed(BeckhoffTwinCatVendorProfile, payload)


def build_r7d_manifest() -> R7DManifest:
    return R7DManifest(
        manifestId="control.r7d-manifest@1",
        domainPackId=R7D_DOMAIN_PACK_ID,
        evaluatorVersion=R7D_EVALUATOR_ID,
        runnerId=R7D_RUNNER_ID,
        vendorProfileId="axiom.control.beckhoff-twincat-default-profile@1",
        verifierId="axiom.control.beckhoff-twincat-read-verifier@1",
        verifierVersion="0.2.0",
        targetVendor="Beckhoff Automation",
        targetControllerFamily="TwinCAT 3",
        minimumTwinCatBuild=4026,
        targetInterface="TF6100 OPC UA Server",
        supportedPlatforms=("Windows",),
        defaultScenarioId=R7D_DEFAULT_SCENARIO_ID,
        scenarioIds=R7D_SCENARIO_IDS,
        permissionCeiling="Shadow",
        deviceWriteAllowed=False,
        vendorProfileStatus="Passed",
        vendorRuntimeStatus="Open",
        deploymentShadowStatus="Open",
        realityValidationStatus="Open",
        deviceSafetyStatus="NotAssessed",
        processSafetyStatus="NotAssessed",
    )


def _open_check(
    check_id: str, title: str, reason_code: str, **details: Any
) -> R7DReadinessCheck:
    return R7DReadinessCheck(
        checkId=check_id,
        title=title,
        status="Open",
        reasonCode=reason_code,
        details=details,
    )


def _blocked_check(
    check_id: str, title: str, reason_code: str, **details: Any
) -> R7DReadinessCheck:
    return R7DReadinessCheck(
        checkId=check_id,
        title=title,
        status="Blocked",
        reasonCode=reason_code,
        details=details,
    )


def _passed_check(
    check_id: str, title: str, **details: Any
) -> R7DReadinessCheck:
    return R7DReadinessCheck(
        checkId=check_id, title=title, status="Passed", details=details
    )


def _installation_check(
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    profile: BeckhoffTwinCatVendorProfile,
) -> R7DReadinessCheck:
    title = "TwinCAT 3 Build 4026+ and TF6100 runtime packages"
    if runtime_evidence is None:
        return _open_check(
            "r7d.installation", title, "BeckhoffRuntimeEvidenceMissing"
        )
    if runtime_evidence.profile_content_hash != profile.content_hash:
        return _blocked_check(
            "r7d.installation",
            title,
            "RuntimeEvidenceProfileMismatch",
            expectedProfileContentHash=profile.content_hash,
            actualProfileContentHash=runtime_evidence.profile_content_hash,
        )
    if runtime_evidence.source_kind != "vendor-runtime":
        return _blocked_check(
            "r7d.installation", title, "ContractFixtureNotVendorRuntime"
        )
    probe = runtime_evidence.installation
    details = {
        "tcpkgAvailable": probe.tcpkg_available,
        "twinCatBuild": probe.twincat_build,
        "packages": [package.package_id for package in probe.packages],
        "serverBinarySha256": (
            probe.server_binary.sha256 if probe.server_binary is not None else None
        ),
    }
    if probe.status == "Passed":
        return _passed_check("r7d.installation", title, **details)
    if probe.status == "Blocked":
        return _blocked_check(
            "r7d.installation",
            title,
            probe.reason_code or "TwinCatInstallationBlocked",
            **details,
        )
    return _open_check(
        "r7d.installation",
        title,
        probe.reason_code or "TwinCatInstallationEvidenceOpen",
        **details,
    )


def _license_check(
    runtime_evidence: BeckhoffRuntimeEvidence | None,
) -> R7DReadinessCheck:
    title = "TF6100 license state"
    if runtime_evidence is None:
        return _open_check("r7d.license", title, "Tf6100LicenseEvidenceMissing")
    probe = runtime_evidence.license
    details = {
        "licenseId": probe.license_id,
        "state": probe.state,
        "deploymentRequires": "Full",
    }
    if probe.state in {"Full", "Trial"}:
        return _passed_check("r7d.license", title, **details)
    if probe.state == "Missing":
        return _blocked_check("r7d.license", title, "Tf6100LicenseMissing", **details)
    return _open_check("r7d.license", title, "Tf6100LicenseStateUnknown", **details)


def _server_identity_matches(
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence,
) -> bool:
    expected = profile.server_identity
    observed = runtime_evidence.server_identity
    if expected is None or observed is None:
        return False
    return all(
        getattr(expected, field) == getattr(observed, field)
        for field in (
            "endpoint_url",
            "server_application_uri",
            "server_certificate_sha256",
            "product_uri",
            "manufacturer_name",
            "product_name",
            "software_version",
            "build_number",
        )
    )


def _server_identity_check(
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
) -> R7DReadinessCheck:
    title = "Pinned TwinCAT OPC UA Server BuildInfo"
    if profile.binding_status != "Bound":
        return _open_check("r7d.server-identity", title, "DeploymentBindingOpen")
    if runtime_evidence is None or runtime_evidence.server_identity is None:
        return _open_check(
            "r7d.server-identity", title, "ServerIdentityEvidenceMissing"
        )
    observed = runtime_evidence.server_identity
    details = {
        "manufacturerName": observed.manufacturer_name,
        "productName": observed.product_name,
        "softwareVersion": observed.software_version,
        "buildNumber": observed.build_number,
        "serverCertificateSha256": observed.server_certificate_sha256,
    }
    if _server_identity_matches(profile, runtime_evidence):
        return _passed_check("r7d.server-identity", title, **details)
    return _blocked_check(
        "r7d.server-identity", title, "TwinCatServerIdentityMismatch", **details
    )


def _node_mapping_matches(
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence,
) -> bool:
    if runtime_evidence.channel_access is None:
        return False
    for expected, observed in zip(profile.channels, runtime_evidence.channel_access):
        binding = expected.node_binding
        if binding is None or (
            expected.axis_id != observed.axis_id
            or expected.canonical_signal_id != observed.canonical_signal_id
            or binding.namespace_uri != observed.namespace_uri
            or binding.identifier != observed.identifier
            or binding.expected_data_type != observed.data_type
            or binding.required_access_level != observed.access_level
            or binding.required_user_access_level != observed.user_access_level
        ):
            return False
    return True


def _node_mapping_check(
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
) -> R7DReadinessCheck:
    title = "X/Y/Z/B/C node mapping and read-only access levels"
    if profile.binding_status != "Bound":
        return _open_check("r7d.node-mapping", title, "DeploymentBindingOpen")
    if runtime_evidence is None or runtime_evidence.channel_access is None:
        return _open_check("r7d.node-mapping", title, "NodeAccessEvidenceMissing")
    details = {
        "axes": [channel.axis_id for channel in runtime_evidence.channel_access],
        "accessLevels": [
            channel.access_level for channel in runtime_evidence.channel_access
        ],
        "userAccessLevels": [
            channel.user_access_level for channel in runtime_evidence.channel_access
        ],
    }
    if _node_mapping_matches(profile, runtime_evidence):
        return _passed_check("r7d.node-mapping", title, **details)
    return _blocked_check(
        "r7d.node-mapping", title, "BeckhoffNodeMappingMismatch", **details
    )


def _readonly_check(
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
) -> R7DReadinessCheck:
    title = "Independent controller-side write rejection"
    if runtime_evidence is None or runtime_evidence.write_rejection.status == "NotRun":
        return _open_check(
            "r7d.readonly-enforcement", title, "IndependentWriteProbeMissing"
        )
    receipt = runtime_evidence.write_rejection
    probe = profile.permission_probe
    details = {
        "statusCode": receipt.status_code,
        "serverValueUnchanged": receipt.server_value_unchanged,
        "operationCount": receipt.operation_count,
        "probeIdentifier": receipt.probe_identifier,
    }
    if (
        receipt.status == "Rejected"
        and probe is not None
        and receipt.probe_namespace_uri == probe.node_binding.namespace_uri
        and receipt.probe_identifier == probe.node_binding.identifier
    ):
        return _passed_check("r7d.readonly-enforcement", title, **details)
    return _blocked_check(
        "r7d.readonly-enforcement", title, "ControllerAcceptedWriteProbe", **details
    )


def _transport_matches_profile(
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence,
    transport_evidence: OpcUaTransportEvidence,
) -> bool:
    identity = profile.server_identity
    if identity is None:
        return False
    if (
        runtime_evidence.transport_evidence_content_hash
        != transport_evidence.content_hash
        or transport_evidence.endpoint.endpoint_url != identity.endpoint_url
        or transport_evidence.endpoint.server_application_uri
        != identity.server_application_uri
        or transport_evidence.endpoint.server_certificate_sha256
        != identity.server_certificate_sha256
    ):
        return False
    for expected, observed in zip(profile.channels, transport_evidence.channels):
        binding = expected.node_binding
        if binding is None or (
            expected.axis_id != observed.axis_id
            or expected.canonical_signal_id != observed.canonical_signal_id
            or expected.unit != observed.unit
            or binding.namespace_uri != observed.namespace_uri
            or binding.identifier != observed.identifier
        ):
            return False
    return True


def _transport_check(
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    transport_evidence: OpcUaTransportEvidence | None,
) -> R7DReadinessCheck:
    title = "R7-C secure five-axis transport receipt"
    if profile.binding_status != "Bound":
        return _open_check("r7d.transport", title, "DeploymentBindingOpen")
    if runtime_evidence is None or transport_evidence is None:
        return _open_check("r7d.transport", title, "TransportEvidenceMissing")
    details = {
        "transportEvidenceContentHash": transport_evidence.content_hash,
        "receivedFrameCount": transport_evidence.receipt.received_frame_count,
        "droppedNotificationCount": (
            transport_evidence.receipt.dropped_notification_count
        ),
    }
    if _transport_matches_profile(profile, runtime_evidence, transport_evidence):
        return _passed_check("r7d.transport", title, **details)
    return _blocked_check(
        "r7d.transport", title, "TransportEvidenceBindingMismatch", **details
    )


def assess_r7d_beckhoff(
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    transport_evidence: OpcUaTransportEvidence | None,
) -> BeckhoffVendorReadinessAudit:
    checks = [
        _passed_check(
            "r7d.target",
            "Beckhoff TwinCAT 3 target selection",
            vendor="Beckhoff Automation",
            controllerFamily="TwinCAT 3",
            minimumBuild=4026,
            interface="TF6100 OPC UA Server",
            platform="Windows",
        ),
        _passed_check(
            "r7d.profile",
            "Versioned Beckhoff Vendor Profile contract",
            profileId=profile.profile_id,
            profileContentHash=profile.content_hash,
            bindingStatus=profile.binding_status,
            permissionCeiling="Shadow",
            deviceWriteAllowed=False,
        ),
        _installation_check(runtime_evidence, profile),
        _license_check(runtime_evidence),
        _server_identity_check(profile, runtime_evidence),
        _node_mapping_check(profile, runtime_evidence),
        _readonly_check(profile, runtime_evidence),
        _transport_check(profile, runtime_evidence, transport_evidence),
        _open_check(
            "r7d.reality-gate",
            "Independent case-scoped deployment Shadow validation",
            "RealDeploymentCaptureMissing",
            requiresIndependentRealCapture=True,
            countsTowardReality=False,
            deviceSafetyStatus="NotAssessed",
            processSafetyStatus="NotAssessed",
        ),
    ]
    runtime_checks = checks[2:8]
    vendor_runtime_status = (
        "Blocked"
        if any(check.status == "Blocked" for check in runtime_checks)
        else "Passed"
        if all(check.status == "Passed" for check in runtime_checks)
        else "Open"
    )
    payload: dict[str, Any] = {
        "artifactType": "axiom.control.beckhoff-vendor-readiness",
        "schemaVersion": 1,
        "auditId": "control.r7d.beckhoff-vendor-readiness-audit@1",
        "profileContentHash": profile.content_hash,
        "checks": checks,
        "readinessOutcome": (
            "Blocked" if any(check.status == "Blocked" for check in checks) else "Open"
        ),
        "permissionCeiling": "Shadow",
        "deviceWriteAllowed": False,
        "vendorProfileStatus": "Passed",
        "vendorRuntimeStatus": vendor_runtime_status,
        "deploymentShadowStatus": "Open",
        "realityValidationStatus": "Open",
        "controlledTrialStatus": "Open",
        "closedLoopStatus": "Open",
        "deviceSafetyStatus": "NotAssessed",
        "processSafetyStatus": "NotAssessed",
    }
    if runtime_evidence is not None:
        payload["runtimeEvidenceContentHash"] = runtime_evidence.content_hash
    if transport_evidence is not None:
        payload["transportEvidenceContentHash"] = transport_evidence.content_hash
    return _sealed(BeckhoffVendorReadinessAudit, payload)


def _run_spec(
    profile: BeckhoffTwinCatVendorProfile,
    audit: BeckhoffVendorReadinessAudit,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    transport_evidence: OpcUaTransportEvidence | None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "artifact": audit.model_dump(mode="json", by_alias=True, exclude_none=True),
        "profile": profile.model_dump(mode="json", by_alias=True, exclude_none=True),
        "case": {
            "caseId": "control.r7d.beckhoff-vendor-readiness.case@1",
            "requiredMetrics": [
                "control.beckhoff-profile-contract@1",
                "control.beckhoff-deployment-reality@1",
            ],
            "optionalMetrics": [
                "control.beckhoff-runtime-conformance@1",
                "control.beckhoff-installation@1",
                "control.beckhoff-license@1",
                "control.beckhoff-server-identity@1",
                "control.beckhoff-node-mapping@1",
                "control.beckhoff-readonly-enforcement@1",
                "control.beckhoff-transport@1",
            ],
        },
    }
    if runtime_evidence is not None:
        request["runtimeEvidence"] = runtime_evidence.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    if transport_evidence is not None:
        request["transportEvidence"] = transport_evidence.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    return {
        "subjectId": "axiom.control.beckhoff-vendor-readiness@1",
        "subjectVersion": "1",
        "domainPackId": R7D_DOMAIN_PACK_ID,
        "runnerId": R7D_RUNNER_ID,
        "evaluatorVersion": R7D_EVALUATOR_ID,
        "request": request,
    }


@lru_cache(maxsize=1)
def _scenario() -> R7DScenario:
    profile = build_default_beckhoff_profile()
    audit = assess_r7d_beckhoff(profile, None, None)
    summary = R7DScenarioSummary(
        scenarioId=R7D_DEFAULT_SCENARIO_ID,
        title="Beckhoff TwinCAT runtime evidence (open)",
        description=(
            "The Windows-only TwinCAT 3 Build 4026+ / TF6100 Vendor Profile is "
            "frozen, while deployment identity, node bindings, license and real runtime "
            "evidence remain open."
        ),
        expectedOutcome="Inconclusive",
        expectedReadinessOutcome="Open",
        countsTowardReality=False,
    )
    return R7DScenario(
        summary=summary,
        profile=profile,
        readiness_audit=audit,
        runtime_evidence=None,
        transport_evidence=None,
        run_spec=_run_spec(profile, audit, None, None),
    )


def list_r7d_scenarios() -> tuple[R7DScenarioSummary, ...]:
    return (_scenario().summary,)


def load_r7d_scenario(
    scenario_id: str = R7D_DEFAULT_SCENARIO_ID,
) -> R7DScenario:
    if scenario_id != R7D_DEFAULT_SCENARIO_ID:
        raise KeyError(
            f"unknown R7-D scenario '{scenario_id}'; expected: {R7D_DEFAULT_SCENARIO_ID}"
        )
    return _scenario()


def _payload(
    summary: R7DScenarioSummary,
    profile: BeckhoffTwinCatVendorProfile,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
    transport_evidence: OpcUaTransportEvidence | None,
) -> R7DExamplePayload:
    audit = assess_r7d_beckhoff(profile, runtime_evidence, transport_evidence)
    run_spec = _run_spec(profile, audit, runtime_evidence, transport_evidence)
    RunSpec.model_validate(run_spec)
    return R7DExamplePayload(
        manifest=build_r7d_manifest(),
        scenario=summary,
        profile=profile,
        readinessAudit=audit,
        runtimeEvidence=runtime_evidence,
        transportEvidence=transport_evidence,
        runSpec=run_spec,
    )


def r7d_example_payload(
    scenario_id: str = R7D_DEFAULT_SCENARIO_ID,
) -> R7DExamplePayload:
    scenario = load_r7d_scenario(scenario_id)
    return _payload(
        scenario.summary,
        scenario.profile,
        scenario.runtime_evidence,
        scenario.transport_evidence,
    )


def assess_r7d_payload(request: R7DAssessmentRequest) -> R7DExamplePayload:
    profile = request.profile or build_default_beckhoff_profile()
    summary = R7DScenarioSummary(
        scenarioId="external-beckhoff-runtime-assessment",
        title="External Beckhoff TwinCAT runtime evidence assessment",
        description=(
            "Imported vendor-runtime evidence is checked against an exact versioned "
            "profile without granting device authority or closing the reality gate."
        ),
        expectedOutcome="Inconclusive",
        expectedReadinessOutcome="Open",
        countsTowardReality=False,
    )
    return _payload(
        summary, profile, request.runtime_evidence, request.transport_evidence
    )


def r7d_example_run_spec(
    scenario_id: str = R7D_DEFAULT_SCENARIO_ID,
) -> dict[str, Any]:
    return deepcopy(load_r7d_scenario(scenario_id).run_spec)


def validate_r7d_example_run_spec(
    scenario_id: str = R7D_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r7d_example_run_spec(scenario_id))


__all__ = [
    "assess_r7d_beckhoff",
    "assess_r7d_payload",
    "build_default_beckhoff_profile",
    "build_r7d_manifest",
    "list_r7d_scenarios",
    "load_r7d_scenario",
    "r7d_example_payload",
    "r7d_example_run_spec",
    "validate_r7d_example_run_spec",
]
