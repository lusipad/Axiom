"""Three-layer CNC grey-box model and a synthetic CNC controller simulator.

Kernel `generic-fir-biquad@1` (see `GREYBOX_REQUIRED_PARAMETER_IDS`):
1. Layer 1 (analytical backbone):
   - Hard min-clipped speed envelopes (programmed feed, axis projection, centripetal,
     corner-rounding curvature, micro-segment lookahead braking distance).
   - Forward-backward acceleration-limited speed propagation and an empirical
     post-filter corner speed valley.
   - FIR sinc + 2nd-order Butterworth magnitude radial shrink on arcs.
   - Steady-state error expansion of a P-P cascade with velocity/acceleration
     feed-forward (`c_v`, `c_a`) and the resulting signed normal shift.
   Several terms carry empirical coefficients; they are engineering approximations,
   not exact laws.
2. Layer 2 (bounded calibration): `lsq_linear` / trust-region `least_squares` fit of the
   constants in `GreyBoxPhysicalConstants`. These are fitting coefficients; they are
   not guaranteed to equal the machine's physical quantities (identifiability is not
   checked yet).
3. Layer 3 (optional residual): low-dimensional ARD Matern-5/2 GP on the residual,
   enabled per metric only when it improves leave-one-out error (see parameter_learner).

`simulate_realistic_cnc_controller` is a SYNTHETIC test fixture. It shares structure
and constants with the kernel above, so agreement between the two is self-consistency,
not evidence about a real machine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from pydantic import Field
from scipy.optimize import least_squares, lsq_linear, minimize

from .benchmark import (
    AXES,
    CORNER_ANGLE_DEGREES,
    MICRO_SEGMENT_THRESHOLD_MM,
    BenchmarkArc,
    BenchmarkSample,
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncQualityReport,
    _arc_geometry,
    _segment_ends,
    benchmark_case_hash,
)
from .controller_profile import (
    CanonicalControlQuantities,
    ControllerProfile,
    default_generic_controller_profile,
)
from .models import AxiomModel
from .parameter_space import (
    CncParameterRegistry,
    SourceKind,
    default_cnc_parameter_registry,
    default_parameter_values,
)

_DEFAULT_GENERIC_PROFILE = default_generic_controller_profile()

# The grey-box kernel below encodes ONE controller architecture: tolerance-based corner
# blending, post-interpolation FIR + 2nd-order low-pass, and a P-P cascade with velocity /
# acceleration feed-forward. Its formulas read these parameter ids directly; a registry
# for a different CNC must map onto them (controller profile) or the kernel must refuse it,
# otherwise every unmapped parameter silently falls back to its default.
GREYBOX_KERNEL_ID = "generic-fir-biquad@1"
GREYBOX_REQUIRED_PARAMETER_IDS: tuple[str, ...] = (
    "g1.corner_tolerance_mm",
    "g1.small_seg_chord_tol_mm",
    "g1.lookahead_block_count",
    "g1.corner_angle_threshold_deg",
    "g1.collinear_merge_angle_deg",
    "g1.curvature_speed_clamp_factor",
    "g1.min_segment_length_mm",
    "g1.spline_degree",
    "g2.path_max_feed_override",
    "g2.path_tangential_acc_mm_s2",
    "g2.path_tangential_jerk_mm_s3",
    "g2.centripetal_acc_limit_mm_s2",
    "g2.axis_vel_limit_x",
    "g2.axis_vel_limit_y",
    "g2.axis_vel_limit_z",
    "g2.axis_acc_limit_x",
    "g2.axis_acc_limit_y",
    "g2.axis_acc_limit_z",
    "g2.fir_moving_avg_time_ms",
    "g2.biquad_lowpass_freq_hz",
    "g2.bell_acc_shape_factor",
    "g3.servo_kp_x",
    "g3.servo_kp_y",
    "g3.servo_kp_z",
    "g3.vel_feedforward_x",
    "g3.vel_feedforward_y",
    "g3.vel_feedforward_z",
    "g3.acc_feedforward_x",
    "g3.acc_feedforward_y",
    "g3.friction_comp_amp_x",
    "g3.friction_comp_amp_y",
    "g3.notch_filter_freq_hz",
)


def missing_greybox_parameter_ids(registry: CncParameterRegistry) -> tuple[str, ...]:
    """Kernel parameter ids that `registry` does not define (empty tuple means compatible)."""
    present = {p.parameter_id for p in registry.parameters}
    return tuple(pid for pid in GREYBOX_REQUIRED_PARAMETER_IDS if pid not in present)


@dataclass(frozen=True)
class PrimitiveSegmentSpec:
    index: int
    kind: Literal["line", "arc", "micro-cluster"]
    length_mm: float
    radius_mm: float  # inf for straight lines
    mean_chord_mm: float
    abs_unit_vec: tuple[float, float, float]


@dataclass(frozen=True)
class CornerSpec:
    vertex_index: int
    turn_angle_rad: float
    turn_angle_deg: float
    bisector_abs_vec: tuple[float, float, float]
    min_adjacent_length_mm: float


@dataclass(frozen=True)
class CaseGeometryProfile:
    case_id: str
    total_length_mm: float
    programmed_feed_mm_s: float
    sample_period_s: float
    axis_vel_limits: tuple[float, float, float]
    axis_acc_limits: tuple[float, float, float]
    segments: tuple[PrimitiveSegmentSpec, ...]
    corners: tuple[CornerSpec, ...]
    has_arcs: bool
    has_corners: bool
    has_micro_segments: bool
    has_xy_reversals: bool
    has_z_motion: bool


def extract_case_geometry_profile(case: CncBenchmarkCase) -> CaseGeometryProfile:
    """Extract pure geometric primitive structure from any CncBenchmarkCase (zero trace needed)."""
    path = np.asarray(case.reference_path, dtype=float)
    arcs_map: dict[int, BenchmarkArc] = {arc.segment_index: arc for arc in (case.reference_arcs or ())}
    ends = _segment_ends(path, arcs_map)

    primitives: list[PrimitiveSegmentSpec] = []
    micro_buf: list[tuple[int, float, np.ndarray]] = []
    has_arcs = False
    has_micro = False
    has_reversals = False
    has_z = bool(float(np.ptp(path[:, 2])) > 1e-6) if len(path) > 0 else False

    def _flush_micro() -> None:
        nonlocal has_micro
        if not micro_buf:
            return
        if len(micro_buf) < 3:
            for idx, seg_l, u_vec in micro_buf:
                primitives.append(
                    PrimitiveSegmentSpec(
                        index=idx,
                        kind="line",
                        length_mm=seg_l,
                        radius_mm=float("inf"),
                        mean_chord_mm=seg_l,
                        abs_unit_vec=(float(abs(u_vec[0])), float(abs(u_vec[1])), float(abs(u_vec[2]))),
                    )
                )
        else:
            has_micro = True
            lengths = [item[1] for item in micro_buf]
            mean_u = np.mean([np.abs(item[2]) for item in micro_buf], axis=0)
            primitives.append(
                PrimitiveSegmentSpec(
                    index=micro_buf[0][0],
                    kind="micro-cluster",
                    length_mm=float(sum(lengths)),
                    radius_mm=float("inf"),
                    mean_chord_mm=float(np.mean(lengths)),
                    abs_unit_vec=(float(mean_u[0]), float(mean_u[1]), float(mean_u[2])),
                )
            )
        micro_buf.clear()

    prev_u: np.ndarray | None = None
    for seg_idx, seg_len, start_u, end_u in ends:
        arc = arcs_map.get(seg_idx)
        if prev_u is not None:
            if (prev_u[0] * start_u[0] < -1e-6) or (prev_u[1] * start_u[1] < -1e-6):
                has_reversals = True
        prev_u = end_u

        if arc is None and seg_len <= MICRO_SEGMENT_THRESHOLD_MM:
            micro_buf.append((seg_idx, seg_len, start_u))
            continue
        _flush_micro()
        if arc is not None:
            has_arcs = True
            _, radius, a0, sweep = _arc_geometry(path, arc)
            if abs(sweep) >= 0.5 * math.pi - 1e-6:
                has_reversals = True
            samples_ang = np.linspace(a0, a0 + sweep, 9)
            sign = math.copysign(1.0, sweep)
            dz = abs(float(path[seg_idx + 1, 2] - path[seg_idx, 2]))
            uz = min(1.0, dz / max(seg_len, 1e-9)) if dz > 1e-9 else 0.0
            xy_scale = math.sqrt(max(0.0, 1.0 - uz * uz))
            ux = float(np.max(np.abs(-np.sin(samples_ang) * sign))) * xy_scale
            uy = float(np.max(np.abs(np.cos(samples_ang) * sign))) * xy_scale
            # Effective 3D helical curvature radius R_helix = R / xy_scale^2
            eff_radius = radius / max(xy_scale * xy_scale, 1e-4)
            primitives.append(
                PrimitiveSegmentSpec(
                    index=seg_idx,
                    kind="arc",
                    length_mm=seg_len,
                    radius_mm=eff_radius,
                    mean_chord_mm=seg_len,
                    abs_unit_vec=(ux, uy, uz),
                )
            )
        else:
            primitives.append(
                PrimitiveSegmentSpec(
                    index=seg_idx,
                    kind="line",
                    length_mm=seg_len,
                    radius_mm=float("inf"),
                    mean_chord_mm=seg_len,
                    abs_unit_vec=(float(abs(start_u[0])), float(abs(start_u[1])), float(abs(start_u[2]))),
                )
            )
    _flush_micro()

    corners: list[CornerSpec] = []
    for (_, len_a, _, before_u), (idx_b, len_b, after_u, _) in zip(ends, ends[1:]):
        cos_val = float(np.clip(np.dot(before_u, after_u), -1.0, 1.0))
        ang_rad = math.acos(cos_val)
        ang_deg = math.degrees(ang_rad)
        if ang_deg >= CORNER_ANGLE_DEGREES:
            diff_u = after_u - before_u
            norm_d = float(np.linalg.norm(diff_u))
            bisec = np.abs(diff_u / norm_d) if norm_d > 1e-9 else np.array([0.7071, 0.7071, 0.0])
            corners.append(
                CornerSpec(
                    vertex_index=idx_b,
                    turn_angle_rad=ang_rad,
                    turn_angle_deg=ang_deg,
                    bisector_abs_vec=(float(bisec[0]), float(bisec[1]), float(bisec[2])),
                    min_adjacent_length_mm=float(min(len_a, len_b)),
                )
            )

    total_len = float(sum(p.length_mm for p in primitives))
    prog_feed_s = (float(case.programmed_feed_mm_min) / 60.0) if case.programmed_feed_mm_min else 50.0
    vel_lims = tuple(float(lim.maximum_velocity_mm_s) for lim in case.axis_limits)
    acc_lims = tuple(float(lim.maximum_acceleration_mm_s2) for lim in case.axis_limits)

    return CaseGeometryProfile(
        case_id=case.case_id,
        total_length_mm=max(total_len, 1e-9),
        programmed_feed_mm_s=prog_feed_s,
        sample_period_s=float(case.sample_period_seconds),
        axis_vel_limits=(vel_lims[0], vel_lims[1], vel_lims[2]),
        axis_acc_limits=(acc_lims[0], acc_lims[1], acc_lims[2]),
        segments=tuple(primitives),
        corners=tuple(corners),
        has_arcs=has_arcs,
        has_corners=len(corners) > 0,
        has_micro_segments=has_micro,
        has_xy_reversals=has_reversals,
        has_z_motion=has_z,
    )


class GreyBoxPhysicalConstants(AxiomModel):
    """Interpretable physical calibration constants of the planner & machine servo loop."""

    spline_curvature_deg3: float = Field(default=0.68, alias="splineCurvatureDeg3")
    spline_curvature_deg5: float = Field(default=0.54, alias="splineCurvatureDeg5")
    lookahead_safety_factor: float = Field(default=0.85, alias="lookaheadSafetyFactor")
    bell_ramp_overhead: float = Field(default=0.35, alias="bellRampOverhead")
    cruise_time_scale: float = Field(default=1.00, alias="cruiseTimeScale")
    jerk_ramp_weight: float = Field(default=1.00, alias="jerkRampWeight")
    corner_tol_realization: float = Field(default=0.50, alias="cornerTolRealization")
    corner_filter_coupling: float = Field(default=0.125, alias="cornerFilterCoupling")
    corner_valley_filter_fill: float = Field(default=0.32, alias="cornerValleyFilterFill")
    chord_tol_realization: float = Field(default=0.50, alias="chordTolRealization")
    jerk_filter_scale: float = Field(default=0.75, alias="jerkFilterScale")
    velocity_loop_ratio_x: float = Field(default=4.0, alias="velocityLoopRatioX")
    velocity_loop_ratio_y: float = Field(default=4.0, alias="velocityLoopRatioY")
    velocity_loop_ratio_z: float = Field(default=4.0, alias="velocityLoopRatioZ")
    stribeck_breakaway_x_mm: float = Field(default=0.010, alias="stribeckBreakawayXMm")
    stribeck_breakaway_y_mm: float = Field(default=0.010, alias="stribeckBreakawayYMm")
    identified_resonance_hz: float = Field(default=115.0, alias="identifiedResonanceHz")
    resonance_compliance_gain: float = Field(default=0.0, alias="resonanceComplianceGain")


def _hardmin(values: Sequence[float]) -> float:
    """Deterministic hard minimum preserving exact piecewise bottleneck dead-zone plateaus."""
    return min(values)


def compute_filter_time_scales(q: CanonicalControlQuantities) -> tuple[float, float, float | None]:
    """Return `(filter_tau_s, valley_tau_eff_s, omega_lp_rad_s)` from canonical filter settings."""
    tau_fir = max(0.0, q.fir_time_s)
    if q.lowpass_cutoff_hz is not None:
        omega_lp = 2.0 * math.pi * max(2.0, q.lowpass_cutoff_hz)
        filter_tau = tau_fir + (math.sqrt(2.0) / omega_lp)
        valley_tau_eff = math.sqrt(tau_fir ** 2 + (2.0 / omega_lp) ** 2)
        return filter_tau, valley_tau_eff, omega_lp
    return tau_fir, tau_fir, None


def compute_servo_lag_coefficients(
    q: CanonicalControlQuantities,
    consts: GreyBoxPhysicalConstants,
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    """Steady-state P-P cascade velocity lag `c_v`, acceleration lag `c_a`, and inward curvature gain."""
    kp = q.servo_kp_1_s
    vff = q.vel_feedforward_ratio
    aff = q.acc_feedforward_ratio
    psi_v = (consts.velocity_loop_ratio_x, consts.velocity_loop_ratio_y, consts.velocity_loop_ratio_z)
    c_v = (
        (1.0 - vff[0]) / kp[0],
        (1.0 - vff[1]) / kp[1],
        (1.0 - vff[2]) / kp[2],
    )
    c_a = (
        ((1.0 - aff[0]) / (psi_v[0] * (kp[0] ** 2))) - ((1.0 - vff[0]) / (kp[0] ** 2)),
        ((1.0 - aff[1]) / (psi_v[1] * (kp[1] ** 2))) - ((1.0 - vff[1]) / (kp[1] ** 2)),
        ((1.0 - aff[2]) / (psi_v[2] * (kp[2] ** 2))) - ((1.0 - vff[2]) / (kp[2] ** 2)),
    )
    inward_curv_gain = (
        -(c_a[0] + 0.5 * (c_v[0] ** 2)),
        -(c_a[1] + 0.5 * (c_v[1] ** 2)),
        -(c_a[2] + 0.5 * (c_v[2] ** 2)),
    )
    return c_v, c_a, inward_curv_gain


def compute_segment_speed_envelopes(
    profile: CaseGeometryProfile,
    q: CanonicalControlQuantities,
    consts: GreyBoxPhysicalConstants,
) -> tuple[list[float], list[float], list[float], list[float], tuple[float, float, float]]:
    """Mechanism 1: Hard min-clipped steady-state segment speed & effective acceleration envelopes."""
    v_prog = q.feed_override_ratio * profile.programmed_feed_mm_s
    v_lim = (
        min(profile.axis_vel_limits[0], q.axis_vel_limit_mm_s[0]),
        min(profile.axis_vel_limits[1], q.axis_vel_limit_mm_s[1]),
        min(profile.axis_vel_limits[2], q.axis_vel_limit_mm_s[2]),
    )
    a_lim = (
        min(profile.axis_acc_limits[0], q.axis_acc_limit_mm_s2[0]),
        min(profile.axis_acc_limits[1], q.axis_acc_limit_mm_s2[1]),
        min(profile.axis_acc_limits[2], q.axis_acc_limit_mm_s2[2]),
    )
    seg_speeds: list[float] = []
    seg_eff_accs: list[float] = []
    peak_axis_vels = [0.0, 0.0, 0.0]
    peak_axis_accs = [0.0, 0.0, 0.0]

    for seg in profile.segments:
        ux, uy, uz = seg.abs_unit_vec
        v_ax = min(
            v_lim[0] / ux if ux > 1e-9 else float("inf"),
            v_lim[1] / uy if uy > 1e-9 else float("inf"),
            v_lim[2] / uz if uz > 1e-9 else float("inf"),
        )
        a_ax = min(
            a_lim[0] / ux if ux > 1e-9 else float("inf"),
            a_lim[1] / uy if uy > 1e-9 else float("inf"),
            a_lim[2] / uz if uz > 1e-9 else float("inf"),
        )
        a_eff = min(q.path_tangential_acc_mm_s2, a_ax)
        v_curv = (
            q.curvature_speed_clamp_factor * math.sqrt(q.centripetal_acc_limit_mm_s2 * seg.radius_mm)
            if math.isfinite(seg.radius_mm)
            else float("inf")
        )
        if seg.kind == "micro-cluster":
            eff_chord = max(seg.mean_chord_mm, q.min_segment_length_mm)
            v_la = math.sqrt(
                max(1e-6, 2.0 * consts.lookahead_safety_factor * a_eff * q.lookahead_block_count * eff_chord)
            )
        else:
            v_la = float("inf")

        v_s = max(1.0, _hardmin((v_prog, v_ax, v_curv, v_la)))
        seg_speeds.append(v_s)
        seg_eff_accs.append(a_eff)
        for ax_i, u_comp in enumerate((ux, uy, uz)):
            peak_axis_vels[ax_i] = max(peak_axis_vels[ax_i], v_s * u_comp)
            peak_axis_accs[ax_i] = max(peak_axis_accs[ax_i], a_eff * u_comp)
        if seg.kind == "arc" and math.isfinite(seg.radius_mm):
            a_cent_actual = (v_s ** 2) / max(seg.radius_mm, 1e-6)
            peak_axis_accs[0] = max(peak_axis_accs[0], a_cent_actual * ux)
            peak_axis_accs[1] = max(peak_axis_accs[1], a_cent_actual * uy)

    return seg_speeds, seg_eff_accs, peak_axis_vels, peak_axis_accs, a_lim


def compute_corner_blending_mechanics(
    profile: CaseGeometryProfile,
    q: CanonicalControlQuantities,
    consts: GreyBoxPhysicalConstants,
    seg_speeds: Sequence[float],
    a_lim: tuple[float, float, float],
    filter_tau: float,
    c_v: tuple[float, float, float],
    inward_curv_gain: tuple[float, float, float],
    peak_axis_accs: list[float],
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """Mechanism 2: Inscribed spline corner blending, filter corner-pull, and servo normal shift."""
    v_prog = q.feed_override_ratio * profile.programmed_feed_mm_s
    psi_spl = consts.spline_curvature_deg5 if q.spline_degree >= 5 else consts.spline_curvature_deg3

    corner_speeds: list[float] = []
    corner_blend_times: list[float] = []
    cmd_corner_devs: list[float] = []
    act_corner_devs: list[float] = []
    normal_servo_peaks: list[float] = []

    for cor in profile.corners:
        if cor.turn_angle_deg <= q.collinear_merge_angle_deg:
            v_c = max(seg_speeds) if seg_speeds else v_prog
            e_cmd_c = 0.0
            t_blend = 0.0
            act_c = 0.0
            servo_norm_c = 0.0
        else:
            half_ang = 0.5 * cor.turn_angle_rad
            one_minus_cos = max(1.0 - math.cos(half_ang), 1e-6)
            geom_cap = 0.45 * cor.min_adjacent_length_mm * math.sin(half_ang)
            eff_tol = (
                min(q.corner_tolerance_mm, geom_cap)
                if cor.turn_angle_deg >= q.corner_angle_threshold_deg
                else min(0.20 * q.corner_tolerance_mm, geom_cap)
            )
            r_in = max(1e-5, eff_tol * math.cos(half_ang) / one_minus_cos)
            d_trim = min(0.40 * cor.min_adjacent_length_mm, r_in * math.tan(half_ang))
            r_eff = max(1e-5, psi_spl * r_in)
            bx, by, bz = cor.bisector_abs_vec
            a_cor_lim = min(
                q.centripetal_acc_limit_mm_s2,
                a_lim[0] / bx if bx > 1e-9 else float("inf"),
                a_lim[1] / by if by > 1e-9 else float("inf"),
                a_lim[2] / bz if bz > 1e-9 else float("inf"),
            )
            v_c = min(v_prog, q.curvature_speed_clamp_factor * math.sqrt(a_cor_lim * r_eff))
            if seg_speeds:
                v_c = min(v_c, max(seg_speeds))
            t_blend = (2.0 * d_trim) / max(v_c, 1.0)
            e_cmd_c = (
                consts.corner_tol_realization * eff_tol
                + consts.corner_filter_coupling * v_c * filter_tau * math.sin(half_ang)
            )
            r_servo_eff = r_eff + 0.55 * v_c * filter_tau / max(math.sin(half_ang), 0.15)
            a_norm_c = min(max(a_lim), (v_c ** 2) / max(r_servo_eff, 0.05))
            for ax_i, b_comp in enumerate((bx, by, bz)):
                peak_axis_accs[ax_i] = max(peak_axis_accs[ax_i], min(a_lim[ax_i], a_norm_c * b_comp))

            b_sq_sum = max(bx * bx + by * by + bz * bz, 1e-9)
            mean_inward_gain = (
                (bx * bx) * inward_curv_gain[0]
                + (by * by) * inward_curv_gain[1]
                + (bz * bz) * inward_curv_gain[2]
            ) / b_sq_sum
            dr_servo_inward_c = mean_inward_gain * a_norm_c
            vel_mis_c = v_c * math.cos(half_ang) * abs(c_v[0] - c_v[1]) * bx * by
            acc_mis_c = 0.5 * a_norm_c * abs(inward_curv_gain[0] - inward_curv_gain[1]) * (bx + by) * 0.5
            servo_norm_c = abs(dr_servo_inward_c) + vel_mis_c + acc_mis_c
            act_c = abs(e_cmd_c + dr_servo_inward_c) + vel_mis_c + acc_mis_c

        corner_speeds.append(v_c)
        corner_blend_times.append(t_blend)
        cmd_corner_devs.append(e_cmd_c)
        act_corner_devs.append(act_c)
        normal_servo_peaks.append(servo_norm_c)

    return corner_speeds, corner_blend_times, cmd_corner_devs, act_corner_devs, normal_servo_peaks


def propagate_kinematic_time_law(
    profile: CaseGeometryProfile,
    q: CanonicalControlQuantities,
    consts: GreyBoxPhysicalConstants,
    seg_speeds: Sequence[float],
    seg_eff_accs: Sequence[float],
    corner_speeds: Sequence[float],
    corner_blend_times: Sequence[float],
    filter_tau: float,
    valley_tau_eff: float,
) -> tuple[float, float, float]:
    """Mechanism 3: Forward-backward acceleration propagation, S-curve tail, and corner valley speed."""
    v_prog = q.feed_override_ratio * profile.programmed_feed_mm_s
    n_prims = len(profile.segments)
    boundary_v = [0.0] * (n_prims + 1)
    default_junction_v = min(corner_speeds) if corner_speeds else (min(seg_speeds) if seg_speeds else v_prog)
    for k in range(1, n_prims):
        boundary_v[k] = corner_speeds[k - 1] if (k - 1) < len(corner_speeds) else default_junction_v
    for k in range(n_prims):
        reach = math.sqrt(boundary_v[k] ** 2 + 2.0 * seg_eff_accs[k] * profile.segments[k].length_mm)
        boundary_v[k + 1] = min(boundary_v[k + 1], reach, seg_speeds[k])
    for k in range(n_prims - 1, -1, -1):
        reach = math.sqrt(boundary_v[k + 1] ** 2 + 2.0 * seg_eff_accs[k] * profile.segments[k].length_mm)
        boundary_v[k] = min(boundary_v[k], reach, seg_speeds[k])

    raw_kin_time = 0.0
    total_s_tail = 0.0
    seg_peak_speeds: list[float] = []
    for k, seg in enumerate(profile.segments):
        v0, v1 = boundary_v[k], boundary_v[k + 1]
        v_target = seg_speeds[k]
        a_e = seg_eff_accs[k]
        d_acc = max(0.0, (v_target ** 2 - v0 ** 2) / (2.0 * a_e))
        d_dec = max(0.0, (v_target ** 2 - v1 ** 2) / (2.0 * a_e))
        if d_acc + d_dec <= seg.length_mm:
            v_peak_seg = v_target
            d_cruise = seg.length_mm - (d_acc + d_dec)
            t_cruise = d_cruise / max(v_peak_seg, 1e-6)
        else:
            v_peak_seg = math.sqrt(max(1e-6, 0.5 * (v0 ** 2 + v1 ** 2) + a_e * seg.length_mm))
            t_cruise = 0.0
        seg_peak_speeds.append(v_peak_seg)
        t_ramps = ((abs(v_peak_seg - v0) + abs(v_peak_seg - v1)) / a_e) * (
            1.0 + consts.bell_ramp_overhead * q.bell_acc_shape_factor
        )
        s_curve_tail = (
            consts.jerk_ramp_weight * (a_e / q.path_tangential_jerk_mm_s3)
            if (abs(v_peak_seg - v0) > 1.0 or abs(v_peak_seg - v1) > 1.0)
            else 0.0
        )
        raw_kin_time += consts.cruise_time_scale * t_cruise + t_ramps
        total_s_tail += s_curve_tail

    total_seg_time = raw_kin_time + total_s_tail
    duration_pred = max(profile.sample_period_s, total_seg_time + filter_tau)
    scurve_vel_scale = raw_kin_time / max(total_seg_time, 1e-9) if raw_kin_time > 1e-6 else 1.0

    achieved_corner_min = 0.0
    if corner_speeds:
        post_filter_corner_vels: list[float] = []
        eff_ramp_acc = (
            (min(seg_eff_accs) if seg_eff_accs else q.path_tangential_acc_mm_s2)
            / (1.0 + 0.35 * q.bell_acc_shape_factor)
        )
        adj_cruise_cap = max(seg_peak_speeds) if seg_peak_speeds else v_prog
        for idx_c, v_c_raw in enumerate(corner_speeds):
            v_junction = boundary_v[idx_c + 1] if (idx_c + 1) < n_prims else v_c_raw
            v_base_c = min(v_c_raw, v_junction)
            t_bl = corner_blend_times[idx_c]
            excess_win = max(0.0, valley_tau_eff - 0.5 * t_bl)
            valley_lift = (
                consts.corner_valley_filter_fill
                * eff_ramp_acc
                * (excess_win ** 2)
                / max(4.0 * valley_tau_eff, 1e-4)
                if valley_tau_eff > 1e-5
                else 0.0
            )
            half_a = 0.5 * profile.corners[idx_c].turn_angle_rad
            vec_fold = (
                1.0
                - (1.0 - math.cos(half_a))
                * min(1.0, valley_tau_eff / max(t_bl + valley_tau_eff, 1e-5))
                * 0.35
            )
            v_post = scurve_vel_scale * min(adj_cruise_cap, (v_base_c + valley_lift) * vec_fold)
            post_filter_corner_vels.append(max(0.0, v_post))
        achieved_corner_min = min(post_filter_corner_vels)

    return duration_pred, scurve_vel_scale, achieved_corner_min


def compute_arc_and_micro_deviations(
    profile: CaseGeometryProfile,
    q: CanonicalControlQuantities,
    consts: GreyBoxPhysicalConstants,
    seg_speeds: Sequence[float],
    scurve_vel_scale: float,
    omega_lp: float | None,
    c_v: tuple[float, float, float],
    inward_curv_gain: tuple[float, float, float],
    cmd_corner_devs: Sequence[float],
    normal_servo_peaks: list[float],
) -> tuple[float, list[float], list[float], float]:
    """Mechanism 4: FIR/low-pass command radial shrink, micro-segment chord error, and servo arc shift."""
    cmd_arc_devs: list[float] = []
    act_arc_devs: list[float] = []
    signed_radial_offsets: list[float] = []
    max_rev_acc = 0.0

    for k, seg in enumerate(profile.segments):
        if seg.kind == "arc" and math.isfinite(seg.radius_mm):
            v_arc = seg_speeds[k] * scurve_vel_scale
            r_s = max(seg.radius_mm, 1e-6)
            omega_s = v_arc / r_s
            half_arg = 0.5 * omega_s * q.fir_time_s
            sinc_val = (math.sin(half_arg) / half_arg) if half_arg > 1e-8 else (1.0 - (half_arg ** 2) / 6.0)
            biquad_val = (1.0 / math.sqrt(1.0 + (omega_s / omega_lp) ** 4)) if omega_lp is not None else 1.0
            dr_cmd = max(0.0, r_s * (1.0 - sinc_val * biquad_val))
            cmd_arc_devs.append(dr_cmd)

            a_cent_arc = (v_arc ** 2) / r_s
            dr_servo_inward = 0.5 * (inward_curv_gain[0] + inward_curv_gain[1]) * a_cent_arc
            dr_mismatch = (
                0.5 * v_arc * abs(c_v[0] - c_v[1])
                + 0.5 * a_cent_arc * abs(inward_curv_gain[0] - inward_curv_gain[1])
            )
            total_inward = dr_cmd + dr_servo_inward
            signed_radial_offsets.append(-total_inward)
            normal_servo_peaks.append(abs(dr_servo_inward) + dr_mismatch)
            act_arc_devs.append(abs(total_inward) + dr_mismatch)
            max_rev_acc = max(max_rev_acc, a_cent_arc)

    cmd_micro_dev = consts.chord_tol_realization * q.small_seg_chord_tol_mm if profile.has_micro_segments else 0.0
    sampled_dev_pred = max([0.0, cmd_micro_dev] + list(cmd_corner_devs) + cmd_arc_devs)
    return sampled_dev_pred, act_arc_devs, signed_radial_offsets, max_rev_acc


def compute_filtered_jerk_metrics(
    profile: CaseGeometryProfile,
    q: CanonicalControlQuantities,
    consts: GreyBoxPhysicalConstants,
    omega_lp: float | None,
) -> tuple[float, float]:
    """Mechanism 5: Post-filter discrete jerk RMS and Savitzky-Golay smoothed jerk RMS."""
    a_t = q.path_tangential_acc_mm_s2
    j_t = q.path_tangential_jerk_mm_s3
    fir_att = 1.0 / math.sqrt(1.0 + ((j_t * q.fir_time_s) / max(a_t, 1.0)) ** 2)
    lp_att = (
        1.0 / math.sqrt(1.0 + (j_t / max(omega_lp * a_t, 1.0)) ** 2)
        if omega_lp is not None
        else 1.0
    )
    quant_floor = (math.sqrt(20.0 / 12.0) * 1e-7) / (profile.sample_period_s ** 3)
    clean_jerk_rms = consts.jerk_filter_scale * j_t * (1.0 - 0.42 * q.bell_acc_shape_factor) * fir_att * lp_att
    jerk_rms_pred = math.sqrt(clean_jerk_rms ** 2 + quant_floor ** 2)
    smoothed_jerk_pred = 0.88 * clean_jerk_rms
    return jerk_rms_pred, smoothed_jerk_pred


def compute_servo_tracking_and_excitation(
    profile: CaseGeometryProfile,
    q: CanonicalControlQuantities,
    consts: GreyBoxPhysicalConstants,
    seg_speeds: Sequence[float],
    seg_eff_accs: Sequence[float],
    scurve_vel_scale: float,
    filter_tau: float,
    c_v: tuple[float, float, float],
    c_a: tuple[float, float, float],
    max_rev_acc: float,
    normal_servo_peaks: list[float],
) -> tuple[float, float, float, float, float, float, float, list[float]]:
    """Mechanism 6 & 7: Following error, tangential lag, quadrant glitch excess, resonance & mismatch."""
    kp = q.servo_kp_1_s
    fe_candidates: list[float] = [0.0]
    tang_candidates: list[float] = [0.0]
    eff_scurve_j_att = 1.0 / math.sqrt(1.0 + (filter_tau * kp[0] * 0.35) ** 2)
    for k, seg in enumerate(profile.segments):
        ux, uy, uz = seg.abs_unit_vec
        u_vec = (ux, uy, uz)
        v_seg = seg_speeds[k] * scurve_vel_scale
        a_seg = (
            (seg_eff_accs[k] / (1.0 + 0.35 * q.bell_acc_shape_factor))
            * (scurve_vel_scale ** 2)
            * eff_scurve_j_att
        )
        fe_cruise = math.sqrt(sum((c_v[i] * v_seg * u_vec[i]) ** 2 for i in range(3)))
        fe_ramp = math.sqrt(
            sum((0.55 * c_v[i] * v_seg * u_vec[i] + c_a[i] * a_seg * u_vec[i]) ** 2 for i in range(3))
        )
        if seg.kind == "arc" and math.isfinite(seg.radius_mm):
            a_cent = (v_seg ** 2) / max(seg.radius_mm, 1e-6)
            fe_arc = math.sqrt(
                (0.5 * (abs(c_v[0]) + abs(c_v[1])) * v_seg) ** 2
                + (0.5 * (abs(c_a[0]) + abs(c_a[1])) * a_cent) ** 2
            )
            fe_candidates.append(fe_arc)
        fe_candidates.extend((fe_cruise, fe_ramp))
        tang_candidates.append(fe_cruise)
    following_err_pred = max(fe_candidates)
    tangential_lag_pred = max(tang_candidates)

    if profile.has_xy_reversals or profile.has_arcs:
        rev_scale = math.sqrt(max(max_rev_acc, 500.0) / 2500.0)
        q_x = math.sqrt(
            (consts.stribeck_breakaway_x_mm * (60.0 / kp[0]) * rev_scale - q.friction_comp_amp_mm[0]) ** 2 + 1e-9
        )
        q_y = math.sqrt(
            (consts.stribeck_breakaway_y_mm * (60.0 / kp[1]) * rev_scale - q.friction_comp_amp_mm[1]) ** 2 + 1e-9
        )
        quad_glitch_pred = max(q_x, q_y)
    else:
        quad_glitch_pred = 0.0

    f_res = consts.identified_resonance_hz
    arg_res = math.pi * f_res * q.fir_time_s
    fir_res_gain = abs(math.sin(arg_res) / arg_res) if arg_res > 1e-6 else 1.0
    lp_res_gain = (
        1.0 / math.sqrt(1.0 + (f_res / q.lowpass_cutoff_hz) ** 4)
        if q.lowpass_cutoff_hz is not None
        else 1.0
    )
    notch_suppression = (
        1.0 - 0.85 * math.exp(-((q.notch_freq_hz - f_res) ** 2) / (2.0 * (18.0 ** 2)))
        if q.notch_freq_hz is not None
        else 1.0
    )
    kp_amp = (0.5 * (kp[0] + kp[1]) / 60.0) ** 0.75
    vib_err_mm = (
        consts.resonance_compliance_gain
        * (q.path_tangential_jerk_mm_s3 / 250000.0)
        * fir_res_gain
        * lp_res_gain
        * notch_suppression
        * kp_amp
    )
    resonance_rms_pred = 0.55 * vib_err_mm

    line_mis_devs: list[float] = []
    for k, seg in enumerate(profile.segments):
        ux, uy, uz = seg.abs_unit_vec
        v_l = seg_speeds[k] * scurve_vel_scale
        if seg.kind == "line":
            mis_xy = v_l * ux * uy * abs(c_v[0] - c_v[1]) if (ux > 0.05 and uy > 0.05) else 0.0
            mis_xz = v_l * ux * uz * abs(c_v[0] - c_v[2]) if (ux > 0.05 and uz > 0.05) else 0.0
            mis_yz = v_l * uy * uz * abs(c_v[1] - c_v[2]) if (uy > 0.05 and uz > 0.05) else 0.0
            tot_mis = mis_xy + mis_xz + mis_yz
            if tot_mis > 0.0:
                line_mis_devs.append(tot_mis)
                normal_servo_peaks.append(tot_mis)

    return (
        following_err_pred,
        tangential_lag_pred,
        quad_glitch_pred,
        vib_err_mm,
        resonance_rms_pred,
        fir_res_gain * lp_res_gain,
        notch_suppression,
        line_mis_devs,
    )


def evaluate_canonical_greybox_backbone(
    profile: CaseGeometryProfile,
    q: CanonicalControlQuantities,
    consts: GreyBoxPhysicalConstants,
) -> dict[str, float]:
    """Evaluate composable grey-box mechanisms over vendor-neutral `CanonicalControlQuantities`."""
    v_prog = q.feed_override_ratio * profile.programmed_feed_mm_s
    filter_tau, valley_tau_eff, omega_lp = compute_filter_time_scales(q)
    c_v, c_a, inward_curv_gain = compute_servo_lag_coefficients(q, consts)

    seg_speeds, seg_eff_accs, _, peak_axis_accs, a_lim = compute_segment_speed_envelopes(profile, q, consts)
    corner_speeds, corner_blend_times, cmd_corner_devs, act_corner_devs, normal_servo_peaks = (
        compute_corner_blending_mechanics(
            profile, q, consts, seg_speeds, a_lim, filter_tau, c_v, inward_curv_gain, peak_axis_accs
        )
    )
    duration_pred, scurve_vel_scale, achieved_corner_min = propagate_kinematic_time_law(
        profile, q, consts, seg_speeds, seg_eff_accs, corner_speeds, corner_blend_times, filter_tau, valley_tau_eff
    )
    sampled_dev_pred, act_arc_devs, signed_radial_offsets, max_rev_acc = compute_arc_and_micro_deviations(
        profile, q, consts, seg_speeds, scurve_vel_scale, omega_lp, c_v, inward_curv_gain, cmd_corner_devs, normal_servo_peaks
    )
    jerk_rms_pred, smoothed_jerk_pred = compute_filtered_jerk_metrics(profile, q, consts, omega_lp)
    (
        following_err_pred,
        tangential_lag_pred,
        quad_glitch_pred,
        vib_err_mm,
        resonance_rms_pred,
        fir_lp_res_gain,
        notch_suppression,
        line_mis_devs,
    ) = compute_servo_tracking_and_excitation(
        profile, q, consts, seg_speeds, seg_eff_accs, scurve_vel_scale, filter_tau, c_v, c_a, max_rev_acc, normal_servo_peaks
    )

    arc_with_glitch = (
        [d + 0.65 * quad_glitch_pred for d in act_arc_devs]
        if act_arc_devs
        else ([quad_glitch_pred] if profile.has_xy_reversals else [])
    )
    cmd_micro_only = [consts.chord_tol_realization * q.small_seg_chord_tol_mm] if profile.has_micro_segments else [0.0]
    base_act_candidates = cmd_micro_only + act_corner_devs + arc_with_glitch + line_mis_devs
    actual_dev_pred = max(base_act_candidates) + vib_err_mm
    normal_servo_max = (
        max([0.0] + normal_servo_peaks + ([quad_glitch_pred] if (profile.has_arcs or profile.has_xy_reversals) else []))
        + vib_err_mm
    )
    feed_util_pred = min(1.5, profile.total_length_mm / max(duration_pred * profile.programmed_feed_mm_s, 1e-6))

    return {
        "durationSeconds": duration_pred,
        "sampledPathDeviationMaxMm": sampled_dev_pred,
        "discreteJerkRms": jerk_rms_pred,
        "smoothedJerkRmsMmS3": smoothed_jerk_pred,
        "cornerSpeedMinMmS": achieved_corner_min,
        "feedUtilizationRatio": feed_util_pred,
        "followingErrorMaxMm": following_err_pred,
        "tangentialLagMaxMm": tangential_lag_pred,
        "normalServoErrorMaxMm": normal_servo_max,
        "signedRadialOffsetMeanMm": float(np.mean(signed_radial_offsets)) if signed_radial_offsets else 0.0,
        "actualPathDeviationMaxMm": actual_dev_pred,
        "quadrantGlitchExcessMm": quad_glitch_pred,
        "dominantResonanceFreqHz": consts.identified_resonance_hz,
        "resonanceBandRmsMm": resonance_rms_pred,
        "velocityMaxMmS": (max(seg_speeds) * scurve_vel_scale) if seg_speeds else v_prog,
        "accelerationMaxMmS2": max(peak_axis_accs) if any(peak_axis_accs) else q.path_tangential_acc_mm_s2,
        "jerkRmsMmS3": jerk_rms_pred,
        "firResonanceGain": fir_lp_res_gain,
        "notchSuppressionFactor": notch_suppression,
    }


def evaluate_greybox_backbone(
    profile: CaseGeometryProfile | CncBenchmarkCase,
    params: Mapping[str, float],
    consts: GreyBoxPhysicalConstants | None = None,
    *,
    controller_profile: ControllerProfile | None = None,
) -> dict[str, float]:
    """Evaluate all white-box + calibrated grey-box predictions for `profile` via `controller_profile`."""
    geom = extract_case_geometry_profile(profile) if isinstance(profile, CncBenchmarkCase) else profile
    ctrl_prof = controller_profile or _DEFAULT_GENERIC_PROFILE
    q = ctrl_prof.to_canonical(params)
    return evaluate_canonical_greybox_backbone(geom, q, consts or GreyBoxPhysicalConstants())


def calibrate_greybox_constants(
    records: Sequence[tuple[CaseGeometryProfile, CncBenchmarkCase, CncAlgorithmExport, CncQualityReport, dict[str, float]]],
    *,
    controller_profile: ControllerProfile | None = None,
) -> tuple[GreyBoxPhysicalConstants, tuple[str, ...]]:
    """Calibrate the grey-box physical constants via time-series NNLS & bounded Trust-Region Reflective."""
    ctrl_prof = controller_profile or _DEFAULT_GENERIC_PROFILE
    init = GreyBoxPhysicalConstants()
    notes: list[str] = []

    canonical_records = [(prof, case, exp, rep, ctrl_prof.to_canonical(p_dict)) for prof, case, exp, rep, p_dict in records]
    ctrl_records = [rec for rec in canonical_records if rec[3].servo_metrics is not None]

    # Step 1: Time-series closed-form identification of servo velocity-loop ratios & FFT resonance
    psi_v_est = [init.velocity_loop_ratio_x, init.velocity_loop_ratio_y, init.velocity_loop_ratio_z]
    res_freqs: list[float] = []

    if ctrl_records:
        for ax_idx in range(3):
            design_col: list[float] = []
            target_col: list[float] = []
            for _, case, exp, rep, q_ctrl in ctrl_records:
                if len(exp.samples) < 6 or any(s.actual_position_mm is None for s in exp.samples):
                    continue
                dt = case.sample_period_seconds
                q_cmd = np.asarray([s.position_mm[ax_idx] for s in exp.samples], dtype=np.float64)
                q_act = np.asarray([s.actual_position_mm[ax_idx] for s in exp.samples], dtype=np.float64)  # type: ignore[index]
                if float(np.ptp(q_cmd)) < 1e-4:
                    continue
                vel = np.gradient(q_cmd, dt)
                acc = np.gradient(vel, dt)
                kp_i = q_ctrl.servo_kp_1_s[ax_idx]
                vff_i = q_ctrl.vel_feedforward_ratio[ax_idx]
                aff_i = q_ctrl.acc_feedforward_ratio[ax_idx]
                e_obs = q_cmd - q_act
                known_part = ((1.0 - vff_i) / kp_i) * vel - ((1.0 - vff_i) / (kp_i ** 2)) * acc
                basis = ((1.0 - aff_i) / (kp_i ** 2)) * acc
                active_idx = np.abs(basis) > 1e-6
                if int(np.sum(active_idx)) >= 4:
                    design_col.extend(basis[active_idx].tolist())
                    target_col.extend((e_obs[active_idx] - known_part[active_idx]).tolist())

            if len(design_col) >= 6:
                A_mat = np.asarray(design_col, dtype=np.float64).reshape(-1, 1)
                b_vec = np.asarray(target_col, dtype=np.float64)
                sol = lsq_linear(A_mat, b_vec, bounds=(1.0 / 15.0, 1.0 / 0.8))
                inv_psi = float(sol.x[0])
                if inv_psi > 1e-6:
                    psi_v_est[ax_idx] = float(np.clip(1.0 / inv_psi, 0.8, 15.0))

        for _, _, _, rep, _ in ctrl_records:
            assert rep.servo_metrics is not None
            f_m = rep.servo_metrics.get("dominantResonanceFreqHz")
            r_m = rep.servo_metrics.get("resonanceBandRmsMm")
            if f_m and f_m.value and f_m.value >= 25.0 and r_m and (r_m.value or 0.0) > 1e-4:
                res_freqs.append(float(f_m.value))

    f_res_ident = float(np.median(res_freqs)) if res_freqs else 115.0

    # Step 2: Calibrate planner speed/deviation/corner-valley/jerk physical constants on all reports
    # Vector x_plan = [spline_deg3, spline_deg5, lookahead_safety, bell_overhead, cruise_scale, jerk_ramp_w,
    #                  corner_tol_real, corner_fir_coup, corner_valley_fill, chord_tol_real, jerk_scale]
    x0_plan = np.array([0.68, 0.54, 0.85, 0.35, 1.00, 1.00, 0.45, 0.12, 0.32, 0.45, 0.65], dtype=np.float64)
    lb_plan = np.array([0.25, 0.20, 0.15, 0.00, 0.70, 0.10, 0.10, 0.00, 0.00, 0.05, 0.02], dtype=np.float64)
    ub_plan = np.array([1.60, 1.50, 2.50, 1.50, 1.45, 2.50, 1.15, 0.80, 1.60, 1.15, 3.00], dtype=np.float64)

    def _make_consts(xp: np.ndarray, xs: np.ndarray) -> GreyBoxPhysicalConstants:
        return GreyBoxPhysicalConstants(
            splineCurvatureDeg3=float(xp[0]),
            splineCurvatureDeg5=float(xp[1]),
            lookaheadSafetyFactor=float(xp[2]),
            bellRampOverhead=float(xp[3]),
            cruiseTimeScale=float(xp[4]),
            jerkRampWeight=float(xp[5]),
            cornerTolRealization=float(xp[6]),
            cornerFilterCoupling=float(xp[7]),
            cornerValleyFilterFill=float(xp[8]),
            chordTolRealization=float(xp[9]),
            jerkFilterScale=float(xp[10]),
            velocityLoopRatioX=float(xs[0]),
            velocityLoopRatioY=float(xs[1]),
            velocityLoopRatioZ=float(xs[2]),
            stribeckBreakawayXMm=float(xs[3]),
            stribeckBreakawayYMm=float(xs[4]),
            identifiedResonanceHz=f_res_ident,
            resonanceComplianceGain=float(xs[5]),
        )

    xs_init = np.array([psi_v_est[0], psi_v_est[1], psi_v_est[2], 0.010, 0.010, 0.002], dtype=np.float64)

    dur_scale = max(float(np.std([r[3].kinematic_summary["durationSeconds"] for r in canonical_records])), 0.02)
    dev_scale = max(float(np.std([r[3].kinematic_summary["sampledPathDeviationMaxMm"] for r in canonical_records])), 0.002)
    jrk_scale = max(float(np.std([r[3].kinematic_summary["jerkRmsMmS3"] for r in canonical_records])), 5000.0)
    cor_v_obs = [
        float(r[3].analysis.metrics["cornerSpeedMinMmS"].value)
        for r in canonical_records
        if "cornerSpeedMinMmS" in r[3].analysis.metrics and r[3].analysis.metrics["cornerSpeedMinMmS"].value is not None
    ]
    cor_v_scale = max(float(np.std(cor_v_obs)) if len(cor_v_obs) >= 2 else 2.0, 1.0)

    def _plan_residuals(xp: np.ndarray) -> np.ndarray:
        c_tmp = _make_consts(xp, xs_init)
        res_list: list[float] = []
        for prof, _, _, rep, q_rec in canonical_records:
            pred = evaluate_canonical_greybox_backbone(prof, q_rec, c_tmp)
            res_list.append((pred["durationSeconds"] - rep.kinematic_summary["durationSeconds"]) / dur_scale)
            res_list.append((pred["sampledPathDeviationMaxMm"] - rep.kinematic_summary["sampledPathDeviationMaxMm"]) / dev_scale)
            res_list.append(0.5 * (pred["discreteJerkRms"] - rep.kinematic_summary["jerkRmsMmS3"]) / jrk_scale)
            cv_m = rep.analysis.metrics.get("cornerSpeedMinMmS")
            if prof.has_corners and cv_m is not None and cv_m.value is not None:
                res_list.append(0.65 * (pred["cornerSpeedMinMmS"] - float(cv_m.value)) / cor_v_scale)
        prior_pen = 0.08 * (xp - x0_plan) / (ub_plan - lb_plan)
        return np.concatenate([np.asarray(res_list, dtype=np.float64), prior_pen])

    if len(canonical_records) >= 3:
        opt_p = least_squares(_plan_residuals, x0_plan, bounds=(lb_plan, ub_plan), method="trf", max_nfev=130)
        xp_opt = opt_p.x
    else:
        xp_opt = x0_plan

    # Step 3: Calibrate servo friction & resonance compliance constants on controller traces
    if len(ctrl_records) >= 3:
        lb_s = np.array([0.8, 0.8, 0.8, 0.0, 0.0, 0.0], dtype=np.float64)
        ub_s = np.array([15.0, 15.0, 15.0, 0.045, 0.045, 0.040], dtype=np.float64)
        act_scale = max(
            float(np.std([r[3].servo_metrics["actualPathDeviationMaxMm"].value or 0.0 for r in ctrl_records if r[3].servo_metrics])),
            0.002,
        )

        def _servo_residuals(xs: np.ndarray) -> np.ndarray:
            c_tmp = _make_consts(xp_opt, xs)
            s_res: list[float] = []
            for prof, _, _, rep, q_ctrl in ctrl_records:
                assert rep.servo_metrics is not None
                pred = evaluate_canonical_greybox_backbone(prof, q_ctrl, c_tmp)
                fe_obs = float(rep.servo_metrics["followingErrorMaxMm"].value or 0.0)
                act_obs = float(rep.servo_metrics["actualPathDeviationMaxMm"].value or 0.0)
                qg_obs = float(rep.servo_metrics["quadrantGlitchExcessMm"].value or 0.0)
                s_res.append((pred["followingErrorMaxMm"] - fe_obs) / act_scale)
                s_res.append(1.25 * (pred["actualPathDeviationMaxMm"] - act_obs) / act_scale)
                if prof.has_arcs or prof.has_xy_reversals:
                    s_res.append(0.8 * (pred["quadrantGlitchExcessMm"] - qg_obs) / act_scale)
            prior_s = 0.10 * (xs - xs_init) / (ub_s - lb_s)
            return np.concatenate([np.asarray(s_res, dtype=np.float64), prior_s])

        opt_s = least_squares(_servo_residuals, xs_init, bounds=(lb_s, ub_s), method="trf", max_nfev=110)
        xs_opt = opt_s.x
    else:
        xs_opt = xs_init

    calibrated = _make_consts(xp_opt, xs_opt)

    def _bound_hits(names: Sequence[str], x: np.ndarray, lb: np.ndarray, ub: np.ndarray) -> list[str]:
        return [n for n, v, lo, hi in zip(names, x, lb, ub) if min(v - lo, hi - v) <= 0.02 * (hi - lo)]

    plan_names = (
        "splineCurvatureDeg3", "splineCurvatureDeg5", "lookaheadSafetyFactor", "bellRampOverhead",
        "cruiseTimeScale", "jerkRampWeight", "cornerTolRealization", "cornerFilterCoupling",
        "cornerValleyFilterFill", "chordTolRealization", "jerkFilterScale",
    )
    servo_names = (
        "velocityLoopRatioX", "velocityLoopRatioY", "velocityLoopRatioZ",
        "stribeckBreakawayXMm", "stribeckBreakawayYMm", "resonanceComplianceGain",
    )
    hits = _bound_hits(plan_names, xp_opt, lb_plan, ub_plan) if len(canonical_records) >= 3 else []
    if len(ctrl_records) >= 3:
        hits += _bound_hits(servo_names, xs_opt, lb_s, ub_s)
    notes.append(
        f"规划层拟合系数（{ctrl_prof.profile_id}，非直接物理量）：3阶/5阶样条曲率系数=({calibrated.spline_curvature_deg3:.3f}, {calibrated.spline_curvature_deg5:.3f})，"
        f"前瞻刹停裕度={calibrated.lookahead_safety_factor:.3f}，拐角滤波耦合={calibrated.corner_filter_coupling:.3f}，"
        f"拐角谷值平滑系数={calibrated.corner_valley_filter_fill:.3f}"
    )
    if ctrl_records:
        notes.append(
            f"伺服层拟合系数（非直接物理量，未做可辨识性检验）：X/Y 速度环带宽比=({calibrated.velocity_loop_ratio_x:.2f}, {calibrated.velocity_loop_ratio_y:.2f})，"
            f"摩擦突跳基准=({calibrated.stribeck_breakaway_x_mm * 1000:.1f}, {calibrated.stribeck_breakaway_y_mm * 1000:.1f}) µm；"
            f"FFT 实测主谐振峰中位数={calibrated.identified_resonance_hz:.1f} Hz"
        )
    if hits:
        notes.append(
            "以下系数贴近标定边界，当前数据无法辨识，请勿当作机床物理参数解读：" + "、".join(hits)
        )
    return calibrated, tuple(notes)


def matern52_kernel(
    X1: np.ndarray,
    X2: np.ndarray,
    length_scales: np.ndarray,
    signal_var: float,
) -> np.ndarray:
    """Anisotropic Matérn-5/2 covariance matrix."""
    ls = np.maximum(np.asarray(length_scales, dtype=np.float64), 1e-4)
    diff = (X1[:, None, :] - X2[None, :, :]) / ls[None, None, :]
    r = np.sqrt(np.sum(diff * diff, axis=2) + 1e-18)
    sqrt5_r = math.sqrt(5.0) * r
    return signal_var * (1.0 + sqrt5_r + (5.0 / 3.0) * (r * r)) * np.exp(-sqrt5_r)


def fit_mle_ard_matern52_gp(
    X: np.ndarray,
    residuals: np.ndarray,
) -> tuple[np.ndarray, float, float, np.ndarray]:
    """Fit ARD Matérn-5/2 GP hyperparameters via exact Marginal Log-Likelihood (L-BFGS-B)."""
    n_samples, k_dim = X.shape
    y_var = float(np.var(residuals))
    if n_samples < 4 or k_dim == 0 or y_var < 1e-16:
        ls_init = np.ones(max(k_dim, 1), dtype=np.float64)
        sig_v = max(y_var, 1e-12)
        noi_v = max(0.1 * sig_v, 1e-12)
        K = matern52_kernel(X, X, ls_init[:k_dim], sig_v) + noi_v * np.eye(n_samples)
        alpha = np.linalg.solve(K, residuals) if n_samples > 0 else np.zeros(0)
        return ls_init[:k_dim], sig_v, noi_v, alpha

    y_scale = math.sqrt(y_var)
    y_norm = residuals / y_scale

    theta0 = np.concatenate([np.zeros(k_dim), [0.0, math.log(0.08)]])
    bounds = [(-1.2, 2.0)] * k_dim + [(-4.0, 2.5), (-7.0, 0.5)]

    def _neg_log_marginal_likelihood(theta: np.ndarray) -> float:
        ls = np.exp(theta[:k_dim])
        sig_v = float(math.exp(theta[k_dim]))
        noi_v = float(math.exp(theta[k_dim + 1]))
        K = matern52_kernel(X, X, ls, sig_v) + (noi_v + 1e-8) * np.eye(n_samples)
        try:
            L = np.linalg.cholesky(K)
            alpha_n = np.linalg.solve(L.T, np.linalg.solve(L, y_norm))
            data_fit = 0.5 * float(np.dot(y_norm, alpha_n))
            complexity = float(np.sum(np.log(np.diag(L))))
            reg = 0.04 * float(np.sum(theta[:k_dim] ** 2))
            return data_fit + complexity + reg
        except np.linalg.LinAlgError:
            return 1e9

    res_opt = minimize(_neg_log_marginal_likelihood, theta0, method="L-BFGS-B", bounds=bounds, options={"maxiter": 65})
    th = res_opt.x if res_opt.success or np.isfinite(res_opt.fun) else theta0
    ls_opt = np.exp(th[:k_dim])
    sig_var_opt = float(math.exp(th[k_dim])) * y_var
    noi_var_opt = max(float(math.exp(th[k_dim + 1])) * y_var, 1e-12)

    K_full = matern52_kernel(X, X, ls_opt, sig_var_opt) + noi_var_opt * np.eye(n_samples)
    gp_alpha = np.linalg.solve(K_full, residuals)
    return ls_opt, sig_var_opt, noi_var_opt, gp_alpha


def simulate_realistic_cnc_controller(
    case: CncBenchmarkCase,
    parameters: Mapping[str, float],
    *,
    source_kind: SourceKind = "algorithm-export",
    registry: CncParameterRegistry | None = None,
    controller_profile: ControllerProfile | None = None,
    algorithm_version: str = "realistic-cnc-kernel-v1",
    machine_resonance_hz: float = 115.0,
) -> CncAlgorithmExport:
    """Synthetic discrete-time CNC planner, filter and servo simulator (test fixture only).

    Implements hard min-clipped lookahead, inscribed corner blending, translation-invariant
    local-curvature micro-spline chord pull, a causal FIR moving average followed by two
    cascaded first-order low-pass stages (critically damped, not a true Butterworth), a P-P
    position/velocity cascade with feed-forward (no velocity-loop integrator), a quadrant-
    reversal stiction pulse, and a trajectory-driven RK4 structural mode filtered by a
    discrete-time IIR biquad notch. Its hidden constants remain close to kernel defaults, so
    it must not be used as the sole ground truth for transfer or calibration claims.
    """
    ctrl_prof = controller_profile or _DEFAULT_GENERIC_PROFILE
    reg = registry or ctrl_prof.registry
    p = {**default_parameter_values(reg), **dict(parameters)}
    q = ctrl_prof.to_canonical(p)
    prof = extract_case_geometry_profile(case)
    dt = case.sample_period_seconds

    eps_cor = q.corner_tolerance_mm
    eps_chord = q.small_seg_chord_tol_mm if ctrl_prof.capabilities.has_micro_spline else 0.0
    n_la = q.lookahead_block_count
    ang_th = q.corner_angle_threshold_deg
    col_deg = q.collinear_merge_angle_deg
    curv_clamp = q.curvature_speed_clamp_factor
    l_min = q.min_segment_length_mm
    spl_deg = q.spline_degree

    feed_ovr = q.feed_override_ratio
    a_t = q.path_tangential_acc_mm_s2
    j_t = q.path_tangential_jerk_mm_s3
    a_n = q.centripetal_acc_limit_mm_s2
    v_lim = q.axis_vel_limit_mm_s
    a_lim = q.axis_acc_limit_mm_s2
    fir_ms = q.fir_time_s * 1e3
    f_lp = q.lowpass_cutoff_hz
    beta_bell = q.bell_acc_shape_factor

    # 1. Build geometric path with inscribed corner rounding arcs along vertices
    raw_vertices = np.asarray(case.reference_path, dtype=float)
    arcs_map = {arc.segment_index: arc for arc in (case.reference_arcs or ())}
    ends = _segment_ends(raw_vertices, arcs_map)

    fine_pts: list[np.ndarray] = []
    fine_v_caps: list[float] = []
    v_prog = feed_ovr * prof.programmed_feed_mm_s
    psi_spl_true = 0.54 if spl_deg >= 5 else 0.68

    n_segs = len(ends)
    vertex_chord_pull = np.zeros_like(raw_vertices, dtype=np.float64)
    if eps_chord > 0.0 and len(raw_vertices) >= 3:
        for v_i in range(1, len(raw_vertices) - 1):
            if (v_i - 1) in arcs_map or v_i in arcs_map:
                continue
            v_in = raw_vertices[v_i] - raw_vertices[v_i - 1]
            v_out = raw_vertices[v_i + 1] - raw_vertices[v_i]
            ds_prev = float(np.linalg.norm(v_in))
            ds_next = float(np.linalg.norm(v_out))
            if min(ds_prev, ds_next) <= MICRO_SEGMENT_THRESHOLD_MM and ds_prev > 1e-9 and ds_next > 1e-9:
                du = (v_out / ds_next) - (v_in / ds_prev)
                du_norm = float(np.linalg.norm(du))
                if du_norm > 1e-9:
                    kappa_est = du_norm / (0.5 * (ds_prev + ds_next))
                    pull_mag = 0.35 * eps_chord * min(1.0, kappa_est / 0.05)
                    vertex_chord_pull[v_i] = pull_mag * (du / du_norm)

    corner_trim = [0.0] * (n_segs + 1)
    corner_v_map: dict[int, float] = {}
    for (_, len_a, _, u_before), (idx_b, len_b, u_after, _) in zip(ends, ends[1:]):
        cos_v = float(np.clip(np.dot(u_before, u_after), -1.0, 1.0))
        ang_rad = math.acos(cos_v)
        ang_deg = math.degrees(ang_rad)
        if ang_deg <= col_deg:
            continue
        half_a = 0.5 * ang_rad
        eff_tol = eps_cor if ang_deg >= ang_th else 0.20 * eps_cor
        max_trim = 0.40 * min(len_a, len_b)
        r_in = eff_tol * math.cos(half_a) / max(1.0 - math.cos(half_a), 1e-6)
        d_trim = min(max_trim, r_in * math.tan(half_a))
        if max_trim > 1e-6 and r_in * math.tan(half_a) > max_trim:
            r_in = d_trim / max(math.tan(half_a), 1e-6)
        r_eff = max(1e-5, psi_spl_true * r_in)
        diff_u = u_after - u_before
        bisec = np.abs(diff_u / max(float(np.linalg.norm(diff_u)), 1e-9))
        a_cor = min(
            a_n,
            a_lim[0] / bisec[0] if bisec[0] > 1e-9 else float("inf"),
            a_lim[1] / bisec[1] if bisec[1] > 1e-9 else float("inf"),
            a_lim[2] / bisec[2] if bisec[2] > 1e-9 else float("inf"),
        )
        v_cor = min(v_prog, curv_clamp * math.sqrt(a_cor * r_eff))
        corner_trim[idx_b] = d_trim
        corner_v_map[idx_b] = v_cor

    for k_pos, (seg_idx, seg_len, u_start, _) in enumerate(ends):
        arc = arcs_map.get(seg_idx)
        ux, uy, uz = abs(u_start[0]), abs(u_start[1]), abs(u_start[2])
        v_ax = min(
            v_lim[0] / ux if ux > 1e-9 else float("inf"),
            v_lim[1] / uy if uy > 1e-9 else float("inf"),
            v_lim[2] / uz if uz > 1e-9 else float("inf"),
        )
        a_ax = min(
            a_lim[0] / ux if ux > 1e-9 else float("inf"),
            a_lim[1] / uy if uy > 1e-9 else float("inf"),
            a_lim[2] / uz if uz > 1e-9 else float("inf"),
        )
        a_eff = min(a_t, a_ax)
        if arc is not None:
            center, radius, a0, sweep = _arc_geometry(raw_vertices, arc)
            z0 = float(raw_vertices[seg_idx, 2])
            z1 = float(raw_vertices[seg_idx + 1, 2])
            dz = abs(z1 - z0)
            uz_arc = min(1.0, dz / max(seg_len, 1e-9)) if dz > 1e-9 else 0.0
            xy_sc = math.sqrt(max(0.0, 1.0 - uz_arc * uz_arc))
            samples_ang = np.linspace(a0, a0 + sweep, 9)
            sign_s = math.copysign(1.0, sweep)
            ux_arc = float(np.max(np.abs(-np.sin(samples_ang) * sign_s))) * xy_sc
            uy_arc = float(np.max(np.abs(np.cos(samples_ang) * sign_s))) * xy_sc
            v_ax_arc = min(
                v_lim[0] / ux_arc if ux_arc > 1e-9 else float("inf"),
                v_lim[1] / uy_arc if uy_arc > 1e-9 else float("inf"),
                v_lim[2] / uz_arc if uz_arc > 1e-9 else float("inf"),
            )
            eff_r = radius / max(xy_sc * xy_sc, 1e-4)
            v_seg_cap = min(v_prog, v_ax_arc, curv_clamp * math.sqrt(a_n * eff_r))
            n_sub = max(8, int(math.ceil(seg_len / 0.15)))
            for j in range(n_sub if k_pos < n_segs - 1 else n_sub + 1):
                frac_j = j / n_sub
                ang = a0 + sweep * frac_j
                pt = np.array([center[0] + radius * math.cos(ang), center[1] + radius * math.sin(ang), z0 + (z1 - z0) * frac_j])
                fine_pts.append(pt)
                fine_v_caps.append(v_seg_cap)
        else:
            is_micro = seg_len <= MICRO_SEGMENT_THRESHOLD_MM
            v_la = math.sqrt(max(1.0, 2.0 * 0.85 * a_eff * n_la * max(seg_len, l_min))) if is_micro else float("inf")
            v_seg_cap = min(v_prog, v_ax, v_la)
            trim_s = corner_trim[seg_idx] if not is_micro else 0.0
            trim_e = corner_trim[seg_idx + 1] if not is_micro else 0.0
            s0 = min(trim_s, 0.45 * seg_len)
            s1 = max(s0 + 1e-6, seg_len - min(trim_e, 0.45 * seg_len))
            p_start = raw_vertices[seg_idx]
            vec = raw_vertices[seg_idx + 1] - p_start
            n_sub = max(2, int(math.ceil((s1 - s0) / 0.25)))
            for j in range(n_sub + 1):
                if j == 0 and k_pos > 0 and trim_s == 0.0:
                    continue
                u_frac = (s0 + (s1 - s0) * (j / n_sub)) / max(seg_len, 1e-9)
                pt = p_start + u_frac * vec
                if is_micro and eps_chord > 0:
                    pt = pt + (1.0 - u_frac) * vertex_chord_pull[seg_idx] + u_frac * vertex_chord_pull[seg_idx + 1]
                fine_pts.append(pt)
                fine_v_caps.append(v_seg_cap)

            next_v = seg_idx + 1
            if next_v < len(raw_vertices) - 1 and corner_trim[next_v] > 1e-6 and not is_micro:
                p_in = p_start + (s1 / seg_len) * vec
                p_vx = raw_vertices[next_v]
                next_len = max(float(np.linalg.norm(raw_vertices[next_v + 1] - p_vx)), 1e-9)
                p_out = p_vx + (min(corner_trim[next_v], 0.45 * next_len) / next_len) * (raw_vertices[next_v + 1] - p_vx)
                v_cor_cap = corner_v_map.get(next_v, v_seg_cap)
                # G2-continuous quartic Bezier blend [p_in, c1, p_vx_pull, c2, p_out] with zero endpoint curvature jump
                c1 = 0.5 * (p_in + p_vx)
                c2 = 0.5 * (p_out + p_vx)
                for b_i in range(1, 13):
                    tau_b = b_i / 12.0
                    om = 1.0 - tau_b
                    b_pt = (
                        (om ** 4) * p_in
                        + 4.0 * (om ** 3) * tau_b * c1
                        + 6.0 * (om ** 2) * (tau_b ** 2) * p_vx
                        + 4.0 * om * (tau_b ** 3) * c2
                        + (tau_b ** 4) * p_out
                    )
                    fine_pts.append(b_pt)
                    fine_v_caps.append(v_cor_cap)

    pts_arr = np.asarray(fine_pts, dtype=np.float64)
    v_caps = np.asarray(fine_v_caps, dtype=np.float64)
    v_caps[0] = 0.0
    v_caps[-1] = 0.0

    ds_arr = np.linalg.norm(np.diff(pts_arr, axis=0), axis=1)
    eff_a = a_t / (1.0 + 0.35 * beta_bell)
    for i in range(len(ds_arr)):
        v_caps[i + 1] = min(v_caps[i + 1], math.sqrt(v_caps[i] ** 2 + 2.0 * eff_a * ds_arr[i]))
    for i in range(len(ds_arr) - 1, -1, -1):
        v_caps[i] = min(v_caps[i], math.sqrt(v_caps[i + 1] ** 2 + 2.0 * eff_a * ds_arr[i]))

    seg_dt = np.zeros(len(ds_arr), dtype=np.float64)
    for i in range(len(ds_arr)):
        v_mid = max(0.5 * (v_caps[i] + v_caps[i + 1]), 0.5)
        seg_dt[i] = ds_arr[i] / v_mid
    node_t = np.concatenate([[0.0], np.cumsum(seg_dt)])
    jerk_tail = a_t / max(j_t, 1000.0)
    node_t = node_t * ((node_t[-1] + jerk_tail) / max(node_t[-1], 1e-9))

    node_s = np.concatenate([[0.0], np.cumsum(ds_arr)])
    n_base = max(6, int(math.ceil(node_t[-1] / dt)) + 1)
    t_grid = np.arange(n_base, dtype=np.float64) * dt
    s_grid = np.interp(t_grid, node_t, node_s)

    # 1b. True C2 S-curve jerk limiting along 1D arc-length progress s(t) (double-boxcar velocity smoothing, zero corner-cutting!)
    n_scurve = min(10, max(2, int(round((0.35 * eff_a / max(j_t, 1000.0)) / dt))))
    if n_scurve > 1:
        ker_j = np.ones(n_scurve, dtype=np.float64) / n_scurve
        for _ in range(2):
            padded_s = np.concatenate([np.repeat(s_grid[:1], n_scurve - 1), s_grid, np.repeat(s_grid[-1:], n_scurve - 1)])
            s_grid = np.convolve(padded_s, ker_j, mode="valid")
        s_grid[0] = 0.0
        s_grid[-1] = node_s[-1]

    cmd_pos = np.column_stack([np.interp(s_grid, node_s, pts_arr[:, ax]) for ax in range(3)])

    # 2. Apply post-interpolation Cartesian FIR moving-average + 2nd-order Butterworth lowpass
    n_fir = max(1, int(round((fir_ms * 1e-3) / dt)))
    if n_fir > 1:
        pad_tail = np.repeat(cmd_pos[-1:, :], n_fir - 1, axis=0)
        padded = np.vstack([np.repeat(cmd_pos[:1, :], n_fir - 1, axis=0), cmd_pos, pad_tail])
        kernel = np.ones(n_fir, dtype=np.float64) / n_fir
        cmd_pos = np.column_stack([np.convolve(padded[:, ax], kernel, mode="valid") for ax in range(3)])

    if f_lp is not None:
        rc = 1.0 / (2.0 * math.pi * max(f_lp, 2.0))
        alpha_lp = dt / (rc + dt)
    else:
        rc = 0.0
        alpha_lp = 1.0
    if alpha_lp < 0.98:
        lp_out = np.empty_like(cmd_pos)
        state1 = cmd_pos[0].copy()
        state2 = cmd_pos[0].copy()
        for k in range(len(cmd_pos)):
            state1 = state1 + alpha_lp * (cmd_pos[k] - state1)
            state2 = state2 + alpha_lp * (state1 - state2)
            lp_out[k] = state2
        extra_rows: list[np.ndarray] = []
        target_end = raw_vertices[-1]
        for _ in range(min(40, int(round(3.0 * rc / dt)) + 2)):
            if float(np.linalg.norm(state2 - target_end)) <= 2e-4:
                break
            state1 = state1 + alpha_lp * (target_end - state1)
            state2 = state2 + alpha_lp * (state1 - state2)
            extra_rows.append(state2.copy())
        if extra_rows:
            lp_out = np.vstack([lp_out, np.asarray(extra_rows)])
        lp_out[-1] = target_end
        lp_out[0] = raw_vertices[0]
        cmd_pos = lp_out

    n_total = len(cmd_pos)
    t_full = np.arange(n_total, dtype=np.float64) * dt

    # 3. Cascade P-PI Servo Loop + Stribeck Quadrant Stiction + Structural Resonance (when controller-trace)
    act_pos: np.ndarray | None = None
    if source_kind == "controller-trace":
        kp_arr = np.array(q.servo_kp_1_s, dtype=np.float64)
        vff_arr = np.array(q.vel_feedforward_ratio, dtype=np.float64)
        aff_arr = np.array(q.acc_feedforward_ratio, dtype=np.float64)
        fric_comp = np.array([q.friction_comp_amp_mm[0], q.friction_comp_amp_mm[1], 0.0], dtype=np.float64)
        f_notch = q.notch_freq_hz

        cmd_vel = np.gradient(cmd_pos, dt, axis=0)
        cmd_acc = np.gradient(cmd_vel, dt, axis=0)

        psi_v_true = np.array([4.2, 4.0, 3.8])
        act_pos = np.zeros_like(cmd_pos)
        n_sub_ode = max(4, int(math.ceil(dt * float(np.max(kp_arr * psi_v_true)) * 4.0)))
        h = dt / n_sub_ode
        for ax in range(3):
            pos_s = float(cmd_pos[0, ax])
            vel_s = 0.0
            kp_a = float(kp_arr[ax])
            wv_a = float(psi_v_true[ax]) * kp_a
            vff_a = float(vff_arr[ax])
            aff_a = float(aff_arr[ax])
            act_pos[0, ax] = pos_s
            for k in range(n_total - 1):
                for sub in range(n_sub_ode):
                    frac = (sub + 1) / n_sub_ode
                    qc = float(cmd_pos[k, ax] + frac * (cmd_pos[k + 1, ax] - cmd_pos[k, ax]))
                    vc = float(cmd_vel[k, ax] + frac * (cmd_vel[k + 1, ax] - cmd_vel[k, ax]))
                    ac = float(cmd_acc[k, ax] + frac * (cmd_acc[k + 1, ax] - cmd_acc[k, ax]))
                    v_ref = kp_a * (qc - pos_s) + vff_a * vc
                    acc_s = wv_a * (v_ref - vel_s) + aff_a * ac
                    vel_s += h * acc_s
                    pos_s += h * vel_s
                act_pos[k + 1, ax] = pos_s

        true_stiction = np.array([0.011, 0.011])
        for ax in range(2):
            v_col = cmd_vel[:, ax]
            flips = np.where(v_col[:-1] * v_col[1:] <= 0.0)[0] + 1
            for r_i in flips:
                a_rev = abs(float(cmd_acc[r_i, ax]))
                if a_rev < 20.0:
                    continue
                raw_stick = true_stiction[ax] * (60.0 / float(kp_arr[ax])) * math.sqrt(a_rev / 2500.0)
                residual_glitch = raw_stick - float(fric_comp[ax])
                decay_tau = max(2.0 * dt, 0.65 / float(kp_arr[ax]))
                t_rel = t_full - t_full[r_i]
                mask = (t_rel >= 0.0) & (t_rel <= 6.0 * decay_tau)
                pulse = residual_glitch * (t_rel[mask] / decay_tau) * np.exp(1.0 - t_rel[mask] / decay_tau)
                sign_dir = -1.0 if float(cmd_acc[r_i, ax]) >= 0 else 1.0
                act_pos[mask, ax] += sign_dir * pulse

        if 0.5 / dt > machine_resonance_hz * 1.15:
            s_end = float(node_s[-1]) if len(node_s) > 0 else 0.0
            if s_end > 1e-6:
                taper = np.clip(np.minimum(s_grid / 0.5, (s_end - s_grid) / 0.5), 0.0, 1.0)
                m_idx = np.arange(1, 33, dtype=np.float64)
                k_spatial = 1.1 + 4.2 * ((m_idx * 0.61803398875) % 1.0)
                max_ds = float(np.max(np.abs(np.diff(s_grid)))) if len(s_grid) > 1 else 0.0
                nyq_mask = (k_spatial * max_ds <= 0.42).astype(np.float64)
                n_active = max(1.0, float(np.sum(nyq_mask)))
                phases = 2.0 * math.pi * ((m_idx * 0.38196601125) % 1.0)
                tex_filt = 0.00036 * taper * np.sum(
                    (np.sin(2.0 * math.pi * np.outer(s_grid, k_spatial) + phases) * nyq_mask) / math.sqrt(n_active),
                    axis=1,
                )
                if n_fir > 1:
                    pad_tex = np.concatenate(
                        [np.repeat(tex_filt[:1], n_fir - 1), tex_filt, np.repeat(tex_filt[-1:], n_fir - 1)]
                    )
                    tex_filt = np.convolve(pad_tex, np.ones(n_fir, dtype=np.float64) / n_fir, mode="valid")
                if len(tex_filt) < n_total:
                    tex_filt = np.pad(tex_filt, (0, n_total - len(tex_filt)), mode="edge")
                else:
                    tex_filt = tex_filt[:n_total]
                # Sample-period-invariant exact exponential high-pass (zero DC when stationary)
                alpha_hp = math.exp(-dt / 0.003)
                tex_hp = np.zeros(n_total, dtype=np.float64)
                lp_slow = float(tex_filt[0])
                for k in range(n_total):
                    xk = float(tex_filt[k])
                    lp_slow = alpha_hp * lp_slow + (1.0 - alpha_hp) * xk
                    tex_hp[k] = xk - lp_slow
            else:
                tex_hp = np.zeros(n_total, dtype=np.float64)

            cmd_jrk = np.gradient(cmd_acc, dt, axis=0)
            lin_jx = cmd_jrk[:, 0] - 0.75 * cmd_jrk[:, 1]
            kp_gain = (0.5 * (float(kp_arr[0]) + float(kp_arr[1])) / 60.0) ** 0.75
            raw_u = kp_gain * (8.0e-10 * lin_jx + 1.0 * tex_hp)

            if f_notch is not None and 1.0 < f_notch < 0.48 / dt:
                w0 = 2.0 * math.pi * f_notch * dt
                bw_hz = 28.0
                alpha_n = math.sin(w0) * math.sinh(
                    0.5 * math.log(2.0) * (2.0 * math.pi * bw_hz * dt) / max(math.sin(w0), 1e-6)
                )
                a0 = 1.0 + alpha_n
                b0 = 1.0 / a0
                b1 = (-2.0 * math.cos(w0)) / a0
                b2 = 1.0 / a0
                a1 = (-2.0 * math.cos(w0)) / a0
                a2 = (1.0 - alpha_n) / a0
                u_drv = np.zeros_like(raw_u)
                x1 = x2 = y1 = y2 = 0.0
                for k in range(n_total):
                    xk = float(raw_u[k])
                    yk = b0 * xk + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                    x2, x1, y2, y1 = x1, xk, y1, yk
                    u_drv[k] = yk
            else:
                u_drv = raw_u

            omega_r = 2.0 * math.pi * machine_resonance_hz
            zeta_r = 0.018
            res_disp = np.zeros(n_total, dtype=np.float64)
            z_pos, z_vel = 0.0, 0.0
            n_sub_r = max(4, int(math.ceil(dt * omega_r * 2.0)))
            hr = dt / n_sub_r
            w2 = omega_r * omega_r
            two_zw = 2.0 * zeta_r * omega_r
            for k in range(n_total):
                uk = float(u_drv[k])
                for _ in range(n_sub_r):
                    k1z, k1v = z_vel, w2 * (uk - z_pos) - two_zw * z_vel
                    z2, v2 = z_pos + 0.5 * hr * k1z, z_vel + 0.5 * hr * k1v
                    k2z, k2v = v2, w2 * (uk - z2) - two_zw * v2
                    z3, v3 = z_pos + 0.5 * hr * k2z, z_vel + 0.5 * hr * k2v
                    k3z, k3v = v3, w2 * (uk - z3) - two_zw * v3
                    z4, v4 = z_pos + hr * k3z, z_vel + hr * k3v
                    k4z, k4v = v4, w2 * (uk - z4) - two_zw * v4
                    z_pos += (hr / 6.0) * (k1z + 2.0 * k2z + 2.0 * k3z + k4z)
                    z_vel += (hr / 6.0) * (k1v + 2.0 * k2v + 2.0 * k3v + k4v)
                res_disp[k] = z_pos
            res_disp[0] = 0.0
            res_disp[-1] = 0.0
            act_pos[:, 0] += res_disp
            act_pos[:, 1] -= 0.7 * res_disp

        act_pos[0] = cmd_pos[0]
        act_pos[-1] = cmd_pos[-1]

    samples = tuple(
        BenchmarkSample(
            sampleIndex=i,
            t=round(float(t_full[i]), 9),
            positionMm=(
                round(float(cmd_pos[i, 0]), 7),
                round(float(cmd_pos[i, 1]), 7),
                round(float(cmd_pos[i, 2]), 7),
            ),
            actualPositionMm=(
                (
                    round(float(act_pos[i, 0]), 7),
                    round(float(act_pos[i, 1]), 7),
                    round(float(act_pos[i, 2]), 7),
                )
                if act_pos is not None
                else None
            ),
        )
        for i in range(n_total)
    )
    return CncAlgorithmExport(
        algorithmId="axiom.realistic-cnc-planner",
        algorithmVersion=algorithm_version,
        sourceKind=source_kind,
        caseContentHash=benchmark_case_hash(case),
        coordinateFrame=case.coordinate_frame,
        unit="mm",
        samplePeriodSeconds=dt,
        positionResolutionMm=1e-7,
        parameterRegistryId=reg.registry_id,
        parameters={k: round(float(v), 6) for k, v in p.items()},
        samples=samples,
    )
