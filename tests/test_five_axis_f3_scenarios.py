from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

if "axiom.five_axis.f3_timing" not in sys.modules:
    timing_stub = types.ModuleType("axiom.five_axis.f3_timing")
    timing_stub.plan_second_order_time_law = lambda *_args, **_kwargs: None
    timing_stub.plan_jerk_feasible_time_law = lambda *_args, **_kwargs: None
    timing_stub.evaluate_continuous_state = lambda *_args, **_kwargs: None
    timing_stub.verify_continuous_trajectory = lambda *_args, **_kwargs: None
    sys.modules["axiom.five_axis.f3_timing"] = timing_stub

import axiom.five_axis.f3_scenarios as scenarios_module
import axiom.five_axis.f3_sampling as sampling_module
from axiom.five_axis.f2_kinematics import forward_kinematics
from axiom.five_axis.f3_models import (
    AxisConstraintUsage,
    ContinuousTrajectorySpan,
    ContinuousTrajectoryVerification,
    M4ContinuousTrajectory,
    RealizedNodeContract,
    TimeLawDefinition,
    TrajectoryOptimality,
)
from axiom.five_axis.f3_sampling import M5DiscreteCommand, M5Sample, M5SampledTrajectory, ReconstructionPolicy


def _canonical_hash(model) -> str:
    return scenarios_module._canonical_content_id(model)


def _build_m4(
    axis_path,
    profile,
    *,
    trajectory_id: str,
    timing_mode: str,
    classification: str,
    spans: tuple[ContinuousTrajectorySpan, ...],
) -> M4ContinuousTrajectory:
    total_duration = spans[-1].end_time_seconds if spans else 0.0
    usage = []
    for constraint in profile.axis_constraints:
        usage.append(
            AxisConstraintUsage(
                axisId=constraint.axis_id,
                unit=constraint.unit,
                maximumVelocity=constraint.maximum_velocity * 0.5,
                velocityLimit=constraint.maximum_velocity,
                maximumAcceleration=constraint.maximum_acceleration * 0.5,
                accelerationLimit=constraint.maximum_acceleration,
                maximumJerk=(constraint.maximum_jerk * 0.5 if constraint.maximum_jerk is not None else None),
                jerkLimit=constraint.maximum_jerk,
            )
        )
    node_contracts = tuple(
        RealizedNodeContract(
            nodeId=node.node_id,
            sigma=node.sigma,
            eventType=("dwell" if node.boundary_mode == "dwell" else "mandatory-stop"),
            boundaryMode=node.boundary_mode,
            dwellSeconds=node.dwell_seconds,
            source="profile",
        )
        for node in profile.node_constraints
    )
    optimality = (
        TrajectoryOptimality(classification="ProvenOptimal", proofGapSeconds=0.0, rationale="fixture")
        if classification == "ProvenOptimal"
        else TrajectoryOptimality(classification="FeasibleOnly", rationale="fixture")
    )
    return M4ContinuousTrajectory(
        artifactType="five-axis.m4-continuous-trajectory",
        schemaId="five-axis.m4-continuous-trajectory@1",
        schemaVersion=1,
        trajectoryId=trajectory_id,
        sourceAxisPath=axis_path,
        sourceAxisPathContentId=_canonical_hash(axis_path),
        motionConstraintProfile=profile,
        motionConstraintProfileContentId=_canonical_hash(profile),
        solverId=f"five-axis.fixture.{timing_mode}@1",
        timingMode=timing_mode,
        spans=spans,
        verification=ContinuousTrajectoryVerification(
            verificationId=f"{trajectory_id}.verification",
            solverId=f"five-axis.fixture.verify.{timing_mode}@1",
            evidenceLevel="Certified",
            claimId="five-axis.continuously-feasible-claim@1",
            overallStatus="Supported",
            totalDurationSeconds=total_duration,
            optimality=optimality,
            nodeContracts=node_contracts,
            axisConstraintUsage=tuple(usage),
            errorLedger=(),
        ),
        provenance=(scenarios_module._upstream_provenance(axis_path, method="fixture"),),
    )


def _task_pose(machine_profile, q):
    pose = forward_kinematics(
        machine_profile,
        {axis.axis_id: q[index] for index, axis in enumerate(machine_profile.axes)},
    )
    return {"position": pose.position, "toolAxis": pose.tool_axis}


