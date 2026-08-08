import json
import math
import statistics
from numbers import Real
from pathlib import Path

import pytest

from axiom.cli import main
from axiom.evaluator import evaluate


SUITE_DIR = Path(__file__).parents[1] / "fixtures" / "cnc_scenarios"
MANIFEST = json.loads((SUITE_DIR / "manifest.json").read_text(encoding="utf-8"))
CASES = MANIFEST["cases"]
ABS_TOL = MANIFEST["numericTolerance"]["absolute"]
REL_TOL = MANIFEST["numericTolerance"]["relative"]


def _load_request(case):
    return json.loads((SUITE_DIR / case["file"]).read_text(encoding="utf-8"))


def _assert_value(actual, expected):
    if isinstance(expected, Real) and not isinstance(expected, bool):
        assert isinstance(actual, Real) and not isinstance(actual, bool)
        assert math.isclose(actual, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL)
        return
    if isinstance(expected, list):
        assert len(actual) == len(expected)
        for actual_item, expected_item in zip(actual, expected, strict=True):
            _assert_value(actual_item, expected_item)
        return
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            _assert_value(actual[key], expected[key])
        return
    assert actual == expected


def _polyline_length(points):
    return sum(math.dist(start, end) for start, end in zip(points, points[1:]))


def test_cnc_fixture_manifest_is_complete_and_explicitly_synthetic():
    listed_files = {case["file"] for case in CASES}
    actual_files = {
        path.relative_to(SUITE_DIR).as_posix()
        for path in (SUITE_DIR / "requests").glob("*.json")
    }

    assert MANIFEST["synthetic"] is True
    assert MANIFEST["datasetType"] == "deterministic-engineering-synthetic"
    assert "not real machine observations" in MANIFEST["disclaimer"]
    assert len({case["id"] for case in CASES}) == len(CASES)
    assert listed_files == actual_files
    for case in CASES:
        assert _load_request(case)["case"]["caseId"] == case["id"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_cnc_fixture_matches_its_acceptance_contract(case):
    report = evaluate(_load_request(case))

    assert report.execution_status.value == case["expectedExecutionStatus"]
    assert report.case_outcome.value == case["expectedCaseOutcome"]
    assert {failure.code for failure in report.domain_failures} == set(case["expectedDomainFailureCodes"])
    assert {item.capability_id for item in report.capabilities} == set(case["expectedCapabilityIds"])
    assert report.provenance is not None
    assert report.content_hash == report.provenance.request_hash

    for metric_id, expected in case["expectedMetrics"].items():
        result = report.metric_result(metric_id)
        assert result.status.value == expected["status"]
        _assert_value(result.value, expected["value"])
        if "unit" in expected:
            assert result.unit == expected["unit"]
        if "thresholdPassed" in expected:
            assert result.threshold_passed is expected["thresholdPassed"]
        if "reasonCode" in expected:
            assert result.reason_code == expected["reasonCode"]

    if "expectedScore" in case:
        assert report.score is not None
        assert report.score.status.value == case["expectedScore"]["status"]
        _assert_value(report.score.value, case["expectedScore"]["value"])

    if "expectedReferenceStrategyId" in case:
        reference_results = [
            result for result in report.metric_results if "referenceBinding" in result.details
        ]
        assert reference_results
        assert all(
            result.details["referenceBinding"]["strategyId"] == case["expectedReferenceStrategyId"]
            for result in reference_results
        )

    if "expectedProvenanceFields" in case:
        provenance = report.provenance.model_dump(mode="json", by_alias=True)
        for field in case["expectedProvenanceFields"]:
            assert provenance[field]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_cnc_fixture_replays_deterministically(case):
    payload = _load_request(case)

    first = evaluate(payload).model_dump(mode="json", by_alias=True)
    second = evaluate(payload).model_dump(mode="json", by_alias=True)

    assert first == second


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_cnc_fixture_runs_through_cli(case, capsys):
    request_path = SUITE_DIR / case["file"]

    exit_code = main(["evaluate", str(request_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == case["expectedExitCode"]
    assert output["executionStatus"] == case["expectedExecutionStatus"]
    assert output["caseOutcome"] == case["expectedCaseOutcome"]


def test_g1_sample_is_a_uniform_linear_move():
    payload = _load_request(next(case for case in CASES if "g1-linear" in case["id"]))
    points = payload["artifact"]["points"]

    assert all(point[1:] == [0.0, -2.0] for point in points)
    assert [point[0] for point in points] == list(range(0, 101, 10))
    assert _polyline_length(points) == 100.0


def test_g2_sample_is_a_clockwise_quarter_circle_in_g17_plane():
    payload = _load_request(next(case for case in CASES if case["id"].startswith("cnc-g2")))
    points = payload["artifact"]["points"]
    angles = [math.atan2(y, x) for x, y, _ in points]

    assert all(math.isclose(math.hypot(x, y), 20.0, abs_tol=1e-6) for x, y, _ in points)
    assert all(later < earlier for earlier, later in zip(angles, angles[1:]))
    assert _polyline_length(points) < math.pi * 20.0 / 2.0


def test_g3_circle_uses_closed_semantics_without_repeating_endpoint():
    payload = _load_request(next(case for case in CASES if "closed-circle" in case["id"]))
    points = payload["artifact"]["points"]
    closed_length = _polyline_length(points) + math.dist(points[-1], points[0])

    assert payload["artifact"]["semantics"]["closed"] is True
    assert points[0] != points[-1]
    assert all(math.isclose(math.hypot(x, y), 10.0, abs_tol=1e-6) for x, y, _ in points)
    expected = next(case for case in CASES if "closed-circle" in case["id"])
    assert math.isclose(
        closed_length,
        expected["expectedMetrics"]["path.length.closed"]["value"],
        abs_tol=ABS_TOL,
    )
    assert closed_length < 2.0 * math.pi * 10.0


def test_g3_helix_has_two_xy_turns_and_monotonic_z_descent():
    payload = _load_request(next(case for case in CASES if "helical" in case["id"]))
    points = payload["artifact"]["points"]
    z_values = [point[2] for point in points]
    sampled_length = _polyline_length(points)
    analytical_length = math.hypot(4.0 * math.pi * 10.0, 4.0)

    assert all(math.isclose(math.hypot(x, y), 10.0, abs_tol=1e-6) for x, y, _ in points)
    assert all(later < earlier for earlier, later in zip(z_values, z_values[1:]))
    assert points[0][:2] == points[8][:2] == points[16][:2]
    assert z_values[0] == 0.0 and z_values[-1] == -4.0
    assert sampled_length < analytical_length


def test_sampled_corner_contains_timing_jitter_but_remains_monotonic():
    payload = _load_request(next(case for case in CASES if "sampled-corner" in case["id"]))
    values = payload["artifact"]["parameter"]["values"]
    intervals = [end - start for start, end in zip(values, values[1:])]

    assert min(intervals) > 0
    assert statistics.pstdev(intervals) > 0
    assert math.isclose(statistics.mean(intervals), 4.05, abs_tol=ABS_TOL)


@pytest.mark.parametrize("expected_max", [0.025, 0.08])
def test_contour_observation_distances_are_independently_recomputed(expected_max):
    suffix = "pass" if expected_max == 0.025 else "fail"
    payload = _load_request(next(case for case in CASES if f"observation-{suffix}" in case["id"]))
    observed = payload["artifact"]["points"]
    reference = payload["referenceBinding"]["reference"]["points"]
    distances = [math.dist(actual, nominal) for actual, nominal in zip(observed, reference, strict=True)]

    expected_rms = math.sqrt(statistics.mean(distance * distance for distance in distances))
    report = evaluate(payload)

    assert math.isclose(max(distances), expected_max, abs_tol=ABS_TOL)
    assert math.isclose(report.metric_result("paired.euclidean.rms").value, expected_rms, abs_tol=ABS_TOL)
    expected_score = 100.0 * max(0.0, min(1.0, (0.05 - expected_max) / 0.05))
    assert math.isclose(report.score.value, expected_score, abs_tol=ABS_TOL)
