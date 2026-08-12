from __future__ import annotations

import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from axiom.evaluator import _content_hash
from axiom.five_axis import (
    f1_runtime,
    f2_runtime,
    f3_runtime,
    f4_adapters,
    f4_runtime,
    f4_scenarios,
)
from axiom.five_axis.f2_collision import evaluate_configuration_q_free
from axiom.five_axis.f2_kinematics import normalize_numeric_identity
from axiom.five_axis.f4_scenarios import (
    build_f4_stage_acceptance_report,
    f4_example_payload,
    load_f4_scenario,
    validate_f4_example_run_spec,
)
from axiom.run import evaluate_run, validate_run_bundle_integrity

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "five_axis_f4"
TARGET_ENVIRONMENT = {
    "system": "Windows",
    "machine": "AMD64",
    "python": "3.12.10",
    "numpy": "2.5.2",
    "scipy": "1.18.0",
    "pint": "0.25.3",
    "pydantic": "2.13.4",
    "openblasCoreType": "Haswell",
    "openblasNumThreads": "1",
    "ompNumThreads": "1",
}


def _manifest() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _portable_content_hash(payload: Any) -> str:
    serializable = (
        payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        if hasattr(payload, "model_dump")
        else payload
    )
    return _content_hash(normalize_numeric_identity(serializable))


def _portable_case_hashes(scenario_id: str) -> dict[str, str | None]:
    scenario = load_f4_scenario(scenario_id)
    return {
        "expectedCandidateGeometryContentId": _portable_content_hash(scenario.candidateGeometry),
        "expectedAxisPathContentId": _portable_content_hash(scenario.axisPath),
        "expectedContinuousTrajectoryContentId": _portable_content_hash(scenario.continuousTrajectory),
        "expectedCollisionModelContentId": _portable_content_hash(scenario.collisionModel),
        "expectedReferenceInvocationContentId": _portable_content_hash(scenario.referenceInvocation),
        "expectedSutInvocationContentId": _portable_content_hash(scenario.sutInvocation),
        "expectedReferenceCommandContentId": (
            scenario.referenceCommand.content_id if scenario.referenceCommand is not None else None
        ),
        "expectedSutCommandContentId": (
            scenario.sutCommand.content_id if scenario.sutCommand is not None else None
        ),
    }


def _actual_bundle_hashes(scenario_ids: list[str]) -> dict[str, str]:
    return {
        scenario_id: evaluate_run(validate_f4_example_run_spec(scenario_id)).bundle_hash
        for scenario_id in scenario_ids
    }


@contextmanager
def _bound_fixture_environment(monkeypatch: Any) -> Iterator[dict[str, str]]:
    for module, attribute in (
        (f1_runtime, "current_f1_numeric_environment"),
        (f2_runtime, "current_f2_numeric_environment"),
        (f3_runtime, "current_f3_numeric_environment"),
        (f4_runtime, "current_f4_numeric_environment"),
    ):
        monkeypatch.setattr(module, attribute, lambda target=TARGET_ENVIRONMENT: dict(target))
    monkeypatch.setattr(f4_adapters, "_numeric_environment", lambda: dict(TARGET_ENVIRONMENT))
    f4_scenarios._build_scenario_core.cache_clear()
    f4_scenarios.build_f4_stage_acceptance_report.cache_clear()
    try:
        yield dict(TARGET_ENVIRONMENT)
    finally:
        f4_scenarios._build_scenario_core.cache_clear()
        f4_scenarios.build_f4_stage_acceptance_report.cache_clear()


