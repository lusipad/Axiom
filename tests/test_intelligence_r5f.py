from __future__ import annotations

from copy import deepcopy
import platform

import pytest
from pydantic import ValidationError

from axiom.intelligence import (
    R5FCandidateImpactReport,
    R5ESyntheticCampaignReport,
    assess_r5f_candidate_downstream_impact,
    build_r5e_campaign_request,
    build_r5f_manifest,
    execute_r5e_synthetic_campaign,
    load_r5f_fixture_manifest,
)
from axiom.intelligence.models import canonical_hash
from axiom.optimization import R6V2CandidateSurrogateContext


@pytest.fixture(scope="module")
def campaign_report() -> R5ESyntheticCampaignReport:
    request = build_r5e_campaign_request(accountable_party_id="fixture-reviewer")
    return execute_r5e_synthetic_campaign(request, current_platform="Windows")


@pytest.fixture(scope="module")
def impact_report(
    campaign_report: R5ESyntheticCampaignReport,
) -> R5FCandidateImpactReport:
    return assess_r5f_candidate_downstream_impact(
        campaign_report, current_platform="Windows"
    )


def _reseal(payload: dict[str, object]) -> None:
    payload.pop("contentHash", None)
    payload["contentHash"] = canonical_hash(payload)


def test_manifest_freezes_offline_evaluation_without_promotion() -> None:
    manifest = build_r5f_manifest()

    assert manifest.stage == "R5-F"
    assert manifest.platform == "windows"
    assert manifest.scenario_ids == (
        "canonical-goal-conditioned-speed",
        "canonical-goal-conditioned-quality",
        "canonical-goal-conditioned-compact-command",
    )
    assert manifest.screening_candidate_count == 135
    assert manifest.exact_validation_budget == 27
    assert manifest.candidate_use_status == "EvaluatedOnly"
    assert manifest.automatic_model_promotion_allowed is False
    assert manifest.device_write_allowed is False


def test_candidate_is_compared_under_the_same_three_exact_searches(
    campaign_report: R5ESyntheticCampaignReport,
    impact_report: R5FCandidateImpactReport,
) -> None:
    assert impact_report.source_campaign_report == campaign_report
    assert impact_report.impact_gate_status == "Passed"
    assert impact_report.candidate_use_status == "EvaluatedOnly"
    assert impact_report.model_promotion_status == "NotPerformed"
    assert impact_report.real_world_generalization_status == "Open"
    assert impact_report.permission_level == "Offline"
    assert impact_report.device_write_allowed is False
    assert tuple(item.scenario_id for item in impact_report.scenario_impacts) == (
        "canonical-goal-conditioned-speed",
        "canonical-goal-conditioned-quality",
        "canonical-goal-conditioned-compact-command",
    )

    for item in impact_report.scenario_impacts:
        baseline = item.baseline_recommendation
        candidate = item.candidate_recommendation
        assert baseline.search_request.scenario_id == item.scenario_id
        assert candidate.search_request.scenario_id == item.scenario_id
        assert baseline.search_request.intent == candidate.search_request.intent
        assert baseline.screening_candidate_count == 135
        assert candidate.screening_candidate_count == 135
        assert baseline.screening_receipt.selected_count == 27
        assert candidate.screening_receipt.selected_count == 27
        assert len(baseline.exact_candidates) == 27
        assert len(candidate.exact_candidates) == 27
        assert baseline.search_request.surrogate_context.context_id.endswith("@1")
        assert isinstance(
            candidate.search_request.surrogate_context,
            R6V2CandidateSurrogateContext,
        )
        assert item.selected_candidate_overlap_count == 27
        assert item.baseline_only_selected_candidate_ids == ()
        assert item.candidate_only_selected_candidate_ids == ()
        assert item.primary_objective_status == "NoRegression"
        assert item.candidate_best_value == pytest.approx(item.baseline_best_value)
        assert len(item.shared_prediction_error_deltas) == 2

    assert tuple(
        item.screening_order_changed for item in impact_report.scenario_impacts
    ) == (True, True, False)


