from __future__ import annotations

import math
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from typing import Any

from ..models import RunSpec
from .models import AxisValidationSeries
from .reality_models import (
    FIVE_AXIS_REALITY_DOMAIN_PACK_ID,
    PHYSICAL_REALITY_EVALUATOR_ID,
    PHYSICAL_REALITY_RUNNER_ID,
    R41_DEFAULT_SCENARIO_ID,
    R41_SCENARIO_IDS,
    PhysicalRealityAnalysis,
    PhysicalRealityCheck,
    PhysicalRealityEvidencePair,
    R41AssessmentRequest,
    R41ExamplePayload,
    R41Manifest,
    R41Scenario,
    R41ScenarioSummary,
    RealityPhysicalApplicability,
    RealityPhysicalModelDefinition,
    identity_hash,
)
from .simulation import exact_zoh_response, fit_first_order_model

R41_CONTRACT_METRIC_ID = "five-axis.physical.reality-contract-valid@1"
R41_INDEPENDENT_METRIC_ID = "five-axis.physical.independent-real-runs@1"
R41_DEPLOYMENT_METRIC_ID = "five-axis.physical.r7e-deployment-gates@1"
R41_CALIBRATION_METRIC_ID = "five-axis.physical.real-calibration-traceable@1"
R41_ALIGNMENT_METRIC_ID = "five-axis.physical.real-alignment-coverage@1"
R41_LINEAR_RMSE_METRIC_ID = "five-axis.physical.real-linear-holdout-rmse@1"
R41_ROTARY_RMSE_METRIC_ID = "five-axis.physical.real-rotary-holdout-rmse@1"
R41_DECOMPOSITION_METRIC_ID = "five-axis.physical.real-residual-decomposition@1"
R41_FIT_METRIC_ID = "five-axis.physical.real-holdout-fit@1"
R41_REALITY_METRIC_ID = "five-axis.physical.reality-validated@2"

_AXES = ("X", "Y", "Z", "B", "C")
_UNITS = ("mm", "mm", "mm", "rad", "rad")
_FAMILIES = (
    "linear-mm",
    "linear-mm",
    "linear-mm",
    "rotary-rad",
    "rotary-rad",
)
_UNMODELED = (
    "friction-and-backlash-outside-calibration-run",
    "controller-feedforward-and-saturation",
    "cross-axis-coupling-and-structural-flexibility",
    "geometric-assembly-error",
    "thermal-drift",
    "cutting-force-tool-workpiece-process",
    "sensor-and-external-metrology-uncertainty",
)


def _check(
    check_id: str,
    title: str,
    status: str,
    reason: str | None = None,
    **details: Any,
) -> PhysicalRealityCheck:
    return PhysicalRealityCheck(
        checkId=check_id,
        title=title,
        status=status,
        reasonCode=reason,
        details=details,
    )


def _seal_analysis(**fields: Any) -> PhysicalRealityAnalysis:
    provisional = PhysicalRealityAnalysis.model_construct(
        **fields, content_hash="0" * 64
    )
    payload = provisional.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"}
    )
    payload["contentHash"] = identity_hash(provisional, exclude="content_hash")
    return PhysicalRealityAnalysis.model_validate(payload)


def build_reality_evidence_pair(
    *,
    pair_id: str,
    role: str,
    r7e_request: Any,
) -> PhysicalRealityEvidencePair:
    command = r7e_request.command
    evidence = r7e_request.shadow_evidence
    if command is None or evidence is None:
        raise ValueError("R7-E request must contain command and Shadow evidence")
    provisional = PhysicalRealityEvidencePair.model_construct(
        pair_id=pair_id,
        role=role,
        r7e_request=r7e_request.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        command_content_hash=command.content_id,
        shadow_evidence_content_hash=evidence.content_hash,
        pair_content_hash="0" * 64,
    )
    payload = provisional.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"pair_content_hash"}
    )
    payload["pairContentHash"] = identity_hash(
        provisional, exclude="pair_content_hash"
    )
    return PhysicalRealityEvidencePair.model_validate(payload)


