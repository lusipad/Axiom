from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..five_axis.f3_sampling import M5DiscreteCommand
from ..machine.models import MachineObservationRequest
from ..models import AxiomModel, EvaluationCase, _require_json_number

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_VERSIONED_ID_PATTERN = r"^.+@[0-9]+$"
_AXIS_CONTRACT = (
    ("X", "linear-mm", "mm"),
    ("Y", "linear-mm", "mm"),
    ("Z", "linear-mm", "mm"),
    ("B", "rotary-rad", "rad"),
    ("C", "rotary-rad", "rad"),
)


def _finite_number(value: Any) -> Any:
    value = _require_json_number(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("value must be finite")
    return value


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


def _identity_hash(model: AxiomModel, *, exclude: str) -> str:
    payload = model.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude={exclude},
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PhysicalAxisParameter(AxiomModel):
    axis_id: str = Field(alias="axisId", min_length=1)
    axis_index: int = Field(alias="axisIndex", ge=0, le=4)
    unit_family: Literal["linear-mm", "rotary-rad"] = Field(alias="unitFamily")
    unit: Literal["mm", "rad"]
    excitation_status: Literal["identified", "insufficient-excitation"] = Field(alias="excitationStatus")
    time_constant_seconds: float | None = Field(default=None, alias="timeConstantSeconds", gt=0)
    bias: float | None = None

    @field_validator("time_constant_seconds", "bias", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        if value is None:
            return None
        return _finite_number(value)

    @model_validator(mode="after")
    def require_consistent_axis_contract(self) -> "PhysicalAxisParameter":
        expected_unit = "mm" if self.unit_family == "linear-mm" else "rad"
        if self.unit != expected_unit:
            raise ValueError("axis unit must match unitFamily")
        identified = self.excitation_status == "identified"
        if identified != (self.time_constant_seconds is not None and self.bias is not None):
            raise ValueError("identified axes require tau and bias; insufficient axes must omit them")
        return self


class PhysicalApplicability(AxiomModel):
    device_ids: tuple[str, ...] = Field(alias="deviceIds", min_length=1)
    controller_families: tuple[str, ...] = Field(alias="controllerFamilies", min_length=1)
    trajectory_families: tuple[str, ...] = Field(alias="trajectoryFamilies", min_length=1)
    sample_period_min_seconds: float = Field(alias="samplePeriodMinSeconds", gt=0)
    sample_period_max_seconds: float = Field(alias="samplePeriodMaxSeconds", gt=0)
    evidence_source: Literal["synthetic-sil"] = Field(alias="evidenceSource")

    @field_validator("sample_period_min_seconds", "sample_period_max_seconds", mode="before")
    @classmethod
    def reject_invalid_periods(cls, value: Any) -> Any:
        return _finite_number(value)

    @model_validator(mode="after")
    def require_ordered_period_range(self) -> "PhysicalApplicability":
        if self.sample_period_min_seconds > self.sample_period_max_seconds:
            raise ValueError("sample period applicability bounds must be ordered")
        return self


class PhysicalModelDefinition(AxiomModel):
    schema_id: Literal["five-axis.physical-model-definition@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    model_id: str = Field(alias="modelId", pattern=_VERSIONED_ID_PATTERN)
    model_family_id: Literal["five-axis.independent-first-order-axis-model@1"] = Field(alias="modelFamilyId")
    integration_method: Literal["exact-zoh"] = Field(alias="integrationMethod")
    state_definition: tuple[str, ...] = Field(alias="stateDefinition", min_length=1)
    input_definition: tuple[str, ...] = Field(alias="inputDefinition", min_length=1)
    output_definition: tuple[str, ...] = Field(alias="outputDefinition", min_length=1)
    parameter_source: Literal["deterministic-grid-search"] = Field(alias="parameterSource")
    calibration_id: str = Field(alias="calibrationId", pattern=_VERSIONED_ID_PATTERN)
    calibration_command_content_id: str = Field(alias="calibrationCommandContentId", pattern=_HASH_PATTERN)
    calibration_trace_content_hash: str = Field(alias="calibrationTraceContentHash", pattern=_HASH_PATTERN)
    alignment_policy_id: Literal["five-axis.physical-alignment.exact-device-time@1"] = Field(
        alias="alignmentPolicyId"
    )
    axes: tuple[PhysicalAxisParameter, ...] = Field(min_length=5, max_length=5)
    applicability: PhysicalApplicability
    unmodeled_factors: tuple[str, ...] = Field(alias="unmodeledFactors", min_length=1)

    @model_validator(mode="after")
    def require_five_unique_axes(self) -> "PhysicalModelDefinition":
        indexes = [axis.axis_index for axis in self.axes]
        ids = [axis.axis_id for axis in self.axes]
        if indexes != [0, 1, 2, 3, 4]:
            raise ValueError("axes must be serialized in axisIndex order 0..4")
        if len(set(ids)) != 5:
            raise ValueError("axisId values must be unique")
        observed_contract = tuple((axis.axis_id, axis.unit_family, axis.unit) for axis in self.axes)
        if observed_contract != _AXIS_CONTRACT:
            raise ValueError("axes must use the frozen X/Y/Z/B/C unit contract")
        return self


class PhysicalResponseSample(AxiomModel):
    sample_index: int = Field(alias="sampleIndex", ge=0)
    t: float = Field(ge=0)
    command: tuple[float, float, float, float, float]
    simulated: tuple[float, float, float, float, float]

    @field_validator("t", mode="before")
    @classmethod
    def reject_invalid_time(cls, value: Any) -> Any:
        return _finite_number(value)

    @field_validator("command", "simulated", mode="before")
    @classmethod
    def reject_invalid_vectors(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            if len(value) != 5:
                raise ValueError("axis vectors must contain five values")
            for item in value:
                _finite_number(item)
        return value


class PhysicalResponseTrace(AxiomModel):
    artifact_type: Literal["five-axis.physical-response-trace"] = Field(alias="artifactType")
    schema_id: Literal["five-axis.physical-response-trace@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    response_trace_id: str = Field(alias="responseTraceId", min_length=1)
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    source_model_id: str = Field(alias="sourceModelId", pattern=_VERSIONED_ID_PATTERN)
    source_model_content_hash: str = Field(alias="sourceModelContentHash", pattern=_HASH_PATTERN)
    source_command_id: str = Field(alias="sourceCommandId", min_length=1)
    source_command_content_id: str = Field(alias="sourceCommandContentId", pattern=_HASH_PATTERN)
    sample_period: float = Field(alias="samplePeriod", gt=0)
    axis_units: tuple[Literal["mm", "rad"], ...] = Field(alias="axisUnits", min_length=5, max_length=5)
    integration_method: Literal["exact-zoh"] = Field(alias="integrationMethod")
    samples: tuple[PhysicalResponseSample, ...] = Field(min_length=1)
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @field_validator("sample_period", mode="before")
    @classmethod
    def reject_invalid_period(cls, value: Any) -> Any:
        return _finite_number(value)

    @model_validator(mode="after")
    def require_contiguous_samples(self) -> "PhysicalResponseTrace":
        if self.axis_units != ("mm", "mm", "mm", "rad", "rad"):
            raise ValueError("axisUnits must use the frozen X/Y/Z/B/C unit order")
        for index, sample in enumerate(self.samples):
            if sample.sample_index != index:
                raise ValueError("response sample indexes must be contiguous from zero")
            if index and sample.t <= self.samples[index - 1].t:
                raise ValueError("response sample times must be strictly increasing")
        if self.content_hash != _identity_hash(self, exclude="content_hash"):
            raise ValueError("contentHash must match PhysicalResponseTrace content")
        return self


class AxisChannelBinding(AxiomModel):
    axis_id: str = Field(alias="axisId", min_length=1)
    axis_index: int = Field(alias="axisIndex", ge=0, le=4)
    channel_id: str = Field(alias="channelId", min_length=1)
    unit_family: Literal["linear-mm", "rotary-rad"] = Field(alias="unitFamily")
    unit: Literal["mm", "rad"]

    @model_validator(mode="after")
    def require_unit_family(self) -> "AxisChannelBinding":
        if self.unit != ("mm" if self.unit_family == "linear-mm" else "rad"):
            raise ValueError("binding unit must match unitFamily")
        return self


class PhysicalRunAlignment(AxiomModel):
    alignment_id: str = Field(alias="alignmentId", pattern=_VERSIONED_ID_PATTERN)
    policy_id: Literal["five-axis.physical-alignment.exact-device-time@1"] = Field(alias="policyId")
    calibration_command_start_device_timestamp: str = Field(alias="calibrationCommandStartDeviceTimestamp")
    validation_command_start_device_timestamp: str = Field(alias="validationCommandStartDeviceTimestamp")
    maximum_time_error_seconds: float = Field(alias="maximumTimeErrorSeconds", ge=0)
    interpolation_allowed: Literal[False] = Field(default=False, alias="interpolationAllowed")
    bindings: tuple[AxisChannelBinding, ...] = Field(min_length=5, max_length=5)

    @field_validator(
        "calibration_command_start_device_timestamp",
        "validation_command_start_device_timestamp",
    )
    @classmethod
    def require_aware_timestamps(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @field_validator("maximum_time_error_seconds", mode="before")
    @classmethod
    def reject_invalid_tolerance(cls, value: Any) -> Any:
        return _finite_number(value)

    @model_validator(mode="after")
    def require_unique_bindings(self) -> "PhysicalRunAlignment":
        indexes = [binding.axis_index for binding in self.bindings]
        if indexes != [0, 1, 2, 3, 4]:
            raise ValueError("bindings must be serialized in axisIndex order 0..4")
        if len({binding.channel_id for binding in self.bindings}) != 5:
            raise ValueError("channelId values must be unique")
        return self


class PhysicalEvidencePair(AxiomModel):
    pair_id: str = Field(alias="pairId", min_length=1)
    role: Literal["calibration", "validation"]
    trajectory_family: str = Field(alias="trajectoryFamily", min_length=1)
    command: M5DiscreteCommand
    observation: MachineObservationRequest
    command_content_id: str = Field(alias="commandContentId", pattern=_HASH_PATTERN)
    trace_content_hash: str = Field(alias="traceContentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def bind_declared_identities(self) -> "PhysicalEvidencePair":
        if self.command_content_id != self.command.content_id:
            raise ValueError("commandContentId must identify command")
        if self.trace_content_hash != self.observation.artifact.capture_receipt.trace_content_hash:
            raise ValueError("traceContentHash must identify observation artifact")
        return self


class PhysicalModelValidationRequest(AxiomModel):
    artifact: PhysicalResponseTrace
    physical_model: PhysicalModelDefinition = Field(alias="physicalModel")
    calibration_pair: PhysicalEvidencePair = Field(alias="calibrationPair")
    validation_pair: PhysicalEvidencePair = Field(alias="validationPair")
    alignment: PhysicalRunAlignment
    fit_improvement_minimum: float = Field(alias="fitImprovementMinimum", ge=0, le=1)
    excitation_span_minimum: float = Field(alias="excitationSpanMinimum", gt=0)
    decomposition_tolerance: float = Field(alias="decompositionTolerance", ge=0)
    case: EvaluationCase

    @field_validator(
        "fit_improvement_minimum",
        "excitation_span_minimum",
        "decomposition_tolerance",
        mode="before",
    )
    @classmethod
    def reject_invalid_thresholds(cls, value: Any) -> Any:
        return _finite_number(value)

    @model_validator(mode="after")
    def require_roles_and_bindings(self) -> "PhysicalModelValidationRequest":
        if self.calibration_pair.role != "calibration" or self.validation_pair.role != "validation":
            raise ValueError("calibrationPair and validationPair must use their frozen roles")
        if self.physical_model.calibration_command_content_id != self.calibration_pair.command_content_id:
            raise ValueError("physicalModel calibrationCommandContentId must identify calibrationPair")
        if self.physical_model.calibration_trace_content_hash != self.calibration_pair.trace_content_hash:
            raise ValueError("physicalModel calibrationTraceContentHash must identify calibrationPair")
        if self.artifact.source_model_id != self.physical_model.model_id:
            raise ValueError("artifact sourceModelId must match physicalModel")
        if self.artifact.source_command_id != self.validation_pair.command.discrete_command_id:
            raise ValueError("artifact sourceCommandId must identify validation command")
        if self.artifact.source_command_content_id != self.validation_pair.command_content_id:
            raise ValueError("artifact sourceCommandContentId must identify validation command")
        return self


class CalibrationAxisResult(AxiomModel):
    axis_id: str = Field(alias="axisId")
    axis_index: int = Field(alias="axisIndex", ge=0, le=4)
    unit_family: Literal["linear-mm", "rotary-rad"] = Field(alias="unitFamily")
    unit: Literal["mm", "rad"]
    status: Literal["identified", "insufficient-excitation"]
    excitation_span: float = Field(alias="excitationSpan", ge=0)
    time_constant_seconds: float | None = Field(default=None, alias="timeConstantSeconds", gt=0)
    bias: float | None = None
    rmse: float | None = Field(default=None, ge=0)
    deterministic_work_units: int = Field(alias="deterministicWorkUnits", ge=0)

    @field_validator("excitation_span", "time_constant_seconds", "bias", "rmse", mode="before")
    @classmethod
    def reject_invalid_results(cls, value: Any) -> Any:
        if value is None:
            return None
        return _finite_number(value)


class CalibrationResult(AxiomModel):
    calibration_id: str = Field(alias="calibrationId", pattern=_VERSIONED_ID_PATTERN)
    method_id: Literal["five-axis.first-order-grid-calibration@1"] = Field(alias="methodId")
    axes: tuple[CalibrationAxisResult, ...] = Field(min_length=5, max_length=5)
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def require_content_identity(self) -> "CalibrationResult":
        if self.content_hash != _identity_hash(self, exclude="content_hash"):
            raise ValueError("contentHash must match CalibrationResult content")
        return self


class AxisValidationSeries(AxiomModel):
    axis_id: str = Field(alias="axisId")
    axis_index: int = Field(alias="axisIndex", ge=0, le=4)
    unit_family: Literal["linear-mm", "rotary-rad"] = Field(alias="unitFamily")
    unit: Literal["mm", "rad"]
    excitation_status: Literal["identified", "insufficient-excitation"] = Field(alias="excitationStatus")
    times: tuple[float, ...]
    command: tuple[float, ...]
    simulation: tuple[float, ...]
    observation: tuple[float, ...]
    math_observation_max_absolute: float | None = Field(default=None, alias="mathObservationMaxAbsolute", ge=0)
    math_observation_rmse: float | None = Field(default=None, alias="mathObservationRmse", ge=0)
    simulation_observation_max_absolute: float | None = Field(
        default=None, alias="simulationObservationMaxAbsolute", ge=0
    )
    simulation_observation_rmse: float | None = Field(default=None, alias="simulationObservationRmse", ge=0)
    improvement_ratio: float | None = Field(default=None, alias="improvementRatio")
    decomposition_closure_max: float | None = Field(default=None, alias="decompositionClosureMax", ge=0)


class PhysicalValidationAnalysis(AxiomModel):
    analysis_id: str = Field(alias="analysisId", min_length=1)
    method_id: Literal["five-axis.physical-validation-analysis@1"] = Field(alias="methodId")
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    calibration: CalibrationResult
    leakage_free: bool = Field(alias="leakageFree")
    alignment_coverage: float = Field(alias="alignmentCoverage", ge=0, le=1)
    maximum_time_error_seconds: float = Field(alias="maximumTimeErrorSeconds", ge=0)
    axes: tuple[AxisValidationSeries, ...] = Field(min_length=5, max_length=5)
    linear_math_observation_max_absolute: float | None = Field(
        default=None, alias="linearMathObservationMaxAbsolute", ge=0
    )
    linear_math_observation_rmse: float | None = Field(default=None, alias="linearMathObservationRmse", ge=0)
    linear_simulation_observation_max_absolute: float | None = Field(
        default=None, alias="linearSimulationObservationMaxAbsolute", ge=0
    )
    linear_simulation_observation_rmse: float | None = Field(
        default=None, alias="linearSimulationObservationRmse", ge=0
    )
    linear_improvement_ratio: float | None = Field(default=None, alias="linearImprovementRatio")
    rotary_math_observation_max_absolute: float | None = Field(
        default=None, alias="rotaryMathObservationMaxAbsolute", ge=0
    )
    rotary_math_observation_rmse: float | None = Field(default=None, alias="rotaryMathObservationRmse", ge=0)
    rotary_simulation_observation_max_absolute: float | None = Field(
        default=None, alias="rotarySimulationObservationMaxAbsolute", ge=0
    )
    rotary_simulation_observation_rmse: float | None = Field(
        default=None, alias="rotarySimulationObservationRmse", ge=0
    )
    decomposition_closure_max: float | None = Field(default=None, alias="decompositionClosureMax", ge=0)
    fit_within_tolerance: bool = Field(alias="fitWithinTolerance")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def require_content_identity(self) -> "PhysicalValidationAnalysis":
        if self.content_hash != _identity_hash(self, exclude="content_hash"):
            raise ValueError("contentHash must match PhysicalValidationAnalysis content")
        return self


__all__ = [
    "AxisChannelBinding",
    "AxisValidationSeries",
    "CalibrationAxisResult",
    "CalibrationResult",
    "PhysicalApplicability",
    "PhysicalAxisParameter",
    "PhysicalEvidencePair",
    "PhysicalModelDefinition",
    "PhysicalModelValidationRequest",
    "PhysicalResponseSample",
    "PhysicalResponseTrace",
    "PhysicalRunAlignment",
    "PhysicalValidationAnalysis",
]
