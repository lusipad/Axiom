from __future__ import annotations

import hashlib
import json
import math
import operator
import platform
import re
from dataclasses import dataclass
from importlib.metadata import version as package_version
from typing import Any, Mapping

import numpy as np
from pint import DimensionalityError, UndefinedUnitError, UnitRegistry
from pydantic import ValidationError
from scipy.spatial.distance import cdist

from .models import (
    CapabilityResolution,
    CaseOutcome,
    DomainFailure,
    EvaluationReport,
    EvaluationRequest,
    Evidence,
    ExecutionStatus,
    MetricRequest,
    MetricResult,
    MetricStatus,
    OrderedPointSequence,
    Provenance,
    ScoreComponent,
    ScoreResult,
    Threshold,
)

_UREG = UnitRegistry()
_LENGTH_DIMENSION = _UREG.meter.dimensionality
_TIME_DIMENSION = _UREG.second.dimensionality
_ALIGNMENT_ID = "ordered-point.alignment.identity@1"
_DISTANCE_ID = "ordered-point.distance.euclidean@1"
_BOUNDARY_POLICY_ID = "ordered-point.boundary.finite-sequence@1"
_TOLERANCE_POLICY_ID = "ordered-point.tolerance.absolute@1"
_UNSCALED_UNITS = {"coordinate-unit", "parameter-unit"}
_MAX_PAIRWISE_CELLS = 5_000_000
_MAX_FRECHET_PATH_BUDGET = 2_000_000

_CAP_PARSED = "ordered-point.artifact.parsed@1"
_CAP_VALID = "ordered-point.artifact.valid@1"
_CAP_ORDERED = "ordered-point.sequence.ordered@1"
_CAP_EUCLIDEAN = "ordered-point.coordinate.euclidean@1"
_CAP_UNIT = "ordered-point.coordinate.unit-known@1"
_CAP_FRAME = "ordered-point.coordinate.frame-known@1"
_CAP_CLOSED = "ordered-point.sequence.closed-declared@1"
_CAP_REFERENCE = "ordered-point.reference.bound@1"
_CAP_CORRESPONDENCE = "ordered-point.correspondence.policy-bound@1"
_CAP_PARAMETER = "ordered-point.parameter.values@1"
_CAP_TIME = "ordered-point.parameter.time@1"

_INTRINSIC_METRICS = {
    "point.count",
    "coordinate.dimension",
    "coordinate.finite",
    "duplicate.consecutive.count",
    "segment.zero_length.count",
    "bounds.axis_aligned",
    "path.length.open",
    "closure.gap",
    "path.length.closed",
    "step.length.min",
    "step.length.max",
    "step.length.mean",
    "step.length.rms",
    "step.length.std",
}
_TIME_INTERVAL_METRICS = {
    "parameter.interval.min",
    "parameter.interval.max",
    "parameter.interval.mean",
    "parameter.interval.std",
}
_KINEMATIC_METRICS = {
    "speed.point.mean",
    "acceleration.point.max",
}
_TIME_METRICS = _TIME_INTERVAL_METRICS | _KINEMATIC_METRICS
_REFERENCE_STRATEGIES = {
    "paired.euclidean.rms": "ordered-point.correspondence.index-paired@1",
    "paired.euclidean.max": "ordered-point.correspondence.index-paired@1",
    "nearest.directed.mean": "ordered-point.correspondence.nearest-directed@1",
    "nearest.directed.max": "ordered-point.correspondence.nearest-directed@1",
    "hausdorff.discrete": "ordered-point.correspondence.discrete-hausdorff@1",
    "frechet.discrete": "ordered-point.correspondence.discrete-frechet@1",
}
_SUPPORTED_STRATEGIES = set(_REFERENCE_STRATEGIES.values())


@dataclass(frozen=True)
class _ArtifactState:
    artifact: OrderedPointSequence
    points: np.ndarray | None
    valid: bool
    capabilities: frozenset[str]
    failures: tuple[DomainFailure, ...]
    length_unit: str | None
    time_unit: str | None

    @property
    def result_length_unit(self) -> str:
        return self.length_unit or "coordinate-unit"


