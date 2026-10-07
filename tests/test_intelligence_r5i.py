from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache

import pytest

from axiom.cli import main
from axiom.intelligence import (
    R5IMonitoringSample,
    R5IPromotionDecision,
    assess_r5i_monitoring_window,
    build_r5h_assessment_request,
    build_r5i_manifest,
    build_r5i_monitoring_request,
    build_r5i_preflight_request,
    build_r5i_promotion_decision,
    build_r5i_rollback_request,
    apply_r5i_promotion_transaction,
    apply_r5i_rollback_transaction,
    assess_r5h_candidate_real_holdout,
    predict_r5i_active_model,
    preflight_r5i_model_promotion,
    read_r5i_registry_status,
    list_r5i_monitoring_windows,
)
from axiom.intelligence.models import canonical_hash
from tests.test_intelligence_r5h import build_test_only_r5h_chain


AUTHORITY_KEY = b"axiom-r5i-test-only-authority-key"
AUTHORITY_KEY_ID = "test-only-r5i-review-key"


@lru_cache(maxsize=1)
def _passed_chain():
    return build_test_only_r5h_chain()


def _approved_decision(dossier, assessment, *, decided_by: str = "independent-reviewer"):
    return build_r5i_promotion_decision(
        dossier,
        assessment,
        decision_id="axiom.intelligence.r5i.test-decision@1",
        decision="Approve",
        decided_by=decided_by,
        decided_at="2026-08-14T12:00:00+00:00",
        authority_key_id=AUTHORITY_KEY_ID,
        authority_key=AUTHORITY_KEY,
    )


def test_r5i_manifest_keeps_device_and_web_writes_forbidden() -> None:
    manifest = build_r5i_manifest()

    assert manifest.stage == "R5-I"
    assert manifest.platform == "windows"
    assert manifest.registry_kind == "sqlite-local"
    assert manifest.web_state_mutation_allowed is False
    assert manifest.local_cli_transaction_required is True
    assert manifest.automatic_model_promotion_allowed is False
    assert manifest.automatic_rollback_allowed is False
    assert manifest.automatic_deployment_allowed is False
    assert manifest.device_write_allowed is False


def test_r5i_cli_status_is_read_only_for_an_uninitialized_registry(
    tmp_path,
    capsys,
) -> None:
    registry = tmp_path / "uninitialized.db"

    exit_code = main(
        ["model-lifecycle", "status", "--registry", str(registry)]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["registryInitialized"] is False
    assert output["generation"] == 0
    assert output["modelRegistryWritePerformed"] is False
    assert output["deviceWriteAllowed"] is False
    assert not registry.exists()


def test_r5i_preflight_passes_only_for_replayed_case_scoped_evidence() -> None:
    dossier, _, _, assessment = _passed_chain()
    decision = _approved_decision(dossier, assessment)
    request = build_r5i_preflight_request(dossier, assessment, decision)

    first = preflight_r5i_model_promotion(
        request,
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        current_platform="Windows",
    )
    second = preflight_r5i_model_promotion(
        request,
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        current_platform="Windows",
    )

    assert first == second
    assert first.overall_status == "Passed"
    assert first.promotion_transaction_status == "Eligible"
    assert first.authorization_verified is True
    assert first.registry_transaction_allowed is True
    assert {check.status for check in first.checks} == {"Passed"}
    assert first.model_promotion_status == "NotPerformed"
    assert first.model_registry_write_performed is False
    assert first.activation_performed is False
    assert first.default_model_changed is False
    assert first.automatic_deployment_allowed is False
    assert first.device_write_allowed is False


def test_r5i_open_holdout_and_non_independent_reviewer_are_blocked() -> None:
    dossier, registration, _, passed = _passed_chain()
    open_assessment = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            dossier,
            registration,
            evidence_reports=(),
        ),
        current_platform="Windows",
    )
    open_decision = _approved_decision(dossier, open_assessment)
    open_report = preflight_r5i_model_promotion(
        build_r5i_preflight_request(dossier, open_assessment, open_decision),
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        current_platform="Windows",
    )
    assert open_report.overall_status == "Blocked"
    assert open_report.registry_transaction_allowed is False
    assert open_report.checks[1].reason_code == "CaseScopedHoldoutRequired"

    same_reviewer = _approved_decision(
        dossier,
        passed,
        decided_by=dossier.request.prepared_by,
    )
    reviewer_report = preflight_r5i_model_promotion(
        build_r5i_preflight_request(dossier, passed, same_reviewer),
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        current_platform="Windows",
    )
    assert reviewer_report.overall_status == "Blocked"
    assert reviewer_report.checks[4].reason_code == "IndependentReviewerRequired"


