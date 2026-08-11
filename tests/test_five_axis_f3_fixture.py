from __future__ import annotations

import json
import math
import os
import platform
from pathlib import Path
from typing import Any

from axiom.five_axis.f3_sampling import verify_interval_reconstruction
from axiom.five_axis.f3_scenarios import (
    current_f3_numeric_environment,
    f3_example_payload,
    load_f3_scenario,
    validate_f3_example_run_spec,
)
from axiom.run import evaluate_run, validate_run_bundle_integrity


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "five_axis_f3"


def _manifest() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _fixture_environment() -> dict[str, str]:
    return {
        **current_f3_numeric_environment(),
        "platformVersion": platform.version(),
    }


def _actual_bundle_hashes(scenario_ids: list[str]) -> dict[str, str]:
    return {
        scenario_id: evaluate_run(validate_f3_example_run_spec(scenario_id)).bundle_hash
        for scenario_id in scenario_ids
    }


def test_f3_reference_fixture_freezes_artifacts_policies_and_claims() -> None:
    manifest = _manifest()
    source_text = (FIXTURE_ROOT / manifest["programFile"]).read_text(encoding="utf-8")

    for case in manifest["cases"]:
        scenario_id = case["id"]
        scenario = load_f3_scenario(scenario_id)
        payload = f3_example_payload(scenario_id)
        artifact = scenario.sampledTrajectory or scenario.discreteCommand
        assert artifact is not None

        assert payload["source"]["sourceText"] == source_text
        assert payload["source"]["normalizedProgram"]["sourceSyntaxId"] == manifest["sourceSyntaxId"]
        assert scenario.axisPath.machine_profile.profile_id == case["machineProfileId"]
        assert scenario.motionConstraintProfile.profile_id == case["motionConstraintProfileId"]
        assert scenario.continuousTrajectory.source_axis_path_content_id == case["expectedAxisPathContentId"]
        assert scenario.continuousTrajectory.motion_constraint_profile_content_id == (
            case["expectedMotionConstraintProfileContentId"]
        )
        assert artifact.source_m4_content_id == case["expectedContinuousTrajectoryContentId"]
        assert artifact.artifact_type == case["expectedM5ArtifactType"]
        assert artifact.content_id == case["expectedM5ContentId"]
        assert scenario.continuousTrajectory.timing_mode == case["expectedTimingMode"]
        assert scenario.continuousTrajectory.verification.optimality.classification == (
            case["expectedOptimality"]
        )
        assert math.isclose(
            scenario.continuousTrajectory.verification.total_duration_seconds,
            case["expectedDurationSeconds"],
            rel_tol=0.0,
            abs_tol=1e-15,
        )
        assert artifact.reconstruction_policy.policy_id == case["reconstructionPolicyId"]
        assert verify_interval_reconstruction(artifact).status == case["expectedIntervalVerificationStatus"]
        assert tuple(scenario.manifest.fixture_content_ids) == (
            case["expectedAxisPathContentId"],
            case["expectedContinuousTrajectoryContentId"],
            case["expectedM5ContentId"],
        )

        bundle = evaluate_run(validate_f3_example_run_spec(scenario_id))
        assert validate_run_bundle_integrity(bundle) == []
        assert bundle.run.execution_status.value == case["expectedExecutionStatus"]
        assert bundle.run.case_outcome.value == case["expectedCaseOutcome"]
        claims = {claim.claim_definition_id: claim for claim in bundle.claims}
        manifest_claims = {claim.claim_id: claim for claim in scenario.manifest.expected_claims}
        summary_claims = payload["scenario"]["expectedClaimStatusById"]
        for claim_id, expected in case["expectedClaims"].items():
            claim = claims[claim_id]
            manifest_claim = manifest_claims[claim_id]
            assert claim.status.value == expected["status"]
            actual_level = claim.evidence.level if claim.evidence is not None else None
            assert actual_level == expected["evidenceLevel"]
            assert manifest_claim.expected_status == expected["status"]
            assert manifest_claim.evidence_level == expected["evidenceLevel"]
            assert summary_claims[claim_id] == expected["status"]


def test_f3_reference_fixture_replays_environment_bound_bundle_hashes_when_applicable() -> None:
    manifest = _manifest()
    matching = [
        identity
        for identity in manifest["environmentBoundIdentities"]
        if identity["numericEnvironment"] == _fixture_environment()
    ]
    scenario_ids = [case["id"] for case in manifest["cases"]]
    if os.environ.get("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1":
        actual_hashes = _actual_bundle_hashes(scenario_ids)
        assert len(matching) == 1, (
            "missing unique environment-bound fixture identity for "
            f"{_fixture_environment()!r}; actual bundle hashes: {actual_hashes!r}"
        )
    expected_hashes = matching[0]["bundleHashes"] if matching else {}
    if os.environ.get("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1":
        assert set(expected_hashes) == set(scenario_ids), (
            "environment-bound bundle hashes do not cover every scenario for "
            f"{_fixture_environment()!r}: expected keys={sorted(expected_hashes)!r}, "
            f"actual hashes={_actual_bundle_hashes(scenario_ids)!r}"
        )
    for scenario_id in scenario_ids:
        first = evaluate_run(validate_f3_example_run_spec(scenario_id))
        second = evaluate_run(validate_f3_example_run_spec(scenario_id))
        assert first.bundle_hash == second.bundle_hash
        if scenario_id in expected_hashes:
            assert first.bundle_hash == expected_hashes[scenario_id], (
                f"{scenario_id}: expected {expected_hashes[scenario_id]!r}, got {first.bundle_hash!r}, "
                f"environment={_fixture_environment()!r}, actual bundle hashes={_actual_bundle_hashes(scenario_ids)!r}"
            )
