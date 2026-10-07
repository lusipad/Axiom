from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from axiom.cli import main
from axiom.intelligence.real_holdout_campaign import (
    PreregisteredRealHoldoutIntakeRequest,
    RealHoldoutCampaignCaseSlot,
    RealHoldoutCampaignRegistrationRequest,
    assess_preregistered_real_holdout_intake,
    register_real_holdout_campaign,
)
from axiom.intelligence.r5b_runtime import (
    R5B_HOLDOUT_ISOLATION_METRIC_ID,
    R5B_REAL_WORLD_GENERALIZATION_METRIC_ID,
)
from axiom.run import evaluate_run
from axiom.web import create_app
from tests.test_real_holdout_intake import _complete_cases, _governance


def _slot(case) -> RealHoldoutCampaignCaseSlot:
    assert case.report.calibration_pair is not None
    assert case.report.validation_pair is not None
    calibration = case.report.calibration_pair.parsed_r7e_request()
    validation = case.report.validation_pair.parsed_r7e_request()
    assert calibration.command is not None
    assert validation.command is not None
    return RealHoldoutCampaignCaseSlot(
        caseId=case.report.case_id,
        assessmentId=case.report.assessment_id,
        calibrationPairId=case.report.calibration_pair_id,
        validationPairId=case.report.validation_pair_id,
        role=case.role,
        topology=case.topology,
        trajectoryFamily=case.trajectory_family,
        taskId=case.task_id,
        conditionId=case.condition_id,
        batchId=case.batch_id,
        deviceId=case.device_profile.device_id,
        calibrationCommandContentId=calibration.command.content_id,
        validationCommandContentId=validation.command.content_id,
        maximumTimeErrorSeconds=case.maximum_time_error_seconds,
    )


def _registration_request() -> RealHoldoutCampaignRegistrationRequest:
    cases = _complete_cases()
    return RealHoldoutCampaignRegistrationRequest(
        schemaId="axiom.intelligence.real-holdout-campaign-registration-request@1",
        schemaVersion=1,
        campaignId="field.real-holdout-campaign@1",
        holdoutSetId="field.real-holdout-set@1",
        selectionId="field.real-holdout-selection@1",
        baseRunSpec=__import__(
            "axiom.intelligence", fromlist=["validate_r5b_example_run_spec"]
        ).validate_r5b_example_run_spec(),
        cases=tuple(_slot(case) for case in cases),
        registeredAt="2026-08-14T00:00:00+00:00",
        registrationAuthorityId="field-campaign-owner",
        registrationRecordId="external-registry-record-2026-08-14-001",
        registrationMethod="external-owner-attestation",
    )


def _strict_request() -> PreregisteredRealHoldoutIntakeRequest:
    registration = register_real_holdout_campaign(_registration_request())
    return PreregisteredRealHoldoutIntakeRequest(
        schemaId="axiom.intelligence.preregistered-real-holdout-intake-request@1",
        schemaVersion=1,
        intakeId="field.preregistered-real-holdout-intake@1",
        baseRunSpec=_registration_request().base_run_spec,
        governance=_governance(datetime(2026, 8, 15, tzinfo=timezone.utc)),
        campaignManifest=registration.manifest,
        campaignRegistration=registration.registration,
        cases=_complete_cases(),
    )


def test_campaign_registration_is_deterministic_and_freezes_coverage() -> None:
    request = _registration_request()

    first = register_real_holdout_campaign(request)
    second = register_real_holdout_campaign(request)

    assert first == second
    assert first.registration_status == "Passed"
    assert first.manifest.platform == "windows"
    assert len(first.manifest.cases) == 3
    assert first.registration.campaign_content_hash == first.manifest.content_hash
    assert first.counts_toward_reality is False
    assert first.device_safety_status == "NotAssessed"


def test_campaign_manifest_rejects_incomplete_or_reused_selection_slots() -> None:
    payload = _registration_request().model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    payload["cases"] = payload["cases"][:2]
    with pytest.raises(ValidationError, match="at least 3 items"):
        RealHoldoutCampaignRegistrationRequest.model_validate(payload)

    payload = _registration_request().model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    payload["cases"][2]["taskId"] = payload["cases"][0]["taskId"]
    with pytest.raises(ValidationError, match="taskId"):
        RealHoldoutCampaignRegistrationRequest.model_validate(payload)


