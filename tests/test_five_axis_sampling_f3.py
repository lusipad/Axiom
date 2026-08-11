from __future__ import annotations

import hashlib
import json

import pytest

import axiom.five_axis.f3_sampling as sampling_module
from axiom.five_axis.f2_kinematics import forward_kinematics
from axiom.five_axis.f2_models import M3CandidateAxisPath
from axiom.five_axis.f3_models import M4ContinuousTrajectory, MotionConstraintProfile
from axiom.five_axis.f3_sampling import (
    FOH_POLICY_ID,
    POLYNOMIAL_POLICY_ID,
    REFERENCE_M4_POLICY_ID,
    ZOH_POLICY_ID,
    M5DiscreteCommand,
    M5SampledTrajectory,
    ReconstructionPolicy,
    sample_continuous_trajectory,
    verify_interval_reconstruction,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _canonical_hash(model) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
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


def _regularity_certificate(segment_id: str, node_id: str, certificate_id: str) -> dict:
    derivatives = [{"order": 0, "components": [0.0] * 5}, {"order": 1, "components": [1.0] * 5}]
    return {
        "certificateId": certificate_id,
        "segmentEvidence": [
            {
                "segmentId": segment_id,
                "continuityClass": "C1",
                "derivatives": derivatives,
                "verificationMethod": "analytic",
            }
        ],
        "nodeEvidence": [
            {
                "nodeId": node_id,
                "continuityClass": "C1",
                "leftDerivatives": derivatives,
                "rightDerivatives": derivatives,
                "verificationMethod": "analytic",
            }
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
        "regularityCertificate": _regularity_certificate(segment_id, node_id, "m2.reg.1"),
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


def _m3_payload() -> dict:
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
                "continuityClass": "C1",
                "interpolation": "linear",
                "coefficientBasis": "local-power@1",
                "coefficients": [[0.0, 0.0, 0.0, 0.0, 0.0], [20.0, 0.0, 0.0, 0.25, 0.5]],
            }
        ],
        "nodeEvents": [{"nodeId": "m3.node.1", "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": "m3.seg.1"}],
        "regularityCertificate": _regularity_certificate("m3.seg.1", "m3.node.1", "m3.reg.1"),
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


def _build_m4(duration: float, *, velocity_limit: float, acceleration_limit: float, jerk_limit: float) -> M4ContinuousTrajectory:
    axis_path = M3CandidateAxisPath.model_validate(_m3_payload())
    profile = MotionConstraintProfile.model_validate(
        {
            "artifactType": "five-axis.motion-constraint-profile",
            "schemaId": "five-axis.motion-constraint-profile@1",
            "schemaVersion": 1,
            "profileId": "five-axis.motion-constraint.demo@1",
            "machineProfileId": axis_path.machine_profile.profile_id,
            "machineProfileContentId": axis_path.machine_profile_content_id,
            "axisConstraints": [
                {
                    "axisId": axis.axis_id,
                    "unit": axis.limits.unit,
                    "maximumVelocity": velocity_limit,
                    "maximumAcceleration": acceleration_limit,
                    "maximumJerk": jerk_limit,
                }
                for axis in axis_path.machine_profile.axes
            ],
            "startBoundary": {"sigmaVelocity": 0.0, "sigmaAcceleration": 0.0},
            "endBoundary": {"sigmaVelocity": 0.0, "sigmaAcceleration": 0.0},
            "nodeConstraints": [{"nodeId": "m3.node.1", "sigma": 0.0, "boundaryMode": "allow-continuous"}],
            "policyIds": ["five-axis.motion-constraint-profile.strict@1"],
            "provenance": [_provenance("m2.geom.1")],
        }
    )
    return M4ContinuousTrajectory.model_validate(
        {
            "artifactType": "five-axis.m4-continuous-trajectory",
            "schemaId": "five-axis.m4-continuous-trajectory@1",
            "schemaVersion": 1,
            "trajectoryId": "m4.trajectory.1",
            "sourceAxisPath": axis_path.model_dump(mode="json", by_alias=True),
            "sourceAxisPathContentId": _canonical_hash(axis_path),
            "motionConstraintProfile": profile.model_dump(mode="json", by_alias=True),
            "motionConstraintProfileContentId": _canonical_hash(profile),
            "solverId": "five-axis.m4-timing.demo@1",
            "timingMode": "smoothstep7-feasible",
            "spans": [
                {
                    "spanId": "span.1",
                    "spanKind": "move",
                    "segmentIds": ["m3.seg.1"],
                    "startTimeSeconds": 0.0,
                    "endTimeSeconds": duration,
                    "sigmaStart": 0.0,
                    "sigmaEnd": 1.0,
                    "timeLaw": {
                        "lawKind": "smoothstep7",
                        "durationSeconds": duration,
                        "sigmaVelocityLimit": 1.0,
                        "sigmaAccelerationLimit": 1.0,
                        "sigmaJerkLimit": 1.0,
                        "peakSigmaVelocity": 1.0,
                        "peakSigmaAcceleration": 1.0,
                        "peakSigmaJerk": 1.0,
                    },
                }
            ],
            "verification": {
                "verificationId": "m4.verification.1",
                "solverId": "five-axis.m4-verifier.demo@1",
                "evidenceLevel": "Certified",
                "claimId": "five-axis.continuously-feasible-claim@1",
                "overallStatus": "Supported",
                "totalDurationSeconds": duration,
                "optimality": {"classification": "FeasibleOnly", "rationale": "fixture"},
                "nodeContracts": [
                    {
                        "nodeId": "m3.node.1",
                        "sigma": 0.0,
                        "eventType": "ordinary-junction",
                        "boundaryMode": "allow-continuous",
                        "source": "event-type",
                    }
                ],
                "axisConstraintUsage": [
                    {
                        "axisId": axis.axis_id,
                        "unit": axis.limits.unit,
                        "maximumVelocity": velocity_limit * 0.5,
                        "velocityLimit": velocity_limit,
                        "maximumAcceleration": acceleration_limit * 0.5,
                        "accelerationLimit": acceleration_limit,
                        "maximumJerk": jerk_limit * 0.5,
                        "jerkLimit": jerk_limit,
                    }
                    for axis in axis_path.machine_profile.axes
                ],
                "errorLedger": [],
            },
            "provenance": [_provenance("m2.geom.1")],
        }
    )


def _smooth_state(duration: float, t: float) -> dict:
    u = t / duration
    q = (
        0.2 * u + 0.05 * u**2,
        0.15 * u**2,
        -0.1 * u + 0.02 * u**3,
        0.04 * u**2,
        -0.03 * u**2 + 0.01 * u**3,
    )
    qdot = (
        (0.2 + 0.1 * u) / duration,
        (0.3 * u) / duration,
        (-0.1 + 0.06 * u**2) / duration,
        (0.08 * u) / duration,
        (-0.06 * u + 0.03 * u**2) / duration,
    )
    qddot = (
        0.1 / duration**2,
        0.3 / duration**2,
        (0.12 * u) / duration**2,
        0.08 / duration**2,
        (-0.06 + 0.06 * u) / duration**2,
    )
    qjerk = (
        0.0,
        0.0,
        0.12 / duration**3,
        0.0,
        0.06 / duration**3,
    )
    return {
        "sigma": u,
        "jointPosition": q,
        "jointVelocity": qdot,
        "jointAcceleration": qddot,
        "jointJerk": qjerk,
    }


def _interior_overspeed_state(duration: float, t: float, scale: float = 1.0) -> dict:
    u = t / duration
    base = scale * (u**2 - 2.0 * u**3 + u**4)
    q = (base, 0.0, 0.0, 0.0, 0.0)
    qdot = (scale * (2.0 * u - 6.0 * u**2 + 4.0 * u**3) / duration, 0.0, 0.0, 0.0, 0.0)
    qddot = (scale * (2.0 - 12.0 * u + 12.0 * u**2) / duration**2, 0.0, 0.0, 0.0, 0.0)
    qjerk = (scale * (-12.0 + 24.0 * u) / duration**3, 0.0, 0.0, 0.0, 0.0)
    return {
        "sigma": u,
        "jointPosition": q,
        "jointVelocity": qdot,
        "jointAcceleration": qddot,
        "jointJerk": qjerk,
    }


def _install_evaluator(monkeypatch: pytest.MonkeyPatch, state_factory):
    def evaluator(m4: M4ContinuousTrajectory, t: float) -> dict:
        duration = m4.verification.total_duration_seconds
        return state_factory(duration, t)

    monkeypatch.setattr(sampling_module, "_F3_TIMING_EVALUATOR", evaluator)
    monkeypatch.setattr(
        sampling_module,
        "_F3_TIMING_VERIFIER",
        lambda m4: m4.verification,
    )


def test_sampling_appends_remainder_endpoint_and_uses_forward_kinematics(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, _smooth_state)
    m4 = _build_m4(1.25, velocity_limit=10.0, acceleration_limit=10.0, jerk_limit=10.0)

    artifact = sample_continuous_trajectory(m4, sample_period=0.5, policy="reference-m4", final_hold=True)

    assert isinstance(artifact, M5SampledTrajectory)
    assert [sample.t for sample in artifact.samples] == pytest.approx([0.0, 0.5, 1.0, 1.25])
    assert artifact.remainder_duration == pytest.approx(0.25)
    assert [interval.interval_semantics for interval in artifact.intervals] == ["[t_k,t_k+1)"] * 3
    pose = forward_kinematics(
        m4.source_axis_path.machine_profile,
        {
            axis.axis_id: artifact.samples[1].q[index]
            for index, axis in enumerate(m4.source_axis_path.machine_profile.axes)
        },
    )
    assert artifact.samples[1].task_pose.position == pytest.approx(pose.position)
    assert artifact.samples[1].task_pose.tool_axis == pytest.approx(pose.tool_axis)


def test_reference_m4_roundtrip_stays_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, _smooth_state)
    m4 = _build_m4(1.25, velocity_limit=100.0, acceleration_limit=100.0, jerk_limit=100.0)

    artifact = sample_continuous_trajectory(m4, sample_period=0.5, policy=ReconstructionPolicy(policyId=REFERENCE_M4_POLICY_ID), final_hold=False)
    roundtrip = M5SampledTrajectory.model_validate(artifact.model_dump(mode="json", by_alias=True))
    result = verify_interval_reconstruction(roundtrip)

    assert result.status == "Supported"
    assert result.evidence_level == "Certified"
    assert result.method == "five-axis.m5.reference-m4.replay-certified-power-bound@1"
    assert roundtrip.source_m4_content_id == _canonical_hash(roundtrip.source_m4)