def _build_sample_artifact(m4: M4ContinuousTrajectory, policy_id: str):
    start_q = tuple(m4.source_axis_path.joint_segments[0].evaluate(0.0))
    end_q = tuple(m4.source_axis_path.joint_segments[-1].evaluate(1.0))
    machine_profile = m4.source_axis_path.machine_profile
    sample_cls = M5SampledTrajectory if policy_id in {"reference-m4", "five-axis.reconstruction.reference-m4@1", "polynomial", "five-axis.reconstruction.polynomial@1"} else M5DiscreteCommand
    artifact_type = "five-axis.m5-sampled-trajectory" if sample_cls is M5SampledTrajectory else "five-axis.m5-discrete-command"
    schema_id = "five-axis.m5-sampled-trajectory@1" if sample_cls is M5SampledTrajectory else "five-axis.m5-discrete-command@1"
    model = sample_cls.model_construct(
        artifact_type=artifact_type,
        schema_id=schema_id,
        schema_version=1,
        content_id="0" * 64,
        source_m4=m4,
        source_m4_id=m4.trajectory_id,
        source_m4_content_id=_canonical_hash(m4),
        sample_period=0.25,
        duration=m4.verification.total_duration_seconds,
        remainder_duration=0.0,
        terminal_sample_included=True,
        final_hold=False,
        reconstruction_policy=ReconstructionPolicy(policyId=policy_id),
        limits=sampling_module._limits_for(m4),
        samples=(
            M5Sample(
                sampleId=f"{m4.trajectory_id}.sample.0",
                sampleIndex=0,
                t=0.0,
                cycle=0,
                sigma=0.0,
                q=start_q,
                qdot=(0.0, 0.0, 0.0, 0.0, 0.0),
                qddot=(0.0, 0.0, 0.0, 0.0, 0.0),
                qjerk=(0.0, 0.0, 0.0, 0.0, 0.0),
                taskPose=_task_pose(machine_profile, start_q),
                provenance=(),
            ),
            M5Sample(
                sampleId=f"{m4.trajectory_id}.sample.1",
                sampleIndex=1,
                t=m4.verification.total_duration_seconds,
                cycle=1,
                sigma=1.0,
                q=end_q,
                qdot=(0.0, 0.0, 0.0, 0.0, 0.0),
                qddot=(0.0, 0.0, 0.0, 0.0, 0.0),
                qjerk=(0.0, 0.0, 0.0, 0.0, 0.0),
                taskPose=_task_pose(machine_profile, end_q),
                provenance=(),
            ),
        ),
        intervals=(
            sampling_module.M5IntervalRecord(
                intervalId=f"{m4.trajectory_id}.interval.0",
                intervalIndex=0,
                startSampleIndex=0,
                endSampleIndex=1,
                tStart=0.0,
                tEnd=m4.verification.total_duration_seconds,
                certificateCoefficients=tuple(tuple(0.0 for _ in range(5)) for _ in range(8)),
            ),
        ),
        provenance=(),
        **{("sampled_trajectory_id" if sample_cls is M5SampledTrajectory else "discrete_command_id"): f"{m4.trajectory_id}.m5"},
    )
    return model.model_copy(update={"content_id": sampling_module._canonical_content_id(model)}, deep=True)


