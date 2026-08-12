from __future__ import annotations

import math
import platform
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib.metadata import version as package_version
from typing import Any, Literal, Sequence

from ..domain import (
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    ArtifactTypeDescriptor,
    DomainPack,
    FailureMapping,
    MetricDefinition,
    NumericTolerance,
    register_domain_pack,
)
from ..evaluator import _aggregate_outcome, _apply_threshold, _content_hash, _seal_evaluation_report
from ..machine.runtime import (
    CLOCK_ALIGNED_METRIC_ID,
    COORDINATE_CONTEXT_METRIC_ID,
    LINEAGE_COMPLETE_METRIC_ID,
    RAW_INTEGRITY_METRIC_ID,
    READ_ONLY_CAPTURE_METRIC_ID,
    evaluate_machine_observation,
    machine_trace_content_hash,
)
from ..models import (
    CapabilityResolution,
    CaseOutcome,
    CoreEvaluationRequest,
    Evidence,
    EvaluationReport,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Provenance,
)
from ..runtime import DomainRuntimeBinding, register_domain_runtime_binding
from .models import (
    AxisValidationSeries,
    PhysicalEvidencePair,
    PhysicalModelValidationRequest,
    PhysicalRunAlignment,
    PhysicalValidationAnalysis,
)
from .simulation import (
    fit_first_order_model,
    physical_model_content_hash,
    physical_response_content_hash,
    simulate_physical_response,
)

FIVE_AXIS_PHYSICAL_DOMAIN_PACK_ID = "five-axis.domain-pack@6"
PHYSICAL_EVALUATOR_ID = "five-axis-physical-model-evaluator@1"
PHYSICAL_RUNNER_ID = "five-axis-physical-simulation@1"

CONTRACT_VALID_METRIC_ID = "five-axis.physical.simulation-contract-valid@1"
CALIBRATION_TRACEABLE_METRIC_ID = "five-axis.physical.calibration-traceable@1"
ALIGNMENT_VALID_METRIC_ID = "five-axis.physical.alignment-valid@1"
LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID = "five-axis.physical.linear.math-observation-max-absolute@1"
LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID = "five-axis.physical.linear.math-observation-rmse@1"
LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID = (
    "five-axis.physical.linear.simulation-observation-max-absolute@1"
)
LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID = "five-axis.physical.linear.simulation-observation-rmse@1"
LINEAR_IMPROVEMENT_RATIO_METRIC_ID = "five-axis.physical.linear.improvement-ratio@1"
ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID = "five-axis.physical.rotary.math-observation-max-absolute@1"
ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID = "five-axis.physical.rotary.math-observation-rmse@1"
ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID = (
    "five-axis.physical.rotary.simulation-observation-max-absolute@1"
)
ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID = "five-axis.physical.rotary.simulation-observation-rmse@1"
DECOMPOSITION_CLOSED_METRIC_ID = "five-axis.physical.residual-decomposition-closed@1"
FIT_WITHIN_TOLERANCE_METRIC_ID = "five-axis.physical.model-fit-within-tolerance@1"
REALITY_VALIDATED_METRIC_ID = "five-axis.physical.reality-validated@1"

CONTRACT_VALID_CLAIM_ID = "five-axis.physical-model-contract-valid-claim@1"
CALIBRATION_TRACEABLE_CLAIM_ID = "five-axis.physical-calibration-traceable-claim@1"
ALIGNMENT_VALID_CLAIM_ID = "five-axis.physical-alignment-valid-claim@1"
DECOMPOSITION_CLOSED_CLAIM_ID = "five-axis.physical-residual-decomposition-closed-claim@1"
FIT_WITHIN_TOLERANCE_CLAIM_ID = "five-axis.physical-model-fit-within-tolerance-claim@1"
REALITY_VALIDATED_CLAIM_ID = "five-axis.physical-model-reality-validated-claim@1"

CAP_RESPONSE_ARTIFACT = "five-axis.physical.response-trace@1"
CAP_MODEL_PROFILE = "five-axis.physical.model-profile@1"
CAP_CALIBRATION_PROFILE = "five-axis.physical.calibration-profile@1"
CAP_ALIGNMENT_ADAPTER = "five-axis.physical.signal-alignment@1"
CAP_VALIDATION_EVALUATOR = "five-axis.physical.validation-evaluator@1"

_R3_REQUIRED_METRICS = (
    RAW_INTEGRITY_METRIC_ID,
    READ_ONLY_CAPTURE_METRIC_ID,
    LINEAGE_COMPLETE_METRIC_ID,
    CLOCK_ALIGNED_METRIC_ID,
    COORDINATE_CONTEXT_METRIC_ID,
)


def _definition(
    metric_id: str,
    *,
    requires: tuple[str, ...],
    claim_id: str | None = None,
    predicate: str | None = None,
    direction: Literal["lower-is-better", "higher-is-better"] | None = None,
    unit: str | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=requires,
        claimDefinitionId=claim_id,
        claimPredicate=predicate,
        direction=direction,
        numericTolerance=(
            NumericTolerance(absolute=1e-12, relative=1e-12, unit=unit) if direction else None
        ),
    )


_METRIC_DEFINITIONS = (
    _definition(
        CONTRACT_VALID_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_MODEL_PROFILE, CAP_VALIDATION_EVALUATOR),
        claim_id=CONTRACT_VALID_CLAIM_ID,
        predicate="five-axis physical simulation contract is valid",
    ),
    _definition(
        CALIBRATION_TRACEABLE_METRIC_ID,
        requires=(CAP_MODEL_PROFILE, CAP_CALIBRATION_PROFILE, CAP_VALIDATION_EVALUATOR),
        claim_id=CALIBRATION_TRACEABLE_CLAIM_ID,
        predicate="five-axis physical calibration is independently traceable",
    ),
    _definition(
        ALIGNMENT_VALID_METRIC_ID,
        requires=(CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        claim_id=ALIGNMENT_VALID_CLAIM_ID,
        predicate="five-axis command and observation signals are fully aligned",
    ),
    _definition(
        LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        requires=(CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        direction="lower-is-better",
        unit="mm",
    ),
    _definition(
        LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID,
        requires=(CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        direction="lower-is-better",
        unit="mm",
    ),
    _definition(
        LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        direction="lower-is-better",
        unit="mm",
    ),
    _definition(
        LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        direction="lower-is-better",
        unit="mm",
    ),
    _definition(
        LINEAR_IMPROVEMENT_RATIO_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_VALIDATION_EVALUATOR),
        direction="higher-is-better",
        unit="ratio",
    ),
    _definition(
        ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        requires=(CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        direction="lower-is-better",
        unit="rad",
    ),
    _definition(
        ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID,
        requires=(CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        direction="lower-is-better",
        unit="rad",
    ),
    _definition(
        ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        direction="lower-is-better",
        unit="rad",
    ),
    _definition(
        ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        direction="lower-is-better",
        unit="rad",
    ),
    _definition(
        DECOMPOSITION_CLOSED_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        claim_id=DECOMPOSITION_CLOSED_CLAIM_ID,
        predicate="five-axis physical residual decomposition closes within tolerance",
    ),
    _definition(
        FIT_WITHIN_TOLERANCE_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_CALIBRATION_PROFILE, CAP_VALIDATION_EVALUATOR),
        claim_id=FIT_WITHIN_TOLERANCE_CLAIM_ID,
        predicate="five-axis physical holdout fit improves within the declared tolerance",
    ),
    _definition(
        REALITY_VALIDATED_METRIC_ID,
        requires=(CAP_RESPONSE_ARTIFACT, CAP_ALIGNMENT_ADAPTER, CAP_VALIDATION_EVALUATOR),
        claim_id=REALITY_VALIDATED_CLAIM_ID,
        predicate="five-axis physical model is validated against real device holdout evidence",
    ),
)

_FAILURE_MAPPINGS = (
    FailureMapping(
        code="MalformedEvaluationRequest",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="ArtifactTypeMismatch",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="ArtifactSchemaVersionMismatch",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="DomainEvaluatorFailed",
        executionStatus=ExecutionStatus.EXECUTION_FAILED,
        metricStatus=MetricStatus.NUMERICAL_FAILURE,
        caseOutcome=CaseOutcome.INCONCLUSIVE,
    ),
)

FIVE_AXIS_PHYSICAL_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=FIVE_AXIS_PHYSICAL_DOMAIN_PACK_ID,
        artifactType="five-axis.physical-response-trace",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="five-axis.physical-response-trace",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m5-discrete-command",
                schemaVersion=1,
                role="reference",
            ),
            ArtifactTypeDescriptor(
                artifactType="machine.telemetry-trace",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=PHYSICAL_EVALUATOR_ID,
        runnerId=PHYSICAL_RUNNER_ID,
        runnerIds=(PHYSICAL_RUNNER_ID,),
        capabilityIds=(
            CAP_RESPONSE_ARTIFACT,
            CAP_MODEL_PROFILE,
            CAP_CALIBRATION_PROFILE,
            CAP_ALIGNMENT_ADAPTER,
            CAP_VALIDATION_EVALUATOR,
        ),
        metricDefinitions=_METRIC_DEFINITIONS,
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            CONTRACT_VALID_CLAIM_ID,
            CALIBRATION_TRACEABLE_CLAIM_ID,
            ALIGNMENT_VALID_CLAIM_ID,
            DECOMPOSITION_CLOSED_CLAIM_ID,
            FIT_WITHIN_TOLERANCE_CLAIM_ID,
            REALITY_VALIDATED_CLAIM_ID,
        ),
        comparisonPolicyIds=(),
        failureMappings=_FAILURE_MAPPINGS,
    )
)