def build_r41_manifest() -> R41Manifest:
    return R41Manifest(
        manifestId="physical.r4.1-manifest@1",
        stage="R4.1",
        domainPackId=FIVE_AXIS_REALITY_DOMAIN_PACK_ID,
        evaluatorVersion=PHYSICAL_REALITY_EVALUATOR_ID,
        runnerId=PHYSICAL_REALITY_RUNNER_ID,
        supportedPlatforms=("Windows",),
        requiredIndependentRuns=2,
        calibrationRole="calibration",
        validationRole="validation",
        interpolationAllowed=False,
        defaultScenarioId=R41_DEFAULT_SCENARIO_ID,
        scenarioIds=R41_SCENARIO_IDS,
        realityValidationStatus="Open",
        controlledTrialStatus="Open",
        closedLoopStatus="Open",
        deviceSafetyStatus="NotAssessed",
        processSafetyStatus="NotAssessed",
    )


def _replay_r7e(pair: PhysicalRealityEvidencePair) -> bool:
    from ..control.r7e_scenarios import assess_r7e_shadow

    request = pair.parsed_r7e_request()
    replay = assess_r7e_shadow(
        request.vendor_profile,
        request.runtime_evidence,
        request.witness_profile,
        request.controller_profile,
        request.authority,
        request.capture_authorization,
        request.command,
        request.shadow_evidence,
    )
    evidence = request.shadow_evidence
    return bool(
        replay == request.artifact
        and replay.deployment_shadow_status == "Passed"
        and evidence is not None
        and evidence.source_kind == "controller-live-read"
        and evidence.declared_real
    )


def _pairs_are_independent(
    calibration: PhysicalRealityEvidencePair,
    validation: PhysicalRealityEvidencePair,
) -> bool:
    left = calibration.parsed_r7e_request()
    right = validation.parsed_r7e_request()
    left_evidence = left.shadow_evidence
    right_evidence = right.shadow_evidence
    left_authorization = left.capture_authorization
    right_authorization = right.capture_authorization
    return bool(
        calibration.role == "calibration"
        and validation.role == "validation"
        and calibration.pair_id != validation.pair_id
        and calibration.pair_content_hash != validation.pair_content_hash
        and calibration.shadow_evidence_content_hash
        != validation.shadow_evidence_content_hash
        and left_evidence is not None
        and right_evidence is not None
        and datetime.fromisoformat(left_evidence.captured_at)
        < datetime.fromisoformat(right_evidence.captured_at)
        and left_evidence.capture_authorization_content_hash
        != right_evidence.capture_authorization_content_hash
        and left_authorization is not None
        and right_authorization is not None
        and (
            left_authorization.authorized_from,
            left_authorization.authorized_until,
        )
        != (
            right_authorization.authorized_from,
            right_authorization.authorized_until,
        )
    )


def _same_device(
    calibration: PhysicalRealityEvidencePair,
    validation: PhysicalRealityEvidencePair,
) -> bool:
    left = calibration.parsed_r7e_request().controller_profile
    right = validation.parsed_r7e_request().controller_profile
    return bool(
        left is not None
        and right is not None
        and left.content_hash == right.content_hash
        and left.machine_id == right.machine_id
        and calibration.parsed_r7e_request().case.case_id
        == validation.parsed_r7e_request().case.case_id
    )


def _series(pair: PhysicalRealityEvidencePair) -> tuple[
    tuple[float, ...],
    tuple[tuple[float, ...], ...],
    tuple[tuple[float, ...], ...],
]:
    request = pair.parsed_r7e_request()
    command = request.command
    evidence = request.shadow_evidence
    assert command is not None and evidence is not None
    times = tuple(float(sample.t) for sample in command.samples)
    commands = tuple(
        tuple(float(sample.q[axis]) for sample in command.samples)
        for axis in range(5)
    )
    observations = tuple(
        tuple(float(frame.samples[axis].value) for frame in evidence.frames)
        for axis in range(5)
    )
    return times, commands, observations


def _rmse(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(
        sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) / len(left)
    )


def _group_rmse(
    axes: Sequence[AxisValidationSeries], *, family: str, source: str
) -> float | None:
    squared: list[float] = []
    for axis in axes:
        if axis.unit_family != family or axis.excitation_status != "identified":
            continue
        values = axis.command if source == "math" else axis.simulation
        squared.extend(
            (left - right) ** 2
            for left, right in zip(values, axis.observation, strict=True)
        )
    return math.sqrt(sum(squared) / len(squared)) if squared else None


def _analysis_from_pairs(
    calibration_pair: PhysicalRealityEvidencePair,
    validation_pair: PhysicalRealityEvidencePair,
    *,
    fit_improvement_minimum: float,
    excitation_span_minimum: float,
    decomposition_tolerance: float,
) -> PhysicalRealityAnalysis:
    independent = _pairs_are_independent(calibration_pair, validation_pair)
    same_device = _same_device(calibration_pair, validation_pair)
    calibration_gate = _replay_r7e(calibration_pair)
    validation_gate = _replay_r7e(validation_pair)
    checks = [
        _check(
            "r41.contract",
            "Two-run Windows physical reality validation contract",
            "Passed",
            requiredIndependentRuns=2,
            interpolationApplied=False,
        ),
        _check(
            "r41.independent-evidence",
            "Calibration and holdout evidence are disjoint",
            "Passed" if independent else "Blocked",
            None if independent else "CalibrationValidationLeakage",
        ),
        _check(
            "r41.r7e-deployment-gates",
            "Both inputs passed case-scoped R7-E deployment Shadow gates",
            "Passed" if calibration_gate and validation_gate and same_device else "Blocked",
            (
                None
                if calibration_gate and validation_gate and same_device
                else "R7EDeploymentEvidenceInvalidOrDifferentDevice"
            ),
        ),
    ]
    if not independent or not calibration_gate or not validation_gate or not same_device:
        checks.extend(
            (
                _check(
                    "r41.calibration",
                    "Independent real calibration replay",
                    "Blocked",
                    "RealityEvidenceGateBlocked",
                ),
                _check(
                    "r41.alignment",
                    "Exact sample-index alignment",
                    "Blocked",
                    "RealityEvidenceGateBlocked",
                ),
                _check(
                    "r41.holdout-fit",
                    "Disjoint real holdout fit",
                    "Blocked",
                    "RealityEvidenceGateBlocked",
                ),
                _check(
                    "r41.residual-decomposition",
                    "Command/model/observation residual closure",
                    "Blocked",
                    "RealityEvidenceGateBlocked",
                ),
                _check(
                    "r41.reality-gate",
                    "Case-scoped physical model reality validation",
                    "Blocked",
                    "RealityEvidenceGateBlocked",
                ),
            )
        )
        return _seal_analysis(
            artifact_type="five-axis.physical-reality-analysis",
            schema_id="five-axis.physical-reality-analysis@1",
            schema_version=1,
            analysis_id="five-axis.r4.1.reality-analysis@1",
            calibration_pair_content_hash=calibration_pair.pair_content_hash,
            validation_pair_content_hash=validation_pair.pair_content_hash,
            checks=tuple(checks),
            axes=(),
            alignment_coverage=0.0,
            fit_status="Blocked",
            reality_validation_status="Blocked",
            counts_toward_reality=False,
            validation_scope="single-device-case-scoped",
            controlled_trial_status="Open",
            closed_loop_status="Open",
            device_safety_status="NotAssessed",
            process_safety_status="NotAssessed",
        )

    calibration_times, calibration_commands, calibration_observations = _series(
        calibration_pair
    )
    validation_times, validation_commands, validation_observations = _series(
        validation_pair
    )
    calibration_request = calibration_pair.parsed_r7e_request()
    validation_request = validation_pair.parsed_r7e_request()
    calibration_command = calibration_request.command
    validation_command = validation_request.command
    controller = calibration_request.controller_profile
    assert calibration_command is not None and validation_command is not None
    assert controller is not None
    periods_match = math.isclose(
        calibration_command.sample_period,
        validation_command.sample_period,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    if not periods_match:
        checks.extend(
            (
                _check(
                    "r41.calibration",
                    "Independent real calibration replay",
                    "Blocked",
                    "SamplePeriodMismatch",
                ),
                _check(
                    "r41.alignment",
                    "Exact sample-index alignment",
                    "Passed",
                    coverage=1.0,
                ),
                _check(
                    "r41.holdout-fit",
                    "Disjoint real holdout fit",
                    "Blocked",
                    "SamplePeriodMismatch",
                ),
                _check(
                    "r41.residual-decomposition",
                    "Command/model/observation residual closure",
                    "Blocked",
                    "SamplePeriodMismatch",
                ),
                _check(
                    "r41.reality-gate",
                    "Case-scoped physical model reality validation",
                    "Blocked",
                    "SamplePeriodMismatch",
                ),
            )
        )
        return _seal_analysis(
            artifact_type="five-axis.physical-reality-analysis",
            schema_id="five-axis.physical-reality-analysis@1",
            schema_version=1,
            analysis_id="five-axis.r4.1.reality-analysis@1",
            calibration_pair_content_hash=calibration_pair.pair_content_hash,
            validation_pair_content_hash=validation_pair.pair_content_hash,
            checks=tuple(checks),
            axes=(),
            alignment_coverage=1.0,
            fit_status="Blocked",
            reality_validation_status="Blocked",
            counts_toward_reality=False,
            validation_scope="single-device-case-scoped",
            controlled_trial_status="Open",
            closed_loop_status="Open",
            device_safety_status="NotAssessed",
            process_safety_status="NotAssessed",
        )

    calibration_evidence = calibration_request.shadow_evidence
    assert calibration_evidence is not None
    suffix = calibration_evidence.content_hash[:12]
    model_v1, calibration = fit_first_order_model(
        calibration_id=f"five-axis.r4.1.real-calibration-{suffix}@1",
        model_id=f"five-axis.r4.1.real-model-{suffix}@1",
        calibration_command_content_id=calibration_command.content_id,
        calibration_trace_content_hash=calibration_evidence.content_hash,
        device_id=controller.machine_id,
        controller_family=controller.controller_family,
        trajectory_families=("five-axis-real-shadow",),
        sample_period=calibration_command.sample_period,
        commands_by_axis=calibration_commands,
        observations_by_axis=calibration_observations,
        times=calibration_times,
        excitation_span_minimum=excitation_span_minimum,
    )
    model_provisional = RealityPhysicalModelDefinition.model_construct(
        schema_id="five-axis.physical-model-definition@2",
        schema_version=2,
        model_id=model_v1.model_id,
        model_family_id=model_v1.model_family_id,
        integration_method=model_v1.integration_method,
        parameter_source=model_v1.parameter_source,
        calibration_id=model_v1.calibration_id,
        calibration_command_content_hash=calibration_command.content_id,
        calibration_shadow_evidence_content_hash=calibration_evidence.content_hash,
        axes=model_v1.axes,
        applicability=RealityPhysicalApplicability(
            deviceId=controller.machine_id,
            controllerProfileContentHash=controller.content_hash,
            caseId=calibration_request.case.case_id,
            trajectoryFamilies=("five-axis-real-shadow",),
            samplePeriodSeconds=calibration_command.sample_period,
            evidenceSource="controller-live-read",
            validationScope="single-device-case-scoped",
        ),
        unmodeled_factors=_UNMODELED,
        content_hash="0" * 64,
    )
    model_payload = model_provisional.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"}
    )
    model_payload["contentHash"] = identity_hash(
        model_provisional, exclude="content_hash"
    )
    model = RealityPhysicalModelDefinition.model_validate(model_payload)

    axes: list[AxisValidationSeries] = []
    closure_max = 0.0
    all_identified = True
    for axis in model.axes:
        command_series = validation_commands[axis.axis_index]
        observation_series = validation_observations[axis.axis_index]
        if axis.excitation_status == "identified":
            assert axis.time_constant_seconds is not None and axis.bias is not None
            simulation = exact_zoh_response(
                command_series,
                validation_times,
                time_constant_seconds=axis.time_constant_seconds,
                bias=axis.bias,
            )
            math_rmse = _rmse(command_series, observation_series)
            simulation_rmse = _rmse(simulation, observation_series)
            improvement = (
                (math_rmse - simulation_rmse) / math_rmse if math_rmse > 0 else None
            )
            closure = max(
                abs((obs - cmd) - ((obs - sim) + (sim - cmd)))
                for obs, sim, cmd in zip(
                    observation_series, simulation, command_series, strict=True
                )
            )
            closure_max = max(closure_max, closure)
        else:
            all_identified = False
            simulation = command_series
            math_rmse = simulation_rmse = improvement = closure = None
        axes.append(
            AxisValidationSeries(
                axisId=axis.axis_id,
                axisIndex=axis.axis_index,
                unitFamily=axis.unit_family,
                unit=axis.unit,
                excitationStatus=axis.excitation_status,
                times=validation_times,
                command=command_series,
                simulation=simulation,
                observation=observation_series,
                mathObservationRmse=math_rmse,
                simulationObservationRmse=simulation_rmse,
                improvementRatio=improvement,
                decompositionClosureMax=closure,
            )
        )
    axis_tuple = tuple(axes)
    linear_math = _group_rmse(axis_tuple, family="linear-mm", source="math")
    linear_sim = _group_rmse(axis_tuple, family="linear-mm", source="simulation")
    rotary_math = _group_rmse(axis_tuple, family="rotary-rad", source="math")
    rotary_sim = _group_rmse(axis_tuple, family="rotary-rad", source="simulation")
    linear_improvement = (
        (linear_math - linear_sim) / linear_math
        if linear_math and linear_sim is not None
        else None
    )
    rotary_improvement = (
        (rotary_math - rotary_sim) / rotary_math
        if rotary_math and rotary_sim is not None
        else None
    )
    fit_passed = bool(
        all_identified
        and linear_improvement is not None
        and rotary_improvement is not None
        and linear_improvement >= fit_improvement_minimum
        and rotary_improvement >= fit_improvement_minimum
    )
    closure_passed = closure_max <= decomposition_tolerance
    checks.extend(
        (
            _check(
                "r41.calibration",
                "Independent real calibration replay",
                "Passed" if all_identified else "Refuted",
                None if all_identified else "InsufficientFiveAxisExcitation",
                calibrationContentHash=calibration.content_hash,
            ),
            _check(
                "r41.alignment",
                "Exact sample-index alignment",
                "Passed",
                coverage=1.0,
                interpolationApplied=False,
            ),
            _check(
                "r41.holdout-fit",
                "Disjoint real holdout fit",
                "Passed" if fit_passed else "Refuted",
                None if fit_passed else "RealHoldoutFitBelowTolerance",
                linearImprovementRatio=linear_improvement,
                rotaryImprovementRatio=rotary_improvement,
                minimum=fit_improvement_minimum,
            ),
            _check(
                "r41.residual-decomposition",
                "Command/model/observation residual closure",
                "Passed" if closure_passed else "Refuted",
                None if closure_passed else "ResidualDecompositionOpen",
                closureMax=closure_max,
                tolerance=decomposition_tolerance,
            ),
        )
    )
    reality_passed = all_identified and fit_passed and closure_passed
    checks.append(
        _check(
            "r41.reality-gate",
            "Case-scoped physical model reality validation",
            "Passed" if reality_passed else "Refuted",
            None if reality_passed else "RealHoldoutValidationRefuted",
            validationScope="single-device-case-scoped",
        )
    )
    return _seal_analysis(
        artifact_type="five-axis.physical-reality-analysis",
        schema_id="five-axis.physical-reality-analysis@1",
        schema_version=1,
        analysis_id="five-axis.r4.1.reality-analysis@1",
        calibration_pair_content_hash=calibration_pair.pair_content_hash,
        validation_pair_content_hash=validation_pair.pair_content_hash,
        checks=tuple(checks),
        model=model,
        calibration=calibration,
        axes=axis_tuple,
        linear_math_observation_rmse=linear_math,
        linear_simulation_observation_rmse=linear_sim,
        linear_improvement_ratio=linear_improvement,
        rotary_math_observation_rmse=rotary_math,
        rotary_simulation_observation_rmse=rotary_sim,
        rotary_improvement_ratio=rotary_improvement,
        decomposition_closure_max=closure_max,
        alignment_coverage=1.0,
        fit_status="Passed" if fit_passed else "Refuted",
        reality_validation_status="Passed" if reality_passed else "Refuted",
        counts_toward_reality=reality_passed,
        validation_scope="single-device-case-scoped",
        controlled_trial_status="Open",
        closed_loop_status="Open",
        device_safety_status="NotAssessed",
        process_safety_status="NotAssessed",
    )


