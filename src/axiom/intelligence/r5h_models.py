from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    Field,
    JsonValue,
    PlainValidator,
    field_validator,
    model_validator,
)

from ..field_evidence import FieldEvidenceAssessmentReport
from ..five_axis.f3_sampling import M5DiscreteCommand
from ..models import AxiomModel, _require_json_number
from .models import canonical_hash
from .r5g_models import R5GModelPromotionReadinessDossier

HASH_PATTERN = r"^[0-9a-f]{64}$"
VERSIONED_ID_PATTERN = r"^.+@[0-9]+$"
_EPSILON = 1e-12

R5H_CHECK_IDS = (
    "r5h.dossier-lineage@1",
    "r5h.pre-capture-registration@1",
    "r5h.evidence-coverage@1",
    "r5h.exact-command-binding@1",
    "r5h.r41-reality-evidence@1",
    "r5h.cycle-exact-planner@1",
    "r5h.linear-reality-label@1",
    "r5h.candidate-noninferiority@1",
)
R5H_TARGET_IDS = (
    "cycleTimeSeconds",
    "linearFollowingErrorMaxMm",
)
R5H_SAFETY_BANNER = (
    "CANDIDATE REAL HOLDOUT / CASE-SCOPED ONLY / "
    "AWAITING INDEPENDENT HUMAN DECISION / NO MODEL ACTIVATION / "
    "NOT DEVICE SAFE"
)


def _finite(value: Any) -> Any:
    parsed = _require_json_number(value)
    if not math.isfinite(float(parsed)):
        raise ValueError("value must be finite")
    return value


def _linear_actual_from_report(report: FieldEvidenceAssessmentReport) -> float:
    axes = report.reality_assessment.analysis.axes
    linear = tuple(axis for axis in axes if axis.unit_family == "linear-mm")
    if tuple(axis.axis_id for axis in linear) != ("X", "Y", "Z"):
        raise ValueError("R5-H requires ordered X/Y/Z reality axes")
    values = [
        abs(command - observation)
        for axis in linear
        for command, observation in zip(
            axis.command,
            axis.observation,
            strict=True,
        )
    ]
    if not values:
        raise ValueError("R5-H requires non-empty X/Y/Z reality series")
    return max(values)


def _field_evidence_report_input(value: Any) -> FieldEvidenceAssessmentReport:
    return FieldEvidenceAssessmentReport.model_validate(value)


def _readiness_dossier_input(value: Any) -> R5GModelPromotionReadinessDossier:
    return R5GModelPromotionReadinessDossier.model_validate(value)


_ReadinessDossierInput = Annotated[
    Any,
    PlainValidator(
        _readiness_dossier_input,
        json_schema_input_type=dict[str, JsonValue],
    ),
]


_FieldEvidenceAssessmentReportInput = Annotated[
    Any,
    PlainValidator(
        _field_evidence_report_input,
        json_schema_input_type=dict[str, JsonValue],
    ),
]


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


def _validate_case_coverage(
    cases: tuple[R5HCandidateHoldoutCaseSpec, ...],
) -> None:
    if len(cases) < 3:
        raise ValueError("candidate holdout study requires at least three cases")
    case_ids = tuple(case.case_id for case in cases)
    assessment_ids = tuple(case.assessment_id for case in cases)
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("candidate holdout caseId values must be unique")
    if len(set(assessment_ids)) != len(assessment_ids):
        raise ValueError("candidate holdout assessmentId values must be unique")
    in_domain = tuple(case for case in cases if case.role == "in-domain")
    if len(in_domain) < 2:
        raise ValueError("candidate holdout study requires two in-domain cases")
    if len({case.device_id for case in in_domain}) < 2:
        raise ValueError("in-domain cases must span two devices")
    if len({case.condition_id for case in in_domain}) < 2:
        raise ValueError("in-domain cases must span two conditions")
    ood_probes = tuple(case for case in cases if case.role == "ood-probe")
    if not ood_probes:
        raise ValueError("candidate holdout study requires an ood-probe case")
    in_domain_devices = {case.device_id for case in in_domain}
    in_domain_conditions = {case.condition_id for case in in_domain}
    if not any(
        case.device_id not in in_domain_devices
        or case.condition_id not in in_domain_conditions
        for case in ood_probes
    ):
        raise ValueError("ood-probe must use an unseen device or condition context")


