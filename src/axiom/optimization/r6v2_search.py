from __future__ import annotations

import math
from typing import Any

from ..five_axis.f4_scenarios import load_f4_scenario
from ..intelligence.r5c_interpreter import predict_conditional_effect
from ..intelligence.r5c_models import ConditionalEffectPredictionRequest
from ..intelligence.r5c_scenarios import load_r5c_scenario
from ..intelligence.scenarios import load_r5_scenario
from ..models import ParameterSet
from ..physical import (
    CanonicalParameterPointEvaluation,
    PhysicalModelDefinition,
    build_r4_multirate_applicability_evidence,
    build_r4_multirate_physical_model,
    evaluate_canonical_parameter_point,
)
from .models import R6_GATE_IDS, OptimizationObjectiveVector, canonical_hash
from .r6v2_models import (
    R6V2_EXACT_VALIDATION_BUDGET,
    CommandCountOptimizationIntent,
    CycleTimeOptimizationIntent,
    LinearErrorOptimizationIntent,
    OptimizationIntentV2,
    R6V2CandidateSearchRequest,
    R6V2CandidateSurrogateContext,
    R6V2ExactCandidate,
    R6V2SearchRequest,
    R6V2ScreeningCandidate,
    R6V2SurrogateContext,
    R6V2SurrogateScreeningReceipt,
    R6V2ValidationPlan,
    RecommendationSetV2,
    RecommendationSetV3,
)
from .search import _gate_claim_status, _ood_fraction


def _feed_code(feed_override: float) -> str:
    return f"{round(feed_override * 1000):04d}"


def _period_code(sample_period: float) -> str:
    return f"{round(sample_period * 1000):03d}ms"


def _candidate_id(feed_override: float, sample_period: float) -> str:
    return (
        f"optimization.r6v2.feed-{_feed_code(feed_override)}."
        f"period-{_period_code(sample_period)}@1"
    )


def _parameter_set(feed_override: float, sample_period: float) -> ParameterSet:
    return ParameterSet(
        parameterSetId=_candidate_id(feed_override, sample_period),
        parameterSchemaId="optimization.r6v2.feed-and-sampling@1",
        schemaVersion=1,
        values={"feedOverride": feed_override, "samplePeriod": sample_period},
        units={"feedOverride": "ratio", "samplePeriod": "s"},
    )


def evaluate_r6v2_parameter_point(
    *,
    feed_override: float,
    sample_period: float,
    physical_model: PhysicalModelDefinition | None = None,
) -> CanonicalParameterPointEvaluation:
    """Replay the exact F3/F4/R4 protocol used to seal an R6 v2 candidate."""
    model = physical_model or build_r4_multirate_physical_model()
    feed_code = _feed_code(feed_override)
    period_code = _period_code(sample_period)
    return evaluate_canonical_parameter_point(
        model,
        feed_override=feed_override,
        sample_period=sample_period,
        profile_id=f"five-axis.r6v2.motion-profile.feed-{feed_code}@1",
        feed_source="optimization.r6v2.goal-conditioned-search@1",
        trajectory_id=f"five-axis.r6v2.m4.feed-{feed_code}-v1",
        invocation_id=(
            f"optimization.r6v2.feed-{feed_code}.period-{period_code}.invoke"
        ),
        response_trace_id=(
            f"optimization.r6v2.feed-{feed_code}.period-{period_code}.response@1"
        ),
    )


def _sample_count(duration: float, sample_period: float) -> int:
    count = math.floor((duration + 1e-12) / sample_period) + 1
    if not math.isclose(
        (count - 1) * sample_period, duration, rel_tol=0.0, abs_tol=1e-12
    ):
        count += 1
    return count


def build_r6v2_surrogate_context() -> R6V2SurrogateContext:
    scenario = load_r5c_scenario()
    payload: dict[str, Any] = {
        "contextId": "optimization.r6v2.r5c-surrogate-context@1",
        "modelBundle": scenario.model_bundle.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "trainingReceipt": scenario.training_receipt.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "parityReceipt": scenario.parity_receipt.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "datasetContentHash": scenario.dataset.content_hash,
        "splitManifestContentHash": scenario.split_manifest.content_hash,
    }
    payload["contextHash"] = canonical_hash(payload)
    return R6V2SurrogateContext.model_validate(payload)


def build_r6v2_search_request(scenario_id: str) -> R6V2SearchRequest:
    if scenario_id == "canonical-goal-conditioned-speed":
        intent: OptimizationIntentV2 = CycleTimeOptimizationIntent(
            intentId="optimization.r6v2.speed-intent@1",
            maximumLinearFollowingErrorMm=0.46,
            maximumCommandSampleCount=18,
        )
    elif scenario_id == "canonical-goal-conditioned-quality":
        intent = LinearErrorOptimizationIntent(
            intentId="optimization.r6v2.quality-intent@1",
            maximumCycleTimeSeconds=0.86,
            maximumCommandSampleCount=18,
        )
    elif scenario_id == "canonical-goal-conditioned-compact-command":
        intent = CommandCountOptimizationIntent(
            intentId="optimization.r6v2.compact-command-intent@1",
            maximumCycleTimeSeconds=0.86,
            maximumLinearFollowingErrorMm=0.49,
        )
    else:
        raise KeyError(f"unknown R6 v2 scenario: {scenario_id}")
    return R6V2SearchRequest(
        scenarioId=scenario_id,
        intent=intent,
        surrogateContext=build_r6v2_surrogate_context(),
    )


def build_r6v2_candidate_search_request(
    scenario_id: str,
    surrogate_context: R6V2CandidateSurrogateContext,
) -> R6V2CandidateSearchRequest:
    baseline = build_r6v2_search_request(scenario_id)
    payload = baseline.model_dump(mode="json", by_alias=True)
    payload["schemaId"] = "optimization.search-request@3"
    payload["surrogateContext"] = surrogate_context.model_dump(
        mode="json", by_alias=True
    )
    return R6V2CandidateSearchRequest.model_validate(payload)


def _constraint_limits(intent: OptimizationIntentV2) -> dict[str, float | int]:
    if isinstance(intent, CycleTimeOptimizationIntent):
        return {
            "linearFollowingErrorMaxMm": intent.maximum_linear_following_error_mm,
            "commandSampleCount": intent.maximum_command_sample_count,
        }
    if isinstance(intent, LinearErrorOptimizationIntent):
        return {
            "cycleTimeSeconds": intent.maximum_cycle_time_seconds,
            "commandSampleCount": intent.maximum_command_sample_count,
        }
    return {
        "cycleTimeSeconds": intent.maximum_cycle_time_seconds,
        "linearFollowingErrorMaxMm": intent.maximum_linear_following_error_mm,
    }


def _possibly_feasible(
    intent: OptimizationIntentV2,
    *,
    cycle_lower: float,
    error_lower: float,
    count_lower: int,
) -> bool:
    lower = {
        "cycleTimeSeconds": cycle_lower,
        "linearFollowingErrorMaxMm": max(0.0, error_lower),
        "commandSampleCount": count_lower,
    }
    return all(
        lower[target_id] <= limit
        for target_id, limit in _constraint_limits(intent).items()
    )


def _exact_constraints_satisfied(
    intent: OptimizationIntentV2, objectives: OptimizationObjectiveVector
) -> bool:
    exact = {
        "cycleTimeSeconds": objectives.cycle_time_seconds,
        "linearFollowingErrorMaxMm": objectives.linear_following_error_max_mm,
        "commandSampleCount": objectives.command_sample_count,
    }
    return all(
        exact[target_id] <= limit
        for target_id, limit in _constraint_limits(intent).items()
    )


def _screening_primary_value(
    intent: OptimizationIntentV2, candidate: dict[str, Any], *, lower: bool
) -> float | int:
    suffix = "Lower" if lower else "Value"
    if intent.primary_objective_id == "cycleTimeSeconds":
        return candidate[f"cycleTime{suffix}"]
    if intent.primary_objective_id == "linearFollowingErrorMaxMm":
        return candidate[f"linearError{suffix}"]
    return candidate[f"commandSampleCount{suffix}"]


