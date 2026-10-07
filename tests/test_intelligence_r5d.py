from __future__ import annotations

import json
import os

import numpy as np
import pytest
from pydantic import ValidationError

from axiom.intelligence import (
    R5D_CANDIDATE_FEED_OVERRIDES,
    R5D_CANDIDATE_SAMPLE_PERIODS,
    R5DExperimentPlanRequest,
    build_r5d_experiment_plan_request,
    build_r5d_manifest,
    load_r5c_scenario,
    load_r5d_fixture_manifest,
    plan_r5d_simulation_experiments,
    r5d_example_payload,
)
from axiom.intelligence.models import canonical_hash
from axiom.intelligence.r5c_interpreter import conditional_effect_feature_vector
from axiom.intelligence.r5c_training import RIDGE_LAMBDA


def test_r5d_default_plan_reduces_maximum_design_leverage_deterministically() -> None:
    request = build_r5d_experiment_plan_request()

    first = plan_r5d_simulation_experiments(request, current_platform="Windows")
    second = plan_r5d_simulation_experiments(request, current_platform="Windows")

    assert first == second
    assert first.status == "Planned"
    assert first.candidate_pool_size == 135
    assert first.available_candidate_count == 110
    assert first.design_sample_count == 15
    assert first.excluded_observed_point_count == 25
    assert first.requested_batch_size == 5
    assert len(first.proposals) == 5
    assert [
        (proposal.feed_override, proposal.sample_period) for proposal in first.proposals
    ] == [
        (0.675, 0.04),
        (0.65, 0.045),
        (0.75, 0.08),
        (1.0, 0.055),
        (0.975, 0.08),
    ]
    assert first.maximum_candidate_leverage_before == pytest.approx(2.5149375050227714)
    assert first.maximum_candidate_leverage_after == pytest.approx(0.4275568387783708)
    assert first.relative_maximum_leverage_reduction > 0.82
    assert first.global_optimality_status == "NotClaimed"


def test_r5d_selected_points_match_an_independent_sequential_numpy_oracle() -> None:
    scenario = load_r5c_scenario()
    request = build_r5d_experiment_plan_request()
    plan = plan_r5d_simulation_experiments(request, current_platform="Windows")
    train_ids = set(scenario.split_manifest.partitions[0].sample_ids)

    def features(point: tuple[float, float]) -> np.ndarray:
        return np.asarray(
            conditional_effect_feature_vector(
                scenario.dataset.domain,
                feed_override=point[0],
                sample_period=point[1],
            ),
            dtype=np.float64,
        )

    design = np.asarray(
        [
            features((sample.feed_override, sample.sample_period))
            for sample in scenario.dataset.samples
            if sample.sample_id in train_ids
        ],
        dtype=np.float64,
    )
    information = design.T @ design + RIDGE_LAMBDA * np.eye(6)
    observed = {
        (sample.feed_override, sample.sample_period)
        for sample in scenario.dataset.samples
    }
    pool = [
        (feed, period)
        for feed in R5D_CANDIDATE_FEED_OVERRIDES
        for period in R5D_CANDIDATE_SAMPLE_PERIODS
        if (feed, period) not in observed
    ]

    for proposal in plan.proposals:
        scored = [
            (float(vector @ np.linalg.solve(information, vector)), point)
            for point in pool
            for vector in (features(point),)
        ]
        expected_score, expected_point = sorted(
            scored,
            key=lambda item: (-float(f"{item[0]:.15g}"), item[1]),
        )[0]
        actual_point = (proposal.feed_override, proposal.sample_period)
        assert actual_point == expected_point
        assert proposal.design_leverage == pytest.approx(expected_score, abs=1e-12)
        vector = features(actual_point)
        information += np.outer(vector, vector)
        pool.remove(actual_point)


def test_r5d_plan_keeps_predictions_units_and_permissions_separate() -> None:
    payload = r5d_example_payload()
    observed = {
        (sample.feed_override, sample.sample_period)
        for sample in payload.request.dataset.samples
    }

    assert payload.plan.status == "Planned"
    assert all(
        (proposal.feed_override, proposal.sample_period) not in observed
        for proposal in payload.plan.proposals
    )
    assert (
        len(
            {
                (proposal.feed_override, proposal.sample_period)
                for proposal in payload.plan.proposals
            }
        )
        == 5
    )
    assert all(
        [(item.target_id, item.unit) for item in proposal.predicted_outcomes]
        == [
            ("cycleTimeSeconds", "s"),
            ("linearFollowingErrorMaxMm", "mm"),
        ]
        for proposal in payload.plan.proposals
    )
    assert payload.plan.experiment_execution_status == "NotExecuted"
    assert payload.plan.model_update_status == "NotPerformed"
    assert payload.plan.automatic_execution_allowed is False
    assert payload.plan.device_write_allowed is False
    assert payload.plan.real_world_generalization_status == "Open"