@dataclass(frozen=True, slots=True)
class _AlignedSignals:
    coverage: float
    maximum_time_error_seconds: float
    times: tuple[float, ...]
    command_by_axis: tuple[tuple[float, ...], ...]
    observation_by_axis: tuple[tuple[float, ...], ...]


def _parse_request(request: CoreEvaluationRequest) -> PhysicalModelValidationRequest:
    return PhysicalModelValidationRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _r3_context_valid(pair: PhysicalEvidencePair) -> bool:
    report = evaluate_machine_observation(pair.observation)
    results = {result.metric_id: result for result in report.metric_results}
    return all(
        metric_id in results
        and results[metric_id].status is MetricStatus.COMPUTED
        and results[metric_id].value is True
        for metric_id in _R3_REQUIRED_METRICS
    )


def _align_pair(
    pair: PhysicalEvidencePair,
    alignment: PhysicalRunAlignment,
    *,
    anchor_value: str,
) -> _AlignedSignals:
    anchor = datetime.fromisoformat(anchor_value)
    frames = pair.observation.artifact.frames
    parsed_frames = tuple((datetime.fromisoformat(frame.device_timestamp), frame) for frame in frames)
    matched_frames: list[Any] = []
    matched_times: list[float] = []
    maximum_error = 0.0
    used_sequences: set[int] = set()
    for sample in pair.command.samples:
        target = anchor + timedelta(seconds=float(sample.t))
        closest_timestamp, closest_frame = min(
            parsed_frames,
            key=lambda item: abs((item[0] - target).total_seconds()),
        )
        error = abs((closest_timestamp - target).total_seconds())
        if error > alignment.maximum_time_error_seconds or closest_frame.sequence_id in used_sequences:
            continue
        used_sequences.add(closest_frame.sequence_id)
        maximum_error = max(maximum_error, error)
        matched_times.append(float(sample.t))
        matched_frames.append(closest_frame)

    coverage = len(matched_frames) / len(pair.command.samples)
    if coverage != 1.0:
        return _AlignedSignals(
            coverage=coverage,
            maximum_time_error_seconds=maximum_error,
            times=tuple(matched_times),
            command_by_axis=((), (), (), (), ()),
            observation_by_axis=((), (), (), (), ()),
        )

    command_by_axis = tuple(
        tuple(float(sample.q[axis_index]) for sample in pair.command.samples) for axis_index in range(5)
    )
    observations: list[tuple[float, ...]] = []
    for binding in alignment.bindings:
        values: list[float] = []
        for frame in matched_frames:
            samples = {sample.channel_id: sample for sample in frame.samples}
            observed = samples.get(binding.channel_id)
            if observed is None or not isinstance(observed.value, (int, float)):
                return _AlignedSignals(
                    coverage=0.0,
                    maximum_time_error_seconds=maximum_error,
                    times=(),
                    command_by_axis=((), (), (), (), ()),
                    observation_by_axis=((), (), (), (), ()),
                )
            values.append(float(observed.value))
        observations.append(tuple(values))
    return _AlignedSignals(
        coverage=coverage,
        maximum_time_error_seconds=maximum_error,
        times=tuple(matched_times),
        command_by_axis=command_by_axis,
        observation_by_axis=tuple(observations),
    )


def _rmse(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) / len(left))


def _max_absolute_error(left: Sequence[float], right: Sequence[float]) -> float:
    return max(abs(a - b) for a, b in zip(left, right, strict=True))


