from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from axiom import evaluate_run
from axiom.control import (
    R7B_DEFAULT_SCENARIO_ID,
    R7B_DOMAIN_PACK_ID,
    DeploymentAdapterReceipt,
    DeploymentShadowCapture,
    DeploymentShadowEvidenceSet,
    ReadOnlyAuthorityEvidence,
    assess_r7b_deployment_shadow,
    build_r7b_manifest,
    list_r7b_scenarios,
    r7b_contract_fixture_evidence,
    r7b_example_payload,
    validate_r7b_example_run_spec,
)
from axiom.control.models import canonical_hash
from axiom.models import RunSpec


def test_r7b_manifest_freezes_vendor_neutral_windows_readiness_boundary() -> None:
    manifest = build_r7b_manifest()

    assert manifest.domain_pack_id == R7B_DOMAIN_PACK_ID
    assert manifest.supported_platforms == ("Windows",)
    assert manifest.permission_ceiling == "Shadow"
    assert manifest.device_write_allowed is False
    assert manifest.contract_readiness_status == "Passed"
    assert manifest.vendor_adapter_status == "Open"
    assert manifest.deployment_shadow_status == "Open"
    assert manifest.controlled_trial_status == "Open"
    assert manifest.closed_loop_status == "Open"


def test_r7b_default_payload_requires_external_real_evidence() -> None:
    payload = r7b_example_payload()

    assert payload.scenario.scenario_id == R7B_DEFAULT_SCENARIO_ID
    assert payload.evidence_set is None
    assert payload.readiness_audit.readiness_outcome == "Open"
    assert payload.readiness_audit.deployment_shadow_status == "Open"
    checks = {check.check_id: check for check in payload.readiness_audit.checks}
    assert checks["r7b.contract"].status == "Passed"
    assert checks["r7b.external-evidence"].reason_code == "DeploymentShadowEvidenceMissing"
    assert checks["r7b.vendor-adapter"].reason_code == "VendorAdapterUnselected"


def test_r7b_contract_fixture_cannot_be_promoted_to_real_deployment() -> None:
    evidence = r7b_contract_fixture_evidence()
    audit = assess_r7b_deployment_shadow(evidence)

    assert evidence.capture.source_kind == "contract-fixture"
    assert audit.readiness_outcome == "Blocked"
    assert audit.deployment_shadow_status == "Open"
    assert audit.reality_evidence_level == "None"
    checks = {check.check_id: check for check in audit.checks}
    assert checks["r7b.external-evidence"].reason_code == "NonRealEvidenceSource"
    assert checks["r7b.authority"].reason_code == "AuthorityEvidenceUnverified"


def test_r7b_client_cannot_self_assert_controller_authority() -> None:
    raw = r7b_contract_fixture_evidence().authority.model_dump(
        mode="json", by_alias=True
    )
    raw["verificationStatus"] = "Verified"

    with pytest.raises(ValidationError, match="trustAnchorContentHash"):
        ReadOnlyAuthorityEvidence.model_validate(raw)


def test_r7b_real_looking_upload_cannot_bypass_missing_vendor_verifier() -> None:
    raw = r7b_contract_fixture_evidence().model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    profile = raw["controllerProfile"]
    profile.update(
        {
            "vendor": "SelectedVendor",
            "controllerFamily": "selected-family",
            "controllerModel": "selected-model",
            "softwareVersion": "selected-version",
            "targetStatus": "Selected",
        }
    )
    profile["contentHash"] = canonical_hash(
        {key: value for key, value in profile.items() if key != "contentHash"}
    )
    profile_hash = profile["contentHash"]

    authority = raw["authority"]
    authority.update(
        {
            "controllerProfileContentHash": profile_hash,
            "attestationKind": "vendor-signed",
            "verificationStatus": "Verified",
            "trustAnchorContentHash": "3" * 64,
        }
    )
    authority["contentHash"] = canonical_hash(
        {key: value for key, value in authority.items() if key != "contentHash"}
    )

    capture = raw["capture"]
    capture.update(
        {
            "sourceKind": "controller-export",
            "declaredReal": True,
            "controllerProfileContentHash": profile_hash,
        }
    )
    capture["contentHash"] = canonical_hash(
        {key: value for key, value in capture.items() if key != "contentHash"}
    )

    receipt = raw["adapterReceipt"]
    receipt.update(
        {
            "controllerProfileContentHash": profile_hash,
            "captureContentHash": capture["contentHash"],
        }
    )
    receipt["contentHash"] = canonical_hash(
        {key: value for key, value in receipt.items() if key != "contentHash"}
    )

    binding = raw["clockSignalBinding"]
    binding.update(
        {
            "controllerProfileContentHash": profile_hash,
            "clockMethod": "vendor-declared",
        }
    )
    binding["contentHash"] = canonical_hash(
        {key: value for key, value in binding.items() if key != "contentHash"}
    )

    provenance = raw["provenance"]
    provenance.update(
        {
            "capturedOutsideRepository": True,
            "sourceContentHash": capture["contentHash"],
        }
    )
    provenance["contentHash"] = canonical_hash(
        {key: value for key, value in provenance.items() if key != "contentHash"}
    )
    raw["contentHash"] = canonical_hash(
        {key: value for key, value in raw.items() if key != "contentHash"}
    )

    evidence = DeploymentShadowEvidenceSet.model_validate(raw)
    audit = assess_r7b_deployment_shadow(evidence)
    checks = {check.check_id: check for check in audit.checks}

    assert checks["r7b.external-evidence"].status == "Passed"
    assert checks["r7b.capture-integrity"].status == "Passed"
    assert checks["r7b.clock-signal-coverage"].status == "Passed"
    assert checks["r7b.vendor-adapter"].reason_code == "VendorAdapterVerifierUnavailable"
    assert checks["r7b.authority"].reason_code == "AuthorityVerifierUnavailable"
    assert checks["r7b.reality-gate"].status == "Open"
    assert audit.readiness_outcome == "Open"
    assert audit.deployment_shadow_status == "Open"