def evaluate(payload: Mapping[str, Any] | EvaluationRequest) -> EvaluationReport:
    """Evaluate one ordered point sequence without inferring missing semantics."""
    payload_hash = _content_hash(payload)
    try:
        request = payload if isinstance(payload, EvaluationRequest) else EvaluationRequest.model_validate(payload)
    except ValidationError as exc:
        return _seal_evaluation_report(
            EvaluationReport(
                execution_status=ExecutionStatus.SKIPPED,
                case_outcome=CaseOutcome.INVALID,
                domain_failures=[
                    DomainFailure(
                        code="MalformedRequest",
                        message="Request does not satisfy evaluation-request@1.",
                        path=_validation_path(exc),
                    )
                ],
                content_hash=payload_hash,
            )
        )

    request_hash = _content_hash(request)
    provenance = _build_provenance(request, request_hash)

    artifact_state = _validate_artifact(request.artifact, "artifact")
    failures = list(artifact_state.failures)
    capabilities = set(artifact_state.capabilities)
    reference_state: _ArtifactState | None = None
    case_invalid = not artifact_state.valid

    metric_requests = request.case.required_metrics + request.case.optional_metrics
    metric_ids = [item.metric_id for item in metric_requests]
    if len(metric_ids) != len(set(metric_ids)):
        failures.append(
            DomainFailure(
                code="DuplicateMetricRequest",
                message="A metric may appear only once in an EvaluationCase.",
                path="case",
            )
        )
        case_invalid = True

    profile = request.case.score_profile
    if profile is not None:
        rule_ids = [rule.metric_id for rule in profile.rules]
        if len(rule_ids) != len(set(rule_ids)) or not set(rule_ids).issubset(metric_ids):
            failures.append(
                DomainFailure(
                    code="InvalidScoreProfile",
                    message="Score rules must be unique and refer to requested metrics.",
                    path="case.scoreProfile.rules",
                )
            )
            case_invalid = True

    binding = request.reference_binding
    if binding is not None:
        policy_fields = {
            "referenceBinding.alignment": binding.alignment,
            "referenceBinding.strategyId": binding.strategy_id,
            "referenceBinding.distanceId": binding.distance_id,
            "referenceBinding.tolerance.policyId": binding.tolerance.policy_id,
            "referenceBinding.boundaryPolicy": binding.boundary_policy,
        }
        for policy_path, policy_id in policy_fields.items():
            if not _is_versioned_id(policy_id):
                failures.append(
                    DomainFailure(
                        code="UnversionedReferencePolicy",
                        message="ReferenceBinding policy IDs must end in a numeric version.",
                        path=policy_path,
                    )
                )
                case_invalid = True
        if binding.tolerance.unit != "coordinate-unit" and not _has_dimension(
            binding.tolerance.unit, _LENGTH_DIMENSION
        ):
            failures.append(
                DomainFailure(
                    code="InvalidToleranceUnit",
                    message="Reference tolerance must use coordinate-unit or a physical length unit.",
                    path="referenceBinding.tolerance.unit",
                )
            )
            case_invalid = True

        reference_state = _validate_artifact(binding.reference, "referenceBinding.reference")
        failures.extend(reference_state.failures)
        if not reference_state.valid:
            case_invalid = True
        elif artifact_state.valid and artifact_state.points is not None and reference_state.points is not None:
            if artifact_state.points.shape[1] != reference_state.points.shape[1]:
                failures.append(
                    DomainFailure(
                        code="ReferenceDimensionMismatch",
                        message="Observed and reference point dimensions differ.",
                        path="referenceBinding.reference.points",
                    )
                )
                case_invalid = True
            else:
                if _is_versioned_id(binding.strategy_id):
                    capabilities.add(_CAP_CORRESPONDENCE)
                if _binding_context_complete(artifact_state, reference_state, binding):
                    capabilities.add(_CAP_REFERENCE)

        observed_frame = _known_frame(request.artifact)
        reference_frame = _known_frame(binding.reference)
        if binding.alignment == _ALIGNMENT_ID and observed_frame and reference_frame and observed_frame != reference_frame:
            failures.append(
                DomainFailure(
                    code="ProfileConflict",
                    message="Identity alignment cannot join different declared coordinate frames.",
                    path="referenceBinding.alignment",
                )
            )
            case_invalid = True

    if case_invalid:
        results = [
            _unavailable(item.metric_id, MetricStatus.INVALID_OBSERVATION, "InvalidEvaluationInput")
            for item in metric_requests
        ]
        return _report(
            execution_status=ExecutionStatus.SKIPPED,
            case_outcome=CaseOutcome.INVALID,
            metric_results=results,
            capabilities=capabilities,
            failures=failures,
            score=_invalid_score(profile.profile_id) if profile is not None else None,
            provenance=provenance,
        )

    results: list[MetricResult] = []
    for item in metric_requests:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            result = _compute_metric(item.metric_id, artifact_state, binding, reference_state, failures)
        results.append(_apply_threshold(result, item.threshold))

    required_results = results[: len(request.case.required_metrics)]
    outcome = _aggregate_outcome(required_results)
    preflight_statuses = {
        MetricStatus.NOT_APPLICABLE,
        MetricStatus.INSUFFICIENT_CONTEXT,
        MetricStatus.UNSUPPORTED_CAPABILITY,
    }
    execution = (
        ExecutionStatus.SKIPPED
        if any(result.status in preflight_statuses for result in required_results)
        else ExecutionStatus.SUCCEEDED
    )
    score = _compute_score(profile, results) if profile is not None else None

    return _report(
        execution_status=execution,
        case_outcome=outcome,
        metric_results=results,
        capabilities=capabilities,
        failures=failures,
        score=score,
        provenance=provenance,
    )


