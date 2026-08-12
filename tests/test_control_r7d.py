from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from axiom import evaluate_run
from axiom.control.models import canonical_hash
from axiom.control.r7c_models import OpcUaTransportEvidence
from axiom.control.r7d_models import (
    BeckhoffRuntimeEvidence,
    BeckhoffTwinCatVendorProfile,
    R7DAssessmentRequest,
    R7D_DEFAULT_SCENARIO_ID,
    R7D_DOMAIN_PACK_ID,
)
from axiom.control.r7d_scenarios import (
    assess_r7d_beckhoff,
    assess_r7d_payload,
    build_default_beckhoff_profile,
    build_r7d_manifest,
    list_r7d_scenarios,
    r7d_example_payload,
    validate_r7d_example_run_spec,
)
from axiom.models import RunSpec


def _bound_profile() -> BeckhoffTwinCatVendorProfile:
    payload = build_default_beckhoff_profile().model_dump(
        mode="json", by_alias=True, exclude={"content_hash"}
    )
    payload["bindingStatus"] = "Bound"
    payload["serverIdentity"] = {
        "endpointUrl": "opc.tcp://beckhoff-controller:4840",
        "serverApplicationUri": "urn:beckhoff-controller:TcOpcUaServer",
        "serverCertificateSha256": "1" * 64,
        "productUri": "urn:beckhoff:TwinCAT:OPC-UA:Server",
        "manufacturerName": "Beckhoff Automation",
        "productName": "TwinCAT OPC UA Server",
        "softwareVersion": "4.5.2",
        "buildNumber": "4026.17",
    }
    payload["licenseBinding"] = {
        "namespaceUri": "urn:beckhoff-controller:PLC1",
        "resultIdentifier": "MAIN.Tf6100LicenseResult",
        "expirationIdentifier": "MAIN.Tf6100LicenseExpiration",
        "resultDataType": "Int32",
        "fullResultCodes": [0, 255],
        "trialResultCodes": [254],
    }
    payload["permissionProbe"] = {
        "purpose": "non-actuating-readonly-permission-canary",
        "deploymentOwnerAttestedNonActuating": True,
        "nodeBinding": {
            "namespaceUri": "urn:beckhoff-controller:PLC1",
            "identifier": "MAIN.AxiomReadOnlyPermissionCanary",
            "expectedDataType": "Double",
            "requiredAccessLevel": 1,
            "requiredUserAccessLevel": 1,
        },
    }
    for channel in payload["channels"]:
        axis = channel["axisId"]
        channel["nodeBinding"] = {
            "namespaceUri": "urn:beckhoff-controller:PLC1",
            "identifier": f"MAIN.Axis{axis}Position",
            "expectedDataType": "Double",
            "requiredAccessLevel": 1,
            "requiredUserAccessLevel": 1,
        }
    payload["contentHash"] = canonical_hash(payload)
    return BeckhoffTwinCatVendorProfile.model_validate(payload)


