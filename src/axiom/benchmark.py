"""File-based CNC A/B comparison, independent of the built-in F4 solvers.

This evaluates sampled XYZ commands. Finite differences are diagnostics of the
command stream, not certificates for a controller's inter-sample motion law.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Annotated, Any, Literal, Mapping

import numpy as np
from pydantic import BeforeValidator, Field, StrictInt, model_validator

from .models import AxiomModel, _require_json_number

Number = Annotated[float, BeforeValidator(_require_json_number), Field(allow_inf_nan=False)]
Coordinate = Annotated[Number, Field(ge=-1e9, le=1e9)]
Positive = Annotated[Number, Field(gt=0, le=1e30)]
Nonnegative = Annotated[Number, Field(ge=0, le=1e30)]
Period = Annotated[Number, Field(ge=1e-6, le=1)]
Point = tuple[Coordinate, Coordinate, Coordinate]
AXES = ("X", "Y", "Z")
MAX_DISTANCE_PAIRS = 20_000_000
CORNER_ANGLE_DEGREES = 5.0
ARC_RADIUS_RELATIVE_TOLERANCE = 1e-6
BENCHMARK_SCOPE = "sampled-xyz-command"
UNCHECKED_PROPERTIES = (
    "continuous-inter-sample-constraints",
    "path-traversal-order-and-coverage",
    "collision-and-kinematics",
    "physical-response-and-machining-quality",
)


class BenchmarkAxisLimits(AxiomModel):
    axis: Literal["X", "Y", "Z"]
    minimum_position_mm: Coordinate = Field(alias="minimumPositionMm")
    maximum_position_mm: Coordinate = Field(alias="maximumPositionMm")
    maximum_velocity_mm_s: Positive = Field(alias="maximumVelocityMmS")
    maximum_acceleration_mm_s2: Positive = Field(alias="maximumAccelerationMmS2")
    maximum_jerk_mm_s3: Positive = Field(alias="maximumJerkMmS3")

    @model_validator(mode="after")
    def ordered_limits(self) -> BenchmarkAxisLimits:
        if self.minimum_position_mm >= self.maximum_position_mm:
            raise ValueError("minimumPositionMm must be less than maximumPositionMm")
        return self


class BenchmarkTolerances(AxiomModel):
    duration_seconds: Nonnegative = Field(default=0, alias="durationSeconds")
    path_deviation_mm: Nonnegative = Field(default=0.001, alias="pathDeviationMm")
    computation_seconds: Nonnegative = Field(default=0.0001, alias="computationSeconds")
    # Optional metrics are compared only when the case declares a tolerance, so
    # older cases keep their content hash and their A/B outcome.
    path_deviation_rms_mm: Nonnegative | None = Field(default=None, alias="pathDeviationRmsMm")
    path_deviation_p99_mm: Nonnegative | None = Field(default=None, alias="pathDeviationP99Mm")
    jerk_mm_s3: Nonnegative | None = Field(default=None, alias="jerkMmS3")


class BenchmarkArc(AxiomModel):
    """Marks one referencePath segment as an exact arc in the XY plane (G17)."""

    segment_index: Annotated[StrictInt, Field(ge=0)] = Field(alias="segmentIndex")
    center_mm: tuple[Coordinate, Coordinate] = Field(alias="centerMm")
    direction: Literal["cw", "ccw"]


class CncBenchmarkCase(AxiomModel):
    schema_id: Literal["axiom.cnc-benchmark-case@1"] = Field(
        default="axiom.cnc-benchmark-case@1", alias="schemaId"
    )
    case_id: str = Field(alias="caseId", min_length=1, max_length=200)
    coordinate_frame: str = Field(alias="coordinateFrame", min_length=1, max_length=200)
    unit: Literal["mm"]
    sample_period_seconds: Period = Field(alias="samplePeriodSeconds")
    reference_path: tuple[Point, ...] = Field(alias="referencePath", min_length=2, max_length=10_000)
    reference_arcs: tuple[BenchmarkArc, ...] | None = Field(default=None, alias="referenceArcs", max_length=10_000)
    programmed_feed_mm_min: Positive | None = Field(default=None, alias="programmedFeedMmMin")
    axis_limits: tuple[BenchmarkAxisLimits, BenchmarkAxisLimits, BenchmarkAxisLimits] = Field(alias="axisLimits")
    maximum_path_deviation_mm: Nonnegative = Field(alias="maximumPathDeviationMm")
    maximum_endpoint_error_mm: Nonnegative = Field(alias="maximumEndpointErrorMm")
    comparison_tolerances: BenchmarkTolerances = Field(default_factory=BenchmarkTolerances, alias="comparisonTolerances")

    @model_validator(mode="after")
    def validate_path(self) -> CncBenchmarkCase:
        if tuple(item.axis for item in self.axis_limits) != AXES:
            raise ValueError("axisLimits must be ordered X, Y, Z")
        if all(point == self.reference_path[0] for point in self.reference_path):
            raise ValueError("referencePath must contain a nonzero segment")
        seen: set[int] = set()
        for arc in self.reference_arcs or ():
            if arc.segment_index >= len(self.reference_path) - 1 or arc.segment_index in seen:
                raise ValueError("referenceArcs segmentIndex must name a distinct referencePath segment")
            seen.add(arc.segment_index)
            start, end = self.reference_path[arc.segment_index], self.reference_path[arc.segment_index + 1]
            if start[2] != end[2]:
                raise ValueError("referenceArcs must lie in one XY plane; helical arcs are not supported")
            if start == end:
                raise ValueError("referenceArcs cannot be full circles; split them into two arcs")
            radii = [math.hypot(point[0] - arc.center_mm[0], point[1] - arc.center_mm[1]) for point in (start, end)]
            if min(radii) <= 0 or abs(radii[0] - radii[1]) > ARC_RADIUS_RELATIVE_TOLERANCE * max(1.0, max(radii)):
                raise ValueError("referenceArcs start and end must be equidistant from a distinct centerMm")
        return self


class BenchmarkSample(AxiomModel):
    sample_index: Annotated[StrictInt, Field(ge=0)] = Field(alias="sampleIndex")
    t: Annotated[Number, Field(ge=0, le=100_000)]
    position_mm: Point = Field(alias="positionMm")


class BenchmarkTiming(AxiomModel):
    elapsed_seconds: Nonnegative = Field(alias="elapsedSeconds")
    environment_id: str = Field(alias="environmentId", min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=200)


class CncAlgorithmExport(AxiomModel):
    schema_id: Literal["axiom.cnc-algorithm-export@1"] = Field(
        default="axiom.cnc-algorithm-export@1", alias="schemaId"
    )
    algorithm_id: str = Field(alias="algorithmId", min_length=1, max_length=200)
    algorithm_version: str = Field(alias="algorithmVersion", min_length=1, max_length=200)
    source_kind: Literal["algorithm-export", "controller-trace", "synthetic-example"] = Field(alias="sourceKind")
    case_content_hash: str = Field(alias="caseContentHash", pattern=r"^[0-9a-f]{64}$")
    coordinate_frame: str = Field(alias="coordinateFrame", min_length=1, max_length=200)
    unit: Literal["mm"]
    sample_period_seconds: Period = Field(alias="samplePeriodSeconds")
    samples: tuple[BenchmarkSample, ...] = Field(min_length=2, max_length=100_000)
    computation: BenchmarkTiming | None = None

    @model_validator(mode="after")
    def uniform_samples(self) -> CncAlgorithmExport:
        for index, sample in enumerate(self.samples):
            if sample.sample_index != index:
                raise ValueError("sampleIndex must start at zero and be contiguous")
            expected = index * self.sample_period_seconds
            tolerance = max(1e-12, self.sample_period_seconds * 1e-6)
            if abs(sample.t - expected) > tolerance:
                raise ValueError("t must start at zero and follow samplePeriodSeconds; no resampling is performed")
        return self


class CncBenchmarkRequest(AxiomModel):
    case: CncBenchmarkCase
    baseline: CncAlgorithmExport
    candidate: CncAlgorithmExport

    @model_validator(mode="after")
    def matching_conditions(self) -> CncBenchmarkRequest:
        expected_hash = benchmark_case_hash(self.case)
        for role, run in (("baseline", self.baseline), ("candidate", self.candidate)):
            if run.case_content_hash != expected_hash:
                raise ValueError(f"{role}.caseContentHash does not identify the supplied case")
            if run.coordinate_frame != self.case.coordinate_frame:
                raise ValueError(f"{role}.coordinateFrame differs from the case")
            if run.sample_period_seconds != self.case.sample_period_seconds:
                raise ValueError(f"{role}.samplePeriodSeconds differs from the case")
        pair_count = (len(self.baseline.samples) + len(self.candidate.samples)) * (len(self.case.reference_path) - 1)
        if pair_count > MAX_DISTANCE_PAIRS:
            raise ValueError(f"comparison exceeds the {MAX_DISTANCE_PAIRS} point/segment pair budget; split the case")
        return self


class BenchmarkLocation(AxiomModel):
    sample_index: int = Field(alias="sampleIndex")
    t: float
    axis: str | None = None
    reference_segment_index: int | None = Field(default=None, alias="referenceSegmentIndex")


class BenchmarkMetric(AxiomModel):
    value: float | None
    unit: str
    location: BenchmarkLocation | None = None


class BenchmarkCheck(AxiomModel):
    check_id: str = Field(alias="checkId")
    status: Literal["WithinLimit", "Violated", "InsufficientSamples"]
    value: float | None
    limit: float
    unit: str
    location: BenchmarkLocation | None = None


class BenchmarkRunAnalysis(AxiomModel):
    algorithm_id: str = Field(alias="algorithmId")
    algorithm_version: str = Field(alias="algorithmVersion")
    source_kind: str = Field(alias="sourceKind")
    export_content_hash: str = Field(alias="exportContentHash")
    sample_count: int = Field(alias="sampleCount")
    metrics: dict[str, BenchmarkMetric]
    checks: tuple[BenchmarkCheck, ...]


class BenchmarkDifference(AxiomModel):
    metric_id: str = Field(alias="metricId")
    baseline: float | None
    candidate: float | None
    delta: float | None
    unit: str
    tolerance: float
    status: Literal["Improved", "Regressed", "WithinTolerance", "NotComparable"]
    reason: str | None = None


class CncBenchmarkReport(AxiomModel):
    schema_id: Literal["axiom.cnc-benchmark-report@1"] = Field(default="axiom.cnc-benchmark-report@1", alias="schemaId")
    evaluator_version: Literal["cnc-sampled-comparison@1"] = Field(default="cnc-sampled-comparison@1", alias="evaluatorVersion")
    case_id: str = Field(alias="caseId")
    case_content_hash: str = Field(alias="caseContentHash")
    scope: Literal["sampled-xyz-command"] = BENCHMARK_SCOPE
    unchecked_properties: tuple[str, ...] = Field(default=UNCHECKED_PROPERTIES, alias="uncheckedProperties")
    baseline: BenchmarkRunAnalysis
    candidate: BenchmarkRunAnalysis
    differences: tuple[BenchmarkDifference, ...]
    outcome: Literal["Improved", "Regressed", "Tradeoff", "WithinTolerance", "CandidateViolatesLimits", "Inconclusive"]
    reasons: tuple[str, ...]
    report_content_hash: str = Field(alias="reportContentHash")


def _hash(model: AxiomModel | dict[str, Any]) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True) if isinstance(model, AxiomModel) else model
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def benchmark_case_hash(case: CncBenchmarkCase | Mapping[str, Any]) -> str:
    resolved = case if isinstance(case, CncBenchmarkCase) else CncBenchmarkCase.model_validate(case)
    return _hash(resolved)


def _arc_geometry(path: np.ndarray, arc: BenchmarkArc) -> tuple[np.ndarray, float, float, float]:
    """Center, radius, start angle and signed sweep (ccw positive, never zero)."""
    start, end = path[arc.segment_index], path[arc.segment_index + 1]
    center = np.asarray(arc.center_mm, dtype=float)
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = (a1 - a0) % (2 * math.pi) if arc.direction == "ccw" else -((a0 - a1) % (2 * math.pi))
    return center, float(np.hypot(*(start[:2] - center))), a0, sweep


def _arc_squared_distances(points: np.ndarray, path: np.ndarray, arc: BenchmarkArc) -> np.ndarray:
    center, radius, a0, sweep = _arc_geometry(path, arc)
    relative = points[:, :2] - center
    radial = np.hypot(relative[:, 0], relative[:, 1])
    offset = (np.arctan2(relative[:, 1], relative[:, 0]) - a0) * math.copysign(1.0, sweep) % (2 * math.pi)
    dz = points[:, 2] - path[arc.segment_index][2]
    on_arc = (offset <= abs(sweep)) | (radial == 0)
    endpoints = np.minimum(
        np.sum((points - path[arc.segment_index]) ** 2, axis=1),
        np.sum((points - path[arc.segment_index + 1]) ** 2, axis=1),
    )
    return np.where(on_arc, (radial - radius) ** 2 + dz * dz, endpoints)


def _path_deviations(positions: np.ndarray, path: np.ndarray, arcs: tuple[BenchmarkArc, ...] = ()) -> tuple[np.ndarray, np.ndarray]:
    """Exact point-to-path distance (line segments and XY arcs), evaluated in bounded chunks."""
    starts = path[:-1]
    vectors = path[1:] - starts
    squared_lengths = np.sum(vectors * vectors, axis=1)
    denominators = np.where(squared_lengths > 0, squared_lengths, 1.0)
    errors = np.empty(len(positions))
    segments = np.empty(len(positions), dtype=np.int64)
    for start in range(0, len(positions), 64):
        points = positions[start:start + 64]
        relative = points[:, None, :] - starts
        progress = np.clip(np.sum(relative * vectors, axis=2) / denominators, 0.0, 1.0)
        residual = relative - progress[:, :, None] * vectors
        distances = np.sum(residual * residual, axis=2)
        for arc in arcs:
            distances[:, arc.segment_index] = _arc_squared_distances(points, path, arc)
        nearest = np.argmin(distances, axis=1)
        segments[start:start + len(points)] = nearest
        errors[start:start + len(points)] = np.sqrt(distances[np.arange(len(points)), nearest])
    return errors, segments


def _segment_ends(path: np.ndarray, arcs: Mapping[int, BenchmarkArc]) -> list[tuple[int, float, np.ndarray, np.ndarray]]:
    """(index, length, start tangent, end tangent) of every nonzero segment."""
    result = []
    for index in range(len(path) - 1):
        arc = arcs.get(index)
        if arc is None:
            vector = path[index + 1] - path[index]
            length = float(np.linalg.norm(vector))
            if length > 0:
                result.append((index, length, vector / length, vector / length))
            continue
        _, radius, a0, sweep = _arc_geometry(path, arc)
        sign = math.copysign(1.0, sweep)
        tangent = lambda angle: np.array([-math.sin(angle) * sign, math.cos(angle) * sign, 0.0])  # noqa: E731
        result.append((index, radius * abs(sweep), tangent(a0), tangent(a0 + sweep)))
    return result


def reference_path_length_mm(case: CncBenchmarkCase) -> float:
    path = np.asarray(case.reference_path, dtype=float)
    return sum(length for _, length, _, _ in _segment_ends(path, {arc.segment_index: arc for arc in case.reference_arcs or ()}))


def _reference_corners(case: CncBenchmarkCase) -> list[tuple[int, float]]:
    """Path vertices (by referencePath index) whose tangent turns by at least CORNER_ANGLE_DEGREES."""
    path = np.asarray(case.reference_path, dtype=float)
    ends = _segment_ends(path, {arc.segment_index: arc for arc in case.reference_arcs or ()})
    corners = []
    for (_, _, _, before), (index, _, after, _) in zip(ends, ends[1:]):
        angle = math.degrees(math.acos(float(np.clip(np.dot(before, after), -1.0, 1.0))))
        if angle >= CORNER_ANGLE_DEGREES:
            corners.append((index, angle))
    return corners


def _analyse(case: CncBenchmarkCase, run: CncAlgorithmExport) -> BenchmarkRunAnalysis:
    positions = np.asarray([sample.position_mm for sample in run.samples], dtype=float)
    times = np.asarray([sample.t for sample in run.samples], dtype=float)
    path = np.asarray(case.reference_path, dtype=float)
    checks: list[BenchmarkCheck] = []

    def location(index: int, axis: str | None = None, segment: int | None = None) -> BenchmarkLocation:
        return BenchmarkLocation(sampleIndex=index, t=float(times[index]), axis=axis, referenceSegmentIndex=segment)

    def check(name: str, metric: BenchmarkMetric, limit: float) -> None:
        status = "InsufficientSamples" if metric.value is None else "Violated" if metric.value > limit else "WithinLimit"
        checks.append(BenchmarkCheck(checkId=name, status=status, value=metric.value, limit=limit, unit=metric.unit, location=metric.location))

    errors, nearest_segments = _path_deviations(positions, path, case.reference_arcs or ())
    index = int(np.argmax(errors))
    metrics = {
        "durationSeconds": BenchmarkMetric(value=float(times[-1]), unit="s"),
        "sampledPathDeviationMaxMm": BenchmarkMetric(value=float(errors[index]), unit="mm", location=location(index, segment=int(nearest_segments[index]))),
        "sampledPathDeviationRmsMm": BenchmarkMetric(value=float(np.sqrt(np.mean(errors * errors))), unit="mm"),
        "sampledPathDeviationP95Mm": BenchmarkMetric(value=float(np.quantile(errors, 0.95)), unit="mm"),
        "sampledPathDeviationP99Mm": BenchmarkMetric(value=float(np.quantile(errors, 0.99)), unit="mm"),
    }
    # Path speed at the sample nearest each reference corner (central difference).
    corner_speed = BenchmarkMetric(value=None, unit="mm/s")
    for vertex, _ in _reference_corners(case):
        nearest = int(np.argmin(np.sum((positions - path[vertex]) ** 2, axis=1)))
        left, right = max(nearest - 1, 0), min(nearest + 1, len(positions) - 1)
        speed = float(np.linalg.norm(positions[right] - positions[left]) / ((right - left) * case.sample_period_seconds))
        if corner_speed.value is None or speed < corner_speed.value:
            corner_speed = BenchmarkMetric(value=speed, unit="mm/s", location=location(nearest, segment=vertex))
    metrics["cornerSpeedMinMmS"] = corner_speed
    feed_utilization = None
    if case.programmed_feed_mm_min is not None and times[-1] > 0:
        feed_utilization = reference_path_length_mm(case) / (times[-1] * case.programmed_feed_mm_min / 60.0)
    metrics["feedUtilization"] = BenchmarkMetric(value=feed_utilization, unit="ratio")
    endpoint_errors = (math.dist(run.samples[0].position_mm, case.reference_path[0]), math.dist(run.samples[-1].position_mm, case.reference_path[-1]))
    endpoint = 0 if endpoint_errors[0] >= endpoint_errors[1] else len(times) - 1
    metrics["endpointErrorMaxMm"] = BenchmarkMetric(value=max(endpoint_errors), unit="mm", location=location(endpoint))
    check("sampled-path-deviation", metrics["sampledPathDeviationMaxMm"], case.maximum_path_deviation_mm)
    check("endpoints", metrics["endpointErrorMaxMm"], case.maximum_endpoint_error_mm)

    for axis_index, limits in enumerate(case.axis_limits):
        excess = np.maximum(limits.minimum_position_mm - positions[:, axis_index], positions[:, axis_index] - limits.maximum_position_mm)
        index = int(np.argmax(excess))
        check(f"{limits.axis}.position-range", BenchmarkMetric(value=max(0.0, float(excess[index])), unit="mm", location=location(index, limits.axis)), 0.0)

    # All operators use the declared fixed command period, after validating the
    # supplied timestamps. kth differences are located at their right endpoint.
    differences = positions
    for order, (name, unit, limit_field) in enumerate((
        ("Velocity", "mm/s", "maximum_velocity_mm_s"),
        ("Acceleration", "mm/s^2", "maximum_acceleration_mm_s2"),
        ("Jerk", "mm/s^3", "maximum_jerk_mm_s3"),
    ), 1):
        differences = np.diff(differences, axis=0) / case.sample_period_seconds
        global_metric = BenchmarkMetric(value=None, unit=unit)
        for axis_index, limits in enumerate(case.axis_limits):
            metric = BenchmarkMetric(value=None, unit=unit)
            if len(differences):
                index = int(np.argmax(np.abs(differences[:, axis_index])))
                metric = BenchmarkMetric(value=float(abs(differences[index, axis_index])), unit=unit, location=location(index + order, limits.axis))
                if global_metric.value is None or metric.value > global_metric.value:
                    global_metric = metric
            check(f"{limits.axis}.discrete-{name.lower()}", metric, getattr(limits, limit_field))
        metrics[f"discrete{name}Max"] = global_metric
    magnitudes = np.linalg.norm(differences, axis=1)
    metrics["discreteJerkRms"] = BenchmarkMetric(value=float(np.sqrt(np.mean(magnitudes * magnitudes))) if len(magnitudes) else None, unit="mm/s^3")
    metrics["computationSeconds"] = BenchmarkMetric(value=run.computation.elapsed_seconds if run.computation else None, unit="s")
    return BenchmarkRunAnalysis(algorithmId=run.algorithm_id, algorithmVersion=run.algorithm_version, sourceKind=run.source_kind, exportContentHash=_hash(run), sampleCount=len(run.samples), metrics=metrics, checks=tuple(checks))


def compare_cnc_exports(payload: CncBenchmarkRequest | Mapping[str, Any]) -> CncBenchmarkReport:
    # Revalidate model instances too: callers may use model_copy/model_construct.
    request = CncBenchmarkRequest.model_validate(payload.model_dump(mode="json", by_alias=True) if isinstance(payload, CncBenchmarkRequest) else payload)
    baseline, candidate = (_analyse(request.case, run) for run in (request.baseline, request.candidate))
    tolerances = request.case.comparison_tolerances
    differences: list[BenchmarkDifference] = []
    compared = [("durationSeconds", tolerances.duration_seconds), ("sampledPathDeviationMaxMm", tolerances.path_deviation_mm)]
    compared += [
        (name, tolerance)
        for name, tolerance in (
            ("sampledPathDeviationRmsMm", tolerances.path_deviation_rms_mm),
            ("sampledPathDeviationP99Mm", tolerances.path_deviation_p99_mm),
            ("discreteJerkMax", tolerances.jerk_mm_s3),
        )
        if tolerance is not None
    ]
    compared.append(("computationSeconds", tolerances.computation_seconds))
    for name, tolerance in compared:
        left, right = baseline.metrics[name], candidate.metrics[name]
        reason = None
        if left.value is None or right.value is None:
            reason = "Both exports must include this measurement"
        elif name == "computationSeconds":
            a, b = request.baseline.computation, request.candidate.computation
            if a is None or b is None or (a.environment_id, a.method) != (b.environment_id, b.method):
                reason = "Timing environment and measurement method must match"
        delta = right.value - left.value if reason is None and left.value is not None and right.value is not None else None
        status = "NotComparable" if delta is None else "Regressed" if delta > tolerance else "Improved" if delta < -tolerance else "WithinTolerance"
        differences.append(BenchmarkDifference(metricId=name, baseline=left.value, candidate=right.value, delta=delta, unit=left.unit, tolerance=tolerance, status=status, reason=reason))

    reasons: list[str] = []
    if any(item.status == "Violated" for item in candidate.checks):
        outcome = "CandidateViolatesLimits"
        reasons.append("Candidate violates one or more sampled-command limits")
    elif any(item.status != "WithinLimit" for item in (*baseline.checks, *candidate.checks)):
        outcome = "Inconclusive"
        reasons.append("A/B quality comparison requires a valid baseline and enough samples for every requested check")
    elif request.baseline.source_kind != request.candidate.source_kind:
        outcome = "Inconclusive"
        reasons.append("Synthetic examples and algorithm exports cannot establish one A/B result")
    else:
        statuses = {item.status for item in differences}
        outcome = "Tradeoff" if {"Improved", "Regressed"} <= statuses else "Regressed" if "Regressed" in statuses else "Improved" if "Improved" in statuses else "WithinTolerance"
        reasons.append("Lower duration, sampled path deviation and comparable reported computation time are preferred; no weighted score is used")
        if len(compared) > 3:
            reasons.append("Case-declared tolerances also compare " + ", ".join(name for name, _ in compared[2:-1]) + "; lower is preferred")
    reasons.append("Discrete V/A/J differences do not certify continuous velocity, acceleration or jerk")
    reasons.append("Computation timing is producer-reported; a single observation does not establish statistical significance")
    if request.baseline.source_kind == "synthetic-example" or request.candidate.source_kind == "synthetic-example":
        reasons.append("Synthetic example data: this report is not evidence about a production algorithm")
    report = CncBenchmarkReport(caseId=request.case.case_id, caseContentHash=benchmark_case_hash(request.case), baseline=baseline, candidate=candidate, differences=tuple(differences), outcome=outcome, reasons=tuple(reasons), reportContentHash="")
    content = report.model_dump(mode="json", by_alias=True, exclude_none=True)
    content.pop("reportContentHash")
    return report.model_copy(update={"report_content_hash": _hash(content)})


def cnc_benchmark_example() -> CncBenchmarkRequest:
    """A small declared synthetic regression; never relabel as real evidence."""
    case = CncBenchmarkCase(caseId="example.line-regression", coordinateFrame="workpiece", unit="mm", samplePeriodSeconds=0.01, referencePath=((0, 0, 0), (1, 0, 0)), axisLimits=tuple(BenchmarkAxisLimits(axis=axis, minimumPositionMm=-10, maximumPositionMm=10, maximumVelocityMmS=100, maximumAccelerationMmS2=10_000, maximumJerkMmS3=1_000_000) for axis in AXES), maximumPathDeviationMm=0.03, maximumEndpointErrorMm=0.001)
    runs = []
    for role in ("baseline", "candidate"):
        runs.append(CncAlgorithmExport(algorithmId="example.planner", algorithmVersion=role, sourceKind="synthetic-example", caseContentHash=benchmark_case_hash(case), coordinateFrame=case.coordinate_frame, unit="mm", samplePeriodSeconds=case.sample_period_seconds, samples=tuple(BenchmarkSample(sampleIndex=index, t=index * 0.01, positionMm=(index / 10, 0.08 if role == "candidate" and index == 5 else 0, 0)) for index in range(11))))
    return CncBenchmarkRequest(case=case, baseline=runs[0], candidate=runs[1])


_METRIC_LABELS = {
    "durationSeconds": "加工时间",
    "sampledPathDeviationMaxMm": "最大轮廓误差",
    "sampledPathDeviationRmsMm": "RMS 轮廓误差",
    "sampledPathDeviationP95Mm": "P95 轮廓误差",
    "sampledPathDeviationP99Mm": "P99 轮廓误差",
    "endpointErrorMaxMm": "端点误差",
    "discreteVelocityMax": "最大轴速度",
    "discreteAccelerationMax": "最大轴加速度",
    "discreteJerkMax": "最大轴 Jerk",
    "discreteJerkRms": "RMS Jerk",
    "cornerSpeedMinMmS": "最低拐角速度",
    "feedUtilization": "进给利用率",
    "computationSeconds": "计算耗时",
}
_STATUS_LABELS = {"Improved": "改善", "Regressed": "退化", "WithinTolerance": "容差内", "NotComparable": "不可比"}
_OUTCOME_LABELS = {
    "Improved": "改善",
    "Regressed": "退化",
    "Tradeoff": "取舍（有改善也有退化）",
    "WithinTolerance": "无显著差异",
    "CandidateViolatesLimits": "候选版本超限",
    "Inconclusive": "无法下结论",
}


def _cell(value: float | None) -> str:
    # Values below 1 pm are floating-point noise for a millimetre-scale report.
    return "-" if value is None else "0" if abs(value) < 1e-9 else f"{value:.6g}"


def _pad(text: str, width: int, *, right: bool = False) -> str:
    """Pad by terminal display width (CJK characters occupy two columns)."""
    shown = sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)
    fill = " " * max(width - shown, 1 if right else 0)
    return fill + text if right else text + fill


def render_report_table(report: CncBenchmarkReport) -> str:
    """Plain-text A/B table for people; the JSON report remains authoritative."""
    compared = {item.metric_id: item for item in report.differences}
    lines = [
        f"案例 {report.case_id}",
        f"A = {report.baseline.algorithm_id} {report.baseline.algorithm_version}（{report.baseline.sample_count} 个采样）",
        f"B = {report.candidate.algorithm_id} {report.candidate.algorithm_version}（{report.candidate.sample_count} 个采样）",
        "",
        _pad("指标", 16) + _pad("A", 14, right=True) + _pad("B", 14, right=True) + _pad("变化", 24, right=True) + _pad("单位", 10, right=True) + "  判定",
    ]
    for metric_id, label in _METRIC_LABELS.items():
        left, right = report.baseline.metrics.get(metric_id), report.candidate.metrics.get(metric_id)
        if left is None or right is None or (left.value is None and right.value is None):
            continue
        delta = right.value - left.value if left.value is not None and right.value is not None else None
        if delta is not None and abs(delta) < 1e-9:
            delta = 0.0
        change = "-" if delta is None else "0" if delta == 0 else f"{delta:+.6g}"
        if delta and left.value and abs(left.value) >= 1e-9:
            change += f" ({delta / abs(left.value):+.1%})"
        verdict = _STATUS_LABELS[compared[metric_id].status] if metric_id in compared else "仅参考"
        lines.append(_pad(label, 16) + _pad(_cell(left.value), 14, right=True) + _pad(_cell(right.value), 14, right=True) + _pad(change, 24, right=True) + _pad(left.unit, 10, right=True) + f"  {verdict}")
    violations = [check for check in report.candidate.checks if check.status == "Violated"]
    if violations:
        lines += ["", "候选版本超限："]
        lines += [f"  {item.check_id}: {_cell(item.value)} {item.unit} > {_cell(item.limit)}" + (f"（第 {item.location.sample_index} 个采样）" if item.location else "") for item in violations]
    lines += ["", f"结论：{_OUTCOME_LABELS[report.outcome]}"]
    lines += [f"  - {reason}" for reason in report.reasons]
    return "\n".join(lines) + "\n"
