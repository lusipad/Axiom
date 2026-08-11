from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, cast

import numpy as np
from scipy.optimize import least_squares  # type: ignore[import-untyped]

from .f2_models import (
    AxisLimitObservation,
    AxisLimits,
    AxisWrapState,
    FreeAxisParameter,
    IKSolution,
    KinematicResidual,
    MachineAxis,
    MachineProfile,
    RigidTransform,
    SingularityIndicator,
)


_EPSILON = 1e-12
_LIMIT_TOLERANCE = 1e-9
_SINGULAR_TOLERANCE = 1e-8
_JACOBIAN_LINEAR_STEP_MM = 1e-5
_JACOBIAN_ROTARY_STEP_RAD = 1e-7
_POSITION_TOLERANCE_MM = 1e-6
_ORIENTATION_TOLERANCE_RAD = 1e-9
_POSITION_RESIDUAL_SCALE_MM = 1.0
_ORIENTATION_RESIDUAL_SCALE_RAD = 1.0
_NUMERIC_EVIDENCE_SIGNIFICANT_DIGITS = 12
_DEFAULT_TOOL_OFFSET = (0.0, 0.0, -100.0)
_LINEAR_LIMITS = (-500.0, 500.0)
_TILT_LIMITS = (-2.0 * math.pi / 3.0, 2.0 * math.pi / 3.0)
_SPIN_LIMITS = (-2.0 * math.pi, 2.0 * math.pi)
_STANDARD_PROFILE_IDS = {
    "table-table-ac": "five-axis.machine-profile.canonical-table-table-ac@1",
    "head-table-workpiece-c-tool-b": "five-axis.machine-profile.canonical-head-table-workpiece-c-tool-b@1",
    "head-head-cb": "five-axis.machine-profile.canonical-head-head-cb@1",
}
_STANDARD_KIND_BY_PROFILE_ID = {profile_id: kind for kind, profile_id in _STANDARD_PROFILE_IDS.items()}


class KinematicsError(ValueError):
    """Raised when a kinematics artifact cannot be evaluated deterministically."""


def canonical_numeric_evidence(value: float) -> float:
    return float(f"{value:.{_NUMERIC_EVIDENCE_SIGNIFICANT_DIGITS}g}")


@dataclass(frozen=True)
class AxisLimitSpec:
    lower: float = -math.inf
    upper: float = math.inf


@dataclass(frozen=True)
class AxisSpec:
    axis_id: str
    axis_order: int
    joint_type: str
    axis_symbol: str
    semantic_role: str
    installation_side: str
    direction: tuple[float, float, float]
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    sign: float = 1.0
    zero_position: float = 0.0
    periodic: bool = False
    limits: AxisLimitSpec = AxisLimitSpec()


@dataclass(frozen=True)
class RigidTransformSpec:
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_quaternion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)


@dataclass(frozen=True)
class MachineProfileSpec:
    profile_id: str
    topology: str
    axes: tuple[AxisSpec, ...]
    workpiece_frame: RigidTransformSpec = RigidTransformSpec()
    tool_mount_frame: RigidTransformSpec = RigidTransformSpec(translation=_DEFAULT_TOOL_OFFSET)
    profile_version: str = "1"


@dataclass(frozen=True)
class PoseSolution:
    position: tuple[float, float, float]
    tool_axis: tuple[float, float, float]
    homogeneous_transform: tuple[tuple[float, float, float, float], ...]


@dataclass(frozen=True)
class JacobianEvidence:
    matrix: tuple[tuple[float, ...], ...]
    singular_values: tuple[float, ...]
    minimum_singular_value: float
    singular: bool
    method_id: str
    position_scale_mm: float
    orientation_scale_rad: float
    linear_step_mm: float
    rotary_step_rad: float
    singular_tolerance: float


@dataclass(frozen=True)
class IKSolutionCandidate:
    solution_id: str
    branch_id: str
    joint_values: tuple[tuple[str, float], ...]
    wrap_state: tuple[AxisWrapState, ...]
    axis_limit_state: tuple[AxisLimitObservation, ...]
    residuals: tuple[KinematicResidual, ...]
    singularity: JacobianEvidence
    within_limits: bool
    solver_kind: str
    evidence_level: Literal["Exact", "Validated"]
    free_parameters: tuple[tuple[str, float, float, Literal["rad"]], ...] = ()
    solver_status: int | None = None
    solver_evaluations: int | None = None


@dataclass(frozen=True)
class IKSearchResult:
    status: str
    solutions: tuple[IKSolutionCandidate, ...]
    proof: str
    policy_id: str


def build_canonical_table_table_ac_profile(
) -> MachineProfile:
    return _build_canonical_profile(
        profile_id=_STANDARD_PROFILE_IDS["table-table-ac"],
        topology="dual-table",
        rotary_axes=(
            ("A", "workpiece-rotary-primary", "workpiece", (1.0, 0.0, 0.0), False, _TILT_LIMITS),
            ("C", "workpiece-rotary-secondary", "workpiece", (0.0, 0.0, 1.0), True, _SPIN_LIMITS),
        ),
    )


def build_canonical_head_table_bc_profile(
) -> MachineProfile:
    return _build_canonical_profile(
        profile_id=_STANDARD_PROFILE_IDS["head-table-workpiece-c-tool-b"],
        topology="head-table",
        rotary_axes=(
            ("C", "workpiece-rotary-primary", "workpiece", (0.0, 0.0, 1.0), True, _SPIN_LIMITS),
            ("B", "tool-rotary-primary", "tool", (0.0, 1.0, 0.0), False, _TILT_LIMITS),
        ),
    )


