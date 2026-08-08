import math

import axiom.evaluator as evaluator_module
from axiom import CaseOutcome, ExecutionStatus, MetricStatus, evaluate


def _reference(points, *, unit=None, frame=None):
    artifact = {
        "artifactType": "ordered-point-sequence",
        "schemaVersion": 1,
        "points": points,
    }
    if unit is not None or frame is not None:
        artifact["semantics"] = {}
        if unit is not None:
            artifact["semantics"]["unit"] = unit
        if frame is not None:
            artifact["semantics"]["coordinateFrame"] = frame
    return artifact


def _binding(points, strategy, *, unit=None, frame=None, **overrides):
    binding = {
        "reference": _reference(points, unit=unit, frame=frame),
        "alignment": "ordered-point.alignment.identity@1",
        "strategyId": strategy,
        "distanceId": "ordered-point.distance.euclidean@1",
        "tolerance": {
            "policyId": "ordered-point.tolerance.absolute@1",
            "value": 1e-12,
            "unit": unit or "coordinate-unit",
        },
        "boundaryPolicy": "ordered-point.boundary.finite-sequence@1",
    }
    binding.update(overrides)
    return binding


def test_index_paired_metrics_convert_compatible_units(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [10, 0]],
            ["paired.euclidean.rms", "paired.euclidean.max"],
            semantics={"unit": "mm", "coordinateFrame": "workpiece"},
            reference_binding=_binding(
                [[0, 0], [1, 0]],
                "ordered-point.correspondence.index-paired@1",
                unit="cm",
                frame="workpiece",
            ),
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.metric_result("paired.euclidean.rms").value == 0
    assert report.metric_result("paired.euclidean.rms").unit == "mm"
    binding_details = report.metric_result("paired.euclidean.rms").details["referenceBinding"]
    assert binding_details["strategyId"] == "ordered-point.correspondence.index-paired@1"
    assert binding_details["tolerance"]["valueInResultUnit"] == 1e-11


def test_paired_metric_rejects_unequal_point_counts(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["paired.euclidean.max"],
            reference_binding=_binding([[0, 0]], "ordered-point.correspondence.index-paired@1"),
        )
    )

    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.metric_result("paired.euclidean.max").status is MetricStatus.INVALID_OBSERVATION
    assert "UndefinedCorrespondence" in {failure.code for failure in report.domain_failures}


def test_nearest_directed_tie_breaks_to_smallest_reference_index(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["nearest.directed.max"],
            reference_binding=_binding(
                [[-1, 0], [1, 0]],
                "ordered-point.correspondence.nearest-directed@1",
            ),
        )
    )

    result = report.metric_result("nearest.directed.max")
    assert result.value == 1
    assert result.details["witness"] == {"observedIndex": 0, "referenceIndex": 0, "tieCount": 2}


def test_discrete_hausdorff_uses_lexicographically_smallest_witness(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [2, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding([[1, 0]], "ordered-point.correspondence.discrete-hausdorff@1"),
        )
    )

    result = report.metric_result("hausdorff.discrete")
    assert result.value == 1
    assert result.details["witness"] == {"observedIndex": 0, "referenceIndex": 0}


def test_discrete_frechet_reports_value_and_coupling_path(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["frechet.discrete"],
            reference_binding=_binding(
                [[0, 0], [2, 0]],
                "ordered-point.correspondence.discrete-frechet@1",
            ),
        )
    )

    result = report.metric_result("frechet.discrete")
    assert math.isclose(result.value, 1)
    assert result.details["couplingPath"] == [[0, 0], [1, 0], [1, 1]]


def test_reference_dimension_mismatch_is_an_invalid_binding(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding(
                [[0, 0, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
            ),
        )
    )

    assert report.case_outcome is CaseOutcome.INVALID
    assert "ReferenceDimensionMismatch" in {failure.code for failure in report.domain_failures}


def test_reference_metric_without_binding_is_insufficient_context(make_request):
    report = evaluate(make_request([[0, 0]], ["hausdorff.discrete"]))

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    result = report.metric_result("hausdorff.discrete")
    assert result.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert result.reason_code == "ReferenceBindingMissing"


def test_metric_and_correspondence_strategy_must_match(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding(
                [[0, 0]],
                "ordered-point.correspondence.nearest-directed@1",
            ),
        )
    )

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert report.metric_result("hausdorff.discrete").status is MetricStatus.NOT_APPLICABLE
    assert "UndefinedCorrespondence" in {failure.code for failure in report.domain_failures}


