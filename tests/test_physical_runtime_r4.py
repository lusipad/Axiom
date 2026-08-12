from __future__ import annotations

import pytest

from axiom.models import CaseOutcome, ClaimStatus, MetricStatus, RunSpec
from axiom.physical.models import PhysicalModelValidationRequest
from axiom.physical.runtime import (
    ALIGNMENT_VALID_METRIC_ID,
    CALIBRATION_TRACEABLE_METRIC_ID,
    FIT_WITHIN_TOLERANCE_METRIC_ID,
    LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
    LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID,
    LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
    LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
    REALITY_VALIDATED_CLAIM_ID,
    REALITY_VALIDATED_METRIC_ID,
    ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
    ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID,
    ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
    ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
    analyze_physical_validation,
)
from axiom.physical.scenarios import validate_r4_example_run_spec
from axiom.run import evaluate_run, validate_run_bundle_integrity


def _metric(bundle, metric_id: str):
    return next(result for result in bundle.report.metric_results if result.metric_id == metric_id)


def _run_spec_with_optional_metrics(*metric_ids: str, scenario_id: str = "in-domain-synthetic-sil") -> RunSpec:
    payload = validate_r4_example_run_spec(scenario_id).model_dump(
        mode="json",
        by_alias=True,
        exclude_unset=True,
        exclude_none=True,
    )
    existing = {
        metric["metricId"] if isinstance(metric, dict) else metric
        for metric in payload["request"]["case"]["optionalMetrics"]
    }
    for metric_id in metric_ids:
        if metric_id not in existing:
            payload["request"]["case"]["optionalMetrics"].append({"metricId": metric_id})
    return RunSpec.model_validate(payload)


def test_positive_sil_run_is_reproducible_but_never_claims_device_safety() -> None:
    run_spec = validate_r4_example_run_spec()
    first = evaluate_run(run_spec)
    second = evaluate_run(run_spec)

    assert validate_run_bundle_integrity(first) == []
    assert first.bundle_hash == second.bundle_hash
    assert first.run.case_outcome is CaseOutcome.PASSED
    assert first.report.provenance.numeric_environment["system"] == "Windows"
    assert _metric(first, CALIBRATION_TRACEABLE_METRIC_ID).value is True
    assert _metric(first, FIT_WITHIN_TOLERANCE_METRIC_ID).value is True

    reality_metric = _metric(first, REALITY_VALIDATED_METRIC_ID)
    assert reality_metric.status is MetricStatus.INSUFFICIENT_CONTEXT
    reality_claim = next(claim for claim in first.claims if claim.claim_definition_id == REALITY_VALIDATED_CLAIM_ID)
    assert reality_claim.status is ClaimStatus.INCONCLUSIVE

    serialized = first.model_dump_json(by_alias=True)
    for forbidden in ("DeviceSafe", "ProcessSafe", "safe-to-run", "上机许可"):
        assert forbidden not in serialized


def test_positive_sil_run_reports_linear_grouped_max_and_rmse_metrics() -> None:
    run_spec = _run_spec_with_optional_metrics(
        LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID,
        LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
    )
    bundle = evaluate_run(run_spec)
    analysis = analyze_physical_validation(
        PhysicalModelValidationRequest.model_validate(
            run_spec.request.model_dump(mode="json", by_alias=True, exclude_unset=True, exclude_none=True)
        )
    )

    assert validate_run_bundle_integrity(bundle) == []

    expected = {
        LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID: (analysis.linear_math_observation_max_absolute, "mm"),
        LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID: (analysis.linear_math_observation_rmse, "mm"),
        LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID: (
            analysis.linear_simulation_observation_max_absolute,
            "mm",
        ),
        LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID: (analysis.linear_simulation_observation_rmse, "mm"),
    }
    for metric_id, (value, unit) in expected.items():
        assert value is not None
        result = _metric(bundle, metric_id)
        assert result.status is MetricStatus.COMPUTED
        assert result.unit == unit
        assert result.value == pytest.approx(value)


@pytest.mark.parametrize(
    ("scenario_id", "expected_outcome", "metric_id", "expected_status", "expected_value"),
    [
        (
            "model-mismatch-detected",
            CaseOutcome.FAILED,
            FIT_WITHIN_TOLERANCE_METRIC_ID,
            MetricStatus.COMPUTED,
            False,
        ),
        (
            "time-alignment-mismatch",
            CaseOutcome.FAILED,
            ALIGNMENT_VALID_METRIC_ID,
            MetricStatus.COMPUTED,
            False,
        ),
        (
            "calibration-validation-leakage",
            CaseOutcome.FAILED,
            CALIBRATION_TRACEABLE_METRIC_ID,
            MetricStatus.COMPUTED,
            False,
        ),
        (
            "missing-coordinate-context",
            CaseOutcome.INCONCLUSIVE,
            ALIGNMENT_VALID_METRIC_ID,
            MetricStatus.INSUFFICIENT_CONTEXT,
            None,
        ),
    ],
)
def test_counterexamples_fail_closed(
    scenario_id: str,
    expected_outcome: CaseOutcome,
    metric_id: str,
    expected_status: MetricStatus,
    expected_value: bool | None,
) -> None:
    bundle = evaluate_run(validate_r4_example_run_spec(scenario_id))
    result = _metric(bundle, metric_id)

    assert validate_run_bundle_integrity(bundle) == []
    assert bundle.run.case_outcome is expected_outcome
    assert result.status is expected_status
    assert result.value is expected_value


def test_insufficient_rotary_excitation_marks_all_grouped_rotary_metrics_not_applicable() -> None:
    bundle = evaluate_run(
        _run_spec_with_optional_metrics(
            ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
            ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID,
            ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
            ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
            scenario_id="insufficient-axis-excitation",
        )
    )

    assert validate_run_bundle_integrity(bundle) == []
    assert bundle.run.case_outcome is CaseOutcome.PASSED
    for metric_id in (
        ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID,
        ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
    ):
        result = _metric(bundle, metric_id)
        assert result.status is MetricStatus.NOT_APPLICABLE
        assert result.value is None
        assert result.reason_code == "InsufficientRotaryAxisExcitation"


def test_missing_coordinate_context_keeps_new_grouped_metrics_in_insufficient_context() -> None:
    bundle = evaluate_run(
        _run_spec_with_optional_metrics(
            LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
            ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
            scenario_id="missing-coordinate-context",
        )
    )

    assert validate_run_bundle_integrity(bundle) == []
    assert bundle.run.case_outcome is CaseOutcome.INCONCLUSIVE
    for metric_id in (
        LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
    ):
        result = _metric(bundle, metric_id)
        assert result.status is MetricStatus.INSUFFICIENT_CONTEXT
        assert result.value is None
        assert result.reason_code == "PhysicalValidationAnalysisUnavailable"


def test_tampered_response_payload_is_rejected_before_domain_evaluation() -> None:
    payload = validate_r4_example_run_spec().model_dump(mode="json", by_alias=True)
    payload["request"]["artifact"]["samples"][1]["simulated"][0] += 1.0
    tampered = RunSpec.model_validate(payload)

    bundle = evaluate_run(tampered)

    assert bundle.run.case_outcome is CaseOutcome.INVALID
    assert bundle.report.domain_failures
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"
    assert all(result.reason_code == "RunSpecIncompatible" for result in bundle.report.metric_results)