def test_same_samples_reconstruct_differently_by_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, _smooth_state)
    m4 = _build_m4(1.0, velocity_limit=100.0, acceleration_limit=100.0, jerk_limit=100.0)

    polynomial = sample_continuous_trajectory(m4, sample_period=0.5, policy=POLYNOMIAL_POLICY_ID, final_hold=False)
    zoh = sample_continuous_trajectory(m4, sample_period=0.5, policy=ZOH_POLICY_ID, final_hold=False)

    polynomial_state = sampling_module._evaluate_policy_state(polynomial, 0.25)
    zoh_state = sampling_module._evaluate_policy_state(zoh, 0.25)

    assert polynomial_state["q"] != pytest.approx(zoh_state["q"])


def test_foh_and_zoh_stay_overall_unsupported_under_full_closure_request(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, _smooth_state)
    m4 = _build_m4(1.0, velocity_limit=100.0, acceleration_limit=100.0, jerk_limit=100.0)

    foh = sample_continuous_trajectory(m4, sample_period=0.5, policy=FOH_POLICY_ID, final_hold=False)
    zoh = sample_continuous_trajectory(m4, sample_period=0.5, policy=ZOH_POLICY_ID, final_hold=False)

    foh_result = verify_interval_reconstruction(foh)
    zoh_result = verify_interval_reconstruction(zoh)

    assert isinstance(foh, M5DiscreteCommand)
    assert foh_result.status == "Unsupported"
    assert next(item for item in foh_result.quantities if item.quantity == "position").status == "Supported"
    assert next(item for item in foh_result.quantities if item.quantity == "velocity").status == "Supported"
    assert next(item for item in foh_result.quantities if item.quantity == "acceleration").status == "Unsupported"
    assert zoh_result.status == "Unsupported"
    assert next(item for item in zoh_result.quantities if item.quantity == "velocity").status == "Unsupported"