def _group_max_absolute(
    axes: Sequence[AxisValidationSeries],
    *,
    unit_family: str,
    field: Literal["math", "simulation"],
) -> float | None:
    maxima: list[float] = []
    for axis in axes:
        if axis.unit_family != unit_family or axis.excitation_status != "identified":
            continue
        source = axis.command if field == "math" else axis.simulation
        maxima.extend(abs(left - right) for left, right in zip(source, axis.observation, strict=True))
    return max(maxima) if maxima else None


def _group_rmse(
    axes: Sequence[AxisValidationSeries],
    *,
    unit_family: str,
    field: Literal["math", "simulation"],
) -> float | None:
    squared: list[float] = []
    for axis in axes:
        if axis.unit_family != unit_family or axis.excitation_status != "identified":
            continue
        source = axis.command if field == "math" else axis.simulation
        squared.extend((left - right) ** 2 for left, right in zip(source, axis.observation, strict=True))
    return math.sqrt(sum(squared) / len(squared)) if squared else None


def _leakage_free(request: PhysicalModelValidationRequest) -> bool:
    calibration = request.calibration_pair
    validation = request.validation_pair
    return (
        calibration.pair_id != validation.pair_id
        and calibration.command_content_id != validation.command_content_id
        and calibration.trace_content_hash != validation.trace_content_hash
    )


def _calibration_replay_matches(
    request: PhysicalModelValidationRequest,
    calibration_signals: _AlignedSignals,
) -> tuple[bool, str | None]:
    if calibration_signals.coverage != 1.0:
        return False, "CalibrationAlignmentIncomplete"
    calibration_observation = request.calibration_pair.observation
    try:
        recomputed_model, _ = fit_first_order_model(
            calibration_id=request.physical_model.calibration_id,
            model_id=request.physical_model.model_id,
            calibration_command_content_id=request.calibration_pair.command_content_id,
            calibration_trace_content_hash=request.calibration_pair.trace_content_hash,
            device_id=calibration_observation.artifact.device_identity.device_id,
            controller_family=calibration_observation.artifact.device_identity.controller_family,
            trajectory_families=request.physical_model.applicability.trajectory_families,
            sample_period=request.calibration_pair.command.sample_period,
            commands_by_axis=calibration_signals.command_by_axis,
            observations_by_axis=calibration_signals.observation_by_axis,
            times=calibration_signals.times,
            excitation_span_minimum=request.excitation_span_minimum,
        )
    except ValueError as exc:
        return False, str(exc)
    if recomputed_model != request.physical_model:
        return False, "physicalModel parameters do not match independent calibration replay"
    return True, None


def _analysis_payload(analysis: PhysicalValidationAnalysis) -> dict[str, Any]:
    return analysis.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude={"content_hash"},
    )


