from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .control import R7EAssessmentRequest, R7EExamplePayload, assess_r7e_payload
from .control.models import canonical_hash
from .control.r7e_models import R7EEvaluationRequest
from .models import AxiomModel
from .physical import (
    PhysicalRealityEvidencePair,
    R41AssessmentRequest,
    R41ExamplePayload,
    assess_r41_payload,
    build_reality_evidence_pair,
)

FIELD_EVIDENCE_REQUEST_SCHEMA_ID = "axiom.field-evidence-assessment-request@1"
FIELD_EVIDENCE_REPORT_SCHEMA_ID = "axiom.field-evidence-assessment-report@1"

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_VERSIONED_ID_PATTERN = r"^.+@[0-9]+$"


class FieldEvidenceAssessmentRequest(AxiomModel):
    schema_id: Literal["axiom.field-evidence-assessment-request@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    assessment_id: str = Field(alias="assessmentId", pattern=_VERSIONED_ID_PATTERN)
    calibration_pair_id: str = Field(
        alias="calibrationPairId", pattern=_VERSIONED_ID_PATTERN
    )
    validation_pair_id: str = Field(
        alias="validationPairId", pattern=_VERSIONED_ID_PATTERN
    )
    calibration: R7EAssessmentRequest
    validation: R7EAssessmentRequest
    fit_improvement_minimum: float = Field(
        default=0.2, alias="fitImprovementMinimum", ge=0, le=1
    )
    excitation_span_minimum: float = Field(
        default=1e-6, alias="excitationSpanMinimum", gt=0
    )
    decomposition_tolerance: float = Field(
        default=1e-12, alias="decompositionTolerance", ge=0
    )

    @model_validator(mode="after")
    def require_one_explicit_case(self) -> FieldEvidenceAssessmentRequest:
        if self.calibration_pair_id == self.validation_pair_id:
            raise ValueError("calibrationPairId and validationPairId must be distinct")
        calibration_case = self.calibration.case_id
        validation_case = self.validation.case_id
        if calibration_case is None or validation_case is None:
            raise ValueError("both R7-E assessments require an explicit caseId")
        if calibration_case != validation_case:
            raise ValueError("calibration and validation must use the same caseId")
        return self


class FieldEvidenceAssessmentReport(AxiomModel):
    schema_id: Literal["axiom.field-evidence-assessment-report@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    assessment_id: str = Field(alias="assessmentId", pattern=_VERSIONED_ID_PATTERN)
    case_id: str = Field(alias="caseId", min_length=1)
    calibration_pair_id: str = Field(
        alias="calibrationPairId", pattern=_VERSIONED_ID_PATTERN
    )
    validation_pair_id: str = Field(
        alias="validationPairId", pattern=_VERSIONED_ID_PATTERN
    )
    calibration_assessment: R7EExamplePayload = Field(alias="calibrationAssessment")
    validation_assessment: R7EExamplePayload = Field(alias="validationAssessment")
    calibration_pair: PhysicalRealityEvidencePair | None = Field(
        default=None, alias="calibrationPair"
    )
    validation_pair: PhysicalRealityEvidencePair | None = Field(
        default=None, alias="validationPair"
    )
    reality_assessment: R41ExamplePayload = Field(alias="realityAssessment")
    overall_status: Literal["Passed", "Open", "Blocked", "Refuted"] = Field(
        alias="overallStatus"
    )
    counts_toward_reality: bool = Field(alias="countsTowardReality")
    validation_scope: Literal["single-device-case-scoped"] = Field(
        alias="validationScope"
    )
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(
        alias="processSafetyStatus"
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_report(self) -> FieldEvidenceAssessmentReport:
        calibration_request = _parsed_r7e_request(self.calibration_assessment)
        validation_request = _parsed_r7e_request(self.validation_assessment)
        if (
            calibration_request.case.case_id != self.case_id
            or validation_request.case.case_id != self.case_id
        ):
            raise ValueError("R7-E assessment Case identity mismatch")

        calibration_passed = (
            self.calibration_assessment.readiness_audit.deployment_shadow_status
            == "Passed"
        )
        validation_passed = (
            self.validation_assessment.readiness_audit.deployment_shadow_status
            == "Passed"
        )
        has_calibration_pair = self.calibration_pair is not None
        has_validation_pair = self.validation_pair is not None
        if has_calibration_pair != has_validation_pair:
            raise ValueError("calibrationPair and validationPair must be present together")
        if (calibration_passed and validation_passed) != has_calibration_pair:
            raise ValueError("reality pairs require two Passed R7-E deployment gates")
        if self.calibration_pair_id == self.validation_pair_id:
            raise ValueError("calibrationPairId and validationPairId must be distinct")

        if self.calibration_pair is not None and self.validation_pair is not None:
            if self.calibration_pair.pair_id != self.calibration_pair_id:
                raise ValueError("calibrationPairId mismatch")
            if self.validation_pair.pair_id != self.validation_pair_id:
                raise ValueError("validationPairId mismatch")
            if self.calibration_pair.role != "calibration":
                raise ValueError("calibrationPair must use calibration role")
            if self.validation_pair.role != "validation":
                raise ValueError("validationPair must use validation role")
            if self.calibration_pair.r7e_request != calibration_request.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ):
                raise ValueError("calibrationPair R7-E request mismatch")
            if self.validation_pair.r7e_request != validation_request.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ):
                raise ValueError("validationPair R7-E request mismatch")

        if self.reality_assessment.calibration_pair != self.calibration_pair:
            raise ValueError("realityAssessment calibrationPair mismatch")
        if self.reality_assessment.validation_pair != self.validation_pair:
            raise ValueError("realityAssessment validationPair mismatch")

        expected_status = _overall_status(
            self.calibration_assessment,
            self.validation_assessment,
            self.reality_assessment,
        )
        if self.overall_status != expected_status:
            raise ValueError("overallStatus must reflect R7-E and R4.1 gates")
        if self.counts_toward_reality != (expected_status == "Passed"):
            raise ValueError("countsTowardReality must reflect overallStatus")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match field evidence report")
        return self


def _parsed_r7e_request(payload: R7EExamplePayload) -> R7EEvaluationRequest:
    return R7EEvaluationRequest.model_validate(payload.run_spec["request"])


def _overall_status(
    calibration: R7EExamplePayload,
    validation: R7EExamplePayload,
    reality: R41ExamplePayload,
) -> Literal["Passed", "Open", "Blocked", "Refuted"]:
    audits = (calibration.readiness_audit, validation.readiness_audit)
    if any(audit.readiness_outcome == "Blocked" for audit in audits):
        return "Blocked"
    if any(audit.deployment_shadow_status != "Passed" for audit in audits):
        return "Open"
    return reality.analysis.reality_validation_status


def assess_field_evidence(
    request: FieldEvidenceAssessmentRequest,
) -> FieldEvidenceAssessmentReport:
    calibration_assessment = assess_r7e_payload(request.calibration)
    validation_assessment = assess_r7e_payload(request.validation)

    calibration_pair = None
    validation_pair = None
    if (
        calibration_assessment.readiness_audit.deployment_shadow_status == "Passed"
        and validation_assessment.readiness_audit.deployment_shadow_status == "Passed"
    ):
        calibration_pair = build_reality_evidence_pair(
            pair_id=request.calibration_pair_id,
            role="calibration",
            r7e_request=_parsed_r7e_request(calibration_assessment),
        )
        validation_pair = build_reality_evidence_pair(
            pair_id=request.validation_pair_id,
            role="validation",
            r7e_request=_parsed_r7e_request(validation_assessment),
        )

    reality_assessment = assess_r41_payload(
        R41AssessmentRequest(
            calibrationPair=calibration_pair,
            validationPair=validation_pair,
            fitImprovementMinimum=request.fit_improvement_minimum,
            excitationSpanMinimum=request.excitation_span_minimum,
            decompositionTolerance=request.decomposition_tolerance,
        )
    )
    overall_status = _overall_status(
        calibration_assessment, validation_assessment, reality_assessment
    )
    provisional = FieldEvidenceAssessmentReport.model_construct(
        schema_id=FIELD_EVIDENCE_REPORT_SCHEMA_ID,
        schema_version=1,
        assessment_id=request.assessment_id,
        case_id=request.calibration.case_id,
        calibration_pair_id=request.calibration_pair_id,
        validation_pair_id=request.validation_pair_id,
        calibration_assessment=calibration_assessment,
        validation_assessment=validation_assessment,
        calibration_pair=calibration_pair,
        validation_pair=validation_pair,
        reality_assessment=reality_assessment,
        overall_status=overall_status,
        counts_toward_reality=overall_status == "Passed",
        validation_scope="single-device-case-scoped",
        controlled_trial_status="Open",
        closed_loop_status="Open",
        device_safety_status="NotAssessed",
        process_safety_status="NotAssessed",
        content_hash="0" * 64,
    )
    payload = provisional.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"}
    )
    payload["contentHash"] = canonical_hash(provisional, exclude={"content_hash"})
    return FieldEvidenceAssessmentReport.model_validate(payload)


__all__ = [
    "FIELD_EVIDENCE_REPORT_SCHEMA_ID",
    "FIELD_EVIDENCE_REQUEST_SCHEMA_ID",
    "FieldEvidenceAssessmentReport",
    "FieldEvidenceAssessmentRequest",
    "assess_field_evidence",
]
