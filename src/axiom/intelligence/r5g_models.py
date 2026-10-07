from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel
from .models import HASH_PATTERN, VERSIONED_ID_PATTERN, canonical_hash
from .r5f_models import R5FCandidateImpactReport

R5G_SAFETY_BANNER = (
    "PROMOTION READINESS REVIEW / AWAITING INDEPENDENT HUMAN DECISION / "
    "NO MODEL ACTIVATION / NOT REALITY VALIDATED / NOT DEVICE SAFE"
)

R5G_READINESS_CHECK_IDS = (
    "r5e-candidate-gate@1",
    "r5f-impact-gate@1",
    "r5f-deterministic-replay@1",
    "single-candidate-lineage@1",
    "rollback-baseline-bound@1",
)

R5G_REMAINING_GATE_IDS = (
    "real-world-holdout@1",
    "independent-human-decision@1",
    "model-registry@1",
    "activation-and-default-switch@1",
    "rollback-execution@1",
    "runtime-monitoring@1",
)


def _model_identities(
    impact_report: R5FCandidateImpactReport,
) -> tuple[str, str, str]:
    baseline_hashes = {
        item.baseline_recommendation.search_request.surrogate_context.model_bundle.content_hash
        for item in impact_report.scenario_impacts
    }
    candidate_contexts = {
        item.candidate_recommendation.search_request.surrogate_context.context_hash: (
            item.candidate_recommendation.search_request.surrogate_context.model_bundle.content_hash
        )
        for item in impact_report.scenario_impacts
    }
    if len(baseline_hashes) != 1 or len(candidate_contexts) != 1:
        raise ValueError("R5-G requires one baseline and one candidate lineage")
    candidate_context_hash, candidate_model_hash = next(iter(candidate_contexts.items()))
    return next(iter(baseline_hashes)), candidate_model_hash, candidate_context_hash


def _restore_r6v2_parameter_numbers(value: object) -> object:
    if isinstance(value, dict):
        normalized = {
            key: _restore_r6v2_parameter_numbers(item) for key, item in value.items()
        }
        if normalized.get("parameterSchemaId") == (
            "optimization.r6v2.feed-and-sampling@1"
        ):
            values = normalized.get("values")
            if isinstance(values, dict):
                for key in ("feedOverride", "samplePeriod"):
                    item = values.get(key)
                    if isinstance(item, int) and not isinstance(item, bool):
                        values[key] = float(item)
        return normalized
    if isinstance(value, list):
        return [_restore_r6v2_parameter_numbers(item) for item in value]
    return value


class R5GReviewAcknowledgements(AxiomModel):
    reality_gate_open_acknowledged: Literal[True] = Field(
        alias="realityGateOpenAcknowledged"
    )
    device_safety_not_established_acknowledged: Literal[True] = Field(
        alias="deviceSafetyNotEstablishedAcknowledged"
    )
    automatic_deployment_forbidden_acknowledged: Literal[True] = Field(
        alias="automaticDeploymentForbiddenAcknowledged"
    )


class R5GPromotionReadinessCommand(AxiomModel):
    impact_report: R5FCandidateImpactReport = Field(alias="impactReport")
    prepared_by: str = Field(alias="preparedBy", min_length=1, max_length=128)
    reality_gate_open_acknowledged: Literal[True] = Field(
        alias="realityGateOpenAcknowledged"
    )
    device_safety_not_established_acknowledged: Literal[True] = Field(
        alias="deviceSafetyNotEstablishedAcknowledged"
    )
    automatic_deployment_forbidden_acknowledged: Literal[True] = Field(
        alias="automaticDeploymentForbiddenAcknowledged"
    )

    @field_validator("impact_report", mode="before")
    @classmethod
    def restore_javascript_parameter_numbers(cls, value: object) -> object:
        return _restore_r6v2_parameter_numbers(value)

    @field_validator("prepared_by")
    @classmethod
    def reject_blank_preparer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("preparedBy must not be blank")
        return value


class R5GPromotionReadinessRequest(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.model-promotion-readiness-request@1"
    ] = Field(alias="schemaId")
    request_id: str = Field(alias="requestId", pattern=VERSIONED_ID_PATTERN)
    impact_report: R5FCandidateImpactReport = Field(alias="impactReport")
    prepared_by: str = Field(alias="preparedBy", min_length=1, max_length=128)
    review_scope: Literal["synthetic-offline-review"] = Field(alias="reviewScope")
    rollback_baseline_model_bundle_hash: str = Field(
        alias="rollbackBaselineModelBundleHash", pattern=HASH_PATTERN
    )
    acknowledgements: R5GReviewAcknowledgements
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("impact_report", mode="before")
    @classmethod
    def restore_javascript_parameter_numbers(cls, value: object) -> object:
        return _restore_r6v2_parameter_numbers(value)

    @field_validator("prepared_by")
    @classmethod
    def reject_blank_preparer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("preparedBy must not be blank")
        return value

    @model_validator(mode="after")
    def validate_request_identity(self) -> R5GPromotionReadinessRequest:
        R5FCandidateImpactReport.model_validate(
            self.impact_report.model_dump(mode="json", by_alias=True)
        )
        baseline_hash, candidate_hash, _ = _model_identities(self.impact_report)
        if self.rollback_baseline_model_bundle_hash != baseline_hash:
            raise ValueError("rollback baseline must identify the R5-C v1 model")
        if candidate_hash == baseline_hash:
            raise ValueError("candidate model must be distinct from rollback baseline")
        if self.impact_report.model_promotion_status != "NotPerformed":
            raise ValueError("R5-G requires model promotion to remain NotPerformed")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match readiness request content")
        return self


class R5GReadinessCheck(AxiomModel):
    check_id: str = Field(alias="checkId", pattern=VERSIONED_ID_PATTERN)
    status: Literal["Passed", "Blocked"]
    evidence_hash: str = Field(alias="evidenceHash", pattern=HASH_PATTERN)
    reason_code: str = Field(alias="reasonCode", min_length=1)


class R5GRemainingGate(AxiomModel):
    gate_id: str = Field(alias="gateId", pattern=VERSIONED_ID_PATTERN)
    status: Literal["Open"]
    reason_code: str = Field(alias="reasonCode", min_length=1)


class R5GModelPromotionReadinessDossier(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.model-promotion-readiness-dossier@1"
    ] = Field(alias="schemaId")
    dossier_id: str = Field(alias="dossierId", pattern=VERSIONED_ID_PATTERN)
    request: R5GPromotionReadinessRequest
    source_campaign_report_hash: str = Field(
        alias="sourceCampaignReportHash", pattern=HASH_PATTERN
    )
    source_impact_report_hash: str = Field(
        alias="sourceImpactReportHash", pattern=HASH_PATTERN
    )
    replayed_impact_report_hash: str = Field(
        alias="replayedImpactReportHash", pattern=HASH_PATTERN
    )
    baseline_model_bundle_hash: str = Field(
        alias="baselineModelBundleHash", pattern=HASH_PATTERN
    )
    candidate_model_bundle_hash: str = Field(
        alias="candidateModelBundleHash", pattern=HASH_PATTERN
    )
    candidate_context_hash: str = Field(
        alias="candidateContextHash", pattern=HASH_PATTERN
    )
    readiness_checks: tuple[
        R5GReadinessCheck,
        R5GReadinessCheck,
        R5GReadinessCheck,
        R5GReadinessCheck,
        R5GReadinessCheck,
    ] = Field(alias="readinessChecks")
    remaining_gates: tuple[
        R5GRemainingGate,
        R5GRemainingGate,
        R5GRemainingGate,
        R5GRemainingGate,
        R5GRemainingGate,
        R5GRemainingGate,
    ] = Field(alias="remainingGates")
    review_readiness_status: Literal[
        "ReadyForIndependentReview", "Blocked"
    ] = Field(alias="reviewReadinessStatus")
    review_decision_status: Literal[
        "AwaitingIndependentHumanDecision"
    ] = Field(alias="reviewDecisionStatus")
    candidate_use_status: Literal["EvaluatedOnly"] = Field(
        alias="candidateUseStatus"
    )
    model_promotion_status: Literal["NotPerformed"] = Field(
        alias="modelPromotionStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    default_model_changed: Literal[False] = Field(alias="defaultModelChanged")
    model_registry_write_performed: Literal[False] = Field(
        alias="modelRegistryWritePerformed"
    )
    activation_performed: Literal[False] = Field(alias="activationPerformed")
    automatic_deployment_allowed: Literal[False] = Field(
        alias="automaticDeploymentAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[
        "PROMOTION READINESS REVIEW / AWAITING INDEPENDENT HUMAN DECISION / NO MODEL ACTIVATION / NOT REALITY VALIDATED / NOT DEVICE SAFE"
    ] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_dossier(self) -> R5GModelPromotionReadinessDossier:
        R5GPromotionReadinessRequest.model_validate(
            self.request.model_dump(mode="json", by_alias=True)
        )
        impact = self.request.impact_report
        baseline_hash, candidate_hash, context_hash = _model_identities(impact)
        expected_identities = (
            (self.source_campaign_report_hash, impact.source_campaign_report.content_hash),
            (self.source_impact_report_hash, impact.content_hash),
            (self.replayed_impact_report_hash, impact.content_hash),
            (self.baseline_model_bundle_hash, baseline_hash),
            (self.candidate_model_bundle_hash, candidate_hash),
            (self.candidate_context_hash, context_hash),
        )
        if any(actual != expected for actual, expected in expected_identities):
            raise ValueError("R5-G dossier identities must match source evidence")
        if tuple(item.check_id for item in self.readiness_checks) != (
            R5G_READINESS_CHECK_IDS
        ):
            raise ValueError("readinessChecks must use the frozen check order")
        expected_check_statuses = (
            "Passed",
            "Passed" if impact.impact_gate_status == "Passed" else "Blocked",
            "Passed",
            "Passed",
            "Passed",
        )
        if tuple(item.status for item in self.readiness_checks) != (
            expected_check_statuses
        ):
            raise ValueError("readiness check statuses must match source evidence")
        if tuple(item.gate_id for item in self.remaining_gates) != (
            R5G_REMAINING_GATE_IDS
        ):
            raise ValueError("remainingGates must use the frozen gate order")
        expected_readiness = (
            "ReadyForIndependentReview"
            if all(item.status == "Passed" for item in self.readiness_checks)
            else "Blocked"
        )
        if self.review_readiness_status != expected_readiness:
            raise ValueError("reviewReadinessStatus must derive from readiness checks")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match readiness dossier content")
        return self


class R5GManifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5g-manifest@1"] = Field(
        alias="manifestId"
    )
    schema_id: Literal["axiom.intelligence.r5g-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-G"]
    platform: Literal["windows"]
    review_scope: Literal["synthetic-offline-review"] = Field(alias="reviewScope")
    review_readiness_status: Literal["ReadyForIndependentReview"] = Field(
        alias="reviewReadinessStatus"
    )
    review_decision_status: Literal[
        "AwaitingIndependentHumanDecision"
    ] = Field(alias="reviewDecisionStatus")
    automatic_model_promotion_allowed: Literal[False] = Field(
        alias="automaticModelPromotionAllowed"
    )
    model_registry_write_allowed: Literal[False] = Field(
        alias="modelRegistryWriteAllowed"
    )
    default_model_change_allowed: Literal[False] = Field(
        alias="defaultModelChangeAllowed"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[
        "PROMOTION READINESS REVIEW / AWAITING INDEPENDENT HUMAN DECISION / NO MODEL ACTIVATION / NOT REALITY VALIDATED / NOT DEVICE SAFE"
    ] = Field(alias="safetyBanner")


__all__ = [
    "R5G_READINESS_CHECK_IDS",
    "R5G_REMAINING_GATE_IDS",
    "R5G_SAFETY_BANNER",
    "R5GManifest",
    "R5GModelPromotionReadinessDossier",
    "R5GPromotionReadinessCommand",
    "R5GPromotionReadinessRequest",
    "R5GReadinessCheck",
    "R5GRemainingGate",
    "R5GReviewAcknowledgements",
]