def _transport_payload(profile: BeckhoffTwinCatVendorProfile) -> dict[str, Any]:
    identity = profile.server_identity
    assert identity is not None
    channels = [
        {
            "channelId": f"axis.{channel.axis_id}.position",
            "namespaceUri": channel.node_binding.namespace_uri,
            "identifier": channel.node_binding.identifier,
            "canonicalSignalId": channel.canonical_signal_id,
            "quantity": "axis-position",
            "axisId": channel.axis_id,
            "unit": channel.unit,
        }
        for channel in profile.channels
        if channel.node_binding is not None
    ]
    frames = []
    for sequence, timestamp in enumerate(
        ("2026-08-13T08:00:00+00:00", "2026-08-13T08:00:00.05+00:00")
    ):
        frames.append(
            {
                "sequence": sequence,
                "protocolSequenceNumber": sequence + 1,
                "hostTimestamp": timestamp,
                "samples": [
                    {
                        "channelId": channel["channelId"],
                        "valueType": "Double",
                        "valueText": str(sequence + index / 10),
                        "unit": channel["unit"],
                        "quality": "good",
                        "statusCode": "Good",
                        "sourceTimestamp": timestamp,
                        "serverTimestamp": timestamp,
                    }
                    for index, channel in enumerate(channels)
                ],
            }
        )
    payload: dict[str, Any] = {
        "schemaId": "axiom.control.opcua-transport-evidence@1",
        "evidenceId": "axiom.control.beckhoff.transport-test@1",
        "adapterId": "axiom.control.opcua-shadow-read-adapter@1",
        "adapterVersion": "0.1.0",
        "platform": "Windows",
        "protocol": "opc-ua",
        "accessMode": "read-subscribe-only",
        "declaredReal": False,
        "countsTowardReality": False,
        "configFileSha256": "2" * 64,
        "endpoint": {
            "endpointUrl": identity.endpoint_url,
            "serverApplicationUri": identity.server_application_uri,
            "serverCertificateSha256": identity.server_certificate_sha256,
            "clientApplicationUri": "urn:axiom:beckhoff:shadow-client",
            "clientCertificateSha256": "3" * 64,
            "securityPolicyUri": (
                "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256"
            ),
            "messageSecurityMode": "SignAndEncrypt",
            "identityType": "username",
            "principalId": "beckhoff-shadow-reader",
            "anonymous": False,
        },
        "subscription": {
            "requestedPublishingIntervalMs": 50,
            "revisedPublishingIntervalMs": 50,
            "requestedSamplingIntervalMs": 20,
            "queueSize": 32,
            "monitoredItemCount": 5,
        },
        "channels": channels,
        "frames": frames,
        "receipt": {
            "status": "Succeeded",
            "openedAt": "2026-08-13T07:59:59.9+00:00",
            "closedAt": "2026-08-13T08:00:00.1+00:00",
            "readOperationCount": 0,
            "subscribeOperationCount": 1,
            "writeOperationCount": 0,
            "methodCallOperationCount": 0,
            "receivedFrameCount": 2,
            "receivedSampleCount": 10,
            "droppedNotificationCount": 0,
            "transcriptContentHash": canonical_hash(frames),
        },
        "virtualTransportStatus": "Passed",
        "vendorAdapterStatus": "Open",
        "realityValidationStatus": "Open",
        "deviceSafetyStatus": "NotAssessed",
        "processSafetyStatus": "NotAssessed",
    }
    payload["contentHash"] = canonical_hash(payload)
    return payload


def _runtime_payload(
    profile: BeckhoffTwinCatVendorProfile,
    transport: OpcUaTransportEvidence,
    *,
    source_kind: str = "vendor-runtime",
) -> dict[str, Any]:
    identity = profile.server_identity
    assert identity is not None
    payload: dict[str, Any] = {
        "schemaId": "axiom.control.beckhoff-runtime-evidence@1",
        "evidenceId": "axiom.control.beckhoff.runtime-test@1",
        "profileContentHash": profile.content_hash,
        "profileFileSha256": "4" * 64,
        "verifierId": "axiom.control.beckhoff-twincat-read-verifier@1",
        "verifierVersion": "0.2.0",
        "verifierBinarySha256": "5" * 64,
        "platform": "Windows",
        "sourceKind": source_kind,
        "capturedAt": "2026-08-13T08:00:01+00:00",
        "installation": {
            "status": "Passed",
            "tcpkgAvailable": True,
            "tcpkgSha256": "6" * 64,
            "twinCatBuild": 4026,
            "packages": [
                {
                    "packageId": "TwinCAT.Standard.XAR",
                    "version": "4026.17.0",
                    "installed": True,
                    "receiptSha256": "7" * 64,
                },
                {
                    "packageId": "TF6100.OpcUaServer.XAR",
                    "version": "4.5.2",
                    "installed": True,
                    "receiptSha256": "8" * 64,
                },
            ],
            "serverBinary": {
                "relativePath": "Functions/TF6100-OPC-UA/Win64/Server/TcOpcUaServer.exe",
                "productName": "TwinCAT OPC UA Server",
                "companyName": "Beckhoff Automation",
                "fileVersion": "4.5.2",
                "sha256": "9" * 64,
            },
        },
        "license": {
            "licenseId": "TF6100",
            "state": "Full",
            "source": "TwinCAT license runtime",
            "resultCode": 0,
            "resultNodeId": "urn:beckhoff-controller:PLC1|MAIN.Tf6100LicenseResult",
            "receiptSha256": "a" * 64,
        },
        "serverIdentity": {
            **identity.model_dump(mode="json", by_alias=True),
            "buildDate": "2026-01-01T00:00:00+00:00",
        },
        "channelAccess": [
            {
                "axisId": channel.axis_id,
                "canonicalSignalId": channel.canonical_signal_id,
                "namespaceUri": channel.node_binding.namespace_uri,
                "identifier": channel.node_binding.identifier,
                "dataType": "Double",
                "accessLevel": 1,
                "userAccessLevel": 1,
            }
            for channel in profile.channels
            if channel.node_binding is not None
        ],
        "writeRejection": {
            "verifierId": (
                "axiom.control.beckhoff-independent-write-rejection-verifier@1"
            ),
            "status": "Rejected",
            "operationCount": 1,
            "probeNamespaceUri": "urn:beckhoff-controller:PLC1",
            "probeIdentifier": "MAIN.AxiomReadOnlyPermissionCanary",
            "valueHashBefore": "c" * 64,
            "valueHashAfter": "c" * 64,
            "statusCode": "BadNotWritable",
            "serverValueUnchanged": True,
        },
        "transportEvidenceContentHash": transport.content_hash,
        "declaredReal": False,
        "countsTowardReality": False,
        "realityValidationStatus": "Open",
        "deviceSafetyStatus": "NotAssessed",
        "processSafetyStatus": "NotAssessed",
    }
    payload["writeRejection"]["receiptSha256"] = canonical_hash(
        payload["writeRejection"]
    )
    payload["contentHash"] = canonical_hash(payload)
    return payload


