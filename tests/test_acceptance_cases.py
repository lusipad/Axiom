from axiom import CaseOutcome, ExecutionStatus, MetricStatus, evaluate


def test_ops_c01_unitless_intrinsic_metrics(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["point.count", "path.length.open", "closure.gap"],
            case_id="OPS-C01",
        )
    )

    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("point.count").value == 2
    assert report.metric_result("path.length.open").value == 5
    assert report.metric_result("path.length.open").unit == "coordinate-unit"
    assert report.metric_result("closure.gap").value == 5


def test_ops_c02_closed_length_without_declaration(make_request):
    report = evaluate(make_request([[0, 0], [3, 4]], ["path.length.closed"], case_id="OPS-C02"))

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert report.metric_result("path.length.closed").status is MetricStatus.INSUFFICIENT_CONTEXT


def test_ops_c03_closed_length_explicitly_not_applicable(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["path.length.closed"],
            semantics={"closed": False},
            case_id="OPS-C03",
        )
    )

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert report.metric_result("path.length.closed").status is MetricStatus.NOT_APPLICABLE


def test_ops_c04_closed_length(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["path.length.closed"],
            semantics={"closed": True},
            case_id="OPS-C04",
        )
    )

    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("path.length.closed").value == 10
    assert report.metric_result("path.length.closed").unit == "coordinate-unit"


def test_ops_c05_physical_threshold_without_physical_unit(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            [
                {
                    "metricId": "path.length.open",
                    "threshold": {"operator": "<=", "value": 6, "unit": "mm"},
                }
            ],
            case_id="OPS-C05",
        )
    )

    result = report.metric_result("path.length.open")
    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert result.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert result.value is None


def test_ops_c06_bound_but_unsupported_reference_strategy(make_request):
    reference = {
        "artifactType": "ordered-point-sequence",
        "schemaVersion": 1,
        "points": [[0, 0], [1, 0]],
    }
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["hausdorff.discrete"],
            reference_binding={
                "reference": reference,
                "alignment": "ordered-point.alignment.identity@1",
                "strategyId": "vendor.correspondence.unknown@1",
                "distanceId": "ordered-point.distance.euclidean@1",
                "tolerance": {
                    "policyId": "ordered-point.tolerance.absolute@1",
                    "value": 1e-12,
                    "unit": "coordinate-unit",
                },
                "boundaryPolicy": "ordered-point.boundary.finite-sequence@1",
            },
            case_id="OPS-C06",
        )
    )

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert report.metric_result("hausdorff.discrete").status is MetricStatus.UNSUPPORTED_CAPABILITY