def test_nearest_directed_max_uses_smallest_observed_index_on_a_tie(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [2, 0]],
            ["nearest.directed.max"],
            reference_binding=_binding(
                [[1, 0]],
                "ordered-point.correspondence.nearest-directed@1",
            ),
        )
    )

    assert report.metric_result("nearest.directed.max").details["witness"] == {
        "observedIndex": 0,
        "referenceIndex": 0,
        "tieCount": 1,
    }


def test_hausdorff_tie_across_both_directions_uses_lexicographic_witness(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [4, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding(
                [[1, 0], [3, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
            ),
        )
    )

    assert report.metric_result("hausdorff.discrete").details["witness"] == {
        "observedIndex": 0,
        "referenceIndex": 0,
    }


def test_one_sided_physical_unit_is_insufficient_reference_context(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            semantics={"unit": "mm"},
            reference_binding=_binding(
                [[0, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
            ),
        )
    )

    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    result = report.metric_result("hausdorff.discrete")
    assert result.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert result.reason_code == "ReferenceUnitContextIncomplete"


def test_physical_reference_comparison_requires_frames_on_both_sides(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            semantics={"unit": "mm", "coordinateFrame": "workpiece"},
            reference_binding=_binding(
                [[1, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
                unit="mm",
            ),
        )
    )

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert report.metric_result("hausdorff.discrete").reason_code == "ReferenceFrameContextIncomplete"


def test_conflicting_frames_make_identity_alignment_invalid(make_request):
    binding = _binding(
        [[0, 0]],
        "ordered-point.correspondence.discrete-hausdorff@1",
    )
    binding["reference"]["semantics"] = {"coordinateFrame": "machine"}
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            semantics={"coordinateFrame": "workpiece"},
            reference_binding=binding,
        )
    )

    assert report.case_outcome is CaseOutcome.INVALID
    assert "ProfileConflict" in {failure.code for failure in report.domain_failures}


def test_unsupported_alignment_is_distinct_from_missing_context(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding(
                [[0, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
                alignment="vendor.alignment.rigid@1",
            ),
        )
    )

    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert report.metric_result("hausdorff.discrete").reason_code == "UnsupportedAlignment"


def test_unsupported_alignment_takes_priority_over_incomplete_unit_context(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            semantics={"unit": "mm"},
            reference_binding=_binding(
                [[0, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
                alignment="vendor.alignment.rigid@1",
            ),
        )
    )

    result = report.metric_result("hausdorff.discrete")
    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert result.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert result.reason_code == "UnsupportedAlignment"


def test_unsupported_distance_is_distinct_from_missing_context(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding(
                [[0, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
                distanceId="vendor.distance.custom@1",
            ),
        )
    )

    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert report.metric_result("hausdorff.discrete").reason_code == "UnsupportedDistanceDefinition"


def test_unsupported_tolerance_policy_is_reported_as_capability_gap(make_request):
    binding = _binding(
        [[0, 0]],
        "ordered-point.correspondence.discrete-hausdorff@1",
    )
    binding["tolerance"]["policyId"] = "vendor.tolerance.custom@1"
    report = evaluate(make_request([[0, 0]], ["hausdorff.discrete"], reference_binding=binding))

    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert report.metric_result("hausdorff.discrete").reason_code == "UnsupportedTolerancePolicy"


def test_unsupported_boundary_policy_is_reported_as_capability_gap(make_request):
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding(
                [[0, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
                boundaryPolicy="vendor.boundary.custom@1",
            ),
        )
    )

    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert report.metric_result("hausdorff.discrete").reason_code == "UnsupportedBoundaryPolicy"


def test_unversioned_reference_policy_makes_the_case_invalid(make_request):
    binding = _binding(
        [[0, 0]],
        "ordered-point.correspondence.discrete-hausdorff@1",
    )
    binding["strategyId"] = "ordered-point.correspondence.discrete-hausdorff"
    report = evaluate(make_request([[0, 0]], ["hausdorff.discrete"], reference_binding=binding))

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert "UnversionedReferencePolicy" in {failure.code for failure in report.domain_failures}
    assert report.metric_result("hausdorff.discrete").status is MetricStatus.INVALID_OBSERVATION


def test_non_length_reference_tolerance_unit_is_invalid(make_request):
    binding = _binding(
        [[0, 0]],
        "ordered-point.correspondence.discrete-hausdorff@1",
    )
    binding["tolerance"]["unit"] = "s"
    report = evaluate(make_request([[0, 0]], ["hausdorff.discrete"], reference_binding=binding))

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INVALID
    assert "InvalidToleranceUnit" in {failure.code for failure in report.domain_failures}


def test_physical_reference_requires_a_physical_tolerance(make_request):
    binding = _binding(
        [[0, 0]],
        "ordered-point.correspondence.discrete-hausdorff@1",
        unit="mm",
        frame="workpiece",
    )
    binding["tolerance"]["unit"] = "coordinate-unit"
    report = evaluate(
        make_request(
            [[0, 0]],
            ["hausdorff.discrete"],
            semantics={"unit": "mm", "coordinateFrame": "workpiece"},
            reference_binding=binding,
        )
    )

    result = report.metric_result("hausdorff.discrete")
    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert result.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert result.reason_code == "ReferenceToleranceContextIncomplete"


def test_discrete_hausdorff_value_is_symmetric(make_request):
    strategy = "ordered-point.correspondence.discrete-hausdorff@1"
    first = evaluate(
        make_request(
            [[0, 0], [4, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding([[1, 0]], strategy),
        )
    )
    second = evaluate(
        make_request(
            [[1, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding([[0, 0], [4, 0]], strategy),
        )
    )

    assert first.metric_result("hausdorff.discrete").value == 3
    assert second.metric_result("hausdorff.discrete").value == 3


def test_nearest_directed_mean_preserves_direction(make_request):
    strategy = "ordered-point.correspondence.nearest-directed@1"
    forward = evaluate(
        make_request(
            [[0, 0], [10, 0]],
            ["nearest.directed.mean"],
            reference_binding=_binding([[0, 0], [1, 0]], strategy),
        )
    )
    reverse = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["nearest.directed.mean"],
            reference_binding=_binding([[0, 0], [10, 0]], strategy),
        )
    )

    assert forward.metric_result("nearest.directed.mean").value == 4.5
    assert reverse.metric_result("nearest.directed.mean").value == 0.5


def test_reference_tolerance_does_not_turn_nearby_distances_into_a_tie(make_request):
    binding = _binding(
        [[1.0, 0], [1.0 + 5e-7, 0]],
        "ordered-point.correspondence.nearest-directed@1",
    )
    binding["tolerance"]["value"] = 1e-6
    report = evaluate(make_request([[0, 0]], ["nearest.directed.max"], reference_binding=binding))

    assert report.metric_result("nearest.directed.max").details["witness"] == {
        "observedIndex": 0,
        "referenceIndex": 0,
        "tieCount": 1,
    }


def test_pairwise_distance_budget_is_reported_as_an_unsupported_capability(make_request, monkeypatch):
    monkeypatch.setattr(evaluator_module, "_MAX_PAIRWISE_CELLS", 3)
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["hausdorff.discrete"],
            reference_binding=_binding(
                [[0, 0], [1, 0]],
                "ordered-point.correspondence.discrete-hausdorff@1",
            ),
        )
    )

    result = report.metric_result("hausdorff.discrete")
    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert result.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert result.reason_code == "ComplexityBudgetExceeded"
    assert result.details == {
        "budgetKind": "pairwise-distance-cells",
        "requested": 4,
        "limit": 3,
    }


def test_frechet_path_budget_is_checked_before_allocating_the_distance_matrix(make_request, monkeypatch):
    monkeypatch.setattr(evaluator_module, "_MAX_FRECHET_PATH_BUDGET", 15)
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["frechet.discrete"],
            reference_binding=_binding(
                [[0, 0], [1, 0]],
                "ordered-point.correspondence.discrete-frechet@1",
            ),
        )
    )

    result = report.metric_result("frechet.discrete")
    assert report.case_outcome is CaseOutcome.UNSUPPORTED
    assert result.reason_code == "ComplexityBudgetExceeded"
    assert result.details == {
        "budgetKind": "frechet-path-storage",
        "requested": 16,
        "limit": 15,
    }


def test_finite_reference_coordinates_that_overflow_report_numerical_failure(make_request):
    report = evaluate(
        make_request(
            [[1e308, 0]],
            ["paired.euclidean.max"],
            reference_binding=_binding(
                [[-1e308, 0]],
                "ordered-point.correspondence.index-paired@1",
            ),
        )
    )

    result = report.metric_result("paired.euclidean.max")
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert result.status is MetricStatus.NUMERICAL_FAILURE
    assert result.reason_code == "NonFiniteComputation"
