from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from axiom.control import (
    R7EAssessmentRequest,
    R7E_DEFAULT_SCENARIO_ID,
    R7E_DOMAIN_PACK_ID,
    BeckhoffShadowCaptureAuthorization,
    assess_r7e_payload,
    assess_r7e_shadow,
    build_default_beckhoff_shadow_witness_profile,
    build_r7e_manifest,
    list_r7e_scenarios,
    r7e_example_payload,
    validate_r7e_example_run_spec,
)
from axiom.control.models import canonical_hash
from axiom.five_axis import f4_example_payload
from axiom.run import evaluate_run


def _authorization_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaId": "axiom.control.beckhoff-shadow-capture-authorization@1",
        "authorizationId": "beckhoff.shadow.test-authorization@1",
        "dataOwnerId": "test-owner",
        "controllerProfileContentHash": "3" * 64,
        "commandContentHash": "4" * 64,
        "authorizedFrom": "2026-08-13T07:59:00+00:00",
        "authorizedUntil": "2026-08-13T08:01:00+00:00",
        "acquisitionPurpose": "deployment-shadow-validation",
        "capturedOutsideRepository": True,
        "evaluationAuthorized": True,
        "attestationKind": "data-owner-attestation",
        "attestationContentHash": "5" * 64,
    }
    return {**payload, "contentHash": canonical_hash(payload)}


def _complete_shadow_criteria_inputs() -> dict[str, SimpleNamespace]:
    command_hash = "4" * 64
    vendor = SimpleNamespace(content_hash="1" * 64, binding_status="Bound")
    runtime = SimpleNamespace(
        content_hash="2" * 64,
        profile_content_hash=vendor.content_hash,
        source_kind="vendor-runtime",
        installation=SimpleNamespace(status="Passed"),
        license=SimpleNamespace(state="Full"),
        server_identity=SimpleNamespace(),
        channel_access=SimpleNamespace(),
        write_rejection=SimpleNamespace(status="Rejected"),
        transport_evidence_content_hash="a" * 64,
    )
    controller = SimpleNamespace(content_hash="3" * 64, target_status="Selected")
    authority = SimpleNamespace(
        content_hash="6" * 64,
        controller_profile_content_hash=controller.content_hash,
        verification_status="Verified",
        attestation_kind="independent-audit",
        granted_operations=("read", "subscribe"),
        principal_id="test-reader",
        enforcement_point="controller",
    )
    authorization = SimpleNamespace(
        content_hash="7" * 64,
        controller_profile_content_hash=controller.content_hash,
        command_content_hash=command_hash,
        authorized_from="2026-08-13T07:59:00+00:00",
        authorized_until="2026-08-13T08:01:00+00:00",
    )
    witness = SimpleNamespace(
        content_hash="8" * 64,
        vendor_profile_content_hash=vendor.content_hash,
        runtime_evidence_content_hash=runtime.content_hash,
        expected_command_content_hash=command_hash,
        binding_status="Bound",
        capture_policy="sample-index-triggered-batch-read",
        maximum_timestamp_uncertainty_ms=20.0,
        nodes=(None,) * 7,
    )
    command = SimpleNamespace(
        content_id=command_hash,
        samples=tuple(SimpleNamespace(sample_index=index) for index in range(2)),
    )
    frames = []
    for index in range(2):
        timestamp = f"2026-08-13T08:00:0{index}+00:00"
        samples = tuple(
            SimpleNamespace(
                quality="good",
                status_code="Good",
                source_timestamp=timestamp,
                server_timestamp=timestamp,
            )
            for _ in range(5)
        )
        frames.append(
            SimpleNamespace(
                sequence=index,
                protocol_sequence_number=index + 1,
                notified_sample_index=index,
                read_sample_index=index,
                command_content_hash=command_hash,
                host_timestamp=timestamp,
                samples=samples,
            )
        )
    receipt = SimpleNamespace(
        status="Succeeded",
        opened_at="2026-08-13T08:00:00+00:00",
        closed_at="2026-08-13T08:00:01+00:00",
        accepted_frame_count=2,
        rejected_frame_count=0,
        dropped_sample_index_count=0,
        read_operation_count=2,
        write_operation_count=0,
        method_call_operation_count=0,
    )
    evidence = SimpleNamespace(
        content_hash="9" * 64,
        source_kind="controller-live-read",
        declared_real=True,
        vendor_profile_content_hash=vendor.content_hash,
        runtime_evidence_content_hash=runtime.content_hash,
        witness_profile_content_hash=witness.content_hash,
        controller_profile_content_hash=controller.content_hash,
        authority_content_hash=authority.content_hash,
        capture_authorization_content_hash=authorization.content_hash,
        command_content_hash=command_hash,
        captured_at=receipt.closed_at,
        frames=tuple(frames),
        receipt=receipt,
    )
    return {
        "vendor_profile": vendor,
        "runtime_evidence": runtime,
        "witness_profile": witness,
        "controller_profile": controller,
        "authority": authority,
        "capture_authorization": authorization,
        "command": command,
        "shadow_evidence": evidence,
    }