class R5HCandidateHoldoutCaseSpec(AxiomModel):
    case_id: str = Field(alias="caseId", pattern=VERSIONED_ID_PATTERN)
    assessment_id: str = Field(alias="assessmentId", pattern=VERSIONED_ID_PATTERN)
    role: Literal["in-domain", "ood-probe"]
    device_id: str = Field(alias="deviceId", min_length=1)
    condition_id: str = Field(alias="conditionId", min_length=1)
    feed_override: float = Field(alias="feedOverride", ge=0.65, le=1.0)
    sample_period: float = Field(alias="samplePeriod", ge=0.04, le=0.08)

    @field_validator("feed_override", "sample_period", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)


class R5HStudyRegistrationCommand(AxiomModel):
    readiness_dossier: _ReadinessDossierInput = Field(
        alias="readinessDossier",
        description="Canonical sealed R5-G readiness dossier JSON artifact.",
    )
    study_id: str = Field(alias="studyId", pattern=VERSIONED_ID_PATTERN)
    created_at: str = Field(alias="createdAt", min_length=1)
    registered_at: str = Field(alias="registeredAt", min_length=1)
    registration_authority_id: str = Field(
        alias="registrationAuthorityId", min_length=1
    )
    registration_record_id: str = Field(alias="registrationRecordId", min_length=1)
    cases: tuple[R5HCandidateHoldoutCaseSpec, ...] = Field(min_length=3)


