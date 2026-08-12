from __future__ import annotations

import math
from typing import Iterable, Sequence

from ..evaluator import _content_hash
from ..five_axis.f3_sampling import M5DiscreteCommand
from .models import (
    CalibrationAxisResult,
    CalibrationResult,
    PhysicalApplicability,
    PhysicalAxisParameter,
    PhysicalModelDefinition,
    PhysicalResponseSample,
    PhysicalResponseTrace,
)

_AXIS_IDS = ("X", "Y", "Z", "B", "C")
_AXIS_UNITS = ("mm", "mm", "mm", "rad", "rad")
_UNIT_FAMILIES = ("linear-mm", "linear-mm", "linear-mm", "rotary-rad", "rotary-rad")
_TAU_GRID = tuple(value / 1000.0 for value in range(20, 401, 5))


def physical_model_content_hash(model: PhysicalModelDefinition) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    return _content_hash(payload)


def physical_response_content_hash(trace: PhysicalResponseTrace) -> str:
    payload = trace.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"})
    return _content_hash(payload)


def calibration_content_hash(calibration: CalibrationResult) -> str:
    payload = calibration.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"})
    return _content_hash(payload)


def exact_zoh_response(
    command: Sequence[float],
    times: Sequence[float],
    *,
    time_constant_seconds: float,
    bias: float,
) -> tuple[float, ...]:
    if not command or len(command) != len(times):
        raise ValueError("command and times must be non-empty and have equal length")
    if time_constant_seconds <= 0 or not math.isfinite(time_constant_seconds):
        raise ValueError("time_constant_seconds must be finite and positive")
    if not math.isfinite(bias):
        raise ValueError("bias must be finite")
    if any(not math.isfinite(value) for value in command) or any(not math.isfinite(value) for value in times):
        raise ValueError("command and times must contain finite values")
    if any(right <= left for left, right in zip(times, times[1:], strict=False)):
        raise ValueError("times must be strictly increasing")

    state = float(command[0])
    response = [state + bias]
    for index in range(1, len(command)):
        dt = float(times[index] - times[index - 1])
        alpha = math.exp(-dt / time_constant_seconds)
        held_command = float(command[index - 1])
        state = held_command + (state - held_command) * alpha
        response.append(state + bias)
    return tuple(response)


def _rmse(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("RMSE operands must be non-empty and have equal length")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) / len(left))


def fit_first_order_axis(
    *,
    axis_id: str,
    axis_index: int,
    unit_family: str,
    unit: str,
    command: Sequence[float],
    observation: Sequence[float],
    times: Sequence[float],
    excitation_span_minimum: float,
    tau_grid: Iterable[float] = _TAU_GRID,
) -> CalibrationAxisResult:
    if len(command) != len(observation) or len(command) != len(times) or not command:
        raise ValueError("calibration command, observation and times must have equal non-zero length")
    span = float(max(command) - min(command))
    if span < excitation_span_minimum:
        return CalibrationAxisResult(
            axisId=axis_id,
            axisIndex=axis_index,
            unitFamily=unit_family,
            unit=unit,
            status="insufficient-excitation",
            excitationSpan=span,
            deterministicWorkUnits=0,
        )

    candidates = tuple(float(value) for value in tau_grid)
    if not candidates:
        raise ValueError("tau_grid must not be empty")
    best: tuple[float, float, float] | None = None
    for tau in candidates:
        zero_bias = exact_zoh_response(command, times, time_constant_seconds=tau, bias=0.0)
        bias = sum(observed_value - predicted for observed_value, predicted in zip(observation, zero_bias, strict=True)) / len(
            observation
        )
        predicted = tuple(value + bias for value in zero_bias)
        score = _rmse(predicted, observation)
        candidate = (score, tau, bias)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    rmse, tau, bias = best
    return CalibrationAxisResult(
        axisId=axis_id,
        axisIndex=axis_index,
        unitFamily=unit_family,
        unit=unit,
        status="identified",
        excitationSpan=span,
        timeConstantSeconds=tau,
        bias=bias,
        rmse=rmse,
        deterministicWorkUnits=len(candidates),
    )