def assess_r41_reality(
    calibration_pair: PhysicalRealityEvidencePair | None,
    validation_pair: PhysicalRealityEvidencePair | None,
    *,
    fit_improvement_minimum: float = 0.2,
    excitation_span_minimum: float = 1e-6,
    decomposition_tolerance: float = 1e-12,
) -> PhysicalRealityAnalysis:
    if calibration_pair is not None and validation_pair is not None:
        return _analysis_from_pairs(
            calibration_pair,
            validation_pair,
            fit_improvement_minimum=fit_improvement_minimum,
            excitation_span_minimum=excitation_span_minimum,
            decomposition_tolerance=decomposition_tolerance,
        )
    checks = (
        _check(
            "r41.contract",
            "Two-run Windows physical reality validation contract",
            "Passed",
            requiredIndependentRuns=2,
            interpolationApplied=False,
        ),
        _check(
            "r41.independent-evidence",
            "Calibration and holdout evidence are disjoint",
            "Open",
            "IndependentRealRunsMissing",
        ),
        _check(
            "r41.r7e-deployment-gates",
            "Both inputs passed case-scoped R7-E deployment Shadow gates",
            "Open",
            "R7EDeploymentEvidenceMissing",
        ),
        _check(
            "r41.calibration",
            "Independent real calibration replay",
            "Open",
            "CalibrationRunMissing",
        ),
        _check(
            "r41.alignment",
            "Exact sample-index alignment",
            "Open",
            "RealRunAlignmentMissing",
        ),
        _check(
            "r41.holdout-fit",
            "Disjoint real holdout fit",
            "Open",
            "ValidationRunMissing",
        ),
        _check(
            "r41.residual-decomposition",
            "Command/model/observation residual closure",
            "Open",
            "RealResidualsMissing",
        ),
        _check(
            "r41.reality-gate",
            "Case-scoped physical model reality validation",
            "Open",
            "IndependentRealCalibrationAndHoldoutRequired",
        ),
    )
    return _seal_analysis(
        artifact_type="five-axis.physical-reality-analysis",
        schema_id="five-axis.physical-reality-analysis@1",
        schema_version=1,
        analysis_id="five-axis.r4.1.reality-analysis@1",
        calibration_pair_content_hash=(
            calibration_pair.pair_content_hash if calibration_pair else None
        ),
        validation_pair_content_hash=(
            validation_pair.pair_content_hash if validation_pair else None
        ),
        checks=checks,
        axes=(),
        alignment_coverage=0.0,
        fit_status="Open",
        reality_validation_status="Open",
        counts_toward_reality=False,
        validation_scope="single-device-case-scoped",
        controlled_trial_status="Open",
        closed_loop_status="Open",
        device_safety_status="NotAssessed",
        process_safety_status="NotAssessed",
    )


