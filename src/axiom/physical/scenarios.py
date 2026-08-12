from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from ..five_axis.f4_scenarios import load_f4_scenario
from ..five_axis.f4_scenarios import validate_f4_example_run_spec
from ..machine.models import (
    ClockMapping,
    CoordinateAlignment,
    DeviceChannel,
    DeviceIdentity,
    DeviceProfile,
    MachineObservationRequest,
    MachineRunLineage,
    MachineTelemetryTrace,
    TelemetryFrame,
    TelemetrySample,
    UpstreamClaimReference,
)
from ..machine.runtime import (
    CLOCK_ALIGNED_METRIC_ID,
    COORDINATE_CONTEXT_METRIC_ID,
    LINEAGE_COMPLETE_METRIC_ID,
    RAW_INTEGRITY_METRIC_ID,
    READ_ONLY_CAPTURE_METRIC_ID,
    machine_trace_content_hash,
)
from ..models import CaseOutcome, Claim, EvaluationCase, MetricResult, RunSpec
from ..run import evaluate_run, validate_run_bundle_integrity
from .runtime import (
    ALIGNMENT_VALID_METRIC_ID,
    CALIBRATION_TRACEABLE_METRIC_ID,
    CONTRACT_VALID_METRIC_ID,
    DECOMPOSITION_CLOSED_METRIC_ID,
    FIT_WITHIN_TOLERANCE_METRIC_ID,
    FIVE_AXIS_PHYSICAL_DOMAIN_PACK_ID,
    LINEAR_IMPROVEMENT_RATIO_METRIC_ID,
    LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID,
    LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
    PHYSICAL_EVALUATOR_ID,
    PHYSICAL_RUNNER_ID,
    REALITY_VALIDATED_METRIC_ID,
    ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
)
from .models import (
    _identity_hash,
    AxisChannelBinding,
    AxisValidationSeries,
    CalibrationResult,
    PhysicalEvidencePair,
    PhysicalModelDefinition,
    PhysicalResponseTrace,
    PhysicalRunAlignment,
    PhysicalValidationAnalysis,
)
from .simulation import (
    fit_first_order_model,
    simulate_physical_response,
)

_DEFAULT_SCENARIO_ID = "in-domain-synthetic-sil"
_AXIS_IDS = ("X", "Y", "Z", "B", "C")
_AXIS_UNITS = ("mm", "mm", "mm", "rad", "rad")
_UNIT_FAMILIES = ("linear-mm", "linear-mm", "linear-mm", "rotary-rad", "rotary-rad")
_EXCITATION_SPAN_MINIMUM = 0.05
_FIT_IMPROVEMENT_MINIMUM = 0.35
_DECOMPOSITION_TOLERANCE = 1e-12
_DEVICE_ID = "sim-840d-r4"
_CONTROLLER_FAMILY = "siemens-840d"
_CALIBRATION_ID = "five-axis.r4.synthetic-calibration@1"
_MODEL_ID = "five-axis.r4.synthetic-first-order-model@1"
_VALIDATION_ANALYSIS_METHOD_ID = "five-axis.physical-validation-analysis@1"
_MANIFEST_ID = "physical.r4-manifest@1"
_SCENARIO_AXIS_IDS = list(_AXIS_IDS)
_BASE_TIME = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)
_F4_UPSTREAM_SCENARIO_ID = "canonical-head-table-solver"
_F4_CLAIM_IDS = frozenset(
    {
        "five-axis.geometry-valid-claim@1",
        "five-axis.task-geometry-collision-free-claim@1",
        "five-axis.kinematically-feasible-claim@1",
        "five-axis.configuration-collision-free-claim@1",
        "five-axis.continuously-feasible-claim@1",
        "five-axis.interval-certified-claim@1",
        "five-axis.model-collision-free-claim@1",
    }
)


def _axis_channel_id(axis_id: str) -> str:
    return f"axis.{axis_id.lower()}.actual"


def _timestamp(seconds: float, *, offset_seconds: float = 0.0) -> str:
    return (_BASE_TIME + timedelta(seconds=seconds + offset_seconds)).isoformat().replace("+00:00", "Z")


def _rmse(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) / len(left))


def _group_rmse(
    axes: tuple[AxisValidationSeries, ...],
    *,
    unit_family: str,
    field: str,
) -> float | None:
    squared: list[float] = []
    for axis in axes:
        if axis.unit_family != unit_family or axis.excitation_status != "identified":
            continue
        source = axis.command if field == "math" else axis.simulation
        squared.extend((left - right) ** 2 for left, right in zip(source, axis.observation, strict=True))
    return math.sqrt(sum(squared) / len(squared)) if squared else None


def _independent_oracle_response(
    command: tuple[float, ...],
    times: tuple[float, ...],
    *,
    tau_primary: float,
    tau_secondary: float,
    bias: float,
    disturbance_scale: float,
    phase: float,
) -> tuple[float, ...]:
    if len(command) != len(times) or not command:
        raise ValueError("command and times must have equal non-zero length")
    stage_one = float(command[0])
    stage_two = float(command[0])
    response = [stage_two + bias]
    total_duration = max(times[-1] - times[0], 1e-9)
    for index in range(1, len(times)):
        dt = times[index] - times[index - 1]
        alpha_one = math.exp(-dt / tau_primary)
        alpha_two = math.exp(-dt / tau_secondary)
        held_command = float(command[index - 1])
        stage_one = held_command + (stage_one - held_command) * alpha_one
        stage_two = stage_one + (stage_two - stage_one) * alpha_two
        normalized_time = (times[index] - times[0]) / total_duration
        disturbance = disturbance_scale * (
            0.65 * math.sin(2.7 * times[index] + phase)
            + 0.25 * math.cos(5.1 * times[index] + 0.5 * phase)
            + 0.10 * normalized_time
        )
        response.append(stage_two + bias + disturbance)
    return tuple(response)


def _command_series(command, axis_index: int) -> tuple[float, ...]:
    return tuple(float(sample.q[axis_index]) for sample in command.samples)


def _time_series(command) -> tuple[float, ...]:
    return tuple(float(sample.t) for sample in command.samples)


