from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from axiom.field_evidence import (
    FieldEvidenceAssessmentRequest,
    assess_field_evidence,
)
from axiom.five_axis.f2_kinematics import normalize_numeric_identity
from axiom.five_axis.f3_sampling import M5DiscreteCommand
from axiom.intelligence import (
    R5HCandidateHoldoutAssessment,
    R5HCandidateHoldoutAssessmentRequest,
    R5HCandidateHoldoutCaseSpec,
    R5HCandidateHoldoutStudyManifest,
    R5HCandidateHoldoutStudyRegistration,
    R5HCandidateHoldoutStudyRegistrationReport,
    R5HCandidateHoldoutStudyRegistrationRequest,
    assess_r5f_candidate_downstream_impact,
    assess_r5h_candidate_real_holdout,
    build_r5e_campaign_request,
    build_r5g_promotion_readiness_request,
    build_r5h_assessment_request,
    build_r5h_manifest,
    build_r5h_study_registration_request,
    execute_r5e_synthetic_campaign,
    prepare_r5g_model_promotion_readiness,
    register_r5h_candidate_holdout_study,
)
from axiom.intelligence.models import canonical_hash
from tests.test_field_evidence import _complete_test_r7e_request


def _build_readiness_dossier():
    campaign = execute_r5e_synthetic_campaign(
        build_r5e_campaign_request(accountable_party_id="r5h-fixture-owner"),
        current_platform="Windows",
    )
    impact = assess_r5f_candidate_downstream_impact(
        campaign,
        current_platform="Windows",
    )
    request = build_r5g_promotion_readiness_request(
        impact,
        prepared_by="r5h-readiness-preparer",
    )
    return prepare_r5g_model_promotion_readiness(
        request,
        current_platform="Windows",
    )


@pytest.fixture(scope="module")
def readiness_dossier():
    return _build_readiness_dossier()


def _build_case_specs() -> tuple[R5HCandidateHoldoutCaseSpec, ...]:
    return (
        R5HCandidateHoldoutCaseSpec(
            caseId="field.r5h.case-a@1",
            assessmentId="field.r5h.assessment-a@1",
            role="in-domain",
            deviceId="field-machine-a",
            conditionId="cold-start",
            feedOverride=0.65,
            samplePeriod=0.04,
        ),
        R5HCandidateHoldoutCaseSpec(
            caseId="field.r5h.case-b@1",
            assessmentId="field.r5h.assessment-b@1",
            role="in-domain",
            deviceId="field-machine-b",
            conditionId="warm-steady",
            feedOverride=0.825,
            samplePeriod=0.08,
        ),
        R5HCandidateHoldoutCaseSpec(
            caseId="field.r5h.case-ood@1",
            assessmentId="field.r5h.assessment-ood@1",
            role="ood-probe",
            deviceId="field-machine-c",
            conditionId="unseen-load",
            feedOverride=1.0,
            samplePeriod=0.06,
        ),
    )


@pytest.fixture(scope="module")
def case_specs() -> tuple[R5HCandidateHoldoutCaseSpec, ...]:
    return _build_case_specs()


def _build_registration_request(readiness_dossier, case_specs):
    return build_r5h_study_registration_request(
        readiness_dossier,
        study_id="axiom.intelligence.r5h.field-study@1",
        created_at="2026-08-13T06:00:00+00:00",
        registered_at="2026-08-13T06:30:00+00:00",
        registration_authority_id="field-model-owner",
        registration_record_id="external-r5h-record-001",
        cases=case_specs,
    )


@pytest.fixture(scope="module")
def registration_request(readiness_dossier, case_specs):
    return _build_registration_request(readiness_dossier, case_specs)


@pytest.fixture(scope="module")
def registration_report(registration_request):
    return register_r5h_candidate_holdout_study(
        registration_request,
        current_platform="Windows",
    )


