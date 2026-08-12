from __future__ import annotations

import pytest

from axiom.models import CaseOutcome, ExecutionStatus, MetricStatus
from axiom.physical.models import PhysicalModelValidationRequest
from axiom.physical.runtime import (
    ALIGNMENT_VALID_METRIC_ID,
    ALIGNMENT_VALID_CLAIM_ID,
    CALIBRATION_TRACEABLE_METRIC_ID,
    FIT_WITHIN_TOLERANCE_CLAIM_ID,
    FIT_WITHIN_TOLERANCE_METRIC_ID,
    LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID,
    REALITY_VALIDATED_METRIC_ID,
    ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
    analyze_physical_validation,
)
from axiom.physical.scenarios import (
    build_r4_manifest,
    list_r4_scenarios,
    load_r4_scenario,
    r4_example_payload,
    r4_example_run_spec,
    validate_r4_example_run_spec,
)
from axiom.run import evaluate_run, validate_run_bundle_integrity


def _metric(bundle, metric_id: str):
    return next(result for result in bundle.report.metric_results if result.metric_id == metric_id)


def _payload_claim(payload: dict[str, object], claim_definition_id: str) -> dict[str, object]:
    claims = payload["analysis"]["claims"]  # type: ignore[index]
    return next(claim for claim in claims if claim["claimDefinitionId"] == claim_definition_id)  # type: ignore[index]


def _payload_metric(payload: dict[str, object], metric_id: str) -> dict[str, object]:
    metrics = payload["analysis"]["metricResults"]  # type: ignore[index]
    return next(metric for metric in metrics if metric["metricId"] == metric_id)  # type: ignore[index]


def _runtime_analysis(scenario_id: str = "in-domain-synthetic-sil"):
    scenario = load_r4_scenario(scenario_id)
    request = PhysicalModelValidationRequest.model_validate(scenario.runSpec["request"])
    return analyze_physical_validation(request)


def test_r4_catalog_freezes_default_id_and_six_windows_only_scenarios() -> None:
    manifest = build_r4_manifest()
    summaries = list_r4_scenarios()

    assert manifest["defaultScenarioId"] == "in-domain-synthetic-sil"
    assert manifest["domainPackId"] == "five-axis.domain-pack@6"
    assert manifest["platform"] == "windows"
    assert manifest["safetyBanner"] == "MODEL VALIDATION / NOT DEVICE SAFE"
    assert manifest["validationBanner"] == "SYNTHETIC SIL / REALITY VALIDATION OPEN"
    assert manifest["syntheticContractStatus"] == "Passed"
    assert manifest["realityValidationStatus"] == "Open"
    assert [item.scenarioId for item in summaries] == [
        "in-domain-synthetic-sil",
        "model-mismatch-detected",
        "time-alignment-mismatch",
        "calibration-validation-leakage",
        "insufficient-axis-excitation",
        "missing-coordinate-context",
    ]
    assert "windows-linear-rotary-validation" not in {item.scenarioId for item in summaries}


def test_positive_r4_scenario_uses_independent_oracle_and_keeps_b_c_insufficient() -> None:
    scenario = load_r4_scenario()
    runtime_analysis = _runtime_analysis()

    assert scenario.summary.scenarioId == "in-domain-synthetic-sil"
    assert scenario.summary.syntheticContractStatus == "Passed"
    assert scenario.summary.realityValidationStatus == "Open"
    assert scenario.calibrationPair.command_content_id != scenario.validationPair.command_content_id
    assert scenario.calibrationPair.trace_content_hash != scenario.validationPair.trace_content_hash
    assert scenario.validationAnalysis == runtime_analysis
    assert scenario.validationAnalysis.leakage_free is True
    assert scenario.validationAnalysis.alignment_coverage == 1.0
    assert scenario.validationAnalysis.fit_within_tolerance is True
    assert scenario.validationAnalysis.linear_improvement_ratio is not None
    assert scenario.validationAnalysis.linear_improvement_ratio > 0.35
    assert scenario.validationAnalysis.decomposition_closure_max is not None
    assert scenario.validationAnalysis.decomposition_closure_max <= 1e-12

    identified = {axis.axis_id for axis in scenario.physicalModel.axes if axis.excitation_status == "identified"}
    insufficient = {axis.axis_id for axis in scenario.physicalModel.axes if axis.excitation_status == "insufficient-excitation"}
    assert identified >= {"X", "Y"}
    assert {"B", "C"}.issubset(insufficient)

    axis_b = next(axis for axis in scenario.validationAnalysis.axes if axis.axis_id == "B")
    axis_c = next(axis for axis in scenario.validationAnalysis.axes if axis.axis_id == "C")
    assert axis_b.math_observation_rmse is None
    assert axis_b.simulation_observation_rmse is None
    assert axis_c.math_observation_rmse is None
    assert axis_c.simulation_observation_rmse is None
    assert scenario.validationAnalysis.rotary_math_observation_rmse is None
    assert scenario.validationAnalysis.rotary_simulation_observation_rmse is None

    axis_x = next(axis for axis in scenario.validationAnalysis.axes if axis.axis_id == "X")
    assert axis_x.math_observation_rmse is not None
    assert axis_x.simulation_observation_rmse is not None
    assert axis_x.simulation_observation_rmse < axis_x.math_observation_rmse
    assert tuple(axis_x.simulation) != tuple(axis_x.observation)