def fit_first_order_model(
    *,
    calibration_id: str,
    model_id: str,
    calibration_command_content_id: str,
    calibration_trace_content_hash: str,
    device_id: str,
    controller_family: str,
    trajectory_families: Sequence[str],
    sample_period: float,
    commands_by_axis: Sequence[Sequence[float]],
    observations_by_axis: Sequence[Sequence[float]],
    times: Sequence[float],
    excitation_span_minimum: float,
) -> tuple[PhysicalModelDefinition, CalibrationResult]:
    if len(commands_by_axis) != 5 or len(observations_by_axis) != 5:
        raise ValueError("five command and observation axis series are required")
    calibrated_axes = tuple(
        fit_first_order_axis(
            axis_id=_AXIS_IDS[index],
            axis_index=index,
            unit_family=_UNIT_FAMILIES[index],
            unit=_AXIS_UNITS[index],
            command=commands_by_axis[index],
            observation=observations_by_axis[index],
            times=times,
            excitation_span_minimum=excitation_span_minimum,
        )
        for index in range(5)
    )
    calibration_payload = {
        "calibrationId": calibration_id,
        "methodId": "five-axis.first-order-grid-calibration@1",
        "axes": [axis.model_dump(mode="json", by_alias=True, exclude_none=True) for axis in calibrated_axes],
    }
    calibration_payload["contentHash"] = _content_hash(calibration_payload)
    calibration = CalibrationResult.model_validate(calibration_payload)
    model_axes = tuple(
        PhysicalAxisParameter(
            axisId=axis.axis_id,
            axisIndex=axis.axis_index,
            unitFamily=axis.unit_family,
            unit=axis.unit,
            excitationStatus=axis.status,
            timeConstantSeconds=axis.time_constant_seconds,
            bias=axis.bias,
        )
        for axis in calibrated_axes
    )
    model = PhysicalModelDefinition(
        schemaId="five-axis.physical-model-definition@1",
        schemaVersion=1,
        modelId=model_id,
        modelFamilyId="five-axis.independent-first-order-axis-model@1",
        integrationMethod="exact-zoh",
        stateDefinition=tuple(f"x_{axis_id}" for axis_id in _AXIS_IDS),
        inputDefinition=tuple(f"q_command_{axis_id}" for axis_id in _AXIS_IDS),
        outputDefinition=tuple(f"q_response_{axis_id}" for axis_id in _AXIS_IDS),
        parameterSource="deterministic-grid-search",
        calibrationId=calibration_id,
        calibrationCommandContentId=calibration_command_content_id,
        calibrationTraceContentHash=calibration_trace_content_hash,
        alignmentPolicyId="five-axis.physical-alignment.exact-device-time@1",
        axes=model_axes,
        applicability=PhysicalApplicability(
            deviceIds=(device_id,),
            controllerFamilies=(controller_family,),
            trajectoryFamilies=tuple(trajectory_families),
            samplePeriodMinSeconds=sample_period,
            samplePeriodMaxSeconds=sample_period,
            evidenceSource="synthetic-sil",
        ),
        unmodeledFactors=(
            "friction-and-backlash",
            "controller-feedforward-and-saturation",
            "cross-axis-coupling-and-structural-flexibility",
            "geometric-assembly-error",
            "thermal-drift",
            "cutting-force-tool-workpiece-process",
            "sensor-and-external-metrology-uncertainty",
        ),
    )
    return model, calibration


def simulate_physical_response(
    model: PhysicalModelDefinition,
    command: M5DiscreteCommand,
    *,
    response_trace_id: str,
) -> PhysicalResponseTrace:
    from .applicability import require_physical_model_sample_period

    require_physical_model_sample_period(model, command.sample_period)
    times = tuple(float(sample.t) for sample in command.samples)
    commands_by_axis = tuple(tuple(float(sample.q[index]) for sample in command.samples) for index in range(5))
    simulated_by_axis: list[tuple[float, ...]] = []
    for axis in model.axes:
        series = commands_by_axis[axis.axis_index]
        if axis.excitation_status == "insufficient-excitation":
            if max(series) - min(series) > 1e-12:
                raise ValueError(
                    f"validation command excites uncalibrated axis {axis.axis_id}; no response may be synthesized"
                )
            simulated_by_axis.append(series)
            continue
        assert axis.time_constant_seconds is not None and axis.bias is not None
        simulated_by_axis.append(
            exact_zoh_response(
                series,
                times,
                time_constant_seconds=axis.time_constant_seconds,
                bias=axis.bias,
            )
        )
    samples = tuple(
        PhysicalResponseSample(
            sampleIndex=index,
            t=time,
            command=tuple(commands_by_axis[axis][index] for axis in range(5)),
            simulated=tuple(simulated_by_axis[axis][index] for axis in range(5)),
        )
        for index, time in enumerate(times)
    )
    response_payload = {
        "artifactType": "five-axis.physical-response-trace",
        "schemaId": "five-axis.physical-response-trace@1",
        "schemaVersion": 1,
        "responseTraceId": response_trace_id,
        "sourceKind": "synthetic-sil",
        "sourceModelId": model.model_id,
        "sourceModelContentHash": physical_model_content_hash(model),
        "sourceCommandId": command.discrete_command_id,
        "sourceCommandContentId": command.content_id,
        "samplePeriod": command.sample_period,
        "axisUnits": _AXIS_UNITS,
        "integrationMethod": "exact-zoh",
        "samples": [sample.model_dump(mode="json", by_alias=True) for sample in samples],
    }
    response_payload["contentHash"] = _content_hash(response_payload)
    return PhysicalResponseTrace.model_validate(response_payload)


__all__ = [
    "calibration_content_hash",
    "exact_zoh_response",
    "fit_first_order_axis",
    "fit_first_order_model",
    "physical_model_content_hash",
    "physical_response_content_hash",
    "simulate_physical_response",
]