def test_f4_reference_fixture_freezes_portable_hashes_claims_and_stage_report() -> None:
    manifest = _manifest()
    source_text = (FIXTURE_ROOT / manifest["programFile"]).read_text(encoding="utf-8")
    report = build_f4_stage_acceptance_report()

    assert report.content_hash == manifest["expectedStageAcceptanceReportContentHash"]
    assert report.status == manifest["expectedStageAcceptanceReportStatus"]
    assert [
        item.model_dump(mode="json", by_alias=True, exclude_none=True)
        for item in report.topology_coverage
    ] == manifest["expectedTopologyCoverage"]
    assert [
        item.model_dump(mode="json", by_alias=True, exclude_none=True)
        for item in report.counterexample_coverage
    ] == manifest["expectedCounterexampleCoverage"]

    for case in manifest["cases"]:
        scenario_id = case["id"]
        scenario = load_f4_scenario(scenario_id)
        payload = f4_example_payload(scenario_id)

        assert payload["source"]["sourceText"] == source_text
        assert payload["source"]["normalizedProgram"]["sourceSyntaxId"] == manifest["sourceSyntaxId"]
        assert payload["acceptanceReport"]["contentHash"] == manifest["expectedStageAcceptanceReportContentHash"]
        assert payload["acceptanceReport"]["status"] == manifest["expectedStageAcceptanceReportStatus"]
        assert scenario.summary.topology == case["topology"]
        assert scenario.summary.countsTowardClosure is case["countsTowardClosure"]
        assert scenario.stageAcceptanceReport == report

        for field, actual in _portable_case_hashes(scenario_id).items():
            assert actual == case[field]

        assert scenario.referenceReceipt.status == case["expectedReferenceReceiptStatus"]
        assert scenario.sutReceipt.status == case["expectedSutReceiptStatus"]
        assert scenario.scenarioResult.cross_validation_status == case["expectedCrossValidationStatus"]
        assert scenario.scenarioResult.collision_status == case["expectedCollisionStatus"]

        if case["countsTowardClosure"]:
            bundle = evaluate_run(validate_f4_example_run_spec(scenario_id))
            assert validate_run_bundle_integrity(bundle) == []
            assert bundle.run.execution_status.value == case["expectedExecutionStatus"]
            assert bundle.run.case_outcome.value == case["expectedCaseOutcome"]

            expected_claims = case["expectedClaims"]
            math_claims = {
                claim.claim_definition_id: claim
                for claim in bundle.claims
                if claim.claim_definition_id.startswith("five-axis.")
            }
            assert len(math_claims) == len(expected_claims) == 7
            assert set(math_claims) == set(expected_claims)

            manifest_claims = {claim.claim_id: claim for claim in scenario.manifest.expected_claims}
            assert len(manifest_claims) == len(expected_claims) == 7
            assert set(manifest_claims) == set(expected_claims)

            for claim_id, expected in expected_claims.items():
                claim = math_claims[claim_id]
                assert claim.status.value == expected["status"]
                actual_level = claim.evidence.level if claim.evidence is not None else None
                assert actual_level == expected["evidenceLevel"]
        elif scenario_id == "adapter-input-hash-mismatch":
            assert scenario.referenceCommand is not None
            assert scenario.sutCommand is None
            assert scenario.sutReceipt.failure_code == case["expectedSutFailureCode"]
            assert scenario.crossValidation is None
            assert scenario.collisionVerification is None
        else:
            expected_interval = case["expectedCollisionInterval"]

            assert scenario.referenceCommand is not None
            assert scenario.sutCommand is not None
            assert scenario.crossValidation is not None
            assert scenario.collisionVerification is not None

            collision_intervals = [
                item
                for item in scenario.collisionVerification.interval_evaluations
                if item.status == "collision"
            ]
            assert len(collision_intervals) == 1
            collision_interval = collision_intervals[0]
            assert math.isclose(collision_interval.t_start, expected_interval["tStart"], rel_tol=0.0, abs_tol=1e-15)
            assert math.isclose(collision_interval.t_end, expected_interval["tEnd"], rel_tol=0.0, abs_tol=1e-15)
            assert math.isclose(
                collision_interval.witness_time,
                expected_interval["witnessTime"],
                rel_tol=0.0,
                abs_tol=1e-15,
            )

            start_sample = next(
                sample
                for sample in scenario.sutCommand.samples
                if math.isclose(sample.t, expected_interval["tStart"], rel_tol=0.0, abs_tol=1e-15)
            )
            end_sample = next(
                sample
                for sample in scenario.sutCommand.samples
                if math.isclose(sample.t, expected_interval["tEnd"], rel_tol=0.0, abs_tol=1e-15)
            )
            source_axis_path = scenario.sutCommand.source_m4.source_axis_path

            assert evaluate_configuration_q_free(
                source_axis_path,
                collision_model=scenario.collisionModel,
                sigma=start_sample.sigma,
            ).status == expected_interval["startEndpointStatus"]
            assert evaluate_configuration_q_free(
                source_axis_path,
                collision_model=scenario.collisionModel,
                sigma=end_sample.sigma,
            ).status == expected_interval["endEndpointStatus"]


def test_f4_reference_fixture_replays_windows_environment_bound_bundle_hashes(monkeypatch: Any) -> None:
    manifest = _manifest()
    scenario_ids = [case["id"] for case in manifest["cases"] if case["countsTowardClosure"]]
    actual_environment = f4_runtime.current_f4_numeric_environment()
    if actual_environment != TARGET_ENVIRONMENT:
        pytest.skip(
            "environment-bound F4 bundle hashes require the exact Windows acceptance environment; "
            f"actual={actual_environment!r}"
        )

    with _bound_fixture_environment(monkeypatch) as target_environment:
        matching = [
            identity
            for identity in manifest["environmentBoundIdentities"]
            if identity["numericEnvironment"] == target_environment
        ]
        actual_hashes = _actual_bundle_hashes(scenario_ids)

        assert len(matching) == 1, (
            "missing unique environment-bound fixture identity for "
            f"{target_environment!r}; actual bundle hashes: {actual_hashes!r}"
        )

        expected_hashes = matching[0]["bundleHashes"]
        assert set(expected_hashes) == set(scenario_ids), (
            "environment-bound bundle hashes do not cover every positive solver scenario for "
            f"{target_environment!r}: expected keys={sorted(expected_hashes)!r}, actual hashes={actual_hashes!r}"
        )

        for scenario_id in scenario_ids:
            first = evaluate_run(validate_f4_example_run_spec(scenario_id))
            second = evaluate_run(validate_f4_example_run_spec(scenario_id))
            assert first.bundle_hash == second.bundle_hash
            assert first.bundle_hash == expected_hashes[scenario_id], (
                f"{scenario_id}: expected {expected_hashes[scenario_id]!r}, got {first.bundle_hash!r}, "
                f"environment={target_environment!r}, actual bundle hashes={actual_hashes!r}"
            )
