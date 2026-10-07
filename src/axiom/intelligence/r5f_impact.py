from __future__ import annotations

import math
import platform
import json
from importlib.resources import files
from typing import Any

from ..optimization import (
    R6V2_SCENARIO_IDS,
    R6V2CandidateSurrogateContext,
    RecommendationSetV2,
    RecommendationSetV3,
    build_r6v2_candidate_search_request,
    load_r6v2_scenario,
    search_r6v2_recommendations,
)
from .models import canonical_hash
from .r5e_campaign import execute_r5e_synthetic_campaign
from .r5e_models import R5ESyntheticCampaignReport
from .r5f_models import (
    R5F_SAFETY_BANNER,
    R5FCandidateImpactReport,
    R5FManifest,
    R5FScenarioImpact,
)


def _seal(model_type: type[Any], payload: dict[str, Any]) -> Any:
    payload["contentHash"] = canonical_hash(payload)
    return model_type.model_validate(payload)


def build_r5f_manifest() -> R5FManifest:
    return R5FManifest(
        manifestId="axiom.intelligence.r5f-manifest@1",
        schemaId="axiom.intelligence.r5f-manifest@1",
        schemaVersion=1,
        stage="R5-F",
        platform="windows",
        baselineContextId="optimization.r6v2.r5c-surrogate-context@1",
        candidateContextId="optimization.r6v2.r5e-candidate-surrogate-context@2",
        scenarioIds=R6V2_SCENARIO_IDS,
        screeningCandidateCount=135,
        exactValidationBudget=27,
        candidateUseStatus="EvaluatedOnly",
        automaticModelPromotionAllowed=False,
        realWorldGeneralizationStatus="Open",
        permissionLevel="Offline",
        deviceWriteAllowed=False,
        safetyBanner=R5F_SAFETY_BANNER,
    )


def _candidate_context(
    campaign: R5ESyntheticCampaignReport,
) -> R6V2CandidateSurrogateContext:
    payload = {
        "contextId": "optimization.r6v2.r5e-candidate-surrogate-context@2",
        "modelBundle": campaign.model_bundle.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "trainingReceipt": campaign.training_receipt.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "parityReceipt": campaign.parity_receipt.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "candidateAssessment": campaign.candidate_assessment.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "datasetContentHash": campaign.dataset.content_hash,
        "splitManifestContentHash": campaign.split_manifest.content_hash,
        "sourceCampaignReportHash": campaign.content_hash,
    }
    payload["contextHash"] = canonical_hash(payload)
    return R6V2CandidateSurrogateContext.model_validate(payload)


def _primary_value(recommendation: RecommendationSetV2) -> float | int | None:
    candidates = {
        item.candidate_id: item for item in recommendation.exact_candidates
    }
    best = [
        candidates[item]
        for item in recommendation.best_observed_candidate_ids
        if item in candidates
    ]
    if not best:
        return None
    primary = recommendation.search_request.intent.primary_objective_id
    if primary == "cycleTimeSeconds":
        return min(item.objectives.cycle_time_seconds for item in best)
    if primary == "linearFollowingErrorMaxMm":
        return min(item.objectives.linear_following_error_max_mm for item in best)
    return min(item.objectives.command_sample_count for item in best)


def _prediction_delta_payloads(
    baseline: RecommendationSetV2,
    candidate: RecommendationSetV3,
) -> list[dict[str, Any]]:
    baseline_by_id = {item.candidate_id: item for item in baseline.exact_candidates}
    candidate_by_id = {
        item.candidate_id: item for item in candidate.exact_candidates
    }
    shared_ids = tuple(
        item
        for item in baseline.screening_receipt.selected_candidate_ids
        if item in candidate_by_id
    )
    if not shared_ids:
        raise ValueError("R5-F requires at least one shared exact candidate")
    payloads: list[dict[str, Any]] = []
    for target_id, unit, attribute in (
        ("cycleTimeSeconds", "s", "cycle_time_prediction_absolute_error"),
        (
            "linearFollowingErrorMaxMm",
            "mm",
            "linear_error_prediction_absolute_error",
        ),
    ):
        baseline_error = math.fsum(
            getattr(baseline_by_id[item], attribute) for item in shared_ids
        ) / len(shared_ids)
        candidate_error = math.fsum(
            getattr(candidate_by_id[item], attribute) for item in shared_ids
        ) / len(shared_ids)
        change = candidate_error - baseline_error
        payloads.append(
            {
                "targetId": target_id,
                "unit": unit,
                "sharedCandidateCount": len(shared_ids),
                "baselineMeanAbsoluteError": baseline_error,
                "candidateMeanAbsoluteError": candidate_error,
                "absoluteChange": change,
                "status": (
                    "Improved"
                    if change < -1e-15
                    else "Regressed"
                    if change > 1e-15
                    else "Unchanged"
                ),
            }
        )
    return payloads


