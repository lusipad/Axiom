from __future__ import annotations

import json
import os

import pytest
from pydantic import ValidationError

from axiom import evaluate_run
from axiom.models import RunSpec
from axiom.optimization import (
    CommandCountOptimizationIntent,
    CycleTimeOptimizationIntent,
    LinearErrorOptimizationIntent,
    RecommendationSetV2,
    build_r6v2_manifest,
    load_r6v2_scenario,
    load_r6v2_fixture_manifest,
    search_r6v2_recommendations,
    validate_r6v2_example_run_spec,
)


def test_r6v2_intents_require_one_primary_and_both_secondary_limits() -> None:
    with pytest.raises(ValidationError):
        CycleTimeOptimizationIntent.model_validate(
            {
                "primaryObjectiveId": "cycleTimeSeconds",
                "maximumLinearFollowingErrorMm": 0.46,
            }
        )
    with pytest.raises(ValidationError):
        LinearErrorOptimizationIntent.model_validate(
            {
                "primaryObjectiveId": "cycleTimeSeconds",
                "maximumCycleTimeSeconds": 0.86,
                "maximumCommandSampleCount": 18,
            }
        )
    with pytest.raises(ValidationError):
        CommandCountOptimizationIntent.model_validate(
            {
                "primaryObjectiveId": "commandSampleCount",
                "maximumCycleTimeSeconds": 0.86,
                "maximumLinearFollowingErrorMm": float("nan"),
            }
        )


@pytest.mark.parametrize(
    ("scenario_id", "primary_id", "expected_value", "expected_parameters"),
    [
        (
            "canonical-goal-conditioned-speed",
            "cycleTimeSeconds",
            0.8230326497988096,
            (
                {"feedOverride": 0.825, "samplePeriod": 0.05},
                {"feedOverride": 0.825, "samplePeriod": 0.055},
            ),
        ),
        (
            "canonical-goal-conditioned-quality",
            "linearFollowingErrorMaxMm",
            0.43596512868787585,
            ({"feedOverride": 0.8, "samplePeriod": 0.05},),
        ),
        (
            "canonical-goal-conditioned-compact-command",
            "commandSampleCount",
            12,
            ({"feedOverride": 0.8, "samplePeriod": 0.08},),
        ),
    ],
)
def test_r6v2_canonical_intents_recover_full_oracle_best_with_27_exact_replays(
    scenario_id: str,
    primary_id: str,
    expected_value: float,
    expected_parameters: tuple[dict[str, float], ...],
) -> None:
    scenario = load_r6v2_scenario(scenario_id)
    recommendations = scenario.recommendation_set

    assert recommendations.screening_receipt.candidate_count == 135
    assert recommendations.screening_receipt.selected_count <= 27
    assert len(recommendations.exact_candidates) <= 27
    assert recommendations.global_optimality_status == "NotClaimed"
    assert (
        recommendations.optimality_scope
        == "best-observed-within-exact-validation-budget"
    )
    assert recommendations.permission_level == "Offline"
    assert recommendations.device_write_allowed is False

    best = [
        candidate
        for candidate in recommendations.exact_candidates
        if candidate.candidate_id in recommendations.best_observed_candidate_ids
    ]
    assert best
    assert {candidate.parameter_set.values["feedOverride"] for candidate in best} == {
        item["feedOverride"] for item in expected_parameters
    }
    assert (
        tuple(candidate.parameter_set.values for candidate in best)
        == expected_parameters
    )
    assert all(
        getattr(candidate.objectives, _objective_attribute(primary_id))
        == pytest.approx(expected_value)
        for candidate in best
    )


def _objective_attribute(primary_id: str) -> str:
    return {
        "cycleTimeSeconds": "cycle_time_seconds",
        "linearFollowingErrorMaxMm": "linear_following_error_max_mm",
        "commandSampleCount": "command_sample_count",
    }[primary_id]