def _build_screening_receipt(
    request: R6V2SearchRequest | R6V2CandidateSearchRequest,
) -> R6V2SurrogateScreeningReceipt:
    raw: list[dict[str, Any]] = []
    bundle = request.surrogate_context.model_bundle
    for feed_override in request.feed_overrides:
        for sample_period in request.sample_periods:
            prediction = predict_conditional_effect(
                ConditionalEffectPredictionRequest(
                    modelBundle=bundle,
                    feedOverride=feed_override,
                    samplePeriod=sample_period,
                )
            )
            if prediction.status != "Predicted":
                raise ValueError("frozen R6 v2 grid must remain inside the R5-C domain")
            by_target = {item.target_id: item for item in prediction.predictions}
            cycle = by_target["cycleTimeSeconds"]
            linear_error = by_target["linearFollowingErrorMaxMm"]
            count_value = _sample_count(cycle.value, sample_period)
            count_lower = _sample_count(max(0.0, cycle.lower), sample_period)
            count_upper = _sample_count(max(0.0, cycle.upper), sample_period)
            raw.append(
                {
                    "candidateId": _candidate_id(feed_override, sample_period),
                    "parameterSet": _parameter_set(
                        feed_override, sample_period
                    ).model_dump(mode="json", by_alias=True),
                    "feedOverride": feed_override,
                    "samplePeriod": sample_period,
                    "cycleTimeValue": cycle.value,
                    "cycleTimeLower": cycle.lower,
                    "cycleTimeUpper": cycle.upper,
                    "linearErrorValue": linear_error.value,
                    "linearErrorLower": linear_error.lower,
                    "linearErrorUpper": linear_error.upper,
                    "commandSampleCountValue": count_value,
                    "commandSampleCountLower": count_lower,
                    "commandSampleCountUpper": count_upper,
                    "possiblyFeasible": _possibly_feasible(
                        request.intent,
                        cycle_lower=cycle.lower,
                        error_lower=linear_error.lower,
                        count_lower=count_lower,
                    ),
                }
            )
    possible = [item for item in raw if item["possiblyFeasible"]]
    possible.sort(
        key=lambda item: (
            round(
                float(_screening_primary_value(request.intent, item, lower=True)),
                6,
            ),
            round(
                float(_screening_primary_value(request.intent, item, lower=False)),
                6,
            ),
            item["feedOverride"],
            item["samplePeriod"],
        )
    )
    rank_by_id = {item["candidateId"]: index + 1 for index, item in enumerate(possible)}
    typed: list[R6V2ScreeningCandidate] = []
    for item in raw:
        rank = rank_by_id.get(item["candidateId"])
        selected = rank is not None and rank <= request.exact_validation_budget
        reason_code = (
            None
            if selected
            else (
                "ExactValidationBudgetExceeded"
                if item["possiblyFeasible"]
                else "ConstraintLowerBoundExceeded"
            )
        )
        payload: dict[str, Any] = {
            "candidateId": item["candidateId"],
            "parameterSet": item["parameterSet"],
            "cycleTimeEstimate": {
                "targetId": "cycleTimeSeconds",
                "unit": "s",
                "value": item["cycleTimeValue"],
                "lower": item["cycleTimeLower"],
                "upper": item["cycleTimeUpper"],
            },
            "linearErrorEstimate": {
                "targetId": "linearFollowingErrorMaxMm",
                "unit": "mm",
                "value": item["linearErrorValue"],
                "lower": item["linearErrorLower"],
                "upper": item["linearErrorUpper"],
            },
            "estimatedCommandSampleCount": item["commandSampleCountValue"],
            "estimatedCommandSampleCountLower": item["commandSampleCountLower"],
            "estimatedCommandSampleCountUpper": item["commandSampleCountUpper"],
            "domainStatus": "InDomain",
            "possiblyFeasible": item["possiblyFeasible"],
            "screeningRank": rank,
            "selectedForExactValidation": selected,
        }
        if reason_code is not None:
            payload["reasonCode"] = reason_code
        payload["contentHash"] = canonical_hash(
            {key: value for key, value in payload.items() if value is not None}
        )
        typed.append(R6V2ScreeningCandidate.model_validate(payload))
    selected_ids = tuple(
        item.candidate_id
        for item in sorted(
            (item for item in typed if item.selected_for_exact_validation),
            key=lambda item: item.screening_rank or 0,
        )
    )
    candidate_context = isinstance(request, R6V2CandidateSearchRequest)
    receipt_payload: dict[str, Any] = {
        "artifactType": "axiom.optimization.surrogate-screening-receipt",
        "schemaId": "axiom.optimization.surrogate-screening-receipt@1",
        "schemaVersion": 1,
        "receiptId": (
            f"optimization.r6v2.{request.scenario_id}.candidate-impact.screening@1"
            if candidate_context
            else f"optimization.r6v2.{request.scenario_id}.screening@1"
        ),
        "searchRequestHash": canonical_hash(request),
        "surrogateContextHash": request.surrogate_context.context_hash,
        "modelBundleHash": bundle.content_hash,
        "screeningPolicyId": request.screening_policy_id,
        "candidateCount": len(typed),
        "possiblyFeasibleCount": len(possible),
        "selectedCount": len(selected_ids),
        "exactValidationBudget": request.exact_validation_budget,
        "selectedCandidateIds": list(selected_ids),
        "candidates": [
            item.model_dump(mode="json", by_alias=True, exclude_none=True)
            for item in typed
        ],
    }
    receipt_payload["contentHash"] = canonical_hash(receipt_payload)
    return R6V2SurrogateScreeningReceipt.model_validate(receipt_payload)