def test_r5i_reject_decision_is_final_without_transaction_eligibility() -> None:
    dossier, _, _, assessment = _passed_chain()
    decision = build_r5i_promotion_decision(
        dossier,
        assessment,
        decision_id="axiom.intelligence.r5i.test-rejection@1",
        decision="Reject",
        decided_by="independent-reviewer",
        decided_at="2026-08-14T12:00:00+00:00",
        authority_key_id=AUTHORITY_KEY_ID,
        authority_key=AUTHORITY_KEY,
    )
    report = preflight_r5i_model_promotion(
        build_r5i_preflight_request(dossier, assessment, decision),
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        current_platform="Windows",
    )

    assert report.overall_status == "Rejected"
    assert report.promotion_transaction_status == "Rejected"
    assert report.authorization_verified is True
    assert report.registry_transaction_allowed is False
    assert report.model_registry_write_performed is False


def test_r5i_tampered_or_unknown_authority_proof_is_blocked() -> None:
    dossier, _, _, assessment = _passed_chain()
    decision = _approved_decision(dossier, assessment)
    raw = deepcopy(decision.model_dump(mode="json", by_alias=True))
    raw["authorizationProof"] = "f" * 64
    raw["contentHash"] = canonical_hash(
        {key: value for key, value in raw.items() if key != "contentHash"}
    )
    tampered = R5IPromotionDecision.model_validate(raw)

    wrong_proof = preflight_r5i_model_promotion(
        build_r5i_preflight_request(dossier, assessment, tampered),
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        current_platform="Windows",
    )
    assert wrong_proof.overall_status == "Blocked"
    assert wrong_proof.authorization_verified is False
    assert wrong_proof.checks[5].reason_code == "AuthorizationProofMismatch"

    unknown_key = preflight_r5i_model_promotion(
        build_r5i_preflight_request(dossier, assessment, decision),
        authority_keys={},
        current_platform="Windows",
    )
    assert unknown_key.overall_status == "Blocked"
    assert unknown_key.checks[5].reason_code == "AuthorityKeyUnavailable"


def test_r5i_non_windows_fails_closed() -> None:
    dossier, _, _, assessment = _passed_chain()
    decision = _approved_decision(dossier, assessment)
    report = preflight_r5i_model_promotion(
        build_r5i_preflight_request(dossier, assessment, decision),
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        current_platform="Linux",
    )

    assert report.overall_status == "Blocked"
    assert report.registry_transaction_allowed is False
    assert report.checks[0].reason_code == "UnsupportedRuntimePlatform"


def test_r5i_blocked_preflight_never_creates_registry(tmp_path) -> None:
    dossier, registration, _, _ = _passed_chain()
    open_assessment = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            dossier,
            registration,
            evidence_reports=(),
        ),
        current_platform="Windows",
    )
    decision = _approved_decision(dossier, open_assessment)
    registry = tmp_path / "blocked.db"

    with pytest.raises(ValueError, match="preflight is not eligible"):
        apply_r5i_promotion_transaction(
            registry,
            build_r5i_preflight_request(dossier, open_assessment, decision),
            authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
            event_id="axiom.intelligence.r5i.blocked-activation@1",
            activated_at="2026-08-14T12:05:00+00:00",
            expected_generation=0,
            current_platform="Windows",
        )

    assert not registry.exists()


