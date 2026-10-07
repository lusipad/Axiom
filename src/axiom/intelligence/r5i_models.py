from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, JsonValue, PlainValidator, field_validator, model_validator

from ..models import AxiomModel, _require_json_number
from .models import HASH_PATTERN, VERSIONED_ID_PATTERN, canonical_hash
from .r5g_models import R5GModelPromotionReadinessDossier
from .r5h_models import R5HCandidateHoldoutAssessment

R5I_SAFETY_BANNER = (
    "LOCAL MODEL LIFECYCLE ONLY / EXPLICIT AUTHORIZED TRANSACTION / "
    "NO AUTOMATIC PROMOTION / NO DEVICE DEPLOYMENT / NOT DEVICE SAFE"
)

R5I_PREFLIGHT_CHECK_IDS = (
    "r5i.runtime-platform@1",
    "r5i.case-scoped-holdout@1",
    "r5i.dossier-readiness-replay@1",
    "r5i.evidence-lineage-binding@1",
    "r5i.independent-reviewer@1",
    "r5i.authorization-proof@1",
    "r5i.post-evidence-decision@1",
)

R5I_MONITORING_CHECK_IDS = (
    "r5i.monitoring-registry-binding@1",
    "r5i.monitoring-bundle-integrity@1",
    "r5i.monitoring-inference-completeness@1",
    "r5i.monitoring-ood-envelope@1",
    "r5i.monitoring-target-performance@1",
)


def _preflight_request_input(value: Any) -> R5IPromotionPreflightRequest:
    return R5IPromotionPreflightRequest.model_validate(value)


_PreflightRequestInput = Annotated[
    Any,
    PlainValidator(
        _preflight_request_input,
        json_schema_input_type=dict[str, JsonValue],
    ),
]


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


