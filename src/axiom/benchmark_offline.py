"""Local, rest-to-rest, single-axis SUT fixtures; never production evidence."""

from __future__ import annotations

import math
import platform
from importlib.metadata import version
from pathlib import Path
from typing import Any, Mapping

from pydantic import Field

from .benchmark import (
    AXES,
    BenchmarkAxisLimits,
    BenchmarkSample,
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncBenchmarkRequest,
    Number,
    _hash,
    benchmark_case_hash,
    compare_cnc_exports,
)
from .models import AxiomModel

RUCKIG_VERSION = "0.12.2"
OFFLINE_CASE_NAMES = ("long", "short", "velocity-boundary")


class RuckigOfflineOptions(AxiomModel):
    limit_scale: Number = Field(default=0.99, gt=0, le=1, alias="limitScale")


def generate_ruckig_export(
    case: CncBenchmarkCase | Mapping[str, Any],
    options: RuckigOfflineOptions = RuckigOfflineOptions(),
) -> tuple[CncAlgorithmExport, dict[str, Any]]:
    options = RuckigOfflineOptions.model_validate(options.model_dump(mode="json", by_alias=True))
    resolved = CncBenchmarkCase.model_validate(
        case.model_dump(mode="json", by_alias=True) if isinstance(case, CncBenchmarkCase) else case
    )
    if resolved.reference_arcs or len(resolved.reference_path) != 2:
        raise ValueError("Ruckig offline adapter accepts two-point single-axis lines only; no intermediate waypoints or cloud API")
    start, target = resolved.reference_path
    moving_axes = [axis for axis in range(3) if start[axis] != target[axis]]
    if len(moving_axes) != 1:
        raise ValueError("Ruckig offline adapter requires exactly one moving axis")
    for point in (start, target):
        if any(not limits.minimum_position_mm <= point[axis] <= limits.maximum_position_mm for axis, limits in enumerate(resolved.axis_limits)):
            raise ValueError("Start and target must lie within the case position limits")
    try:
        import ruckig
    except ImportError as exc:
        raise ValueError('Install the optional local SUT with: python -m pip install -e ".[offline]"') from exc
    if version("ruckig") != RUCKIG_VERSION:
        raise ValueError(f"Offline adapter requires ruckig=={RUCKIG_VERSION}; other versions need separate validation")

    axis = moving_axes[0]
    limits = resolved.axis_limits[axis]
    period = resolved.sample_period_seconds
    parameters = {
        "currentPosition": [start[axis]], "currentVelocity": [0.0], "currentAcceleration": [0.0],
        "targetPosition": [target[axis]], "targetVelocity": [0.0], "targetAcceleration": [0.0],
        "maxVelocity": [limits.maximum_velocity_mm_s * options.limit_scale],
        "maxAcceleration": [limits.maximum_acceleration_mm_s2 * options.limit_scale],
        "maxJerk": [limits.maximum_jerk_mm_s3 * options.limit_scale],
        "limitScale": options.limit_scale,
        "durationDiscretization": "Discrete", "samplePeriodSeconds": period,
        "movingAxis": AXES[axis], "fixedPositionMm": list(start),
    }
    inp = ruckig.InputParameter(1)
    inp.current_position = parameters["currentPosition"]
    inp.current_velocity = parameters["currentVelocity"]
    inp.current_acceleration = parameters["currentAcceleration"]
    inp.target_position = parameters["targetPosition"]
    inp.target_velocity = parameters["targetVelocity"]
    inp.target_acceleration = parameters["targetAcceleration"]
    inp.max_velocity = parameters["maxVelocity"]
    inp.max_acceleration = parameters["maxAcceleration"]
    inp.max_jerk = parameters["maxJerk"]
    inp.duration_discretization = ruckig.DurationDiscretization.Discrete
    trajectory = ruckig.Trajectory(1)
    try:
        result = ruckig.Ruckig(1, period).calculate(inp, trajectory)
    except ruckig.RuckigError as exc:
        raise ValueError(f"Local Ruckig calculation failed: {exc}") from exc
    if result not in (ruckig.Result.Working, ruckig.Result.Finished):
        raise ValueError(f"Local Ruckig calculation failed: {result}")
    duration = trajectory.duration
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Ruckig returned an invalid duration")
    cycles = round(duration / period)
    if abs(duration - cycles * period) > max(1e-12, period * 1e-6):
        raise ValueError("Ruckig duration does not match the fixed sample grid; no resampling is performed")
    if not 3 <= cycles < 100_000:
        raise ValueError("Offline export needs 4..100000 samples; adjust case period or displacement")
    samples = []
    for index in range(cycles + 1):
        position, _, _ = trajectory.at_time(index * period)
        xyz = list(start)
        xyz[axis] = position[0]
        samples.append(BenchmarkSample(sampleIndex=index, t=index * period, positionMm=(xyz[0], xyz[1], xyz[2])))
    export = CncAlgorithmExport(
        algorithmId="ruckig.community.local-rest-to-rest", algorithmVersion=RUCKIG_VERSION,
        sourceKind="offline-sut", caseContentHash=benchmark_case_hash(resolved),
        coordinateFrame=resolved.coordinate_frame, unit="mm", samplePeriodSeconds=period,
        samples=tuple(samples),
    )
    generator_input = {
        "adapterVersion": "ruckig-single-axis@1", "ruckigVersion": RUCKIG_VERSION,
        "caseContentHash": export.case_content_hash, "parameters": parameters,
    }
    manifest = {
        "schemaId": "axiom.offline-sut-manifest@1", "purpose": "evaluator-integration-validation",
        "generatorInput": generator_input, "generatorInputHash": _hash(generator_input),
        "exportContentHash": _hash(export), "trajectoryDurationSeconds": duration,
        "samplePolicy": "Ruckig discrete duration; inclusive uniform grid; no resampling, padding or endpoint snapping",
        "environment": {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine()},
        "uncheckedProperties": ["production-algorithm-quality", "controller-response", "machining-quality"],
    }
    return export, manifest


