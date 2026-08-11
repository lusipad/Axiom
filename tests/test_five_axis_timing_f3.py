from __future__ import annotations

import hashlib
import json
import math

import pytest

from axiom.five_axis.f2_models import M3CandidateAxisPath
from axiom.five_axis.f3_models import MotionConstraintProfile
from axiom.five_axis.f3_timing import (
    evaluate_continuous_state,
    plan_jerk_feasible_time_law,
    plan_second_order_time_law,
    verify_continuous_trajectory,
)


_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_SLOPE = (20.0, 0.0, 0.0, 0.25, 0.5)


def _canonical_hash(model: object) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)  # type: ignore[attr-defined]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _provenance(source_id: str) -> dict:
    return {"sourceStage": "M2", "sourceId": source_id, "sourceContentId": _HASH_A, "method": "fixture"}


def _path_progress(segment_id: str, progress_id: str) -> dict:
    return {
        "progressId": progress_id,
        "schemaVersion": 1,
        "progressParameter": "sigma",
        "unit": "dimensionless",
        "mappings": [
            {
                "mappingId": f"{progress_id}.map.1",
                "sourceSegmentId": segment_id,
                "sourceLocalStart": 0.0,
                "sourceLocalEnd": 1.0,
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "degenerateKind": "none",
                "provenance": _provenance("m2.geom.1"),
            }
        ],
    }


def _derivatives(order_count: int) -> list[dict]:
    values = {
        0: [0.0, 0.0, 0.0, 0.0, 0.0],
        1: list(_SLOPE),
        2: [0.0, 0.0, 0.0, 0.0, 0.0],
        3: [0.0, 0.0, 0.0, 0.0, 0.0],
    }
    return [{"order": order, "components": values[order]} for order in range(order_count + 1)]


def _regularity_certificate(segment_id: str, node_specs: list[tuple[str, str]]) -> dict:
    max_order = max(3 if continuity == "C3" else 1 for _, continuity in node_specs)
    segment_continuity = "C3" if max_order == 3 else "C1"
    return {
        "certificateId": "m3.reg.1",
        "segmentEvidence": [
            {
                "segmentId": segment_id,
                "continuityClass": segment_continuity,
                "derivatives": _derivatives(3 if segment_continuity == "C3" else 1),
                "verificationMethod": "analytic",
            }
        ],
        "nodeEvidence": [
            {
                "nodeId": node_id,
                "continuityClass": continuity,
                "leftDerivatives": _derivatives(3 if continuity == "C3" else 1),
                "rightDerivatives": _derivatives(3 if continuity == "C3" else 1),
                "verificationMethod": "analytic",
            }
            for node_id, continuity in node_specs
        ],
    }