def test_polynomial_verifier_catches_interior_overspeed_not_visible_at_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, lambda duration, t: _interior_overspeed_state(duration, t, scale=8.0))
    m4 = _build_m4(1.0, velocity_limit=0.5, acceleration_limit=100.0, jerk_limit=100.0)

    artifact = sample_continuous_trajectory(m4, sample_period=1.0, policy=POLYNOMIAL_POLICY_ID, final_hold=False)
    result = verify_interval_reconstruction(artifact)
    velocity = next(item for item in result.quantities if item.quantity == "velocity")

    assert [sample.qdot[0] for sample in artifact.samples] == pytest.approx([0.0, 0.0])
    assert result.status == "Refuted"
    assert velocity.status == "Refuted"
    assert velocity.axis_results[0].reason_code == "IntervalInteriorLimitExceeded"


def test_verifier_refutes_sample_tamper_against_embedded_source(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, _smooth_state)
    m4 = _build_m4(1.0, velocity_limit=100.0, acceleration_limit=100.0, jerk_limit=100.0)

    artifact = sample_continuous_trajectory(m4, sample_period=0.5, policy=REFERENCE_M4_POLICY_ID, final_hold=False)
    samples = list(artifact.samples)
    samples[1] = samples[1].model_copy(update={"q": (samples[1].q[0] + 0.25, *samples[1].q[1:])})
    tampered_model = artifact.model_copy(update={"samples": tuple(samples)}, deep=True)
    payload = tampered_model.model_dump(mode="json", by_alias=True)
    payload["contentId"] = sampling_module._canonical_content_id(tampered_model)
    tampered = M5SampledTrajectory.model_validate(payload)

    result = verify_interval_reconstruction(tampered)

    assert result.status == "Refuted"
    assert next(item for item in result.quantities if item.quantity == "interval-certified").reason_code == "SampleReplayMismatch"