def _validate_artifact(artifact: OrderedPointSequence, path: str) -> _ArtifactState:
    failures: list[DomainFailure] = []
    capabilities = {_CAP_PARSED}
    points: np.ndarray | None = None

    if not artifact.points:
        failures.append(DomainFailure(code="EmptySequence", message="At least one point is required.", path=f"{path}.points"))
    else:
        dimensions = [len(point) for point in artifact.points]
        if len(set(dimensions)) != 1:
            failures.append(
                DomainFailure(
                    code="InconsistentDimension",
                    message="All points must have the same dimension.",
                    path=f"{path}.points",
                )
            )
        elif dimensions[0] not in (2, 3):
            failures.append(
                DomainFailure(
                    code="UnsupportedDimension",
                    message="Only two- and three-dimensional Euclidean points are supported.",
                    path=f"{path}.points",
                )
            )
        else:
            points = np.asarray(artifact.points, dtype=np.float64)
            if not bool(np.all(np.isfinite(points))):
                failures.append(
                    DomainFailure(
                        code="NonFiniteCoordinate",
                        message="All coordinates must be finite.",
                        path=f"{path}.points",
                    )
                )

    length_unit: str | None = None
    submitted_unit = artifact.semantics.unit if artifact.semantics else None
    if submitted_unit is not None:
        if not submitted_unit.strip():
            failures.append(
                DomainFailure(
                    code="InvalidUnit",
                    message="An explicitly supplied coordinate unit cannot be empty.",
                    path=f"{path}.semantics.unit",
                )
            )
        elif submitted_unit.lower() == "unknown":
            pass
        elif submitted_unit == "coordinate-unit":
            failures.append(
                DomainFailure(
                    code="InvalidUnit",
                    message="coordinate-unit is an evaluator result marker, not a submitted physical unit.",
                    path=f"{path}.semantics.unit",
                )
            )
        elif _has_dimension(submitted_unit, _LENGTH_DIMENSION):
            length_unit = submitted_unit
            capabilities.add(_CAP_UNIT)
        else:
            failures.append(
                DomainFailure(
                    code="InvalidUnit",
                    message="Coordinate unit must be a physical length unit.",
                    path=f"{path}.semantics.unit",
                )
            )

    if _known_frame(artifact):
        capabilities.add(_CAP_FRAME)
    if artifact.semantics is not None and artifact.semantics.closed is not None:
        capabilities.add(_CAP_CLOSED)

    time_unit: str | None = None
    if artifact.parameter is not None:
        parameter = artifact.parameter
        parameter_valid = True
        if len(parameter.values) != len(artifact.points):
            failures.append(
                DomainFailure(
                    code="ParameterLengthMismatch",
                    message="Parameter values must match the number of points.",
                    path=f"{path}.parameter.values",
                )
            )
            parameter_valid = False
        values = np.asarray(parameter.values, dtype=np.float64)
        if not bool(np.all(np.isfinite(values))):
            failures.append(
                DomainFailure(
                    code="NonFiniteParameter",
                    message="Parameter values must be finite.",
                    path=f"{path}.parameter.values",
                )
            )
            parameter_valid = False
        if values.size > 1:
            with np.errstate(over="ignore", invalid="ignore"):
                parameter_increases = bool(np.all(np.diff(values) > 0))
            if not parameter_increases:
                failures.append(
                    DomainFailure(
                        code="NonMonotoneParameter",
                        message="Time values must be strictly increasing.",
                        path=f"{path}.parameter.values",
                    )
                )
                parameter_valid = False
        if parameter_valid:
            capabilities.add(_CAP_PARAMETER)

        if parameter.unit is not None:
            if not parameter.unit.strip():
                failures.append(
                    DomainFailure(
                        code="InvalidParameterUnit",
                        message="An explicitly supplied time unit cannot be empty.",
                        path=f"{path}.parameter.unit",
                    )
                )
            elif parameter.unit.lower() == "unknown":
                pass
            elif _has_dimension(parameter.unit, _TIME_DIMENSION):
                time_unit = parameter.unit
                if parameter_valid:
                    capabilities.add(_CAP_TIME)
            else:
                failures.append(
                    DomainFailure(
                        code="InvalidParameterUnit",
                        message="A time parameter requires a physical time unit.",
                        path=f"{path}.parameter.unit",
                    )
                )

    valid = not any(failure.severity == "error" for failure in failures)
    if valid and points is not None:
        capabilities.update({_CAP_VALID, _CAP_ORDERED, _CAP_EUCLIDEAN})
        if len(points) > 1:
            with np.errstate(over="ignore", invalid="ignore"):
                duplicate_count = int(
                    np.count_nonzero(np.linalg.norm(np.diff(points, axis=0), axis=1) == 0)
                )
            if duplicate_count:
                failures.append(
                    DomainFailure(
                        code="ConsecutiveDuplicate",
                        message=f"Found {duplicate_count} consecutive duplicate point pair(s).",
                        path=f"{path}.points",
                        severity="finding",
                    )
                )

    return _ArtifactState(
        artifact=artifact,
        points=points,
        valid=valid,
        capabilities=frozenset(capabilities),
        failures=tuple(failures),
        length_unit=length_unit,
        time_unit=time_unit,
    )


def _compute_metric(
    metric_id: str,
    state: _ArtifactState,
    binding: Any,
    reference_state: _ArtifactState | None,
    failures: list[DomainFailure],
) -> MetricResult:
    if metric_id in _INTRINSIC_METRICS:
        return _compute_intrinsic(metric_id, state)
    if metric_id in _TIME_METRICS:
        return _compute_time(metric_id, state)
    if metric_id in _REFERENCE_STRATEGIES:
        return _compute_reference(metric_id, state, binding, reference_state, failures)
    return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "UnknownMetricDefinition")