def _build_trace(
    *,
    trace_id: str,
    observed_by_axis: tuple[tuple[float, ...], ...],
    times: tuple[float, ...],
    time_shift_seconds: float = 0.0,
) -> MachineTelemetryTrace:
    provisional = MachineTelemetryTrace(
        artifactType="machine.telemetry-trace",
        schemaVersion=1,
        traceId=trace_id,
        sourceKind="synthetic-replay",
        captureReceipt={
            "receiptId": f"receipt:{trace_id}",
            "sourceId": "axiom.windows-file-telemetry-source@1",
            "operation": "file-import",
            "transport": "windows-file-json",
            "capturedAt": _timestamp(times[-1] + time_shift_seconds),
            "traceContentHash": "0" * 64,
        },
        deviceIdentity=DeviceIdentity(
            deviceId=_DEVICE_ID,
            controllerFamily=_CONTROLLER_FAMILY,
            machineModel="vmc-5x-r4-sim",
        ),
        frames=tuple(
            TelemetryFrame(
                sequenceId=100 + index,
                deviceTimestamp=_timestamp(time, offset_seconds=time_shift_seconds),
                samples=tuple(
                    TelemetrySample(
                        channelId=_axis_channel_id(axis_id),
                        value=observed_by_axis[axis][index],
                        unit=_AXIS_UNITS[axis],
                    )
                    for axis, axis_id in enumerate(_AXIS_IDS)
                ),
            )
            for index, time in enumerate(times)
        ),
        vendorMetadata={
            "programName": "DEMO_5X_R4",
            "channel": "CHANNEL_1",
            "platform": "windows",
        },
    )
    trace_hash = machine_trace_content_hash(provisional)
    return provisional.model_copy(
        update={
            "capture_receipt": provisional.capture_receipt.model_copy(
                update={"trace_content_hash": trace_hash}
            )
        }
    )


def _device_profile() -> DeviceProfile:
    return DeviceProfile(
        profileId="device-profile.sim-840d-r4@1",
        deviceId=_DEVICE_ID,
        manufacturer="Axiom Simulation",
        machineModel="vmc-5x-r4-sim",
        controllerFamily=_CONTROLLER_FAMILY,
        firmwareVersion="sim-fw-1.0",
        exportVersion="windows-file-json@1",
        allowedReadOnlyOperations=("file-import",),
        calibrationId="calibration.sim-840d-r4@1",
        channels=tuple(
            DeviceChannel(
                channelId=_axis_channel_id(axis_id),
                kind="scalar",
                unit=_AXIS_UNITS[index],
            )
            for index, axis_id in enumerate(_AXIS_IDS)
        ),
    )


def _clock_mapping(reference_timestamp: str) -> ClockMapping:
    return ClockMapping(
        mappingId="clock-map.sim-840d-r4@1",
        deviceId=_DEVICE_ID,
        mappingMethod="fixed-offset",
        deviceReferenceTimestamp=reference_timestamp,
        hostReferenceTimestamp=(_BASE_TIME + timedelta(milliseconds=12)).isoformat().replace("+00:00", "Z"),
        offsetMilliseconds=12.0,
        driftBoundMilliseconds=1.5,
    )


def _coordinate_alignment() -> CoordinateAlignment:
    return CoordinateAlignment(
        alignmentId="alignment.sim-840d-r4@1",
        deviceId=_DEVICE_ID,
        machineCoordinateFrame="machine",
        workCoordinateFrame="workpiece",
        sourceKind="synthetic-reference",
        effectiveAt="2026-08-11T00:00:00Z",
        calibrationStatus="calibrated",
        calibrationId="calibration.sim-840d-r4@1",
        channelIds=tuple(_axis_channel_id(axis_id) for axis_id in _AXIS_IDS),
    )


def _observation_request(
    *,
    trace: MachineTelemetryTrace,
    coordinate_alignment: CoordinateAlignment | None,
    lineage: MachineRunLineage,
) -> MachineObservationRequest:
    required_metrics = [
        RAW_INTEGRITY_METRIC_ID,
        READ_ONLY_CAPTURE_METRIC_ID,
        LINEAGE_COMPLETE_METRIC_ID,
        CLOCK_ALIGNED_METRIC_ID,
    ]
    if coordinate_alignment is not None:
        required_metrics.append(COORDINATE_CONTEXT_METRIC_ID)
    else:
        required_metrics.append(COORDINATE_CONTEXT_METRIC_ID)
    return MachineObservationRequest(
        artifact=trace,
        deviceProfile=_device_profile(),
        clockMapping=_clock_mapping(trace.frames[0].device_timestamp),
        coordinateAlignment=coordinate_alignment,
        lineage=lineage,
        case=EvaluationCase(
            caseId=f"machine-r3-bootstrap:{trace.trace_id}@1",
            requiredMetrics=required_metrics,
        ),
    )


@lru_cache(maxsize=3)
def _paired_lineage(f4_scenario_id: str, command_content_id: str, trace_id: str) -> MachineRunLineage:
    bundle = evaluate_run(validate_f4_example_run_spec(f4_scenario_id))
    upstream = tuple(
        UpstreamClaimReference(
            claimDefinitionId=claim.claim_definition_id,
            status=claim.status.value,
            reportContentHash=bundle.report.content_hash,
        )
        for claim in bundle.claims
        if claim.claim_definition_id in _F4_CLAIM_IDS
    )
    return MachineRunLineage(
        machineRunId=f"machine-run:{trace_id}",
        pairingStatus="paired",
        baselineKind="reference",
        baselineRunBundleHash=bundle.bundle_hash,
        sourceCommandContentHash=command_content_id,
        upstreamClaims=upstream,
    )


def _physical_evidence_pair(
    *,
    pair_id: str,
    role: str,
    command,
    observation: MachineObservationRequest,
) -> PhysicalEvidencePair:
    return PhysicalEvidencePair(
        pairId=pair_id,
        role=role,
        trajectoryFamily="five-axis.canonical-f4",
        command=command,
        observation=observation,
        commandContentId=command.content_id,
        traceContentHash=observation.artifact.capture_receipt.trace_content_hash,
    )