def test_verifier_refutes_interval_coefficient_tamper(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, _smooth_state)
    m4 = _build_m4(1.0, velocity_limit=100.0, acceleration_limit=100.0, jerk_limit=100.0)

    artifact = sample_continuous_trajectory(m4, sample_period=0.5, policy=POLYNOMIAL_POLICY_ID, final_hold=False)
    intervals = list(artifact.intervals)
    coefficients = [list(row) for row in intervals[0].certificate_coefficients]
    coefficients[0][0] += 0.1
    intervals[0] = intervals[0].model_copy(update={"certificate_coefficients": tuple(tuple(row) for row in coefficients)})
    tampered_model = artifact.model_copy(update={"intervals": tuple(intervals)}, deep=True)
    payload = tampered_model.model_dump(mode="json", by_alias=True)
    payload["contentId"] = sampling_module._canonical_content_id(tampered_model)
    tampered = M5SampledTrajectory.model_validate(payload)

    result = verify_interval_reconstruction(tampered)

    assert result.status == "Refuted"
    assert next(item for item in result.quantities if item.quantity == "interval-certified").reason_code == "CoefficientEndpointMismatch"


def test_sampling_rejects_non_finite_sample_period(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, _smooth_state)
    m4 = _build_m4(1.0, velocity_limit=100.0, acceleration_limit=100.0, jerk_limit=100.0)

    with pytest.raises(ValueError, match="value must be a finite JSON number"):
        sample_continuous_trajectory(m4, sample_period=float("nan"), policy=REFERENCE_M4_POLICY_ID, final_hold=False)


def test_policy_state_rejects_times_past_duration_without_final_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_evaluator(monkeypatch, _smooth_state)
    m4 = _build_m4(1.0, velocity_limit=100.0, acceleration_limit=100.0, jerk_limit=100.0)
    artifact = sample_continuous_trajectory(m4, sample_period=0.5, policy=REFERENCE_M4_POLICY_ID, final_hold=False)

    with pytest.raises(ValueError, match="t exceeds the sampled duration and finalHold is disabled"):
        sampling_module._evaluate_policy_state(artifact, 1.01)
