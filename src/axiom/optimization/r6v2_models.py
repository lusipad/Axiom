from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from ..intelligence.models import HASH_PATTERN, VERSIONED_ID_PATTERN
from ..intelligence.r5c_models import (
    ConditionalEffectModelBundle,
    ConditionalEffectModelBundleV2,
    ConditionalEffectParityReceipt,
    ConditionalEffectParityReceiptV2,
    ConditionalEffectTrainingReceipt,
    ConditionalEffectTrainingReceiptV2,
)
from ..intelligence.r5e_models import R5EModelCandidateAssessment
from ..models import AxiomModel, EvaluationCase, ParameterSet
from ..physical.applicability import PhysicalMultirateApplicabilityEvidence
from .models import (
    R6_GATE_IDS,
    R6_OBJECTIVE_IDS,
    OptimizationGateReceipt,
    OptimizationObjectiveVector,
    canonical_hash,
)

R6V2_DOMAIN_PACK_ID = "optimization.domain-pack@2"
R6V2_EVALUATOR_ID = "optimization-evaluator@2"
R6V2_RUNNER_ID = "optimization-surrogate-assisted-search@2"
R6V2_DEFAULT_SCENARIO_ID = "canonical-goal-conditioned-speed"
R6V2_SCENARIO_IDS = (
    R6V2_DEFAULT_SCENARIO_ID,
    "canonical-goal-conditioned-quality",
    "canonical-goal-conditioned-compact-command",
)
R6V2_FEED_OVERRIDES = tuple(round(0.65 + 0.025 * index, 3) for index in range(15))
R6V2_SAMPLE_PERIODS = tuple(
    round(0.04 + 0.005 * index, 3) for index in range(9)
)
R6V2_SCREENING_CANDIDATE_COUNT = 135
R6V2_EXACT_VALIDATION_BUDGET = 27


def _finite(value: Any) -> Any:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("value must be a finite JSON number")
    return value


class CycleTimeOptimizationIntent(AxiomModel):
    intent_id: str = Field(
        default="optimization.r6v2.speed-intent@1",
        alias="intentId",
        pattern=VERSIONED_ID_PATTERN,
    )
    primary_objective_id: Literal["cycleTimeSeconds"] = Field(
        default="cycleTimeSeconds", alias="primaryObjectiveId"
    )
    maximum_linear_following_error_mm: float = Field(
        alias="maximumLinearFollowingErrorMm", gt=0.0
    )
    maximum_command_sample_count: int = Field(
        alias="maximumCommandSampleCount", ge=2
    )

    @field_validator("maximum_linear_following_error_mm", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)


class LinearErrorOptimizationIntent(AxiomModel):
    intent_id: str = Field(
        default="optimization.r6v2.quality-intent@1",
        alias="intentId",
        pattern=VERSIONED_ID_PATTERN,
    )
    primary_objective_id: Literal["linearFollowingErrorMaxMm"] = Field(
        default="linearFollowingErrorMaxMm", alias="primaryObjectiveId"
    )
    maximum_cycle_time_seconds: float = Field(
        alias="maximumCycleTimeSeconds", gt=0.0
    )
    maximum_command_sample_count: int = Field(
        alias="maximumCommandSampleCount", ge=2
    )

    @field_validator("maximum_cycle_time_seconds", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)


class CommandCountOptimizationIntent(AxiomModel):
    intent_id: str = Field(
        default="optimization.r6v2.compact-command-intent@1",
        alias="intentId",
        pattern=VERSIONED_ID_PATTERN,
    )
    primary_objective_id: Literal["commandSampleCount"] = Field(
        default="commandSampleCount", alias="primaryObjectiveId"
    )
    maximum_cycle_time_seconds: float = Field(
        alias="maximumCycleTimeSeconds", gt=0.0
    )
    maximum_linear_following_error_mm: float = Field(
        alias="maximumLinearFollowingErrorMm", gt=0.0
    )

    @field_validator(
        "maximum_cycle_time_seconds",
        "maximum_linear_following_error_mm",
        mode="before",
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)


