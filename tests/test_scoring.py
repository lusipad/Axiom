from axiom import CaseOutcome, MetricStatus, evaluate


PROFILE = {
    "profileId": "demo.geometry-score@1",
    "applicableContext": "unit-test",
    "rules": [
        {
            "metricId": "path.length.open",
            "direction": "lower-is-better",
            "best": 0,
            "worst": 10,
            "weight": 1,
        }
    ],
}


def test_no_profile_means_no_total_score(make_request):
    report = evaluate(make_request([[0, 0], [3, 4]], ["path.length.open"]))

    assert report.score is None


def test_explicit_versioned_profile_computes_a_bounded_score(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["path.length.open"],
            score_profile=PROFILE,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.COMPUTED
    assert report.score.value == 50
    assert report.score.profile_id == "demo.geometry-score@1"


def test_score_combines_mixed_directions_using_declared_weights(make_request):
    profile = {
        "profileId": "mixed-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "path.length.open",
                "direction": "lower-is-better",
                "best": 0,
                "worst": 10,
                "weight": 3,
            },
            {
                "metricId": "point.count",
                "direction": "higher-is-better",
                "best": 2,
                "worst": 0,
                "weight": 1,
            },
        ],
    }
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["path.length.open", "point.count"],
            score_profile=profile,
        )
    )

    assert report.score.status is MetricStatus.COMPUTED
    assert report.score.value == 62.5
    assert [component.normalized_value for component in report.score.components] == [0.5, 1.0]
    assert [component.weight for component in report.score.components] == [3.0, 1.0]


def test_one_unavailable_rule_rejects_the_whole_score(make_request):
    profile = {
        "profileId": "incomplete-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "point.count",
                "direction": "higher-is-better",
                "best": 2,
                "worst": 0,
                "weight": 1,
            },
            {
                "metricId": "hausdorff.discrete",
                "direction": "lower-is-better",
                "best": 0,
                "worst": 1,
                "weight": 1,
            },
        ],
    }
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["point.count"],
            optional=["hausdorff.discrete"],
            score_profile=profile,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert report.score.reason_code == "ScoreMetricUnavailable"
    assert report.score.value is None


def test_score_reports_numerical_failure_when_endpoint_span_overflows(make_request):
    profile = {
        "profileId": "overflow-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "point.count",
                "direction": "lower-is-better",
                "best": -1e308,
                "worst": 1e308,
                "weight": 1,
            }
        ],
    }
    report = evaluate(make_request([[0, 0]], ["point.count"], score_profile=profile))

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.NUMERICAL_FAILURE
    assert report.score.reason_code == "NonFiniteComputation"
    assert report.score.value is None


def test_score_does_not_override_a_failed_hard_gate(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            [
                {
                    "metricId": "path.length.open",
                    "threshold": {"operator": "<=", "value": 4},
                }
            ],
            score_profile=PROFILE,
        )
    )

    assert report.case_outcome is CaseOutcome.FAILED
    assert report.score.value == 50


def test_physical_score_rule_is_unavailable_for_unitless_coordinates(make_request):
    profile = {
        **PROFILE,
        "rules": [{**PROFILE["rules"][0], "unit": "mm"}],
    }
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["path.length.open"],
            score_profile=profile,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert report.score.value is None


def test_score_profile_can_only_use_requested_metrics(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["point.count"],
            score_profile=PROFILE,
        )
    )

    assert report.case_outcome is CaseOutcome.INVALID
    assert "InvalidScoreProfile" in {failure.code for failure in report.domain_failures}


def test_score_profile_rules_must_be_unique(make_request):
    profile = {**PROFILE, "rules": [PROFILE["rules"][0], PROFILE["rules"][0]]}
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["path.length.open"],
            score_profile=profile,
        )
    )

    assert report.case_outcome is CaseOutcome.INVALID
    assert "InvalidScoreProfile" in {failure.code for failure in report.domain_failures}


def test_higher_is_better_score_is_clamped_to_one_hundred(make_request):
    profile = {
        "profileId": "count-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "point.count",
                "direction": "higher-is-better",
                "best": 2,
                "worst": 0,
                "weight": 1,
            }
        ],
    }
    report = evaluate(
        make_request(
            [[0, 0], [1, 0], [2, 0]],
            ["point.count"],
            score_profile=profile,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.COMPUTED
    assert report.score.value == 100
    assert report.score.components[0].normalized_value == 1


def test_lower_is_better_score_is_clamped_to_zero(make_request):
    report = evaluate(
        make_request(
            [[0, 0], [20, 0]],
            ["path.length.open"],
            score_profile=PROFILE,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.value == 0


def test_incompatible_score_unit_does_not_change_case_outcome(make_request):
    profile = {
        **PROFILE,
        "rules": [{**PROFILE["rules"][0], "unit": "s"}],
    }
    report = evaluate(
        make_request(
            [[0, 0], [3, 4]],
            ["path.length.open"],
            semantics={"unit": "mm"},
            score_profile=profile,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.NOT_APPLICABLE
    assert report.score.reason_code == "ScoreRuleUnitIncompatible"
    assert report.score.value is None


def test_dimensionless_metric_rejects_a_physical_score_unit(make_request):
    profile = {
        "profileId": "invalid-count-unit-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "point.count",
                "direction": "higher-is-better",
                "best": 2,
                "worst": 0,
                "weight": 1,
                "unit": "mm",
            }
        ],
    }
    report = evaluate(make_request([[0, 0]], ["point.count"], score_profile=profile))

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.NOT_APPLICABLE
    assert report.score.reason_code == "ScoreRuleUnitIncompatible"


def test_parameter_unit_cannot_be_compared_to_a_physical_score_rule(make_request):
    profile = {
        "profileId": "time-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "parameter.interval.mean",
                "direction": "lower-is-better",
                "best": 0,
                "worst": 2,
                "weight": 1,
                "unit": "s",
            }
        ],
    }
    report = evaluate(
        make_request(
            [[0, 0], [1, 0]],
            ["parameter.interval.mean"],
            parameter={"kind": "time", "values": [0, 1]},
            score_profile=profile,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert report.score.reason_code == "PhysicalScoreRuleRequiresKnownUnit"


def test_score_converts_compatible_units_before_normalization(make_request):
    profile = {
        "profileId": "converted-length-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "path.length.open",
                "direction": "lower-is-better",
                "best": 0,
                "worst": 2,
                "weight": 1,
                "unit": "cm",
            }
        ],
    }
    report = evaluate(
        make_request(
            [[0, 0], [10, 0]],
            ["path.length.open"],
            semantics={"unit": "mm"},
            score_profile=profile,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.COMPUTED
    assert report.score.value == 50


def test_structured_metric_cannot_be_reduced_to_a_score(make_request):
    profile = {
        "profileId": "invalid-bounds-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "bounds.axis_aligned",
                "direction": "lower-is-better",
                "best": 0,
                "worst": 1,
                "weight": 1,
            }
        ],
    }
    report = evaluate(
        make_request(
            [[0, 0], [1, 1]],
            ["bounds.axis_aligned"],
            score_profile=profile,
        )
    )

    assert report.case_outcome is CaseOutcome.PASSED
    assert report.score.status is MetricStatus.INVALID_OBSERVATION
    assert report.score.reason_code == "ScoreMetricUnavailable"
    assert report.score.value is None


def test_score_direction_requires_ordered_endpoints(make_request):
    profile = {
        "profileId": "bad-score@1",
        "applicableContext": "unit-test",
        "rules": [
            {
                "metricId": "point.count",
                "direction": "higher-is-better",
                "best": 0,
                "worst": 10,
                "weight": 1,
            }
        ],
    }
    report = evaluate(make_request([[0, 0]], ["point.count"], score_profile=profile))

    assert report.case_outcome is CaseOutcome.INVALID
    assert report.domain_failures[0].code == "MalformedRequest"