def test_r7b_capture_rejects_sequence_gaps_and_receipt_rejects_writes() -> None:
    evidence = r7b_contract_fixture_evidence()
    capture = evidence.capture.model_dump(mode="json", by_alias=True)
    capture["frames"][1]["sequence"] = 2
    capture["contentHash"] = canonical_hash(
        {key: value for key, value in capture.items() if key != "contentHash"}
    )

    with pytest.raises(ValidationError, match="sequence must be contiguous"):
        DeploymentShadowCapture.model_validate(capture)

    receipt = evidence.adapter_receipt.model_dump(mode="json", by_alias=True)
    receipt["writeOperationCount"] = 1

    with pytest.raises(ValidationError, match="writeOperationCount"):
        DeploymentAdapterReceipt.model_validate(receipt)


def test_r7b_evidence_set_rejects_cross_object_hash_mismatch() -> None:
    raw = r7b_contract_fixture_evidence().model_dump(mode="json", by_alias=True)
    raw["adapterReceipt"]["captureContentHash"] = "0" * 64
    receipt_without_hash = {
        key: value
        for key, value in raw["adapterReceipt"].items()
        if key != "contentHash"
    }
    raw["adapterReceipt"]["contentHash"] = canonical_hash(receipt_without_hash)

    with pytest.raises(ValidationError, match="captureContentHash"):
        DeploymentShadowEvidenceSet.model_validate(raw)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda raw: raw["provenance"].update(sourceContentHash="9" * 64),
            "provenance sourceContentHash mismatch",
        ),
        (
            lambda raw: raw["adapterReceipt"].update(receivedSampleCount=3),
            "adapterReceipt receivedSampleCount mismatch",
        ),
    ),
)
def test_r7b_evidence_set_rejects_provenance_and_sample_count_mismatch(
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    raw = r7b_contract_fixture_evidence().model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    mutate(raw)
    object_key = "provenance" if message.startswith("provenance") else "adapterReceipt"
    raw[object_key]["contentHash"] = canonical_hash(
        {
            key: value
            for key, value in raw[object_key].items()
            if key != "contentHash"
        }
    )
    raw["contentHash"] = canonical_hash(
        {key: value for key, value in raw.items() if key != "contentHash"}
    )

    with pytest.raises(ValidationError, match=message):
        DeploymentShadowEvidenceSet.model_validate(raw)


def test_r7b_public_run_stays_inconclusive_until_real_adapter_exists() -> None:
    bundle = evaluate_run(validate_r7b_example_run_spec())
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Inconclusive"
    assert claims["control.deployment-shadow-contract-ready-claim@1"] == "Supported"
    assert claims["control.deployment-shadow-reality-claim@1"] == "Inconclusive"


def test_r7b_tampered_readiness_audit_is_rejected() -> None:
    raw = validate_r7b_example_run_spec().model_dump(mode="json", by_alias=True)
    raw["request"]["artifact"]["deploymentShadowStatus"] = "Passed"

    bundle = evaluate_run(RunSpec.model_validate(raw))

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Invalid"
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_r7b_public_artifacts_never_serialize_device_safety_claims() -> None:
    serialized = json.dumps(
        r7b_example_payload().model_dump(mode="json", by_alias=True), sort_keys=True
    )

    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_r7b_catalog_has_only_non_reality_counting_contract_scenarios() -> None:
    scenarios = list_r7b_scenarios()

    assert scenarios
    assert scenarios[0].scenario_id == R7B_DEFAULT_SCENARIO_ID
    assert all(scenario.counts_toward_reality is False for scenario in scenarios)


def test_r7b_non_windows_runtime_is_structured_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import r7b_runtime

    monkeypatch.setattr(r7b_runtime.platform, "system", lambda: "Linux")

    bundle = evaluate_run(validate_r7b_example_run_spec())

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Unsupported"
    assert all(
        result.reason_code == "UnsupportedRuntimePlatform"
        for result in bundle.report.metric_results
    )