def test_r5i_promotion_is_atomic_persistent_and_idempotent(tmp_path) -> None:
    dossier, _, _, assessment = _passed_chain()
    decision = _approved_decision(dossier, assessment)
    request = build_r5i_preflight_request(dossier, assessment, decision)
    registry = tmp_path / "registry.db"

    receipt = apply_r5i_promotion_transaction(
        registry,
        request,
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        event_id="axiom.intelligence.r5i.activation@1",
        activated_at="2026-08-14T12:05:00+00:00",
        expected_generation=0,
        current_platform="Windows",
    )

    assert receipt.transaction_status == "Applied"
    assert receipt.event_kind == "Promotion"
    assert receipt.source_model_bundle_hash == dossier.baseline_model_bundle_hash
    assert receipt.target_model_bundle_hash == dossier.candidate_model_bundle_hash
    assert receipt.generation == 1
    assert receipt.readback_model_bundle_hash == dossier.candidate_model_bundle_hash
    assert receipt.readback_generation == 1
    assert receipt.model_promotion_status == "Performed"
    assert receipt.model_registry_write_performed is True
    assert receipt.activation_performed is True
    assert receipt.default_model_changed is True
    assert receipt.device_write_performed is False

    restarted = read_r5i_registry_status(registry)
    assert restarted.registry_initialized is True
    assert restarted.current_model_bundle_hash == dossier.candidate_model_bundle_hash
    assert restarted.rollback_baseline_model_bundle_hash == (
        dossier.baseline_model_bundle_hash
    )
    assert restarted.generation == 1
    assert restarted.latest_event == receipt

    replayed = apply_r5i_promotion_transaction(
        registry,
        request,
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        event_id="axiom.intelligence.r5i.activation@1",
        activated_at="2026-08-14T12:05:00+00:00",
        expected_generation=0,
        current_platform="Windows",
    )
    assert replayed == receipt
    assert read_r5i_registry_status(registry).generation == 1


def test_r5i_cli_promotes_and_predicts_only_through_the_local_registry(
    tmp_path,
    capsys,
) -> None:
    dossier, _, _, assessment = _passed_chain()
    decision = _approved_decision(dossier, assessment)
    request = build_r5i_preflight_request(dossier, assessment, decision)
    request_path = tmp_path / "promotion.json"
    key_path = tmp_path / "authority.key"
    registry = tmp_path / "cli-registry.db"
    request_path.write_text(
        request.model_dump_json(indent=2, by_alias=True),
        encoding="utf-8",
    )
    key_path.write_bytes(AUTHORITY_KEY)

    exit_code = main(
        [
            "model-lifecycle",
            "promote",
            str(request_path),
            "--registry",
            str(registry),
            "--authority-key-file",
            str(key_path),
            "--event-id",
            "axiom.intelligence.r5i.cli-activation@1",
            "--activated-at",
            "2026-08-14T12:05:00+00:00",
            "--expected-generation",
            "0",
        ]
    )
    receipt = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert receipt["eventKind"] == "Promotion"
    assert receipt["generation"] == 1
    assert receipt["targetModelBundleHash"] == dossier.candidate_model_bundle_hash
    assert receipt["deviceWritePerformed"] is False

    prediction_exit = main(
        [
            "model-lifecycle",
            "predict",
            "--registry",
            str(registry),
            "--feed-override",
            "0.825",
            "--sample-period",
            "0.08",
        ]
    )
    prediction = json.loads(capsys.readouterr().out)
    assert prediction_exit == 0
    assert prediction["modelBundleHash"] == dossier.candidate_model_bundle_hash
    assert prediction["deviceWriteAllowed"] is False