def test_r5d_request_rejects_split_leakage_and_identity_rebinding() -> None:
    request = build_r5d_experiment_plan_request()
    raw = request.model_dump(mode="json", by_alias=True)
    train = raw["splitManifest"]["partitions"][0]["sampleIds"]
    test = raw["splitManifest"]["partitions"][2]["sampleIds"]
    train[0], test[0] = test[0], train[0]
    split = raw["splitManifest"]
    split["contentHash"] = canonical_hash(
        {key: value for key, value in split.items() if key != "contentHash"}
    )
    raw["modelBundle"]["splitManifestHash"] = split["contentHash"]
    bundle = raw["modelBundle"]
    bundle["contentHash"] = canonical_hash(
        {key: value for key, value in bundle.items() if key != "contentHash"}
    )
    with pytest.raises(ValidationError, match="declared split"):
        R5DExperimentPlanRequest.model_validate(raw)

    raw = request.model_dump(mode="json", by_alias=True)
    raw["modelBundle"]["datasetContentHash"] = "0" * 64
    bundle = raw["modelBundle"]
    bundle["contentHash"] = canonical_hash(
        {key: value for key, value in bundle.items() if key != "contentHash"}
    )
    with pytest.raises(ValidationError, match="dataset"):
        R5DExperimentPlanRequest.model_validate(raw)


@pytest.mark.parametrize("batch_size", [0, 11])
def test_r5d_request_rejects_out_of_range_batch(batch_size: int) -> None:
    raw = build_r5d_experiment_plan_request().model_dump(mode="json", by_alias=True)
    raw["batchSize"] = batch_size

    with pytest.raises(ValidationError):
        R5DExperimentPlanRequest.model_validate(raw)


def test_r5d_non_windows_is_structurally_blocked() -> None:
    plan = plan_r5d_simulation_experiments(
        build_r5d_experiment_plan_request(), current_platform="Linux"
    )

    assert plan.status == "Blocked"
    assert plan.reason_codes == ("UnsupportedRuntimePlatform",)
    assert plan.proposals == ()
    assert plan.maximum_candidate_leverage_before is None
    assert plan.maximum_candidate_leverage_after is None
    assert plan.device_write_allowed is False


def test_r5d_manifest_and_serialized_plan_do_not_overclaim() -> None:
    manifest = build_r5d_manifest()
    serialized = json.dumps(
        r5d_example_payload().model_dump(mode="json", by_alias=True),
        sort_keys=True,
    )

    assert manifest.stage == "R5-D"
    assert manifest.candidate_pool_size == 135
    assert manifest.default_available_candidate_count == 110
    assert manifest.default_batch_size == 5
    assert manifest.maximum_batch_size == 10
    assert manifest.global_optimality_status == "NotClaimed"
    assert manifest.automatic_execution_allowed is False
    assert manifest.device_write_allowed is False
    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_packaged_r5d_fixture_freezes_environment_bound_identities() -> None:
    request = build_r5d_experiment_plan_request()
    plan = plan_r5d_simulation_experiments(request, current_platform="Windows")
    fixture = load_r5d_fixture_manifest()
    identity_key = (
        "windowsReleaseExpectedIdentities"
        if os.getenv("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1"
        else "developmentExpectedIdentities"
    )

    assert fixture["expectedProposalIds"] == [
        proposal.experiment_id for proposal in plan.proposals
    ]
    assert fixture["expectedDesignGates"] == {
        "maximumCandidateLeverageBefore": plan.maximum_candidate_leverage_before,
        "maximumCandidateLeverageAfter": plan.maximum_candidate_leverage_after,
        "relativeMaximumLeverageReduction": plan.relative_maximum_leverage_reduction,
    }
    assert fixture[identity_key] == {
        "requestContentHash": canonical_hash(request),
        "planContentHash": plan.content_hash,
    }