def _calibration_command(
    planned: M5DiscreteCommand,
    *,
    index_shift: int,
) -> M5DiscreteCommand:
    payload = planned.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["discreteCommandId"] = f"r5h.calibration-{index_shift}.command.v1"
    for index, sample in enumerate(payload["samples"]):
        sample["q"] = [
            ((index + index_shift) % 4) * 0.1,
            ((index * 2 + index_shift) % 5) * 0.12,
            ((index * 3 + index_shift) % 6) * 0.08,
            ((index * 2 + 1 + index_shift) % 5) * 0.01,
            ((index * 3 + 2 + index_shift) % 7) * 0.012,
        ]
    identity = deepcopy(payload)
    identity.pop("contentId")
    encoded = json.dumps(
        normalize_numeric_identity(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload["contentId"] = hashlib.sha256(encoded).hexdigest()
    return M5DiscreteCommand.model_validate(payload)


def _build_field_evidence_reports(registration_report):
    reports = []
    start = datetime(2026, 8, 13, 8, tzinfo=timezone.utc)
    for index, plan in enumerate(registration_report.manifest.cases):
        calibration = _complete_test_r7e_request(
            role="calibration",
            start=start + timedelta(hours=index * 2),
            shift=index,
            case_id=plan.case_id,
            machine_id=plan.device_id,
            identity_suffix=f"r5h-{index}",
            override_command=_calibration_command(
                plan.planned_command,
                index_shift=index,
            ),
            axis_biases=(-0.02, -0.05, -0.01, 0.002, -0.003),
        )
        validation = _complete_test_r7e_request(
            role="validation",
            start=start + timedelta(hours=index * 2 + 1),
            shift=index + 1,
            case_id=plan.case_id,
            machine_id=plan.device_id,
            identity_suffix=f"r5h-{index}",
            override_command=plan.planned_command,
            axis_biases=(-0.02, -0.05, -0.01, 0.002, -0.003),
        )
        report = assess_field_evidence(
            FieldEvidenceAssessmentRequest(
                schemaId="axiom.field-evidence-assessment-request@1",
                schemaVersion=1,
                assessmentId=plan.assessment_id,
                calibrationPairId=f"field.r5h.calibration-{index}@1",
                validationPairId=f"field.r5h.validation-{index}@1",
                calibration=calibration,
                validation=validation,
            )
        )
        assert report.overall_status == "Passed", [
            (check.check_id, check.status, check.reason_code, check.details)
            for check in report.reality_assessment.analysis.checks
            if check.status != "Passed"
        ]
        reports.append(report)
    return tuple(reports)


@pytest.fixture(scope="module")
def field_evidence_reports(registration_report):
    return _build_field_evidence_reports(registration_report)


def build_test_only_r5h_chain():
    readiness = _build_readiness_dossier()
    registration = register_r5h_candidate_holdout_study(
        _build_registration_request(readiness, _build_case_specs()),
        current_platform="Windows",
    )
    reports = _build_field_evidence_reports(registration)
    assessment = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            readiness,
            registration,
            evidence_reports=reports,
        ),
        current_platform="Windows",
    )
    return readiness, registration, reports, assessment


def _reseal(payload: dict[str, object]) -> None:
    payload.pop("contentHash", None)
    payload["contentHash"] = canonical_hash(payload)


def _typed_reseal(model_type, payload: dict[str, object]):
    draft = {**payload, "contentHash": "0" * 64}
    provisional = model_type.model_construct(**draft)
    draft["contentHash"] = canonical_hash(
        provisional,
        exclude={"content_hash"},
    )
    return model_type.model_validate(draft)


def test_manifest_and_registration_keep_promotion_open(
    readiness_dossier,
    registration_report,
) -> None:
    manifest = build_r5h_manifest()

    assert manifest.stage == "R5-H"
    assert manifest.platform == "windows"
    assert manifest.bundled_real_evidence_present is False
    assert manifest.real_world_generalization_status == "Open"
    assert manifest.model_registry_write_allowed is False
    assert manifest.activation_allowed is False
    assert manifest.device_write_allowed is False

    assert registration_report.registration_status == "Passed"
    assert registration_report.manifest.readiness_dossier_content_hash == (
        readiness_dossier.content_hash
    )
    assert len(registration_report.manifest.cases) == 3
    assert registration_report.model_promotion_status == "NotPerformed"
    assert registration_report.model_registry_write_performed is False
    assert registration_report.activation_performed is False


def test_empty_external_evidence_stays_open_and_deterministic(
    readiness_dossier,
    registration_report,
) -> None:
    request = build_r5h_assessment_request(
        readiness_dossier,
        registration_report,
        evidence_reports=(),
    )

    first = assess_r5h_candidate_real_holdout(
        request,
        current_platform="Windows",
    )
    second = assess_r5h_candidate_real_holdout(
        request,
        current_platform="Windows",
    )

    assert first == second
    assert first.overall_status == "Open"
    assert first.real_world_generalization_status == "Open"
    assert first.case_results == ()
    assert first.target_results == ()
    assert first.review_decision_status == "AwaitingIndependentHumanDecision"
    assert first.model_promotion_status == "NotPerformed"
    assert first.default_model_changed is False
    assert first.model_registry_write_performed is False
    assert first.activation_performed is False
    assert first.device_write_allowed is False
    assert {check.status for check in first.checks} == {"Passed", "Open"}