def analyze_physical_validation(request: PhysicalModelValidationRequest) -> PhysicalValidationAnalysis:
    calibration_signals = _align_pair(
        request.calibration_pair,
        request.alignment,
        anchor_value=request.alignment.calibration_command_start_device_timestamp,
    )
    validation_signals = _align_pair(
        request.validation_pair,
        request.alignment,
        anchor_value=request.alignment.validation_command_start_device_timestamp,
    )
    if calibration_signals.coverage != 1.0 or validation_signals.coverage != 1.0:
        raise ValueError("PhysicalRunAlignment does not cover every command sample")
    if not _r3_context_valid(request.calibration_pair) or not _r3_context_valid(request.validation_pair):
        raise ValueError("R3 observation context is not complete")
    if not _leakage_free(request):
        raise ValueError("calibration and validation evidence identities must be disjoint")

    calibration_observation = request.calibration_pair.observation
    recomputed_model, calibration = fit_first_order_model(
        calibration_id=request.physical_model.calibration_id,
        model_id=request.physical_model.model_id,
        calibration_command_content_id=request.calibration_pair.command_content_id,
        calibration_trace_content_hash=request.calibration_pair.trace_content_hash,
        device_id=calibration_observation.artifact.device_identity.device_id,
        controller_family=calibration_observation.artifact.device_identity.controller_family,
        trajectory_families=request.physical_model.applicability.trajectory_families,
        sample_period=request.calibration_pair.command.sample_period,
        commands_by_axis=calibration_signals.command_by_axis,
        observations_by_axis=calibration_signals.observation_by_axis,
        times=calibration_signals.times,
        excitation_span_minimum=request.excitation_span_minimum,
    )
    if recomputed_model != request.physical_model:
        raise ValueError("physicalModel parameters do not match independent calibration replay")

    replay = simulate_physical_response(
        request.physical_model,
        request.validation_pair.command,
        response_trace_id=request.artifact.response_trace_id,
    )
    if replay != request.artifact:
        raise ValueError("PhysicalResponseTrace does not match independent exact-ZOH replay")

    times = validation_signals.times
    command_by_axis = validation_signals.command_by_axis
    observation_by_axis = validation_signals.observation_by_axis
    simulation_by_axis = tuple(
        tuple(sample.simulated[axis_index] for sample in replay.samples) for axis_index in range(5)
    )
    axes: list[AxisValidationSeries] = []
    closure_max = 0.0
    for parameter in request.physical_model.axes:
        axis_index = parameter.axis_index
        command = command_by_axis[axis_index]
        simulation = simulation_by_axis[axis_index]
        observation = observation_by_axis[axis_index]
        if parameter.excitation_status == "identified":
            math_max = _max_absolute_error(command, observation)
            math_rmse = _rmse(command, observation)
            simulation_max = _max_absolute_error(simulation, observation)
            simulation_rmse = _rmse(simulation, observation)
            improvement = 1.0 - simulation_rmse / math_rmse if math_rmse > 0 else 0.0
            axis_closure = max(
                abs((math_value - observed) - ((math_value - simulated) + (simulated - observed)))
                for math_value, simulated, observed in zip(command, simulation, observation, strict=True)
            )
            closure_max = max(closure_max, axis_closure)
        else:
            math_max = math_rmse = simulation_max = simulation_rmse = improvement = axis_closure = None
        axes.append(
            AxisValidationSeries(
                axisId=parameter.axis_id,
                axisIndex=axis_index,
                unitFamily=parameter.unit_family,
                unit=parameter.unit,
                excitationStatus=parameter.excitation_status,
                times=times,
                command=command,
                simulation=simulation,
                observation=observation,
                mathObservationMaxAbsolute=math_max,
                mathObservationRmse=math_rmse,
                simulationObservationMaxAbsolute=simulation_max,
                simulationObservationRmse=simulation_rmse,
                improvementRatio=improvement,
                decompositionClosureMax=axis_closure,
            )
        )
    axis_tuple = tuple(axes)
    linear_math_max = _group_max_absolute(axis_tuple, unit_family="linear-mm", field="math")
    linear_math = _group_rmse(axis_tuple, unit_family="linear-mm", field="math")
    linear_simulation_max = _group_max_absolute(axis_tuple, unit_family="linear-mm", field="simulation")
    linear_simulation = _group_rmse(axis_tuple, unit_family="linear-mm", field="simulation")
    linear_improvement = (
        1.0 - linear_simulation / linear_math
        if linear_math is not None and linear_math > 0 and linear_simulation is not None
        else None
    )
    rotary_math_max = _group_max_absolute(axis_tuple, unit_family="rotary-rad", field="math")
    rotary_math = _group_rmse(axis_tuple, unit_family="rotary-rad", field="math")
    rotary_simulation_max = _group_max_absolute(axis_tuple, unit_family="rotary-rad", field="simulation")
    rotary_simulation = _group_rmse(axis_tuple, unit_family="rotary-rad", field="simulation")
    fit = linear_improvement is not None and linear_improvement >= request.fit_improvement_minimum
    provisional = PhysicalValidationAnalysis.model_construct(
        analysis_id=f"analysis:{request.artifact.content_hash}",
        method_id="five-axis.physical-validation-analysis@1",
        source_kind="synthetic-sil",
        calibration=calibration,
        leakage_free=True,
        alignment_coverage=1.0,
        maximum_time_error_seconds=max(
            calibration_signals.maximum_time_error_seconds,
            validation_signals.maximum_time_error_seconds,
        ),
        axes=axis_tuple,
        linear_math_observation_max_absolute=linear_math_max,
        linear_math_observation_rmse=linear_math,
        linear_simulation_observation_max_absolute=linear_simulation_max,
        linear_simulation_observation_rmse=linear_simulation,
        linear_improvement_ratio=linear_improvement,
        rotary_math_observation_max_absolute=rotary_math_max,
        rotary_math_observation_rmse=rotary_math,
        rotary_simulation_observation_max_absolute=rotary_simulation_max,
        rotary_simulation_observation_rmse=rotary_simulation,
        decomposition_closure_max=closure_max,
        fit_within_tolerance=fit,
        content_hash="0" * 64,
    )
    payload = _analysis_payload(provisional)
    payload["contentHash"] = _content_hash(payload)
    return PhysicalValidationAnalysis.model_validate(payload)