def _alignment() -> PhysicalRunAlignment:
    return PhysicalRunAlignment(
        alignmentId="five-axis.r4.synthetic-alignment@1",
        policyId="five-axis.physical-alignment.exact-device-time@1",
        calibrationCommandStartDeviceTimestamp=_timestamp(0.0),
        validationCommandStartDeviceTimestamp=_timestamp(0.0),
        maximumTimeErrorSeconds=0.002,
        interpolationAllowed=False,
        bindings=tuple(
            AxisChannelBinding(
                axisId=axis_id,
                axisIndex=index,
                channelId=_axis_channel_id(axis_id),
                unitFamily=_UNIT_FAMILIES[index],
                unit=_AXIS_UNITS[index],
            )
            for index, axis_id in enumerate(_AXIS_IDS)
        ),
    )


def _analysis_content_hash(analysis: PhysicalValidationAnalysis) -> str:
    return _identity_hash(analysis, exclude="content_hash")


def _metric_group(metric_id: str) -> str | None:
    if ".linear." in metric_id:
        return "linear-mm"
    if ".rotary." in metric_id:
        return "rotary-rad"
    return None


def _title_from_identifier(identifier: str) -> str:
    stem = identifier.split("@", 1)[0].split(".")[-1]
    words = stem.replace("-", " ").split()
    normalized = [word.upper() if word in {"rmse"} else word for word in words]
    return " ".join(normalized) if normalized else identifier


def _metric_label(result: MetricResult) -> str:
    group = _metric_group(result.metric_id)
    base = _title_from_identifier(result.metric_id)
    if group == "linear-mm":
        return f"Linear {base}"
    if group == "rotary-rad":
        return f"Rotary {base}"
    return _title_from_identifier(result.metric_definition_id)


def _claim_title(claim: Claim) -> str:
    titles = {
        "axiom.core.case-outcome-claim@1": "Canonical run outcome",
        "five-axis.physical-model-contract-valid-claim@1": "Simulation contract validity",
        "five-axis.physical-calibration-traceable-claim@1": "Calibration traceability",
        "five-axis.physical-alignment-valid-claim@1": "Signal alignment validity",
        "five-axis.physical-residual-decomposition-closed-claim@1": "Residual decomposition closure",
        "five-axis.physical-model-fit-within-tolerance-claim@1": "Holdout fit within tolerance",
        "five-axis.physical-model-reality-validated-claim@1": "Reality validation status",
    }
    return titles.get(claim.claim_definition_id, _title_from_identifier(claim.claim_definition_id))


def _normalize_physical_model(model: PhysicalModelDefinition) -> PhysicalModelDefinition:
    return PhysicalModelDefinition.model_validate(
        model.model_dump(mode="json", by_alias=True, exclude_none=True)
    )


def _build_analysis(
    *,
    analysis_id: str,
    calibration: CalibrationResult,
    model: PhysicalModelDefinition,
    calibration_pair: PhysicalEvidencePair,
    validation_pair: PhysicalEvidencePair,
    response_trace: PhysicalResponseTrace,
    leakage_free: bool,
    alignment_coverage: float,
    maximum_time_error_seconds: float,
) -> PhysicalValidationAnalysis:
    command_by_axis = tuple(_command_series(validation_pair.command, axis) for axis in range(5))
    observation_by_axis = tuple(
        tuple(
            float(frame.samples[axis].value)
            for frame in validation_pair.observation.artifact.frames
        )
        for axis in range(5)
    )
    simulation_by_axis = tuple(
        tuple(sample.simulated[axis] for sample in response_trace.samples)
        for axis in range(5)
    )
    axis_series = []
    closure_max = 0.0
    for axis in model.axes:
        command = command_by_axis[axis.axis_index]
        simulation = simulation_by_axis[axis.axis_index]
        observation = observation_by_axis[axis.axis_index]
        if axis.excitation_status == "identified":
            math_rmse = _rmse(command, observation)
            sim_rmse = _rmse(simulation, observation)
            improvement = (math_rmse - sim_rmse) / math_rmse if math_rmse > 0 else None
            closure = max(
                abs((obs - cmd) - ((obs - sim) + (sim - cmd)))
                for obs, sim, cmd in zip(observation, simulation, command, strict=True)
            )
            closure_max = max(closure_max, closure)
        else:
            math_rmse = sim_rmse = improvement = closure = None
        axis_series.append(
            AxisValidationSeries(
                axisId=axis.axis_id,
                axisIndex=axis.axis_index,
                unitFamily=axis.unit_family,
                unit=axis.unit,
                excitationStatus=axis.excitation_status,
                times=tuple(sample.t for sample in response_trace.samples),
                command=command,
                simulation=simulation,
                observation=observation,
                mathObservationRmse=math_rmse,
                simulationObservationRmse=sim_rmse,
                improvementRatio=improvement,
                decompositionClosureMax=closure,
            )
        )
    axis_series_tuple = tuple(axis_series)
    linear_math_rmse = _group_rmse(axis_series_tuple, unit_family="linear-mm", field="math")
    linear_sim_rmse = _group_rmse(axis_series_tuple, unit_family="linear-mm", field="simulation")
    rotary_math_rmse = _group_rmse(axis_series_tuple, unit_family="rotary-rad", field="math")
    rotary_sim_rmse = _group_rmse(axis_series_tuple, unit_family="rotary-rad", field="simulation")
    linear_improvement = (
        (linear_math_rmse - linear_sim_rmse) / linear_math_rmse
        if linear_math_rmse is not None and linear_sim_rmse is not None and linear_math_rmse > 0
        else None
    )
    provisional = PhysicalValidationAnalysis.model_construct(
        analysis_id=analysis_id,
        method_id=_VALIDATION_ANALYSIS_METHOD_ID,
        source_kind="synthetic-sil",
        calibration=calibration,
        leakage_free=leakage_free,
        alignment_coverage=alignment_coverage,
        maximum_time_error_seconds=maximum_time_error_seconds,
        axes=axis_series_tuple,
        linear_math_observation_rmse=linear_math_rmse,
        linear_simulation_observation_rmse=linear_sim_rmse,
        linear_improvement_ratio=linear_improvement,
        rotary_math_observation_rmse=rotary_math_rmse,
        rotary_simulation_observation_rmse=rotary_sim_rmse,
        decomposition_closure_max=closure_max,
        fit_within_tolerance=bool(
            leakage_free
            and alignment_coverage == 1.0
            and linear_improvement is not None
            and linear_improvement >= _FIT_IMPROVEMENT_MINIMUM
            and closure_max <= _DECOMPOSITION_TOLERANCE
        ),
        content_hash="0" * 64,
    )
    payload = provisional.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["contentHash"] = _analysis_content_hash(provisional)
    return PhysicalValidationAnalysis.model_validate(payload)