def _compute_intrinsic(metric_id: str, state: _ArtifactState) -> MetricResult:
    assert state.points is not None
    points = state.points
    count = len(points)
    unit = state.result_length_unit

    if metric_id == "point.count":
        return _computed(metric_id, count, method="artifact-structure@1")
    if metric_id == "coordinate.dimension":
        return _computed(metric_id, int(points.shape[1]), method="artifact-structure@1")
    if metric_id == "coordinate.finite":
        return _computed(metric_id, True, method="numpy-isfinite@1")
    if metric_id == "bounds.axis_aligned":
        value = {"min": np.min(points, axis=0).tolist(), "max": np.max(points, axis=0).tolist()}
        return _computed(metric_id, value, unit=unit, method="numpy-axis-bounds@1")

    if count < 2:
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MinimumPointCountNotMet")

    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    if metric_id == "duplicate.consecutive.count" or metric_id == "segment.zero_length.count":
        return _computed(metric_id, int(np.count_nonzero(steps == 0)), method="euclidean-exact-zero@1")
    if metric_id == "path.length.open":
        return _computed(metric_id, float(np.sum(steps)), unit=unit, method="euclidean-polyline@1")
    if metric_id == "closure.gap":
        return _computed(metric_id, float(np.linalg.norm(points[-1] - points[0])), unit=unit, method="euclidean@1")
    if metric_id == "path.length.closed":
        closed = state.artifact.semantics.closed if state.artifact.semantics else None
        if closed is None:
            return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "ClosedSemanticsMissing")
        if not closed:
            return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "SequenceDeclaredOpen")
        value = float(np.sum(steps) + np.linalg.norm(points[-1] - points[0]))
        return _computed(metric_id, value, unit=unit, method="euclidean-closed-polyline@1")

    statistic = metric_id.rsplit(".", 1)[-1]
    calculators = {
        "min": np.min,
        "max": np.max,
        "mean": np.mean,
        "rms": lambda values: np.sqrt(np.mean(np.square(values))),
        "std": np.std,
    }
    return _computed(metric_id, float(calculators[statistic](steps)), unit=unit, method="numpy-step-statistic@1")


def _compute_time(metric_id: str, state: _ArtifactState) -> MetricResult:
    parameter = state.artifact.parameter
    if parameter is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "ParameterMissing")
    if _CAP_PARAMETER not in state.capabilities:
        return _unavailable(metric_id, MetricStatus.INVALID_OBSERVATION, "InvalidParameterValues")
    if metric_id in _TIME_INTERVAL_METRICS:
        if len(parameter.values) < 2:
            return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MinimumPointCountNotMet")

        intervals = np.diff(np.asarray(parameter.values, dtype=np.float64))
        statistic = metric_id.rsplit(".", 1)[-1]
        calculators = {"min": np.min, "max": np.max, "mean": np.mean, "std": np.std}
        return _computed(
            metric_id,
            float(calculators[statistic](intervals)),
            unit=state.time_unit or "parameter-unit",
            method="numpy-time-interval-statistic@1",
        )
    if _CAP_TIME not in state.capabilities:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "TimeUnitMissing")

    assert state.points is not None
    if metric_id == "speed.point.mean":
        if len(parameter.values) < 2:
            return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MinimumPointCountNotMet")
        return _compute_speed_mean(metric_id, state)
    if len(parameter.values) < 3:
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "MinimumPointCountNotMet")
    return _compute_acceleration_max(metric_id, state)


def _compute_speed_mean(metric_id: str, state: _ArtifactState) -> MetricResult:
    velocities, _ = _forward_adjacent_velocities(state)
    speeds = np.linalg.norm(velocities, axis=1)
    return _computed(
        metric_id,
        float(np.mean(speeds)),
        unit=_kinematic_unit(state, order=1),
        method="numpy-forward-adjacent-speed@1",
    )


def _compute_acceleration_max(metric_id: str, state: _ArtifactState) -> MetricResult:
    velocities, intervals = _forward_adjacent_velocities(state)
    midpoint_intervals = 0.5 * (intervals[:-1] + intervals[1:])
    accelerations = np.diff(velocities, axis=0) / midpoint_intervals[:, np.newaxis]
    magnitudes = np.linalg.norm(accelerations, axis=1)
    return _computed(
        metric_id,
        float(np.max(magnitudes)),
        unit=_kinematic_unit(state, order=2),
        method="numpy-forward-adjacent-acceleration@1",
    )


def _forward_adjacent_velocities(state: _ArtifactState) -> tuple[np.ndarray, np.ndarray]:
    assert state.points is not None
    parameter = state.artifact.parameter
    assert parameter is not None
    intervals = np.diff(np.asarray(parameter.values, dtype=np.float64))
    deltas = np.diff(state.points, axis=0)
    return deltas / intervals[:, np.newaxis], intervals


def _kinematic_unit(state: _ArtifactState, *, order: int) -> str:
    assert state.time_unit is not None
    length_unit = state.length_unit or "coordinate-unit"
    if order == 1:
        return f"{length_unit}/{state.time_unit}"
    return f"{length_unit}/{state.time_unit}^{order}"