def _run_spec(
    analysis: PhysicalRealityAnalysis,
    calibration_pair: PhysicalRealityEvidencePair | None,
    validation_pair: PhysicalRealityEvidencePair | None,
    *,
    fit_improvement_minimum: float = 0.2,
    excitation_span_minimum: float = 1e-6,
    decomposition_tolerance: float = 1e-12,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "artifact": analysis.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "fitImprovementMinimum": fit_improvement_minimum,
        "excitationSpanMinimum": excitation_span_minimum,
        "decompositionTolerance": decomposition_tolerance,
        "case": {
            "caseId": "five-axis.r4.1.physical-reality.case@1",
            "requiredMetrics": [
                R41_CONTRACT_METRIC_ID,
                R41_INDEPENDENT_METRIC_ID,
                R41_DEPLOYMENT_METRIC_ID,
                R41_CALIBRATION_METRIC_ID,
                R41_ALIGNMENT_METRIC_ID,
                R41_FIT_METRIC_ID,
                R41_DECOMPOSITION_METRIC_ID,
                R41_REALITY_METRIC_ID,
            ],
            "optionalMetrics": [
                R41_LINEAR_RMSE_METRIC_ID,
                R41_ROTARY_RMSE_METRIC_ID,
            ],
        },
    }
    if calibration_pair is not None:
        request["calibrationPair"] = calibration_pair.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    if validation_pair is not None:
        request["validationPair"] = validation_pair.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    return {
        "subjectId": "five-axis.physical-reality-validation@1",
        "subjectVersion": "1",
        "domainPackId": FIVE_AXIS_REALITY_DOMAIN_PACK_ID,
        "runnerId": PHYSICAL_REALITY_RUNNER_ID,
        "evaluatorVersion": PHYSICAL_REALITY_EVALUATOR_ID,
        "request": request,
    }