def offline_cases() -> tuple[CncBenchmarkCase, ...]:
    cases = []
    for name, displacement in zip(OFFLINE_CASE_NAMES, (100.0, 0.001, 1.0), strict=True):
        velocity = 1.0 if name == "velocity-boundary" else 10.0
        axis_limits = [BenchmarkAxisLimits(
            axis=axis, minimumPositionMm=-200, maximumPositionMm=200,
            maximumVelocityMmS=velocity, maximumAccelerationMmS2=100, maximumJerkMmS3=1000,
        ) for axis in AXES]
        cases.append(CncBenchmarkCase(
            caseId=f"offline.ruckig.{name}", coordinateFrame="offline-workpiece", unit="mm",
            samplePeriodSeconds=0.001, referencePath=((0, 0, 0), (displacement, 0, 0)),
            axisLimits=(axis_limits[0], axis_limits[1], axis_limits[2]),
            maximumPathDeviationMm=1e-8, maximumEndpointErrorMm=1e-8,
        ))
    return tuple(cases)


def write_offline_suite(out_dir: Path) -> dict[str, Any]:
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise ValueError("Offline suite output directory must be new or empty; existing evidence will not be overwritten")
    bundles = []
    for case in offline_cases():
        baseline, manifest = generate_ruckig_export(case)
        candidate, repeated_manifest = generate_ruckig_export(case)
        request = CncBenchmarkRequest(case=case, baseline=baseline, candidate=candidate)
        report = compare_cnc_exports(request)
        replay = compare_cnc_exports(request.model_dump(mode="json", by_alias=True, exclude_none=True))
        deterministic = baseline == candidate and manifest == repeated_manifest and report == replay
        bundles.append((case, baseline, candidate, request, report, manifest, deterministic))
    summary = {
        "schemaId": "axiom.offline-sut-suite@1", "purpose": "evaluator-integration-validation",
        "comparisonType": "A/A", "ruckigVersion": RUCKIG_VERSION,
        "passed": all(bundle[-1] and bundle[4].outcome == "WithinTolerance" for bundle in bundles),
        "cases": [{
            "caseId": case.case_id, "outcome": report.outcome, "deterministicReplay": deterministic,
            "caseContentHash": report.case_content_hash, "reportContentHash": report.report_content_hash,
            "generatorInputHash": manifest["generatorInputHash"],
        } for case, _, _, _, report, manifest, deterministic in bundles],
        "limitations": "A/A integration check only; not production, continuous-motion or machining evidence",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for case, baseline, candidate, request, report, manifest, _ in bundles:
        stem = case.case_id.rsplit(".", 1)[-1]
        for role, value in (("case", case), ("baseline", baseline), ("candidate", candidate), ("request", request), ("report", report)):
            (out_dir / f"{stem}.{role}.json").write_text(value.model_dump_json(indent=2, by_alias=True, exclude_none=True) + "\n", encoding="utf-8")
        _write_json(out_dir / f"{stem}.manifest.json", manifest)
    _write_json(out_dir / "summary.json", summary)
    return summary


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    import json

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