def _compute_reference(
    metric_id: str,
    state: _ArtifactState,
    binding: Any,
    reference_state: _ArtifactState | None,
    failures: list[DomainFailure],
) -> MetricResult:
    if binding is None or reference_state is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "ReferenceBindingMissing")

    if binding.alignment != _ALIGNMENT_ID:
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "UnsupportedAlignment")
    if binding.distance_id != _DISTANCE_ID:
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "UnsupportedDistanceDefinition")
    if binding.tolerance.policy_id != _TOLERANCE_POLICY_ID:
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "UnsupportedTolerancePolicy")
    if binding.boundary_policy != _BOUNDARY_POLICY_ID:
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "UnsupportedBoundaryPolicy")
    if binding.strategy_id not in _SUPPORTED_STRATEGIES:
        return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "UnsupportedCorrespondenceStrategy")
    if binding.strategy_id != _REFERENCE_STRATEGIES[metric_id]:
        failures.append(
            DomainFailure(
                code="UndefinedCorrespondence",
                message=f"{metric_id} is not defined under {binding.strategy_id}.",
                path="referenceBinding.strategyId",
            )
        )
        return _unavailable(metric_id, MetricStatus.NOT_APPLICABLE, "CorrespondenceStrategyMismatch")

    prepared = _prepare_reference_points(state, reference_state)
    if prepared is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "ReferenceUnitContextIncomplete")
    observed, reference, unit = prepared
    tolerance = _reference_tolerance(binding, unit)
    if tolerance is None:
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "ReferenceToleranceContextIncomplete")
    if not math.isfinite(tolerance):
        return _unavailable(metric_id, MetricStatus.NUMERICAL_FAILURE, "NonFiniteComputation")
    if unit != "coordinate-unit" and not _identity_frame_context_complete(state, reference_state):
        return _unavailable(metric_id, MetricStatus.INSUFFICIENT_CONTEXT, "ReferenceFrameContextIncomplete")

    if metric_id.startswith("paired."):
        if len(observed) != len(reference):
            failures.append(
                DomainFailure(
                    code="UndefinedCorrespondence",
                    message="Index-paired metrics require equal point counts.",
                    path="referenceBinding.reference.points",
                )
            )
            return _unavailable(metric_id, MetricStatus.INVALID_OBSERVATION, "PointCountMismatch")
        distances = np.linalg.norm(observed - reference, axis=1)
        value = float(np.sqrt(np.mean(np.square(distances)))) if metric_id.endswith(".rms") else float(np.max(distances))
        return _with_reference_details(
            _computed(metric_id, value, unit=unit, method="numpy-index-paired-euclidean@1"),
            binding,
            tolerance,
        )

    rows = len(observed)
    columns = len(reference)
    pairwise_cells = rows * columns
    if pairwise_cells > _MAX_PAIRWISE_CELLS:
        return _unavailable(
            metric_id,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            "ComplexityBudgetExceeded",
            details={
                "budgetKind": "pairwise-distance-cells",
                "requested": pairwise_cells,
                "limit": _MAX_PAIRWISE_CELLS,
            },
        )
    if metric_id == "frechet.discrete":
        path_budget = pairwise_cells * (rows + columns)
        if path_budget > _MAX_FRECHET_PATH_BUDGET:
            return _unavailable(
                metric_id,
                MetricStatus.UNSUPPORTED_CAPABILITY,
                "ComplexityBudgetExceeded",
                details={
                    "budgetKind": "frechet-path-storage",
                    "requested": path_budget,
                    "limit": _MAX_FRECHET_PATH_BUDGET,
                },
            )

    distances = cdist(observed, reference, metric="euclidean")
    if metric_id.startswith("nearest.directed"):
        nearest = np.min(distances, axis=1)
        matches = [_nearest_witness(distances, index) for index in range(len(observed))]
        if metric_id.endswith(".mean"):
            return _with_reference_details(
                _computed(
                    metric_id,
                    float(np.mean(nearest)),
                    unit=unit,
                    method="scipy-cdist-nearest-directed@1",
                    details={"matches": matches},
                ),
                binding,
                tolerance,
            )
        observed_index = _first_tied_index(nearest, float(np.max(nearest)))
        return _with_reference_details(
            _computed(
                metric_id,
                float(nearest[observed_index]),
                unit=unit,
                method="scipy-cdist-nearest-directed@1",
                details={"witness": matches[observed_index]},
            ),
            binding,
            tolerance,
        )

    if metric_id == "hausdorff.discrete":
        result = _discrete_hausdorff(metric_id, distances, unit)
    else:
        result = _discrete_frechet(metric_id, distances, unit)
    return _with_reference_details(result, binding, tolerance)


def _prepare_reference_points(
    observed: _ArtifactState, reference: _ArtifactState
) -> tuple[np.ndarray, np.ndarray, str] | None:
    assert observed.points is not None and reference.points is not None
    if (observed.length_unit is None) != (reference.length_unit is None):
        return None
    if observed.length_unit is None:
        return observed.points, reference.points, "coordinate-unit"
    try:
        factor = (1 * _UREG(reference.length_unit)).to(observed.length_unit).magnitude
    except (DimensionalityError, UndefinedUnitError):
        return None
    return observed.points, reference.points * float(factor), observed.length_unit