def _payload(
    summary: R41ScenarioSummary,
    calibration_pair: PhysicalRealityEvidencePair | None,
    validation_pair: PhysicalRealityEvidencePair | None,
    *,
    fit_improvement_minimum: float = 0.2,
    excitation_span_minimum: float = 1e-6,
    decomposition_tolerance: float = 1e-12,
) -> R41ExamplePayload:
    analysis = assess_r41_reality(
        calibration_pair,
        validation_pair,
        fit_improvement_minimum=fit_improvement_minimum,
        excitation_span_minimum=excitation_span_minimum,
        decomposition_tolerance=decomposition_tolerance,
    )
    run_spec = _run_spec(
        analysis,
        calibration_pair,
        validation_pair,
        fit_improvement_minimum=fit_improvement_minimum,
        excitation_span_minimum=excitation_span_minimum,
        decomposition_tolerance=decomposition_tolerance,
    )
    RunSpec.model_validate(run_spec)
    return R41ExamplePayload(
        manifest=build_r41_manifest(),
        scenario=summary,
        calibrationPair=calibration_pair,
        validationPair=validation_pair,
        analysis=analysis,
        runSpec=run_spec,
    )


@lru_cache(maxsize=1)
def _scenario() -> R41Scenario:
    summary = R41ScenarioSummary(
        scenarioId=R41_DEFAULT_SCENARIO_ID,
        title="Independent real calibration and holdout evidence (open)",
        description=(
            "No real TwinCAT capture is bundled. R4.1 requires two disjoint, "
            "case-scoped R7-E passes from the same selected device."
        ),
        expectedOutcome="Inconclusive",
        realityValidationStatus="Open",
        countsTowardReality=False,
    )
    payload = _payload(summary, None, None)
    return R41Scenario(
        summary=summary,
        calibration_pair=None,
        validation_pair=None,
        analysis=payload.analysis,
        run_spec=payload.run_spec,
    )