def test_test_only_field_evidence_exercises_candidate_specific_gate(
    readiness_dossier,
    registration_report,
    field_evidence_reports,
) -> None:
    assessment = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            readiness_dossier,
            registration_report,
            evidence_reports=field_evidence_reports,
        ),
        current_platform="Windows",
    )

    assert assessment.overall_status == "Passed", assessment.target_results
    assert assessment.real_world_generalization_status == "CaseScopedPassed"
    assert len(assessment.case_results) == 3
    assert len(assessment.target_results) == 2
    assert assessment.target_results[0].evidence_source == "exact-planner"
    assert assessment.target_results[0].counts_toward_reality is False
    assert assessment.target_results[1].evidence_source == "controller-live-read"
    assert assessment.target_results[1].counts_toward_reality is True
    assert assessment.review_decision_status == "AwaitingIndependentHumanDecision"
    assert assessment.model_promotion_status == "NotPerformed"
    assert assessment.model_registry_write_performed is False
    assert assessment.activation_performed is False
    assert assessment.device_write_allowed is False


def test_runtime_reality_label_override_is_rejected_by_artifact_validation(
    readiness_dossier,
    registration_report,
    field_evidence_reports,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "axiom.intelligence.r5h_holdout._linear_actual",
        lambda report: 0.0,
    )
    with pytest.raises(
        ValidationError,
        match="linear actual must match X/Y/Z reality evidence",
    ):
        assess_r5h_candidate_real_holdout(
            build_r5h_assessment_request(
                readiness_dossier,
                registration_report,
                evidence_reports=field_evidence_reports,
            ),
            current_platform="Windows",
        )


def test_reordered_or_late_evidence_is_blocked(
    readiness_dossier,
    registration_report,
    field_evidence_reports,
) -> None:
    reordered = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            readiness_dossier,
            registration_report,
            evidence_reports=tuple(reversed(field_evidence_reports)),
        ),
        current_platform="Windows",
    )
    assert reordered.overall_status == "Blocked"
    assert reordered.checks[2].reason_code == "UnexpectedEvidence"

    raw = deepcopy(registration_report.model_dump(mode="json", by_alias=True))
    raw["registration"]["registeredAt"] = "2026-08-14T00:00:00+00:00"
    late_registration_artifact = _typed_reseal(
        R5HCandidateHoldoutStudyRegistration,
        raw["registration"],
    )
    provisional_report = registration_report.model_copy(
        update={
            "registration": late_registration_artifact,
            "content_hash": "0" * 64,
        }
    )
    late_registration = provisional_report.model_copy(
        update={
            "content_hash": canonical_hash(
                provisional_report,
                exclude={"content_hash"},
            )
        }
    )
    late_registration = R5HCandidateHoldoutStudyRegistrationReport.model_validate(
        late_registration.model_dump(mode="json", by_alias=True)
    )
    late = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            readiness_dossier,
            late_registration,
            evidence_reports=field_evidence_reports,
        ),
        current_platform="Windows",
    )
    assert late.overall_status == "Blocked"
    assert late.checks[1].reason_code == "RegistrationNotBeforeCapture"


def test_registration_requires_coverage_and_pre_registration_order(
    registration_request,
) -> None:
    raw = deepcopy(registration_request.model_dump(mode="json", by_alias=True))
    raw["cases"] = raw["cases"][:2]
    _reseal(raw)
    with pytest.raises(ValidationError, match="at least 3"):
        R5HCandidateHoldoutStudyRegistrationRequest.model_validate(raw)

    raw = deepcopy(registration_request.model_dump(mode="json", by_alias=True))
    raw["registeredAt"] = "2026-08-13T05:00:00+00:00"
    _reseal(raw)
    with pytest.raises(ValidationError, match="registeredAt"):
        R5HCandidateHoldoutStudyRegistrationRequest.model_validate(raw)

    raw = deepcopy(registration_request.model_dump(mode="json", by_alias=True))
    raw["cases"][2]["deviceId"] = raw["cases"][0]["deviceId"]
    raw["cases"][2]["conditionId"] = raw["cases"][0]["conditionId"]
    with pytest.raises(ValidationError, match="unseen device or condition"):
        R5HCandidateHoldoutStudyRegistrationRequest.model_validate(raw)