def build_canonical_head_head_cb_profile(
) -> MachineProfile:
    return _build_canonical_profile(
        profile_id=_STANDARD_PROFILE_IDS["head-head-cb"],
        topology="dual-head",
        rotary_axes=(
            ("C", "tool-rotary-primary", "tool", (0.0, 0.0, 1.0), True, _SPIN_LIMITS),
            ("B", "tool-rotary-secondary", "tool", (0.0, 1.0, 0.0), False, _TILT_LIMITS),
        ),
    )


def build_general_machine_profile(
    *,
    profile_id: str,
    topology: Literal["dual-table", "head-table", "dual-head"],
    axes: Iterable[MachineAxis | AxisSpec | Mapping[str, Any] | Any],
    workpiece_frame: RigidTransformSpec | Mapping[str, Any] | Any | None = None,
    tool_mount_frame: RigidTransformSpec | Mapping[str, Any] | Any | None = None,
    profile_version: int = 1,
) -> MachineProfile:
    axis_views = tuple(sorted((_coerce_axis_spec(axis) for axis in axes), key=lambda item: item.axis_order))
    rotary_side_counts = {"workpiece": 0, "tool": 0}
    previous_by_side: dict[str, str] = {}
    contract_axes: list[MachineAxis] = []
    for view in axis_views:
        side = view.installation_side
        if side not in rotary_side_counts:
            raise KinematicsError("installationSide must be workpiece or tool")
        contract_side = cast(Literal["workpiece", "tool"], side)
        parent_axis_id = previous_by_side.get(side)
        if view.joint_type == "linear":
            semantic_role = f"linear-{view.axis_symbol.lower()}"
            unit = "mm"
            joint_type = "prismatic"
        elif view.joint_type == "rotary":
            suffix = "primary" if rotary_side_counts[side] == 0 else "secondary"
            semantic_role = f"{side}-rotary-{suffix}"
            unit = "rad"
            joint_type = "revolute"
        else:
            raise KinematicsError(f"unsupported joint type: {view.joint_type}")
        if not math.isfinite(view.limits.lower) or not math.isfinite(view.limits.upper):
            raise KinematicsError("general MachineProfile axes require finite limits")
        contract_axes.append(
            MachineAxis(
                axisId=view.axis_id,
                axisOrder=view.axis_order,
                jointType=cast(Literal["prismatic", "revolute"], joint_type),
                axisSymbol=cast(Literal["X", "Y", "Z", "A", "B", "C"], view.axis_symbol),
                semanticRole=cast(
                    Literal[
                        "linear-x",
                        "linear-y",
                        "linear-z",
                        "workpiece-rotary-primary",
                        "workpiece-rotary-secondary",
                        "tool-rotary-primary",
                        "tool-rotary-secondary",
                    ],
                    semantic_role,
                ),
                parentAxisId=parent_axis_id,
                origin=view.origin,
                direction=view.direction,
                installationSide=contract_side,
                sign="positive" if view.sign >= 0.0 else "negative",
                zeroPosition=view.zero_position,
                periodic=view.periodic,
                limits=AxisLimits(
                    lower=view.limits.lower,
                    upper=view.limits.upper,
                    unit=cast(Literal["mm", "rad"], unit),
                ),
            )
        )
        if view.joint_type == "rotary":
            rotary_side_counts[side] += 1
        previous_by_side[side] = view.axis_id
    workpiece = _coerce_rigid_transform(workpiece_frame)
    tool = _coerce_rigid_transform(tool_mount_frame, default_translation=_DEFAULT_TOOL_OFFSET)
    return MachineProfile(
        artifactType="five-axis.machine-profile",
        schemaVersion=1,
        profileId=profile_id,
        profileVersion=profile_version,
        topology=topology,
        axes=tuple(contract_axes),
        workpieceFrame=RigidTransform(
            transformId="frame.workpiece",
            translation=workpiece.translation,
            rotationQuaternion=workpiece.rotation_quaternion,
        ),
        toolMountFrame=RigidTransform(
            transformId="frame.tool-mount",
            translation=tool.translation,
            rotationQuaternion=tool.rotation_quaternion,
        ),
    )


def forward_kinematics(
    profile: MachineProfileSpec | Mapping[str, Any] | Any,
    joint_values: Mapping[str, float] | Any,
) -> PoseSolution:
    profile_spec = _coerce_machine_profile(profile)
    ordered_joint_values = _coerce_joint_values(profile_spec, joint_values)
    transform = task_transform(profile_spec, ordered_joint_values)
    return PoseSolution(
        position=_tuple3(transform[:3, 3]),
        tool_axis=_tuple3(transform[:3, 2]),
        homogeneous_transform=_matrix_tuple(transform),
    )


def task_transform(
    profile: MachineProfileSpec | Mapping[str, Any] | Any,
    joint_values: Mapping[str, float] | Any,
) -> np.ndarray:
    profile_spec = _coerce_machine_profile(profile)
    ordered_joint_values = _coerce_joint_values(profile_spec, joint_values)
    world_from_workpiece = _workpiece_chain_transform(profile_spec, ordered_joint_values)
    world_from_tool = _tool_chain_transform(profile_spec, ordered_joint_values)
    return np.linalg.inv(world_from_workpiece) @ world_from_tool


def jacobian_evidence(
    profile: MachineProfileSpec | Mapping[str, Any] | Any,
    joint_values: Mapping[str, float] | Any,
    *,
    singular_tolerance: float = _SINGULAR_TOLERANCE,
) -> JacobianEvidence:
    profile_spec = _coerce_machine_profile(profile)
    ordered_joint_values = _coerce_joint_values(profile_spec, joint_values)
    columns: list[np.ndarray] = []
    for axis in profile_spec.axes:
        step = _JACOBIAN_LINEAR_STEP_MM if axis.joint_type == "linear" else _JACOBIAN_ROTARY_STEP_RAD
        lower = dict(ordered_joint_values)
        upper = dict(ordered_joint_values)
        lower[axis.axis_id] -= step
        upper[axis.axis_id] += step
        lower_pose = forward_kinematics(profile_spec, lower)
        upper_pose = forward_kinematics(profile_spec, upper)
        lower_vector = np.concatenate(
            (
                np.asarray(lower_pose.position) / _POSITION_RESIDUAL_SCALE_MM,
                np.asarray(lower_pose.tool_axis) / (2.0 * math.sin(_ORIENTATION_RESIDUAL_SCALE_RAD * 0.5)),
            )
        )
        upper_vector = np.concatenate(
            (
                np.asarray(upper_pose.position) / _POSITION_RESIDUAL_SCALE_MM,
                np.asarray(upper_pose.tool_axis) / (2.0 * math.sin(_ORIENTATION_RESIDUAL_SCALE_RAD * 0.5)),
            )
        )
        columns.append((upper_vector - lower_vector) / (2.0 * step))
    matrix = np.stack(columns, axis=1) if columns else np.zeros((6, 0), dtype=np.float64)
    raw_singular_values = tuple(float(value) for value in np.linalg.svd(matrix, compute_uv=False))
    raw_minimum = raw_singular_values[-1] if raw_singular_values else math.inf
    singular_values = tuple(canonical_numeric_evidence(value) for value in raw_singular_values)
    minimum = singular_values[-1] if singular_values else math.inf
    return JacobianEvidence(
        matrix=tuple(tuple(float(value) for value in row) for row in matrix.tolist()),
        singular_values=singular_values,
        minimum_singular_value=float(minimum),
        singular=bool(raw_minimum <= singular_tolerance),
        method_id="five-axis.central-difference-scaled-jacobian@1",
        position_scale_mm=_POSITION_RESIDUAL_SCALE_MM,
        orientation_scale_rad=_ORIENTATION_RESIDUAL_SCALE_RAD,
        linear_step_mm=_JACOBIAN_LINEAR_STEP_MM,
        rotary_step_rad=_JACOBIAN_ROTARY_STEP_RAD,
        singular_tolerance=singular_tolerance,
    )


def inverse_kinematics(
    profile: MachineProfileSpec | Mapping[str, Any] | Any,
    target: PoseSolution | Mapping[str, Any] | Any,
    *,
    position_tolerance_mm: float = _POSITION_TOLERANCE_MM,
    orientation_tolerance_rad: float = _ORIENTATION_TOLERANCE_RAD,
) -> IKSearchResult:
    profile_spec = _coerce_machine_profile(profile)
    target_spec = _coerce_pose_solution(target)
    standard_kind = _standard_kind(profile_spec)
    if standard_kind is not None:
        return _inverse_kinematics_standard(
            profile_spec,
            target_spec,
            standard_kind=standard_kind,
            position_tolerance_mm=position_tolerance_mm,
            orientation_tolerance_rad=orientation_tolerance_rad,
        )
    return _inverse_kinematics_numeric(
        profile_spec,
        target_spec,
        position_tolerance_mm=position_tolerance_mm,
        orientation_tolerance_rad=orientation_tolerance_rad,
    )


def ik_candidate_to_contract(candidate: IKSolutionCandidate, *, sigma: float) -> IKSolution:
    maximum = max(candidate.singularity.singular_values, default=0.0)
    minimum = candidate.singularity.minimum_singular_value
    condition = canonical_numeric_evidence(maximum / minimum) if minimum > _EPSILON else None
    return IKSolution(
        solutionId=candidate.solution_id,
        sigma=sigma,
        branchId=candidate.branch_id,
        jointValues=tuple(value for _, value in candidate.joint_values),
        wrapState=candidate.wrap_state,
        freeParameters=tuple(
            FreeAxisParameter(
                axisId=axis_id,
                lower=lower,
                upper=upper,
                unit=unit,
                semantics="continuous-singular-family@1",
            )
            for axis_id, lower, upper, unit in candidate.free_parameters
        ),
        axisLimitState=candidate.axis_limit_state,
        residuals=candidate.residuals,
        singularity=SingularityIndicator(
            status="singular" if candidate.singularity.singular else "regular",
            conditioningMetric=condition,
            minimumSingularValue=minimum,
        ),
        withinLimits=candidate.within_limits,
    )


def _standard_kind(profile: MachineProfileSpec) -> str | None:
    kind = _STANDARD_KIND_BY_PROFILE_ID.get(profile.profile_id)
    if kind is None:
        return None
    expected_profile = {
        "table-table-ac": build_canonical_table_table_ac_profile,
        "head-table-workpiece-c-tool-b": build_canonical_head_table_bc_profile,
        "head-head-cb": build_canonical_head_head_cb_profile,
    }[kind]()
    if profile != _coerce_machine_profile(expected_profile):
        raise KinematicsError("canonical MachineProfile content does not match its versioned profileId")
    return kind


def _build_canonical_profile(
    *,
    profile_id: str,
    topology: Literal["dual-table", "head-table", "dual-head"],
    rotary_axes: tuple[
        tuple[
            Literal["A", "B", "C"],
            str,
            Literal["workpiece", "tool"],
            tuple[float, float, float],
            bool,
            tuple[float, float],
        ],
        ...,
    ],
) -> MachineProfile:
    axis_specs = [
        AxisSpec("X", 0, "linear", "X", "linear-x", "tool", (1.0, 0.0, 0.0), limits=AxisLimitSpec(*_LINEAR_LIMITS)),
        AxisSpec("Y", 1, "linear", "Y", "linear-y", "tool", (0.0, 1.0, 0.0), limits=AxisLimitSpec(*_LINEAR_LIMITS)),
        AxisSpec("Z", 2, "linear", "Z", "linear-z", "tool", (0.0, 0.0, 1.0), limits=AxisLimitSpec(*_LINEAR_LIMITS)),
    ]
    for index, (axis_id, semantic_role, side, direction, periodic, limits) in enumerate(rotary_axes, start=3):
        axis_specs.append(
            AxisSpec(
                axis_id,
                index,
                "rotary",
                axis_id,
                semantic_role,
                side,
                direction,
                periodic=periodic,
                limits=AxisLimitSpec(*limits),
            )
        )
    return build_general_machine_profile(
        profile_id=profile_id,
        profile_version=1,
        topology=topology,
        axes=axis_specs,
        workpiece_frame=RigidTransformSpec(),
        tool_mount_frame=RigidTransformSpec(translation=_DEFAULT_TOOL_OFFSET),
    )


def _inverse_kinematics_standard(
    profile: MachineProfileSpec,
    target: PoseSolution,
    *,
    standard_kind: str,
    position_tolerance_mm: float,
    orientation_tolerance_rad: float,
) -> IKSearchResult:
    tool_axis = _normalize_vector(np.asarray(target.tool_axis, dtype=np.float64))
    branch_seeds = _standard_rotary_branch_seeds(standard_kind, tool_axis)
    if not branch_seeds:
        return IKSearchResult(
            status="NoSolutionProven",
            solutions=(),
            proof="orientation-unreachable",
            policy_id="five-axis.closed-form-ik-policy@1",
        )
    target_transform = np.asarray(target.homogeneous_transform, dtype=np.float64)
    rotary_axes = {axis.axis_id: axis for axis in profile.axes if axis.joint_type == "rotary"}
    solutions: list[IKSolutionCandidate] = []
    for base_branch_id, base_values, free_axis_ids in branch_seeds:
        wrap_options: list[list[tuple[str, float, int]]] = []
        for axis_id, angle in base_values.items():
            axis = rotary_axes[axis_id]
            options = _enumerate_rotary_wraps(axis, angle)
            if axis_id in free_axis_ids and options:
                options = (min(options, key=lambda item: (abs(item[0]), item[0])),)
            if not options:
                wrap_options = []
                break
            wrap_options.append([(axis_id, value, wrap_index) for value, wrap_index in options])
        if not wrap_options:
            continue
        for wrap_variant in _cartesian_product(wrap_options):
            candidate = {axis.axis_id: 0.0 for axis in profile.axes}
            wrap_state: dict[str, int] = {}
            for axis_id, value, wrap_index in wrap_variant:
                candidate[axis_id] = value
                wrap_state[axis_id] = wrap_index
            world_from_workpiece = _workpiece_chain_transform(profile, candidate)
            tool_post_linear = _tool_chain_post_linear_transform(profile, candidate)
            linear_translation = world_from_workpiece @ target_transform
            translation = linear_translation[:3, 3] - tool_post_linear[:3, 3]
            candidate["X"], candidate["Y"], candidate["Z"] = (float(translation[0]), float(translation[1]), float(translation[2]))
            if not _within_limits(profile, candidate):
                continue
            pose = forward_kinematics(profile, candidate)
            residuals = _pose_residuals(pose, target)
            evidence = jacobian_evidence(profile, candidate)
            if (
                residuals["five-axis.position-residual.max@1"] > position_tolerance_mm
                or residuals["five-axis.orientation-residual.max@1"] > orientation_tolerance_rad
            ):
                continue
            solutions.append(
                IKSolutionCandidate(
                    solution_id=f"{base_branch_id}-{'-'.join(str(wrap_state.get(axis_id, 0)) for axis_id in sorted(base_values))}",
                    branch_id=base_branch_id,
                    joint_values=tuple((axis.axis_id, float(candidate[axis.axis_id])) for axis in profile.axes),
                    wrap_state=tuple(
                        AxisWrapState(axisId=axis_id, turns=wrap_state.get(axis_id, 0))
                        for axis_id in sorted(base_values)
                        if rotary_axes[axis_id].periodic
                    ),
                    axis_limit_state=tuple(
                        _axis_limit_observation(axis, candidate[axis.axis_id]) for axis in profile.axes
                    ),
                    residuals=_residual_models(residuals),
                    singularity=evidence,
                    within_limits=True,
                    solver_kind="closed-form",
                    evidence_level="Exact",
                    free_parameters=tuple(
                        (axis_id, rotary_axes[axis_id].limits.lower, rotary_axes[axis_id].limits.upper, "rad")
                        for axis_id in free_axis_ids
                    ),
                )
            )
    deduplicated = _deduplicate_solutions(solutions)
    if deduplicated:
        return IKSearchResult(
            status="SolutionsFound",
            solutions=deduplicated,
            proof="closed-form-complete",
            policy_id="five-axis.closed-form-ik-policy@1",
        )
    return IKSearchResult(
        status="NoSolutionProven",
        solutions=(),
        proof="closed-form-enumeration-exhausted",
        policy_id="five-axis.closed-form-ik-policy@1",
    )


def _inverse_kinematics_numeric(
    profile: MachineProfileSpec,
    target: PoseSolution,
    *,
    position_tolerance_mm: float,
    orientation_tolerance_rad: float,
) -> IKSearchResult:
    axis_ids = [axis.axis_id for axis in profile.axes]
    bounds_lower = np.asarray([axis.limits.lower for axis in profile.axes], dtype=np.float64)
    bounds_upper = np.asarray([axis.limits.upper for axis in profile.axes], dtype=np.float64)
    target_position = np.asarray(target.position, dtype=np.float64)
    target_axis = _normalize_vector(np.asarray(target.tool_axis, dtype=np.float64))
    prepared_seeds = _prepare_numeric_seeds(profile)
    solutions: list[IKSolutionCandidate] = []

    def residual_vector(values: np.ndarray) -> np.ndarray:
        current = {axis_id: float(value) for axis_id, value in zip(axis_ids, values)}
        pose = forward_kinematics(profile, current)
        position_error = np.asarray(pose.position, dtype=np.float64) - target_position
        axis_error = np.asarray(pose.tool_axis, dtype=np.float64) - target_axis
        return np.concatenate(
            (
                position_error / _POSITION_RESIDUAL_SCALE_MM,
                axis_error / (2.0 * math.sin(_ORIENTATION_RESIDUAL_SCALE_RAD * 0.5)),
            )
        )

    for index, seed in enumerate(prepared_seeds):
        result = least_squares(
            residual_vector,
            seed,
            bounds=(bounds_lower, bounds_upper),
            xtol=1e-12,
            ftol=1e-12,
            gtol=1e-12,
            max_nfev=200,
            method="trf",
        )
        candidate = {axis_id: float(value) for axis_id, value in zip(axis_ids, result.x)}
        pose = forward_kinematics(profile, candidate)
        residuals = _pose_residuals(pose, target)
        if (
            residuals["five-axis.position-residual.max@1"] > position_tolerance_mm
            or residuals["five-axis.orientation-residual.max@1"] > orientation_tolerance_rad
        ):
            continue
        evidence = jacobian_evidence(profile, candidate)
        solutions.append(
            IKSolutionCandidate(
                solution_id=f"numeric-{index}",
                branch_id="numeric-search",
                joint_values=tuple((axis.axis_id, float(candidate[axis.axis_id])) for axis in profile.axes),
                wrap_state=tuple(
                    AxisWrapState(axisId=axis.axis_id, turns=_wrap_index(axis, candidate[axis.axis_id]))
                    for axis in profile.axes
                    if axis.periodic
                ),
                axis_limit_state=tuple(
                    _axis_limit_observation(axis, candidate[axis.axis_id]) for axis in profile.axes
                ),
                residuals=_residual_models(residuals),
                singularity=evidence,
                within_limits=_within_limits(profile, candidate),
                solver_kind="numerical-least-squares",
                evidence_level="Validated",
                solver_status=int(result.status),
                solver_evaluations=int(result.nfev),
            )
        )
    deduplicated = _deduplicate_solutions(solutions)
    if deduplicated:
        return IKSearchResult(
            status="SolutionsFound",
            solutions=deduplicated,
            proof="numerical-search",
            policy_id="five-axis.numeric-ik-policy@1",
        )
    return IKSearchResult(
        status="SearchInconclusive",
        solutions=(),
        proof="numerical-search-exhausted",
        policy_id="five-axis.numeric-ik-policy@1",
    )


def _prepare_numeric_seeds(
    profile: MachineProfileSpec,
) -> tuple[np.ndarray, ...]:
    lower = np.asarray([axis.limits.lower for axis in profile.axes], dtype=np.float64)
    upper = np.asarray([axis.limits.upper for axis in profile.axes], dtype=np.float64)
    if not np.all(np.isfinite(lower)) or not np.all(np.isfinite(upper)):
        raise KinematicsError("numeric IK requires finite axis bounds")
    midpoint = (lower + upper) * 0.5
    zero = np.clip(np.zeros(len(profile.axes), dtype=np.float64), lower, upper)
    lower_quartile = lower * 0.75 + upper * 0.25
    upper_quartile = lower * 0.25 + upper * 0.75
    alternating = np.asarray(
        [lower_quartile[index] if index % 2 == 0 else upper_quartile[index] for index in range(len(profile.axes))],
        dtype=np.float64,
    )
    defaults = [zero, midpoint, lower_quartile, upper_quartile, alternating]
    unique: list[np.ndarray] = []
    for seed in defaults:
        if not any(np.allclose(seed, existing, atol=1e-12, rtol=0.0) for existing in unique):
            unique.append(seed)
    return tuple(unique)


def _standard_rotary_branch_seeds(
    topology: str,
    tool_axis: np.ndarray,
) -> tuple[tuple[str, dict[str, float], tuple[str, ...]], ...]:
    x, y, z = (float(value) for value in tool_axis)
    radial = math.hypot(x, y)
    if topology == "table-table-ac":
        if radial <= _EPSILON:
            return (("ac-singular", {"A": 0.0, "C": 0.0}, ("C",)),)
        base_a = math.atan2(radial, z)
        base_c = math.atan2(x, y)
        return (
            ("ac-primary", {"A": base_a, "C": base_c}, ()),
            ("ac-secondary", {"A": -base_a, "C": _wrap_to_pi(base_c + math.pi)}, ()),
        )
    if topology == "head-table-workpiece-c-tool-b":
        if radial <= _EPSILON:
            return (("bc-singular", {"B": 0.0, "C": 0.0}, ("C",)),)
        base_b = math.atan2(radial, z)
        base_c = math.atan2(-y, x)
        return (
            ("bc-primary", {"B": base_b, "C": base_c}, ()),
            ("bc-secondary", {"B": -base_b, "C": _wrap_to_pi(base_c + math.pi)}, ()),
        )
    if topology == "head-head-cb":
        if radial <= _EPSILON:
            return (("cb-singular", {"B": 0.0, "C": 0.0}, ("C",)),)
        base_b = math.atan2(radial, z)
        base_c = math.atan2(y, x)
        return (
            ("cb-primary", {"B": base_b, "C": base_c}, ()),
            ("cb-secondary", {"B": -base_b, "C": _wrap_to_pi(base_c + math.pi)}, ()),
        )
    raise KinematicsError(f"unsupported standard topology: {topology}")


def _enumerate_rotary_wraps(axis: AxisSpec, base_angle: float) -> tuple[tuple[float, int], ...]:
    if not axis.periodic:
        value = axis.sign * base_angle + axis.zero_position
        if not _in_limit(axis.limits, value):
            return ()
        return ((value, 0),)
    scaled = axis.sign * base_angle + axis.zero_position
    if not math.isfinite(axis.limits.lower) or not math.isfinite(axis.limits.upper):
        return ((scaled, 0),)
    minimum = math.ceil((axis.limits.lower - scaled - _LIMIT_TOLERANCE) / (2.0 * math.pi))
    maximum = math.floor((axis.limits.upper - scaled + _LIMIT_TOLERANCE) / (2.0 * math.pi))
    variants = []
    for wrap_index in range(minimum, maximum + 1):
        value = scaled + wrap_index * 2.0 * math.pi
        if _in_limit(axis.limits, value):
            variants.append((float(value), int(wrap_index)))
    return tuple(variants)


def _workpiece_chain_transform(profile: MachineProfileSpec, joint_values: Mapping[str, float]) -> np.ndarray:
    transform = _transform_from_rigid(profile.workpiece_frame)
    for axis in _side_axes(profile, "workpiece"):
        transform = transform @ _axis_transform(axis, joint_values[axis.axis_id])
    return transform


def _tool_chain_transform(profile: MachineProfileSpec, joint_values: Mapping[str, float]) -> np.ndarray:
    transform = np.eye(4, dtype=np.float64)
    for axis in _side_axes(profile, "tool"):
        transform = transform @ _axis_transform(axis, joint_values[axis.axis_id])
    return transform @ _transform_from_rigid(profile.tool_mount_frame)


def _tool_chain_post_linear_transform(profile: MachineProfileSpec, joint_values: Mapping[str, float]) -> np.ndarray:
    transform = np.eye(4, dtype=np.float64)
    for axis in _side_axes(profile, "tool"):
        value = 0.0 if axis.joint_type == "linear" else joint_values[axis.axis_id]
        transform = transform @ _axis_transform(axis, value)
    return transform @ _transform_from_rigid(profile.tool_mount_frame)


def _axis_transform(axis: AxisSpec, commanded_value: float) -> np.ndarray:
    physical_value = axis.sign * (commanded_value - axis.zero_position)
    if axis.joint_type == "linear":
        return _translation_matrix(_scale_vector(axis.direction, physical_value))
    if axis.joint_type == "rotary":
        return _transform_about_axis(axis.origin, axis.direction, physical_value)
    raise KinematicsError(f"unsupported joint type: {axis.joint_type}")


def _transform_about_axis(origin: tuple[float, float, float], direction: tuple[float, float, float], angle: float) -> np.ndarray:
    return _translation_matrix(origin) @ _rotation_transform(direction, angle) @ _translation_matrix(_scale_vector(origin, -1.0))


def _rotation_transform(direction: tuple[float, float, float], angle: float) -> np.ndarray:
    axis = _normalize_vector(np.asarray(direction, dtype=np.float64))
    x, y, z = axis
    c = math.cos(angle)
    s = math.sin(angle)
    t = 1.0 - c
    matrix = np.array(
        (
            (t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0.0),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0.0),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )
    return matrix


def _transform_from_rigid(transform: RigidTransformSpec) -> np.ndarray:
    quaternion = np.asarray(transform.rotation_quaternion, dtype=np.float64)
    quaternion = quaternion / np.linalg.norm(quaternion)
    x, y, z, w = (float(value) for value in quaternion)
    rotation = np.array(
        (
            (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w), 0.0),
            (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w), 0.0),
            (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )
    rotation[:3, 3] = np.asarray(transform.translation, dtype=np.float64)
    return rotation


def _translation_matrix(vector: tuple[float, float, float]) -> np.ndarray:
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, 3] = np.asarray(vector, dtype=np.float64)
    return matrix


def _coerce_machine_profile(profile: MachineProfileSpec | Mapping[str, Any] | Any) -> MachineProfileSpec:
    if isinstance(profile, MachineProfileSpec):
        return profile
    if not isinstance(profile, MachineProfile):
        if isinstance(profile, Mapping):
            profile = MachineProfile.model_validate(profile)
        elif hasattr(profile, "model_dump"):
            profile = MachineProfile.model_validate(profile.model_dump(mode="json", by_alias=True))
        else:
            raise KinematicsError("profile must conform to five-axis.machine-profile@1")
    return MachineProfileSpec(
        profile_id=profile.profile_id,
        topology=profile.topology,
        axes=tuple(_coerce_axis_spec(axis) for axis in profile.axes),
        workpiece_frame=_coerce_rigid_transform(profile.workpiece_frame),
        tool_mount_frame=_coerce_rigid_transform(profile.tool_mount_frame, default_translation=_DEFAULT_TOOL_OFFSET),
        profile_version=str(profile.profile_version),
    )