@pytest.fixture
def patched_builders(monkeypatch: pytest.MonkeyPatch):
    def plan_jerk(axis_path, profile):
        spans = (
            ContinuousTrajectorySpan(
                spanId="fixture.move.0",
                spanKind="move",
                segmentIds=tuple(segment.segment_id for segment in axis_path.joint_segments[:1]),
                startTimeSeconds=0.0,
                endTimeSeconds=1.0,
                sigmaStart=0.0,
                sigmaEnd=1.0,
                timeLaw=TimeLawDefinition(
                    lawKind="smoothstep7",
                    durationSeconds=1.0,
                    sigmaVelocityLimit=1.0,
                    sigmaAccelerationLimit=1.0,
                    sigmaJerkLimit=1.0,
                    peakSigmaVelocity=0.9,
                    peakSigmaAcceleration=0.8,
                    peakSigmaJerk=0.7,
                ),
            ),
        )
        if len(axis_path.joint_segments) == 2:
            spans = (
                ContinuousTrajectorySpan(
                    spanId="fixture.move.0",
                    spanKind="move",
                    segmentIds=(axis_path.joint_segments[0].segment_id,),
                    startTimeSeconds=0.0,
                    endTimeSeconds=0.5,
                    sigmaStart=0.0,
                    sigmaEnd=0.5,
                    timeLaw=TimeLawDefinition(
                        lawKind="smoothstep7",
                        durationSeconds=0.5,
                        sigmaVelocityLimit=1.0,
                        sigmaAccelerationLimit=1.0,
                        sigmaJerkLimit=1.0,
                        peakSigmaVelocity=0.9,
                        peakSigmaAcceleration=0.8,
                        peakSigmaJerk=0.7,
                    ),
                ),
                ContinuousTrajectorySpan(
                    spanId="fixture.dwell",
                    spanKind="dwell",
                    segmentIds=(),
                    startTimeSeconds=0.5,
                    endTimeSeconds=0.9,
                    sigmaStart=0.5,
                    sigmaEnd=0.5,
                    timeLaw=TimeLawDefinition(
                        lawKind="dwell",
                        durationSeconds=0.4,
                        peakSigmaVelocity=0.0,
                        peakSigmaAcceleration=0.0,
                        peakSigmaJerk=0.0,
                    ),
                ),
                ContinuousTrajectorySpan(
                    spanId="fixture.move.1",
                    spanKind="move",
                    segmentIds=(axis_path.joint_segments[1].segment_id,),
                    startTimeSeconds=0.9,
                    endTimeSeconds=1.4,
                    sigmaStart=0.5,
                    sigmaEnd=1.0,
                    timeLaw=TimeLawDefinition(
                        lawKind="smoothstep7",
                        durationSeconds=0.5,
                        sigmaVelocityLimit=1.0,
                        sigmaAccelerationLimit=1.0,
                        sigmaJerkLimit=1.0,
                        peakSigmaVelocity=0.9,
                        peakSigmaAcceleration=0.8,
                        peakSigmaJerk=0.7,
                    ),
                ),
            )
        return _build_m4(
            axis_path,
            profile,
            trajectory_id="fixture.trajectory.jerk",
            timing_mode="smoothstep7-feasible",
            classification="FeasibleOnly",
            spans=spans,
        )

    def plan_second_order(axis_path, profile):
        return _build_m4(
            axis_path,
            profile,
            trajectory_id="fixture.trajectory.second-order",
            timing_mode="second-order-optimal",
            classification="ProvenOptimal",
            spans=(
                ContinuousTrajectorySpan(
                    spanId="fixture.second-order",
                    spanKind="move",
                    segmentIds=tuple(segment.segment_id for segment in axis_path.joint_segments),
                    startTimeSeconds=0.0,
                    endTimeSeconds=0.8,
                    sigmaStart=0.0,
                    sigmaEnd=1.0,
                    timeLaw=TimeLawDefinition(
                        lawKind="trapezoidal",
                        durationSeconds=0.8,
                        accelerationDurationSeconds=0.2,
                        cruiseDurationSeconds=0.4,
                        decelerationDurationSeconds=0.2,
                        sigmaVelocityLimit=1.0,
                        sigmaAccelerationLimit=1.0,
                        peakSigmaVelocity=0.9,
                        peakSigmaAcceleration=0.8,
                        peakSigmaJerk=0.0,
                    ),
                ),
            ),
        )

    monkeypatch.setattr(
        scenarios_module,
        "_resolve_timing_api",
        lambda: SimpleNamespace(
            plan_jerk_feasible_time_law=plan_jerk,
            plan_second_order_time_law=plan_second_order,
            evaluate_continuous_state=lambda *_args, **_kwargs: None,
            verify_continuous_trajectory=lambda *_args, **_kwargs: None,
        ),
    )
    monkeypatch.setattr(
        scenarios_module,
        "_sample_artifact",
        lambda definition, m4: _build_sample_artifact(m4, definition.reconstruction_policy_id),
    )


def test_list_f3_scenarios_exposes_expected_registry_without_materializing_timing() -> None:
    scenario_ids = {item.scenarioId for item in scenarios_module.list_f3_scenarios()}

    assert scenario_ids == {
        "canonical-head-head-jerk",
        "canonical-head-table-jerk",
        "canonical-table-table-jerk",
        "dwell-mandatory-stop",
        "polynomial-interior-violation",
        "second-order-proven-optimal",
        "zoh-moving-unsupported",
    }