def test_assessment_request_rejects_manifest_model_rebinding(
    readiness_dossier,
    registration_report,
) -> None:
    manifest = registration_report.manifest
    provisional = manifest.model_copy(
        update={
            "baseline_model_bundle_hash": "f" * 64,
            "content_hash": "0" * 64,
        }
    )
    rebound_manifest = provisional.model_copy(
        update={
            "content_hash": canonical_hash(
                provisional,
                exclude={"content_hash"},
            )
        }
    )
    rebound_manifest = R5HCandidateHoldoutStudyManifest.model_validate(
        rebound_manifest.model_dump(mode="json", by_alias=True)
    )
    registration = registration_report.registration
    provisional_registration = registration.model_copy(
        update={
            "manifest_content_hash": rebound_manifest.content_hash,
            "content_hash": "0" * 64,
        }
    )
    rebound_registration = provisional_registration.model_copy(
        update={
            "content_hash": canonical_hash(
                provisional_registration,
                exclude={"content_hash"},
            )
        }
    )

    with pytest.raises(ValidationError, match="baseline must match"):
        R5HCandidateHoldoutAssessmentRequest(
            schemaId=("axiom.intelligence.candidate-real-holdout-assessment-request@1"),
            schemaVersion=1,
            assessmentId="axiom.intelligence.r5h.rebound@1",
            readinessDossier=readiness_dossier,
            studyManifest=rebound_manifest,
            studyRegistration=rebound_registration,
            evidenceReports=(),
            platform="windows",
            contentHash="0" * 64,
        )


def test_assessment_models_reject_derived_state_tampering(
    readiness_dossier,
    registration_report,
) -> None:
    assessment = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            readiness_dossier,
            registration_report,
            evidence_reports=(),
        ),
        current_platform="Windows",
    )
    raw = assessment.model_dump(mode="json", by_alias=True)
    raw["modelPromotionStatus"] = "Performed"
    _reseal(raw)
    with pytest.raises(ValidationError):
        R5HCandidateHoldoutAssessment.model_validate(raw)


def test_target_result_rejects_derived_status_tampering(
    readiness_dossier,
    registration_report,
    field_evidence_reports,
) -> None:
    assessment = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            readiness_dossier,
            registration_report,
            evidence_reports=field_evidence_reports,
        ),
        current_platform="Windows",
    )
    raw = assessment.model_dump(mode="json", by_alias=True)
    raw["targetResults"][1]["status"] = "Refuted"
    with pytest.raises(
        ValidationError,
        match="target status must reflect",
    ):
        R5HCandidateHoldoutAssessment.model_validate(raw)


def test_assessment_rejects_resealed_case_plan_rebinding(
    readiness_dossier,
    registration_report,
    field_evidence_reports,
) -> None:
    assessment = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            readiness_dossier,
            registration_report,
            evidence_reports=field_evidence_reports,
        ),
        current_platform="Windows",
    )
    raw = assessment.model_dump(mode="json", by_alias=True)
    raw["caseResults"][0]["deviceId"] = "rebound-device"
    _reseal(raw["caseResults"][0])
    _reseal(raw)
    with pytest.raises(ValidationError, match="frozen case plan"):
        R5HCandidateHoldoutAssessment.model_validate(raw)


def test_assessment_rejects_resealed_target_aggregate_tampering(
    readiness_dossier,
    registration_report,
    field_evidence_reports,
) -> None:
    assessment = assess_r5h_candidate_real_holdout(
        build_r5h_assessment_request(
            readiness_dossier,
            registration_report,
            evidence_reports=field_evidence_reports,
        ),
        current_platform="Windows",
    )
    raw = assessment.model_dump(mode="json", by_alias=True)
    target = raw["targetResults"][0]
    target["baselineRmse"] = 2.0
    target["candidateRmse"] = 1.0
    target["candidateRmseRegressionRatio"] = -0.5
    target["candidateIntervalCoverage"] = 1.0
    target["status"] = "Passed"
    _reseal(raw)
    with pytest.raises(ValidationError, match="target aggregate"):
        R5HCandidateHoldoutAssessment.model_validate(raw)


def test_non_windows_fails_before_any_real_evidence_replay(
    registration_request,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "axiom.intelligence.r5h_holdout.evaluate_canonical_parameter_point",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("exact replay must not run")
        ),
    )
    with pytest.raises(ValueError, match="only supports Windows"):
        register_r5h_candidate_holdout_study(
            registration_request,
            current_platform="Linux",
        )


def test_open_assessment_round_trips(
    readiness_dossier,
    registration_report,
) -> None:
    request = build_r5h_assessment_request(
        readiness_dossier,
        registration_report,
        evidence_reports=(),
    )
    assessment = assess_r5h_candidate_real_holdout(
        request,
        current_platform="Windows",
    )

    assert (
        R5HCandidateHoldoutAssessmentRequest.model_validate(
            request.model_dump(mode="json", by_alias=True)
        )
        == request
    )
    assert (
        R5HCandidateHoldoutAssessment.model_validate(
            assessment.model_dump(mode="json", by_alias=True)
        )
        == assessment
    )