def list_r41_scenarios() -> tuple[R41ScenarioSummary, ...]:
    return (_scenario().summary,)


def load_r41_scenario(scenario_id: str = R41_DEFAULT_SCENARIO_ID) -> R41Scenario:
    if scenario_id != R41_DEFAULT_SCENARIO_ID:
        raise KeyError(
            f"unknown R4.1 scenario '{scenario_id}'; expected: {R41_DEFAULT_SCENARIO_ID}"
        )
    return _scenario()


def r41_example_payload(
    scenario_id: str = R41_DEFAULT_SCENARIO_ID,
) -> R41ExamplePayload:
    scenario = load_r41_scenario(scenario_id)
    return _payload(
        scenario.summary, scenario.calibration_pair, scenario.validation_pair
    )


def assess_r41_payload(request: R41AssessmentRequest) -> R41ExamplePayload:
    analysis = assess_r41_reality(
        request.calibration_pair,
        request.validation_pair,
        fit_improvement_minimum=request.fit_improvement_minimum,
        excitation_span_minimum=request.excitation_span_minimum,
        decomposition_tolerance=request.decomposition_tolerance,
    )
    expected_outcome = (
        "Passed"
        if analysis.reality_validation_status == "Passed"
        else "Failed"
        if analysis.reality_validation_status in {"Refuted", "Blocked"}
        else "Inconclusive"
    )
    summary = R41ScenarioSummary(
        scenarioId="external-physical-reality-assessment",
        title="External two-run physical reality assessment",
        description=(
            "The calibration run is fitted once and the disjoint validation run "
            "is evaluated without interpolation or parameter refit."
        ),
        expectedOutcome=expected_outcome,
        realityValidationStatus=analysis.reality_validation_status,
        countsTowardReality=analysis.counts_toward_reality,
    )
    return _payload(
        summary,
        request.calibration_pair,
        request.validation_pair,
        fit_improvement_minimum=request.fit_improvement_minimum,
        excitation_span_minimum=request.excitation_span_minimum,
        decomposition_tolerance=request.decomposition_tolerance,
    )


def r41_example_run_spec(
    scenario_id: str = R41_DEFAULT_SCENARIO_ID,
) -> dict[str, Any]:
    return deepcopy(load_r41_scenario(scenario_id).run_spec)


def validate_r41_example_run_spec(
    scenario_id: str = R41_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r41_example_run_spec(scenario_id))


__all__ = [
    "R41_ALIGNMENT_METRIC_ID",
    "R41_CALIBRATION_METRIC_ID",
    "R41_CONTRACT_METRIC_ID",
    "R41_DECOMPOSITION_METRIC_ID",
    "R41_DEPLOYMENT_METRIC_ID",
    "R41_FIT_METRIC_ID",
    "R41_INDEPENDENT_METRIC_ID",
    "R41_LINEAR_RMSE_METRIC_ID",
    "R41_REALITY_METRIC_ID",
    "R41_ROTARY_RMSE_METRIC_ID",
    "assess_r41_payload",
    "assess_r41_reality",
    "build_r41_manifest",
    "build_reality_evidence_pair",
    "list_r41_scenarios",
    "load_r41_scenario",
    "r41_example_payload",
    "r41_example_run_spec",
    "validate_r41_example_run_spec",
]
