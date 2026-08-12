from __future__ import annotations

import json
import os
from dataclasses import replace

import pytest

from axiom import evaluate_run
from axiom.five_axis.f4_scenarios import load_f4_scenario
from axiom.models import RunSpec
from axiom.optimization import (
    OptimizationGoal,
    OptimizationParameterGrid,
    OptimizationSearchRequest,
    build_r6_manifest,
    r6_example_payload,
    search_recommendations,
    validate_r6_example_run_spec,
)
from axiom.optimization import search as search_module


def test_r6_default_search_builds_six_hard_gate_safe_offline_candidates() -> None:
    payload = r6_example_payload()
    recommendations = payload.recommendation_set

    assert len(recommendations.candidates) == 6
    assert len(recommendations.pareto_candidate_ids) == 6
    assert recommendations.permission_level == "Offline"
    assert recommendations.device_write_allowed is False
    assert recommendations.automatic_acceptance_allowed is False
    assert recommendations.reality_validation_status == "Open"
    assert all(
        candidate.hard_constraints_satisfied for candidate in recommendations.candidates
    )
    assert all(
        len(candidate.gate_receipts) == 7 for candidate in recommendations.candidates
    )
    assert all(
        candidate.permission_level == "Offline"
        for candidate in recommendations.candidates
    )
    assert all(
        candidate.promotion_eligible is False
        for candidate in recommendations.candidates
    )


def test_r6_search_is_deterministic_and_never_serializes_device_safe_language() -> None:
    request = OptimizationSearchRequest()

    first = search_recommendations(request)
    second = search_recommendations(request)

    assert first == second
    assert first.content_hash == second.content_hash
    expected_content_hash = (
        "f4a4bd3d44b21f9bd068005bbdd5c88c5f7c4b63b3493b3a73c72105ddf0b97d"
        if os.environ.get("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1"
        else "77489ae7d7f51edb0fc8d38979898f893c67d41f50d366f361fb754d9edf5596"
    )
    assert first.content_hash == expected_content_hash
    serialized = json.dumps(
        first.model_dump(mode="json", by_alias=True), sort_keys=True
    )
    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_r6_goal_constraints_filter_pareto_without_weakening_hard_gates() -> None:
    request = OptimizationSearchRequest(
        goal=OptimizationGoal(
            goalId="optimization.r6.fast-low-sample-goal@1",
            maximumCycleTimeSeconds=0.70,
            maximumCommandSampleCount=12,
        )
    )

    recommendations = search_recommendations(request)

    assert len(recommendations.pareto_candidate_ids) == 1
    selected = next(
        candidate
        for candidate in recommendations.candidates
        if candidate.candidate_id == recommendations.pareto_candidate_ids[0]
    )
    assert selected.parameter_set.values == {"feedOverride": 1.0, "samplePeriod": 0.08}
    assert selected.goal_feasible is True
    assert selected.hard_constraints_satisfied is True


def test_r6_pareto_dominance_requires_no_worse_and_one_strictly_better() -> None:
    left = {
        "objectives": {
            "cycleTimeSeconds": 1.0,
            "linearFollowingErrorMaxMm": 0.4,
            "commandSampleCount": 10,
        }
    }
    right = {
        "objectives": {
            "cycleTimeSeconds": 1.0,
            "linearFollowingErrorMaxMm": 0.5,
            "commandSampleCount": 10,
        }
    }

    assert search_module._dominates(left, right) is True
    assert search_module._dominates(right, left) is False
    assert search_module._dominates(left, left) is False


@pytest.mark.parametrize(
    ("source_status", "expected"),
    [
        ("Supported", "Supported"),
        ("Refuted", "Refuted"),
        ("Unsupported", "Inconclusive"),
        ("Insufficient", "Inconclusive"),
        ("unresolved", "Inconclusive"),
    ],
)
def test_r6_maps_source_gate_status_without_upgrading_uncertainty(
    source_status: str, expected: str
) -> None:
    assert search_module._gate_claim_status(source_status) == expected


def test_r6_refuted_upstream_gate_blocks_every_candidate_from_pareto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = load_f4_scenario("canonical-head-table-solver")
    gate_statuses = list(source.stageAcceptanceReport.gate_claim_statuses)
    gate_statuses[0] = gate_statuses[0].model_copy(update={"status": "Refuted"})
    report = source.stageAcceptanceReport.model_copy(
        update={"gate_claim_statuses": tuple(gate_statuses)}
    )
    scenario = replace(source, stageAcceptanceReport=report)
    monkeypatch.setattr(search_module, "load_f4_scenario", lambda _: scenario)

    recommendations = search_recommendations(OptimizationSearchRequest())

    assert recommendations.pareto_candidate_ids == ()
    assert all(
        candidate.gate_receipts[0].status == "Refuted"
        and not candidate.hard_constraints_satisfied
        for candidate in recommendations.candidates
    )


def test_r6_rejects_unvalidated_sample_periods() -> None:
    with pytest.raises(ValueError, match="samplePeriods must be selected"):
        OptimizationParameterGrid(samplePeriods=(0.06,))


def test_r6_domain_runtime_replays_the_recommendation_artifact() -> None:
    bundle = evaluate_run(validate_r6_example_run_spec())
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Passed"
    assert claims["optimization.recommendation-integrity-claim@1"] == "Supported"
    assert claims["optimization.hard-constraints-respected-claim@1"] == "Supported"
    assert claims["optimization.offline-permission-boundary-claim@1"] == "Supported"
    assert claims["optimization.reality-validation-claim@1"] == "Inconclusive"


def test_r6_domain_runtime_rejects_tampered_recommendation_content() -> None:
    payload = validate_r6_example_run_spec().model_dump(mode="json", by_alias=True)
    payload["request"]["artifact"]["candidates"][0]["objectives"][
        "cycleTimeSeconds"
    ] += 1.0
    tampered = RunSpec.model_validate(payload)

    bundle = evaluate_run(tampered)

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Invalid"
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_r6_manifest_exposes_only_windows_offline_search() -> None:
    manifest = build_r6_manifest()

    assert manifest.permission_level == "Offline"
    assert manifest.supported_platforms == ("Windows",)
    assert manifest.device_write_allowed is False
    assert manifest.parameter_ids == ("feedOverride", "samplePeriod")
    assert manifest.objective_ids == (
        "cycleTimeSeconds",
        "linearFollowingErrorMaxMm",
        "commandSampleCount",
    )