def _reference_tolerance(binding: Any, result_unit: str) -> float | None:
    tolerance = binding.tolerance
    if result_unit == "coordinate-unit":
        return tolerance.value if tolerance.unit == "coordinate-unit" else None
    if tolerance.unit == "coordinate-unit":
        return None
    try:
        return float((tolerance.value * _UREG(tolerance.unit)).to(result_unit).magnitude)
    except (DimensionalityError, UndefinedUnitError):
        return None


def _with_reference_details(result: MetricResult, binding: Any, tolerance: float) -> MetricResult:
    details = {
        **result.details,
        "referenceBinding": {
            "alignment": binding.alignment,
            "strategyId": binding.strategy_id,
            "distanceId": binding.distance_id,
            "tolerance": {
                "policyId": binding.tolerance.policy_id,
                "value": binding.tolerance.value,
                "unit": binding.tolerance.unit,
                "valueInResultUnit": tolerance,
            },
            "boundaryPolicy": binding.boundary_policy,
        },
    }
    return result.model_copy(update={"details": details})


def _nearest_witness(distances: np.ndarray, observed_index: int) -> dict[str, int]:
    row = distances[observed_index]
    minimum = float(np.min(row))
    tied = np.flatnonzero(row == minimum)
    return {
        "observedIndex": observed_index,
        "referenceIndex": int(tied[0]),
        "tieCount": int(len(tied)),
    }


def _discrete_hausdorff(metric_id: str, distances: np.ndarray, unit: str) -> MetricResult:
    observed_nearest = np.min(distances, axis=1)
    reference_nearest = np.min(distances, axis=0)
    value = float(max(np.max(observed_nearest), np.max(reference_nearest)))
    candidates: list[tuple[int, int]] = []

    for observed_index, distance in enumerate(observed_nearest):
        if float(distance) == value:
            reference_index = _first_tied_index(distances[observed_index], float(distance))
            candidates.append((observed_index, reference_index))
    for reference_index, distance in enumerate(reference_nearest):
        if float(distance) == value:
            observed_index = _first_tied_index(distances[:, reference_index], float(distance))
            candidates.append((observed_index, reference_index))

    observed_index, reference_index = min(candidates)
    return _computed(
        metric_id,
        value,
        unit=unit,
        method="scipy-cdist-discrete-hausdorff@1",
        details={
            "witness": {"observedIndex": observed_index, "referenceIndex": reference_index},
            "directedObservedToReference": float(np.max(observed_nearest)),
            "directedReferenceToObserved": float(np.max(reference_nearest)),
        },
    )


def _discrete_frechet(metric_id: str, distances: np.ndarray, unit: str) -> MetricResult:
    rows, columns = distances.shape
    values = np.empty((rows, columns), dtype=np.float64)
    paths: list[list[tuple[tuple[int, int], ...] | None]] = [[None] * columns for _ in range(rows)]

    for row in range(rows):
        for column in range(columns):
            current = float(distances[row, column])
            if row == 0 and column == 0:
                values[row, column] = current
                paths[row][column] = ((0, 0),)
                continue

            predecessors: list[tuple[int, int]] = []
            if row > 0:
                predecessors.append((row - 1, column))
            if row > 0 and column > 0:
                predecessors.append((row - 1, column - 1))
            if column > 0:
                predecessors.append((row, column - 1))

            candidate_values = [max(float(values[i, j]), current) for i, j in predecessors]
            best_value = min(candidate_values)
            candidate_paths = [
                paths[i][j] + ((row, column),)
                for (i, j), value in zip(predecessors, candidate_values, strict=True)
                if value == best_value
            ]
            values[row, column] = best_value
            paths[row][column] = min(candidate_paths)

    coupling = paths[-1][-1]
    assert coupling is not None
    return _computed(
        metric_id,
        float(values[-1, -1]),
        unit=unit,
        method="axiom-discrete-frechet-dp@1",
        details={"couplingPath": [list(pair) for pair in coupling]},
    )


def _apply_threshold(result: MetricResult, threshold: Threshold | None) -> MetricResult:
    if threshold is None or result.status is not MetricStatus.COMPUTED:
        return result
    if not isinstance(result.value, (int, float)) or isinstance(result.value, bool):
        return _unavailable(result.metric_id, MetricStatus.NOT_APPLICABLE, "ThresholdRequiresScalarMetric")

    comparison_value = float(result.value)
    if threshold.unit is not None:
        if result.unit is None:
            return _unavailable(result.metric_id, MetricStatus.NOT_APPLICABLE, "ThresholdUnitIncompatible")
        if result.unit in _UNSCALED_UNITS:
            return _unavailable(
                result.metric_id,
                MetricStatus.INSUFFICIENT_CONTEXT,
                "PhysicalThresholdRequiresKnownUnit",
                details={"unscaledValue": result.value, "unscaledUnit": result.unit},
            )
        try:
            comparison_value = float((comparison_value * _UREG(result.unit)).to(threshold.unit).magnitude)
        except (DimensionalityError, UndefinedUnitError):
            return _unavailable(result.metric_id, MetricStatus.NOT_APPLICABLE, "ThresholdUnitIncompatible")

    operations = {"<=": operator.le, "<": operator.lt, ">=": operator.ge, ">": operator.gt}
    if not math.isfinite(comparison_value):
        return _unavailable(result.metric_id, MetricStatus.NUMERICAL_FAILURE, "NonFiniteComputation")
    return result.model_copy(update={"threshold_passed": bool(operations[threshold.operator](comparison_value, threshold.value))})


