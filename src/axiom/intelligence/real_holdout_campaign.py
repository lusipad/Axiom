from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, RunSpec
from .models import HASH_PATTERN, VERSIONED_ID_PATTERN, canonical_hash
from .r5b_models import (
    R5B_DOMAIN_PACK_ID,
    R5B_EVALUATOR_ID,
    R5B_LEAKAGE_DIMENSIONS,
    R5B_RUNNER_ID,
    R5BIntelligenceEvaluationRequest,
    RealHoldoutGovernance,
    RealHoldoutSelectionReceipt,
    RealPairedHoldoutSet,
)
from .real_holdout_intake import (
    RealHoldoutIntakeCase,
    RealHoldoutIntakeReport,
    RealHoldoutIntakeRequest,
    assess_real_holdout_intake,
)

REAL_HOLDOUT_CAMPAIGN_MANIFEST_SCHEMA_ID = (
    "axiom.intelligence.real-holdout-campaign-manifest@1"
)
REAL_HOLDOUT_CAMPAIGN_REGISTRATION_SCHEMA_ID = (
    "axiom.intelligence.real-holdout-campaign-registration@1"
)
REAL_HOLDOUT_CAMPAIGN_REGISTRATION_REQUEST_SCHEMA_ID = (
    "axiom.intelligence.real-holdout-campaign-registration-request@1"
)
REAL_HOLDOUT_CAMPAIGN_REGISTRATION_REPORT_SCHEMA_ID = (
    "axiom.intelligence.real-holdout-campaign-registration-report@1"
)
PREREGISTERED_REAL_HOLDOUT_INTAKE_REQUEST_SCHEMA_ID = (
    "axiom.intelligence.preregistered-real-holdout-intake-request@1"
)
PREREGISTERED_REAL_HOLDOUT_INTAKE_REPORT_SCHEMA_ID = (
    "axiom.intelligence.preregistered-real-holdout-intake-report@1"
)
REAL_HOLDOUT_SELECTION_POLICY_ID = (
    "axiom.intelligence.real-holdout-preregistered-selection@1"
)

_CHECK_IDS = (
    "preregistered-real-holdout-intake.contract",
    "preregistered-real-holdout-intake.registration-timing",
    "preregistered-real-holdout-intake.case-identities",
    "preregistered-real-holdout-intake.output",
)


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


def _finite(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a finite JSON number")
    if not isfinite(value):
        raise ValueError("value must be a finite JSON number")
    return value


def _sealed(model_type: type[AxiomModel], **values: Any) -> Any:
    provisional = model_type.model_construct(content_hash="0" * 64, **values)
    payload = provisional.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude={"content_hash"},
    )
    payload["contentHash"] = canonical_hash(provisional, exclude={"content_hash"})
    return model_type.model_validate(payload)


def _typed_r5b_request(run_spec: RunSpec) -> R5BIntelligenceEvaluationRequest:
    return R5BIntelligenceEvaluationRequest.model_validate(
        run_spec.request.model_dump(mode="json", by_alias=True, exclude_none=True)
    )


def _validate_base_run(run_spec: RunSpec) -> R5BIntelligenceEvaluationRequest:
    if run_spec.domain_pack_id != R5B_DOMAIN_PACK_ID:
        raise ValueError("baseRunSpec must use intelligence.domain-pack@2")
    if run_spec.runner_id != R5B_RUNNER_ID:
        raise ValueError("baseRunSpec must use intelligence-real-holdout-validation@1")
    if run_spec.evaluator_version != R5B_EVALUATOR_ID:
        raise ValueError("baseRunSpec must use intelligence-real-holdout-evaluator@1")
    typed = _typed_r5b_request(run_spec)
    if typed.real_holdout_set is not None:
        raise ValueError("baseRunSpec realHoldoutSet must be absent")
    return typed