def test_r5i_generation_conflict_and_precommit_failure_leave_no_partial_state(
    tmp_path,
    monkeypatch,
) -> None:
    dossier, _, _, assessment = _passed_chain()
    decision = _approved_decision(dossier, assessment)
    request = build_r5i_preflight_request(dossier, assessment, decision)
    registry = tmp_path / "fault.db"

    def fail_before_commit() -> None:
        raise RuntimeError("injected precommit failure")

    monkeypatch.setattr(
        "axiom.intelligence.r5i_registry._transaction_checkpoint",
        fail_before_commit,
    )
    with pytest.raises(RuntimeError, match="injected precommit failure"):
        apply_r5i_promotion_transaction(
            registry,
            request,
            authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
            event_id="axiom.intelligence.r5i.faulted-activation@1",
            activated_at="2026-08-14T12:05:00+00:00",
            expected_generation=0,
            current_platform="Windows",
        )

    status = read_r5i_registry_status(registry)
    assert status.registry_initialized is True
    assert status.current_model_bundle_hash is None
    assert status.generation == 0
    assert status.latest_event is None

    monkeypatch.undo()
    applied = apply_r5i_promotion_transaction(
        registry,
        request,
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        event_id="axiom.intelligence.r5i.activation-after-fault@1",
        activated_at="2026-08-14T12:06:00+00:00",
        expected_generation=0,
        current_platform="Windows",
    )
    assert applied.generation == 1

    second_decision = build_r5i_promotion_decision(
        dossier,
        assessment,
        decision_id="axiom.intelligence.r5i.second-decision@1",
        decision="Approve",
        decided_by="second-independent-reviewer",
        decided_at="2026-08-14T12:10:00+00:00",
        authority_key_id=AUTHORITY_KEY_ID,
        authority_key=AUTHORITY_KEY,
    )
    with pytest.raises(ValueError, match="generation conflict"):
        apply_r5i_promotion_transaction(
            registry,
            build_r5i_preflight_request(dossier, assessment, second_decision),
            authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
            event_id="axiom.intelligence.r5i.conflicting-activation@1",
            activated_at="2026-08-14T12:11:00+00:00",
            expected_generation=0,
            current_platform="Windows",
        )
    assert read_r5i_registry_status(registry).generation == 1


def _activated_registry(tmp_path):
    dossier, _, _, assessment = _passed_chain()
    decision = _approved_decision(dossier, assessment)
    request = build_r5i_preflight_request(dossier, assessment, decision)
    registry = tmp_path / "active.db"
    receipt = apply_r5i_promotion_transaction(
        registry,
        request,
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        event_id="axiom.intelligence.r5i.active-candidate@1",
        activated_at="2026-08-14T12:05:00+00:00",
        expected_generation=0,
        current_platform="Windows",
    )
    return registry, dossier, assessment, receipt


def test_r5i_active_prediction_uses_registry_default(tmp_path) -> None:
    registry, dossier, _, _ = _activated_registry(tmp_path)

    prediction = predict_r5i_active_model(
        registry,
        feed_override=0.825,
        sample_period=0.08,
    )

    assert prediction.model_bundle_hash == dossier.candidate_model_bundle_hash
    assert prediction.status == "Predicted"
    assert prediction.device_write_allowed is False


def test_r5i_monitoring_healthy_open_and_rollback_required(tmp_path) -> None:
    registry, dossier, _, _ = _activated_registry(tmp_path)
    status = read_r5i_registry_status(registry)
    prediction = predict_r5i_active_model(
        registry,
        feed_override=0.825,
        sample_period=0.08,
    )
    actuals = {item.target_id: item.value for item in prediction.predictions}

    healthy_request = build_r5i_monitoring_request(
        registry_status=status,
        window_id="axiom.intelligence.r5i.healthy-window@1",
        opened_at="2026-08-14T13:00:00+00:00",
        closed_at="2026-08-14T13:05:00+00:00",
        samples=(
            R5IMonitoringSample(
                sampleId="healthy-1",
                feedOverride=0.825,
                samplePeriod=0.08,
                actualCycleTimeSeconds=actuals["cycleTimeSeconds"],
                actualLinearFollowingErrorMaxMm=actuals[
                    "linearFollowingErrorMaxMm"
                ],
                evidenceContentHash="a" * 64,
            ),
        ),
        maximum_cycle_rmse_seconds=0.01,
        maximum_linear_rmse_mm=0.01,
    )
    healthy = assess_r5i_monitoring_window(registry, healthy_request)
    assert healthy.monitoring_status == "Healthy"
    assert healthy.rollback_required is False
    assert tuple(item.status for item in healthy.target_results) == (
        "Passed",
        "Passed",
    )

    open_request = build_r5i_monitoring_request(
        registry_status=status,
        window_id="axiom.intelligence.r5i.open-window@1",
        opened_at="2026-08-14T13:10:00+00:00",
        closed_at="2026-08-14T13:15:00+00:00",
        samples=(
            R5IMonitoringSample(
                sampleId="unlabeled-1",
                feedOverride=0.825,
                samplePeriod=0.08,
            ),
        ),
        maximum_cycle_rmse_seconds=0.01,
        maximum_linear_rmse_mm=0.01,
    )
    open_report = assess_r5i_monitoring_window(registry, open_request)
    assert open_report.monitoring_status == "Open"
    assert open_report.rollback_required is False

    regression_request = build_r5i_monitoring_request(
        registry_status=status,
        window_id="axiom.intelligence.r5i.regression-window@1",
        opened_at="2026-08-14T13:20:00+00:00",
        closed_at="2026-08-14T13:25:00+00:00",
        samples=(
            R5IMonitoringSample(
                sampleId="regression-1",
                feedOverride=0.825,
                samplePeriod=0.08,
                actualCycleTimeSeconds=actuals["cycleTimeSeconds"] + 10.0,
                actualLinearFollowingErrorMaxMm=actuals[
                    "linearFollowingErrorMaxMm"
                ]
                + 10.0,
                evidenceContentHash="b" * 64,
            ),
        ),
        maximum_cycle_rmse_seconds=0.01,
        maximum_linear_rmse_mm=0.01,
    )
    regression = assess_r5i_monitoring_window(registry, regression_request)
    assert regression.monitoring_status == "RollbackRequired"
    assert regression.rollback_required is True
    assert regression.model_bundle_hash == dossier.candidate_model_bundle_hash
    assert {item.status for item in regression.target_results} == {"Refuted"}
    assert tuple(
        item.monitoring_status for item in list_r5i_monitoring_windows(registry)
    ) == ("RollbackRequired", "Open", "Healthy")