def _aggregate_outcome(required: list[MetricResult]) -> CaseOutcome:
    if any(result.status is MetricStatus.NOT_APPLICABLE for result in required):
        return CaseOutcome.INVALID
    if any(result.threshold_passed is False for result in required):
        return CaseOutcome.FAILED
    if any(result.status is MetricStatus.UNSUPPORTED_CAPABILITY for result in required):
        return CaseOutcome.UNSUPPORTED
    if any(result.status is not MetricStatus.COMPUTED for result in required):
        return CaseOutcome.INCONCLUSIVE
    return CaseOutcome.PASSED


def _compute_score(profile: Any, results: list[MetricResult]) -> ScoreResult:
    indexed = {result.metric_id: result for result in results}
    components: list[ScoreComponent] = []
    weighted_sum = 0.0
    total_weight = 0.0

    for rule in profile.rules:
        result = indexed[rule.metric_id]
        if result.status is not MetricStatus.COMPUTED or not isinstance(result.value, (int, float)) or isinstance(result.value, bool):
            status = result.status if result.status is not MetricStatus.COMPUTED else MetricStatus.INVALID_OBSERVATION
            return ScoreResult(profile_id=profile.profile_id, status=status, reason_code="ScoreMetricUnavailable")

        value = float(result.value)
        if rule.unit is not None:
            if result.unit is None:
                return ScoreResult(
                    profile_id=profile.profile_id,
                    status=MetricStatus.NOT_APPLICABLE,
                    reason_code="ScoreRuleUnitIncompatible",
                )
            if result.unit in _UNSCALED_UNITS:
                return ScoreResult(
                    profile_id=profile.profile_id,
                    status=MetricStatus.INSUFFICIENT_CONTEXT,
                    reason_code="PhysicalScoreRuleRequiresKnownUnit",
                )
            try:
                value = float((value * _UREG(result.unit)).to(rule.unit).magnitude)
            except (DimensionalityError, UndefinedUnitError):
                return ScoreResult(
                    profile_id=profile.profile_id,
                    status=MetricStatus.NOT_APPLICABLE,
                    reason_code="ScoreRuleUnitIncompatible",
                )

        if rule.direction == "lower-is-better":
            numerator = rule.worst - value
            denominator = rule.worst - rule.best
        else:
            numerator = value - rule.worst
            denominator = rule.best - rule.worst
        if not math.isfinite(numerator) or not math.isfinite(denominator):
            return ScoreResult(
                profile_id=profile.profile_id,
                status=MetricStatus.NUMERICAL_FAILURE,
                reason_code="NonFiniteComputation",
            )
        normalized = numerator / denominator
        normalized = min(1.0, max(0.0, normalized))
        weighted_sum += normalized * rule.weight
        total_weight += rule.weight
        if not math.isfinite(weighted_sum) or not math.isfinite(total_weight):
            return ScoreResult(
                profile_id=profile.profile_id,
                status=MetricStatus.NUMERICAL_FAILURE,
                reason_code="NonFiniteComputation",
            )
        components.append(
            ScoreComponent(metric_id=rule.metric_id, normalized_value=normalized, weight=rule.weight)
        )

    return ScoreResult(
        profile_id=profile.profile_id,
        status=MetricStatus.COMPUTED,
        value=100.0 * weighted_sum / total_weight,
        components=components,
    )


def _computed(
    metric_id: str,
    value: Any,
    *,
    unit: str | None = None,
    method: str,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    if not _value_is_finite(value):
        return _unavailable(metric_id, MetricStatus.NUMERICAL_FAILURE, "NonFiniteComputation")
    return MetricResult(
        metric_id=metric_id,
        metric_definition_id=f"ordered-point.{metric_id}@1",
        requires=_metric_requirements(metric_id),
        status=MetricStatus.COMPUTED,
        value=value,
        unit=unit,
        details=details or {},
        evidence=Evidence(level="Observed", method=method),
    )


def _value_is_finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_value_is_finite(item) for item in value)
    if isinstance(value, dict):
        return all(_value_is_finite(item) for item in value.values())
    return True


def _unavailable(
    metric_id: str,
    status: MetricStatus,
    reason_code: str,
    *,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        metric_definition_id=f"ordered-point.{metric_id}@1",
        requires=_metric_requirements(metric_id),
        status=status,
        reason_code=reason_code,
        details=details or {},
    )


def _report(
    *,
    execution_status: ExecutionStatus,
    case_outcome: CaseOutcome,
    metric_results: list[MetricResult],
    capabilities: set[str],
    failures: list[DomainFailure],
    score: ScoreResult | None,
    provenance: Provenance,
) -> EvaluationReport:
    return _seal_evaluation_report(
        EvaluationReport(
            execution_status=execution_status,
            case_outcome=case_outcome,
            metric_results=metric_results,
            capabilities=[
                CapabilityResolution(
                    capability_id=capability,
                    source="ReferenceBinding"
                    if capability in {_CAP_REFERENCE, _CAP_CORRESPONDENCE}
                    else "Artifact",
                )
                for capability in sorted(capabilities)
            ],
            domain_failures=failures,
            content_hash="",
            provenance=provenance,
            score=score,
        )
    )