def test_r7e_manifest_freezes_windows_beckhoff_shadow_witness() -> None:
    manifest = build_r7e_manifest()

    assert manifest.domain_pack_id == R7E_DOMAIN_PACK_ID
    assert manifest.supported_platforms == ("Windows",)
    assert manifest.target_vendor == "Beckhoff Automation"
    assert manifest.target_interface == "TF6100 OPC UA Server"
    assert manifest.capture_policy == "sample-index-triggered-batch-read"
    assert manifest.device_write_allowed is False
    assert manifest.deployment_shadow_status == "Open"
    assert manifest.reality_validation_status == "Open"


def test_r7e_default_witness_profile_has_no_fabricated_node_bindings() -> None:
    profile = build_default_beckhoff_shadow_witness_profile()

    assert profile.binding_status == "Open"
    assert profile.runtime_evidence_content_hash is None
    assert profile.expected_command_content_hash is None
    assert profile.nodes == ()
    assert profile.device_write_allowed is False


def test_r7e_capture_authorization_requires_an_ordered_utc_window() -> None:
    authorization = BeckhoffShadowCaptureAuthorization.model_validate(
        _authorization_payload()
    )

    assert authorization.authorized_from == "2026-08-13T07:59:00+00:00"
    assert authorization.authorized_until == "2026-08-13T08:01:00+00:00"

    reversed_window = _authorization_payload()
    reversed_window["authorizedUntil"] = "2026-08-13T07:58:00+00:00"
    reversed_window["contentHash"] = canonical_hash(
        {key: value for key, value in reversed_window.items() if key != "contentHash"}
    )
    with pytest.raises(ValueError, match="authorizedUntil"):
        BeckhoffShadowCaptureAuthorization.model_validate(reversed_window)

    naive_window = _authorization_payload()
    naive_window["authorizedFrom"] = "2026-08-13T07:59:00"
    naive_window["contentHash"] = canonical_hash(
        {key: value for key, value in naive_window.items() if key != "contentHash"}
    )
    with pytest.raises(ValueError, match="explicit UTC offset"):
        BeckhoffShadowCaptureAuthorization.model_validate(naive_window)


def test_r7e_external_command_requires_and_preserves_case_identity() -> None:
    command = f4_example_payload("canonical-head-table-solver")["artifacts"][
        "referenceCommand"
    ]

    with pytest.raises(ValidationError, match="caseId is required"):
        R7EAssessmentRequest.model_validate({"command": command})

    request = R7EAssessmentRequest.model_validate(
        {"caseId": "site.part-family-17@1", "command": command}
    )
    payload = assess_r7e_payload(request)

    assert payload.run_spec["request"]["case"]["caseId"] == "site.part-family-17@1"


def test_r7e_complete_real_criteria_support_only_case_scoped_shadow() -> None:
    audit = assess_r7e_shadow(**_complete_shadow_criteria_inputs())

    assert audit.readiness_outcome == "Passed"
    assert audit.deployment_shadow_status == "Passed"
    assert audit.counts_toward_deployment_shadow is True
    assert audit.reality_validation_status == "Open"
    assert audit.counts_toward_reality is False
    assert audit.device_safety_status == "NotAssessed"
    assert audit.process_safety_status == "NotAssessed"


