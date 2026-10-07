from __future__ import annotations

from copy import deepcopy
import platform

import pytest
from pydantic import ValidationError

from axiom.intelligence import (
    R5ESyntheticCampaignReport,
    R5ESyntheticCampaignRequest,
    build_r5e_campaign_request,
    build_r5e_manifest,
    execute_r5e_synthetic_campaign,
    load_r5e_fixture_manifest,
    r5e_example_payload,
)
from axiom.intelligence.models import canonical_hash


@pytest.fixture(scope="module")
def campaign_request() -> R5ESyntheticCampaignRequest:
    return build_r5e_campaign_request(accountable_party_id="local-reviewer")


@pytest.fixture(scope="module")
def campaign_report(
    campaign_request: R5ESyntheticCampaignRequest,
) -> R5ESyntheticCampaignReport:
    return execute_r5e_synthetic_campaign(campaign_request, current_platform="Windows")


def _reseal(payload: dict[str, object]) -> None:
    payload.pop("contentHash", None)
    payload["contentHash"] = canonical_hash(payload)


def test_manifest_and_example_stop_before_approval_or_execution() -> None:
    manifest = build_r5e_manifest()
    example = r5e_example_payload()

    assert manifest.stage == "R5-E"
    assert manifest.automatic_execution_allowed is False
    assert manifest.automatic_model_promotion_allowed is False
    assert example.approval_requirements.approval_required is True
    assert example.approval_requirements.device_authority_granted is False
    assert example.plan.experiment_execution_status == "NotExecuted"
    assert example.plan.model_update_status == "NotPerformed"
    assert not hasattr(example, "approval")


def test_default_campaign_closes_the_synthetic_feedback_loop(
    campaign_request: R5ESyntheticCampaignRequest,
    campaign_report: R5ESyntheticCampaignReport,
) -> None:
    source_samples = campaign_request.plan_request.dataset.samples
    source_partitions = campaign_request.plan_request.split_manifest.partitions

    assert campaign_report.campaign_execution_status == "Succeeded"
    assert campaign_report.acquisition_receipt.result_count == 5
    assert len(campaign_report.dataset.samples) == 30
    assert campaign_report.dataset.samples[:25] == source_samples
    assert tuple(
        len(item.sample_ids) for item in campaign_report.split_manifest.partitions
    ) == (
        20,
        5,
        5,
    )
    assert campaign_report.split_manifest.partitions[1:] == source_partitions[1:]
    assert (
        tuple(
            sample.declared_split_id for sample in campaign_report.dataset.samples[25:]
        )
        == ("train",) * 5
    )
    assert campaign_report.model_bundle.schema_version == 2
    assert campaign_report.training_receipt.train_sample_count == 20
    assert campaign_report.parity_receipt.sample_count == 30
    assert campaign_report.candidate_assessment.candidate_gate_status == "Passed"
    assert campaign_report.candidate_assessment.model_promotion_status == "NotPerformed"
    assert campaign_report.model_promotion_status == "NotPerformed"
    assert campaign_report.real_world_generalization_status == "Open"
    assert campaign_report.device_write_allowed is False


def test_default_acquisition_uses_exact_f3_f4_r4_results(
    campaign_report: R5ESyntheticCampaignReport,
) -> None:
    observed = tuple(
        (
            item.feed_override,
            item.sample_period,
            item.cycle_time_seconds,
            item.linear_following_error_max_mm,
            item.command_sample_count,
        )
        for item in campaign_report.acquisition_receipt.results
    )
    expected = (
        (0.675, 0.04, 1.005928794198545, 0.36550563328863817, 27),
        (0.65, 0.045, 1.0446183632061814, 0.3612146101299807, 25),
        (0.75, 0.08, 0.9053359147786905, 0.4692778032767464, 13),
        (1.0, 0.055, 0.6790019360840179, 0.5323623615207111, 14),
        (0.975, 0.08, 0.6964122421374543, 0.561059765701124, 10),
    )
    for actual_row, expected_row in zip(observed, expected, strict=True):
        assert actual_row == pytest.approx(expected_row, rel=0.0, abs=1e-15)
    assert all(
        item.continuous_feasibility_status == "Supported"
        and item.adapter_status == "Succeeded"
        and item.interval_verification_status == "Supported"
        and item.collision_verification_status == "safe"
        and item.device_write_allowed is False
        for item in campaign_report.acquisition_receipt.results
    )


def test_candidate_metrics_are_observations_not_a_general_guarantee(
    campaign_report: R5ESyntheticCampaignReport,
) -> None:
    cycle, linear_error = campaign_report.candidate_assessment.metric_deltas
    assert cycle.status == "Improved"
    assert cycle.relative_improvement > 0.44
    assert linear_error.status == "Improved"
    assert linear_error.relative_improvement > 0.24
    assert (
        campaign_report.candidate_assessment.general_improvement_guarantee
        == "NotClaimed"
    )


def test_replanning_uses_twenty_design_points_and_excludes_all_thirty(
    campaign_report: R5ESyntheticCampaignReport,
) -> None:
    plan = campaign_report.next_plan
    assert plan.design_sample_count == 20
    assert plan.excluded_observed_point_count == 30
    assert plan.available_candidate_count == 105
    assert tuple(
        (item.feed_override, item.sample_period) for item in plan.proposals
    ) == (
        (0.975, 0.04),
        (0.675, 0.08),
        (0.7, 0.04),
        (0.775, 0.08),
        (1.0, 0.065),
    )
    assert plan.experiment_execution_status == "NotExecuted"
    assert plan.model_update_status == "NotPerformed"