def _dominates(left: R6V2ExactCandidate, right: R6V2ExactCandidate) -> bool:
    left_values = (
        left.objectives.cycle_time_seconds,
        left.objectives.linear_following_error_max_mm,
        left.objectives.command_sample_count,
    )
    right_values = (
        right.objectives.cycle_time_seconds,
        right.objectives.linear_following_error_max_mm,
        right.objectives.command_sample_count,
    )
    return all(
        left_value <= right_value
        for left_value, right_value in zip(left_values, right_values, strict=True)
    ) and any(
        left_value < right_value
        for left_value, right_value in zip(left_values, right_values, strict=True)
    )


def _primary_exact_value(
    intent: OptimizationIntentV2, candidate: R6V2ExactCandidate
) -> float | int:
    if intent.primary_objective_id == "cycleTimeSeconds":
        return candidate.objectives.cycle_time_seconds
    if intent.primary_objective_id == "linearFollowingErrorMaxMm":
        return candidate.objectives.linear_following_error_max_mm
    return candidate.objectives.command_sample_count


def _exact_candidates(
    request: R6V2SearchRequest | R6V2CandidateSearchRequest,
    receipt: R6V2SurrogateScreeningReceipt,
) -> tuple[R6V2ExactCandidate, ...]:
    upstream = load_f4_scenario("canonical-head-table-solver")
    physical_model = build_r4_multirate_physical_model()
    applicability = build_r4_multirate_applicability_evidence()
    r5a_bundle = load_r5_scenario().model_bundle
    upstream_gates = {
        item.claim_id: item
        for item in upstream.stageAcceptanceReport.gate_claim_statuses
    }
    screening_by_id = {item.candidate_id: item for item in receipt.candidates}
    provisional: list[R6V2ExactCandidate] = []
    for candidate_id in receipt.selected_candidate_ids:
        screening = screening_by_id[candidate_id]
        feed_override = float(screening.parameter_set.values["feedOverride"])
        sample_period = float(screening.parameter_set.values["samplePeriod"])
        point = evaluate_r6v2_parameter_point(
            feed_override=feed_override,
            sample_period=sample_period,
            physical_model=physical_model,
        )
        objectives = OptimizationObjectiveVector(
            cycleTimeSeconds=point.continuous_verification.total_duration_seconds,
            linearFollowingErrorMaxMm=point.linear_following_error_max_mm,
            commandSampleCount=len(point.command.samples),
        )
        gate_statuses = {
            claim_id: _gate_claim_status(upstream_gates[claim_id].status)
            for claim_id in R6_GATE_IDS[:4]
        }
        gate_statuses[R6_GATE_IDS[4]] = _gate_claim_status(
            point.continuous_verification.overall_status
        )
        gate_statuses[R6_GATE_IDS[5]] = _gate_claim_status(
            point.interval_verification.status
        )
        gate_statuses[R6_GATE_IDS[6]] = _gate_claim_status(
            point.collision_verification.status
        )
        evidence_hashes = {
            claim_id: canonical_hash(upstream_gates[claim_id])
            for claim_id in R6_GATE_IDS[:4]
        }
        evidence_hashes[R6_GATE_IDS[4]] = canonical_hash(point.continuous_verification)
        evidence_hashes[R6_GATE_IDS[5]] = canonical_hash(point.interval_verification)
        evidence_hashes[R6_GATE_IDS[6]] = canonical_hash(point.collision_verification)
        gate_receipts = [
            {
                "claimId": claim_id,
                "status": gate_statuses[claim_id],
                "evidenceContentHash": evidence_hashes[claim_id],
                "method": (
                    "optimization.r6v2.inherited-f4-gate@1"
                    if index < 4
                    else "optimization.r6v2.exact-replay@1"
                ),
            }
            for index, claim_id in enumerate(R6_GATE_IDS)
        ]
        hard = applicability.status == "Passed" and all(
            item["status"] == "Supported" for item in gate_receipts
        )
        exact_constraints = _exact_constraints_satisfied(request.intent, objectives)
        ood_fraction = _ood_fraction(r5a_bundle, point.command, point.response)
        ranking_source = (
            "R5-E candidate"
            if isinstance(request, R6V2CandidateSearchRequest)
            else "R5-C"
        )
        payload: dict[str, Any] = {
            "candidateId": candidate_id,
            "parameterSet": screening.parameter_set.model_dump(
                mode="json", by_alias=True
            ),
            "screeningEstimateContentHash": screening.content_hash,
            "screeningPossiblyFeasible": True,
            "screeningRank": screening.screening_rank,
            "objectives": objectives.model_dump(mode="json", by_alias=True),
            "gateReceipts": gate_receipts,
            "physicalApplicabilityPassed": applicability.status == "Passed",
            "hardConstraintsSatisfied": hard,
            "exactConstraintsSatisfied": exact_constraints,
            "recommendationEligible": hard and exact_constraints,
            "paretoOptimalWithinValidated": False,
            "bestObserved": False,
            "m4ContentHash": canonical_hash(point.continuous_trajectory),
            "m5ContentHash": point.command.content_id,
            "physicalResponseContentHash": point.response.content_hash,
            "r5aModelBundleHash": r5a_bundle.content_hash,
            "oodFraction": ood_fraction,
            "epistemicStatus": (
                "InDomain" if ood_fraction == 0.0 else "PartiallyOutOfDomain"
            ),
            "cycleTimePredictionAbsoluteError": abs(
                objectives.cycle_time_seconds - screening.cycle_time_estimate.value
            ),
            "linearErrorPredictionAbsoluteError": abs(
                objectives.linear_following_error_max_mm
                - screening.linear_error_estimate.value
            ),
            "permissionLevel": "Offline",
            "deviceWriteAllowed": False,
            "promotionEligible": False,
            "explanation": (
                f"{ranking_source} ranked this candidate {screening.screening_rank}; "
                "exact F3/F4/R4 "
                f"replay {'satisfied' if exact_constraints else 'did not satisfy'} the "
                "declared epsilon constraints. Reality validation remains Open."
            ),
        }
        payload["contentHash"] = canonical_hash(payload)
        provisional.append(R6V2ExactCandidate.model_validate(payload))

    eligible = [item for item in provisional if item.recommendation_eligible]
    pareto_ids = {
        item.candidate_id
        for item in eligible
        if not any(_dominates(other, item) for other in eligible if other is not item)
    }
    if eligible:
        best_value = min(
            _primary_exact_value(request.intent, item) for item in eligible
        )
        best_ids = {
            item.candidate_id
            for item in eligible
            if _primary_exact_value(request.intent, item) == best_value
        }
    else:
        best_ids = set()
    sealed: list[R6V2ExactCandidate] = []
    for item in provisional:
        payload = item.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"}
        )
        payload["paretoOptimalWithinValidated"] = item.candidate_id in pareto_ids
        payload["bestObserved"] = item.candidate_id in best_ids
        payload["contentHash"] = canonical_hash(payload)
        sealed.append(R6V2ExactCandidate.model_validate(payload))
    return tuple(sealed)


