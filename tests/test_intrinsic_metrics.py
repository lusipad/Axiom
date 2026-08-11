import math

from hypothesis import given, strategies as st

from axiom import CaseOutcome, evaluate


def test_step_statistics_and_bounds(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4], [3, 12]],
            [
                "bounds.axis_aligned",
                "step.length.min",
                "step.length.max",
                "step.length.mean",
                "step.length.rms",
                "step.length.std",
            ],
            semantics={"unit": "mm"},
        )
    )

    assert report.metric_result("bounds.axis_aligned").value == {"min": [0.0, 0.0], "max": [3.0, 12.0]}
    assert report.metric_result("step.length.min").value == 5
    assert report.metric_result("step.length.max").value == 8
    assert report.metric_result("step.length.mean").value == 6.5
    assert math.isclose(report.metric_result("step.length.rms").value, math.sqrt(44.5))
    assert report.metric_result("step.length.std").value == 1.5
    assert report.metric_result("step.length.mean").unit == "mm"


@given(
    dx=st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
    dy=st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
)
def test_translation_preserves_open_path_length(dx, dy):
    original = [[0.0, 0.0], [3.0, 4.0], [5.0, 4.0]]
    translated = [[x + dx, y + dy] for x, y in original]

    def request(points):
        return {
            "artifact": {
                "artifactType": "ordered-point-sequence",
                "schemaVersion": 1,
                "points": points,
            },
            "case": {
                "caseId": "translation-invariance@1",
                "requiredMetrics": ["path.length.open"],
            },
        }

    first = evaluate(request(original))
    second = evaluate(request(translated))

    assert first.case_outcome is CaseOutcome.PASSED
    assert math.isclose(
        first.metric_result("path.length.open").value,
        second.metric_result("path.length.open").value,
        rel_tol=1e-12,
        abs_tol=1e-9,
    )


def test_single_point_keeps_structure_metrics_but_cannot_define_path(make_request):
    report = evaluate(
        make_request(
            [[1, 2]],
            ["point.count"],
            optional=["path.length.open"],
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("point.count").value == 1
    assert report.metric_result("path.length.open").status.value == "NotApplicable"


def test_three_dimensional_structure_facts_are_computed(make_request):
    report = evaluate(
        make_request(
            [[0, 0, 0], [1, 2, 3]],
            ["coordinate.dimension", "coordinate.finite"],
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("coordinate.dimension").value == 3
    assert report.metric_result("coordinate.finite").value is True


def test_rigid_rotation_preserves_euclidean_geometry(make_request):
    metrics = ["path.length.open", "closure.gap", "step.length.mean"]
    original = evaluate(make_request([[0, 0], [3, 4], [5, 4]], metrics))
    rotated = evaluate(make_request([[0, 0], [-4, 3], [-4, 5]], metrics))

    for metric_id in metrics:
        assert math.isclose(
            original.metric_result(metric_id).value,
            rotated.metric_result(metric_id).value,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )


def test_uniform_scale_changes_lengths_by_the_same_factor(make_request):
    metrics = ["point.count", "path.length.open", "closure.gap"]
    original = evaluate(make_request([[0, 0], [3, 4]], metrics))
    scaled = evaluate(make_request([[0, 0], [6, 8]], metrics))

    assert scaled.metric_result("point.count").value == original.metric_result("point.count").value
    assert scaled.metric_result("path.length.open").value == 2 * original.metric_result("path.length.open").value
    assert scaled.metric_result("closure.gap").value == 2 * original.metric_result("closure.gap").value


def test_reversing_sequence_preserves_undirected_length_metrics(make_request):
    metrics = ["path.length.open", "closure.gap", "step.length.max"]
    points = [[0, 0], [3, 4], [3, 12]]
    forward = evaluate(make_request(points, metrics))
    reverse = evaluate(make_request(list(reversed(points)), metrics))

    for metric_id in metrics:
        assert forward.metric_result(metric_id).value == reverse.metric_result(metric_id).value