def test_canonical_jerk_payload_is_deterministic_and_supported(patched_builders) -> None:
    first = scenarios_module.f3_example_payload("canonical-head-head-jerk")
    second = scenarios_module.f3_example_payload("canonical-head-head-jerk")
    m5_descriptor = next(item for item in first["manifest"]["artifactDescriptors"] if item["stage"] == "M5")

    assert first == second
    assert first["scenario"]["expectedClaimStatusById"] == {
        "five-axis.continuously-feasible-claim@1": "Supported",
        "five-axis.interval-certified-claim@1": "Supported",
    }
    assert first["artifacts"]["sampledTrajectory"]["artifactType"] == "five-axis.m5-sampled-trajectory"
    assert m5_descriptor == {
        "stage": "M5",
        "artifactType": "five-axis.m5-sampled-trajectory",
        "schemaId": "five-axis.m5-sampled-trajectory@1",
    }
    assert first["manifest"]["expectedClaims"][0]["claimId"] == "five-axis.continuously-feasible-claim@1"
    assert first["manifest"]["expectedClaims"][1]["claimId"] == "five-axis.interval-certified-claim@1"
    assert scenarios_module.validate_f3_example_run_spec("canonical-head-head-jerk").domain_pack_id == (
        scenarios_module.FIVE_AXIS_F3_DOMAIN_PACK_ID
    )


def test_second_order_scenario_omits_jerk_request_and_uses_discrete_command(patched_builders) -> None:
    scenario = scenarios_module.load_f3_scenario("second-order-proven-optimal")
    descriptor = next(item for item in scenario.manifest.artifact_descriptors if item.stage == "M5")

    assert all(item.maximum_jerk is None for item in scenario.motionConstraintProfile.axis_constraints)
    assert scenario.discreteCommand is not None
    assert scenario.sampledTrajectory is None
    assert descriptor.artifact_type == scenario.discreteCommand.artifact_type
    assert descriptor.schema_id == scenario.discreteCommand.schema_id
    assert scenario.continuousTrajectory.verification.optimality.classification == "ProvenOptimal"
    assert scenario.manifest.expected_claims[1].expected_status == "Inconclusive"
    assert scenario.manifest.expected_claims[1].evidence_level is None


def test_dwell_scenario_splits_single_segment_and_inserts_real_constraints(patched_builders) -> None:
    scenario = scenarios_module.load_f3_scenario("dwell-mandatory-stop")

    assert len(scenario.axisPath.joint_segments) == 2
    assert [event.event_type for event in scenario.axisPath.node_events] == ["mandatory-stop", "dwell"]
    assert [node.boundary_mode for node in scenario.motionConstraintProfile.node_constraints] == [
        "mandatory-stop",
        "dwell",
    ]
    assert scenario.motionConstraintProfile.node_constraints[1].dwell_seconds == pytest.approx(0.4)
    assert [span.span_kind for span in scenario.continuousTrajectory.spans] == ["move", "dwell", "move"]


def test_zoh_and_polynomial_scenarios_preserve_expected_interval_statuses(patched_builders) -> None:
    zoh = scenarios_module.load_f3_scenario("zoh-moving-unsupported")
    polynomial = scenarios_module.load_f3_scenario("polynomial-interior-violation")
    zoh_descriptor = next(item for item in zoh.manifest.artifact_descriptors if item.stage == "M5")
    polynomial_descriptor = next(item for item in polynomial.manifest.artifact_descriptors if item.stage == "M5")

    assert zoh.discreteCommand is not None
    assert zoh_descriptor.artifact_type == zoh.discreteCommand.artifact_type
    assert zoh_descriptor.schema_id == zoh.discreteCommand.schema_id
    assert zoh.manifest.expected_claims[1].expected_status == "Inconclusive"
    assert zoh.manifest.expected_claims[1].evidence_level is None
    assert polynomial.sampledTrajectory is not None
    assert polynomial_descriptor.artifact_type == polynomial.sampledTrajectory.artifact_type
    assert polynomial_descriptor.schema_id == polynomial.sampledTrajectory.schema_id
    assert polynomial.manifest.expected_claims[1].expected_status == "Refuted"


def test_unknown_f3_scenario_raises_clear_error() -> None:
    with pytest.raises(KeyError, match="unknown F3 scenario"):
        scenarios_module.load_f3_scenario("unknown")