def _metric_definition(metric_id: str) -> MetricDefinition:
    return FIVE_AXIS_PHYSICAL_DOMAIN_PACK.metric_definition(metric_id)


def _computed(
    metric_id: str,
    value: Any,
    *,
    unit: str | None = None,
    reason_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    definition = _metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=MetricStatus.COMPUTED,
        value=value,
        unit=unit,
        reasonCode=reason_code,
        details=details or {},
        evidence=Evidence(level="Observed", method=f"{metric_id}.synthetic-sil-replay@1"),
    )


def _unavailable(metric_id: str, status: MetricStatus, reason_code: str, **details: Any) -> MetricResult:
    definition = _metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=status,
        reasonCode=reason_code,
        details=details,
        evidence=Evidence(level="Observed", method=f"{metric_id}.synthetic-sil-boundary@1"),
    )


def _bind_boolean_gate(result: MetricResult) -> MetricResult:
    if result.status is MetricStatus.COMPUTED and isinstance(result.value, bool):
        return result.model_copy(update={"threshold_passed": result.value})
    return result


def evaluate_physical_model(request: PhysicalModelValidationRequest) -> EvaluationReport:
    leakage_free = _leakage_free(request)
    model_identity_valid = request.artifact.source_model_content_hash == physical_model_content_hash(
        request.physical_model
    )
    response_identity_valid = request.artifact.content_hash == physical_response_content_hash(request.artifact)
    lineage_valid = all(
        pair.observation.lineage.source_command_content_hash == pair.command_content_id
        and machine_trace_content_hash(pair.observation.artifact) == pair.trace_content_hash
        for pair in (request.calibration_pair, request.validation_pair)
    )
    contract_valid = model_identity_valid and response_identity_valid and lineage_valid

    calibration_alignment = _align_pair(
        request.calibration_pair,
        request.alignment,
        anchor_value=request.alignment.calibration_command_start_device_timestamp,
    )
    validation_alignment = _align_pair(
        request.validation_pair,
        request.alignment,
        anchor_value=request.alignment.validation_command_start_device_timestamp,
    )
    calibration_context_valid = _r3_context_valid(request.calibration_pair)
    validation_context_valid = _r3_context_valid(request.validation_pair)
    context_valid = calibration_context_valid and validation_context_valid
    alignment_valid = (
        context_valid and calibration_alignment.coverage == 1.0 and validation_alignment.coverage == 1.0
    )

    calibration_traceable = False
    calibration_error: str | None = None
    if calibration_context_valid and calibration_alignment.coverage == 1.0:
        calibration_traceable, calibration_error = _calibration_replay_matches(request, calibration_alignment)

    analysis: PhysicalValidationAnalysis | None = None
    analysis_error: str | None = None
    if contract_valid and leakage_free and alignment_valid:
        try:
            analysis = analyze_physical_validation(request)
        except ValueError as exc:
            analysis_error = str(exc)

    if not leakage_free:
        calibration_result = _computed(
            CALIBRATION_TRACEABLE_METRIC_ID,
            False,
            reason_code="CalibrationValidationLeakage",
            details={"leakageFree": False},
        )
    elif not calibration_context_valid or calibration_alignment.coverage != 1.0:
        calibration_result = _unavailable(
            CALIBRATION_TRACEABLE_METRIC_ID,
            MetricStatus.INSUFFICIENT_CONTEXT,
            "CalibrationContextIncomplete",
            calibrationCoverage=calibration_alignment.coverage,
        )
    else:
        calibration_result = _computed(
            CALIBRATION_TRACEABLE_METRIC_ID,
            calibration_traceable,
            reason_code=None if calibration_traceable else "CalibrationReplayMismatch",
            details={"calibrationError": calibration_error, "leakageFree": True},
        )

    evaluated: dict[str, MetricResult] = {
        CONTRACT_VALID_METRIC_ID: _computed(
            CONTRACT_VALID_METRIC_ID,
            contract_valid,
            reason_code=None if contract_valid else "PhysicalContractIdentityMismatch",
            details={
                "responseContentHash": request.artifact.content_hash,
                "modelContentHash": request.artifact.source_model_content_hash,
                "syntheticSil": True,
            },
        ),
        CALIBRATION_TRACEABLE_METRIC_ID: calibration_result,
        ALIGNMENT_VALID_METRIC_ID: (
            _computed(
                ALIGNMENT_VALID_METRIC_ID,
                alignment_valid,
                reason_code=None if alignment_valid else "SignalAlignmentIncomplete",
                details={
                    "calibrationCoverage": calibration_alignment.coverage,
                    "validationCoverage": validation_alignment.coverage,
                    "interpolationApplied": False,
                },
            )
            if context_valid
            else _unavailable(
                ALIGNMENT_VALID_METRIC_ID,
                MetricStatus.INSUFFICIENT_CONTEXT,
                "R3AlignmentContextIncomplete",
                interpolationApplied=False,
            )
        ),
        REALITY_VALIDATED_METRIC_ID: _unavailable(
            REALITY_VALIDATED_METRIC_ID,
            MetricStatus.INSUFFICIENT_CONTEXT,
            "SyntheticSILIsNotRealityValidation",
            sourceKind="synthetic-replay",
            realityValidationStatus="Open",
        ),
    }
    if analysis is None:
        unavailable_status = (
            MetricStatus.INVALID_OBSERVATION
            if not leakage_free or analysis_error is not None
            else MetricStatus.INSUFFICIENT_CONTEXT
        )
        unavailable_reason = (
            "CalibrationValidationLeakage" if not leakage_free else "PhysicalValidationAnalysisUnavailable"
        )
        for metric_id in (
            LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
            LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID,
            LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
            LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
            LINEAR_IMPROVEMENT_RATIO_METRIC_ID,
            ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
            ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID,
            ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
            ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
            DECOMPOSITION_CLOSED_METRIC_ID,
            FIT_WITHIN_TOLERANCE_METRIC_ID,
        ):
            evaluated[metric_id] = _unavailable(metric_id, unavailable_status, unavailable_reason)
    else:
        evaluated.update(
            {
                LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID: _computed(
                    LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
                    analysis.linear_math_observation_max_absolute,
                    unit="mm",
                    details={"analysisContentHash": analysis.content_hash},
                ),
                LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID: _computed(
                    LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID,
                    analysis.linear_math_observation_rmse,
                    unit="mm",
                    details={"analysisContentHash": analysis.content_hash},
                ),
                LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID: _computed(
                    LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
                    analysis.linear_simulation_observation_max_absolute,
                    unit="mm",
                    details={"analysisContentHash": analysis.content_hash},
                ),
                LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID: _computed(
                    LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
                    analysis.linear_simulation_observation_rmse,
                    unit="mm",
                    details={"analysisContentHash": analysis.content_hash},
                ),
                LINEAR_IMPROVEMENT_RATIO_METRIC_ID: _computed(
                    LINEAR_IMPROVEMENT_RATIO_METRIC_ID,
                    analysis.linear_improvement_ratio,
                    unit="ratio",
                    details={"minimum": request.fit_improvement_minimum},
                ),
                ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID: (
                    _computed(
                        ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
                        analysis.rotary_math_observation_max_absolute,
                        unit="rad",
                    )
                    if analysis.rotary_math_observation_max_absolute is not None
                    else _unavailable(
                        ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
                        MetricStatus.NOT_APPLICABLE,
                        "InsufficientRotaryAxisExcitation",
                    )
                ),
                ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID: (
                    _computed(
                        ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID,
                        analysis.rotary_math_observation_rmse,
                        unit="rad",
                    )
                    if analysis.rotary_math_observation_rmse is not None
                    else _unavailable(
                        ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID,
                        MetricStatus.NOT_APPLICABLE,
                        "InsufficientRotaryAxisExcitation",
                    )
                ),
                ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID: (
                    _computed(
                        ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
                        analysis.rotary_simulation_observation_max_absolute,
                        unit="rad",
                    )
                    if analysis.rotary_simulation_observation_max_absolute is not None
                    else _unavailable(
                        ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID,
                        MetricStatus.NOT_APPLICABLE,
                        "InsufficientRotaryAxisExcitation",
                    )
                ),
                ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID: (
                    _computed(
                        ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
                        analysis.rotary_simulation_observation_rmse,
                        unit="rad",
                    )
                    if analysis.rotary_simulation_observation_rmse is not None
                    else _unavailable(
                        ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID,
                        MetricStatus.NOT_APPLICABLE,
                        "InsufficientRotaryAxisExcitation",
                    )
                ),
                DECOMPOSITION_CLOSED_METRIC_ID: _computed(
                    DECOMPOSITION_CLOSED_METRIC_ID,
                    (analysis.decomposition_closure_max or 0.0) <= request.decomposition_tolerance,
                    details={
                        "closureMax": analysis.decomposition_closure_max,
                        "tolerance": request.decomposition_tolerance,
                    },
                ),
                FIT_WITHIN_TOLERANCE_METRIC_ID: _computed(
                    FIT_WITHIN_TOLERANCE_METRIC_ID,
                    analysis.fit_within_tolerance,
                    details={
                        "linearImprovementRatio": analysis.linear_improvement_ratio,
                        "minimum": request.fit_improvement_minimum,
                    },
                ),
            }
        )

    requested = request.case.required_metrics + request.case.optional_metrics
    results = [
        _bind_boolean_gate(_apply_threshold(evaluated[item.metric_id], item.threshold)) for item in requested
    ]
    required_results = results[: len(request.case.required_metrics)]
    provenance = Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=PHYSICAL_RUNNER_ID,
        evaluatorVersion=PHYSICAL_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment={
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "pydantic": package_version("pydantic"),
        },
        contextHashes={
            "physicalModel": physical_model_content_hash(request.physical_model),
            "calibrationCommand": request.calibration_pair.command_content_id,
            "calibrationObservation": request.calibration_pair.trace_content_hash,
            "validationCommand": request.validation_pair.command_content_id,
            "validationObservation": request.validation_pair.trace_content_hash,
            "alignment": _content_hash(request.alignment),
        },
    )
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(required_results),
            metricResults=results,
            capabilities=(
                CapabilityResolution(capabilityId=CAP_RESPONSE_ARTIFACT, source="Artifact"),
                CapabilityResolution(capabilityId=CAP_MODEL_PROFILE, source="Profile"),
                CapabilityResolution(capabilityId=CAP_CALIBRATION_PROFILE, source="Profile"),
                CapabilityResolution(capabilityId=CAP_ALIGNMENT_ADAPTER, source="Adapter"),
                CapabilityResolution(capabilityId=CAP_VALIDATION_EVALUATOR, source="Evaluator"),
            ),
            contentHash="",
            evaluatorVersion=PHYSICAL_EVALUATOR_ID,
            provenance=provenance,
        )
    )


