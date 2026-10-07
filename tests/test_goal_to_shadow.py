from __future__ import annotations

import json
import os

import pytest
from pydantic import ValidationError

from axiom.control import (
    GoalToShadowProjectionError,
    GoalToShadowRequest,
    PhysicalShadowProjection,
    build_physical_shadow_projection,
    rehearse_goal_to_shadow,
)
from axiom.optimization import (
    build_r6v2_search_request,
    evaluate_r6v2_parameter_point,
    load_r6v2_scenario,
)


@pytest.fixture(scope="module")
def goal_request() -> GoalToShadowRequest:
    return GoalToShadowRequest(
        searchRequest=build_r6v2_search_request("canonical-goal-conditioned-speed")
    )


@pytest.fixture(scope="module")
def default_report(goal_request: GoalToShadowRequest):
    return rehearse_goal_to_shadow(goal_request, current_platform="Windows")


def test_goal_to_shadow_replays_the_selected_exact_physical_response(
    default_report,
) -> None:
    report = default_report
    recommendation = report.recommendation_set
    projection = report.physical_shadow_projection
    runtime = report.runtime_audit

    assert report.status == "Passed"
    assert recommendation is not None
    assert projection is not None
    assert runtime is not None
    assert report.selected_candidate_id == recommendation.best_observed_candidate_ids[0]
    candidate = next(
        item
        for item in recommendation.exact_candidates
        if item.candidate_id == report.selected_candidate_id
    )
    assert projection.candidate_content_hash == candidate.content_hash
    assert projection.candidate_m4_content_hash == candidate.m4_content_hash
    assert projection.source_m5_content_hash == candidate.m5_content_hash
    assert (
        projection.source_physical_response_content_hash
        == candidate.physical_response_content_hash
    )
    assert projection.sample_count == candidate.objectives.command_sample_count == 18
    assert projection.interpolation_applied is False
    assert projection.linear_axis_ids == ("X", "Y", "Z")
    assert projection.linear_axis_unit == "mm"
    assert projection.excluded_rotary_axis_ids == ("B", "C")
    assert projection.source_kind == "synthetic-sil"
    assert runtime.final_state == "Completed"
    assert runtime.device_write_performed is False
    release_environment = os.getenv("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1"
    assert projection.content_hash == (
        "3adaeb17223558f3fa1cd2b41bc4dfc6086fc0087206f4140316e656d0a581eb"
        if release_environment
        else "a8b7c70578c6f76455393afd1a95d8b490119db4fe1b9b7f5336aaceb493b314"
    )
    assert projection.shadow_trace.content_hash == (
        "4b7ddeabde2f2978164470315395acd9b67f1bb039d8533e991652944dbd9765"
    )
    assert runtime.content_hash == (
        "002bcf9a812c15e3df9545678e8957f86af83db8f1a5d5441be5e4e7d63b6727"
        if release_environment
        else "0e3b43edf52cfef7e942a8f0d80de7b85fd447381b8f2e0afddcca2fe284751a"
    )
    assert report.content_hash == (
        "746f283dba4d508cc784df5e7805a3d6d00bc58d26ecc3e03261782d7a14f467"
        if release_environment
        else "716385d0ac9c31a1d0ca5243cf5e636e5cd81087a2f0b0618e29a429000217c6"
    )


def test_goal_to_shadow_uses_only_xyz_for_each_linear_error_sample(
    default_report,
) -> None:
    projection = default_report.physical_shadow_projection
    assert projection is not None

    derived = []
    for response, shadow in zip(
        projection.physical_response.samples,
        projection.shadow_trace.samples,
        strict=True,
    ):
        error = max(
            abs(response.command[index] - response.simulated[index])
            for index in range(3)
        )
        derived.append(error)
        assert shadow.sequence == response.sample_index
        assert shadow.time_seconds == response.t
        assert shadow.linear_following_error_mm == pytest.approx(error, abs=1e-12)
        assert shadow.ood_fraction == projection.candidate_ood_fraction

    assert projection.maximum_linear_following_error_mm == pytest.approx(max(derived))


def test_goal_to_shadow_replay_is_deterministic_within_numeric_environment(
    goal_request: GoalToShadowRequest,
    default_report,
) -> None:
    replay = rehearse_goal_to_shadow(goal_request, current_platform="Windows")

    assert replay.content_hash == default_report.content_hash
    assert (
        replay.physical_shadow_projection.content_hash
        == default_report.physical_shadow_projection.content_hash
    )
    assert (
        replay.runtime_audit.content_hash == default_report.runtime_audit.content_hash
    )


def test_goal_to_shadow_allows_explicit_non_best_exact_eligible_candidate(
    goal_request: GoalToShadowRequest,
) -> None:
    recommendation = load_r6v2_scenario().recommendation_set
    candidate_id = next(
        item.candidate_id
        for item in recommendation.exact_candidates
        if item.recommendation_eligible and not item.best_observed
    )
    report = rehearse_goal_to_shadow(
        goal_request.model_copy(update={"candidate_id": candidate_id}),
        current_platform="Windows",
    )

    assert report.status == "Passed"
    assert report.selected_candidate_id == candidate_id
    assert report.recommendation_projection.selection_class in {
        "ParetoWithinValidated",
        "ExactEligible",
    }
    assert report.runtime_audit.acceptance_record.automatic is False


def test_goal_to_shadow_blocks_ineligible_and_missing_candidates(
    goal_request: GoalToShadowRequest,
) -> None:
    recommendation = load_r6v2_scenario().recommendation_set
    ineligible_id = next(
        item.candidate_id
        for item in recommendation.exact_candidates
        if not item.recommendation_eligible
    )

    ineligible = rehearse_goal_to_shadow(
        goal_request.model_copy(update={"candidate_id": ineligible_id}),
        current_platform="Windows",
    )
    missing = rehearse_goal_to_shadow(
        goal_request.model_copy(
            update={"candidate_id": "optimization.r6v2.not-validated@1"}
        ),
        current_platform="Windows",
    )

    assert ineligible.status == "Blocked"
    assert ineligible.reason_codes == ("ExactCandidateIneligible",)
    assert ineligible.physical_shadow_projection is None
    assert ineligible.runtime_audit is None
    assert missing.status == "Blocked"
    assert missing.reason_codes == ("ExactCandidateMissing",)
    assert missing.runtime_audit is None


def test_goal_to_shadow_rejects_cross_candidate_physical_replay() -> None:
    recommendation = load_r6v2_scenario().recommendation_set
    left, right = recommendation.exact_candidates[:2]
    wrong_point = evaluate_r6v2_parameter_point(
        feed_override=float(right.parameter_set.values["feedOverride"]),
        sample_period=float(right.parameter_set.values["samplePeriod"]),
    )

    with pytest.raises(GoalToShadowProjectionError) as caught:
        build_physical_shadow_projection(recommendation, left, wrong_point)

    assert caught.value.reason_code in {
        "ExactReplayM4IdentityMismatch",
        "ExactReplayM5IdentityMismatch",
        "ExactReplayPhysicalResponseIdentityMismatch",
    }


def test_goal_to_shadow_projection_rejects_trace_tampering(default_report) -> None:
    projection = default_report.physical_shadow_projection
    assert projection is not None
    raw = projection.model_dump(mode="json", by_alias=True)
    raw["shadowTrace"]["samples"][0]["linearFollowingErrorMm"] += 0.01

    with pytest.raises(ValidationError):
        PhysicalShadowProjection.model_validate(raw)


def test_goal_to_shadow_non_windows_is_structurally_blocked(
    goal_request: GoalToShadowRequest,
) -> None:
    report = rehearse_goal_to_shadow(goal_request, current_platform="Linux")

    assert report.status == "Blocked"
    assert report.reason_codes == ("UnsupportedRuntimePlatform",)
    assert report.recommendation_set is None
    assert report.runtime_audit is None


def test_goal_to_shadow_never_claims_reality_or_device_safety(default_report) -> None:
    serialized = json.dumps(
        default_report.model_dump(mode="json", by_alias=True), sort_keys=True
    )

    assert default_report.deployment_shadow_status == "Open"
    assert default_report.reality_validation_status == "Open"
    assert default_report.controlled_trial_status == "Open"
    assert default_report.closed_loop_status == "Open"
    assert default_report.device_safety_status == "NotAssessed"
    assert default_report.process_safety_status == "NotAssessed"
    assert default_report.device_write_allowed is False
    assert default_report.automatic_acceptance_allowed is False
    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized
