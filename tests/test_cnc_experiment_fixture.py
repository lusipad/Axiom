from __future__ import annotations

import asyncio
import json
import math
import platform
from pathlib import Path

import fastapi
import hypothesis
import httpx
import numpy
import pint
import pydantic
import pytest
import scipy
import uvicorn

from axiom.cli import main
from axiom.experiment import run_experiment
from axiom.run import validate_run_bundle_integrity
from axiom.web import create_app


SUITE_DIR = Path(__file__).parents[1] / "fixtures" / "cnc_scenarios"
MANIFEST = json.loads((SUITE_DIR / "manifest.json").read_text(encoding="utf-8"))
EXPERIMENT_CASES = MANIFEST["experimentCases"]
ABS_TOL = MANIFEST["numericTolerance"]["absolute"]


def _load(case: dict) -> dict:
    return json.loads((SUITE_DIR / case["file"]).read_text(encoding="utf-8"))


def _current_dependency_signature() -> dict[str, dict[str, str]]:
    return {
        "numericEnvironment": {
            "python": platform.python_version(),
            "numpy": numpy.__version__,
            "scipy": scipy.__version__,
            "pint": pint.__version__,
            "pydantic": pydantic.__version__,
        },
        "directDependencies": {
            "fastapi": fastapi.__version__,
            "numpy": numpy.__version__,
            "pint": pint.__version__,
            "pydantic": pydantic.__version__,
            "scipy": scipy.__version__,
            "uvicorn": uvicorn.__version__,
            "httpx": httpx.__version__,
            "pytest": pytest.__version__,
            "hypothesis": hypothesis.__version__,
        },
    }


def _matching_environment_identity(case: dict) -> dict | None:
    current = _current_dependency_signature()
    for record in case["expectedEnvironmentBoundIdentities"]:
        if (
            record["numericEnvironment"] == current["numericEnvironment"]
            and record["directDependencies"] == current["directDependencies"]
        ):
            return record
    return None


async def _post_experiment(payload: dict) -> dict:
    transport = httpx.ASGITransport(app=create_app(serve_frontend=False))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/experiments/run", json=payload)
        assert response.status_code == 200
        return response.json()


def test_cnc_experiment_manifest_lists_every_fixed_experiment_fixture():
    listed = {case["file"] for case in EXPERIMENT_CASES}
    actual = {
        path.relative_to(SUITE_DIR).as_posix()
        for path in (SUITE_DIR / "experiments").glob("*.json")
    }

    assert listed == actual
    assert len({case["id"] for case in EXPERIMENT_CASES}) == len(EXPERIMENT_CASES)
    assert all(_load(case)["experimentId"] == case["id"] for case in EXPERIMENT_CASES)


def test_true_case_d_fixture_matches_its_frozen_acceptance_contract():
    case = EXPERIMENT_CASES[0]
    report = run_experiment(_load(case))
    baseline = report.arm_results[0].run_bundle
    candidate = report.arm_results[1].run_bundle

    assert report.execution_status.value == case["expectedExecutionStatus"]
    assert report.case_outcome.value == case["expectedCaseOutcome"]
    assert [arm.case_outcome.value for arm in report.arm_results] == case["expectedArmOutcomes"]
    assert report.shared_input_hash == case["expectedSharedInputHash"]
    assert report.parameter_set_hash == case["expectedParameterSetHash"]
    assert report.experiment_spec_hash == case["expectedExperimentSpecHash"]
    assert report.content_hash == run_experiment(_load(case)).content_hash
    assert report.comparison is not None
    assert report.comparison.compatibility.compatible is case["expectedCompatible"]

    expected = case["expectedMetric"]
    metric = next(
        item for item in report.comparison.metric_comparisons if item.metric_id == expected["metricId"]
    )
    assert math.isclose(metric.left_value, expected["left"], abs_tol=ABS_TOL)
    assert math.isclose(metric.right_value, expected["right"], abs_tol=ABS_TOL)
    assert math.isclose(metric.delta, expected["delta"], abs_tol=ABS_TOL)
    assert metric.unit == expected["unit"]
    assert metric.preferred_subject_id == expected["preferredSubjectId"]
    assert baseline is not None
    assert candidate is not None
    assert validate_run_bundle_integrity(baseline) == []
    assert validate_run_bundle_integrity(candidate) == []


def test_true_case_d_fixture_is_identical_across_python_cli_and_http(capsys):
    case = EXPERIMENT_CASES[0]
    path = SUITE_DIR / case["file"]
    payload = _load(case)
    python_result = run_experiment(payload).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert main(["experiment", str(path)]) == case["expectedExitCode"]
    cli_result = json.loads(capsys.readouterr().out)
    http_result = asyncio.run(_post_experiment(payload))

    assert cli_result == python_result
    assert http_result == python_result
    assert run_experiment(payload).model_dump(mode="json", by_alias=True, exclude_none=True) == python_result


def test_case_d_manifest_environment_bound_identities_are_unique_and_complete():
    case = EXPERIMENT_CASES[0]
    identities = case["expectedEnvironmentBoundIdentities"]
    keys = {
        (
            json.dumps(item["numericEnvironment"], sort_keys=True),
            json.dumps(item["directDependencies"], sort_keys=True),
        )
        for item in identities
    }

    assert len(keys) == len(identities)
    assert all(item["label"] for item in identities)
    assert all(item["numericEnvironment"] for item in identities)
    assert all(item["directDependencies"] for item in identities)
    assert all(item["baselineBundleHash"] for item in identities)
    assert all(item["candidateBundleHash"] for item in identities)
    assert all(item["comparisonContentHash"] for item in identities)


def test_true_case_d_fixture_uses_golden_environment_bound_hashes_only_on_exact_environment_match():
    case = EXPERIMENT_CASES[0]
    first = run_experiment(_load(case))
    second = run_experiment(_load(case))
    first_baseline = first.arm_results[0].run_bundle
    first_candidate = first.arm_results[1].run_bundle
    second_baseline = second.arm_results[0].run_bundle
    second_candidate = second.arm_results[1].run_bundle

    assert first_baseline is not None
    assert first_candidate is not None
    assert second_baseline is not None
    assert second_candidate is not None
    assert first.comparison is not None
    assert second.comparison is not None
    assert validate_run_bundle_integrity(first_baseline) == []
    assert validate_run_bundle_integrity(first_candidate) == []
    assert validate_run_bundle_integrity(second_baseline) == []
    assert validate_run_bundle_integrity(second_candidate) == []

    identity = _matching_environment_identity(case)
    if identity is not None:
        assert first_baseline.bundle_hash == identity["baselineBundleHash"]
        assert first_candidate.bundle_hash == identity["candidateBundleHash"]
        assert first.comparison.content_hash == identity["comparisonContentHash"]
        return

    assert first_baseline.bundle_hash == second_baseline.bundle_hash
    assert first_candidate.bundle_hash == second_candidate.bundle_hash
    assert first.comparison.content_hash == second.comparison.content_hash
    assert first.content_hash == second.content_hash
