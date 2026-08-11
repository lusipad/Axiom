from __future__ import annotations

import json
import math
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
        for claim_id, expected in case["expectedClaims"].items():
            claim = claims[claim_id]
            assert claim.status.value == expected["status"]
            actual_level = claim.evidence.level if claim.evidence is not None else None
            assert actual_level == expected["evidenceLevel"]


def test_f3_reference_fixture_replays_environment_bound_bundle_hashes_when_applicable() -> None:
    manifest = _manifest()
    matching = [
        identity
        for identity in manifest["environmentBoundIdentities"]
        if identity["numericEnvironment"] == current_f3_numeric_environment()
    ]
    if not matching:
        return

    for scenario_id, expected_hash in matching[0]["bundleHashes"].items():
        first = evaluate_run(validate_f3_example_run_spec(scenario_id))
        second = evaluate_run(validate_f3_example_run_spec(scenario_id))
        assert first.bundle_hash == expected_hash
        assert second.bundle_hash == expected_hash