@pytest.mark.parametrize(
    ("scenario_id", "expectation"),
    [
        ("model-mismatch-detected", "mismatch"),
        ("time-alignment-mismatch", "alignment"),
        ("calibration-validation-leakage", "leakage"),
        ("insufficient-axis-excitation", "excitation"),
        ("missing-coordinate-context", "coordinate"),
    ],
)
def test_r4_counterexample_metadata_freezes_failure_mode(
    scenario_id: str,
    expectation: str,
) -> None:
    scenario = load_r4_scenario(scenario_id)

    assert scenario.summary.syntheticContractStatus == "Passed"
    assert scenario.summary.realityValidationStatus == "Open"

    if expectation == "mismatch":
        assert scenario.validationAnalysis.fit_within_tolerance is False
        assert scenario.validationAnalysis.linear_improvement_ratio is not None
        assert scenario.validationAnalysis.linear_improvement_ratio < 0.35
    elif expectation == "alignment":
        assert scenario.validationAnalysis.fit_within_tolerance is False
        assert scenario.validationAnalysis.alignment_coverage == 0.0
        assert scenario.validationAnalysis.maximum_time_error_seconds > 0.002
    elif expectation == "leakage":
        assert scenario.validationAnalysis.fit_within_tolerance is False
        assert scenario.validationAnalysis.leakage_free is False
        assert scenario.calibrationPair.command_content_id == scenario.validationPair.command_content_id
        assert scenario.calibrationPair.trace_content_hash == scenario.validationPair.trace_content_hash
    elif expectation == "excitation":
        insufficient = {
            axis.axis_id for axis in scenario.physicalModel.axes if axis.excitation_status == "insufficient-excitation"
        }
        assert {"B", "C"}.issubset(insufficient)
    else:
        assert scenario.validationPair.observation.coordinate_alignment is None