class RealHoldoutCampaignCaseSlot(AxiomModel):
    case_id: str = Field(alias="caseId", pattern=VERSIONED_ID_PATTERN)
    assessment_id: str = Field(alias="assessmentId", pattern=VERSIONED_ID_PATTERN)
    calibration_pair_id: str = Field(
        alias="calibrationPairId", pattern=VERSIONED_ID_PATTERN
    )
    validation_pair_id: str = Field(
        alias="validationPairId", pattern=VERSIONED_ID_PATTERN
    )
    role: Literal["in-domain", "ood-probe"]
    topology: Literal["dual-table", "head-table", "dual-head"]
    trajectory_family: str = Field(alias="trajectoryFamily", min_length=1)
    task_id: str = Field(alias="taskId", min_length=1)
    condition_id: str = Field(alias="conditionId", min_length=1)
    batch_id: str = Field(alias="batchId", min_length=1)
    device_id: str = Field(alias="deviceId", min_length=1)
    calibration_command_content_id: str = Field(
        alias="calibrationCommandContentId", pattern=HASH_PATTERN
    )
    validation_command_content_id: str = Field(
        alias="validationCommandContentId", pattern=HASH_PATTERN
    )
    maximum_time_error_seconds: float = Field(alias="maximumTimeErrorSeconds", ge=0.0)

    @field_validator("maximum_time_error_seconds", mode="before")
    @classmethod
    def require_finite_time_error(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def require_distinct_pairs(self) -> RealHoldoutCampaignCaseSlot:
        if self.calibration_pair_id == self.validation_pair_id:
            raise ValueError("calibrationPairId and validationPairId must be distinct")
        return self


def _validate_campaign_slots(
    cases: tuple[RealHoldoutCampaignCaseSlot, ...],
) -> None:
    if len(cases) < 3:
        raise ValueError("campaign requires at least three campaign slots")
    unique_fields = (
        ("caseId", tuple(case.case_id for case in cases)),
        ("assessmentId", tuple(case.assessment_id for case in cases)),
        ("taskId", tuple(case.task_id for case in cases)),
        ("batchId", tuple(case.batch_id for case in cases)),
    )
    for field_name, values in unique_fields:
        if len(values) != len(set(values)):
            raise ValueError(f"campaign {field_name} values must be unique")
    pair_ids = tuple(
        pair_id
        for case in cases
        for pair_id in (case.calibration_pair_id, case.validation_pair_id)
    )
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("campaign pair identities must be unique")
    in_domain = tuple(case for case in cases if case.role == "in-domain")
    if len(in_domain) < 2:
        raise ValueError("campaign requires at least two in-domain slots")
    if not any(case.role == "ood-probe" for case in cases):
        raise ValueError("campaign requires at least one ood-probe slot")
    if len({case.device_id for case in in_domain}) < 2:
        raise ValueError("in-domain campaign slots must span two devices")
    if len({case.condition_id for case in in_domain}) < 2:
        raise ValueError("in-domain campaign slots must span two conditions")


class RealHoldoutCampaignManifest(AxiomModel):
    artifact_type: Literal["axiom.intelligence.real-holdout-campaign-manifest"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["axiom.intelligence.real-holdout-campaign-manifest@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    campaign_id: str = Field(alias="campaignId", pattern=VERSIONED_ID_PATTERN)
    holdout_set_id: str = Field(alias="holdoutSetId", pattern=VERSIONED_ID_PATTERN)
    selection_id: str = Field(alias="selectionId", pattern=VERSIONED_ID_PATTERN)
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    training_dataset_hash: str = Field(
        alias="trainingDatasetHash", pattern=HASH_PATTERN
    )
    selection_policy_id: Literal[
        "axiom.intelligence.real-holdout-preregistered-selection@1"
    ] = Field(alias="selectionPolicyId")
    leakage_dimensions: tuple[
        Literal["device"],
        Literal["condition"],
        Literal["task"],
        Literal["batch"],
        Literal["time"],
    ] = Field(alias="leakageDimensions", min_length=5, max_length=5)
    platform: Literal["windows"]
    cases: tuple[RealHoldoutCampaignCaseSlot, ...] = Field(min_length=3)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> RealHoldoutCampaignManifest:
        if tuple(self.leakage_dimensions) != R5B_LEAKAGE_DIMENSIONS:
            raise ValueError(
                "campaign leakageDimensions must freeze device/condition/task/batch/time"
            )
        _validate_campaign_slots(self.cases)
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match campaign manifest content")
        return self


class RealHoldoutCampaignRegistration(AxiomModel):
    artifact_type: Literal["axiom.intelligence.real-holdout-campaign-registration"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["axiom.intelligence.real-holdout-campaign-registration@1"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    campaign_content_hash: str = Field(
        alias="campaignContentHash", pattern=HASH_PATTERN
    )
    registered_at: str = Field(alias="registeredAt", min_length=1)
    registration_authority_id: str = Field(
        alias="registrationAuthorityId", min_length=1
    )
    registration_record_id: str = Field(alias="registrationRecordId", min_length=1)
    registration_method: Literal["external-owner-attestation"] = Field(
        alias="registrationMethod"
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("registered_at")
    @classmethod
    def require_registered_at(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="registeredAt")

    @model_validator(mode="after")
    def validate_contract(self) -> RealHoldoutCampaignRegistration:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match campaign registration content")
        return self


class RealHoldoutCampaignRegistrationRequest(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.real-holdout-campaign-registration-request@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    campaign_id: str = Field(alias="campaignId", pattern=VERSIONED_ID_PATTERN)
    holdout_set_id: str = Field(alias="holdoutSetId", pattern=VERSIONED_ID_PATTERN)
    selection_id: str = Field(alias="selectionId", pattern=VERSIONED_ID_PATTERN)
    base_run_spec: RunSpec = Field(alias="baseRunSpec")
    cases: tuple[RealHoldoutCampaignCaseSlot, ...] = Field(min_length=3)
    registered_at: str = Field(alias="registeredAt", min_length=1)
    registration_authority_id: str = Field(
        alias="registrationAuthorityId", min_length=1
    )
    registration_record_id: str = Field(alias="registrationRecordId", min_length=1)
    registration_method: Literal["external-owner-attestation"] = Field(
        alias="registrationMethod"
    )

    @field_validator("registered_at")
    @classmethod
    def require_registered_at(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="registeredAt")

    @model_validator(mode="after")
    def validate_contract(self) -> RealHoldoutCampaignRegistrationRequest:
        _validate_base_run(self.base_run_spec)
        _validate_campaign_slots(self.cases)
        return self


class RealHoldoutCampaignRegistrationReport(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.real-holdout-campaign-registration-report@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    manifest: RealHoldoutCampaignManifest
    registration: RealHoldoutCampaignRegistration
    registration_status: Literal["Passed"] = Field(alias="registrationStatus")
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")
    trust_boundary: Literal["external-owner-attestation"] = Field(alias="trustBoundary")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> RealHoldoutCampaignRegistrationReport:
        if self.registration.campaign_content_hash != self.manifest.content_hash:
            raise ValueError("registration must identify campaign manifest")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match campaign registration report")
        return self


class PreregisteredRealHoldoutIntakeRequest(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.preregistered-real-holdout-intake-request@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    intake_id: str = Field(alias="intakeId", pattern=VERSIONED_ID_PATTERN)
    base_run_spec: RunSpec = Field(alias="baseRunSpec")
    governance: RealHoldoutGovernance
    campaign_manifest: RealHoldoutCampaignManifest = Field(alias="campaignManifest")
    campaign_registration: RealHoldoutCampaignRegistration = Field(
        alias="campaignRegistration"
    )
    cases: tuple[RealHoldoutIntakeCase, ...] = ()

    @model_validator(mode="after")
    def validate_contract(self) -> PreregisteredRealHoldoutIntakeRequest:
        base = _validate_base_run(self.base_run_spec)
        manifest = self.campaign_manifest
        if manifest.model_bundle_hash != base.artifact.content_hash:
            raise ValueError("campaign modelBundleHash must identify baseRunSpec")
        if manifest.training_dataset_hash != base.dataset.content_hash:
            raise ValueError("campaign trainingDatasetHash must identify baseRunSpec")
        if self.campaign_registration.campaign_content_hash != manifest.content_hash:
            raise ValueError("campaign registration must identify manifest")
        return self


class PreregisteredRealHoldoutIntakeCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class PreregisteredRealHoldoutIntakeReport(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.preregistered-real-holdout-intake-report@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    intake_id: str = Field(alias="intakeId", pattern=VERSIONED_ID_PATTERN)
    campaign_manifest_content_hash: str = Field(
        alias="campaignManifestContentHash", pattern=HASH_PATTERN
    )
    campaign_registration_content_hash: str = Field(
        alias="campaignRegistrationContentHash", pattern=HASH_PATTERN
    )
    checks: tuple[PreregisteredRealHoldoutIntakeCheck, ...] = Field(
        min_length=4, max_length=4
    )
    delegated_intake_report: RealHoldoutIntakeReport | None = Field(
        default=None, alias="delegatedIntakeReport"
    )
    real_holdout_set: RealPairedHoldoutSet | None = Field(
        default=None, alias="realHoldoutSet"
    )
    r5b_run_spec: RunSpec | None = Field(default=None, alias="r5bRunSpec")
    intake_status: Literal["Passed", "Open", "Blocked"] = Field(alias="intakeStatus")
    counts_toward_reality: bool = Field(alias="countsTowardReality")
    validation_scope: Literal["submitted-cases-only"] = Field(alias="validationScope")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> PreregisteredRealHoldoutIntakeReport:
        if tuple(check.check_id for check in self.checks) != _CHECK_IDS:
            raise ValueError("checks must use the frozen preregistered intake order")
        has_outputs = (
            self.real_holdout_set is not None and self.r5b_run_spec is not None
        )
        if (self.real_holdout_set is None) != (self.r5b_run_spec is None):
            raise ValueError("realHoldoutSet and r5bRunSpec must be present together")
        if (self.intake_status == "Passed") != has_outputs:
            raise ValueError("Passed preregistered intake requires output artifacts")
        if self.counts_toward_reality != (self.intake_status == "Passed"):
            raise ValueError("countsTowardReality must reflect intakeStatus")
        if self.real_holdout_set is not None:
            selection = self.real_holdout_set.selection
            if selection.selection_evidence_status != "PreRegistered":
                raise ValueError("output selection must be PreRegistered")
            if (
                selection.campaign_manifest_content_hash
                != self.campaign_manifest_content_hash
                or selection.campaign_registration_content_hash
                != self.campaign_registration_content_hash
            ):
                raise ValueError("output selection must bind campaign identities")
            typed = _typed_r5b_request(self.r5b_run_spec)
            if typed.real_holdout_set != self.real_holdout_set:
                raise ValueError("r5bRunSpec must embed realHoldoutSet exactly")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match preregistered intake report")
        return self


def _check(
    check_id: str,
    title: str,
    status: Literal["Passed", "Open", "Blocked"],
    reason_code: str | None = None,
    **details: Any,
) -> PreregisteredRealHoldoutIntakeCheck:
    return PreregisteredRealHoldoutIntakeCheck(
        checkId=check_id,
        title=title,
        status=status,
        reasonCode=reason_code,
        details=details,
    )


def register_real_holdout_campaign(
    request: RealHoldoutCampaignRegistrationRequest,
) -> RealHoldoutCampaignRegistrationReport:
    base = _typed_r5b_request(request.base_run_spec)
    manifest = _sealed(
        RealHoldoutCampaignManifest,
        artifact_type="axiom.intelligence.real-holdout-campaign-manifest",
        schema_id=REAL_HOLDOUT_CAMPAIGN_MANIFEST_SCHEMA_ID,
        schema_version=1,
        campaign_id=request.campaign_id,
        holdout_set_id=request.holdout_set_id,
        selection_id=request.selection_id,
        model_bundle_hash=base.artifact.content_hash,
        training_dataset_hash=base.dataset.content_hash,
        selection_policy_id=REAL_HOLDOUT_SELECTION_POLICY_ID,
        leakage_dimensions=R5B_LEAKAGE_DIMENSIONS,
        platform="windows",
        cases=request.cases,
    )
    registration = _sealed(
        RealHoldoutCampaignRegistration,
        artifact_type="axiom.intelligence.real-holdout-campaign-registration",
        schema_id=REAL_HOLDOUT_CAMPAIGN_REGISTRATION_SCHEMA_ID,
        schema_version=1,
        campaign_content_hash=manifest.content_hash,
        registered_at=request.registered_at,
        registration_authority_id=request.registration_authority_id,
        registration_record_id=request.registration_record_id,
        registration_method=request.registration_method,
    )
    return _sealed(
        RealHoldoutCampaignRegistrationReport,
        schema_id=REAL_HOLDOUT_CAMPAIGN_REGISTRATION_REPORT_SCHEMA_ID,
        schema_version=1,
        manifest=manifest,
        registration=registration,
        registration_status="Passed",
        counts_toward_reality=False,
        trust_boundary="external-owner-attestation",
        controlled_trial_status="Open",
        closed_loop_status="Open",
        device_safety_status="NotAssessed",
        process_safety_status="NotAssessed",
    )


def _actual_case_values(case: RealHoldoutIntakeCase) -> dict[str, Any] | None:
    report = case.report
    if report.calibration_pair is None or report.validation_pair is None:
        return None
    calibration = report.calibration_pair.parsed_r7e_request()
    validation = report.validation_pair.parsed_r7e_request()
    if (
        calibration.command is None
        or validation.command is None
        or calibration.controller_profile is None
        or validation.controller_profile is None
        or calibration.shadow_evidence is None
        or validation.shadow_evidence is None
    ):
        return None
    return {
        "caseId": report.case_id,
        "assessmentId": report.assessment_id,
        "calibrationPairId": report.calibration_pair_id,
        "validationPairId": report.validation_pair_id,
        "role": case.role,
        "topology": case.topology,
        "trajectoryFamily": case.trajectory_family,
        "taskId": case.task_id,
        "conditionId": case.condition_id,
        "batchId": case.batch_id,
        "deviceId": case.device_profile.device_id,
        "calibrationControllerDeviceId": calibration.controller_profile.machine_id,
        "validationControllerDeviceId": validation.controller_profile.machine_id,
        "calibrationCommandContentId": calibration.command.content_id,
        "validationCommandContentId": validation.command.content_id,
        "maximumTimeErrorSeconds": case.maximum_time_error_seconds,
        "captureOpenedAt": (
            calibration.shadow_evidence.receipt.opened_at,
            validation.shadow_evidence.receipt.opened_at,
        ),
    }


def _case_match_status(
    manifest: RealHoldoutCampaignManifest,
    cases: tuple[RealHoldoutIntakeCase, ...],
) -> tuple[Literal["Passed", "Open", "Blocked"], str | None, list[str]]:
    if len(cases) != len(manifest.cases):
        return "Blocked", "CampaignCaseCountMismatch", []
    incomplete: list[str] = []
    mismatches: list[str] = []
    for slot, case in zip(manifest.cases, cases, strict=True):
        actual = _actual_case_values(case)
        if actual is None:
            incomplete.append(slot.case_id)
            continue
        expected = slot.model_dump(mode="json", by_alias=True, exclude_none=True)
        for field_name, expected_value in expected.items():
            if actual[field_name] != expected_value:
                mismatches.append(f"{slot.case_id}:{field_name}")
        if actual["calibrationControllerDeviceId"] != slot.device_id:
            mismatches.append(f"{slot.case_id}:calibrationControllerDeviceId")
        if actual["validationControllerDeviceId"] != slot.device_id:
            mismatches.append(f"{slot.case_id}:validationControllerDeviceId")
    if mismatches:
        return "Blocked", "CampaignCaseIdentityMismatch", mismatches
    if incomplete:
        return "Open", "CampaignCaseEvidenceIncomplete", incomplete
    return "Passed", None, []


def _registration_timing_status(
    registration: RealHoldoutCampaignRegistration,
    cases: tuple[RealHoldoutIntakeCase, ...],
) -> tuple[Literal["Passed", "Open", "Blocked"], str | None, list[str]]:
    registered_at = datetime.fromisoformat(registration.registered_at)
    incomplete: list[str] = []
    late: list[str] = []
    for case in cases:
        actual = _actual_case_values(case)
        if actual is None:
            incomplete.append(case.report.case_id)
            continue
        if any(
            registered_at >= datetime.fromisoformat(opened_at)
            for opened_at in actual["captureOpenedAt"]
        ):
            late.append(case.report.case_id)
    if late:
        return "Blocked", "CampaignRegisteredAfterCaptureOpened", late
    if incomplete:
        return "Open", "CampaignCaptureTimingIncomplete", incomplete
    return "Passed", None, []


def _run_spec_with_holdout(base: RunSpec, holdout_set: RealPairedHoldoutSet) -> RunSpec:
    payload = base.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["request"]["realHoldoutSet"] = holdout_set.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    payload["request"] = R5BIntelligenceEvaluationRequest.model_validate(
        payload["request"]
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    return RunSpec.model_validate(payload)


def _report(
    request: PreregisteredRealHoldoutIntakeRequest,
    *,
    checks: tuple[PreregisteredRealHoldoutIntakeCheck, ...],
    status: Literal["Passed", "Open", "Blocked"],
    delegated: RealHoldoutIntakeReport | None = None,
    holdout_set: RealPairedHoldoutSet | None = None,
    run_spec: RunSpec | None = None,
) -> PreregisteredRealHoldoutIntakeReport:
    return _sealed(
        PreregisteredRealHoldoutIntakeReport,
        schema_id=PREREGISTERED_REAL_HOLDOUT_INTAKE_REPORT_SCHEMA_ID,
        schema_version=1,
        intake_id=request.intake_id,
        campaign_manifest_content_hash=request.campaign_manifest.content_hash,
        campaign_registration_content_hash=request.campaign_registration.content_hash,
        checks=checks,
        delegated_intake_report=delegated,
        real_holdout_set=holdout_set,
        r5b_run_spec=run_spec,
        intake_status=status,
        counts_toward_reality=status == "Passed",
        validation_scope="submitted-cases-only",
        controlled_trial_status="Open",
        closed_loop_status="Open",
        device_safety_status="NotAssessed",
        process_safety_status="NotAssessed",
    )


def assess_preregistered_real_holdout_intake(
    request: PreregisteredRealHoldoutIntakeRequest,
) -> PreregisteredRealHoldoutIntakeReport:
    timing_status, timing_reason, timing_cases = _registration_timing_status(
        request.campaign_registration, request.cases
    )
    match_status, match_reason, match_fields = _case_match_status(
        request.campaign_manifest, request.cases
    )
    checks = [
        _check(
            _CHECK_IDS[0],
            "Immutable campaign and base R5-B lineage",
            "Passed",
            campaignManifestContentHash=request.campaign_manifest.content_hash,
            campaignRegistrationContentHash=request.campaign_registration.content_hash,
            registrationTrustBoundary="external-owner-attestation",
        ),
        _check(
            _CHECK_IDS[1],
            "Campaign registered before every capture opening",
            timing_status,
            timing_reason,
            affectedCaseIds=timing_cases,
            registeredAt=request.campaign_registration.registered_at,
        ),
        _check(
            _CHECK_IDS[2],
            "Submitted field cases exactly match planned slots",
            match_status,
            match_reason,
            affectedIdentities=match_fields,
        ),
    ]
    if "Blocked" in {timing_status, match_status}:
        checks.append(
            _check(
                _CHECK_IDS[3],
                "PreRegistered holdout and R5-B RunSpec",
                "Blocked",
                timing_reason or match_reason,
            )
        )
        return _report(request, checks=tuple(checks), status="Blocked")

    legacy_request = RealHoldoutIntakeRequest(
        schemaId="axiom.intelligence.real-holdout-intake-request@1",
        schemaVersion=1,
        intakeId=request.intake_id,
        holdoutSetId=request.campaign_manifest.holdout_set_id,
        selectionId=request.campaign_manifest.selection_id,
        selectedBeforeEvaluation=True,
        baseRunSpec=request.base_run_spec,
        governance=request.governance,
        cases=request.cases,
    )
    delegated = assess_real_holdout_intake(legacy_request)
    if (
        timing_status != "Passed"
        or match_status != "Passed"
        or delegated.intake_status != "Passed"
        or delegated.real_holdout_set is None
    ):
        status: Literal["Open", "Blocked"] = (
            "Blocked" if delegated.intake_status == "Blocked" else "Open"
        )
        checks.append(
            _check(
                _CHECK_IDS[3],
                "PreRegistered holdout and R5-B RunSpec",
                status,
                delegated.intake_status == "Blocked"
                and "DelegatedIntakeBlocked"
                or "PreRegisteredEvidenceIncomplete",
                delegatedIntakeStatus=delegated.intake_status,
            )
        )
        return _report(
            request, checks=tuple(checks), status=status, delegated=delegated
        )

    legacy_set = delegated.real_holdout_set
    selection = _sealed(
        RealHoldoutSelectionReceipt,
        selection_id=legacy_set.selection.selection_id,
        model_bundle_hash=legacy_set.selection.model_bundle_hash,
        training_dataset_hash=legacy_set.selection.training_dataset_hash,
        selected_before_evaluation=True,
        leakage_dimensions=legacy_set.selection.leakage_dimensions,
        case_ids=legacy_set.selection.case_ids,
        selection_evidence_status="PreRegistered",
        campaign_manifest_content_hash=request.campaign_manifest.content_hash,
        campaign_registration_content_hash=request.campaign_registration.content_hash,
    )
    holdout_set = _sealed(
        RealPairedHoldoutSet,
        artifact_type=legacy_set.artifact_type,
        schema_id=legacy_set.schema_id,
        schema_version=legacy_set.schema_version,
        holdout_set_id=legacy_set.holdout_set_id,
        model_bundle_hash=legacy_set.model_bundle_hash,
        training_dataset_hash=legacy_set.training_dataset_hash,
        governance=legacy_set.governance,
        selection=selection,
        cases=legacy_set.cases,
    )
    run_spec = _run_spec_with_holdout(request.base_run_spec, holdout_set)
    checks.append(
        _check(
            _CHECK_IDS[3],
            "PreRegistered holdout and R5-B RunSpec",
            "Passed",
            selectionContentHash=selection.content_hash,
            holdoutSetContentHash=holdout_set.content_hash,
        )
    )
    return _report(
        request,
        checks=tuple(checks),
        status="Passed",
        delegated=delegated,
        holdout_set=holdout_set,
        run_spec=run_spec,
    )


__all__ = [
    "PREREGISTERED_REAL_HOLDOUT_INTAKE_REPORT_SCHEMA_ID",
    "PREREGISTERED_REAL_HOLDOUT_INTAKE_REQUEST_SCHEMA_ID",
    "REAL_HOLDOUT_CAMPAIGN_MANIFEST_SCHEMA_ID",
    "REAL_HOLDOUT_CAMPAIGN_REGISTRATION_REPORT_SCHEMA_ID",
    "REAL_HOLDOUT_CAMPAIGN_REGISTRATION_REQUEST_SCHEMA_ID",
    "REAL_HOLDOUT_CAMPAIGN_REGISTRATION_SCHEMA_ID",
    "REAL_HOLDOUT_SELECTION_POLICY_ID",
    "PreregisteredRealHoldoutIntakeCheck",
    "PreregisteredRealHoldoutIntakeReport",
    "PreregisteredRealHoldoutIntakeRequest",
    "RealHoldoutCampaignCaseSlot",
    "RealHoldoutCampaignManifest",
    "RealHoldoutCampaignRegistration",
    "RealHoldoutCampaignRegistrationReport",
    "RealHoldoutCampaignRegistrationRequest",
    "assess_preregistered_real_holdout_intake",
    "register_real_holdout_campaign",
]