def test_r6v2_surrogate_possible_feasibility_never_upgrades_exact_failure() -> None:
    recommendations = load_r6v2_scenario(
        "canonical-goal-conditioned-speed"
    ).recommendation_set

    rejected = [
        candidate
        for candidate in recommendations.exact_candidates
        if not candidate.exact_constraints_satisfied
    ]
    assert rejected
    assert all(candidate.screening_possibly_feasible for candidate in rejected)
    assert all(not candidate.recommendation_eligible for candidate in rejected)
    assert all(
        candidate.candidate_id not in recommendations.exact_feasible_candidate_ids
        for candidate in rejected
    )


def test_r6v2_search_is_deterministic_and_serializes_no_global_or_device_claim() -> (
    None
):
    scenario = load_r6v2_scenario("canonical-goal-conditioned-quality")

    replay = search_r6v2_recommendations(scenario.search_request)

    assert replay == scenario.recommendation_set
    serialized = json.dumps(
        replay.model_dump(mode="json", by_alias=True), sort_keys=True
    )
    assert "global-optimum" not in serialized.lower()
    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_r6v2_models_reject_content_tampering() -> None:
    scenario = load_r6v2_scenario("canonical-goal-conditioned-quality")
    payload = scenario.recommendation_set.model_dump(mode="json", by_alias=True)
    payload["exactCandidates"][0]["objectives"]["linearFollowingErrorMaxMm"] += 1.0

    with pytest.raises(ValidationError, match="contentHash"):
        RecommendationSetV2.model_validate(payload)


def test_r6v2_public_run_replays_same_artifact_and_keeps_reality_open() -> None:
    run_spec = validate_r6v2_example_run_spec(
        "canonical-goal-conditioned-compact-command"
    )
    bundle = evaluate_run(run_spec)
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Passed"
    assert claims["optimization.surrogate-screening-contract-claim@1"] == "Supported"
    assert claims["optimization.exact-recommendation-integrity-claim@2"] == "Supported"
    assert claims["optimization.offline-permission-boundary-claim@2"] == "Supported"
    assert claims["optimization.reality-validation-claim@2"] == "Inconclusive"


def test_r6v2_public_run_rejects_tampered_nested_screening_receipt() -> None:
    payload = validate_r6v2_example_run_spec().model_dump(mode="json", by_alias=True)
    payload["request"]["artifact"]["screeningReceipt"]["candidates"][0][
        "estimatedCommandSampleCount"
    ] += 1

    bundle = evaluate_run(RunSpec.model_validate(payload))

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Invalid"


def test_r6v2_manifest_is_versioned_without_mutating_r6v1() -> None:
    manifest = build_r6v2_manifest()

    assert manifest.domain_pack_id == "optimization.domain-pack@2"
    assert manifest.schema_version == 2
    assert manifest.screening_candidate_count == 135
    assert manifest.exact_validation_budget == 27
    assert manifest.global_optimality_status == "NotClaimed"
    assert manifest.device_write_allowed is False


def test_packaged_r6v2_fixture_freezes_environment_bound_search_identities() -> None:
    fixture = load_r6v2_fixture_manifest()
    profile = (
        fixture["windowsRelease"]
        if os.getenv("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1"
        else fixture
    )

    assert fixture["platform"] == "windows"
    assert fixture["screeningCandidateCount"] == 135
    assert fixture["exactValidationBudget"] == 27
    for scenario_id, expected in profile["scenarios"].items():
        scenario = load_r6v2_scenario(scenario_id)
        recommendations = scenario.recommendation_set
        assert profile["surrogateContextHash"] == (
            recommendations.surrogate_context_hash
        )
        assert expected == {
            "searchRequestHash": recommendations.screening_receipt.search_request_hash,
            "screeningReceiptContentHash": recommendations.screening_receipt.content_hash,
            "recommendationSetContentHash": recommendations.content_hash,
            "bestObservedCandidateIds": list(
                recommendations.best_observed_candidate_ids
            ),
        }