@pytest.mark.parametrize(
    ("case", "check_id", "reason_code"),
    (
        (
            "contract-fixture",
            "r7e.external-provenance",
            "ContractFixtureNotRealControllerCapture",
        ),
        (
            "expired-authorization",
            "r7e.external-provenance",
            "CaptureOutsideAuthorizationWindow",
        ),
        (
            "profile-mismatch",
            "r7e.witness-profile",
            "WitnessVendorProfileMismatch",
        ),
        (
            "command-mismatch",
            "r7e.command-binding",
            "CommandContentHashMismatch",
        ),
        (
            "sample-index-gap",
            "r7e.frame-coverage",
            "IncompleteOrMismatchedSampleIndexCoverage",
        ),
        (
            "duplicate-sample-index",
            "r7e.frame-coverage",
            "IncompleteOrMismatchedSampleIndexCoverage",
        ),
        (
            "bad-quality",
            "r7e.timestamp-integrity",
            "BadOrSuspectAxisSample",
        ),
        (
            "timestamp-skew",
            "r7e.timestamp-integrity",
            "TimestampUncertaintyExceeded",
        ),
        (
            "non-monotonic-order",
            "r7e.timestamp-integrity",
            "NonMonotonicCaptureOrder",
        ),
        (
            "write-observed",
            "r7e.zero-write",
            "ForbiddenDeviceOperationObserved",
        ),
        (
            "method-call-observed",
            "r7e.zero-write",
            "ForbiddenDeviceOperationObserved",
        ),
    ),
)
def test_r7e_real_shadow_criteria_fail_closed(
    case: str,
    check_id: str,
    reason_code: str,
) -> None:
    inputs = _complete_shadow_criteria_inputs()
    evidence = inputs["shadow_evidence"]
    if case == "contract-fixture":
        evidence.source_kind = "contract-fixture"
        evidence.declared_real = False
    elif case == "expired-authorization":
        inputs["capture_authorization"].authorized_until = (
            "2026-08-13T07:58:00+00:00"
        )
    elif case == "profile-mismatch":
        inputs["witness_profile"].vendor_profile_content_hash = "0" * 64
    elif case == "command-mismatch":
        evidence.command_content_hash = "0" * 64
    elif case == "sample-index-gap":
        evidence.frames[1].notified_sample_index = 2
        evidence.frames[1].read_sample_index = 2
    elif case == "duplicate-sample-index":
        evidence.frames[1].notified_sample_index = 0
        evidence.frames[1].read_sample_index = 0
    elif case == "bad-quality":
        evidence.frames[0].samples[0].quality = "bad"
    elif case == "timestamp-skew":
        evidence.frames[0].samples[0].source_timestamp = (
            "2026-08-13T08:00:00.100000+00:00"
        )
    elif case == "non-monotonic-order":
        evidence.frames[1].protocol_sequence_number = 1
    elif case == "write-observed":
        evidence.receipt.write_operation_count = 1
    elif case == "method-call-observed":
        evidence.receipt.method_call_operation_count = 1

    audit = assess_r7e_shadow(**inputs)
    checks = {check.check_id: check for check in audit.checks}

    assert checks[check_id].status == "Blocked"
    assert checks[check_id].reason_code == reason_code
    assert audit.deployment_shadow_status == "Blocked"
    assert audit.counts_toward_deployment_shadow is False


def test_r7e_default_payload_is_open_and_not_reality_counting() -> None:
    payload = r7e_example_payload()

    assert payload.scenario.scenario_id == R7E_DEFAULT_SCENARIO_ID
    assert payload.readiness_audit.deployment_shadow_status == "Open"
    assert payload.readiness_audit.reality_validation_status == "Open"
    assert payload.readiness_audit.counts_toward_deployment_shadow is False
    assert payload.shadow_evidence is None


def test_r7e_default_run_is_inconclusive_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7e_runtime

    monkeypatch.setattr(r7e_runtime.platform, "system", lambda: "Windows")

    bundle = evaluate_run(validate_r7e_example_run_spec())

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Inconclusive"
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}
    assert claims["control.beckhoff-shadow-contract-claim@1"] == "Supported"
    assert claims["control.beckhoff-deployment-shadow-claim@1"] == "Inconclusive"
    assert claims["control.beckhoff-deployment-reality-claim@2"] == "Inconclusive"


def test_r7e_non_windows_runtime_is_structured_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7e_runtime

    monkeypatch.setattr(r7e_runtime.platform, "system", lambda: "Linux")

    bundle = evaluate_run(validate_r7e_example_run_spec())

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Unsupported"
    assert all(
        result.reason_code == "UnsupportedRuntimePlatform"
        for result in bundle.report.metric_results
    )


def test_r7e_public_catalog_never_bundles_fake_real_evidence_or_safety_claims() -> None:
    scenarios = list_r7e_scenarios()
    serialized = json.dumps(
        r7e_example_payload().model_dump(mode="json", by_alias=True), sort_keys=True
    )

    assert scenarios
    assert all(scenario.counts_toward_deployment_shadow is False for scenario in scenarios)
    assert "controller-live-read" not in serialized
    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized
