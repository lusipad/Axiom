from __future__ import annotations

import math

import numpy as np
import pytest

from axiom.five_axis.f2_kinematics import (
    AxisLimitSpec,
    AxisSpec,
    IKSearchResult,
    KinematicsError,
    PoseSolution,
    build_canonical_head_head_cb_profile,
    build_canonical_head_table_bc_profile,
    build_canonical_table_table_ac_profile,
    build_general_machine_profile,
    forward_kinematics,
    ik_candidate_to_contract,
    inverse_kinematics,
    jacobian_evidence,
)


def _solution_by_branch(result: IKSearchResult, branch_id: str):
    return [solution for solution in result.solutions if solution.branch_id == branch_id]


def _joint_map(solution) -> dict[str, float]:
    return dict(solution.joint_values)


@pytest.mark.parametrize(
    ("builder", "joints"),
    (
        (build_canonical_table_table_ac_profile, {"X": 25.0, "Y": -8.0, "Z": 40.0, "A": 0.4, "C": -0.7}),
        (build_canonical_head_table_bc_profile, {"X": 25.0, "Y": -8.0, "Z": 40.0, "C": -0.7, "B": 0.4}),
        (build_canonical_head_head_cb_profile, {"X": 25.0, "Y": -8.0, "Z": 40.0, "C": -0.7, "B": 0.4}),
    ),
)
def test_each_canonical_profile_has_contract_native_closed_form_roundtrip(builder, joints) -> None:
    profile = builder()
    pose = forward_kinematics(profile, joints)

    result = inverse_kinematics(profile, pose)

    assert profile.artifact_type == "five-axis.machine-profile"
    assert result.status == "SolutionsFound"
    assert result.policy_id == "five-axis.closed-form-ik-policy@1"
    assert all(solution.evidence_level == "Exact" for solution in result.solutions)
    assert any(
        forward_kinematics(profile, _joint_map(solution)).position == pytest.approx(pose.position, abs=1e-8)
        and forward_kinematics(profile, _joint_map(solution)).tool_axis == pytest.approx(pose.tool_axis, abs=1e-8)
        for solution in result.solutions
    )


def test_canonical_profile_id_rejects_silent_parameter_override() -> None:
    payload = build_canonical_head_head_cb_profile().model_dump(mode="json", by_alias=True)
    payload["axes"][0]["limits"]["upper"] = 499.0

    with pytest.raises(KinematicsError, match="does not match its versioned profileId"):
        inverse_kinematics(payload, forward_kinematics(payload, {"X": 0.0, "Y": 0.0, "Z": 0.0, "C": 0.2, "B": 0.3}))


def test_table_table_ac_forward_inverse_round_trip_and_wraps() -> None:
    profile = build_canonical_table_table_ac_profile()
    joints = {"X": 120.0, "Y": -45.0, "Z": 30.0, "A": 0.6, "C": 0.8}
    pose = forward_kinematics(profile, joints)

    result = inverse_kinematics(profile, pose)

    assert result.status == "SolutionsFound"
    assert result.proof == "closed-form-complete"
    assert len(result.solutions) >= 4
    primary = _solution_by_branch(result, "ac-primary")
    assert primary
    assert any(math.isclose(_joint_map(solution)["C"], joints["C"], abs_tol=1e-8) for solution in primary)
    assert any(any(item.axis_id == "C" and item.turns == -1 for item in solution.wrap_state) for solution in primary)
    assert any(solution.singularity.singular is False for solution in result.solutions)
    assert all(
        {item.metric_id: item.value for item in solution.residuals}["five-axis.position-residual.max@1"] <= 1e-8
        for solution in result.solutions
    )
    assert tuple((axis.limits.lower, axis.limits.upper) for axis in profile.axes[:3]) == ((-500.0, 500.0),) * 3


def test_head_table_bc_singularity_is_explicit() -> None:
    profile = build_canonical_head_table_bc_profile()
    singular_pose = forward_kinematics(profile, {"X": 10.0, "Y": 20.0, "Z": 30.0, "B": 0.0, "C": 1.2})

    result = inverse_kinematics(profile, singular_pose)

    assert result.status == "SolutionsFound"
    assert all(solution.branch_id == "bc-singular" for solution in result.solutions)
    assert all(solution.singularity.singular is True for solution in result.solutions)
    assert all(math.isclose(_joint_map(solution)["B"], 0.0, abs_tol=1e-8) for solution in result.solutions)
    assert any(math.isclose(_joint_map(solution)["C"], 0.0, abs_tol=1e-8) for solution in result.solutions)
    assert result.solutions[0].free_parameters == (("C", -2.0 * math.pi, 2.0 * math.pi, "rad"),)
    contract = ik_candidate_to_contract(result.solutions[0], sigma=0.0)
    assert contract.free_parameters[0].semantics == "continuous-singular-family@1"


def test_head_head_cb_limit_filter_rejects_outside_tilt_limit() -> None:
    profile = build_canonical_head_head_cb_profile()
    pose = forward_kinematics(profile, {"X": 90.0, "Y": -30.0, "Z": 60.0, "B": 2.2, "C": 0.4})

    result = inverse_kinematics(profile, pose)

    assert result.status == "NoSolutionProven"
    assert result.solutions == ()


def test_forward_kinematics_matches_contract_shape_with_mapping_inputs() -> None:
    profile = build_canonical_head_head_cb_profile().model_dump(mode="json", by_alias=True)

    pose = forward_kinematics(profile, {"X": 12.0, "Y": 3.0, "Z": 40.0, "C": 0.5, "B": 0.25})

    assert pose.position == pytest.approx(
        (
            12.0 - 100.0 * math.sin(0.25) * math.cos(0.5),
            3.0 - 100.0 * math.sin(0.25) * math.sin(0.5),
            40.0 - 100.0 * math.cos(0.25),
        )
    )
    assert pose.tool_axis == pytest.approx(
        (
            math.sin(0.25) * math.cos(0.5),
            math.sin(0.25) * math.sin(0.5),
            math.cos(0.25),
        )
    )


def test_jacobian_evidence_distinguishes_singular_and_regular_pose() -> None:
    profile = build_canonical_head_head_cb_profile()

    singular = jacobian_evidence(profile, {"X": 0.0, "Y": 0.0, "Z": 0.0, "C": 0.0, "B": 0.0})
    regular = jacobian_evidence(profile, {"X": 0.0, "Y": 0.0, "Z": 0.0, "C": 0.5, "B": 0.4})

    assert singular.singular is True
    assert regular.singular is False
    assert singular.minimum_singular_value < regular.minimum_singular_value


def test_jacobian_evidence_canonicalizes_backend_roundoff(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = build_canonical_head_head_cb_profile()
    joint_values = {"X": 0.0, "Y": 0.0, "Z": 0.0, "C": 0.5, "B": 0.4}

    monkeypatch.setattr(
        np.linalg,
        "svd",
        lambda *args, **kwargs: np.asarray((9599.616210932809, 0.010418170376752588)),
    )
    first = jacobian_evidence(profile, joint_values)
    monkeypatch.setattr(
        np.linalg,
        "svd",
        lambda *args, **kwargs: np.asarray((9599.61621093286, 0.010418170376752576)),
    )
    second = jacobian_evidence(profile, joint_values)

    assert first.singular_values == second.singular_values == (9599.61621093, 0.0104181703768)
    assert first.minimum_singular_value == second.minimum_singular_value


def test_jacobian_evidence_keeps_raw_value_for_singularity_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = build_canonical_head_head_cb_profile()
    joint_values = {"X": 0.0, "Y": 0.0, "Z": 0.0, "C": 0.5, "B": 0.4}
    monkeypatch.setattr(
        np.linalg,
        "svd",
        lambda *args, **kwargs: np.asarray((1.0, 1.000000000004e-8)),
    )

    evidence = jacobian_evidence(profile, joint_values)

    assert evidence.minimum_singular_value == 1e-8
    assert evidence.singular is False


def test_general_profile_uses_numeric_fallback_and_round_trips() -> None:
    profile = build_general_machine_profile(
        profile_id="five-axis.machine-profile.general-offset-bc@1",
        topology="dual-head",
        axes=(
            AxisSpec("X", 0, "linear", "X", "translation", "tool", (1.0, 0.0, 0.0), limits=AxisLimitSpec(-500.0, 500.0)),
            AxisSpec("Y", 1, "linear", "Y", "translation", "tool", (0.0, 1.0, 0.0), limits=AxisLimitSpec(-500.0, 500.0)),
            AxisSpec("Z", 2, "linear", "Z", "translation", "tool", (0.0, 0.0, 1.0), limits=AxisLimitSpec(-500.0, 500.0)),
            AxisSpec(
                "C",
                3,
                "rotary",
                "C",
                "spin",
                "tool",
                (0.0, 0.0, 1.0),
                origin=(0.0, 0.0, 40.0),
                periodic=True,
                limits=AxisLimitSpec(-math.pi, math.pi),
            ),
            AxisSpec(
                "B",
                4,
                "rotary",
                "B",
                "tilt",
                "tool",
                (0.0, 1.0, 0.0),
                origin=(0.0, 0.0, 40.0),
                periodic=True,
                limits=AxisLimitSpec(-math.pi / 2.0, math.pi / 2.0),
            ),
        ),
    )
    joints = {"X": 30.0, "Y": -12.0, "Z": 55.0, "C": 0.45, "B": 0.35}
    pose = forward_kinematics(profile, joints)

    result = inverse_kinematics(profile, pose)

    assert result.status == "SolutionsFound"
    assert result.proof == "numerical-search"
    assert result.policy_id == "five-axis.numeric-ik-policy@1"
    assert any(_joint_map(solution) == pytest.approx(joints, abs=1e-5) for solution in result.solutions)
    assert all(forward_kinematics(profile, _joint_map(solution)).position == pytest.approx(pose.position, abs=1e-5) for solution in result.solutions)
    assert result.solutions[0].solver_kind == "numerical-least-squares"


def test_numeric_fallback_without_solution_stays_inconclusive() -> None:
    profile = build_general_machine_profile(
        profile_id="five-axis.machine-profile.general-tight-bc@1",
        topology="dual-head",
        axes=(
            AxisSpec("X", 0, "linear", "X", "translation", "tool", (1.0, 0.0, 0.0), limits=AxisLimitSpec(-10.0, 10.0)),
            AxisSpec("Y", 1, "linear", "Y", "translation", "tool", (0.0, 1.0, 0.0), limits=AxisLimitSpec(-10.0, 10.0)),
            AxisSpec("Z", 2, "linear", "Z", "translation", "tool", (0.0, 0.0, 1.0), limits=AxisLimitSpec(-10.0, 10.0)),
            AxisSpec("C", 3, "rotary", "C", "spin", "tool", (0.0, 0.0, 1.0), periodic=True, limits=AxisLimitSpec(-1.0, 1.0)),
            AxisSpec("B", 4, "rotary", "B", "tilt", "tool", (0.0, 1.0, 0.0), periodic=True, limits=AxisLimitSpec(-1.0, 1.0)),
        ),
    )
    unreachable = PoseSolution(
        position=(1000.0, 1000.0, 1000.0),
        tool_axis=(0.0, 0.0, 1.0),
        homogeneous_transform=(
            (1.0, 0.0, 0.0, 1000.0),
            (0.0, 1.0, 0.0, 1000.0),
            (0.0, 0.0, 1.0, 1000.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )

    result = inverse_kinematics(profile, unreachable)

    assert result.status == "SearchInconclusive"
    assert result.proof == "numerical-search-exhausted"
    assert result.solutions == ()