OptimizationIntentV2 = Annotated[
    CycleTimeOptimizationIntent
    | LinearErrorOptimizationIntent
    | CommandCountOptimizationIntent,
    Field(discriminator="primary_objective_id"),
]


class R6V2SurrogateContext(AxiomModel):
    context_id: Literal["optimization.r6v2.r5c-surrogate-context@1"] = Field(
        alias="contextId"
    )
    model_bundle: ConditionalEffectModelBundle = Field(alias="modelBundle")
    training_receipt: ConditionalEffectTrainingReceipt = Field(
        alias="trainingReceipt"
    )
    parity_receipt: ConditionalEffectParityReceipt = Field(alias="parityReceipt")
    dataset_content_hash: str = Field(
        alias="datasetContentHash", pattern=HASH_PATTERN
    )
    split_manifest_content_hash: str = Field(
        alias="splitManifestContentHash", pattern=HASH_PATTERN
    )
    context_hash: str = Field(alias="contextHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_bindings(self) -> R6V2SurrogateContext:
        bundle = self.model_bundle
        if bundle.synthetic_conditional_effect_contract_status != "Passed":
            raise ValueError("R6 v2 requires a Passed R5-C model bundle")
        if bundle.dataset_content_hash != self.dataset_content_hash:
            raise ValueError("model bundle must identify datasetContentHash")
        if bundle.split_manifest_hash != self.split_manifest_content_hash:
            raise ValueError("model bundle must identify splitManifestContentHash")
        if bundle.training_receipt_hash != self.training_receipt.content_hash:
            raise ValueError("model bundle must identify trainingReceipt")
        if self.training_receipt.dataset_content_hash != self.dataset_content_hash:
            raise ValueError("trainingReceipt must identify dataset")
        if (
            self.training_receipt.split_manifest_hash
            != self.split_manifest_content_hash
        ):
            raise ValueError("trainingReceipt must identify split manifest")
        if self.parity_receipt.model_bundle_hash != bundle.content_hash:
            raise ValueError("parityReceipt must identify model bundle")
        if self.parity_receipt.dataset_content_hash != self.dataset_content_hash:
            raise ValueError("parityReceipt must identify dataset")
        if self.parity_receipt.status != "Passed":
            raise ValueError("R6 v2 requires a Passed target parity receipt")
        expected = canonical_hash(self, exclude={"context_hash"})
        if self.context_hash != expected:
            raise ValueError("contextHash must match R6V2SurrogateContext content")
        return self


class R6V2CandidateSurrogateContext(AxiomModel):
    context_id: Literal[
        "optimization.r6v2.r5e-candidate-surrogate-context@2"
    ] = Field(alias="contextId")
    model_bundle: ConditionalEffectModelBundleV2 = Field(alias="modelBundle")
    training_receipt: ConditionalEffectTrainingReceiptV2 = Field(
        alias="trainingReceipt"
    )
    parity_receipt: ConditionalEffectParityReceiptV2 = Field(alias="parityReceipt")
    candidate_assessment: R5EModelCandidateAssessment = Field(
        alias="candidateAssessment"
    )
    dataset_content_hash: str = Field(
        alias="datasetContentHash", pattern=HASH_PATTERN
    )
    split_manifest_content_hash: str = Field(
        alias="splitManifestContentHash", pattern=HASH_PATTERN
    )
    source_campaign_report_hash: str = Field(
        alias="sourceCampaignReportHash", pattern=HASH_PATTERN
    )
    context_hash: str = Field(alias="contextHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_bindings(self) -> R6V2CandidateSurrogateContext:
        bundle = self.model_bundle
        training = self.training_receipt
        parity = self.parity_receipt
        assessment = self.candidate_assessment
        if bundle.synthetic_conditional_effect_contract_status != "Passed":
            raise ValueError("R6 v2 requires a Passed R5-E candidate model bundle")
        if bundle.dataset_content_hash != self.dataset_content_hash:
            raise ValueError("candidate bundle must identify datasetContentHash")
        if bundle.split_manifest_hash != self.split_manifest_content_hash:
            raise ValueError("candidate bundle must identify splitManifestContentHash")
        if bundle.training_receipt_hash != training.content_hash:
            raise ValueError("candidate bundle must identify trainingReceipt")
        if training.dataset_content_hash != self.dataset_content_hash:
            raise ValueError("trainingReceipt must identify candidate dataset")
        if training.split_manifest_hash != self.split_manifest_content_hash:
            raise ValueError("trainingReceipt must identify candidate split manifest")
        if parity.model_bundle_hash != bundle.content_hash:
            raise ValueError("parityReceipt must identify candidate model bundle")
        if parity.dataset_content_hash != self.dataset_content_hash:
            raise ValueError("parityReceipt must identify candidate dataset")
        if parity.status != "Passed":
            raise ValueError("R6 v2 requires a Passed candidate parity receipt")
        acquisition_hashes = {
            bundle.acquisition_receipt_hash,
            training.acquisition_receipt_hash,
            parity.acquisition_receipt_hash,
        }
        if len(acquisition_hashes) != 1:
            raise ValueError("candidate artifacts must share one acquisition receipt")
        if assessment.candidate_model_bundle_hash != bundle.content_hash:
            raise ValueError("candidate assessment must identify model bundle")
        if assessment.source_model_bundle_hash != bundle.parent_model_bundle_hash:
            raise ValueError("candidate assessment must identify parent model")
        if training.parent_model_bundle_hash != bundle.parent_model_bundle_hash:
            raise ValueError("trainingReceipt must identify parent model")
        if assessment.candidate_gate_status != "Passed":
            raise ValueError("R6 v2 candidate context requires a Passed candidate gate")
        if not assessment.eligible_for_manual_promotion:
            raise ValueError("R6 v2 candidate must remain eligible for manual review")
        if assessment.model_promotion_status != "NotPerformed":
            raise ValueError("R6 v2 candidate context cannot contain a promoted model")
        if self.context_hash != canonical_hash(self, exclude={"context_hash"}):
            raise ValueError("contextHash must match candidate surrogate context")
        return self


class R6V2SearchRequest(AxiomModel):
    schema_id: Literal["optimization.search-request@2"] = Field(
        default="optimization.search-request@2", alias="schemaId"
    )
    scenario_id: Literal[
        "canonical-goal-conditioned-speed",
        "canonical-goal-conditioned-quality",
        "canonical-goal-conditioned-compact-command",
    ] = Field(alias="scenarioId")
    intent: OptimizationIntentV2
    surrogate_context: R6V2SurrogateContext = Field(alias="surrogateContext")
    screening_policy_id: Literal[
        "optimization.r6v2.possible-feasible-lower-bound@1"
    ] = Field(
        default="optimization.r6v2.possible-feasible-lower-bound@1",
        alias="screeningPolicyId",
    )
    feed_overrides: tuple[float, ...] = Field(
        default=R6V2_FEED_OVERRIDES, alias="feedOverrides"
    )
    sample_periods: tuple[float, ...] = Field(
        default=R6V2_SAMPLE_PERIODS, alias="samplePeriods"
    )
    exact_validation_budget: Literal[27] = Field(
        default=R6V2_EXACT_VALIDATION_BUDGET, alias="exactValidationBudget"
    )

    @field_validator("feed_overrides", "sample_periods", mode="before")
    @classmethod
    def reject_non_finite_grid(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            for item in value:
                _finite(item)
        return value

    @model_validator(mode="after")
    def freeze_grid(self) -> R6V2SearchRequest:
        if self.feed_overrides != R6V2_FEED_OVERRIDES:
            raise ValueError("feedOverrides must match the frozen 15-value R6 v2 grid")
        if self.sample_periods != R6V2_SAMPLE_PERIODS:
            raise ValueError(
                "samplePeriods must match the frozen 9-value R6 v2 grid"
            )
        return self


class R6V2CandidateSearchRequest(R6V2SearchRequest):
    schema_id: Literal["optimization.search-request@3"] = Field(
        default="optimization.search-request@3", alias="schemaId"
    )
    surrogate_context: R6V2CandidateSurrogateContext = Field(
        alias="surrogateContext"
    )


class R6V2TargetEstimate(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    value: float
    lower: float
    upper: float

    @field_validator("value", "lower", "upper", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_interval_and_unit(self) -> R6V2TargetEstimate:
        if not self.lower <= self.value <= self.upper:
            raise ValueError("estimate interval must contain value")
        units = {"cycleTimeSeconds": "s", "linearFollowingErrorMaxMm": "mm"}
        if self.unit != units[self.target_id]:
            raise ValueError("target unit must match targetId")
        return self


class R6V2ScreeningCandidate(AxiomModel):
    candidate_id: str = Field(alias="candidateId", pattern=VERSIONED_ID_PATTERN)
    parameter_set: ParameterSet = Field(alias="parameterSet")
    cycle_time_estimate: R6V2TargetEstimate = Field(alias="cycleTimeEstimate")
    linear_error_estimate: R6V2TargetEstimate = Field(alias="linearErrorEstimate")
    estimated_command_sample_count: int = Field(
        alias="estimatedCommandSampleCount", ge=2
    )
    estimated_command_sample_count_lower: int = Field(
        alias="estimatedCommandSampleCountLower", ge=2
    )
    estimated_command_sample_count_upper: int = Field(
        alias="estimatedCommandSampleCountUpper", ge=2
    )
    domain_status: Literal["InDomain"] = Field(alias="domainStatus")
    possibly_feasible: bool = Field(alias="possiblyFeasible")
    screening_rank: int | None = Field(
        default=None, alias="screeningRank", ge=1
    )
    selected_for_exact_validation: bool = Field(alias="selectedForExactValidation")
    reason_code: Literal[
        "ConstraintLowerBoundExceeded", "ExactValidationBudgetExceeded"
    ] | None = Field(default=None, alias="reasonCode")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_selection_state(self) -> R6V2ScreeningCandidate:
        if not (
            self.estimated_command_sample_count_lower
            <= self.estimated_command_sample_count
            <= self.estimated_command_sample_count_upper
        ):
            raise ValueError("estimated command counts must be ordered")
        if self.selected_for_exact_validation:
            if not self.possibly_feasible or self.screening_rank is None:
                raise ValueError("selected candidate must be ranked and possibly feasible")
            if self.screening_rank > R6V2_EXACT_VALIDATION_BUDGET:
                raise ValueError("selected candidate rank exceeds exact budget")
            if self.reason_code is not None:
                raise ValueError("selected candidate must not carry reasonCode")
        elif not self.possibly_feasible:
            if self.screening_rank is not None:
                raise ValueError("constraint-excluded candidate must not be ranked")
            if self.reason_code != "ConstraintLowerBoundExceeded":
                raise ValueError("constraint-excluded candidate needs reasonCode")
        else:
            if (
                self.screening_rank is None
                or self.screening_rank <= R6V2_EXACT_VALIDATION_BUDGET
            ):
                raise ValueError(
                    "budget-excluded candidate must have rank above exact budget"
                )
            if self.reason_code != "ExactValidationBudgetExceeded":
                raise ValueError("budget-excluded candidate needs reasonCode")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match screening candidate content")
        return self


class R6V2SurrogateScreeningReceipt(AxiomModel):
    artifact_type: Literal["axiom.optimization.surrogate-screening-receipt"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["axiom.optimization.surrogate-screening-receipt@1"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    receipt_id: str = Field(alias="receiptId", pattern=VERSIONED_ID_PATTERN)
    search_request_hash: str = Field(alias="searchRequestHash", pattern=HASH_PATTERN)
    surrogate_context_hash: str = Field(
        alias="surrogateContextHash", pattern=HASH_PATTERN
    )
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    screening_policy_id: Literal[
        "optimization.r6v2.possible-feasible-lower-bound@1"
    ] = Field(alias="screeningPolicyId")
    candidate_count: Literal[135] = Field(alias="candidateCount")
    possibly_feasible_count: int = Field(alias="possiblyFeasibleCount", ge=0, le=135)
    selected_count: int = Field(alias="selectedCount", ge=0, le=27)
    exact_validation_budget: Literal[27] = Field(alias="exactValidationBudget")
    selected_candidate_ids: tuple[str, ...] = Field(alias="selectedCandidateIds")
    candidates: tuple[R6V2ScreeningCandidate, ...] = Field(
        min_length=135, max_length=135
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_aggregate(self) -> R6V2SurrogateScreeningReceipt:
        possible = tuple(item for item in self.candidates if item.possibly_feasible)
        selected = tuple(
            sorted(
                (
                    item
                    for item in self.candidates
                    if item.selected_for_exact_validation
                ),
                key=lambda item: item.screening_rank or 0,
            )
        )
        if self.possibly_feasible_count != len(possible):
            raise ValueError("possiblyFeasibleCount must match candidates")
        if self.selected_count != len(selected):
            raise ValueError("selectedCount must match candidates")
        expected_ids = tuple(item.candidate_id for item in selected)
        if self.selected_candidate_ids != expected_ids:
            raise ValueError("selectedCandidateIds must follow screening rank")
        ranks = tuple(item.screening_rank for item in possible)
        if set(ranks) != set(range(1, len(possible) + 1)):
            raise ValueError("possibly feasible candidates must use contiguous ranks")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match screening receipt content")
        return self


class R6V2ExactCandidate(AxiomModel):
    candidate_id: str = Field(alias="candidateId", pattern=VERSIONED_ID_PATTERN)
    parameter_set: ParameterSet = Field(alias="parameterSet")
    screening_estimate_content_hash: str = Field(
        alias="screeningEstimateContentHash", pattern=HASH_PATTERN
    )
    screening_possibly_feasible: Literal[True] = Field(
        alias="screeningPossiblyFeasible"
    )
    screening_rank: int = Field(alias="screeningRank", ge=1, le=27)
    objectives: OptimizationObjectiveVector
    gate_receipts: tuple[OptimizationGateReceipt, ...] = Field(
        alias="gateReceipts", min_length=7, max_length=7
    )
    physical_applicability_passed: bool = Field(alias="physicalApplicabilityPassed")
    hard_constraints_satisfied: bool = Field(alias="hardConstraintsSatisfied")
    exact_constraints_satisfied: bool = Field(alias="exactConstraintsSatisfied")
    recommendation_eligible: bool = Field(alias="recommendationEligible")
    pareto_optimal_within_validated: bool = Field(
        alias="paretoOptimalWithinValidated"
    )
    best_observed: bool = Field(alias="bestObserved")
    m4_content_hash: str = Field(alias="m4ContentHash", pattern=HASH_PATTERN)
    m5_content_hash: str = Field(alias="m5ContentHash", pattern=HASH_PATTERN)
    physical_response_content_hash: str = Field(
        alias="physicalResponseContentHash", pattern=HASH_PATTERN
    )
    r5a_model_bundle_hash: str = Field(
        alias="r5aModelBundleHash", pattern=HASH_PATTERN
    )
    ood_fraction: float = Field(alias="oodFraction", ge=0.0, le=1.0)
    epistemic_status: Literal[
        "InDomain", "PartiallyOutOfDomain", "Unavailable"
    ] = Field(alias="epistemicStatus")
    cycle_time_prediction_absolute_error: float = Field(
        alias="cycleTimePredictionAbsoluteError", ge=0.0
    )
    linear_error_prediction_absolute_error: float = Field(
        alias="linearErrorPredictionAbsoluteError", ge=0.0
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    promotion_eligible: Literal[False] = Field(alias="promotionEligible")
    explanation: str = Field(min_length=1)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator(
        "ood_fraction",
        "cycle_time_prediction_absolute_error",
        "linear_error_prediction_absolute_error",
        mode="before",
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_evidence_and_flags(self) -> R6V2ExactCandidate:
        if tuple(item.claim_id for item in self.gate_receipts) != R6_GATE_IDS:
            raise ValueError("gateReceipts must exactly cover the seven math gates")
        expected_hard = self.physical_applicability_passed and all(
            item.status == "Supported" for item in self.gate_receipts
        )
        if self.hard_constraints_satisfied != expected_hard:
            raise ValueError("hardConstraintsSatisfied must derive from exact gates")
        expected_eligible = expected_hard and self.exact_constraints_satisfied
        if self.recommendation_eligible != expected_eligible:
            raise ValueError("recommendationEligible must derive from exact evidence")
        if (
            self.pareto_optimal_within_validated or self.best_observed
        ) and not expected_eligible:
            raise ValueError("Pareto/best markers require recommendation eligibility")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match exact candidate content")
        return self


class R6V2ValidationPlan(AxiomModel):
    plan_id: Literal["optimization.r6v2.offline-validation-plan@1"] = Field(
        alias="planId"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    optimality_scope: Literal[
        "best-observed-within-exact-validation-budget"
    ] = Field(alias="optimalityScope")
    remaining_gates: tuple[str, ...] = Field(alias="remainingGates", min_length=1)
    stop_conditions: tuple[str, ...] = Field(alias="stopConditions", min_length=1)
    rollback_parameter_set_id: str = Field(
        alias="rollbackParameterSetId", pattern=VERSIONED_ID_PATTERN
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")


def _objective_values(candidate: R6V2ExactCandidate) -> tuple[float, float, int]:
    objectives = candidate.objectives
    return (
        objectives.cycle_time_seconds,
        objectives.linear_following_error_max_mm,
        objectives.command_sample_count,
    )


def _dominates(left: R6V2ExactCandidate, right: R6V2ExactCandidate) -> bool:
    left_values = _objective_values(left)
    right_values = _objective_values(right)
    return all(
        left_value <= right_value
        for left_value, right_value in zip(left_values, right_values, strict=True)
    ) and any(
        left_value < right_value
        for left_value, right_value in zip(left_values, right_values, strict=True)
    )


def _primary_value(
    candidate: R6V2ExactCandidate, primary_objective_id: str
) -> float | int:
    if primary_objective_id == "cycleTimeSeconds":
        return candidate.objectives.cycle_time_seconds
    if primary_objective_id == "linearFollowingErrorMaxMm":
        return candidate.objectives.linear_following_error_max_mm
    return candidate.objectives.command_sample_count


class RecommendationSetV2(AxiomModel):
    artifact_type: Literal["axiom.optimization.recommendation-set"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["axiom.optimization.recommendation-set@2"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[2] = Field(alias="schemaVersion")
    recommendation_set_id: str = Field(
        alias="recommendationSetId", pattern=VERSIONED_ID_PATTERN
    )
    search_request: R6V2SearchRequest = Field(alias="searchRequest")
    surrogate_context_hash: str = Field(
        alias="surrogateContextHash", pattern=HASH_PATTERN
    )
    screening_receipt: R6V2SurrogateScreeningReceipt = Field(
        alias="screeningReceipt"
    )
    exact_candidates: tuple[R6V2ExactCandidate, ...] = Field(
        alias="exactCandidates", max_length=27
    )
    exact_feasible_candidate_ids: tuple[str, ...] = Field(
        alias="exactFeasibleCandidateIds"
    )
    pareto_candidate_ids: tuple[str, ...] = Field(alias="paretoCandidateIds")
    best_observed_candidate_ids: tuple[str, ...] = Field(
        alias="bestObservedCandidateIds"
    )
    physical_applicability_evidence: PhysicalMultirateApplicabilityEvidence = Field(
        alias="physicalApplicabilityEvidence"
    )
    validation_plan: R6V2ValidationPlan = Field(alias="validationPlan")
    screening_candidate_count: Literal[135] = Field(alias="screeningCandidateCount")
    exact_validation_budget: Literal[27] = Field(alias="exactValidationBudget")
    optimality_scope: Literal[
        "best-observed-within-exact-validation-budget"
    ] = Field(alias="optimalityScope")
    global_optimality_status: Literal["NotClaimed"] = Field(
        alias="globalOptimalityStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    automatic_acceptance_allowed: Literal[False] = Field(
        alias="automaticAcceptanceAllowed"
    )
    shadow_status: Literal["Open"] = Field(alias="shadowStatus")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_aggregate_and_identity(self) -> RecommendationSetV2:
        if self.surrogate_context_hash != self.search_request.surrogate_context.context_hash:
            raise ValueError("surrogateContextHash must identify search context")
        if self.screening_receipt.search_request_hash != canonical_hash(
            self.search_request
        ):
            raise ValueError("screening receipt must identify searchRequest")
        if (
            self.screening_receipt.surrogate_context_hash
            != self.surrogate_context_hash
        ):
            raise ValueError("screening receipt must identify surrogate context")
        exact_ids = tuple(item.candidate_id for item in self.exact_candidates)
        if exact_ids != self.screening_receipt.selected_candidate_ids:
            raise ValueError("exact candidates must follow screening selection rank")
        screening = {item.candidate_id: item for item in self.screening_receipt.candidates}
        for candidate in self.exact_candidates:
            estimate = screening[candidate.candidate_id]
            if candidate.screening_estimate_content_hash != estimate.content_hash:
                raise ValueError("exact candidate must identify screening estimate")
            if candidate.screening_rank != estimate.screening_rank:
                raise ValueError("exact candidate rank must match screening estimate")
        eligible = tuple(
            item for item in self.exact_candidates if item.recommendation_eligible
        )
        expected_eligible_ids = tuple(item.candidate_id for item in eligible)
        if self.exact_feasible_candidate_ids != expected_eligible_ids:
            raise ValueError("exactFeasibleCandidateIds must match exact evidence")
        expected_pareto_ids = tuple(
            item.candidate_id
            for item in eligible
            if not any(
                _dominates(other, item) for other in eligible if other is not item
            )
        )
        if self.pareto_candidate_ids != expected_pareto_ids:
            raise ValueError("paretoCandidateIds must match exact feasible candidates")
        primary = self.search_request.intent.primary_objective_id
        if eligible:
            best_value = min(_primary_value(item, primary) for item in eligible)
            expected_best_ids = tuple(
                item.candidate_id
                for item in eligible
                if _primary_value(item, primary) == best_value
            )
        else:
            expected_best_ids = ()
        if self.best_observed_candidate_ids != expected_best_ids:
            raise ValueError("bestObservedCandidateIds must match exact primary objective")
        marked_pareto = tuple(
            item.candidate_id
            for item in self.exact_candidates
            if item.pareto_optimal_within_validated
        )
        marked_best = tuple(
            item.candidate_id for item in self.exact_candidates if item.best_observed
        )
        if marked_pareto != expected_pareto_ids or marked_best != expected_best_ids:
            raise ValueError("exact candidate Pareto/best markers must match aggregate")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match RecommendationSetV2 content")
        return self


class RecommendationSetV3(RecommendationSetV2):
    schema_id: Literal["axiom.optimization.recommendation-set@3"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[3] = Field(alias="schemaVersion")
    search_request: R6V2CandidateSearchRequest = Field(alias="searchRequest")


class R6V2EvaluationRequest(AxiomModel):
    artifact: RecommendationSetV2
    search_spec: R6V2SearchRequest = Field(alias="searchSpec")
    case: EvaluationCase

    @model_validator(mode="after")
    def bind_search_request(self) -> R6V2EvaluationRequest:
        if self.artifact.search_request != self.search_spec:
            raise ValueError("artifact searchRequest must match searchSpec")
        return self


class R6V2Manifest(AxiomModel):
    manifest_id: Literal["optimization.r6v2-manifest@1"] = Field(alias="manifestId")
    schema_id: Literal["optimization.r6v2-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[2] = Field(alias="schemaVersion")
    domain_pack_id: Literal["optimization.domain-pack@2"] = Field(
        alias="domainPackId"
    )
    evaluator_version: Literal["optimization-evaluator@2"] = Field(
        alias="evaluatorVersion"
    )
    runner_id: Literal["optimization-surrogate-assisted-search@2"] = Field(
        alias="runnerId"
    )
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms"
    )
    parameter_ids: tuple[str, str] = Field(alias="parameterIds")
    objective_ids: tuple[str, str, str] = Field(alias="objectiveIds")
    scenario_ids: tuple[str, str, str] = Field(alias="scenarioIds")
    screening_candidate_count: Literal[135] = Field(alias="screeningCandidateCount")
    exact_validation_budget: Literal[27] = Field(alias="exactValidationBudget")
    optimality_scope: Literal[
        "best-observed-within-exact-validation-budget"
    ] = Field(alias="optimalityScope")
    global_optimality_status: Literal["NotClaimed"] = Field(
        alias="globalOptimalityStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")

    @model_validator(mode="after")
    def freeze_contract(self) -> R6V2Manifest:
        if self.parameter_ids != ("feedOverride", "samplePeriod"):
            raise ValueError("parameterIds must match R6 v2 search")
        if self.objective_ids != R6_OBJECTIVE_IDS:
            raise ValueError("objectiveIds must preserve separate R6 objectives")
        if self.scenario_ids != R6V2_SCENARIO_IDS:
            raise ValueError("scenarioIds must match canonical R6 v2 intents")
        return self


class R6V2ScenarioSummary(AxiomModel):
    scenario_id: Literal[
        "canonical-goal-conditioned-speed",
        "canonical-goal-conditioned-quality",
        "canonical-goal-conditioned-compact-command",
    ] = Field(alias="scenarioId")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    primary_objective_id: Literal[
        "cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"
    ] = Field(alias="primaryObjectiveId")
    expected_outcome: Literal["Passed"] = Field(alias="expectedOutcome")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    global_optimality_status: Literal["NotClaimed"] = Field(
        alias="globalOptimalityStatus"
    )


class R6V2ExamplePayload(AxiomModel):
    manifest: R6V2Manifest
    scenario: R6V2ScenarioSummary
    search_request: R6V2SearchRequest = Field(alias="searchRequest")
    recommendation_set: RecommendationSetV2 = Field(alias="recommendationSet")
    run_spec: dict[str, Any] = Field(alias="runSpec")


@dataclass(frozen=True)
class R6V2Scenario:
    summary: R6V2ScenarioSummary
    search_request: R6V2SearchRequest
    recommendation_set: RecommendationSetV2
    run_spec: dict[str, Any]


__all__ = [
    "R6V2_DEFAULT_SCENARIO_ID",
    "R6V2_DOMAIN_PACK_ID",
    "R6V2_EVALUATOR_ID",
    "R6V2_EXACT_VALIDATION_BUDGET",
    "R6V2_FEED_OVERRIDES",
    "R6V2_RUNNER_ID",
    "R6V2_SAMPLE_PERIODS",
    "R6V2_SCENARIO_IDS",
    "R6V2_SCREENING_CANDIDATE_COUNT",
    "CommandCountOptimizationIntent",
    "CycleTimeOptimizationIntent",
    "LinearErrorOptimizationIntent",
    "OptimizationIntentV2",
    "R6V2CandidateSearchRequest",
    "R6V2CandidateSurrogateContext",
    "R6V2EvaluationRequest",
    "R6V2ExactCandidate",
    "R6V2ExamplePayload",
    "R6V2Manifest",
    "R6V2Scenario",
    "R6V2ScenarioSummary",
    "R6V2SearchRequest",
    "R6V2ScreeningCandidate",
    "R6V2SurrogateContext",
    "R6V2SurrogateScreeningReceipt",
    "R6V2TargetEstimate",
    "R6V2ValidationPlan",
    "RecommendationSetV2",
    "RecommendationSetV3",
]