class R5HExactOperatingPoint(AxiomModel):
    planned_m4_content_hash: str = Field(
        alias="plannedM4ContentHash", pattern=HASH_PATTERN
    )
    planned_m5_content_hash: str = Field(
        alias="plannedM5ContentHash", pattern=HASH_PATTERN
    )
    exact_cycle_time_seconds: float = Field(alias="exactCycleTimeSeconds", gt=0)
    command_sample_count: int = Field(alias="commandSampleCount", ge=2)
    numeric_environment: dict[str, str] = Field(
        alias="numericEnvironment", min_length=1
    )

    @field_validator("exact_cycle_time_seconds", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_environment(self) -> R5HExactOperatingPoint:
        if any(
            not key or not isinstance(value, str) or not value
            for key, value in self.numeric_environment.items()
        ):
            raise ValueError("numericEnvironment must use non-empty string entries")
        return self


class R5HCandidateHoldoutCasePlan(R5HCandidateHoldoutCaseSpec):
    exact_operating_point: R5HExactOperatingPoint = Field(alias="exactOperatingPoint")
    planned_command: M5DiscreteCommand = Field(alias="plannedCommand")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> R5HCandidateHoldoutCasePlan:
        if (
            self.planned_command.content_id
            != self.exact_operating_point.planned_m5_content_hash
        ):
            raise ValueError("plannedCommand must match planned M5 content hash")
        if (
            self.planned_command.source_m4_content_id
            != self.exact_operating_point.planned_m4_content_hash
        ):
            raise ValueError("plannedCommand must match planned M4 content hash")
        if not math.isclose(
            self.planned_command.sample_period,
            self.sample_period,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError("plannedCommand sample period must match case plan")
        if not math.isclose(
            self.planned_command.duration,
            self.exact_operating_point.exact_cycle_time_seconds,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("plannedCommand duration must match exact cycle time")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match candidate holdout case plan")
        return self


class R5HCandidateHoldoutStudyRegistrationRequest(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.candidate-holdout-study-registration-request@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    study_id: str = Field(alias="studyId", pattern=VERSIONED_ID_PATTERN)
    readiness_dossier: R5GModelPromotionReadinessDossier = Field(
        alias="readinessDossier"
    )
    created_at: str = Field(alias="createdAt", min_length=1)
    registered_at: str = Field(alias="registeredAt", min_length=1)
    registration_authority_id: str = Field(
        alias="registrationAuthorityId", min_length=1
    )
    registration_record_id: str = Field(alias="registrationRecordId", min_length=1)
    registration_method: Literal["external-owner-attestation"] = Field(
        default="external-owner-attestation", alias="registrationMethod"
    )
    maximum_candidate_rmse_regression_ratio: Literal[0.0] = Field(
        default=0.0, alias="maximumCandidateRmseRegressionRatio"
    )
    minimum_candidate_interval_coverage: Literal[1.0] = Field(
        default=1.0, alias="minimumCandidateIntervalCoverage"
    )
    cases: tuple[R5HCandidateHoldoutCaseSpec, ...] = Field(min_length=3)
    platform: Literal["windows"] = "windows"
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("created_at", "registered_at")
    @classmethod
    def require_aware_timestamp(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_contract(self) -> R5HCandidateHoldoutStudyRegistrationRequest:
        if datetime.fromisoformat(self.registered_at) < datetime.fromisoformat(
            self.created_at
        ):
            raise ValueError("registeredAt must not precede createdAt")
        if self.readiness_dossier.review_readiness_status != (
            "ReadyForIndependentReview"
        ):
            raise ValueError("readiness dossier must be ready for independent review")
        _validate_case_coverage(self.cases)
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match study registration request")
        return self


class R5HCandidateHoldoutStudyManifest(AxiomModel):
    artifact_type: Literal["axiom.intelligence.candidate-holdout-study-manifest"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["axiom.intelligence.candidate-holdout-study-manifest@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    study_id: str = Field(alias="studyId", pattern=VERSIONED_ID_PATTERN)
    readiness_dossier_content_hash: str = Field(
        alias="readinessDossierContentHash", pattern=HASH_PATTERN
    )
    baseline_model_bundle_hash: str = Field(
        alias="baselineModelBundleHash", pattern=HASH_PATTERN
    )
    candidate_model_bundle_hash: str = Field(
        alias="candidateModelBundleHash", pattern=HASH_PATTERN
    )
    created_at: str = Field(alias="createdAt", min_length=1)
    maximum_candidate_rmse_regression_ratio: Literal[0.0] = Field(
        alias="maximumCandidateRmseRegressionRatio"
    )
    minimum_candidate_interval_coverage: Literal[1.0] = Field(
        alias="minimumCandidateIntervalCoverage"
    )
    minimum_in_domain_cases: Literal[2] = Field(default=2, alias="minimumInDomainCases")
    minimum_devices: Literal[2] = Field(default=2, alias="minimumDevices")
    minimum_conditions: Literal[2] = Field(default=2, alias="minimumConditions")
    ood_probe_required: Literal[True] = Field(default=True, alias="oodProbeRequired")
    cases: tuple[R5HCandidateHoldoutCasePlan, ...] = Field(min_length=3)
    platform: Literal["windows"] = "windows"
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("created_at")
    @classmethod
    def require_aware_timestamp(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="createdAt")

    @model_validator(mode="after")
    def validate_contract(self) -> R5HCandidateHoldoutStudyManifest:
        if self.baseline_model_bundle_hash == self.candidate_model_bundle_hash:
            raise ValueError("baseline and candidate model bundles must differ")
        _validate_case_coverage(self.cases)
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match candidate holdout study manifest")
        return self


class R5HCandidateHoldoutStudyRegistration(AxiomModel):
    artifact_type: Literal[
        "axiom.intelligence.candidate-holdout-study-registration"
    ] = Field(alias="artifactType")
    schema_id: Literal["axiom.intelligence.candidate-holdout-study-registration@1"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    study_id: str = Field(alias="studyId", pattern=VERSIONED_ID_PATTERN)
    manifest_content_hash: str = Field(
        alias="manifestContentHash", pattern=HASH_PATTERN
    )
    registered_at: str = Field(alias="registeredAt", min_length=1)
    registration_authority_id: str = Field(
        alias="registrationAuthorityId", min_length=1
    )
    registration_record_id: str = Field(alias="registrationRecordId", min_length=1)
    registration_method: Literal["external-owner-attestation"] = Field(
        alias="registrationMethod"
    )
    trust_boundary: Literal[
        "external authority attestation; not cryptographically verified by Axiom"
    ] = Field(alias="trustBoundary")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("registered_at")
    @classmethod
    def require_aware_timestamp(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="registeredAt")

    @model_validator(mode="after")
    def verify_identity(self) -> R5HCandidateHoldoutStudyRegistration:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match candidate holdout registration")
        return self


class R5HCandidateHoldoutStudyRegistrationReport(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.candidate-holdout-study-registration-report@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    request_content_hash: str = Field(alias="requestContentHash", pattern=HASH_PATTERN)
    manifest: R5HCandidateHoldoutStudyManifest
    registration: R5HCandidateHoldoutStudyRegistration
    registration_status: Literal["Passed"] = Field(alias="registrationStatus")
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    model_promotion_status: Literal["NotPerformed"] = Field(
        alias="modelPromotionStatus"
    )
    model_registry_write_performed: Literal[False] = Field(
        alias="modelRegistryWritePerformed"
    )
    activation_performed: Literal[False] = Field(alias="activationPerformed")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[R5H_SAFETY_BANNER] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> R5HCandidateHoldoutStudyRegistrationReport:
        if self.registration.study_id != self.manifest.study_id:
            raise ValueError("registration studyId must match manifest")
        if self.registration.manifest_content_hash != self.manifest.content_hash:
            raise ValueError("registration must bind manifest contentHash")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match registration report")
        return self


def _registration_report_input(
    value: Any,
) -> R5HCandidateHoldoutStudyRegistrationReport:
    return R5HCandidateHoldoutStudyRegistrationReport.model_validate(value)


_RegistrationReportInput = Annotated[
    Any,
    PlainValidator(
        _registration_report_input,
        json_schema_input_type=dict[str, JsonValue],
    ),
]


class R5HAssessmentCommand(AxiomModel):
    readiness_dossier: _ReadinessDossierInput = Field(
        alias="readinessDossier",
        description="Canonical sealed R5-G readiness dossier JSON artifact.",
    )
    registration_report: _RegistrationReportInput = Field(
        alias="registrationReport",
        description="Canonical sealed R5-H registration report JSON artifact.",
    )
    evidence_reports: tuple[_FieldEvidenceAssessmentReportInput, ...] = Field(
        default_factory=tuple,
        alias="evidenceReports",
        description="Canonical sealed R7-E/R4.1 field evidence report JSON artifacts.",
    )
    assessment_id: str = Field(
        default="axiom.intelligence.r5h.candidate-holdout-assessment@1",
        alias="assessmentId",
        pattern=VERSIONED_ID_PATTERN,
    )


class R5HCandidateHoldoutAssessmentRequest(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.candidate-real-holdout-assessment-request@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    assessment_id: str = Field(alias="assessmentId", pattern=VERSIONED_ID_PATTERN)
    readiness_dossier: R5GModelPromotionReadinessDossier = Field(
        alias="readinessDossier"
    )
    study_manifest: R5HCandidateHoldoutStudyManifest = Field(alias="studyManifest")
    study_registration: R5HCandidateHoldoutStudyRegistration = Field(
        alias="studyRegistration"
    )
    evidence_reports: tuple[FieldEvidenceAssessmentReport, ...] = Field(
        default_factory=tuple, alias="evidenceReports"
    )
    platform: Literal["windows"] = "windows"
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> R5HCandidateHoldoutAssessmentRequest:
        if (
            self.study_manifest.readiness_dossier_content_hash
            != self.readiness_dossier.content_hash
        ):
            raise ValueError("study manifest must bind readiness dossier")
        if self.study_registration.study_id != self.study_manifest.study_id:
            raise ValueError("study registration must use manifest studyId")
        if (
            self.study_registration.manifest_content_hash
            != self.study_manifest.content_hash
        ):
            raise ValueError("study registration must bind manifest contentHash")
        if (
            self.study_manifest.baseline_model_bundle_hash
            != self.readiness_dossier.baseline_model_bundle_hash
        ):
            raise ValueError("study manifest baseline must match readiness dossier")
        if (
            self.study_manifest.candidate_model_bundle_hash
            != self.readiness_dossier.candidate_model_bundle_hash
        ):
            raise ValueError("study manifest candidate must match readiness dossier")
        if datetime.fromisoformat(
            self.study_registration.registered_at
        ) < datetime.fromisoformat(self.study_manifest.created_at):
            raise ValueError("study registration must not precede manifest creation")
        assessment_ids = tuple(report.assessment_id for report in self.evidence_reports)
        if len(assessment_ids) != len(set(assessment_ids)):
            raise ValueError("evidence assessmentId values must be unique")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError(
                "contentHash must match candidate holdout assessment request"
            )
        return self


class R5HPredictionValue(AxiomModel):
    value: float
    lower: float
    upper: float
    absolute_error: float = Field(alias="absoluteError", ge=0)
    interval_covered: bool = Field(alias="intervalCovered")

    @field_validator("value", "lower", "upper", "absolute_error", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_interval(self) -> R5HPredictionValue:
        if self.lower > self.upper:
            raise ValueError("prediction lower must not exceed upper")
        return self


class R5HCaseTargetResult(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    evidence_source: Literal["exact-planner", "controller-live-read"] = Field(
        alias="evidenceSource"
    )
    counts_toward_reality: bool = Field(alias="countsTowardReality")
    actual: float = Field(ge=0)
    baseline: R5HPredictionValue
    candidate: R5HPredictionValue

    @field_validator("actual", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_semantics(self) -> R5HCaseTargetResult:
        expected = {
            "cycleTimeSeconds": ("s", "exact-planner", False),
            "linearFollowingErrorMaxMm": ("mm", "controller-live-read", True),
        }[self.target_id]
        if (self.unit, self.evidence_source, self.counts_toward_reality) != expected:
            raise ValueError("target result evidence semantics mismatch")
        if self.target_id == "cycleTimeSeconds" and self.actual <= 0:
            raise ValueError("cycle target actual must be positive")
        for label, prediction in (
            ("baseline", self.baseline),
            ("candidate", self.candidate),
        ):
            if not math.isclose(
                prediction.absolute_error,
                abs(prediction.value - self.actual),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(f"{label} absoluteError must be derived from actual")
            expected_coverage = prediction.lower <= self.actual <= prediction.upper
            if prediction.interval_covered != expected_coverage:
                raise ValueError(
                    f"{label} intervalCovered must be derived from interval"
                )
        return self


class R5HCandidateHoldoutCaseResult(AxiomModel):
    case_id: str = Field(alias="caseId", pattern=VERSIONED_ID_PATTERN)
    assessment_id: str = Field(alias="assessmentId", pattern=VERSIONED_ID_PATTERN)
    role: Literal["in-domain", "ood-probe"]
    device_id: str = Field(alias="deviceId", min_length=1)
    condition_id: str = Field(alias="conditionId", min_length=1)
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")
    evidence_report_content_hash: str = Field(
        alias="evidenceReportContentHash", pattern=HASH_PATTERN
    )
    captured_at: str = Field(alias="capturedAt", min_length=1)
    reality_evidence_status: Literal["Passed"] = Field(alias="realityEvidenceStatus")
    targets: tuple[R5HCaseTargetResult, ...] = Field(min_length=2, max_length=2)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("feed_override", "sample_period", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @field_validator("captured_at")
    @classmethod
    def require_aware_timestamp(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="capturedAt")

    @model_validator(mode="after")
    def validate_contract(self) -> R5HCandidateHoldoutCaseResult:
        if tuple(target.target_id for target in self.targets) != R5H_TARGET_IDS:
            raise ValueError("case targets must use cycle then linear error order")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match candidate holdout case result")
        return self


class R5HTargetAssessmentResult(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    evidence_source: Literal["exact-planner", "controller-live-read"] = Field(
        alias="evidenceSource"
    )
    counts_toward_reality: bool = Field(alias="countsTowardReality")
    in_domain_case_count: int = Field(alias="inDomainCaseCount", ge=2)
    baseline_rmse: float = Field(alias="baselineRmse", ge=0)
    candidate_rmse: float = Field(alias="candidateRmse", ge=0)
    candidate_rmse_regression_ratio: float = Field(alias="candidateRmseRegressionRatio")
    candidate_interval_coverage: float = Field(
        alias="candidateIntervalCoverage", ge=0, le=1
    )
    status: Literal["Passed", "Refuted"]

    @field_validator(
        "baseline_rmse",
        "candidate_rmse",
        "candidate_rmse_regression_ratio",
        "candidate_interval_coverage",
        mode="before",
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_semantics(self) -> R5HTargetAssessmentResult:
        expected = {
            "cycleTimeSeconds": ("s", "exact-planner", False),
            "linearFollowingErrorMaxMm": ("mm", "controller-live-read", True),
        }[self.target_id]
        if (self.unit, self.evidence_source, self.counts_toward_reality) != expected:
            raise ValueError("target assessment evidence semantics mismatch")
        expected_ratio = (self.candidate_rmse - self.baseline_rmse) / max(
            self.baseline_rmse,
            _EPSILON,
        )
        if not math.isclose(
            self.candidate_rmse_regression_ratio,
            expected_ratio,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "candidateRmseRegressionRatio must be derived from RMSE values"
            )
        expected_status = (
            "Passed"
            if self.candidate_rmse <= self.baseline_rmse + _EPSILON
            and self.candidate_interval_coverage >= 1.0
            else "Refuted"
        )
        if self.status != expected_status:
            raise ValueError("target status must reflect noninferiority and coverage")
        return self


class R5HCandidateHoldoutCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Refuted", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class R5HCandidateHoldoutAssessment(AxiomModel):
    artifact_type: Literal["axiom.intelligence.candidate-real-holdout-assessment"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["axiom.intelligence.candidate-real-holdout-assessment@1"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    assessment_id: str = Field(alias="assessmentId", pattern=VERSIONED_ID_PATTERN)
    request: R5HCandidateHoldoutAssessmentRequest
    readiness_dossier_content_hash: str = Field(
        alias="readinessDossierContentHash", pattern=HASH_PATTERN
    )
    study_manifest_content_hash: str = Field(
        alias="studyManifestContentHash", pattern=HASH_PATTERN
    )
    study_registration_content_hash: str = Field(
        alias="studyRegistrationContentHash", pattern=HASH_PATTERN
    )
    baseline_model_bundle_hash: str = Field(
        alias="baselineModelBundleHash", pattern=HASH_PATTERN
    )
    candidate_model_bundle_hash: str = Field(
        alias="candidateModelBundleHash", pattern=HASH_PATTERN
    )
    checks: tuple[R5HCandidateHoldoutCheck, ...] = Field(min_length=8, max_length=8)
    case_results: tuple[R5HCandidateHoldoutCaseResult, ...] = Field(alias="caseResults")
    target_results: tuple[R5HTargetAssessmentResult, ...] = Field(
        alias="targetResults", max_length=2
    )
    overall_status: Literal["Passed", "Open", "Refuted", "Blocked"] = Field(
        alias="overallStatus"
    )
    real_world_generalization_status: Literal[
        "CaseScopedPassed", "Open", "Refuted", "Blocked"
    ] = Field(alias="realWorldGeneralizationStatus")
    review_decision_status: Literal["AwaitingIndependentHumanDecision"] = Field(
        alias="reviewDecisionStatus"
    )
    candidate_use_status: Literal["EvaluatedOnly"] = Field(alias="candidateUseStatus")
    model_promotion_status: Literal["NotPerformed"] = Field(
        alias="modelPromotionStatus"
    )
    default_model_changed: Literal[False] = Field(alias="defaultModelChanged")
    model_registry_write_performed: Literal[False] = Field(
        alias="modelRegistryWritePerformed"
    )
    activation_performed: Literal[False] = Field(alias="activationPerformed")
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    safety_banner: Literal[R5H_SAFETY_BANNER] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> R5HCandidateHoldoutAssessment:
        if tuple(check.check_id for check in self.checks) != R5H_CHECK_IDS:
            raise ValueError("assessment checks must use the frozen R5-H order")
        if (
            self.readiness_dossier_content_hash
            != self.request.readiness_dossier.content_hash
        ):
            raise ValueError("assessment readiness dossier hash mismatch")
        if self.study_manifest_content_hash != self.request.study_manifest.content_hash:
            raise ValueError("assessment study manifest hash mismatch")
        if (
            self.study_registration_content_hash
            != self.request.study_registration.content_hash
        ):
            raise ValueError("assessment study registration hash mismatch")
        if (
            self.baseline_model_bundle_hash
            != self.request.study_manifest.baseline_model_bundle_hash
        ):
            raise ValueError("assessment baseline model hash mismatch")
        if (
            self.candidate_model_bundle_hash
            != self.request.study_manifest.candidate_model_bundle_hash
        ):
            raise ValueError("assessment candidate model hash mismatch")
        expected_status: Literal["Passed", "Open", "Refuted", "Blocked"]
        statuses = tuple(check.status for check in self.checks)
        if "Blocked" in statuses:
            expected_status = "Blocked"
        elif "Refuted" in statuses:
            expected_status = "Refuted"
        elif all(status == "Passed" for status in statuses):
            expected_status = "Passed"
        else:
            expected_status = "Open"
        if self.overall_status != expected_status:
            raise ValueError("overallStatus must be derived from R5-H checks")
        expected_reality = {
            "Passed": "CaseScopedPassed",
            "Open": "Open",
            "Refuted": "Refuted",
            "Blocked": "Blocked",
        }[expected_status]
        if self.real_world_generalization_status != expected_reality:
            raise ValueError("realWorldGeneralizationStatus must match overallStatus")
        if (
            self.target_results
            and tuple(target.target_id for target in self.target_results)
            != R5H_TARGET_IDS
        ):
            raise ValueError("target results must use the frozen R5-H target order")
        if self.target_results:
            if len(self.target_results) != len(R5H_TARGET_IDS):
                raise ValueError("complete assessment requires both target results")
            plans = self.request.study_manifest.cases
            reports = self.request.evidence_reports
            if len(self.case_results) != len(plans) or len(reports) != len(plans):
                raise ValueError(
                    "complete assessment requires one case result and report per plan"
                )
            for plan, report, result in zip(
                plans, reports, self.case_results, strict=True
            ):
                if (
                    result.case_id,
                    result.assessment_id,
                    result.role,
                    result.device_id,
                    result.condition_id,
                    result.feed_override,
                    result.sample_period,
                ) != (
                    plan.case_id,
                    plan.assessment_id,
                    plan.role,
                    plan.device_id,
                    plan.condition_id,
                    plan.feed_override,
                    plan.sample_period,
                ):
                    raise ValueError("case result must match frozen case plan")
                if (
                    report.assessment_id != plan.assessment_id
                    or report.case_id != plan.case_id
                    or result.evidence_report_content_hash != report.content_hash
                    or report.overall_status != "Passed"
                    or not report.counts_toward_reality
                ):
                    raise ValueError("case result must bind passed reality evidence")
                expected_cycle = plan.exact_operating_point.exact_cycle_time_seconds
                if not math.isclose(
                    result.targets[0].actual,
                    expected_cycle,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("cycle actual must match exact planner result")
                expected_linear = _linear_actual_from_report(report)
                if not math.isclose(
                    result.targets[1].actual,
                    expected_linear,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("linear actual must match X/Y/Z reality evidence")
            in_domain = tuple(
                result for result in self.case_results if result.role == "in-domain"
            )
            for target_index, target_result in enumerate(self.target_results):
                case_targets = tuple(
                    result.targets[target_index] for result in in_domain
                )
                baseline_rmse = math.sqrt(
                    math.fsum(
                        target.baseline.absolute_error**2 for target in case_targets
                    )
                    / len(case_targets)
                )
                candidate_rmse = math.sqrt(
                    math.fsum(
                        target.candidate.absolute_error**2 for target in case_targets
                    )
                    / len(case_targets)
                )
                coverage = math.fsum(
                    1.0 if target.candidate.interval_covered else 0.0
                    for target in case_targets
                ) / len(case_targets)
                if (
                    target_result.in_domain_case_count != len(in_domain)
                    or not math.isclose(
                        target_result.baseline_rmse,
                        baseline_rmse,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                    or not math.isclose(
                        target_result.candidate_rmse,
                        candidate_rmse,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                    or not math.isclose(
                        target_result.candidate_interval_coverage,
                        coverage,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                ):
                    raise ValueError(
                        "target aggregate must be derived from in-domain case results"
                    )
            expected_target_checks = tuple(
                target.status for target in self.target_results
            )
            if tuple(check.status for check in self.checks[5:7]) != (
                expected_target_checks
            ):
                raise ValueError("target checks must match target result status")
            expected_candidate_check = (
                "Passed"
                if all(status == "Passed" for status in expected_target_checks)
                else "Refuted"
            )
            if self.checks[7].status != expected_candidate_check:
                raise ValueError("candidate check must match both target results")
        else:
            if self.case_results:
                raise ValueError("incomplete assessment must not expose case results")
            if any(check.status != "Open" for check in self.checks[5:8]):
                raise ValueError("incomplete assessment target checks must remain Open")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match candidate holdout assessment")
        return self


class R5HManifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5h-manifest@1"] = Field(
        alias="manifestId"
    )
    schema_id: Literal["axiom.intelligence.r5h-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-H"]
    platform: Literal["windows"]
    review_scope: Literal["candidate-case-scoped-real-holdout"] = Field(
        alias="reviewScope"
    )
    source_dossier_schema_id: Literal[
        "axiom.intelligence.model-promotion-readiness-dossier@1"
    ] = Field(alias="sourceDossierSchemaId")
    required_evidence_schema_id: Literal["axiom.field-evidence-assessment-report@1"] = (
        Field(alias="requiredEvidenceSchemaId")
    )
    bundled_real_evidence_present: Literal[False] = Field(
        alias="bundledRealEvidencePresent"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    model_registry_write_allowed: Literal[False] = Field(
        alias="modelRegistryWriteAllowed"
    )
    activation_allowed: Literal[False] = Field(alias="activationAllowed")
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    check_ids: tuple[str, ...] = Field(alias="checkIds", min_length=8, max_length=8)
    target_ids: tuple[str, ...] = Field(alias="targetIds", min_length=2, max_length=2)
    safety_banner: Literal[R5H_SAFETY_BANNER] = Field(alias="safetyBanner")

    @model_validator(mode="after")
    def validate_contract(self) -> R5HManifest:
        if self.check_ids != R5H_CHECK_IDS:
            raise ValueError("manifest checkIds must use the frozen R5-H order")
        if self.target_ids != R5H_TARGET_IDS:
            raise ValueError("manifest targetIds must use the frozen target order")
        return self


__all__ = [
    "R5H_CHECK_IDS",
    "R5H_SAFETY_BANNER",
    "R5H_TARGET_IDS",
    "R5HAssessmentCommand",
    "R5HCandidateHoldoutAssessment",
    "R5HCandidateHoldoutAssessmentRequest",
    "R5HCandidateHoldoutCasePlan",
    "R5HCandidateHoldoutCaseResult",
    "R5HCandidateHoldoutCaseSpec",
    "R5HCandidateHoldoutCheck",
    "R5HCandidateHoldoutStudyManifest",
    "R5HCandidateHoldoutStudyRegistration",
    "R5HCandidateHoldoutStudyRegistrationReport",
    "R5HCandidateHoldoutStudyRegistrationRequest",
    "R5HCaseTargetResult",
    "R5HExactOperatingPoint",
    "R5HManifest",
    "R5HPredictionValue",
    "R5HStudyRegistrationCommand",
    "R5HTargetAssessmentResult",
]
