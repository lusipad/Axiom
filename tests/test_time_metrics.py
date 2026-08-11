import copy

import pytest

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


def test_kinematic_metrics_compute_expected_values_and_units(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4], [6, 4], [6, 0]],
            ["speed.point.mean", "acceleration.point.max"],
            parameter={"kind": "time", "unit": "s", "values": [0, 1, 3, 6]},
        )
    )

    speed = report.metric_result("speed.point.mean")
    acceleration = report.metric_result("acceleration.point.max")

    assert report.case_outcome is CaseOutcome.PASSED
    assert speed.status is MetricStatus.COMPUTED
    assert speed.value == pytest.approx(2.611111111111111)
    assert speed.unit == "coordinate-unit/s"
    assert acceleration.status is MetricStatus.COMPUTED
    assert acceleration.value == pytest.approx(2.848001248439177)
    assert acceleration.unit == "coordinate-unit/s^2"


def test_kinematic_metrics_without_time_unit_are_insufficient_context(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0], [3, 0]],
            ["speed.point.mean", "acceleration.point.max"],
            parameter={"kind": "time", "values": [0, 1, 3]},
        )
    )

    speed = report.metric_result("speed.point.mean")
    acceleration = report.metric_result("acceleration.point.max")

    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert speed.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert speed.reason_code == "TimeUnitMissing"
    assert acceleration.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert acceleration.reason_code == "TimeUnitMissing"


def test_acceleration_requires_three_samples(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["speed.point.mean", "acceleration.point.max"],
            parameter={"kind": "time", "unit": "s", "values": [0, 1]},
        )
    )

    assert report.metric_result("speed.point.mean").status is MetricStatus.COMPUTED
    acceleration = report.metric_result("acceleration.point.max")
    assert acceleration.status is MetricStatus.NOT_APPLICABLE
    assert acceleration.reason_code == "MinimumPointCountNotMet"


def test_kinematic_metrics_are_translation_invariant(make_request):
    base = make_request(
        [[0, 0], [3, 4], [6, 4], [6, 0]],
        ["speed.point.mean", "acceleration.point.max"],
        parameter={"kind": "time", "unit": "s", "values": [0, 1, 3, 6]},
    )
    translated = make_request(
        [[10, -2], [13, 2], [16, 2], [16, -2]],
        ["speed.point.mean", "acceleration.point.max"],
        parameter={"kind": "time", "unit": "s", "values": [0, 1, 3, 6]},
    )

    base_report = evaluate(base)
    translated_report = evaluate(translated)

    assert translated_report.metric_result("speed.point.mean").value == pytest.approx(
        base_report.metric_result("speed.point.mean").value
    )
    assert translated_report.metric_result("acceleration.point.max").value == pytest.approx(
        base_report.metric_result("acceleration.point.max").value
    )


def test_explicit_parameter_policies_freeze_request_hash_without_changing_values(make_request):
    request = make_request(
        [[0, 0], [3, 4], [6, 4], [6, 0]],
        ["speed.point.mean", "acceleration.point.max"],
        parameter={"kind": "time", "unit": "s", "values": [0, 1, 3, 6]},
    )
    explicit_request = copy.deepcopy(request)
    explicit_request["artifact"]["parameter"]["differencePolicy"] = {
        "policyId": "ordered-point.parameter-difference.forward-adjacent@1"
    }
    explicit_request["artifact"]["parameter"]["endpointPolicy"] = {
        "policyId": "ordered-point.parameter-endpoint.interval-only@1"
    }

    implicit_report = evaluate(request)
    explicit_report = evaluate(explicit_request)

    assert implicit_report.metric_result("speed.point.mean").value == pytest.approx(
        explicit_report.metric_result("speed.point.mean").value
    )
    assert implicit_report.metric_result("acceleration.point.max").value == pytest.approx(
        explicit_report.metric_result("acceleration.point.max").value
    )
    assert implicit_report.provenance is not None
    assert explicit_report.provenance is not None
    assert implicit_report.provenance.request_hash != explicit_report.provenance.request_hash


@pytest.mark.parametrize(
    ("field", "policy_id"),
    [
        ("differencePolicy", "ordered-point.parameter-difference.central@1"),
        ("endpointPolicy", "ordered-point.parameter-endpoint.extrapolated@1"),
    ],
)
def test_unimplemented_parameter_policies_are_rejected(make_request, field, policy_id):
    request = make_request(
        [[0, 0], [1, 0], [3, 0]],
        ["speed.point.mean"],
        parameter={"kind": "time", "unit": "s", "values": [0, 1, 3]},
    )
    request["artifact"]["parameter"][field] = {"policyId": policy_id}

    report = evaluate(request)

    assert report.case_outcome is CaseOutcome.INVALID
    assert report.domain_failures[0].code == "MalformedRequest"
    assert report.domain_failures[0].path == f"artifact.parameter.{field}.policyId"
