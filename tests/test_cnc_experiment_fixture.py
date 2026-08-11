from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

import httpx

from axiom.cli import main
from axiom.experiment import run_experiment
from axiom.web import create_app


SUITE_DIR = Path(__file__).parents[1] / "fixtures" / "cnc_scenarios"
MANIFEST = json.loads((SUITE_DIR / "manifest.json").read_text(encoding="utf-8"))
EXPERIMENT_CASES = MANIFEST["experimentCases"]
ABS_TOL = MANIFEST["numericTolerance"]["absolute"]


def _load(case: dict) -> dict:
    return json.loads((SUITE_DIR / case["file"]).read_text(encoding="utf-8"))


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

    assert report.execution_status.value == case["expectedExecutionStatus"]
    assert report.case_outcome.value == case["expectedCaseOutcome"]
    assert [arm.case_outcome.value for arm in report.arm_results] == case["expectedArmOutcomes"]
    assert report.shared_input_hash == case["expectedSharedInputHash"]
    assert report.parameter_set_hash == case["expectedParameterSetHash"]
    assert report.experiment_spec_hash == case["expectedExperimentSpecHash"]
    assert report.content_hash == case["expectedContentHash"]
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