class R5IPromotionDecision(AxiomModel):
    schema_id: Literal["axiom.intelligence.promotion-decision@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    decision_id: str = Field(alias="decisionId", pattern=VERSIONED_ID_PATTERN)
    dossier_content_hash: str = Field(
        alias="dossierContentHash", pattern=HASH_PATTERN
    )
    holdout_assessment_content_hash: str = Field(
        alias="holdoutAssessmentContentHash", pattern=HASH_PATTERN
    )
    candidate_model_bundle_hash: str = Field(
        alias="candidateModelBundleHash", pattern=HASH_PATTERN
    )
    rollback_baseline_model_bundle_hash: str = Field(
        alias="rollbackBaselineModelBundleHash", pattern=HASH_PATTERN
    )
    decision: Literal["Approve", "Reject"]
    decided_by: str = Field(alias="decidedBy", min_length=1, max_length=128)
    decided_at: str = Field(alias="decidedAt", min_length=1)
    authority_key_id: str = Field(
        alias="authorityKeyId", min_length=1, max_length=256
    )
    signed_body_hash: str = Field(alias="signedBodyHash", pattern=HASH_PATTERN)
    authorization_proof: str = Field(
        alias="authorizationProof", pattern=HASH_PATTERN
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("decided_by", "authority_key_id")
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value

    @field_validator("decided_at")
    @classmethod
    def require_aware_decision_time(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="decidedAt")

    @model_validator(mode="after")
    def verify_identity(self) -> R5IPromotionDecision:
        expected_body_hash = canonical_hash(
            self,
            exclude={
                "signed_body_hash",
                "authorization_proof",
                "content_hash",
            },
        )
        if self.signed_body_hash != expected_body_hash:
            raise ValueError("signedBodyHash must match promotion decision body")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match promotion decision content")
        return self


class R5IPromotionPreflightRequest(AxiomModel):
    schema_id: Literal["axiom.intelligence.promotion-preflight-request@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    readiness_dossier: R5GModelPromotionReadinessDossier = Field(
        alias="readinessDossier"
    )
    holdout_assessment: R5HCandidateHoldoutAssessment = Field(
        alias="holdoutAssessment"
    )
    promotion_decision: R5IPromotionDecision = Field(alias="promotionDecision")
    platform: Literal["windows"] = "windows"
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> R5IPromotionPreflightRequest:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match promotion preflight request")
        return self


class R5IPreflightCommand(AxiomModel):
    request: _PreflightRequestInput = Field(
        description="Canonical sealed R5-I promotion preflight request JSON artifact."
    )


class R5IActivePredictionCommand(AxiomModel):
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")

    @field_validator("feed_override", "sample_period", mode="before")
    @classmethod
    def require_finite_numbers(cls, value: object) -> object:
        parsed = _require_json_number(value)
        if float(parsed) != float(parsed) or float(parsed) in (
            float("inf"),
            float("-inf"),
        ):
            raise ValueError("prediction coordinates must be finite")
        return value


class R5IPromotionPreflightCheck(AxiomModel):
    check_id: str = Field(alias="checkId", pattern=VERSIONED_ID_PATTERN)
    status: Literal["Passed", "Blocked"]
    evidence_hash: str = Field(alias="evidenceHash", pattern=HASH_PATTERN)
    reason_code: str = Field(alias="reasonCode", min_length=1)


class R5IPromotionPreflightReport(AxiomModel):
    schema_id: Literal["axiom.intelligence.promotion-preflight-report@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    request_content_hash: str = Field(
        alias="requestContentHash", pattern=HASH_PATTERN
    )
    dossier_content_hash: str = Field(
        alias="dossierContentHash", pattern=HASH_PATTERN
    )
    holdout_assessment_content_hash: str = Field(
        alias="holdoutAssessmentContentHash", pattern=HASH_PATTERN
    )
    promotion_decision_content_hash: str = Field(
        alias="promotionDecisionContentHash", pattern=HASH_PATTERN
    )
    candidate_model_bundle_hash: str = Field(
        alias="candidateModelBundleHash", pattern=HASH_PATTERN
    )
    rollback_baseline_model_bundle_hash: str = Field(
        alias="rollbackBaselineModelBundleHash", pattern=HASH_PATTERN
    )
    checks: tuple[
        R5IPromotionPreflightCheck,
        R5IPromotionPreflightCheck,
        R5IPromotionPreflightCheck,
        R5IPromotionPreflightCheck,
        R5IPromotionPreflightCheck,
        R5IPromotionPreflightCheck,
        R5IPromotionPreflightCheck,
    ]
    overall_status: Literal["Passed", "Blocked", "Rejected"] = Field(
        alias="overallStatus"
    )
    promotion_transaction_status: Literal["Eligible", "Blocked", "Rejected"] = (
        Field(alias="promotionTransactionStatus")
    )
    review_decision_status: Literal["Approved", "Rejected", "Invalid"] = Field(
        alias="reviewDecisionStatus"
    )
    authorization_verified: bool = Field(alias="authorizationVerified")
    registry_transaction_allowed: bool = Field(alias="registryTransactionAllowed")
    real_world_generalization_status: Literal[
        "CaseScopedPassed", "Open", "Refuted", "Blocked"
    ] = Field(alias="realWorldGeneralizationStatus")
    model_promotion_status: Literal["NotPerformed"] = Field(
        alias="modelPromotionStatus"
    )
    model_registry_write_performed: Literal[False] = Field(
        alias="modelRegistryWritePerformed"
    )
    activation_performed: Literal[False] = Field(alias="activationPerformed")
    default_model_changed: Literal[False] = Field(alias="defaultModelChanged")
    automatic_model_promotion_allowed: Literal[False] = Field(
        alias="automaticModelPromotionAllowed"
    )
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    safety_banner: Literal[R5I_SAFETY_BANNER] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> R5IPromotionPreflightReport:
        if tuple(check.check_id for check in self.checks) != R5I_PREFLIGHT_CHECK_IDS:
            raise ValueError("preflight checks must use the frozen R5-I order")
        request = self.request_content_hash
        if not request:
            raise ValueError("requestContentHash is required")
        all_passed = all(check.status == "Passed" for check in self.checks)
        decision = self.review_decision_status
        expected_overall = (
            "Blocked"
            if not all_passed
            else "Rejected"
            if decision == "Rejected"
            else "Passed"
        )
        if self.overall_status != expected_overall:
            raise ValueError("overallStatus must derive from checks and decision")
        expected_transaction = {
            "Passed": "Eligible",
            "Blocked": "Blocked",
            "Rejected": "Rejected",
        }[expected_overall]
        if self.promotion_transaction_status != expected_transaction:
            raise ValueError("promotionTransactionStatus must match overallStatus")
        if self.registry_transaction_allowed != (expected_overall == "Passed"):
            raise ValueError("registryTransactionAllowed must require Passed preflight")
        if self.authorization_verified != (self.checks[5].status == "Passed"):
            raise ValueError("authorizationVerified must match authorization check")
        expected_review = (
            "Invalid"
            if not all_passed
            else "Approved"
            if expected_overall == "Passed"
            else "Rejected"
        )
        if self.review_decision_status != expected_review:
            raise ValueError("reviewDecisionStatus must derive from validated decision")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match promotion preflight report")
        return self


class R5IManifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5i-manifest@1"] = Field(
        alias="manifestId"
    )
    schema_id: Literal["axiom.intelligence.r5i-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-I"]
    platform: Literal["windows"]
    lifecycle_scope: Literal["local-conditional-effect-model"] = Field(
        alias="lifecycleScope"
    )
    registry_kind: Literal["sqlite-local"] = Field(alias="registryKind")
    source_dossier_schema_id: Literal[
        "axiom.intelligence.model-promotion-readiness-dossier@1"
    ] = Field(alias="sourceDossierSchemaId")
    source_holdout_schema_id: Literal[
        "axiom.intelligence.candidate-real-holdout-assessment@1"
    ] = Field(alias="sourceHoldoutSchemaId")
    promotion_decision_schema_id: Literal[
        "axiom.intelligence.promotion-decision@1"
    ] = Field(alias="promotionDecisionSchemaId")
    check_ids: tuple[str, ...] = Field(alias="checkIds", min_length=7, max_length=7)
    web_state_mutation_allowed: Literal[False] = Field(
        alias="webStateMutationAllowed"
    )
    local_cli_transaction_required: Literal[True] = Field(
        alias="localCliTransactionRequired"
    )
    automatic_model_promotion_allowed: Literal[False] = Field(
        alias="automaticModelPromotionAllowed"
    )
    automatic_rollback_allowed: Literal[False] = Field(
        alias="automaticRollbackAllowed"
    )
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[R5I_SAFETY_BANNER] = Field(alias="safetyBanner")

    @model_validator(mode="after")
    def validate_contract(self) -> R5IManifest:
        if self.check_ids != R5I_PREFLIGHT_CHECK_IDS:
            raise ValueError("manifest checkIds must use the frozen R5-I order")
        return self


class R5IActivationReceipt(AxiomModel):
    schema_id: Literal["axiom.intelligence.model-activation-receipt@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    event_id: str = Field(alias="eventId", pattern=VERSIONED_ID_PATTERN)
    event_kind: Literal["Promotion"] = Field(alias="eventKind")
    preflight_report_content_hash: str = Field(
        alias="preflightReportContentHash", pattern=HASH_PATTERN
    )
    promotion_decision_content_hash: str = Field(
        alias="promotionDecisionContentHash", pattern=HASH_PATTERN
    )
    source_model_bundle_hash: str = Field(
        alias="sourceModelBundleHash", pattern=HASH_PATTERN
    )
    target_model_bundle_hash: str = Field(
        alias="targetModelBundleHash", pattern=HASH_PATTERN
    )
    rollback_baseline_model_bundle_hash: str = Field(
        alias="rollbackBaselineModelBundleHash", pattern=HASH_PATTERN
    )
    activated_at: str = Field(alias="activatedAt", min_length=1)
    generation: int = Field(ge=1)
    readback_model_bundle_hash: str = Field(
        alias="readbackModelBundleHash", pattern=HASH_PATTERN
    )
    readback_generation: int = Field(alias="readbackGeneration", ge=1)
    transaction_status: Literal["Applied"] = Field(alias="transactionStatus")
    model_promotion_status: Literal["Performed"] = Field(
        alias="modelPromotionStatus"
    )
    model_registry_write_performed: Literal[True] = Field(
        alias="modelRegistryWritePerformed"
    )
    activation_performed: Literal[True] = Field(alias="activationPerformed")
    default_model_changed: Literal[True] = Field(alias="defaultModelChanged")
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_performed: Literal[False] = Field(alias="deviceWritePerformed")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    safety_banner: Literal[R5I_SAFETY_BANNER] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("activated_at")
    @classmethod
    def require_aware_activation_time(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="activatedAt")

    @model_validator(mode="after")
    def validate_contract(self) -> R5IActivationReceipt:
        if self.source_model_bundle_hash == self.target_model_bundle_hash:
            raise ValueError("promotion must change the local default model")
        if self.source_model_bundle_hash != self.rollback_baseline_model_bundle_hash:
            raise ValueError("promotion source must be the frozen rollback baseline")
        if (
            self.readback_model_bundle_hash != self.target_model_bundle_hash
            or self.readback_generation != self.generation
        ):
            raise ValueError("activation readback must match committed target state")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match activation receipt")
        return self


class R5IRollbackReceipt(AxiomModel):
    schema_id: Literal["axiom.intelligence.model-rollback-receipt@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    event_id: str = Field(alias="eventId", pattern=VERSIONED_ID_PATTERN)
    event_kind: Literal["Rollback"] = Field(alias="eventKind")
    rollback_request_content_hash: str = Field(
        alias="rollbackRequestContentHash", pattern=HASH_PATTERN
    )
    monitoring_report_content_hash: str = Field(
        alias="monitoringReportContentHash", pattern=HASH_PATTERN
    )
    source_model_bundle_hash: str = Field(
        alias="sourceModelBundleHash", pattern=HASH_PATTERN
    )
    target_model_bundle_hash: str = Field(
        alias="targetModelBundleHash", pattern=HASH_PATTERN
    )
    rollback_baseline_model_bundle_hash: str = Field(
        alias="rollbackBaselineModelBundleHash", pattern=HASH_PATTERN
    )
    requested_by: str = Field(alias="requestedBy", min_length=1, max_length=128)
    rolled_back_at: str = Field(alias="rolledBackAt", min_length=1)
    generation: int = Field(ge=2)
    readback_model_bundle_hash: str = Field(
        alias="readbackModelBundleHash", pattern=HASH_PATTERN
    )
    readback_generation: int = Field(alias="readbackGeneration", ge=2)
    transaction_status: Literal["Applied"] = Field(alias="transactionStatus")
    model_promotion_status: Literal["Reverted"] = Field(
        alias="modelPromotionStatus"
    )
    model_registry_write_performed: Literal[True] = Field(
        alias="modelRegistryWritePerformed"
    )
    rollback_performed: Literal[True] = Field(alias="rollbackPerformed")
    default_model_changed: Literal[True] = Field(alias="defaultModelChanged")
    automatic_rollback_allowed: Literal[False] = Field(
        alias="automaticRollbackAllowed"
    )
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_performed: Literal[False] = Field(alias="deviceWritePerformed")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    safety_banner: Literal[R5I_SAFETY_BANNER] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("requested_by")
    @classmethod
    def reject_blank_requester(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("requestedBy must not be blank")
        return value

    @field_validator("rolled_back_at")
    @classmethod
    def require_aware_rollback_time(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="rolledBackAt")

    @model_validator(mode="after")
    def validate_contract(self) -> R5IRollbackReceipt:
        if self.source_model_bundle_hash == self.target_model_bundle_hash:
            raise ValueError("rollback must change the local default model")
        if self.target_model_bundle_hash != self.rollback_baseline_model_bundle_hash:
            raise ValueError("rollback target must be the frozen baseline")
        if (
            self.readback_model_bundle_hash != self.target_model_bundle_hash
            or self.readback_generation != self.generation
        ):
            raise ValueError("rollback readback must match committed baseline state")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match rollback receipt")
        return self


class R5IMonitoringSample(AxiomModel):
    sample_id: str = Field(alias="sampleId", min_length=1, max_length=256)
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")
    actual_cycle_time_seconds: float | None = Field(
        default=None, alias="actualCycleTimeSeconds"
    )
    actual_linear_following_error_max_mm: float | None = Field(
        default=None, alias="actualLinearFollowingErrorMaxMm"
    )
    evidence_content_hash: str | None = Field(
        default=None, alias="evidenceContentHash", pattern=HASH_PATTERN
    )

    @field_validator(
        "feed_override",
        "sample_period",
        "actual_cycle_time_seconds",
        "actual_linear_following_error_max_mm",
        mode="before",
    )
    @classmethod
    def require_finite_numbers(cls, value: object) -> object:
        if value is None:
            return value
        parsed = _require_json_number(value)
        if float(parsed) != float(parsed) or float(parsed) in (
            float("inf"),
            float("-inf"),
        ):
            raise ValueError("monitoring values must be finite")
        return value

    @model_validator(mode="after")
    def validate_labels(self) -> R5IMonitoringSample:
        has_cycle = self.actual_cycle_time_seconds is not None
        has_linear = self.actual_linear_following_error_max_mm is not None
        if has_cycle != has_linear:
            raise ValueError("monitoring labels must contain both frozen targets")
        if has_cycle != (self.evidence_content_hash is not None):
            raise ValueError("labeled monitoring sample requires evidenceContentHash")
        if has_cycle and (
            self.actual_cycle_time_seconds < 0
            or self.actual_linear_following_error_max_mm < 0
        ):
            raise ValueError("monitoring actual values must be non-negative")
        return self


class R5IMonitoringWindowRequest(AxiomModel):
    schema_id: Literal["axiom.intelligence.model-monitoring-window-request@1"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    window_id: str = Field(alias="windowId", pattern=VERSIONED_ID_PATTERN)
    registry_identity: str = Field(alias="registryIdentity", pattern=HASH_PATTERN)
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    generation: int = Field(ge=1)
    opened_at: str = Field(alias="openedAt", min_length=1)
    closed_at: str = Field(alias="closedAt", min_length=1)
    samples: tuple[R5IMonitoringSample, ...] = Field(min_length=1, max_length=10_000)
    maximum_ood_fraction: float = Field(
        alias="maximumOodFraction", ge=0.0, le=1.0
    )
    minimum_interval_coverage: float = Field(
        alias="minimumIntervalCoverage", ge=0.0, le=1.0
    )
    maximum_cycle_rmse_seconds: float = Field(
        alias="maximumCycleRmseSeconds", ge=0.0
    )
    maximum_linear_rmse_mm: float = Field(
        alias="maximumLinearRmseMm", ge=0.0
    )
    monitoring_scope: Literal["local-model-behavior"] = Field(
        alias="monitoringScope"
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("opened_at", "closed_at")
    @classmethod
    def require_aware_times(cls, value: str, info: object) -> str:
        return _aware_timestamp(value, field_name=getattr(info, "field_name"))

    @field_validator(
        "maximum_ood_fraction",
        "minimum_interval_coverage",
        "maximum_cycle_rmse_seconds",
        "maximum_linear_rmse_mm",
        mode="before",
    )
    @classmethod
    def require_finite_thresholds(cls, value: object) -> object:
        parsed = _require_json_number(value)
        if float(parsed) != float(parsed) or float(parsed) in (
            float("inf"),
            float("-inf"),
        ):
            raise ValueError("monitoring thresholds must be finite")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> R5IMonitoringWindowRequest:
        if datetime.fromisoformat(self.closed_at) < datetime.fromisoformat(
            self.opened_at
        ):
            raise ValueError("closedAt must not precede openedAt")
        sample_ids = tuple(sample.sample_id for sample in self.samples)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("monitoring sampleId values must be unique")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match monitoring window request")
        return self


class R5IMonitoringTargetSampleResult(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    predicted: float
    interval_lower: float = Field(alias="intervalLower")
    interval_upper: float = Field(alias="intervalUpper")
    actual: float | None = None
    absolute_error: float | None = Field(default=None, alias="absoluteError")
    interval_covered: bool | None = Field(default=None, alias="intervalCovered")


class R5IMonitoringSampleResult(AxiomModel):
    sample_id: str = Field(alias="sampleId", min_length=1)
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")
    prediction_status: Literal["Predicted", "Abstained", "Failed"] = Field(
        alias="predictionStatus"
    )
    reason_code: str | None = Field(default=None, alias="reasonCode")
    targets: tuple[R5IMonitoringTargetSampleResult, ...] = Field(max_length=2)
    evidence_content_hash: str | None = Field(
        default=None, alias="evidenceContentHash", pattern=HASH_PATTERN
    )


class R5IMonitoringTargetResult(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    labeled_sample_count: int = Field(alias="labeledSampleCount", ge=0)
    rmse: float | None = Field(default=None, ge=0.0)
    interval_coverage: float | None = Field(
        default=None, alias="intervalCoverage", ge=0.0, le=1.0
    )
    status: Literal["Passed", "Open", "Refuted"]
    reason_code: str = Field(alias="reasonCode", min_length=1)


class R5IMonitoringCheck(AxiomModel):
    check_id: str = Field(alias="checkId", pattern=VERSIONED_ID_PATTERN)
    status: Literal["Passed", "Open", "Refuted"]
    reason_code: str = Field(alias="reasonCode", min_length=1)
    evidence_hash: str = Field(alias="evidenceHash", pattern=HASH_PATTERN)


class R5IMonitoringWindowReport(AxiomModel):
    schema_id: Literal["axiom.intelligence.model-monitoring-window-report@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    request: R5IMonitoringWindowRequest
    registry_identity: str = Field(alias="registryIdentity", pattern=HASH_PATTERN)
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    generation: int = Field(ge=1)
    sample_results: tuple[R5IMonitoringSampleResult, ...] = Field(
        alias="sampleResults"
    )
    target_results: tuple[
        R5IMonitoringTargetResult,
        R5IMonitoringTargetResult,
    ] = Field(alias="targetResults")
    checks: tuple[
        R5IMonitoringCheck,
        R5IMonitoringCheck,
        R5IMonitoringCheck,
        R5IMonitoringCheck,
        R5IMonitoringCheck,
    ]
    monitoring_status: Literal["Healthy", "Open", "RollbackRequired"] = Field(
        alias="monitoringStatus"
    )
    rollback_required: bool = Field(alias="rollbackRequired")
    automatic_rollback_allowed: Literal[False] = Field(
        alias="automaticRollbackAllowed"
    )
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    safety_banner: Literal[R5I_SAFETY_BANNER] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> R5IMonitoringWindowReport:
        if (
            self.registry_identity != self.request.registry_identity
            or self.model_bundle_hash != self.request.model_bundle_hash
            or self.generation != self.request.generation
        ):
            raise ValueError("monitoring report must bind its request state")
        if tuple(item.target_id for item in self.target_results) != (
            "cycleTimeSeconds",
            "linearFollowingErrorMaxMm",
        ):
            raise ValueError("monitoring targets must use the frozen order")
        if tuple(check.check_id for check in self.checks) != (
            R5I_MONITORING_CHECK_IDS
        ):
            raise ValueError("monitoring checks must use the frozen R5-I order")
        has_refuted = any(check.status == "Refuted" for check in self.checks)
        has_open = any(check.status == "Open" for check in self.checks)
        expected = (
            "RollbackRequired"
            if has_refuted
            else "Open"
            if has_open
            else "Healthy"
        )
        if self.monitoring_status != expected:
            raise ValueError("monitoringStatus must derive from checks")
        if self.rollback_required != (expected == "RollbackRequired"):
            raise ValueError("rollbackRequired must reflect monitoringStatus")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match monitoring window report")
        return self


class R5IRollbackRequest(AxiomModel):
    schema_id: Literal["axiom.intelligence.model-rollback-request@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    request_id: str = Field(alias="requestId", pattern=VERSIONED_ID_PATTERN)
    registry_identity: str = Field(alias="registryIdentity", pattern=HASH_PATTERN)
    monitoring_report_content_hash: str = Field(
        alias="monitoringReportContentHash", pattern=HASH_PATTERN
    )
    expected_current_model_bundle_hash: str = Field(
        alias="expectedCurrentModelBundleHash", pattern=HASH_PATTERN
    )
    rollback_baseline_model_bundle_hash: str = Field(
        alias="rollbackBaselineModelBundleHash", pattern=HASH_PATTERN
    )
    expected_generation: int = Field(alias="expectedGeneration", ge=1)
    requested_by: str = Field(alias="requestedBy", min_length=1, max_length=128)
    requested_at: str = Field(alias="requestedAt", min_length=1)
    reason: str = Field(min_length=1, max_length=1000)
    authority_key_id: str = Field(
        alias="authorityKeyId", min_length=1, max_length=256
    )
    signed_body_hash: str = Field(alias="signedBodyHash", pattern=HASH_PATTERN)
    authorization_proof: str = Field(
        alias="authorizationProof", pattern=HASH_PATTERN
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("requested_by", "reason", "authority_key_id")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rollback text fields must not be blank")
        return value

    @field_validator("requested_at")
    @classmethod
    def require_aware_requested_time(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="requestedAt")

    @model_validator(mode="after")
    def validate_contract(self) -> R5IRollbackRequest:
        expected_body_hash = canonical_hash(
            self,
            exclude={
                "signed_body_hash",
                "authorization_proof",
                "content_hash",
            },
        )
        if self.signed_body_hash != expected_body_hash:
            raise ValueError("signedBodyHash must match rollback request body")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match rollback request")
        return self


class R5IRegistryStatus(AxiomModel):
    schema_id: Literal["axiom.intelligence.model-registry-status@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    registry_identity: str = Field(alias="registryIdentity", pattern=HASH_PATTERN)
    registry_initialized: bool = Field(alias="registryInitialized")
    current_model_bundle_hash: str | None = Field(
        default=None, alias="currentModelBundleHash", pattern=HASH_PATTERN
    )
    rollback_baseline_model_bundle_hash: str | None = Field(
        default=None,
        alias="rollbackBaselineModelBundleHash",
        pattern=HASH_PATTERN,
    )
    generation: int = Field(ge=0)
    latest_event: R5IActivationReceipt | R5IRollbackReceipt | None = Field(
        default=None, alias="latestEvent"
    )
    model_registry_write_performed: bool = Field(
        alias="modelRegistryWritePerformed"
    )
    activation_performed: bool = Field(alias="activationPerformed")
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    safety_banner: Literal[R5I_SAFETY_BANNER] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> R5IRegistryStatus:
        active = self.current_model_bundle_hash is not None
        if active != (self.generation > 0):
            raise ValueError("registry generation must reflect active model state")
        if active != (self.rollback_baseline_model_bundle_hash is not None):
            raise ValueError("active registry requires a rollback baseline")
        if active != (self.latest_event is not None):
            raise ValueError("active registry requires a latest activation event")
        if self.latest_event is not None and (
            self.latest_event.readback_model_bundle_hash
            != self.current_model_bundle_hash
            or self.latest_event.readback_generation != self.generation
        ):
            raise ValueError("latest event must match registry readback state")
        if self.model_registry_write_performed != active:
            raise ValueError("registry write status must reflect active state")
        if self.activation_performed != active:
            raise ValueError("activation status must reflect active state")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match registry status")
        return self


__all__ = [
    "R5I_MONITORING_CHECK_IDS",
    "R5I_PREFLIGHT_CHECK_IDS",
    "R5I_SAFETY_BANNER",
    "R5IManifest",
    "R5IActivePredictionCommand",
    "R5IActivationReceipt",
    "R5IMonitoringCheck",
    "R5IMonitoringSample",
    "R5IMonitoringSampleResult",
    "R5IMonitoringTargetResult",
    "R5IMonitoringTargetSampleResult",
    "R5IMonitoringWindowReport",
    "R5IMonitoringWindowRequest",
    "R5IPromotionDecision",
    "R5IPreflightCommand",
    "R5IPromotionPreflightCheck",
    "R5IPromotionPreflightReport",
    "R5IPromotionPreflightRequest",
    "R5IRegistryStatus",
    "R5IRollbackReceipt",
    "R5IRollbackRequest",
]
