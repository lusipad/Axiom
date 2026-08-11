from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any

from axiom import evaluate_run
from axiom.evaluator import _content_hash
from axiom.five_axis.f2_runtime import current_f2_numeric_environment
from axiom.five_axis.f2_scenarios import (
    f2_example_payload,
    validate_f2_example_run_spec,
)
from axiom.run import validate_run_bundle_integrity


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "five_axis_f2"


def _load_manifest() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _fixture_environment() -> dict[str, str]:
    return {
        **current_f2_numeric_environment(),
        "platformVersion": platform.version(),
    }


def _actual_bundle_hashes(scenario_ids: list[str]) -> dict[str, str]:
    return {
        scenario_id: evaluate_run(validate_f2_example_run_spec(scenario_id)).bundle_hash
        for scenario_id in scenario_ids
    }


def test_f2_reference_fixture_freezes_portable_artifact_and_claim_contracts() -> None:
    manifest = _load_manifest()
    source_text = (FIXTURE_ROOT / manifest["programFile"]).read_text(encoding="utf-8")

    for case in manifest["cases"]:
        scenario_id = case["id"]
        payload = f2_example_payload(scenario_id)
        artifacts = payload["artifacts"]
        axis_path = artifacts["axisPath"]

        assert payload["source"]["sourceText"] == source_text
        assert payload["source"]["normalizedProgram"]["sourceSyntaxId"] == manifest["sourceSyntaxId"]
        assert payload["source"]["normalizedProgram"]["programId"] == manifest["expectedNormalizedProgramId"]
        assert payload["source"]["referencePath"]["referencePathId"] == manifest["expectedReferencePathId"]
        reference_path_content_id = _content_hash(payload["source"]["referencePath"])
        assert artifacts["candidateGeometry"]["sourceReferencePathContentId"] == reference_path_content_id
        assert artifacts["candidateGeometry"]["provenance"][0]["sourceContentId"] == reference_path_content_id
        assert artifacts["machineProfile"]["profileId"] == case["machineProfileId"]
        assert axis_path["sourceCandidateGeometryContentId"] == case["expectedCandidateGeometryContentId"]
        assert axis_path["machineProfileContentId"] == case["expectedMachineProfileContentId"]
        assert artifacts["collisionModel"]["contentId"] == case["expectedCollisionModelContentId"]
        assert axis_path["axisPathId"] == case["expectedAxisPathId"]

        bundle = evaluate_run(validate_f2_example_run_spec(scenario_id))
        assert validate_run_bundle_integrity(bundle) == []
        assert bundle.run.execution_status.value == case["expectedExecutionStatus"]
        assert bundle.run.case_outcome.value == case["expectedCaseOutcome"]

        claims = {claim.claim_definition_id: claim for claim in bundle.claims}
        for definition_id, expected in case["expectedClaims"].items():
            claim = claims[definition_id]
            assert claim.status.value == expected["status"]
            assert claim.evidence is not None
            assert claim.evidence.level == expected["evidenceLevel"]

        collision_metric = next(
            result
            for result in bundle.report.metric_results
            if result.metric_id == "five-axis.configuration-collision-free@1"
        )
        collision_evaluation = collision_metric.details["collisionEvaluation"]
        assert collision_evaluation["status"] == case["expectedCollisionStatus"]
        if "expectedWitnessSigma" in case:
            witnesses = [
                pair["witnessSigma"]
                for pair in collision_evaluation["pairResults"]
                if pair.get("witnessSigma") is not None
            ]
            assert case["expectedWitnessSigma"] in witnesses


def test_f2_reference_fixture_replays_environment_bound_bundle_hashes_when_applicable() -> None:
    manifest = _load_manifest()
    environment = _fixture_environment()
    matching = [
        identity
        for identity in manifest["environmentBoundIdentities"]
        if identity["numericEnvironment"] == environment
    ]
    scenario_ids = [case["id"] for case in manifest["cases"]]
    if os.environ.get("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1":
        actual_hashes = _actual_bundle_hashes(scenario_ids)
        assert len(matching) == 1, (
            "missing unique environment-bound fixture identity for "
            f"{environment!r}; actual bundle hashes: {actual_hashes!r}"
        )
    expected_hashes = matching[0]["bundleHashes"] if matching else {}
    if os.environ.get("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1":
        assert set(expected_hashes) == set(scenario_ids), (
            f"environment-bound bundle hashes do not cover every scenario for {environment!r}: "
            f"expected keys={sorted(expected_hashes)!r}, actual hashes={_actual_bundle_hashes(scenario_ids)!r}"
        )
    for scenario_id in scenario_ids:
        first = evaluate_run(validate_f2_example_run_spec(scenario_id))
        second = evaluate_run(validate_f2_example_run_spec(scenario_id))
        assert first.bundle_hash == second.bundle_hash
        if scenario_id in expected_hashes:
            assert first.bundle_hash == expected_hashes[scenario_id], (
                f"{scenario_id}: expected {expected_hashes[scenario_id]!r}, got {first.bundle_hash!r}, "
                f"environment={environment!r}, actual bundle hashes={_actual_bundle_hashes(scenario_ids)!r}"
            )