FIVE_AXIS_PHYSICAL_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=FIVE_AXIS_PHYSICAL_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_physical_model,
    )
)


__all__ = [
    "ALIGNMENT_VALID_CLAIM_ID",
    "ALIGNMENT_VALID_METRIC_ID",
    "CALIBRATION_TRACEABLE_CLAIM_ID",
    "CALIBRATION_TRACEABLE_METRIC_ID",
    "CONTRACT_VALID_CLAIM_ID",
    "CONTRACT_VALID_METRIC_ID",
    "DECOMPOSITION_CLOSED_CLAIM_ID",
    "DECOMPOSITION_CLOSED_METRIC_ID",
    "FIT_WITHIN_TOLERANCE_CLAIM_ID",
    "FIT_WITHIN_TOLERANCE_METRIC_ID",
    "FIVE_AXIS_PHYSICAL_DOMAIN_PACK",
    "FIVE_AXIS_PHYSICAL_DOMAIN_PACK_ID",
    "FIVE_AXIS_PHYSICAL_RUNTIME_BINDING",
    "LINEAR_IMPROVEMENT_RATIO_METRIC_ID",
    "LINEAR_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID",
    "LINEAR_MATH_OBSERVATION_RMSE_METRIC_ID",
    "LINEAR_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID",
    "LINEAR_SIMULATION_OBSERVATION_RMSE_METRIC_ID",
    "PHYSICAL_EVALUATOR_ID",
    "PHYSICAL_RUNNER_ID",
    "REALITY_VALIDATED_CLAIM_ID",
    "REALITY_VALIDATED_METRIC_ID",
    "ROTARY_MATH_OBSERVATION_MAX_ABSOLUTE_METRIC_ID",
    "ROTARY_MATH_OBSERVATION_RMSE_METRIC_ID",
    "ROTARY_SIMULATION_OBSERVATION_MAX_ABSOLUTE_METRIC_ID",
    "ROTARY_SIMULATION_OBSERVATION_RMSE_METRIC_ID",
    "analyze_physical_validation",
    "evaluate_physical_model",
]
