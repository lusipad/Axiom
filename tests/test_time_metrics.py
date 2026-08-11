from axiom import CaseOutcome, MetricStatus, evaluate


def test_time_interval_metrics(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0], [2, 0]],
            [
                "parameter.interval.min",
                "parameter.interval.max",
                "parameter.interval.mean",
                "parameter.interval.std",
            ],
            parameter={"kind": "time", "unit": "s", "values": [0, 0.5, 1.5]},
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("parameter.interval.min").value == 0.5
    assert report.metric_result("parameter.interval.max").value == 1
    assert report.metric_result("parameter.interval.mean").value == 0.75
    assert report.metric_result("parameter.interval.std").value == 0.25
    assert report.metric_result("parameter.interval.mean").unit == "s"


def test_time_metric_without_parameter_is_insufficient_context(make_request):
    report = evaluate(make_request([[0, 0], [1, 0]], ["parameter.interval.mean"]))

    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert report.metric_result("parameter.interval.mean").status is MetricStatus.INSUFFICIENT_CONTEXT


def test_parameter_interval_without_time_unit_uses_parameter_unit(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["parameter.interval.mean"],
            parameter={"kind": "time", "values": [0, 1]},
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("parameter.interval.mean").status is MetricStatus.COMPUTED
    assert report.metric_result("parameter.interval.mean").value == 1
    assert report.metric_result("parameter.interval.mean").unit == "parameter-unit"


def test_single_timestamp_cannot_define_an_interval(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["parameter.interval.mean"],
            parameter={"kind": "time", "unit": "s", "values": [0]},
        )
    )

    result = report.metric_result("parameter.interval.mean")
    assert report.execution_status.value == "Skipped"
    assert report.case_outcome is CaseOutcome.INVALID
    assert result.status is MetricStatus.NOT_APPLICABLE
    assert result.reason_code == "MinimumPointCountNotMet"


def test_finite_timestamps_that_overflow_an_interval_report_numerical_failure(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["parameter.interval.mean"],
            parameter={"kind": "time", "unit": "s", "values": [-1e308, 1e308]},
        )
    )

    result = report.metric_result("parameter.interval.mean")
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert result.status is MetricStatus.NUMERICAL_FAILURE
    assert result.reason_code == "NonFiniteComputation"