def _complete_evidence() -> tuple[
    BeckhoffTwinCatVendorProfile, BeckhoffRuntimeEvidence, OpcUaTransportEvidence
]:
    profile = _bound_profile()
    transport = OpcUaTransportEvidence.model_validate(_transport_payload(profile))
    runtime = BeckhoffRuntimeEvidence.model_validate(_runtime_payload(profile, transport))
    return profile, runtime, transport


def test_r7d_manifest_freezes_selected_beckhoff_target() -> None:
    manifest = build_r7d_manifest()

    assert manifest.domain_pack_id == R7D_DOMAIN_PACK_ID
    assert manifest.target_vendor == "Beckhoff Automation"
    assert manifest.target_controller_family == "TwinCAT 3"
    assert manifest.minimum_twincat_build == 4026
    assert manifest.target_interface == "TF6100 OPC UA Server"
    assert manifest.supported_platforms == ("Windows",)
    assert manifest.vendor_profile_status == "Passed"
    assert manifest.vendor_runtime_status == "Open"
    assert manifest.device_write_allowed is False


def test_r7d_default_profile_freezes_semantics_without_faking_node_ids() -> None:
    profile = build_default_beckhoff_profile()

    assert profile.binding_status == "Open"
    assert profile.server_identity is None
    assert tuple(channel.axis_id for channel in profile.channels) == (
        "X",
        "Y",
        "Z",
        "B",
        "C",
    )
    assert all(channel.node_binding is None for channel in profile.channels)
    assert profile.required_packages == (
        "TwinCAT.Standard.XAR",
        "TF6100.OpcUaServer.XAR",
    )


def test_r7d_default_payload_keeps_runtime_and_reality_open() -> None:
    payload = r7d_example_payload()

    assert payload.scenario.scenario_id == R7D_DEFAULT_SCENARIO_ID
    assert payload.readiness_audit.vendor_profile_status == "Passed"
    assert payload.readiness_audit.vendor_runtime_status == "Open"
    assert payload.readiness_audit.deployment_shadow_status == "Open"
    assert payload.readiness_audit.reality_validation_status == "Open"
    assert payload.runtime_evidence is None


def test_r7d_bound_profile_cannot_relabel_a_generic_opcua_server() -> None:
    raw = _bound_profile().model_dump(
        mode="json", by_alias=True, exclude={"content_hash"}
    )
    raw["serverIdentity"]["manufacturerName"] = "Generic Automation"
    raw["serverIdentity"]["productName"] = "Generic OPC UA Server"
    raw["contentHash"] = canonical_hash(raw)

    with pytest.raises(ValidationError, match="Beckhoff"):
        BeckhoffTwinCatVendorProfile.model_validate(raw)