def test_campaign_does_not_mutate_source_objects(
    campaign_request: R5ESyntheticCampaignRequest,
) -> None:
    before = campaign_request.model_dump(mode="json", by_alias=True)
    execute_r5e_synthetic_campaign(campaign_request, current_platform="Windows")
    assert campaign_request.model_dump(mode="json", by_alias=True) == before


def test_campaign_is_deterministic_in_one_numeric_environment(
    campaign_request: R5ESyntheticCampaignRequest,
    campaign_report: R5ESyntheticCampaignReport,
) -> None:
    replay = execute_r5e_synthetic_campaign(
        campaign_request, current_platform="Windows"
    )
    assert replay.content_hash == campaign_report.content_hash
    assert (
        replay.acquisition_receipt.content_hash
        == campaign_report.acquisition_receipt.content_hash
    )


def test_partial_or_cross_plan_approval_is_rejected_before_execution(
    campaign_request: R5ESyntheticCampaignRequest,
) -> None:
    partial = campaign_request.model_dump(mode="json", by_alias=True)
    partial["approval"]["approvedExperimentIds"] = partial["approval"][
        "approvedExperimentIds"
    ][:-1]
    _reseal(partial["approval"])
    _reseal(partial)
    with pytest.raises(ValidationError, match="all proposals in plan order"):
        R5ESyntheticCampaignRequest.model_validate(partial)

    wrong_plan = campaign_request.model_dump(mode="json", by_alias=True)
    wrong_plan["approval"]["planContentHash"] = "0" * 64
    _reseal(wrong_plan["approval"])
    _reseal(wrong_plan)
    with pytest.raises(ValidationError, match="exact plan content"):
        R5ESyntheticCampaignRequest.model_validate(wrong_plan)


def test_non_windows_fails_before_any_physical_acquisition(
    campaign_request: R5ESyntheticCampaignRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_acquire(_request: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("physical acquisition must not run")

    monkeypatch.setattr("axiom.intelligence.r5e_campaign._acquire", forbidden_acquire)
    with pytest.raises(ValueError, match="only supports Windows"):
        execute_r5e_synthetic_campaign(campaign_request, current_platform="Linux")
    assert called is False


def test_tampered_acquisition_result_is_rejected(
    campaign_report: R5ESyntheticCampaignReport,
) -> None:
    raw = deepcopy(campaign_report.model_dump(mode="json", by_alias=True))
    raw["acquisitionReceipt"]["results"][0]["cycleTimeSeconds"] += 0.01
    with pytest.raises(ValidationError, match="experiment result content"):
        R5ESyntheticCampaignReport.model_validate(raw)


def test_resealed_cross_object_lineage_mismatch_is_rejected(
    campaign_report: R5ESyntheticCampaignReport,
) -> None:
    raw = deepcopy(campaign_report.model_dump(mode="json", by_alias=True))
    raw["candidateAssessment"]["sourceModelBundleHash"] = "0" * 64
    _reseal(raw["candidateAssessment"])
    _reseal(raw)

    with pytest.raises(ValidationError, match="both compared models"):
        R5ESyntheticCampaignReport.model_validate(raw)


def test_development_fixture_freezes_the_complete_campaign_lineage(
    campaign_report: R5ESyntheticCampaignReport,
) -> None:
    if platform.python_version() != "3.14.3":
        pytest.skip("development golden requires CPython 3.14.3")
    fixture = load_r5e_fixture_manifest()
    request = build_r5e_campaign_request(
        accountable_party_id=fixture["accountablePartyId"]
    )
    report = execute_r5e_synthetic_campaign(request, current_platform="Windows")
    expected = fixture["developmentExpectedIdentities"]
    assert {
        "campaignRequestContentHash": request.content_hash,
        "acquisitionReceiptContentHash": report.acquisition_receipt.content_hash,
        "datasetContentHash": report.dataset.content_hash,
        "splitManifestContentHash": report.split_manifest.content_hash,
        "trainingReceiptContentHash": report.training_receipt.content_hash,
        "modelBundleContentHash": report.model_bundle.content_hash,
        "parityReceiptContentHash": report.parity_receipt.content_hash,
        "candidateAssessmentContentHash": report.candidate_assessment.content_hash,
        "nextPlanContentHash": report.next_plan.content_hash,
        "reportContentHash": report.content_hash,
    } == expected
    assert fixture["boundary"] == campaign_report.safety_banner


def test_windows_release_fixture_freezes_the_complete_campaign_lineage() -> None:
    if platform.python_version() != "3.12.10":
        pytest.skip("release golden requires CPython 3.12.10")
    fixture = load_r5e_fixture_manifest()
    request = build_r5e_campaign_request(
        accountable_party_id=fixture["accountablePartyId"]
    )
    report = execute_r5e_synthetic_campaign(request, current_platform="Windows")
    assert {
        "campaignRequestContentHash": request.content_hash,
        "acquisitionReceiptContentHash": report.acquisition_receipt.content_hash,
        "datasetContentHash": report.dataset.content_hash,
        "splitManifestContentHash": report.split_manifest.content_hash,
        "trainingReceiptContentHash": report.training_receipt.content_hash,
        "modelBundleContentHash": report.model_bundle.content_hash,
        "parityReceiptContentHash": report.parity_receipt.content_hash,
        "candidateAssessmentContentHash": report.candidate_assessment.content_hash,
        "nextPlanContentHash": report.next_plan.content_hash,
        "reportContentHash": report.content_hash,
    } == fixture["windowsReleaseExpectedIdentities"]