def test_r4_example_payload_and_bootstrap_run_spec_are_real_and_evaluable() -> None:
    payload = r4_example_payload()
    runtime_analysis = _runtime_analysis()
    run_spec = validate_r4_example_run_spec()
    bundle = evaluate_run(run_spec)
    linear_math_metric = _metric(bundle, LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID)
    rotary_metric = _metric(bundle, ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID)
    reality_metric = _metric(bundle, REALITY_VALIDATED_METRIC_ID)
    payload_linear_metric = _payload_metric(payload, LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID)
    payload_rotary_metric = _payload_metric(payload, ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID)

    assert payload["scenario"]["scenarioId"] == "in-domain-synthetic-sil"
    assert payload["manifest"]["defaultScenarioId"] == "in-domain-synthetic-sil"
    assert payload["calibration"]["contentHash"] != payload["validation"]["contentHash"]
    assert [guard["status"] for guard in payload["validation"]["leakageGuards"]] == ["pass", "pass"]
    assert any(axis["axisId"] == "B" and axis["excitationStatus"] == "insufficient" for axis in payload["analysis"]["axes"])
    assert any(axis["axisId"] == "C" and axis["excitationStatus"] == "insufficient" for axis in payload["analysis"]["axes"])
    assert payload["analysis"]["run"]["caseOutcome"] == CaseOutcome.PASSED.value
    assert payload["analysis"]["run"]["executionStatus"] == ExecutionStatus.SUCCEEDED.value
    assert payload["analysis"]["analysisContentHash"] == runtime_analysis.content_hash
    assert payload_linear_metric["value"] == pytest.approx(linear_math_metric.value)
    assert payload_linear_metric["status"] == linear_math_metric.status.value
    assert payload_rotary_metric["status"] == MetricStatus.NOT_APPLICABLE.value
    assert payload_rotary_metric["reasonCode"] == "InsufficientRotaryAxisExcitation"
    assert _payload_claim(payload, FIT_WITHIN_TOLERANCE_CLAIM_ID)["status"] == "Supported"
    assert _payload_claim(payload, "five-axis.physical-model-reality-validated-claim@1")["status"] == "Inconclusive"
    assert all("safe" not in claim["statement"].lower() for claim in payload["analysis"]["claims"])
    axis_b_payload = next(axis for axis in payload["analysis"]["axes"] if axis["axisId"] == "B")
    assert axis_b_payload["residualDecomposition"] == []
    assert run_spec.domain_pack_id == "five-axis.domain-pack@6"

    assert validate_run_bundle_integrity(bundle) == []
    assert bundle.run.execution_status is ExecutionStatus.SUCCEEDED
    assert bundle.run.case_outcome is CaseOutcome.PASSED
    assert bundle.observation.source == "ExecutedSubject"
    assert rotary_metric.status is MetricStatus.NOT_APPLICABLE
    assert reality_metric.status is MetricStatus.INSUFFICIENT_CONTEXT


@pytest.mark.parametrize(
    ("scenario_id", "expected_outcome"),
    [
        ("in-domain-synthetic-sil", CaseOutcome.PASSED),
        ("model-mismatch-detected", CaseOutcome.FAILED),
        ("time-alignment-mismatch", CaseOutcome.FAILED),
        ("calibration-validation-leakage", CaseOutcome.FAILED),
        ("insufficient-axis-excitation", CaseOutcome.PASSED),
        ("missing-coordinate-context", CaseOutcome.INCONCLUSIVE),
    ],
)
def test_r4_run_spec_outcomes_match_expected_failure_modes(
    scenario_id: str,
    expected_outcome: CaseOutcome,
) -> None:
    bundle = evaluate_run(validate_r4_example_run_spec(scenario_id))
    payload = r4_example_payload(scenario_id)

    assert validate_run_bundle_integrity(bundle) == []
    assert bundle.run.execution_status is ExecutionStatus.SUCCEEDED
    assert bundle.run.case_outcome is expected_outcome

    if scenario_id == "model-mismatch-detected":
        assert _metric(bundle, FIT_WITHIN_TOLERANCE_METRIC_ID).value is False
        assert _payload_claim(payload, FIT_WITHIN_TOLERANCE_CLAIM_ID)["status"] == "Refuted"
    elif scenario_id == "time-alignment-mismatch":
        assert _metric(bundle, ALIGNMENT_VALID_METRIC_ID).value is False
    elif scenario_id == "calibration-validation-leakage":
        result = _metric(bundle, CALIBRATION_TRACEABLE_METRIC_ID)
        assert result.value is False
        assert result.reason_code == "CalibrationValidationLeakage"
    elif scenario_id == "insufficient-axis-excitation":
        assert _metric(bundle, ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID).status is MetricStatus.NOT_APPLICABLE
    elif scenario_id == "missing-coordinate-context":
        assert _metric(bundle, ALIGNMENT_VALID_METRIC_ID).status is MetricStatus.INSUFFICIENT_CONTEXT
        claim = _payload_claim(payload, ALIGNMENT_VALID_CLAIM_ID)
        assert claim["status"] == "Inconclusive"
        assert claim["reasonCode"] == "R3AlignmentContextIncomplete"


def test_unknown_r4_scenario_is_rejected() -> None:
    with pytest.raises(KeyError):
        load_r4_scenario("missing")

    with pytest.raises(KeyError):
        r4_example_run_spec("missing")
