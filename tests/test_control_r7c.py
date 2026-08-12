from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from axiom import evaluate_run
from axiom.control import (
    R7CAssessmentRequest,
    R7C_DEFAULT_SCENARIO_ID,
    R7C_DOMAIN_PACK_ID,
    OpcUaTransportEvidence,
    assess_r7c_opcua_transport,
    assess_r7c_payload,
    build_r7c_manifest,
    list_r7c_scenarios,
    r7c_example_payload,
    validate_r7c_example_run_spec,
)
from axiom.control.models import canonical_hash
from axiom.models import RunSpec


def _transport_evidence_payload() -> dict[str, Any]:
    channels = [
        {
            "channelId": f"axis.{axis}.position",
            "namespaceUri": "urn:axiom:control:opcua-shadow:virtual-cnc",
            "identifier": f"Axis.{axis}.Position",
            "canonicalSignalId": f"machine.axis.{axis}.position",
            "quantity": "axis-position",
            "axisId": axis,
            "unit": "mm" if axis in {"X", "Y", "Z"} else "rad",
        }
        for axis in ("X", "Y", "Z", "B", "C")
    ]
    frames = []
    for sequence, timestamp in enumerate(
        ("2026-08-12T12:00:00.0000000+00:00", "2026-08-12T12:00:00.0500000+00:00")
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
        "evidenceId": "axiom.control.opcua-shadow.test-evidence@1",
        "adapterId": "axiom.control.opcua-shadow-read-adapter@1",
        "adapterVersion": "0.1.0",
        "platform": "Windows",
        "protocol": "opc-ua",
        "accessMode": "read-subscribe-only",
        "declaredReal": False,
        "countsTowardReality": False,
        "configFileSha256": "1" * 64,
        "endpoint": {
            "endpointUrl": "opc.tcp://localhost:4840/axiom-opcua-shadow",
            "serverApplicationUri": "urn:localhost:axiom:opcua:server",
            "serverCertificateSha256": "2" * 64,
            "clientApplicationUri": "urn:localhost:axiom:opcua:client",
            "clientCertificateSha256": "3" * 64,
            "securityPolicyUri": (
                "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256"
            ),
            "messageSecurityMode": "SignAndEncrypt",
            "identityType": "username",
            "principalId": "shadow-reader",
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
            "openedAt": "2026-08-12T11:59:59.9000000+00:00",
            "closedAt": "2026-08-12T12:00:00.1000000+00:00",
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


def _transport_evidence() -> OpcUaTransportEvidence:
    return OpcUaTransportEvidence.model_validate(_transport_evidence_payload())


def test_r7c_manifest_freezes_windows_virtual_transport_boundary() -> None:
    manifest = build_r7c_manifest()

    assert manifest.domain_pack_id == R7C_DOMAIN_PACK_ID
    assert manifest.supported_platforms == ("Windows",)
    assert manifest.permission_ceiling == "Shadow"
    assert manifest.device_write_allowed is False
    assert manifest.network_conformance_status == "Passed"
    assert manifest.vendor_adapter_status == "Open"
    assert manifest.reality_validation_status == "Open"


def test_r7c_default_payload_keeps_transport_and_reality_open() -> None:
    payload = r7c_example_payload()

    assert payload.scenario.scenario_id == R7C_DEFAULT_SCENARIO_ID
    assert payload.transport_evidence is None
    assert payload.readiness_audit.virtual_transport_status == "Open"
    assert payload.readiness_audit.vendor_adapter_status == "Open"
    assert payload.readiness_audit.reality_evidence_level == "None"


def test_r7c_valid_virtual_transport_never_promotes_vendor_or_reality() -> None:
    evidence = _transport_evidence()
    audit = assess_r7c_opcua_transport(evidence)
    checks = {check.check_id: check for check in audit.checks}

    assert audit.virtual_transport_status == "Passed"
    assert checks["r7c.secure-channel"].status == "Passed"
    assert checks["r7c.subscription-integrity"].status == "Passed"
    assert checks["r7c.zero-write"].status == "Passed"
    assert audit.vendor_adapter_status == "Open"
    assert audit.deployment_shadow_status == "Open"
    assert audit.reality_evidence_level == "None"


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda raw: raw["receipt"].update(writeOperationCount=1),
            "writeOperationCount",
        ),
        (
            lambda raw: raw["frames"][1].update(sequence=2),
            "frame sequence must be contiguous",
        ),
        (
            lambda raw: raw.update(realityValidationStatus="Passed"),
            "realityValidationStatus",
        ),
        (
            lambda raw: raw.update(deviceSafetyStatus="DeviceSafe"),
            "deviceSafetyStatus",
        ),
    ),
)
def test_r7c_transport_evidence_rejects_write_gap_and_gate_promotion(
    mutate: Any,
    message: str,
) -> None:
    raw = _transport_evidence_payload()
    mutate(raw)
    raw["contentHash"] = canonical_hash(
        {key: value for key, value in raw.items() if key != "contentHash"}
    )

    with pytest.raises(ValidationError, match=message):
        OpcUaTransportEvidence.model_validate(raw)


def test_r7c_public_run_supports_only_contract_and_virtual_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7c_runtime

    monkeypatch.setattr(r7c_runtime.platform, "system", lambda: "Windows")
    payload = assess_r7c_payload(
        R7CAssessmentRequest(transportEvidence=_transport_evidence())
    )
    bundle = evaluate_run(RunSpec.model_validate(payload.run_spec))
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Inconclusive"
    assert claims["control.opcua-adapter-contract-ready-claim@1"] == "Supported"
    assert claims["control.opcua-virtual-transport-claim@1"] == "Supported"
    assert claims["control.opcua-real-deployment-claim@1"] == "Inconclusive"


def test_r7c_default_run_is_structured_inconclusive_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7c_runtime

    monkeypatch.setattr(r7c_runtime.platform, "system", lambda: "Windows")

    bundle = evaluate_run(validate_r7c_example_run_spec())

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Inconclusive"


def test_r7c_non_windows_runtime_is_structured_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7c_runtime

    monkeypatch.setattr(r7c_runtime.platform, "system", lambda: "Linux")

    bundle = evaluate_run(validate_r7c_example_run_spec())

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Unsupported"
    assert all(
        result.reason_code == "UnsupportedRuntimePlatform"
        for result in bundle.report.metric_results
    )


def test_r7c_public_artifacts_never_serialize_safety_claims() -> None:
    serialized = json.dumps(
        r7c_example_payload().model_dump(mode="json", by_alias=True), sort_keys=True
    )

    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_r7c_catalog_has_only_non_reality_counting_scenarios() -> None:
    scenarios = list_r7c_scenarios()

    assert scenarios
    assert all(scenario.counts_toward_reality is False for scenario in scenarios)