def _invalid_score(profile_id: str) -> ScoreResult:
    return ScoreResult(
        profile_id=profile_id,
        status=MetricStatus.INVALID_OBSERVATION,
        reason_code="InvalidEvaluationInput",
    )


def _has_dimension(unit: str, expected: Any) -> bool:
    try:
        return _UREG.Unit(unit).dimensionality == expected
    except (UndefinedUnitError, ValueError):
        return False


def _known_frame(artifact: OrderedPointSequence) -> str | None:
    if artifact.semantics is None or not artifact.semantics.coordinate_frame:
        return None
    frame = artifact.semantics.coordinate_frame.strip()
    return None if not frame or frame.lower() == "unknown" else frame


def _first_tied_index(values: np.ndarray, target: float) -> int:
    tied = np.flatnonzero(values == target)
    return int(tied[0])


def _binding_context_complete(observed: _ArtifactState, reference: _ArtifactState, binding: Any) -> bool:
    if not all(
        _is_versioned_id(policy_id)
        for policy_id in (
            binding.alignment,
            binding.strategy_id,
            binding.distance_id,
            binding.tolerance.policy_id,
            binding.boundary_policy,
        )
    ):
        return False
    if (observed.length_unit is None) != (reference.length_unit is None):
        return False
    result_unit = observed.length_unit or "coordinate-unit"
    if result_unit != "coordinate-unit" and binding.alignment == _ALIGNMENT_ID:
        if not _identity_frame_context_complete(observed, reference):
            return False
    return _reference_tolerance(binding, result_unit) is not None


def _identity_frame_context_complete(observed: _ArtifactState, reference: _ArtifactState) -> bool:
    observed_frame = _known_frame(observed.artifact)
    reference_frame = _known_frame(reference.artifact)
    return observed_frame is not None and observed_frame == reference_frame


def _is_versioned_id(value: str) -> bool:
    return re.fullmatch(r".+@[0-9]+", value) is not None


def _metric_requirements(metric_id: str) -> list[str]:
    if metric_id in {"point.count", "coordinate.dimension", "coordinate.finite"}:
        return [_CAP_PARSED]
    if metric_id in _TIME_INTERVAL_METRICS:
        return [_CAP_PARAMETER]
    if metric_id in _KINEMATIC_METRICS:
        return [_CAP_VALID, _CAP_ORDERED, _CAP_EUCLIDEAN, _CAP_TIME]
    if metric_id in _REFERENCE_STRATEGIES:
        return [_CAP_REFERENCE, _CAP_CORRESPONDENCE, _CAP_EUCLIDEAN]
    if metric_id in _INTRINSIC_METRICS:
        requirements = [_CAP_VALID, _CAP_ORDERED, _CAP_EUCLIDEAN]
        if metric_id == "path.length.closed":
            requirements.append(_CAP_CLOSED)
        return requirements
    return []


def _build_provenance(request: EvaluationRequest, request_hash: str) -> Provenance:
    binding = request.reference_binding
    profile = request.case.score_profile
    return Provenance(
        request_hash=request_hash,
        artifact_hash=_content_hash(request.artifact),
        case_hash=_canonical_content_hash(request.case),
        reference_hash=_content_hash(binding.reference) if binding is not None else None,
        reference_binding_hash=_content_hash(binding) if binding is not None else None,
        score_profile_hash=_canonical_content_hash(profile) if profile is not None else None,
        execution_outcome_policy=request.case.execution_outcome_policy,
        numeric_environment={
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "scipy": package_version("scipy"),
            "pint": package_version("pint"),
            "pydantic": package_version("pydantic"),
        },
    )


def _content_hash(payload: Any) -> str:
    serializable = (
        payload.model_dump(mode="json", by_alias=True, exclude_unset=True)
        if hasattr(payload, "model_dump")
        else payload
    )
    return _hash_serializable(serializable)


def _canonical_content_hash(payload: Any) -> str:
    serializable = (
        payload.model_dump(mode="json", by_alias=True, exclude_unset=False, exclude_none=False)
        if hasattr(payload, "model_dump")
        else payload
    )
    return _hash_serializable(serializable)


def _seal_evaluation_report(report: EvaluationReport) -> EvaluationReport:
    report_hash = _evaluation_report_hash(report)
    if report.content_hash == report_hash:
        return report
    return report.model_copy(update={"content_hash": report_hash})


def _evaluation_report_hash(report: EvaluationReport) -> str:
    return _hash_serializable(_evaluation_report_identity_payload(report))


def _evaluation_report_identity_payload(report: EvaluationReport) -> dict[str, Any]:
    return report.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude={"content_hash"},
    )


def _hash_serializable(serializable: Any) -> str:
    canonical = json.dumps(
        serializable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validation_path(exc: ValidationError) -> str | None:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    if not errors:
        return None
    return ".".join(str(part) for part in errors[0]["loc"])