def _scenario_impact(
    baseline: RecommendationSetV2,
    candidate: RecommendationSetV3,
) -> R5FScenarioImpact:
    baseline_ids = baseline.screening_receipt.selected_candidate_ids
    candidate_ids = candidate.screening_receipt.selected_candidate_ids
    baseline_set = set(baseline_ids)
    candidate_set = set(candidate_ids)
    baseline_best = _primary_value(baseline)
    candidate_best = _primary_value(candidate)
    primary = baseline.search_request.intent.primary_objective_id
    tolerance = 0.0 if primary == "commandSampleCount" else 1e-12
    if baseline_best is None or candidate_best is None:
        status = "Inconclusive"
    elif float(candidate_best) <= float(baseline_best) + tolerance:
        status = "NoRegression"
    else:
        status = "Regressed"
    return _seal(
        R5FScenarioImpact,
        {
            "scenarioId": baseline.search_request.scenario_id,
            "primaryObjectiveId": primary,
            "primaryObjectiveUnit": {
                "cycleTimeSeconds": "s",
                "linearFollowingErrorMaxMm": "mm",
                "commandSampleCount": "count",
            }[primary],
            "baselineRecommendation": baseline.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "candidateRecommendation": candidate.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "selectedCandidateOverlapCount": len(baseline_set & candidate_set),
            "baselineOnlySelectedCandidateIds": [
                item for item in baseline_ids if item not in candidate_set
            ],
            "candidateOnlySelectedCandidateIds": [
                item for item in candidate_ids if item not in baseline_set
            ],
            "screeningOrderChanged": baseline_ids != candidate_ids,
            "baselineBestValue": baseline_best,
            "candidateBestValue": candidate_best,
            "comparisonTolerance": tolerance,
            "primaryObjectiveStatus": status,
            "sharedPredictionErrorDeltas": _prediction_delta_payloads(
                baseline, candidate
            ),
        },
    )


def assess_r5f_candidate_downstream_impact(
    campaign_report: R5ESyntheticCampaignReport,
    *,
    current_platform: str | None = None,
) -> R5FCandidateImpactReport:
    runtime_platform = current_platform or platform.system()
    if runtime_platform.casefold() != "windows":
        raise ValueError("R5-F candidate impact assessment only supports Windows")

    replay = execute_r5e_synthetic_campaign(
        campaign_report.campaign_request,
        current_platform="Windows",
    )
    if replay.content_hash != campaign_report.content_hash:
        raise ValueError("R5-F source campaign report cannot be reproduced")
    if campaign_report.candidate_assessment.candidate_gate_status != "Passed":
        raise ValueError("R5-F requires a Passed R5-E candidate gate")

    candidate_context = _candidate_context(campaign_report)
    impacts: list[R5FScenarioImpact] = []
    for scenario_id in R6V2_SCENARIO_IDS:
        baseline = load_r6v2_scenario(scenario_id).recommendation_set
        if (
            baseline.search_request.surrogate_context.model_bundle.content_hash
            != campaign_report.candidate_assessment.source_model_bundle_hash
        ):
            raise ValueError("R5-F baseline does not match the R5-E parent model")
        candidate_request = build_r6v2_candidate_search_request(
            scenario_id, candidate_context
        )
        candidate = search_r6v2_recommendations(candidate_request)
        if not isinstance(candidate, RecommendationSetV3):
            raise AssertionError("candidate search must return RecommendationSetV3")
        impacts.append(_scenario_impact(baseline, candidate))

    gate_status = (
        "Passed"
        if all(item.primary_objective_status == "NoRegression" for item in impacts)
        else "Failed"
    )
    return _seal(
        R5FCandidateImpactReport,
        {
            "schemaId": "axiom.intelligence.candidate-downstream-impact-report@1",
            "reportId": "axiom.intelligence.r5f.candidate-impact-report@1",
            "sourceCampaignReport": campaign_report.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "scenarioImpacts": [
                item.model_dump(mode="json", by_alias=True, exclude_none=True)
                for item in impacts
            ],
            "impactGateStatus": gate_status,
            "candidateUseStatus": "EvaluatedOnly",
            "modelPromotionStatus": "NotPerformed",
            "generalImprovementGuarantee": "NotClaimed",
            "realWorldGeneralizationStatus": "Open",
            "permissionLevel": "Offline",
            "automaticAcceptanceAllowed": False,
            "deviceWriteAllowed": False,
            "safetyBanner": R5F_SAFETY_BANNER,
        },
    )


def load_r5f_fixture_manifest() -> dict[str, Any]:
    resource = files("axiom.intelligence").joinpath("fixtures", "r5f-manifest.json")
    return json.loads(resource.read_text(encoding="utf-8"))


__all__ = [
    "assess_r5f_candidate_downstream_impact",
    "build_r5f_manifest",
    "load_r5f_fixture_manifest",
]