@dataclass(frozen=True, slots=True)
class R4ScenarioSummary:
    scenarioId: str
    title: str
    description: str
    axisIds: list[str]
    syntheticContractStatus: str
    realityValidationStatus: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenarioId,
            "title": self.title,
            "description": self.description,
            "axisIds": list(self.axisIds),
            "syntheticContractStatus": self.syntheticContractStatus,
            "realityValidationStatus": self.realityValidationStatus,
        }


@dataclass(frozen=True, slots=True)
class PhysicalR4Scenario:
    summary: R4ScenarioSummary
    calibrationPair: PhysicalEvidencePair
    validationPair: PhysicalEvidencePair
    alignment: PhysicalRunAlignment
    physicalModel: PhysicalModelDefinition
    validationArtifact: PhysicalResponseTrace
    validationAnalysis: PhysicalValidationAnalysis
    runSpec: dict[str, Any]


def _build_observed_axes(
    command,
    *,
    variant: str,
) -> tuple[tuple[float, ...], ...]:
    times = _time_series(command)
    if variant == "mismatch":
        return tuple(
            tuple(
                value + (0.001 if index % 2 else -0.001) * (axis_index + 1)
                for index, value in enumerate(_command_series(command, axis_index))
            )
            for axis_index in range(5)
        )
    settings = {
        "default": (
            (0.10, 0.045, 0.018, 0.010, 0.15),
            (0.11, 0.050, -0.014, 0.008, 0.55),
            (0.095, 0.042, 0.006, 0.006, 0.95),
            (0.10, 0.045, 0.0, 0.0004, 1.25),
            (0.10, 0.045, 0.0, 0.0004, 1.55),
        ),
    }[variant]
    observed = []
    for axis_index, config in enumerate(settings):
        command_series = _command_series(command, axis_index)
        tau_primary, tau_secondary, bias, disturbance_scale, phase = config
        observed.append(
            _independent_oracle_response(
                command_series,
                times,
                tau_primary=tau_primary,
                tau_secondary=tau_secondary,
                bias=bias,
                disturbance_scale=disturbance_scale,
                phase=phase,
            )
        )
    return tuple(observed)


