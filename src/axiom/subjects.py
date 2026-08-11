from __future__ import annotations

import math
from collections.abc import Callable

from .domain import PYTHON_CALL_RUNNER_ID
from .models import OrderedPointSequence, ParameterSet, SubjectDefinition


SubjectFunction = Callable[[OrderedPointSequence, ParameterSet], OrderedPointSequence]


class SubjectExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_SUBJECTS: dict[tuple[str, str], tuple[SubjectDefinition, SubjectFunction]] = {}


def register_subject(definition: SubjectDefinition, function: SubjectFunction) -> SubjectDefinition:
    key = (definition.subject_id, definition.subject_version)
    existing = _SUBJECTS.get(key)
    if existing is not None:
        if existing != (definition, function):
            raise ValueError(f"subject identity is already registered: {definition.subject_id}@{definition.subject_version}")
        return existing[0]
    _SUBJECTS[key] = (definition, function)
    return definition


def get_subject(subject_id: str, subject_version: str) -> tuple[SubjectDefinition, SubjectFunction]:
    try:
        return _SUBJECTS[(subject_id, subject_version)]
    except KeyError as exc:
        raise SubjectExecutionError(
            "UnknownSubject",
            f"No local Subject is registered for {subject_id}@{subject_version}.",
        ) from exc


def list_subjects() -> tuple[SubjectDefinition, ...]:
    return tuple(_SUBJECTS[key][0] for key in sorted(_SUBJECTS))


def execute_subject(
    subject_id: str,
    subject_version: str,
    artifact: OrderedPointSequence,
    parameter_set: ParameterSet,
) -> OrderedPointSequence:
    definition, function = get_subject(subject_id, subject_version)
    if definition.runner_id != PYTHON_CALL_RUNNER_ID:
        raise SubjectExecutionError("RunnerMismatch", "The Subject is not bound to python-call@1.")
    if parameter_set.parameter_schema_id != definition.parameter_schema_id:
        raise SubjectExecutionError(
            "ParameterSchemaMismatch",
            "ParameterSet parameterSchemaId does not match the Subject contract.",
        )
    if artifact.artifact_type != definition.input_artifact_type:
        raise SubjectExecutionError(
            "InputContractViolation",
            "Subject input artifactType is not declared.",
        )
    try:
        output = function(artifact, parameter_set)
    except SubjectExecutionError:
        raise
    except Exception as exc:  # The runner converts Subject exceptions into a public failure boundary.
        raise SubjectExecutionError("SubjectExecutionFailed", "The Subject raised an execution error.") from exc
    if not isinstance(output, OrderedPointSequence) or output.artifact_type != definition.output_artifact_type:
        raise SubjectExecutionError("OutputContractViolation", "Subject output artifactType is not declared.")
    return output


def _offset_parameters(
    artifact: OrderedPointSequence, parameter_set: ParameterSet
) -> tuple[list[float], float]:
    vector = parameter_set.values.get("errorVector")
    gain = parameter_set.values.get("compensationGain")
    if not isinstance(vector, list) or not vector:
        raise SubjectExecutionError(
            "ParameterContractViolation",
            "errorVector must be a non-empty array of finite numbers.",
        )
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector):
        raise SubjectExecutionError(
            "ParameterContractViolation",
            "errorVector must be a non-empty array of finite numbers.",
        )
    if isinstance(gain, bool) or not isinstance(gain, (int, float)) or not math.isfinite(gain) or not 0 <= gain <= 1:
        raise SubjectExecutionError(
            "ParameterContractViolation",
            "compensationGain must be a finite ratio in [0, 1].",
        )
    if not artifact.points or any(len(point) != len(vector) for point in artifact.points):
        raise SubjectExecutionError(
            "ParameterContractViolation",
            "errorVector dimension must match every shared input point.",
        )
    expected_unit = artifact.semantics.unit if artifact.semantics and artifact.semantics.unit else "coordinate-unit"
    declared_unit = parameter_set.units.get("errorVector")
    if declared_unit is not None and declared_unit != expected_unit:
        raise SubjectExecutionError(
            "ParameterContractViolation",
            "errorVector unit must match the shared input coordinate unit.",
        )
    return [float(value) for value in vector], float(gain)


def _apply_offset(
    artifact: OrderedPointSequence,
    parameter_set: ParameterSet,
    *,
    compensated: bool,
) -> OrderedPointSequence:
    vector, gain = _offset_parameters(artifact, parameter_set)
    scale = 1.0 - gain if compensated else 1.0
    points = [
        [coordinate + scale * offset for coordinate, offset in zip(point, vector, strict=True)]
        for point in artifact.points
    ]
    return artifact.model_copy(update={"points": points})


def _baseline_subject(artifact: OrderedPointSequence, parameter_set: ParameterSet) -> OrderedPointSequence:
    return _apply_offset(artifact, parameter_set, compensated=False)


def _compensated_subject(artifact: OrderedPointSequence, parameter_set: ParameterSet) -> OrderedPointSequence:
    return _apply_offset(artifact, parameter_set, compensated=True)


_OFFSET_PARAMETER_SCHEMA_ID = "ordered-point.offset-error-parameters@1"

register_subject(
    SubjectDefinition(
        subject_id="ordered-point.offset-baseline",
        subject_version="1",
        display_name="Offset baseline",
        description="Applies the declared deterministic contour error without compensation.",
        parameter_schema_id=_OFFSET_PARAMETER_SCHEMA_ID,
    ),
    _baseline_subject,
)

register_subject(
    SubjectDefinition(
        subject_id="ordered-point.offset-compensated",
        subject_version="1",
        display_name="Offset compensated",
        description="Applies the same contour error after the declared compensation gain.",
        parameter_schema_id=_OFFSET_PARAMETER_SCHEMA_ID,
    ),
    _compensated_subject,
)
