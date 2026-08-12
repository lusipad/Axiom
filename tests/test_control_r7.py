from __future__ import annotations

import json

import pytest

from axiom import evaluate_run
from axiom.control import (
    R7_SCENARIO_IDS,
    RuntimeSpec,
    build_r7_manifest,
    load_r7_scenario,
    r7_example_payload,
    run_shadow,
    validate_r7_example_run_spec,
)
from axiom.models import RunSpec


def test_r7_default_shadow_replay_completes_without_device_authority() -> None:
    payload = r7_example_payload()
    audit = payload.runtime_audit

    assert audit.final_state == "Completed"
    assert audit.admission_decision.status == "Admitted"
    assert audit.acceptance_record.granted_permission == "Shadow"
    assert audit.device_write_allowed is False
    assert audit.device_write_performed is False
    assert audit.synthetic_shadow_contract_status == "Passed"
    assert audit.deployment_shadow_status == "Open"
    assert audit.controlled_trial_status == "Open"
    assert audit.closed_loop_status == "Open"
    assert audit.standards_compliance_status == "NotAssessed"
    assert audit.stop_receipt.requested is False
    assert audit.rollback_receipt.status == "NotRequired"


def test_r7_limit_breach_stops_shadow_and_only_retains_the_baseline() -> None:
    scenario = load_r7_scenario("synthetic-shadow-limit-breach")
    audit = scenario.runtime_audit

    assert audit.final_state == "RollbackVerified"
    assert audit.stop_receipt.requested is True
    assert audit.stop_receipt.effect == "PromotionSuppressed"
    assert audit.stop_receipt.device_stop_command_issued is False
    assert audit.stop_receipt.device_acknowledged is False
    assert audit.rollback_receipt.status == "BaselineRetained"
    assert audit.rollback_receipt.device_write_issued is False
    assert audit.rollback_receipt.device_readback_verified is False
    assert any(
        finding.status == "Breach"
        and "LinearFollowingErrorLimitExceeded" in finding.reason_codes
        for finding in audit.monitor_findings
    )


@pytest.mark.parametrize(
    ("scenario_id", "reason_code"),
    [
        ("deployment-shadow-reality-open", "DeploymentShadowEvidenceMissing"),
        ("controlled-trial-without-authority", "PermissionCeilingExceeded"),
        ("device-write-request-blocked", "DeviceWriteForbidden"),
    ],
)
def test_r7_fail_closed_scenarios_never_arm(scenario_id: str, reason_code: str) -> None:
    audit = load_r7_scenario(scenario_id).runtime_audit

    assert audit.final_state == "Blocked"
    assert audit.admission_decision.status == "Blocked"
    assert reason_code in audit.admission_decision.reason_codes
    assert audit.acceptance_record.granted_permission == "Denied"
    assert audit.device_write_allowed is False
    assert audit.device_write_performed is False
    assert [event.to_state for event in audit.transitions] == ["Prepared", "Blocked"]


@pytest.mark.parametrize("requested_permission", ["Denied", "Offline", "Advisory"])
def test_r7_never_escalates_a_lower_permission_to_shadow(
    requested_permission: str,
) -> None:
    scenario = load_r7_scenario()
    raw_spec = scenario.runtime_spec.model_dump(mode="json", by_alias=True)
    raw_spec["requestedPermission"] = requested_permission

    audit = run_shadow(
        RuntimeSpec.model_validate(raw_spec), scenario.recommendation_set
    )

    assert audit.final_state == "Blocked"
    assert audit.admission_decision.granted_permission == "Denied"
    assert "UnsupportedPermissionMode" in audit.admission_decision.reason_codes


def test_r7_does_not_trust_an_opaque_deployment_evidence_hash() -> None:
    scenario = load_r7_scenario("deployment-shadow-reality-open")
    raw_spec = scenario.runtime_spec.model_dump(mode="json", by_alias=True)
    raw_spec["deploymentShadowEvidenceHash"] = "0" * 64

    audit = run_shadow(
        RuntimeSpec.model_validate(raw_spec), scenario.recommendation_set
    )

    assert audit.final_state == "Blocked"
    assert "DeploymentShadowEvidenceUnverified" in audit.admission_decision.reason_codes


def test_r7_acceptance_record_is_independent_from_the_r6_recommendation() -> None:
    payload = r7_example_payload()

    assert (
        payload.runtime_spec.recommendation_set_content_hash
        == payload.recommendation_set.content_hash
    )
    assert (
        payload.runtime_audit.acceptance_record.evidence_snapshot_hash
        == payload.recommendation_set.content_hash
    )
    assert (
        payload.runtime_audit.acceptance_record.content_hash
        != payload.recommendation_set.content_hash
    )
    assert payload.recommendation_set.permission_level == "Offline"
    assert payload.recommendation_set.device_write_allowed is False


def test_r7_domain_runtime_replays_the_audit_and_keeps_deployment_open() -> None:
    bundle = evaluate_run(validate_r7_example_run_spec())
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Passed"
    assert claims["control.runtime-audit-integrity-claim@1"] == "Supported"
    assert claims["control.admission-policy-enforced-claim@1"] == "Supported"
    assert claims["control.no-device-write-boundary-claim@1"] == "Supported"
    assert claims["control.deployment-readiness-claim@1"] == "Inconclusive"


def test_r7_breach_run_requires_stop_and_rollback_metrics() -> None:
    bundle = evaluate_run(validate_r7_example_run_spec("synthetic-shadow-limit-breach"))
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}

    assert bundle.run.case_outcome.value == "Passed"
    assert claims["control.shadow-stop-path-claim@1"] == "Supported"
    assert claims["control.shadow-rollback-boundary-claim@1"] == "Supported"


def test_r7_tampered_audit_is_rejected_before_it_can_publish_claims() -> None:
    payload = validate_r7_example_run_spec().model_dump(mode="json", by_alias=True)
    payload["request"]["artifact"]["finalState"] = "RollbackVerified"
    bundle = evaluate_run(RunSpec.model_validate(payload))

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Invalid"
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_r7_manifest_and_scenarios_freeze_shadow_as_the_permission_ceiling() -> None:
    manifest = build_r7_manifest()

    assert manifest.supported_platforms == ("Windows",)
    assert manifest.permission_ceiling == "Shadow"
    assert manifest.device_write_allowed is False
    assert manifest.scenario_ids == R7_SCENARIO_IDS
    assert manifest.synthetic_shadow_contract_status == "Passed"
    assert manifest.deployment_shadow_status == "Open"
    assert manifest.controlled_trial_status == "Open"
    assert manifest.closed_loop_status == "Open"


def test_r7_artifacts_do_not_serialize_forbidden_safety_claims() -> None:
    serialized = json.dumps(
        r7_example_payload().model_dump(mode="json", by_alias=True), sort_keys=True
    )

    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_r7_non_windows_runtime_is_explicitly_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import runtime as runtime_module

    monkeypatch.setattr(runtime_module.platform, "system", lambda: "Linux")

    bundle = evaluate_run(validate_r7_example_run_spec())

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Unsupported"
    assert all(
        result.reason_code == "UnsupportedRuntimePlatform"
        for result in bundle.report.metric_results
    )
