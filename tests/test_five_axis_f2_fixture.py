from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pint
import pydantic
import scipy  # type: ignore[import-untyped]

from axiom import evaluate_run
from axiom.evaluator import _content_hash
from axiom.five_axis.f2_scenarios import (
    f2_example_payload,
    validate_f2_example_run_spec,
)
from axiom.run import validate_run_bundle_integrity


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "five_axis_f2"


def _load_manifest() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _numeric_environment() -> dict[str, str]:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pint": pint.__version__,
        "pydantic": pydantic.__version__,
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
    environment = _numeric_environment()
    matching = [
        identity
        for identity in manifest["environmentBoundIdentities"]
        if identity["numericEnvironment"] == environment
    ]
    expected_hashes = matching[0]["bundleHashes"] if matching else {}
    for scenario_id in (case["id"] for case in manifest["cases"]):
        first = evaluate_run(validate_f2_example_run_spec(scenario_id))
        second = evaluate_run(validate_f2_example_run_spec(scenario_id))
        assert first.bundle_hash == second.bundle_hash
        if scenario_id in expected_hashes:
            assert first.bundle_hash == expected_hashes[scenario_id]