def test_r5i_explicit_rollback_requires_trigger_and_changes_active_bundle(tmp_path) -> None:
    registry, dossier, _, _ = _activated_registry(tmp_path)
    status = read_r5i_registry_status(registry)
    prediction = predict_r5i_active_model(
        registry,
        feed_override=0.825,
        sample_period=0.08,
    )
    actuals = {item.target_id: item.value for item in prediction.predictions}
    trigger = assess_r5i_monitoring_window(
        registry,
        build_r5i_monitoring_request(
            registry_status=status,
            window_id="axiom.intelligence.r5i.rollback-trigger@1",
            opened_at="2026-08-14T13:20:00+00:00",
            closed_at="2026-08-14T13:25:00+00:00",
            samples=(
                R5IMonitoringSample(
                    sampleId="rollback-trigger-1",
                    feedOverride=0.825,
                    samplePeriod=0.08,
                    actualCycleTimeSeconds=actuals["cycleTimeSeconds"] + 10.0,
                    actualLinearFollowingErrorMaxMm=actuals[
                        "linearFollowingErrorMaxMm"
                    ]
                    + 10.0,
                    evidenceContentHash="c" * 64,
                ),
            ),
            maximum_cycle_rmse_seconds=0.01,
            maximum_linear_rmse_mm=0.01,
        ),
    )
    rollback_request = build_r5i_rollback_request(
        status,
        trigger,
        request_id="axiom.intelligence.r5i.rollback-request@1",
        requested_by="independent-runtime-owner",
        requested_at="2026-08-14T13:30:00+00:00",
        reason="monitored target regression",
        authority_key_id=AUTHORITY_KEY_ID,
        authority_key=AUTHORITY_KEY,
    )

    rollback = apply_r5i_rollback_transaction(
        registry,
        rollback_request,
        authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        event_id="axiom.intelligence.r5i.rollback@1",
        current_platform="Windows",
    )

    assert rollback.event_kind == "Rollback"
    assert rollback.source_model_bundle_hash == dossier.candidate_model_bundle_hash
    assert rollback.target_model_bundle_hash == dossier.baseline_model_bundle_hash
    assert rollback.generation == 2
    assert rollback.readback_model_bundle_hash == dossier.baseline_model_bundle_hash
    assert rollback.rollback_performed is True
    assert rollback.automatic_rollback_allowed is False
    assert rollback.device_write_performed is False
    status_after = read_r5i_registry_status(registry)
    assert status_after.current_model_bundle_hash == dossier.baseline_model_bundle_hash
    assert status_after.generation == 2

    baseline_prediction = predict_r5i_active_model(
        registry,
        feed_override=0.825,
        sample_period=0.08,
    )
    assert baseline_prediction.model_bundle_hash == dossier.baseline_model_bundle_hash

    healthy = assess_r5i_monitoring_window(
        registry,
        build_r5i_monitoring_request(
            registry_status=status_after,
            window_id="axiom.intelligence.r5i.no-rollback-trigger@1",
            opened_at="2026-08-14T14:00:00+00:00",
            closed_at="2026-08-14T14:05:00+00:00",
            samples=(
                R5IMonitoringSample(
                    sampleId="healthy-baseline-1",
                    feedOverride=0.825,
                    samplePeriod=0.08,
                ),
            ),
            maximum_cycle_rmse_seconds=1.0,
            maximum_linear_rmse_mm=1.0,
        ),
    )
    with pytest.raises(ValueError, match="RollbackRequired"):
        build_r5i_rollback_request(
            status_after,
            healthy,
            request_id="axiom.intelligence.r5i.invalid-rollback@1",
            requested_by="independent-runtime-owner",
            requested_at="2026-08-14T14:10:00+00:00",
            reason="no trigger",
            authority_key_id=AUTHORITY_KEY_ID,
            authority_key=AUTHORITY_KEY,
        )


