import math

import pytest

from axiom import CaseOutcome, ExecutionStatus, MetricStatus, evaluate
from axiom.models import MAX_SEQUENCE_POINTS


@pytest.mark.parametrize(
    ("points", "failure_code"),
    [
        ([], "EmptySequence"),
        ([[0, 0], [1, 2, 3]], "InconsistentDimension"),
        ([[0, 0, 0, 0]], "UnsupportedDimension"),
        ([[0, math.nan]], "NonFiniteCoordinate"),
        ([[0, math.inf]], "NonFiniteCoordinate"),
    ],
)
def test_invalid_point_sequences_are_not_repaired(make_request, points, failure_code):
    report = evaluate(make_request(points, ["point.count"]))

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert failure_code in {failure.code for failure in report.domain_failures}


def test_sequence_point_count_is_bounded_before_evaluation(make_request):
    points = [[0, 0]] * (MAX_SEQUENCE_POINTS + 1)

    report = evaluate(make_request(points, ["point.count"]))

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert report.domain_failures[0].code == "MalformedRequest"
    assert report.domain_failures[0].path == "artifact.points"


def test_parameter_value_count_uses_the_same_sequence_bound(make_request):
    parameter = {
        "kind": "time",
        "values": [0.0] * (MAX_SEQUENCE_POINTS + 1),
    }

    report = evaluate(make_request([[0, 0]], ["point.count"], parameter=parameter))

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert report.domain_failures[0].code == "MalformedRequest"
    assert report.domain_failures[0].path == "artifact.parameter.values"


def test_finite_coordinates_that_overflow_a_distance_report_numerical_failure(make_request):
    report = evaluate(
        make_request(
            [[1e308, 0], [-1e308, 0]],
            ["path.length.open"],
        )
    )

    result = report.metric_result("path.length.open")
    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert result.status is MetricStatus.NUMERICAL_FAILURE
    assert result.reason_code == "NonFiniteComputation"
    assert result.value is None


def test_duplicate_points_are_reported_but_remain_valid(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [0, 0], [1, 0]],
            ["duplicate.consecutive.count", "segment.zero_length.count"],
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("duplicate.consecutive.count").value == 1
    assert report.metric_result("segment.zero_length.count").value == 1
    assert "ConsecutiveDuplicate" in {failure.code for failure in report.domain_failures}


def test_coordinate_unit_marker_cannot_be_submitted(make_request):
    report = evaluate(
        make_request([[0, 0], [1, 0]], ["path.length.open"], semantics={"unit": "coordinate-unit"})
    )

    assert report.case_outcome is CaseOutcome.INVALID
    assert "InvalidUnit" in {failure.code for failure in report.domain_failures}


def test_explicit_empty_coordinate_unit_is_invalid(make_request):
    report = evaluate(make_request([[0, 0]], ["point.count"], semantics={"unit": ""}))

    assert report.case_outcome is CaseOutcome.INVALID
    assert "InvalidUnit" in {failure.code for failure in report.domain_failures}


def test_explicit_empty_time_unit_is_invalid(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["point.count"],
            parameter={"kind": "time", "unit": "", "values": [0]},
        )
    )

    assert report.case_outcome is CaseOutcome.INVALID
    assert "InvalidParameterUnit" in {failure.code for failure in report.domain_failures}


def test_coordinate_unit_must_have_length_dimension(make_request):
    report = evaluate(make_request([[0, 0]], ["point.count"], semantics={"unit": "s"}))

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert "InvalidUnit" in {failure.code for failure in report.domain_failures}


def test_time_parameter_unit_must_have_time_dimension(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["point.count"],
            parameter={"kind": "time", "unit": "mm", "values": [0, 1]},
        )
    )

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert "InvalidParameterUnit" in {failure.code for failure in report.domain_failures}


def test_all_identical_points_remain_valid_and_report_zero_geometry(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [0, 0], [0, 0]],
            [
                "duplicate.consecutive.count",
                "segment.zero_length.count",
                "path.length.open",
                "closure.gap",
            ],
        )
    )

    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("duplicate.consecutive.count").value == 2
    assert report.metric_result("segment.zero_length.count").value == 2
    assert report.metric_result("path.length.open").value == 0
    assert report.metric_result("closure.gap").value == 0
    assert "ConsecutiveDuplicate" in {failure.code for failure in report.domain_failures}


@pytest.mark.parametrize(
    ("parameter", "failure_code"),
    [
        ({"kind": "time", "unit": "s", "values": [0]}, "ParameterLengthMismatch"),
        ({"kind": "time", "unit": "s", "values": [0, 0]}, "NonMonotoneParameter"),
        ({"kind": "time", "unit": "s", "values": [0, -1]}, "NonMonotoneParameter"),
        ({"kind": "time", "unit": "s", "values": [0, math.nan]}, "NonFiniteParameter"),
    ],
)
def test_invalid_time_parameters(make_request, parameter, failure_code):
    report = evaluate(make_request([[0, 0], [1, 0]], ["point.count"], parameter=parameter))

    assert report.case_outcome is CaseOutcome.INVALID
    assert failure_code in {failure.code for failure in report.domain_failures}


def test_malformed_request_returns_a_structured_invalid_report():
    report = evaluate({"artifact": {"points": "not-a-list"}})

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert report.domain_failures[0].code == "MalformedRequest"


@pytest.mark.parametrize("coordinate", [True, "1.0"])
def test_coordinates_are_json_numbers_not_coerced_values(make_request, coordinate):
    report = evaluate(make_request([[0, coordinate]], ["point.count"]))

    assert report.case_outcome is CaseOutcome.INVALID
    assert report.domain_failures[0].code == "MalformedRequest"


def test_duplicate_metric_requests_make_the_case_invalid(make_request):
    report = evaluate(make_request([[0, 0]], ["point.count", "point.count"]))

    assert report.case_outcome is CaseOutcome.INVALID
    assert "DuplicateMetricRequest" in {failure.code for failure in report.domain_failures}


def test_scalar_threshold_cannot_be_applied_to_structured_bounds(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            [
                {
                    "metricId": "bounds.axis_aligned",
                    "threshold": {"operator": "<=", "value": 1},
                }
            ],
        )
    )

    assert report.case_outcome is CaseOutcome.INVALID
    assert report.metric_result("bounds.axis_aligned").status.value == "NotApplicable"


def test_unknown_required_metric_is_an_unsupported_capability(make_request):
    report = evaluate(make_request([[0, 0]], ["vendor.metric.unknown@1"]))

    result = report.metric_result("vendor.metric.unknown@1")
    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert result.status.value == "UnsupportedCapability"
    assert result.reason_code == "UnknownMetricDefinition"


def test_unavailable_optional_metric_does_not_change_a_passed_case(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["point.count"],
            optional=["vendor.metric.unknown@1"],
        )
    )

    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("vendor.metric.unknown@1").status.value == "UnsupportedCapability"