def _machine_profile_payload() -> dict:
    return {
        "artifactType": "five-axis.machine-profile",
        "schemaVersion": 1,
        "profileId": "five-axis.machine-profile.head-table.demo@1",
        "profileVersion": 1,
        "topology": "head-table",
        "axes": [
            {
                "axisId": "axis.x",
                "axisOrder": 0,
                "jointType": "prismatic",
                "axisSymbol": "X",
                "semanticRole": "linear-x",
                "origin": [0.0, 0.0, 0.0],
                "direction": [1.0, 0.0, 0.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": False,
                "limits": {"lower": -500.0, "upper": 500.0, "unit": "mm"},
            },
            {
                "axisId": "axis.y",
                "axisOrder": 1,
                "jointType": "prismatic",
                "axisSymbol": "Y",
                "semanticRole": "linear-y",
                "parentAxisId": "axis.x",
                "origin": [0.0, 0.0, 0.0],
                "direction": [0.0, 1.0, 0.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": False,
                "limits": {"lower": -400.0, "upper": 400.0, "unit": "mm"},
            },
            {
                "axisId": "axis.z",
                "axisOrder": 2,
                "jointType": "prismatic",
                "axisSymbol": "Z",
                "semanticRole": "linear-z",
                "parentAxisId": "axis.y",
                "origin": [0.0, 0.0, 0.0],
                "direction": [0.0, 0.0, 1.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": False,
                "limits": {"lower": -300.0, "upper": 300.0, "unit": "mm"},
            },
            {
                "axisId": "axis.c",
                "axisOrder": 3,
                "jointType": "revolute",
                "axisSymbol": "C",
                "semanticRole": "workpiece-rotary-primary",
                "origin": [0.0, 0.0, 0.0],
                "direction": [0.0, 0.0, 1.0],
                "installationSide": "workpiece",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": True,
                "limits": {"lower": -3.14159, "upper": 3.14159, "unit": "rad"},
            },
            {
                "axisId": "axis.b",
                "axisOrder": 4,
                "jointType": "revolute",
                "axisSymbol": "B",
                "semanticRole": "tool-rotary-primary",
                "parentAxisId": "axis.z",
                "origin": [0.0, 0.0, 120.0],
                "direction": [0.0, 1.0, 0.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": True,
                "limits": {"lower": -6.28318, "upper": 6.28318, "unit": "rad"},
            },
        ],
        "workpieceFrame": {
            "transformId": "frame.workpiece",
            "translation": [0.0, 0.0, 0.0],
            "rotationQuaternion": [0.0, 0.0, 0.0, 1.0],
        },
        "toolMountFrame": {
            "transformId": "frame.tool",
            "translation": [0.0, 0.0, 100.0],
            "rotationQuaternion": [0.0, 0.0, 0.0, 1.0],
        },
    }


def _m2_payload() -> dict:
    segment_id = "m2.seg.1"
    node_id = "m2.node.1"
    return {
        "artifactType": "five-axis.m2-candidate-task-geometry",
        "schemaVersion": 1,
        "candidateGeometryId": "m2.geom.1",
        "sourceReferencePathId": "m1.path.1",
        "sourceReferencePathContentId": _HASH_A,
        "coordinateContext": {"unit": "mm", "coordinateFrame": "machine.work-envelope@1"},
        "pathProgress": _path_progress(segment_id, "m2.progress.1"),
        "positionSemantics": "continuous",
        "positionSegments": [
            {
                "segmentId": segment_id,
                "segmentType": "line",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "lineage": [
                    {
                        "statementId": "stmt.goto.1",
                        "statementIndex": 0,
                        "line": 1,
                        "column": 1,
                        "sourceText": "GOTO/20,0,0",
                        "sourcePath": "fixture.cl",
                    }
                ],
                "startPoint": [0.0, 0.0, 0.0],
                "endPoint": [20.0, 0.0, 0.0],
            }
        ],
        "orientationSegments": [],
        "nodeEvents": [{"nodeId": node_id, "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": segment_id}],
        "regularityCertificate": {
            "certificateId": "m2.reg.1",
            "segmentEvidence": [
                {
                    "segmentId": segment_id,
                    "continuityClass": "C3",
                    "derivatives": _derivatives(3),
                    "verificationMethod": "analytic",
                }
            ],
            "nodeEvidence": [
                {
                    "nodeId": node_id,
                    "continuityClass": "C3",
                    "leftDerivatives": _derivatives(3),
                    "rightDerivatives": _derivatives(3),
                    "verificationMethod": "analytic",
                }
            ],
        },
        "tolerances": [
            {"toleranceId": "tol.position", "target": "position", "tolerance": {"absolute": 0.01, "unit": "mm"}},
            {"toleranceId": "tol.sigma", "target": "sigma", "tolerance": {"absolute": 1e-6, "unit": "dimensionless"}},
        ],
        "correspondence": {
            "certificateId": "corr.1",
            "sourceGeometryId": "m2.geom.1",
            "targetReferencePathId": "m1.path.1",
            "policy": {
                "strategyId": "five-axis.correspondence.monotone-minimax@1",
                "allowedSourceInterval": [0.0, 1.0],
                "allowedTargetInterval": [0.0, 1.0],
                "objective": "minimize-maximum-deviation",
                "deterministicTieBreak": "earliest-target-sigma",
                "numericTolerance": {"absolute": 1e-6, "unit": "mm"},
            },
            "canonicalNodes": [
                {"pathRole": "source", "nodeId": node_id, "sigma": 0.0, "segmentId": segment_id},
                {"pathRole": "target", "nodeId": "m1.node.1", "sigma": 0.0, "segmentId": "m1.seg.1"},
            ],
            "allowedSourceIntervals": [{"sourceSegmentId": segment_id, "allowedTargetIntervals": [[0.0, 1.0]]}],
            "selectedNodeMapping": [{"sourceNodeId": node_id, "targetNodeId": "m1.node.1"}],
            "intervals": [
                {
                    "intervalId": "corr.interval.1",
                    "sourceSigmaStart": 0.0,
                    "sourceSigmaEnd": 1.0,
                    "targetSigmaStart": 0.0,
                    "targetSigmaEnd": 1.0,
                    "sourceSegmentId": segment_id,
                    "targetSegmentId": "m1.seg.1",
                    "correspondenceStatus": "matched",
                    "provenance": _provenance("m2.geom.1"),
                }
            ],
            "primaryObjectiveLower": 0.0,
            "primaryObjectiveUpper": 0.0,
            "objectiveDomain": "continuous",
            "tieBreakObjective": "earliest-target-sigma",
            "numericTolerance": {"absolute": 1e-6, "unit": "mm"},
            "solverVersion": "solver@1",
            "evidenceLevel": "machine-replayable",
        },
        "provenance": [_provenance("m2.geom.1")],
    }


def _m3_payload(
    *,
    event_specs: list[dict] | None = None,
    node_continuities: dict[str, str] | None = None,
) -> dict:
    events = event_specs or [{"nodeId": "m3.node.0", "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": "m3.seg.1"}]
    continuities = node_continuities or {item["nodeId"]: "C3" for item in events}
    node_specs = [(item["nodeId"], continuities[item["nodeId"]]) for item in events]
    return {
        "artifactType": "five-axis.m3-candidate-axis-path",
        "schemaVersion": 1,
        "axisPathId": "m3.path.1",
        "sourceCandidateGeometry": _m2_payload(),
        "sourceCandidateGeometryContentId": _HASH_B,
        "machineProfile": _machine_profile_payload(),
        "machineProfileContentId": _HASH_C,
        "pathProgress": _path_progress("m3.seg.1", "m3.progress.1"),
        "ikSolutions": [
            {
                "solutionId": "ik.0",
                "sigma": 0.0,
                "branchId": "branch.1",
                "jointValues": [0.0, 0.0, 0.0, 0.0, 0.0],
                "wrapState": [{"axisId": "axis.c", "turns": 0}, {"axisId": "axis.b", "turns": 0}],
                "axisLimitState": [{"axisId": axis_id, "status": "within", "distanceToLower": 10.0, "distanceToUpper": 10.0} for axis_id in ("axis.x", "axis.y", "axis.z", "axis.c", "axis.b")],
                "residuals": [
                    {"metricId": "five-axis.position-residual.max@1", "value": 1e-6, "unit": "mm"},
                    {"metricId": "five-axis.orientation-residual.max@1", "value": 1e-6, "unit": "rad"},
                ],
                "singularity": {"status": "regular", "conditioningMetric": 5.0, "minimumSingularValue": 0.2},
                "withinLimits": True,
            },
            {
                "solutionId": "ik.1",
                "sigma": 1.0,
                "branchId": "branch.1",
                "jointValues": [20.0, 0.0, 0.0, 0.25, 0.5],
                "wrapState": [{"axisId": "axis.c", "turns": 0}, {"axisId": "axis.b", "turns": 0}],
                "axisLimitState": [{"axisId": axis_id, "status": "within", "distanceToLower": 10.0, "distanceToUpper": 10.0} for axis_id in ("axis.x", "axis.y", "axis.z", "axis.c", "axis.b")],
                "residuals": [
                    {"metricId": "five-axis.position-residual.max@1", "value": 1e-6, "unit": "mm"},
                    {"metricId": "five-axis.orientation-residual.max@1", "value": 1e-6, "unit": "rad"},
                ],
                "singularity": {"status": "regular", "conditioningMetric": 5.0, "minimumSingularValue": 0.2},
                "withinLimits": True,
            },
        ],
        "branchGraph": {
            "graphId": "graph.1",
            "rootBranchIds": ["branch.1"],
            "branches": [{"branchId": "branch.1", "sigmaStart": 0.0, "sigmaEnd": 1.0, "solutionIds": ["ik.0", "ik.1"], "status": "active"}],
            "transitions": [],
        },
        "jointSegments": [
            {
                "segmentId": "m3.seg.1",
                "branchId": "branch.1",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "startSolutionId": "ik.0",
                "endSolutionId": "ik.1",
                "continuityClass": "C3",
                "interpolation": "linear",
                "coefficientBasis": "local-power@1",
                "coefficients": [[0.0, 0.0, 0.0, 0.0, 0.0], list(_SLOPE)],
            }
        ],
        "nodeEvents": events,
        "regularityCertificate": _regularity_certificate("m3.seg.1", node_specs),
        "kinematicsCertificate": {
            "certificateId": "kin.cert.1",
            "machineProfileId": "five-axis.machine-profile.head-table.demo@1",
            "machineProfileContentId": _HASH_C,
            "sourceCandidateGeometryId": "m2.geom.1",
            "sourceCandidateGeometryContentId": _HASH_B,
            "branchGraphId": "graph.1",
            "solverId": "five-axis.ik-solver.demo@1",
            "solverVersion": "ik-demo-2026-08-11",
            "evidenceLevel": "Exact",
            "continuousMethod": "five-axis.constant-axis-linear-lift@1",
            "claimScope": "selected-continuous-lift",
            "selectedBranchId": "branch.1",
            "intervalCount": 1,
            "positionResidualUpperBound": 1e-6,
            "orientationResidualUpperBound": 1e-6,
            "axisLimitNormalizedMarginLowerBound": 0.1,
            "minimumSingularValueLowerBound": 0.2,
            "singularityHandling": "regular-only",
            "policyIds": ["five-axis.ik-branch-selection@1"],
            "numericEnvironment": {"python": "3.14", "numpy": "2"},
            "positionTolerance": {"toleranceId": "kin.pos", "target": "position", "tolerance": {"absolute": 1e-5, "unit": "mm"}},
            "orientationTolerance": {"toleranceId": "kin.ori", "target": "orientation", "tolerance": {"absolute": 1e-5, "unit": "rad"}},
            "provenance": [_provenance("m2.geom.1")],
        },
        "provenance": [_provenance("m2.geom.1")],
    }


def _build_axis_path(
    *,
    event_specs: list[dict] | None = None,
    node_continuities: dict[str, str] | None = None,
) -> M3CandidateAxisPath:
    return M3CandidateAxisPath.model_validate(
        _m3_payload(event_specs=event_specs, node_continuities=node_continuities)
    )


def _build_profile(
    axis_path: M3CandidateAxisPath,
    *,
    x_velocity: float,
    x_acceleration: float,
    x_jerk: float | None = None,
    node_constraints: list[dict] | None = None,
) -> MotionConstraintProfile:
    constraints = []
    for axis in axis_path.machine_profile.axes:
        constraint = {
            "axisId": axis.axis_id,
            "unit": axis.limits.unit,
            "maximumVelocity": 1_000.0 if axis.axis_id != "axis.x" else x_velocity,
            "maximumAcceleration": 1_000.0 if axis.axis_id != "axis.x" else x_acceleration,
        }
        if x_jerk is not None:
            constraint["maximumJerk"] = 10_000.0 if axis.axis_id != "axis.x" else x_jerk
        constraints.append(constraint)
    return MotionConstraintProfile.model_validate(
        {
            "artifactType": "five-axis.motion-constraint-profile",
            "schemaId": "five-axis.motion-constraint-profile@1",
            "schemaVersion": 1,
            "profileId": "five-axis.motion-constraint.demo@1",
            "machineProfileId": axis_path.machine_profile.profile_id,
            "machineProfileContentId": axis_path.machine_profile_content_id,
            "axisConstraints": constraints,
            "startBoundary": {"sigmaVelocity": 0.0, "sigmaAcceleration": 0.0},
            "endBoundary": {"sigmaVelocity": 0.0, "sigmaAcceleration": 0.0},
            "nodeConstraints": node_constraints or [{"nodeId": axis_path.node_events[0].node_id, "sigma": 0.0, "boundaryMode": "allow-continuous"}],
            "policyIds": ["five-axis.motion-constraint-profile.strict@1"],
            "provenance": [_provenance("m2.geom.1")],
        }
    )


def test_plan_second_order_returns_proven_optimal_triangular_and_trapezoidal() -> None:
    axis_path = _build_axis_path()

    triangular_profile = _build_profile(axis_path, x_velocity=200.0, x_acceleration=80.0)
    triangular = plan_second_order_time_law(axis_path, triangular_profile)

    assert triangular.verification.overall_status == "Supported"
    assert triangular.verification.optimality.classification == "ProvenOptimal"
    assert triangular.spans[0].time_law.law_kind == "triangular"
    assert triangular.spans[0].time_law.duration_seconds == pytest.approx(1.0)
    state = evaluate_continuous_state(triangular, 0.5)
    assert state.sigma == pytest.approx(0.5)
    assert state.joint_velocity[0] == pytest.approx(40.0)
    assert evaluate_continuous_state(triangular, 0.0).sigma_acceleration == pytest.approx(0.0)
    assert evaluate_continuous_state(triangular, triangular.verification.total_duration_seconds).sigma_acceleration == pytest.approx(0.0)

    trapezoidal_profile = _build_profile(axis_path, x_velocity=20.0, x_acceleration=80.0)
    trapezoidal = plan_second_order_time_law(axis_path, trapezoidal_profile)

    assert trapezoidal.spans[0].time_law.law_kind == "trapezoidal"
    assert trapezoidal.spans[0].time_law.duration_seconds == pytest.approx(1.25)
    assert verify_continuous_trajectory(trapezoidal).overall_status == "Supported"


def test_plan_jerk_feasible_uses_certified_smoothstep_constants_and_chain_rule() -> None:
    axis_path = _build_axis_path()
    profile = _build_profile(axis_path, x_velocity=43.75, x_acceleration=525.0, x_jerk=4200.0)

    trajectory = plan_jerk_feasible_time_law(axis_path, profile)
    law = trajectory.spans[0].time_law

    assert trajectory.verification.overall_status == "Supported"
    assert trajectory.verification.optimality.classification == "FeasibleOnly"
    assert law.law_kind == "smoothstep7"
    assert law.duration_seconds == pytest.approx(1.0)
    assert law.peak_sigma_velocity == pytest.approx(math.nextafter(35.0 / 16.0, math.inf))
    assert law.peak_sigma_acceleration == pytest.approx(math.nextafter(26.25, math.inf))
    assert law.peak_sigma_jerk == pytest.approx(math.nextafter(210.0, math.inf))
    mid_state = evaluate_continuous_state(trajectory, 0.5)
    assert mid_state.sigma == pytest.approx(0.5)
    assert mid_state.joint_velocity[0] == pytest.approx(43.75)
    assert mid_state.joint_acceleration[0] == pytest.approx(0.0, abs=1e-9)


def test_semantic_mandatory_stop_and_dwell_split_spans() -> None:
    axis_path = _build_axis_path(
        event_specs=[
            {"nodeId": "m3.node.0", "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": "m3.seg.1"},
            {"nodeId": "m3.node.1", "sigma": 0.5, "eventType": "mandatory-stop", "leftSegmentId": "m3.seg.1", "rightSegmentId": "m3.seg.1"},
            {"nodeId": "m3.node.2", "sigma": 0.75, "eventType": "dwell", "leftSegmentId": "m3.seg.1", "rightSegmentId": "m3.seg.1"},
        ]
    )
    profile = _build_profile(
        axis_path,
        x_velocity=200.0,
        x_acceleration=80.0,
        x_jerk=4200.0,
        node_constraints=[
            {"nodeId": "m3.node.0", "sigma": 0.0, "boundaryMode": "allow-continuous"},
            {"nodeId": "m3.node.1", "sigma": 0.5, "boundaryMode": "allow-continuous"},
            {"nodeId": "m3.node.2", "sigma": 0.75, "boundaryMode": "dwell", "dwellSeconds": 0.2},
        ],
    )

    trajectory = plan_second_order_time_law(axis_path, profile)

    assert [span.span_kind for span in trajectory.spans] == ["move", "move", "dwell", "move"]
    dwell = next(span for span in trajectory.spans if span.span_kind == "dwell")
    dwell_state = evaluate_continuous_state(trajectory, dwell.start_time_seconds + 0.1)
    assert dwell_state.sigma == pytest.approx(0.75)
    assert dwell_state.joint_velocity == pytest.approx((0.0, 0.0, 0.0, 0.0, 0.0))
    first_move_end = evaluate_continuous_state(trajectory, trajectory.spans[0].end_time_seconds)
    assert first_move_end.sigma_velocity == pytest.approx(0.0)
    assert first_move_end.sigma_acceleration == pytest.approx(0.0)


def test_collision_violation_is_refuted() -> None:
    axis_path = _build_axis_path(
        event_specs=[
            {"nodeId": "m3.node.0", "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": "m3.seg.1"},
            {"nodeId": "m3.node.1", "sigma": 0.5, "eventType": "collision-violation", "leftSegmentId": "m3.seg.1", "rightSegmentId": "m3.seg.1"},
        ]
    )
    safe_axis_path = _build_axis_path()
    profile = _build_profile(safe_axis_path, x_velocity=200.0, x_acceleration=80.0)
    safe_trajectory = plan_second_order_time_law(safe_axis_path, profile)

    tampered = safe_trajectory.model_copy(
        update={
            "source_axis_path": axis_path,
            "source_axis_path_content_id": _canonical_hash(axis_path),
        },
        deep=True,
    )
    verification = verify_continuous_trajectory(tampered)

    assert verification.overall_status == "Refuted"
    assert any(entry.code == "CollisionViolationRefuted" for entry in verification.error_ledger)


def test_verifier_refutes_tampered_time_law() -> None:
    axis_path = _build_axis_path()
    profile = _build_profile(axis_path, x_velocity=43.75, x_acceleration=525.0, x_jerk=4200.0)
    trajectory = plan_jerk_feasible_time_law(axis_path, profile)

    bad_span = trajectory.spans[0].model_copy(
        update={
            "time_law": trajectory.spans[0].time_law.model_copy(
                update={"duration_seconds": trajectory.spans[0].time_law.duration_seconds * 0.8}
            )
        }
    )
    tampered = trajectory.model_copy(update={"spans": (bad_span,)}, deep=True)
    verification = verify_continuous_trajectory(tampered)

    assert verification.overall_status == "Refuted"
    assert any(entry.code == "TimeLawMismatch" for entry in verification.error_ledger)


def test_plan_jerk_feasible_rejects_allow_continuous_nodes_without_c3_regularity() -> None:
    axis_path = _build_axis_path(
        event_specs=[
            {"nodeId": "m3.node.0", "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": "m3.seg.1"},
            {"nodeId": "m3.node.1", "sigma": 0.5, "eventType": "ordinary-junction", "leftSegmentId": "m3.seg.1", "rightSegmentId": "m3.seg.1"},
        ],
        node_continuities={"m3.node.0": "C3", "m3.node.1": "C1"},
    )
    profile = _build_profile(
        axis_path,
        x_velocity=43.75,
        x_acceleration=525.0,
        x_jerk=4200.0,
        node_constraints=[
            {"nodeId": "m3.node.0", "sigma": 0.0, "boundaryMode": "allow-continuous"},
            {"nodeId": "m3.node.1", "sigma": 0.5, "boundaryMode": "allow-continuous"},
        ],
    )

    with pytest.raises(
        ValueError,
        match="allow-continuous nodes do not certify the continuity required by the requested timing mode",
    ):
        plan_jerk_feasible_time_law(axis_path, profile)


def test_plan_second_order_rejects_profile_constraints_for_unknown_nodes() -> None:
    axis_path = _build_axis_path()
    profile = _build_profile(
        axis_path,
        x_velocity=200.0,
        x_acceleration=80.0,
        node_constraints=[{"nodeId": "missing.node", "sigma": 0.5, "boundaryMode": "allow-continuous"}],
    )

    with pytest.raises(
        ValueError,
        match="motionConstraintProfile nodeConstraints must target sourceAxisPath nodeEvents",
    ):
        plan_second_order_time_law(axis_path, profile)


def test_plan_second_order_requires_dwell_seconds_for_dwell_events() -> None:
    axis_path = _build_axis_path(
        event_specs=[
            {"nodeId": "m3.node.0", "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": "m3.seg.1"},
            {"nodeId": "m3.node.1", "sigma": 0.5, "eventType": "dwell", "leftSegmentId": "m3.seg.1", "rightSegmentId": "m3.seg.1"},
        ]
    )
    profile = _build_profile(axis_path, x_velocity=200.0, x_acceleration=80.0)

    with pytest.raises(
        ValueError,
        match="dwell nodeEvents require MotionConstraintProfile dwellSeconds",
    ):
        plan_second_order_time_law(axis_path, profile)


def test_plan_jerk_feasible_requires_maximum_jerk_on_moving_axes() -> None:
    axis_path = _build_axis_path()
    profile = _build_profile(axis_path, x_velocity=43.75, x_acceleration=525.0)

    with pytest.raises(
        ValueError,
        match="smoothstep7-feasible planning requires maximumJerk on every moving axis",
    ):
        plan_jerk_feasible_time_law(axis_path, profile)


def test_plan_second_order_does_not_mark_internal_ordinary_junction_as_proven_optimal() -> None:
    axis_path = _build_axis_path(
        event_specs=[
            {"nodeId": "m3.node.0", "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": "m3.seg.1"},
            {"nodeId": "m3.node.1", "sigma": 0.5, "eventType": "ordinary-junction", "leftSegmentId": "m3.seg.1", "rightSegmentId": "m3.seg.1"},
        ]
    )
    profile = _build_profile(
        axis_path,
        x_velocity=200.0,
        x_acceleration=80.0,
        node_constraints=[
            {"nodeId": "m3.node.0", "sigma": 0.0, "boundaryMode": "allow-continuous"},
            {"nodeId": "m3.node.1", "sigma": 0.5, "boundaryMode": "allow-continuous"},
        ],
    )

    with pytest.raises(ValueError, match="does not allow moving internal nodes"):
        plan_second_order_time_law(axis_path, profile)