def search_r6v2_recommendations(
    request: R6V2SearchRequest | R6V2CandidateSearchRequest,
) -> RecommendationSetV2 | RecommendationSetV3:
    screening = _build_screening_receipt(request)
    exact = _exact_candidates(request, screening)
    eligible_ids = tuple(
        item.candidate_id for item in exact if item.recommendation_eligible
    )
    pareto_ids = tuple(
        item.candidate_id for item in exact if item.pareto_optimal_within_validated
    )
    best_ids = tuple(item.candidate_id for item in exact if item.best_observed)
    applicability = build_r4_multirate_applicability_evidence()
    baseline = _parameter_set(1.0, 0.08)
    candidate_context = isinstance(request, R6V2CandidateSearchRequest)
    validation_plan = R6V2ValidationPlan(
        planId="optimization.r6v2.offline-validation-plan@1",
        permissionLevel="Offline",
        optimalityScope="best-observed-within-exact-validation-budget",
        remainingGates=(
            "independent-real-device-holdout",
            "deployment-shadow-without-write",
            "controlled-trial-approval",
            "r7-device-stop-and-rollback-evidence",
        ),
        stopConditions=(
            (
                "R5-E candidate surrogate identity, parity, or domain status changes"
                if candidate_context
                else "R5-C surrogate identity, parity, or domain status changes"
            ),
            "any exact mathematical or physical gate becomes non-Supported",
            "exact objectives violate the declared epsilon constraints",
            "clock, coordinate, calibration, lineage, or reality evidence is incomplete",
        ),
        rollbackParameterSetId=baseline.parameter_set_id,
        deviceWriteAllowed=False,
    )
    payload: dict[str, Any] = {
        "artifactType": "axiom.optimization.recommendation-set",
        "schemaId": (
            "axiom.optimization.recommendation-set@3"
            if candidate_context
            else "axiom.optimization.recommendation-set@2"
        ),
        "schemaVersion": 3 if candidate_context else 2,
        "recommendationSetId": (
            f"axiom.optimization.r6v2.{request.scenario_id}.candidate-impact@1"
            if candidate_context
            else f"axiom.optimization.r6v2.{request.scenario_id}@1"
        ),
        "searchRequest": request.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "surrogateContextHash": request.surrogate_context.context_hash,
        "screeningReceipt": screening.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "exactCandidates": [
            item.model_dump(mode="json", by_alias=True, exclude_none=True)
            for item in exact
        ],
        "exactFeasibleCandidateIds": list(eligible_ids),
        "paretoCandidateIds": list(pareto_ids),
        "bestObservedCandidateIds": list(best_ids),
        "physicalApplicabilityEvidence": applicability.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "validationPlan": validation_plan.model_dump(mode="json", by_alias=True),
        "screeningCandidateCount": 135,
        "exactValidationBudget": R6V2_EXACT_VALIDATION_BUDGET,
        "optimalityScope": "best-observed-within-exact-validation-budget",
        "globalOptimalityStatus": "NotClaimed",
        "permissionLevel": "Offline",
        "deviceWriteAllowed": False,
        "automaticAcceptanceAllowed": False,
        "shadowStatus": "Open",
        "realityValidationStatus": "Open",
    }
    payload["contentHash"] = canonical_hash(payload)
    model_type = RecommendationSetV3 if candidate_context else RecommendationSetV2
    return model_type.model_validate(payload)


__all__ = [
    "build_r6v2_candidate_search_request",
    "build_r6v2_search_request",
    "build_r6v2_surrogate_context",
    "search_r6v2_recommendations",
]