def _physical_run_spec(
    *,
    scenario_id: str,
    artifact: PhysicalResponseTrace,
    physical_model: PhysicalModelDefinition,
    calibration_pair: PhysicalEvidencePair,
    validation_pair: PhysicalEvidencePair,
    alignment: PhysicalRunAlignment,
    required_metrics: tuple[str, ...] | None = None,
    optional_metrics: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    required = required_metrics or (
        CONTRACT_VALID_METRIC_ID,
        CALIBRATION_TRACEABLE_METRIC_ID,
        ALIGNMENT_VALID_METRIC_ID,
        DECOMPOSITION_CLOSED_METRIC_ID,
        FIT_WITHIN_TOLERANCE_METRIC_ID,
    )
    optional = optional_metrics or (
        LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID,
        LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
        LINEAR_IMPROVEMENT_RATIO_METRIC_ID,
        ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
        REALITY_VALIDATED_METRIC_ID,
    )
    case = EvaluationCase(
        caseId=f"five-axis.r4.{scenario_id}@1",
        requiredMetrics=list(required),
        optionalMetrics=list(optional),
    )
    return RunSpec(
        subjectId=physical_model.model_id,
        subjectVersion="1",
        domainPackId=FIVE_AXIS_PHYSICAL_DOMAIN_PACK_ID,
        runnerId=PHYSICAL_RUNNER_ID,
        evaluatorVersion=PHYSICAL_EVALUATOR_ID,
        request={
            "artifact": artifact.model_dump(mode="json", by_alias=True, exclude_none=True),
            "physicalModel": physical_model.model_dump(mode="json", by_alias=True, exclude_none=True),
            "calibrationPair": calibration_pair.model_dump(mode="json", by_alias=True, exclude_none=True),
            "validationPair": validation_pair.model_dump(mode="json", by_alias=True, exclude_none=True),
            "alignment": alignment.model_dump(mode="json", by_alias=True, exclude_none=True),
            "fitImprovementMinimum": _FIT_IMPROVEMENT_MINIMUM,
            "excitationSpanMinimum": _EXCITATION_SPAN_MINIMUM,
            "decompositionTolerance": _DECOMPOSITION_TOLERANCE,
            "case": case.model_dump(mode="json", by_alias=True, exclude_none=True),
        },
    ).model_dump(mode="json", by_alias=True, exclude_none=True)


@lru_cache(maxsize=1)
def _build_positive_base() -> PhysicalR4Scenario:
    calibration_command = load_f4_scenario("canonical-dual-table-solver").sutCommand
    validation_command = load_f4_scenario("canonical-head-table-solver").sutCommand
    assert calibration_command is not None and validation_command is not None

    calibration_times = _time_series(calibration_command)
    validation_times = _time_series(validation_command)
    calibration_observed = _build_observed_axes(calibration_command, variant="default")
    validation_observed = _build_observed_axes(validation_command, variant="default")

    calibration_trace = _build_trace(
        trace_id="trace-r4-calibration",
        observed_by_axis=calibration_observed,
        times=calibration_times,
    )
    validation_trace = _build_trace(
        trace_id="trace-r4-validation",
        observed_by_axis=validation_observed,
        times=validation_times,
    )
    calibration_observation = _observation_request(
        trace=calibration_trace,
        coordinate_alignment=_coordinate_alignment(),
        lineage=_paired_lineage(
            "canonical-dual-table-solver",
            calibration_command.content_id,
            calibration_trace.trace_id,
        ),
    )
    validation_observation = _observation_request(
        trace=validation_trace,
        coordinate_alignment=_coordinate_alignment(),
        lineage=_paired_lineage(
            "canonical-head-table-solver",
            validation_command.content_id,
            validation_trace.trace_id,
        ),
    )
    calibration_pair = _physical_evidence_pair(
        pair_id="five-axis.r4.pair.calibration@1",
        role="calibration",
        command=calibration_command,
        observation=calibration_observation,
    )
    validation_pair = _physical_evidence_pair(
        pair_id="five-axis.r4.pair.validation@1",
        role="validation",
        command=validation_command,
        observation=validation_observation,
    )
    model, calibration = fit_first_order_model(
        calibration_id=_CALIBRATION_ID,
        model_id=_MODEL_ID,
        calibration_command_content_id=calibration_pair.command_content_id,
        calibration_trace_content_hash=calibration_pair.trace_content_hash,
        device_id=_DEVICE_ID,
        controller_family=_CONTROLLER_FAMILY,
        trajectory_families=("five-axis.canonical-f4",),
        sample_period=calibration_command.sample_period,
        commands_by_axis=tuple(_command_series(calibration_command, axis) for axis in range(5)),
        observations_by_axis=calibration_observed,
        times=calibration_times,
        excitation_span_minimum=_EXCITATION_SPAN_MINIMUM,
    )
    model = _normalize_physical_model(model)
    response_trace = simulate_physical_response(
        model,
        validation_command,
        response_trace_id="five-axis.r4.response.validation@1",
    )
    analysis = _build_analysis(
        analysis_id="five-axis.r4.analysis.validation@1",
        calibration=calibration,
        model=model,
        calibration_pair=calibration_pair,
        validation_pair=validation_pair,
        response_trace=response_trace,
        leakage_free=True,
        alignment_coverage=1.0,
        maximum_time_error_seconds=0.0,
    )
    summary = R4ScenarioSummary(
        scenarioId=_DEFAULT_SCENARIO_ID,
        title="In-domain synthetic SIL",
        description="Calibration uses the canonical dual-table solver command; held-out validation uses the canonical head-table solver command. B/C remain insufficiently excited and reality validation stays open.",
        axisIds=_SCENARIO_AXIS_IDS,
        syntheticContractStatus="Passed",
        realityValidationStatus="Open",
    )
    alignment = _alignment()
    return PhysicalR4Scenario(
        summary=summary,
        calibrationPair=calibration_pair,
        validationPair=validation_pair,
        alignment=alignment,
        physicalModel=model,
        validationArtifact=response_trace,
        validationAnalysis=analysis,
        runSpec=_physical_run_spec(
            scenario_id=_DEFAULT_SCENARIO_ID,
            artifact=response_trace,
            physical_model=model,
            calibration_pair=calibration_pair,
            validation_pair=validation_pair,
            alignment=alignment,
        ),
    )


def _build_variants() -> dict[str, PhysicalR4Scenario]:
    base = _build_positive_base()

    validation_command = base.validationPair.command
    mismatch_observed = _build_observed_axes(validation_command, variant="mismatch")
    mismatch_trace = _build_trace(
        trace_id="trace-r4-validation-mismatch",
        observed_by_axis=mismatch_observed,
        times=_time_series(validation_command),
    )
    mismatch_observation = _observation_request(
        trace=mismatch_trace,
        coordinate_alignment=_coordinate_alignment(),
        lineage=_paired_lineage(
            "canonical-head-table-solver",
            validation_command.content_id,
            mismatch_trace.trace_id,
        ),
    )
    mismatch_pair = _physical_evidence_pair(
        pair_id="five-axis.r4.pair.validation-mismatch@1",
        role="validation",
        command=validation_command,
        observation=mismatch_observation,
    )
    mismatch_analysis = _build_analysis(
        analysis_id="five-axis.r4.analysis.mismatch@1",
        calibration=base.validationAnalysis.calibration,
        model=base.physicalModel,
        calibration_pair=base.calibrationPair,
        validation_pair=mismatch_pair,
        response_trace=base.validationArtifact,
        leakage_free=True,
        alignment_coverage=1.0,
        maximum_time_error_seconds=0.0,
    )

    misaligned_trace = _build_trace(
        trace_id="trace-r4-validation-misaligned",
        observed_by_axis=_build_observed_axes(validation_command, variant="default"),
        times=_time_series(validation_command),
        time_shift_seconds=0.02,
    )
    misaligned_observation = _observation_request(
        trace=misaligned_trace,
        coordinate_alignment=_coordinate_alignment(),
        lineage=_paired_lineage(
            "canonical-head-table-solver",
            validation_command.content_id,
            misaligned_trace.trace_id,
        ),
    )
    misaligned_pair = _physical_evidence_pair(
        pair_id="five-axis.r4.pair.validation-misaligned@1",
        role="validation",
        command=validation_command,
        observation=misaligned_observation,
    )
    misaligned_analysis = _build_analysis(
        analysis_id="five-axis.r4.analysis.time-alignment-mismatch@1",
        calibration=base.validationAnalysis.calibration,
        model=base.physicalModel,
        calibration_pair=base.calibrationPair,
        validation_pair=misaligned_pair,
        response_trace=base.validationArtifact,
        leakage_free=True,
        alignment_coverage=0.0,
        maximum_time_error_seconds=0.02,
    )

    leakage_pair = base.calibrationPair.model_copy(update={"role": "validation"})
    leakage_artifact = simulate_physical_response(
        base.physicalModel,
        base.calibrationPair.command,
        response_trace_id="five-axis.r4.response.leakage@1",
    )
    leakage_analysis = _build_analysis(
        analysis_id="five-axis.r4.analysis.leakage@1",
        calibration=base.validationAnalysis.calibration,
        model=base.physicalModel,
        calibration_pair=base.calibrationPair,
        validation_pair=leakage_pair,
        response_trace=leakage_artifact,
        leakage_free=False,
        alignment_coverage=1.0,
        maximum_time_error_seconds=0.0,
    )

    missing_coordinate_observation = _observation_request(
        trace=base.validationPair.observation.artifact,
        coordinate_alignment=None,
        lineage=base.validationPair.observation.lineage,
    )
    missing_coordinate_pair = _physical_evidence_pair(
        pair_id="five-axis.r4.pair.validation-missing-coordinate@1",
        role="validation",
        command=validation_command,
        observation=missing_coordinate_observation,
    )
    missing_coordinate_analysis = _build_analysis(
        analysis_id="five-axis.r4.analysis.missing-coordinate@1",
        calibration=base.validationAnalysis.calibration,
        model=base.physicalModel,
        calibration_pair=base.calibrationPair,
        validation_pair=missing_coordinate_pair,
        response_trace=base.validationArtifact,
        leakage_free=True,
        alignment_coverage=1.0,
        maximum_time_error_seconds=0.0,
    )

    return {
        base.summary.scenarioId: base,
        "model-mismatch-detected": PhysicalR4Scenario(
            summary=R4ScenarioSummary(
                scenarioId="model-mismatch-detected",
                title="Model mismatch detected",
                description="Held-out observation comes from a structurally different SIL oracle regime; the fitted first-order model loses the expected improvement margin.",
                axisIds=_SCENARIO_AXIS_IDS,
                syntheticContractStatus="Passed",
                realityValidationStatus="Open",
            ),
            calibrationPair=base.calibrationPair,
            validationPair=mismatch_pair,
            alignment=base.alignment,
            physicalModel=base.physicalModel,
            validationArtifact=base.validationArtifact,
            validationAnalysis=mismatch_analysis,
            runSpec=_physical_run_spec(
                scenario_id="model-mismatch-detected",
                artifact=base.validationArtifact,
                physical_model=base.physicalModel,
                calibration_pair=base.calibrationPair,
                validation_pair=mismatch_pair,
                alignment=base.alignment,
            ),
        ),
        "time-alignment-mismatch": PhysicalR4Scenario(
            summary=R4ScenarioSummary(
                scenarioId="time-alignment-mismatch",
                title="Time alignment mismatch",
                description="Validation telemetry is shifted beyond the frozen maximum time error budget; no interpolation is allowed.",
                axisIds=_SCENARIO_AXIS_IDS,
                syntheticContractStatus="Passed",
                realityValidationStatus="Open",
            ),
            calibrationPair=base.calibrationPair,
            validationPair=misaligned_pair,
            alignment=base.alignment,
            physicalModel=base.physicalModel,
            validationArtifact=base.validationArtifact,
            validationAnalysis=misaligned_analysis,
            runSpec=_physical_run_spec(
                scenario_id="time-alignment-mismatch",
                artifact=base.validationArtifact,
                physical_model=base.physicalModel,
                calibration_pair=base.calibrationPair,
                validation_pair=misaligned_pair,
                alignment=base.alignment,
            ),
        ),
        "calibration-validation-leakage": PhysicalR4Scenario(
            summary=R4ScenarioSummary(
                scenarioId="calibration-validation-leakage",
                title="Calibration/validation leakage",
                description="Calibration and validation identities collapse onto the same command/trace pair, so the scenario must be blocked.",
                axisIds=_SCENARIO_AXIS_IDS,
                syntheticContractStatus="Passed",
                realityValidationStatus="Open",
            ),
            calibrationPair=base.calibrationPair,
            validationPair=leakage_pair,
            alignment=base.alignment,
            physicalModel=base.physicalModel,
            validationArtifact=leakage_artifact,
            validationAnalysis=leakage_analysis,
            runSpec=_physical_run_spec(
                scenario_id="calibration-validation-leakage",
                artifact=leakage_artifact,
                physical_model=base.physicalModel,
                calibration_pair=base.calibrationPair,
                validation_pair=leakage_pair,
                alignment=base.alignment,
            ),
        ),
        "insufficient-axis-excitation": PhysicalR4Scenario(
            summary=R4ScenarioSummary(
                scenarioId="insufficient-axis-excitation",
                title="Insufficient axis excitation",
                description="The calibration command under-excites B/C; B and C must remain explicitly insufficient rather than receiving fabricated parameters.",
                axisIds=_SCENARIO_AXIS_IDS,
                syntheticContractStatus="Passed",
                realityValidationStatus="Open",
            ),
            calibrationPair=base.calibrationPair,
            validationPair=base.validationPair,
            alignment=base.alignment,
            physicalModel=base.physicalModel,
            validationArtifact=base.validationArtifact,
            validationAnalysis=base.validationAnalysis,
            runSpec=_physical_run_spec(
                scenario_id="insufficient-axis-excitation",
                artifact=base.validationArtifact,
                physical_model=base.physicalModel,
                calibration_pair=base.calibrationPair,
                validation_pair=base.validationPair,
                alignment=base.alignment,
            ),
        ),
        "missing-coordinate-context": PhysicalR4Scenario(
            summary=R4ScenarioSummary(
                scenarioId="missing-coordinate-context",
                title="Missing coordinate context",
                description="Validation telemetry omits calibrated coordinate context, so the observation cannot support full physical interpretation.",
                axisIds=_SCENARIO_AXIS_IDS,
                syntheticContractStatus="Passed",
                realityValidationStatus="Open",
            ),
            calibrationPair=base.calibrationPair,
            validationPair=missing_coordinate_pair,
            alignment=base.alignment,
            physicalModel=base.physicalModel,
            validationArtifact=base.validationArtifact,
            validationAnalysis=missing_coordinate_analysis,
            runSpec=_physical_run_spec(
                scenario_id="missing-coordinate-context",
                artifact=base.validationArtifact,
                physical_model=base.physicalModel,
                calibration_pair=base.calibrationPair,
                validation_pair=missing_coordinate_pair,
                alignment=base.alignment,
                required_metrics=(
                    CONTRACT_VALID_METRIC_ID,
                    ALIGNMENT_VALID_METRIC_ID,
                    DECOMPOSITION_CLOSED_METRIC_ID,
                    FIT_WITHIN_TOLERANCE_METRIC_ID,
                ),
            ),
        ),
    }


@lru_cache(maxsize=1)
def _scenarios() -> dict[str, PhysicalR4Scenario]:
    return _build_variants()


@lru_cache(maxsize=6)
def _scenario_bundle(scenario_id: str):
    bundle = evaluate_run(validate_r4_example_run_spec(scenario_id))
    integrity_errors = validate_run_bundle_integrity(bundle)
    if integrity_errors:
        raise RuntimeError(
            f"built-in R4 scenario '{scenario_id}' produced a non-canonical run bundle: {integrity_errors!r}"
        )
    return bundle


def build_r4_manifest() -> dict[str, Any]:
    return {
        "manifestId": _MANIFEST_ID,
        "schemaId": _MANIFEST_ID,
        "schemaVersion": 1,
        "stage": "R4",
        "domainPackId": "five-axis.domain-pack@6",
        "platform": "windows",
        "defaultScenarioId": _DEFAULT_SCENARIO_ID,
        "safetyBanner": "MODEL VALIDATION / NOT DEVICE SAFE",
        "validationBanner": "SYNTHETIC SIL / REALITY VALIDATION OPEN",
        "syntheticContractStatus": "Passed",
        "realityValidationStatus": "Open",
        "upstreamF4ScenarioId": _F4_UPSTREAM_SCENARIO_ID,
        "model": {
            "equations": ("dx_i/dt = (u_i - x_i) / tau_i", "y_i = x_i + bias_i"),
            "stateIds": [f"x_{axis_id}" for axis_id in _AXIS_IDS],
            "inputIds": [f"q_command_{axis_id}" for axis_id in _AXIS_IDS],
            "outputIds": [f"q_response_{axis_id}" for axis_id in _AXIS_IDS],
            "discretization": "exact-zoh",
            "supportedDevices": [_DEVICE_ID],
            "operatingConditions": ["windows synthetic replay", "held-out canonical F4 solver command"],
            "unmodeledFactors": list(_build_positive_base().physicalModel.unmodeled_factors),
        },
    }


def list_r4_scenarios() -> tuple[R4ScenarioSummary, ...]:
    ordered = (
        _DEFAULT_SCENARIO_ID,
        "model-mismatch-detected",
        "time-alignment-mismatch",
        "calibration-validation-leakage",
        "insufficient-axis-excitation",
        "missing-coordinate-context",
    )
    return tuple(_scenarios()[scenario_id].summary for scenario_id in ordered)


def load_r4_scenario(scenario_id: str = _DEFAULT_SCENARIO_ID) -> PhysicalR4Scenario:
    try:
        return _scenarios()[scenario_id]
    except KeyError as exc:
        available = ", ".join(item.scenarioId for item in list_r4_scenarios())
        raise KeyError(f"unknown R4 scenario '{scenario_id}'; expected one of: {available}") from exc


def r4_example_payload(scenario_id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    scenario = load_r4_scenario(scenario_id)
    analysis = scenario.validationAnalysis
    bundle = _scenario_bundle(scenario_id)
    grouped_metric_results = [
        {
            "metricId": result.metric_id,
            "metricDefinitionId": result.metric_definition_id,
            "label": _metric_label(result),
            "group": group,
            "status": result.status.value,
            "value": result.value,
            "unit": result.unit,
            "thresholdPassed": result.threshold_passed,
            "reasonCode": result.reason_code,
        }
        for result in bundle.report.metric_results
        for group in [_metric_group(result.metric_id)]
        if group is not None
    ]
    canonical_curve_mode = bundle.run.case_outcome is CaseOutcome.PASSED
    payload = {
        "manifest": build_r4_manifest(),
        "scenario": scenario.summary.to_dict(),
        "datasets": {
            "calibration": {
                "datasetId": scenario.calibrationPair.pair_id,
                "traceId": scenario.calibrationPair.observation.artifact.trace_id,
                "scenarioRole": scenario.calibrationPair.role,
                "sourceId": scenario.calibrationPair.observation.artifact.capture_receipt.source_id,
                "capturedAt": scenario.calibrationPair.observation.artifact.capture_receipt.captured_at,
                "contentHash": scenario.calibrationPair.trace_content_hash,
            },
            "validation": {
                "datasetId": scenario.validationPair.pair_id,
                "traceId": scenario.validationPair.observation.artifact.trace_id,
                "scenarioRole": scenario.validationPair.role,
                "sourceId": scenario.validationPair.observation.artifact.capture_receipt.source_id,
                "capturedAt": scenario.validationPair.observation.artifact.capture_receipt.captured_at,
                "contentHash": scenario.validationPair.trace_content_hash,
            },
            "leakageGuards": [
                {
                    "checkId": "distinct-command-content-id",
                    "status": "pass"
                    if scenario.calibrationPair.command_content_id != scenario.validationPair.command_content_id
                    else "blocked",
                    "message": "Calibration and validation commands must not share content identity.",
                },
                {
                    "checkId": "distinct-trace-content-hash",
                    "status": "pass"
                    if scenario.calibrationPair.trace_content_hash != scenario.validationPair.trace_content_hash
                    else "blocked",
                    "message": "Calibration and validation traces must not share trace content hash.",
                },
            ],
        },
        "axes": [
            {
                "axisId": axis.axis_id,
                "family": axis.unit_family,
                "unit": axis.unit,
                "excitationStatus": "excited" if axis.excitation_status == "identified" else "insufficient",
                "series": {
                    "command": [
                        {"time": axis_series.times[index], "value": axis_series.command[index]}
                        for index in range(len(axis_series.times))
                    ],
                    "simulation": [
                        {"time": axis_series.times[index], "value": axis_series.simulation[index]}
                        for index in range(len(axis_series.times))
                    ],
                    "observation": [
                        {"time": axis_series.times[index], "value": axis_series.observation[index]}
                        for index in range(len(axis_series.times))
                    ],
                },
                "metrics": [
                    {
                        "metricId": f"{axis.axis_id.lower()}.math-observation-rmse",
                        "label": f"{axis.axis_id} math-observation RMSE",
                        "group": axis.unit_family,
                        "value": axis_series.math_observation_rmse
                        if axis_series.math_observation_rmse is not None
                        else "InsufficientExcitation",
                        "unit": axis.unit,
                        "axisId": axis.axis_id,
                        "status": axis.excitation_status,
                    },
                    {
                        "metricId": f"{axis.axis_id.lower()}.simulation-observation-rmse",
                        "label": f"{axis.axis_id} simulation-observation RMSE",
                        "group": axis.unit_family,
                        "value": axis_series.simulation_observation_rmse
                        if axis_series.simulation_observation_rmse is not None
                        else "InsufficientExcitation",
                        "unit": axis.unit,
                        "axisId": axis.axis_id,
                        "status": axis.excitation_status,
                    },
                ],
                "residualDecomposition": ([
                    {
                        "componentId": f"{axis.axis_id.lower()}.command-simulation",
                        "label": "command-simulation",
                        "value": max(
                            abs(command - simulated)
                            for command, simulated in zip(axis_series.command, axis_series.simulation, strict=True)
                        ),
                        "unit": axis.unit,
                        "source": "command-simulation",
                    },
                    {
                        "componentId": f"{axis.axis_id.lower()}.simulation-observation",
                        "label": "simulation-observation",
                        "value": max(
                            abs(simulated - observed)
                            for simulated, observed in zip(axis_series.simulation, axis_series.observation, strict=True)
                        ),
                        "unit": axis.unit,
                        "source": "simulation-observation",
                    },
                    {
                        "componentId": f"{axis.axis_id.lower()}.command-observation",
                        "label": "command-observation",
                        "value": max(
                            abs(command - observed)
                            for command, observed in zip(axis_series.command, axis_series.observation, strict=True)
                        ),
                        "unit": axis.unit,
                        "source": "command-observation",
                    },
                ] if axis.excitation_status == "identified" else []),
            }
            for axis, axis_series in zip(scenario.physicalModel.axes, analysis.axes, strict=True)
        ],
        "claims": [
            {
                "claimId": claim.claim_id,
                "claimDefinitionId": claim.claim_definition_id,
                "metricId": claim.metric_id,
                "title": _claim_title(claim),
                "status": claim.status.value,
                "statement": claim.predicate,
                "reasonCode": claim.reason_code,
                "reportContentHash": claim.report_content_hash,
                "evidenceLevel": claim.evidence.level if claim.evidence is not None else None,
                "evidenceIds": ["sealed-run-report"],
            }
            for claim in bundle.claims
            if claim.claim_definition_id == "axiom.core.case-outcome-claim@1"
            or claim.claim_definition_id.startswith("five-axis.physical-")
        ],
        "evidence": [
            {
                "evidenceId": "sealed-run-report",
                "kind": "validation",
                "title": "Canonical evaluation report",
                "summary": (
                    f"Run outcome {bundle.run.case_outcome.value}; "
                    f"execution {bundle.run.execution_status.value}; "
                    "all metric and claim statuses are projected from this sealed report."
                ),
                "contentHash": bundle.report.content_hash,
            },
            *(
                [
                    {
                        "evidenceId": "validation-analysis",
                        "kind": "validation",
                        "title": "Held-out validation analysis",
                        "summary": "Independent SIL oracle versus fitted first-order axis model.",
                        "contentHash": analysis.content_hash,
                    }
                ]
                if canonical_curve_mode
                else [
                    {
                        "evidenceId": "validation-analysis-preview",
                        "kind": "validation",
                        "title": "Diagnostic curve preview",
                        "summary": "Displayed curves are diagnostic preview only and are not canonical evidence for this failing or inconclusive run.",
                    }
                ]
            ),
            {
                "evidenceId": "physical-response-trace",
                "kind": "fit",
                "title": "Physical response trace",
                "summary": "Exact-ZOH replay of the fitted first-order candidate model on the held-out command.",
                "contentHash": scenario.validationArtifact.content_hash,
            },
            {
                "evidenceId": "f4-lineage",
                "kind": "lineage",
                "title": "F4 canonical solver lineage",
                "summary": f"Calibration uses canonical-dual-table-solver; validation uses {_F4_UPSTREAM_SCENARIO_ID}.",
                "contentHash": scenario.validationPair.command_content_id,
            },
        ],
    }
    datasets = payload["datasets"]
    return {
        "manifest": payload["manifest"],
        "scenario": payload["scenario"],
        "model": payload["manifest"]["model"],
        "calibration": datasets["calibration"],
        "validation": {
            **datasets["validation"],
            "leakageGuards": datasets["leakageGuards"],
        },
        "analysis": {
            "traceArtifactType": scenario.validationArtifact.artifact_type,
            "analysisContentHash": analysis.content_hash if canonical_curve_mode else None,
            "curveMode": "canonical-analysis" if canonical_curve_mode else "diagnostic-preview",
            "curveNotice": None
            if canonical_curve_mode
            else "该场景曲线仅用于诊断预览；canonical outcome、metric status 与 claim status 以 sealed run report 为准。",
            "run": {
                "caseOutcome": bundle.run.case_outcome.value,
                "executionStatus": bundle.run.execution_status.value,
                "reportContentHash": bundle.run.report_content_hash,
                "bundleHash": bundle.bundle_hash,
            },
            "axes": payload["axes"],
            "metricResults": grouped_metric_results,
            "claims": payload["claims"],
            "evidence": payload["evidence"],
        },
        "runSpec": scenario.runSpec,
    }


def r4_example_run_spec(scenario_id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    return load_r4_scenario(scenario_id).runSpec


def validate_r4_example_run_spec(scenario_id: str = _DEFAULT_SCENARIO_ID) -> RunSpec:
    return RunSpec.model_validate(r4_example_run_spec(scenario_id))


__all__ = [
    "PhysicalR4Scenario",
    "R4ScenarioSummary",
    "build_r4_manifest",
    "list_r4_scenarios",
    "load_r4_scenario",
    "r4_example_payload",
    "r4_example_run_spec",
    "validate_r4_example_run_spec",
]