def test_r5i_cli_persists_monitoring_and_performs_only_explicit_rollback(
    tmp_path,
    capsys,
) -> None:
    registry, dossier, _, _ = _activated_registry(tmp_path)
    status = read_r5i_registry_status(registry)
    prediction = predict_r5i_active_model(
        registry,
        feed_override=0.825,
        sample_period=0.08,
    )
    actuals = {item.target_id: item.value for item in prediction.predictions}
    monitoring_request = build_r5i_monitoring_request(
        registry_status=status,
        window_id="axiom.intelligence.r5i.cli-rollback-trigger@1",
        opened_at="2026-08-14T15:00:00+00:00",
        closed_at="2026-08-14T15:05:00+00:00",
        samples=(
            R5IMonitoringSample(
                sampleId="cli-regression-1",
                feedOverride=0.825,
                samplePeriod=0.08,
                actualCycleTimeSeconds=actuals["cycleTimeSeconds"] + 10.0,
                actualLinearFollowingErrorMaxMm=(
                    actuals["linearFollowingErrorMaxMm"] + 10.0
                ),
                evidenceContentHash="d" * 64,
            ),
        ),
        maximum_cycle_rmse_seconds=0.01,
        maximum_linear_rmse_mm=0.01,
    )
    monitoring_path = tmp_path / "monitoring.json"
    monitoring_path.write_text(
        monitoring_request.model_dump_json(indent=2, by_alias=True),
        encoding="utf-8",
    )

    monitoring_exit = main(
        [
            "model-lifecycle",
            "monitor",
            str(monitoring_path),
            "--registry",
            str(registry),
        ]
    )
    monitoring_output = json.loads(capsys.readouterr().out)
    assert monitoring_exit == 1
    assert monitoring_output["monitoringStatus"] == "RollbackRequired"
    assert monitoring_output["automaticRollbackAllowed"] is False

    trigger = list_r5i_monitoring_windows(registry, limit=1)[0]
    rollback_request = build_r5i_rollback_request(
        read_r5i_registry_status(registry),
        trigger,
        request_id="axiom.intelligence.r5i.cli-rollback-request@1",
        requested_by="independent-runtime-owner",
        requested_at="2026-08-14T15:10:00+00:00",
        reason="CLI-observed target regression",
        authority_key_id=AUTHORITY_KEY_ID,
        authority_key=AUTHORITY_KEY,
    )
    rollback_path = tmp_path / "rollback.json"
    key_path = tmp_path / "authority.key"
    rollback_path.write_text(
        rollback_request.model_dump_json(indent=2, by_alias=True),
        encoding="utf-8",
    )
    key_path.write_bytes(AUTHORITY_KEY)

    rollback_exit = main(
        [
            "model-lifecycle",
            "rollback",
            str(rollback_path),
            "--registry",
            str(registry),
            "--authority-key-file",
            str(key_path),
            "--event-id",
            "axiom.intelligence.r5i.cli-rollback@1",
        ]
    )
    rollback_output = json.loads(capsys.readouterr().out)

    assert rollback_exit == 0
    assert rollback_output["eventKind"] == "Rollback"
    assert rollback_output["generation"] == 2
    assert rollback_output["targetModelBundleHash"] == (
        dossier.baseline_model_bundle_hash
    )
    assert rollback_output["deviceWritePerformed"] is False