def test_preregistered_intake_binds_campaign_and_enables_runtime_gate() -> None:
    first = assess_preregistered_real_holdout_intake(_strict_request())
    second = assess_preregistered_real_holdout_intake(_strict_request())

    assert first == second
    assert first.intake_status == "Passed"
    assert first.real_holdout_set is not None
    assert first.r5b_run_spec is not None
    selection = first.real_holdout_set.selection
    assert selection.selection_evidence_status == "PreRegistered"
    assert selection.campaign_manifest_content_hash == (
        first.campaign_manifest_content_hash
    )
    assert selection.campaign_registration_content_hash == (
        first.campaign_registration_content_hash
    )

    bundle = evaluate_run(first.r5b_run_spec)
    metrics = {item.metric_id: item for item in bundle.report.metric_results}
    assert metrics[R5B_HOLDOUT_ISOLATION_METRIC_ID].status.value == "Computed"
    assert (
        metrics[R5B_REAL_WORLD_GENERALIZATION_METRIC_ID].reason_code
        != "RealHoldoutSelectionNotPreRegistered"
    )


def test_preregistered_intake_blocks_post_capture_registration() -> None:
    request = _strict_request()
    registration_payload = request.campaign_registration.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    registration_payload["registeredAt"] = "2026-08-14T09:00:00+00:00"
    registration_payload["contentHash"] = "0" * 64
    from axiom.intelligence.models import canonical_hash
    from axiom.intelligence.real_holdout_campaign import RealHoldoutCampaignRegistration

    unsealed = RealHoldoutCampaignRegistration.model_construct(
        artifact_type=registration_payload["artifactType"],
        schema_id=registration_payload["schemaId"],
        schema_version=registration_payload["schemaVersion"],
        campaign_content_hash=registration_payload["campaignContentHash"],
        registered_at=registration_payload["registeredAt"],
        registration_authority_id=registration_payload["registrationAuthorityId"],
        registration_record_id=registration_payload["registrationRecordId"],
        registration_method=registration_payload["registrationMethod"],
        content_hash="",
    )
    registration_payload["contentHash"] = canonical_hash(
        unsealed, exclude={"content_hash"}
    )
    registration = RealHoldoutCampaignRegistration.model_validate(registration_payload)

    report = assess_preregistered_real_holdout_intake(
        request.model_copy(update={"campaign_registration": registration})
    )

    assert report.intake_status == "Blocked"
    assert report.real_holdout_set is None
    assert any(
        check.reason_code == "CampaignRegisteredAfterCaptureOpened"
        for check in report.checks
    )


def test_preregistered_intake_blocks_a_substituted_case_identity() -> None:
    request = _strict_request()
    cases = list(request.cases)
    cases[0] = cases[0].model_copy(update={"task_id": "post-hoc-task"})

    report = assess_preregistered_real_holdout_intake(
        request.model_copy(update={"cases": tuple(cases)})
    )

    assert report.intake_status == "Blocked"
    assert any(
        check.reason_code == "CampaignCaseIdentityMismatch" for check in report.checks
    )


def test_campaign_content_tamper_is_rejected_at_parse_boundary() -> None:
    request = _strict_request().model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    request["campaignManifest"]["cases"][0]["deviceId"] = "substituted-device"

    with pytest.raises(ValidationError, match="contentHash"):
        PreregisteredRealHoldoutIntakeRequest.model_validate(deepcopy(request))


def test_campaign_and_strict_intake_cli_http_share_portable_outputs(
    tmp_path,
    capsys,
) -> None:
    campaign_request = _registration_request()
    campaign_expected = register_real_holdout_campaign(campaign_request).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    campaign_path = tmp_path / "campaign.json"
    campaign_path.write_text(
        campaign_request.model_dump_json(indent=2, by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    assert main(["real-holdout-campaign", str(campaign_path)]) == 0
    assert json.loads(capsys.readouterr().out) == campaign_expected
    campaign_response = TestClient(create_app()).post(
        "/api/v1/intelligence/r5b/campaigns/register",
        json=campaign_request.model_dump(mode="json", by_alias=True, exclude_none=True),
    )
    assert campaign_response.status_code == 200
    assert campaign_response.json() == campaign_expected

    intake_request = _strict_request()
    intake_expected = assess_preregistered_real_holdout_intake(
        intake_request
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    intake_path = tmp_path / "preregistered-intake.json"
    intake_path.write_text(
        intake_request.model_dump_json(indent=2, by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    assert main(["real-holdout-intake", str(intake_path)]) == 0
    assert json.loads(capsys.readouterr().out) == intake_expected
    intake_response = TestClient(create_app()).post(
        "/api/v1/intelligence/r5b/intake/assess-preregistered",
        json=intake_request.model_dump(mode="json", by_alias=True, exclude_none=True),
    )
    assert intake_response.status_code == 200
    assert intake_response.json() == intake_expected
