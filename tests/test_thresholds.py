import pytest

from axiom import CaseOutcome, ExecutionStatus, MetricStatus, evaluate


def test_threshold_converts_compatible_units_before_comparison(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [10, 0]],
            [
                {
                    "metricId": "path.length.open",
                    "threshold": {"operator": "<=", "value": 1, "unit": "cm"},
                }
            ],
            semantics={"unit": "mm"},
        )
    )

    result = report.metric_result("path.length.open")
    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.case_outcome is CaseOutcome.PASSED
    assert result.value == 10
    assert result.unit == "mm"
    assert result.threshold_passed is True


def test_incompatible_threshold_unit_makes_the_metric_not_applicable(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [10, 0]],
            [
                {
                    "metricId": "path.length.open",
                    "threshold": {"operator": "<=", "value": 1, "unit": "s"},
                }
            ],
            semantics={"unit": "mm"},
        )
    )

    result = report.metric_result("path.length.open")
    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert result.status is MetricStatus.NOT_APPLICABLE
    assert result.reason_code == "ThresholdUnitIncompatible"


def test_physical_threshold_on_dimensionless_metric_is_invalid(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            [
                {
                    "metricId": "point.count",
                    "threshold": {"operator": "<=", "value": 1, "unit": "mm"},
                }
            ],
        )
    )

    result = report.metric_result("point.count")
    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert result.status is MetricStatus.NOT_APPLICABLE
    assert result.reason_code == "ThresholdUnitIncompatible"


def test_physical_time_threshold_without_time_unit_is_insufficient_context(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            [
                {
                    "metricId": "parameter.interval.mean",
                    "threshold": {"operator": "<=", "value": 2, "unit": "s"},
                }
            ],
            parameter={"kind": "time", "values": [0, 1]},
        )
    )

    result = report.metric_result("parameter.interval.mean")
    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert result.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert result.reason_code == "PhysicalThresholdRequiresKnownUnit"


@pytest.mark.parametrize(
    ("operator", "limit", "expected"),
    [("<=", 5, True), ("<", 5, False), (">=", 5, True), (">", 5, False)],
)
def test_all_threshold_operators_have_frozen_boundary_semantics(make_request, operator, limit, expected):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            [
                {
                    "metricId": "path.length.open",
                    "threshold": {"operator": operator, "value": limit},
                }
            ],
        )
    )

    assert report.metric_result("path.length.open").threshold_passed is expected
    assert report.case_outcome is (CaseOutcome.PASSED if expected else CaseOutcome.FAILED)
