from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel
from ..optimization.r6v2_models import (
    R6V2_EXACT_VALIDATION_BUDGET,
    R6V2_SCENARIO_IDS,
    R6V2_SCREENING_CANDIDATE_COUNT,
    R6V2CandidateSurrogateContext,
    RecommendationSetV2,
    RecommendationSetV3,
)
from .models import HASH_PATTERN, VERSIONED_ID_PATTERN, canonical_hash
from .r5e_models import R5ESyntheticCampaignReport

R5F_SAFETY_BANNER = (
    "CANDIDATE DOWNSTREAM IMPACT EVALUATION / EVALUATED ONLY / "
    "NOT REALITY VALIDATED / NOT DEVICE SAFE / PROMOTION NOT PERFORMED"
)

R5FScenarioId = Literal[
    "canonical-goal-conditioned-speed",
    "canonical-goal-conditioned-quality",
    "canonical-goal-conditioned-compact-command",
]
R5FPrimaryObjectiveId = Literal[
    "cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"
]


def _finite(value: Any) -> Any:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("value must be a finite JSON number")
    return value


def _primary_value(recommendation: RecommendationSetV2) -> float | int | None:
    best_ids = set(recommendation.best_observed_candidate_ids)
    values = [
        item.objectives
        for item in recommendation.exact_candidates
        if item.candidate_id in best_ids
    ]
    if not values:
        return None
    primary = recommendation.search_request.intent.primary_objective_id
    if primary == "cycleTimeSeconds":
        return min(item.cycle_time_seconds for item in values)
    if primary == "linearFollowingErrorMaxMm":
        return min(item.linear_following_error_max_mm for item in values)
    return min(item.command_sample_count for item in values)