def _coerce_axis_spec(axis: AxisSpec | Mapping[str, Any] | Any) -> AxisSpec:
    if isinstance(axis, AxisSpec):
        return axis
    raw_joint_type = str(_lookup(axis, "jointType", "joint_type"))
    joint_type = {"prismatic": "linear", "revolute": "rotary"}.get(raw_joint_type, raw_joint_type)
    raw_sign = _lookup_optional(axis, "sign")
    if raw_sign in {None, "positive"}:
        sign = 1.0
    elif raw_sign == "negative":
        sign = -1.0
    else:
        sign = float(raw_sign)
    return AxisSpec(
        axis_id=str(_lookup(axis, "axisId", "axis_id")),
        axis_order=int(_lookup(axis, "axisOrder", "axis_order")),
        joint_type=joint_type,
        axis_symbol=str(_lookup(axis, "axisSymbol", "axis_symbol")),
        semantic_role=str(_lookup(axis, "semanticRole", "semantic_role")),
        installation_side=str(_lookup(axis, "installationSide", "installation_side")),
        direction=_tuple3(_lookup(axis, "direction")),
        origin=_tuple3(_lookup_optional(axis, "origin") or (0.0, 0.0, 0.0)),
        sign=sign,
        zero_position=float(_lookup_optional(axis, "zeroPosition", "zero_position") or 0.0),
        periodic=bool(_lookup_optional(axis, "periodic") or False),
        limits=_coerce_limit(_lookup_optional(axis, "limits")),
    )


def _coerce_rigid_transform(
    transform: RigidTransformSpec | Mapping[str, Any] | Any | None,
    *,
    default_translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> RigidTransformSpec:
    if transform is None:
        return RigidTransformSpec(translation=default_translation)
    if isinstance(transform, RigidTransformSpec):
        return transform
    return RigidTransformSpec(
        translation=_tuple3(_lookup_optional(transform, "translation") or default_translation),
        rotation_quaternion=_tuple4(
            _lookup_optional(transform, "rotationQuaternion", "rotation_quaternion") or (0.0, 0.0, 0.0, 1.0)
        ),
    )


def _coerce_pose_solution(target: PoseSolution | Mapping[str, Any] | Any) -> PoseSolution:
    if isinstance(target, PoseSolution):
        return target
    transform = _lookup_optional(target, "homogeneousTransform", "homogeneous_transform")
    if transform is not None:
        matrix = np.asarray(transform, dtype=np.float64)
        return PoseSolution(
            position=_tuple3(matrix[:3, 3]),
            tool_axis=_tuple3(matrix[:3, 2]),
            homogeneous_transform=_matrix_tuple(matrix),
        )
    position = _tuple3(_lookup(target, "position"))
    tool_axis = _normalize_vector(np.asarray(_lookup(target, "toolAxis", "tool_axis"), dtype=np.float64))
    matrix = _canonical_transform(position, tool_axis)
    return PoseSolution(position=position, tool_axis=_tuple3(tool_axis), homogeneous_transform=_matrix_tuple(matrix))


def _coerce_joint_values(profile: MachineProfileSpec, joint_values: Mapping[str, float] | Any) -> dict[str, float]:
    if isinstance(joint_values, Mapping):
        return {axis.axis_id: float(joint_values[axis.axis_id]) for axis in profile.axes}
    values = {}
    for axis in profile.axes:
        values[axis.axis_id] = float(_lookup(joint_values, axis.axis_id, axis.axis_id.lower()))
    return values


def _within_limits(profile: MachineProfileSpec, joint_values: Mapping[str, float]) -> bool:
    return all(_in_limit(axis.limits, joint_values[axis.axis_id]) for axis in profile.axes)


def _in_limit(limit: AxisLimitSpec, value: float) -> bool:
    return value >= limit.lower - _LIMIT_TOLERANCE and value <= limit.upper + _LIMIT_TOLERANCE


def _limit_state(
    axis: AxisSpec,
    value: float,
) -> Literal["within", "at-lower", "at-upper", "violated-lower", "violated-upper"]:
    if not _in_limit(axis.limits, value):
        return "violated-lower" if value < axis.limits.lower else "violated-upper"
    if math.isfinite(axis.limits.lower) and math.isclose(value, axis.limits.lower, abs_tol=_LIMIT_TOLERANCE):
        return "at-lower"
    if math.isfinite(axis.limits.upper) and math.isclose(value, axis.limits.upper, abs_tol=_LIMIT_TOLERANCE):
        return "at-upper"
    return "within"


def _axis_limit_observation(axis: AxisSpec, value: float) -> AxisLimitObservation:
    return AxisLimitObservation(
        axisId=axis.axis_id,
        status=_limit_state(axis, value),
        distanceToLower=value - axis.limits.lower,
        distanceToUpper=axis.limits.upper - value,
    )


def _residual_models(residuals: Mapping[str, float]) -> tuple[KinematicResidual, ...]:
    return (
        KinematicResidual(
            metricId="five-axis.position-residual.max@1",
            value=residuals["five-axis.position-residual.max@1"],
            unit="mm",
        ),
        KinematicResidual(
            metricId="five-axis.orientation-residual.max@1",
            value=residuals["five-axis.orientation-residual.max@1"],
            unit="rad",
        ),
    )


def _wrap_index(axis: AxisSpec, value: float) -> int:
    if not axis.periodic:
        return 0
    reference = axis.zero_position
    return int(round((value - reference) / (2.0 * math.pi)))


def _pose_residuals(actual: PoseSolution, target: PoseSolution) -> dict[str, float]:
    position_error = np.linalg.norm(np.asarray(actual.position) - np.asarray(target.position))
    actual_axis = _normalize_vector(np.asarray(actual.tool_axis, dtype=np.float64))
    target_axis = _normalize_vector(np.asarray(target.tool_axis, dtype=np.float64))
    dot = float(np.clip(np.dot(actual_axis, target_axis), -1.0, 1.0))
    axis_error = math.acos(dot)
    return {
        "five-axis.position-residual.max@1": float(position_error),
        "five-axis.orientation-residual.max@1": float(axis_error),
    }


def _deduplicate_solutions(solutions: Iterable[IKSolutionCandidate]) -> tuple[IKSolutionCandidate, ...]:
    ordered = sorted(
        solutions,
        key=lambda item: (
            item.branch_id,
            tuple(value.turns for value in item.wrap_state),
            tuple(value for _, value in item.joint_values),
        ),
    )
    unique: list[IKSolutionCandidate] = []
    for candidate in ordered:
        if unique and _same_joint_values(unique[-1], candidate):
            continue
        unique.append(candidate)
    return tuple(unique)


def _same_joint_values(left: IKSolutionCandidate, right: IKSolutionCandidate) -> bool:
    return all(math.isclose(lv, rv, abs_tol=1e-9) for (_, lv), (_, rv) in zip(left.joint_values, right.joint_values))


def _side_axes(profile: MachineProfileSpec, side: str) -> tuple[AxisSpec, ...]:
    return tuple(axis for axis in profile.axes if axis.installation_side == side)


def _lookup(obj: Mapping[str, Any] | Any, *names: str) -> Any:
    value = _lookup_optional(obj, *names)
    if value is None:
        raise KinematicsError(f"missing required field among {names!r}")
    return value


def _lookup_optional(obj: Mapping[str, Any] | Any, *names: str) -> Any:
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj:
                return obj[name]
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _coerce_limit(
    value: tuple[float, float] | Mapping[str, Any] | AxisLimitSpec | AxisLimits | None,
) -> AxisLimitSpec:
    if value is None:
        return AxisLimitSpec()
    if isinstance(value, AxisLimitSpec):
        return value
    if isinstance(value, AxisLimits):
        return AxisLimitSpec(lower=value.lower, upper=value.upper)
    if isinstance(value, Mapping):
        lower = value.get("lower", -math.inf)
        upper = value.get("upper", math.inf)
        return AxisLimitSpec(lower=float(lower), upper=float(upper))
    lower, upper = value
    return AxisLimitSpec(lower=float(lower), upper=float(upper))


def _canonical_transform(position: tuple[float, float, float], tool_axis: np.ndarray) -> np.ndarray:
    z_axis = _normalize_vector(tool_axis)
    reference = np.array((0.0, 0.0, 1.0), dtype=np.float64)
    if abs(float(np.dot(reference, z_axis))) > 0.95:
        reference = np.array((1.0, 0.0, 0.0), dtype=np.float64)
    x_axis = np.cross(reference, z_axis)
    x_axis = _normalize_vector(x_axis)
    y_axis = _normalize_vector(np.cross(z_axis, x_axis))
    transform = np.eye(4, dtype=np.float64)
    transform[:3, 0] = x_axis
    transform[:3, 1] = y_axis
    transform[:3, 2] = z_axis
    transform[:3, 3] = np.asarray(position, dtype=np.float64)
    return transform


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= _EPSILON:
        raise KinematicsError("zero vector is not a valid axis")
    return vector / norm


def _matrix_tuple(matrix: np.ndarray) -> tuple[tuple[float, float, float, float], ...]:
    return tuple(cast(tuple[float, float, float, float], tuple(float(value) for value in row)) for row in matrix.tolist())


def _tuple3(value: Iterable[float]) -> tuple[float, float, float]:
    values = tuple(float(component) for component in value)
    if len(values) != 3:
        raise KinematicsError("expected a length-3 vector")
    return values


def _tuple4(value: Iterable[float]) -> tuple[float, float, float, float]:
    values = tuple(float(component) for component in value)
    if len(values) != 4:
        raise KinematicsError("expected a length-4 quaternion")
    return values


def _scale_vector(vector: tuple[float, float, float], scale: float) -> tuple[float, float, float]:
    return (vector[0] * scale, vector[1] * scale, vector[2] * scale)


def _wrap_to_pi(angle: float) -> float:
    wrapped = math.fmod(angle + math.pi, 2.0 * math.pi)
    if wrapped < 0.0:
        wrapped += 2.0 * math.pi
    return wrapped - math.pi


def _cartesian_product(options: list[list[tuple[str, float, int]]]) -> tuple[tuple[tuple[str, float, int], ...], ...]:
    if not options:
        return ()
    product: list[tuple[tuple[str, float, int], ...]] = [()]
    for items in options:
        expanded: list[tuple[tuple[str, float, int], ...]] = []
        for prefix in product:
            for item in items:
                expanded.append(prefix + (item,))
        product = expanded
    return tuple(product)