def test_candidate_context_binds_the_complete_r5e_candidate_lineage(
    impact_report: R5FCandidateImpactReport,
) -> None:
    context = impact_report.scenario_impacts[
        0
    ].candidate_recommendation.search_request.surrogate_context
    assert isinstance(context, R6V2CandidateSurrogateContext)
    assert context.source_campaign_report_hash == impact_report.source_campaign_report.content_hash
    assert context.candidate_assessment.content_hash == (
        impact_report.source_campaign_report.candidate_assessment.content_hash
    )

    raw = deepcopy(context.model_dump(mode="json", by_alias=True))
    raw["candidateAssessment"]["sourceModelBundleHash"] = "0" * 64
    _reseal(raw["candidateAssessment"])
    raw.pop("contextHash")
    raw["contextHash"] = canonical_hash(raw)

    with pytest.raises(ValidationError, match="parent model"):
        R6V2CandidateSurrogateContext.model_validate(raw)


def test_impact_report_rejects_resealed_derived_state(
    impact_report: R5FCandidateImpactReport,
) -> None:
    raw = deepcopy(impact_report.model_dump(mode="json", by_alias=True))
    raw["scenarioImpacts"][0]["screeningOrderChanged"] = False
    _reseal(raw["scenarioImpacts"][0])
    _reseal(raw)

    with pytest.raises(ValidationError, match="screeningOrderChanged"):
        R5FCandidateImpactReport.model_validate(raw)


def test_non_windows_fails_before_any_downstream_search(
    campaign_report: R5ESyntheticCampaignReport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_search(_request: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("downstream search must not run")

    monkeypatch.setattr(
        "axiom.intelligence.r5f_impact.search_r6v2_recommendations",
        forbidden_search,
    )
    with pytest.raises(ValueError, match="only supports Windows"):
        assess_r5f_candidate_downstream_impact(
            campaign_report, current_platform="Linux"
        )
    assert called is False


def test_impact_report_round_trips_without_upgrading_safety_claims(
    impact_report: R5FCandidateImpactReport,
) -> None:
    payload = impact_report.model_dump(mode="json", by_alias=True)
    assert R5FCandidateImpactReport.model_validate(payload) == impact_report
    assert "DeviceSafe" not in str(payload)
    assert "ProcessSafe" not in str(payload)
    assert "safe-to-run" not in str(payload)


def _fixture_identities(report: R5FCandidateImpactReport) -> dict[str, object]:
    candidate_context = report.scenario_impacts[
        0
    ].candidate_recommendation.search_request.surrogate_context
    return {
        "campaignReportContentHash": report.source_campaign_report.content_hash,
        "candidateContextHash": candidate_context.context_hash,
        "scenarioImpacts": {
            item.scenario_id: {
                "candidateRecommendationContentHash": item.candidate_recommendation.content_hash,
                "scenarioImpactContentHash": item.content_hash,
                "screeningOrderChanged": item.screening_order_changed,
                "selectedCandidateOverlapCount": item.selected_candidate_overlap_count,
                "baselineBestValue": item.baseline_best_value,
                "candidateBestValue": item.candidate_best_value,
            }
            for item in report.scenario_impacts
        },
        "reportContentHash": report.content_hash,
    }


def test_development_fixture_freezes_candidate_impact_lineage(
    impact_report: R5FCandidateImpactReport,
) -> None:
    if platform.python_version() != "3.14.3":
        pytest.skip("development golden requires CPython 3.14.3")
    fixture = load_r5f_fixture_manifest()
    assert _fixture_identities(impact_report) == fixture[
        "developmentExpectedIdentities"
    ]
    assert fixture["boundary"] == impact_report.safety_banner


def test_windows_release_fixture_freezes_candidate_impact_lineage(
    impact_report: R5FCandidateImpactReport,
) -> None:
    if platform.python_version() != "3.12.10":
        pytest.skip("release golden requires CPython 3.12.10")
    fixture = load_r5f_fixture_manifest()
    assert _fixture_identities(impact_report) == fixture[
        "windowsReleaseExpectedIdentities"
    ]