class R5FSharedPredictionErrorDelta(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    shared_candidate_count: int = Field(alias="sharedCandidateCount", ge=1, le=27)
    baseline_mean_absolute_error: float = Field(
        alias="baselineMeanAbsoluteError", ge=0.0
    )
    candidate_mean_absolute_error: float = Field(
        alias="candidateMeanAbsoluteError", ge=0.0
    )
    absolute_change: float = Field(alias="absoluteChange")
    status: Literal["Improved", "Unchanged", "Regressed"]

    @field_validator(
        "baseline_mean_absolute_error",
        "candidate_mean_absolute_error",
        "absolute_change",
        mode="before",
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_delta(self) -> R5FSharedPredictionErrorDelta:
        expected_unit = "s" if self.target_id == "cycleTimeSeconds" else "mm"
        if self.unit != expected_unit:
            raise ValueError("prediction error unit must match targetId")
        expected_change = (
            self.candidate_mean_absolute_error
            - self.baseline_mean_absolute_error
        )
        if not math.isclose(
            self.absolute_change, expected_change, rel_tol=0.0, abs_tol=1e-15
        ):
            raise ValueError("absoluteChange must equal candidate minus baseline")
        expected_status = (
            "Improved"
            if expected_change < -1e-15
            else "Regressed"
            if expected_change > 1e-15
            else "Unchanged"
        )
        if self.status != expected_status:
            raise ValueError("prediction error status must match absoluteChange")
        return self


class R5FScenarioImpact(AxiomModel):
    scenario_id: R5FScenarioId = Field(alias="scenarioId")
    primary_objective_id: R5FPrimaryObjectiveId = Field(alias="primaryObjectiveId")
    primary_objective_unit: Literal["s", "mm", "count"] = Field(
        alias="primaryObjectiveUnit"
    )
    baseline_recommendation: RecommendationSetV2 = Field(
        alias="baselineRecommendation"
    )
    candidate_recommendation: RecommendationSetV3 = Field(
        alias="candidateRecommendation"
    )
    selected_candidate_overlap_count: int = Field(
        alias="selectedCandidateOverlapCount", ge=0, le=27
    )
    baseline_only_selected_candidate_ids: tuple[str, ...] = Field(
        alias="baselineOnlySelectedCandidateIds"
    )
    candidate_only_selected_candidate_ids: tuple[str, ...] = Field(
        alias="candidateOnlySelectedCandidateIds"
    )
    screening_order_changed: bool = Field(alias="screeningOrderChanged")
    baseline_best_value: float | int | None = Field(alias="baselineBestValue")
    candidate_best_value: float | int | None = Field(alias="candidateBestValue")
    comparison_tolerance: float = Field(alias="comparisonTolerance", ge=0.0)
    primary_objective_status: Literal[
        "NoRegression", "Regressed", "Inconclusive"
    ] = Field(alias="primaryObjectiveStatus")
    shared_prediction_error_deltas: tuple[
        R5FSharedPredictionErrorDelta, R5FSharedPredictionErrorDelta
    ] = Field(alias="sharedPredictionErrorDeltas")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator(
        "baseline_best_value",
        "candidate_best_value",
        "comparison_tolerance",
        mode="before",
    )
    @classmethod
    def reject_non_finite_optional(cls, value: Any) -> Any:
        return None if value is None else _finite(value)

    @model_validator(mode="after")
    def validate_derived_impact(self) -> R5FScenarioImpact:
        baseline = self.baseline_recommendation
        candidate = self.candidate_recommendation
        if (
            baseline.search_request.scenario_id != self.scenario_id
            or candidate.search_request.scenario_id != self.scenario_id
        ):
            raise ValueError("recommendations must match scenarioId")
        if baseline.search_request.intent != candidate.search_request.intent:
            raise ValueError("baseline and candidate must use the same intent")
        shared_search_fields = (
            (baseline.search_request.feed_overrides, candidate.search_request.feed_overrides),
            (baseline.search_request.sample_periods, candidate.search_request.sample_periods),
            (
                baseline.search_request.exact_validation_budget,
                candidate.search_request.exact_validation_budget,
            ),
            (
                baseline.search_request.screening_policy_id,
                candidate.search_request.screening_policy_id,
            ),
        )
        if any(left != right for left, right in shared_search_fields):
            raise ValueError("baseline and candidate must share one frozen search contract")
        if self.primary_objective_id != baseline.search_request.intent.primary_objective_id:
            raise ValueError("primaryObjectiveId must match the search intent")
        expected_unit = {
            "cycleTimeSeconds": "s",
            "linearFollowingErrorMaxMm": "mm",
            "commandSampleCount": "count",
        }[self.primary_objective_id]
        if self.primary_objective_unit != expected_unit:
            raise ValueError("primaryObjectiveUnit must match primaryObjectiveId")
        for recommendation in (baseline, candidate):
            if recommendation.screening_candidate_count != 135:
                raise ValueError("impact evaluation requires the frozen 135-point grid")
            if recommendation.screening_receipt.selected_count != 27:
                raise ValueError("impact evaluation requires all 27 exact replays")
            if len(recommendation.exact_candidates) != 27:
                raise ValueError("impact evaluation must contain 27 exact candidates")

        baseline_ids = baseline.screening_receipt.selected_candidate_ids
        candidate_ids = candidate.screening_receipt.selected_candidate_ids
        baseline_set = set(baseline_ids)
        candidate_set = set(candidate_ids)
        overlap = baseline_set & candidate_set
        if self.selected_candidate_overlap_count != len(overlap):
            raise ValueError("selectedCandidateOverlapCount must match both selections")
        expected_baseline_only = tuple(
            item for item in baseline_ids if item not in candidate_set
        )
        expected_candidate_only = tuple(
            item for item in candidate_ids if item not in baseline_set
        )
        if self.baseline_only_selected_candidate_ids != expected_baseline_only:
            raise ValueError("baselineOnlySelectedCandidateIds must be derived")
        if self.candidate_only_selected_candidate_ids != expected_candidate_only:
            raise ValueError("candidateOnlySelectedCandidateIds must be derived")
        if self.screening_order_changed != (baseline_ids != candidate_ids):
            raise ValueError("screeningOrderChanged must match ranked selections")

        expected_baseline_best = _primary_value(baseline)
        expected_candidate_best = _primary_value(candidate)
        if self.baseline_best_value != expected_baseline_best:
            raise ValueError("baselineBestValue must match exact best evidence")
        if self.candidate_best_value != expected_candidate_best:
            raise ValueError("candidateBestValue must match exact best evidence")
        expected_tolerance = (
            0.0 if self.primary_objective_id == "commandSampleCount" else 1e-12
        )
        if self.comparison_tolerance != expected_tolerance:
            raise ValueError("comparisonTolerance must match the primary objective")
        if expected_baseline_best is None or expected_candidate_best is None:
            expected_status = "Inconclusive"
        elif float(expected_candidate_best) <= (
            float(expected_baseline_best) + expected_tolerance
        ):
            expected_status = "NoRegression"
        else:
            expected_status = "Regressed"
        if self.primary_objective_status != expected_status:
            raise ValueError("primaryObjectiveStatus must match exact best evidence")

        if tuple(
            item.target_id for item in self.shared_prediction_error_deltas
        ) != ("cycleTimeSeconds", "linearFollowingErrorMaxMm"):
            raise ValueError("shared prediction deltas must keep target order")
        baseline_exact = {item.candidate_id: item for item in baseline.exact_candidates}
        candidate_exact = {
            item.candidate_id: item for item in candidate.exact_candidates
        }
        shared_ids = tuple(item for item in baseline_ids if item in candidate_exact)
        for delta in self.shared_prediction_error_deltas:
            if delta.shared_candidate_count != len(shared_ids):
                raise ValueError("sharedCandidateCount must match exact overlap")
            attribute = (
                "cycle_time_prediction_absolute_error"
                if delta.target_id == "cycleTimeSeconds"
                else "linear_error_prediction_absolute_error"
            )
            expected_baseline_error = math.fsum(
                getattr(baseline_exact[item], attribute) for item in shared_ids
            ) / len(shared_ids)
            expected_candidate_error = math.fsum(
                getattr(candidate_exact[item], attribute) for item in shared_ids
            ) / len(shared_ids)
            if not math.isclose(
                delta.baseline_mean_absolute_error,
                expected_baseline_error,
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise ValueError("baseline prediction error must match shared evidence")
            if not math.isclose(
                delta.candidate_mean_absolute_error,
                expected_candidate_error,
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise ValueError("candidate prediction error must match shared evidence")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match scenario impact content")
        return self


class R5FCandidateImpactReport(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.candidate-downstream-impact-report@1"
    ] = Field(alias="schemaId")
    report_id: str = Field(alias="reportId", pattern=VERSIONED_ID_PATTERN)
    source_campaign_report: R5ESyntheticCampaignReport = Field(
        alias="sourceCampaignReport"
    )
    scenario_impacts: tuple[
        R5FScenarioImpact, R5FScenarioImpact, R5FScenarioImpact
    ] = Field(alias="scenarioImpacts")
    impact_gate_status: Literal["Passed", "Failed"] = Field(
        alias="impactGateStatus"
    )
    candidate_use_status: Literal["EvaluatedOnly"] = Field(
        alias="candidateUseStatus"
    )
    model_promotion_status: Literal["NotPerformed"] = Field(
        alias="modelPromotionStatus"
    )
    general_improvement_guarantee: Literal["NotClaimed"] = Field(
        alias="generalImprovementGuarantee"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    automatic_acceptance_allowed: Literal[False] = Field(
        alias="automaticAcceptanceAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[
        "CANDIDATE DOWNSTREAM IMPACT EVALUATION / EVALUATED ONLY / NOT REALITY VALIDATED / NOT DEVICE SAFE / PROMOTION NOT PERFORMED"
    ] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_lineage_and_status(self) -> R5FCandidateImpactReport:
        if tuple(item.scenario_id for item in self.scenario_impacts) != R6V2_SCENARIO_IDS:
            raise ValueError("scenarioImpacts must cover the three frozen R6 v2 intents")
        campaign = self.source_campaign_report
        if campaign.candidate_assessment.candidate_gate_status != "Passed":
            raise ValueError("R5-F requires a Passed R5-E candidate gate")
        baseline_context_hashes: set[str] = set()
        candidate_context_hashes: set[str] = set()
        for impact in self.scenario_impacts:
            baseline_context = impact.baseline_recommendation.search_request.surrogate_context
            candidate_context = impact.candidate_recommendation.search_request.surrogate_context
            if not isinstance(candidate_context, R6V2CandidateSurrogateContext):
                raise ValueError("candidate recommendation must use candidate context")
            baseline_context_hashes.add(baseline_context.context_hash)
            candidate_context_hashes.add(candidate_context.context_hash)
            if (
                baseline_context.model_bundle.content_hash
                != campaign.candidate_assessment.source_model_bundle_hash
            ):
                raise ValueError("baseline recommendation must use the R5-E parent model")
            candidate_identities = (
                (
                    candidate_context.source_campaign_report_hash,
                    campaign.content_hash,
                ),
                (
                    candidate_context.model_bundle.content_hash,
                    campaign.model_bundle.content_hash,
                ),
                (
                    candidate_context.training_receipt.content_hash,
                    campaign.training_receipt.content_hash,
                ),
                (
                    candidate_context.parity_receipt.content_hash,
                    campaign.parity_receipt.content_hash,
                ),
                (
                    candidate_context.candidate_assessment.content_hash,
                    campaign.candidate_assessment.content_hash,
                ),
                (
                    candidate_context.dataset_content_hash,
                    campaign.dataset.content_hash,
                ),
                (
                    candidate_context.split_manifest_content_hash,
                    campaign.split_manifest.content_hash,
                ),
            )
            if any(actual != expected for actual, expected in candidate_identities):
                raise ValueError("candidate context must identify the complete R5-E report")
        if len(baseline_context_hashes) != 1 or len(candidate_context_hashes) != 1:
            raise ValueError("all scenarios must share one baseline and candidate context")
        expected_gate = (
            "Passed"
            if all(
                item.primary_objective_status == "NoRegression"
                for item in self.scenario_impacts
            )
            else "Failed"
        )
        if self.impact_gate_status != expected_gate:
            raise ValueError("impactGateStatus must derive from all scenario impacts")
        if self.model_promotion_status != campaign.model_promotion_status:
            raise ValueError("R5-F cannot change R5-E model promotion status")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match R5-F impact report content")
        return self


class R5FImpactAssessmentCommand(AxiomModel):
    campaign_report: R5ESyntheticCampaignReport = Field(alias="campaignReport")


class R5FManifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5f-manifest@1"] = Field(
        alias="manifestId"
    )
    schema_id: Literal["axiom.intelligence.r5f-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-F"]
    platform: Literal["windows"]
    baseline_context_id: Literal[
        "optimization.r6v2.r5c-surrogate-context@1"
    ] = Field(alias="baselineContextId")
    candidate_context_id: Literal[
        "optimization.r6v2.r5e-candidate-surrogate-context@2"
    ] = Field(alias="candidateContextId")
    scenario_ids: tuple[R5FScenarioId, R5FScenarioId, R5FScenarioId] = Field(
        alias="scenarioIds"
    )
    screening_candidate_count: Literal[135] = Field(alias="screeningCandidateCount")
    exact_validation_budget: Literal[27] = Field(alias="exactValidationBudget")
    candidate_use_status: Literal["EvaluatedOnly"] = Field(
        alias="candidateUseStatus"
    )
    automatic_model_promotion_allowed: Literal[False] = Field(
        alias="automaticModelPromotionAllowed"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[
        "CANDIDATE DOWNSTREAM IMPACT EVALUATION / EVALUATED ONLY / NOT REALITY VALIDATED / NOT DEVICE SAFE / PROMOTION NOT PERFORMED"
    ] = Field(alias="safetyBanner")

    @model_validator(mode="after")
    def freeze_contract(self) -> R5FManifest:
        if self.scenario_ids != R6V2_SCENARIO_IDS:
            raise ValueError("scenarioIds must match the frozen R6 v2 intent set")
        if self.screening_candidate_count != R6V2_SCREENING_CANDIDATE_COUNT:
            raise ValueError("screeningCandidateCount must match R6 v2")
        if self.exact_validation_budget != R6V2_EXACT_VALIDATION_BUDGET:
            raise ValueError("exactValidationBudget must match R6 v2")
        return self


__all__ = [
    "R5F_SAFETY_BANNER",
    "R5FCandidateImpactReport",
    "R5FImpactAssessmentCommand",
    "R5FManifest",
    "R5FScenarioImpact",
    "R5FSharedPredictionErrorDelta",
]