def test_r7d_complete_vendor_runtime_receipt_never_closes_reality_gate() -> None:
    profile, runtime, transport = _complete_evidence()

    audit = assess_r7d_beckhoff(profile, runtime, transport)
    checks = {check.check_id: check.status for check in audit.checks}

    assert audit.vendor_runtime_status == "Passed"
    assert all(
        checks[check_id] == "Passed"
        for check_id in (
            "r7d.installation",
            "r7d.license",
            "r7d.server-identity",
            "r7d.node-mapping",
            "r7d.readonly-enforcement",
            "r7d.transport",
        )
    )
    assert audit.readiness_outcome == "Open"
    assert audit.deployment_shadow_status == "Open"
    assert audit.reality_validation_status == "Open"
    assert audit.device_safety_status == "NotAssessed"


def test_r7d_contract_fixture_cannot_pass_vendor_runtime() -> None:
    profile, _, transport = _complete_evidence()
    runtime = BeckhoffRuntimeEvidence.model_validate(
        _runtime_payload(profile, transport, source_kind="contract-fixture")
    )

    audit = assess_r7d_beckhoff(profile, runtime, transport)

    assert audit.vendor_runtime_status == "Blocked"
    assert audit.readiness_outcome == "Blocked"
    assert audit.checks[2].reason_code == "ContractFixtureNotVendorRuntime"


def test_r7d_mismatched_server_identity_is_blocked() -> None:
    profile, runtime, transport = _complete_evidence()
    raw = runtime.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"}
    )
    raw["serverIdentity"]["softwareVersion"] = "4.5.3"
    raw["contentHash"] = canonical_hash(raw)
    mismatched = BeckhoffRuntimeEvidence.model_validate(raw)

    audit = assess_r7d_beckhoff(profile, mismatched, transport)

    assert audit.vendor_runtime_status == "Blocked"
    assert audit.checks[4].reason_code == "TwinCatServerIdentityMismatch"


def test_r7d_runtime_evidence_rejects_content_tamper() -> None:
    profile, runtime, _ = _complete_evidence()
    raw = runtime.model_dump(mode="json", by_alias=True)
    raw["profileContentHash"] = profile.content_hash[:-1] + "0"

    with pytest.raises(ValidationError, match="contentHash"):
        BeckhoffRuntimeEvidence.model_validate(raw)


def test_r7d_runtime_evidence_rejects_write_receipt_hash_tamper() -> None:
    profile = _bound_profile()
    transport = OpcUaTransportEvidence.model_validate(_transport_payload(profile))
    raw = _runtime_payload(profile, transport)
    raw["writeRejection"]["statusCode"] = "BadUserAccessDenied"
    raw.pop("contentHash")
    raw["contentHash"] = canonical_hash(raw)

    with pytest.raises(ValidationError, match="receiptSha256"):
        BeckhoffRuntimeEvidence.model_validate(raw)


def test_r7d_public_run_supports_profile_and_runtime_but_not_reality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7d_runtime

    monkeypatch.setattr(r7d_runtime.platform, "system", lambda: "Windows")
    profile, runtime, transport = _complete_evidence()
    payload = assess_r7d_payload(
        R7DAssessmentRequest(
            profile=profile,
            runtimeEvidence=runtime,
            transportEvidence=transport,
        )
    )
    bundle = evaluate_run(RunSpec.model_validate(payload.run_spec))
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Inconclusive"
    assert claims["control.beckhoff-profile-contract-claim@1"] == "Supported"
    assert claims["control.beckhoff-runtime-conformance-claim@1"] == "Supported"
    assert claims["control.beckhoff-deployment-reality-claim@1"] == "Inconclusive"


def test_r7d_default_run_is_inconclusive_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7d_runtime

    monkeypatch.setattr(r7d_runtime.platform, "system", lambda: "Windows")

    bundle = evaluate_run(validate_r7d_example_run_spec())

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Inconclusive"


def test_r7d_non_windows_runtime_is_structured_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7d_runtime

    monkeypatch.setattr(r7d_runtime.platform, "system", lambda: "Linux")

    bundle = evaluate_run(validate_r7d_example_run_spec())

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Unsupported"
    assert all(
        result.reason_code == "UnsupportedRuntimePlatform"
        for result in bundle.report.metric_results
    )


def test_r7d_public_artifacts_never_serialize_safety_claims() -> None:
    serialized = json.dumps(
        r7d_example_payload().model_dump(mode="json", by_alias=True), sort_keys=True
    )

    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_r7d_catalog_has_only_non_reality_counting_scenarios() -> None:
    scenarios = list_r7d_scenarios()

    assert scenarios
    assert all(scenario.counts_toward_reality is False for scenario in scenarios)
