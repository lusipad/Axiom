"""Adversarial physical invariance and structurally-mismatched plant verification tests.

Verifies two critical properties required before any shop-floor deployment:
1. ``simulate_realistic_cnc_controller`` obeys Galilean translation invariance, planar
   rotation invariance, zero artificial bending on collinear micro-segments, and zero
   resonance oscillation when stationary.
2. ``diagnose_single_run``, ``learn_parameter_surrogate``, ``recommend_parameters``,
   ``PredictionVerificationLedger`` and ``assess_cnc_greybox_governance`` remain honest
   and effective on an independent structurally-mismatched CNC plant (underdamped biquad
   command filter, P-PI servo cascade WITH velocity-loop integrator, continuous Stribeck
   friction inside the acceleration loop, and 168 Hz + 238 Hz dual structural modes).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Literal, Mapping

import numpy as np
import pytest

from axiom.benchmark import (
    AXES,
    BenchmarkArc,
    BenchmarkAxisLimits,
    BenchmarkSample,
    CncAlgorithmExport,
    CncBenchmarkCase,
    benchmark_case_hash,
    evaluate_cnc_export,
)

SourceKind = Literal["algorithm-export", "controller-trace", "synthetic-example"]
from axiom.benchmark_standard import StandardCaseSettings, standard_case
from axiom.cnc_governance import assess_cnc_greybox_governance
from axiom.controller_profile import (
    ControllerProfile,
    beckhoff_twincat_nc_profile,
    default_generic_controller_profile,
)
from axiom.greybox_model import (
    MICRO_SEGMENT_THRESHOLD_MM,
    _arc_geometry,
    _segment_ends,
    extract_case_geometry_profile,
    simulate_realistic_cnc_controller,
)
from axiom.machine.models import MachineTelemetryTrace
from axiom.machine.runtime import machine_trace_content_hash
from axiom.parameter_diagnoser import diagnose_single_run
from axiom.parameter_learner import ParameterLearningRequest, learn_parameter_surrogate
from axiom.parameter_recommender import ParameterRecommendationRequest, recommend_parameters
from axiom.parameter_space import default_parameter_values, generate_parameter_doe
from axiom.prediction_ledger import (
    build_prediction_verification_ledger,
    record_prediction_verification,
)


def _translate_case(
    case: CncBenchmarkCase, shift: tuple[float, float, float]
) -> CncBenchmarkCase:
    sx, sy, sz = shift
    new_path = tuple((p[0] + sx, p[1] + sy, p[2] + sz) for p in case.reference_path)
    new_arcs = (
        tuple(
            BenchmarkArc(
                segmentIndex=a.segment_index,
                centerMm=(a.center_mm[0] + sx, a.center_mm[1] + sy),
                direction=a.direction,
            )
            for a in case.reference_arcs
        )
        if case.reference_arcs
        else None
    )
    shift_by_ax = {"X": sx, "Y": sy, "Z": sz}
    new_limits = tuple(
        BenchmarkAxisLimits(
            axis=lim.axis,
            minimumPositionMm=lim.minimum_position_mm + shift_by_ax[lim.axis],
            maximumPositionMm=lim.maximum_position_mm + shift_by_ax[lim.axis],
            maximumVelocityMmS=lim.maximum_velocity_mm_s,
            maximumAccelerationMmS2=lim.maximum_acceleration_mm_s2,
            maximumJerkMmS3=lim.maximum_jerk_mm_s3,
        )
        for lim in case.axis_limits
    )
    return case.model_copy(
        update={
            "case_id": f"{case.case_id}.shifted",
            "reference_path": new_path,
            "reference_arcs": new_arcs,
            "axis_limits": new_limits,
        }
    )


def _wrap_as_r3_telemetry(
    case: CncBenchmarkCase,
    export: CncAlgorithmExport,
    *,
    trace_id: str,
    actual_y_bias_mm: float = 0.0,
) -> MachineTelemetryTrace:
    t0 = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
    dt = case.sample_period_seconds
    frames = []
    for k, s in enumerate(export.samples):
        act = s.actual_position_mm or s.position_mm
        ts = (t0 + timedelta(seconds=round(k * dt, 6))).isoformat().replace("+00:00", "Z")
        frames.append(
            {
                "sequenceId": k,
                "deviceTimestamp": ts,
                "samples": [
                    {"channelId": "cmd_x", "value": float(s.position_mm[0]), "quality": "good"},
                    {"channelId": "cmd_y", "value": float(s.position_mm[1]), "quality": "good"},
                    {"channelId": "cmd_z", "value": float(s.position_mm[2]), "quality": "good"},
                    {"channelId": "act_x", "value": float(act[0]), "quality": "good"},
                    {"channelId": "act_y", "value": float(act[1]) + actual_y_bias_mm, "quality": "good"},
                    {"channelId": "act_z", "value": float(act[2]), "quality": "good"},
                ],
            }
        )
    raw = {
        "schemaVersion": 1,
        "artifactType": "machine.telemetry-trace",
        "traceId": trace_id,
        "sourceKind": "controller-export",
        "deviceIdentity": {
            "deviceId": "adversarial-ppi-rig-01",
            "controllerFamily": "TwinCAT-3",
            "machineModel": "VMC-Adv",
        },
        "captureReceipt": {
            "receiptId": f"rcpt.{trace_id}",
            "sourceId": "axiom.windows-file-telemetry-source@1",
            "operation": "file-import",
            "transport": "windows-file-json",
            "capturedAt": "2026-11-12T12:05:00Z",
            "traceContentHash": "0" * 64,
        },
        "frames": frames,
    }
    unsigned = MachineTelemetryTrace.model_validate(raw)
    raw["captureReceipt"]["traceContentHash"] = machine_trace_content_hash(unsigned)
    return MachineTelemetryTrace.model_validate(raw)


def simulate_adversarial_mismatched_plant(
    case: CncBenchmarkCase,
    parameters: Mapping[str, float],
    *,
    source_kind: SourceKind = "controller-trace",
    controller_profile: ControllerProfile | None = None,
    primary_resonance_hz: float = 168.0,
    secondary_resonance_hz: float = 238.0,
) -> CncAlgorithmExport:
    """Structurally-mismatched CNC plant for adversarial verification.

    Deliberate structural mismatches relative to ``greybox_model.py``:
    1. Planner uses 0.62 lookahead factor and cubic Bezier corner blending (0.42 curvature ratio).
    2. Command filter is an underdamped 2nd-order IIR biquad low-pass (zeta = 0.62, complex poles
       with corner overshoot) rather than two real critically-damped RC poles.
    3. Servo loop is a true P-PI cascade WITH a velocity-loop integrator (K_iv > 0) and strongly
       asymmetric X/Y velocity bandwidth ratios (2.7 vs 5.8), violating the P-P steady-state
       velocity lag formula whenever V_ff != 1.0.
    4. Continuous nonlinear Stribeck + Coulomb friction acts directly inside the acceleration ODE.
    5. Dual lightly-damped structural modes at 168 Hz and 238 Hz.
    """
    ctrl_prof = controller_profile or default_generic_controller_profile()
    reg = ctrl_prof.registry
    p = {**default_parameter_values(reg), **dict(parameters)}
    q = ctrl_prof.to_canonical(p)
    prof = extract_case_geometry_profile(case)
    dt = case.sample_period_seconds

    raw_vertices = np.asarray(case.reference_path, dtype=np.float64)
    arcs_map = {arc.segment_index: arc for arc in (case.reference_arcs or ())}
    ends = _segment_ends(raw_vertices, arcs_map)
    n_segs = len(ends)

    v_prog = q.feed_override_ratio * prof.programmed_feed_mm_s
    eps_cor = q.corner_tolerance_mm
    eps_chord = q.small_seg_chord_tol_mm if ctrl_prof.capabilities.has_micro_spline else 0.0

    # Local curvature inward pull on micro-segments (with mismatched 0.48 realization factor)
    vertex_pull = np.zeros_like(raw_vertices, dtype=np.float64)
    if eps_chord > 0.0 and len(raw_vertices) >= 3:
        for v_i in range(1, len(raw_vertices) - 1):
            if (v_i - 1) in arcs_map or v_i in arcs_map:
                continue
            v_in = raw_vertices[v_i] - raw_vertices[v_i - 1]
            v_out = raw_vertices[v_i + 1] - raw_vertices[v_i]
            ds_p, ds_n = float(np.linalg.norm(v_in)), float(np.linalg.norm(v_out))
            if min(ds_p, ds_n) <= MICRO_SEGMENT_THRESHOLD_MM and ds_p > 1e-9 and ds_n > 1e-9:
                du = (v_out / ds_n) - (v_in / ds_p)
                du_n = float(np.linalg.norm(du))
                if du_n > 1e-9:
                    kappa = du_n / (0.5 * (ds_p + ds_n))
                    vertex_pull[v_i] = 0.48 * eps_chord * min(1.0, kappa / 0.06) * (du / du_n)

    corner_trim = [0.0] * (n_segs + 1)
    corner_v_map: dict[int, float] = {}
    psi_cubic_mismatched = 0.42 if q.spline_degree >= 5 else 0.51
    for (_, len_a, _, u_before), (idx_b, len_b, u_after, _) in zip(ends, ends[1:]):
        cos_v = float(np.clip(np.dot(u_before, u_after), -1.0, 1.0))
        ang_rad = math.acos(cos_v)
        ang_deg = math.degrees(ang_rad)
        if ang_deg <= q.collinear_merge_angle_deg:
            continue
        half_a = 0.5 * ang_rad
        eff_tol = eps_cor if ang_deg >= q.corner_angle_threshold_deg else 0.25 * eps_cor
        max_trim = 0.38 * min(len_a, len_b)
        r_in = eff_tol * math.cos(half_a) / max(1.0 - math.cos(half_a), 1e-6)
        d_trim = min(max_trim, r_in * math.tan(half_a))
        if max_trim > 1e-6 and r_in * math.tan(half_a) > max_trim:
            r_in = d_trim / max(math.tan(half_a), 1e-6)
        r_eff = max(1e-5, psi_cubic_mismatched * r_in)
        diff_u = u_after - u_before
        bisec = np.abs(diff_u / max(float(np.linalg.norm(diff_u)), 1e-9))
        a_cor = min(
            q.centripetal_acc_limit_mm_s2,
            q.axis_acc_limit_mm_s2[0] / bisec[0] if bisec[0] > 1e-9 else float("inf"),
            q.axis_acc_limit_mm_s2[1] / bisec[1] if bisec[1] > 1e-9 else float("inf"),
            q.axis_acc_limit_mm_s2[2] / bisec[2] if bisec[2] > 1e-9 else float("inf"),
        )
        corner_trim[idx_b] = d_trim
        corner_v_map[idx_b] = min(v_prog, q.curvature_speed_clamp_factor * math.sqrt(a_cor * r_eff))

    fine_pts: list[np.ndarray] = []
    fine_v_caps: list[float] = []
    for k_pos, (seg_idx, seg_len, u_start, _) in enumerate(ends):
        arc = arcs_map.get(seg_idx)
        ux, uy, uz = abs(u_start[0]), abs(u_start[1]), abs(u_start[2])
        v_ax = min(
            q.axis_vel_limit_mm_s[0] / ux if ux > 1e-9 else float("inf"),
            q.axis_vel_limit_mm_s[1] / uy if uy > 1e-9 else float("inf"),
            q.axis_vel_limit_mm_s[2] / uz if uz > 1e-9 else float("inf"),
        )
        a_ax = min(
            q.axis_acc_limit_mm_s2[0] / ux if ux > 1e-9 else float("inf"),
            q.axis_acc_limit_mm_s2[1] / uy if uy > 1e-9 else float("inf"),
            q.axis_acc_limit_mm_s2[2] / uz if uz > 1e-9 else float("inf"),
        )
        a_eff = min(q.path_tangential_acc_mm_s2, a_ax)
        if arc is not None:
            center, radius, a0, sweep = _arc_geometry(raw_vertices, arc)
            z0, z1 = float(raw_vertices[seg_idx, 2]), float(raw_vertices[seg_idx + 1, 2])
            v_seg_cap = min(v_prog, v_ax, q.curvature_speed_clamp_factor * math.sqrt(q.centripetal_acc_limit_mm_s2 * radius))
            n_sub = max(8, int(math.ceil(seg_len / 0.15)))
            for j in range(n_sub if k_pos < n_segs - 1 else n_sub + 1):
                frac_j = j / n_sub
                ang = a0 + sweep * frac_j
                fine_pts.append(np.array([center[0] + radius * math.cos(ang), center[1] + radius * math.sin(ang), z0 + (z1 - z0) * frac_j]))
                fine_v_caps.append(v_seg_cap)
        else:
            is_micro = seg_len <= MICRO_SEGMENT_THRESHOLD_MM
            # Mismatched lookahead factor 0.62 (vs kernel's 0.85)
            v_la = math.sqrt(max(1.0, 2.0 * 0.62 * a_eff * q.lookahead_block_count * max(seg_len, q.min_segment_length_mm))) if is_micro else float("inf")
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
                if is_micro and eps_chord > 0.0:
                    pt = pt + (1.0 - u_frac) * vertex_pull[seg_idx] + u_frac * vertex_pull[seg_idx + 1]
                fine_pts.append(pt)
                fine_v_caps.append(v_seg_cap)

            next_v = seg_idx + 1
            if next_v < len(raw_vertices) - 1 and corner_trim[next_v] > 1e-6 and not is_micro:
                p_in = p_start + (s1 / seg_len) * vec
                p_vx = raw_vertices[next_v]
                next_len = max(float(np.linalg.norm(raw_vertices[next_v + 1] - p_vx)), 1e-9)
                p_out = p_vx + (min(corner_trim[next_v], 0.45 * next_len) / next_len) * (raw_vertices[next_v + 1] - p_vx)
                v_cor_cap = corner_v_map.get(next_v, v_seg_cap)
                # Cubic Bezier blend (different curvature profile from kernel's quartic Bezier)
                for b_i in range(1, 13):
                    tau_b = b_i / 12.0
                    om = 1.0 - tau_b
                    b_pt = (om ** 3) * p_in + 3.0 * (om ** 2) * tau_b * p_vx + 3.0 * om * (tau_b ** 2) * p_vx + (tau_b ** 3) * p_out
                    fine_pts.append(b_pt)
                    fine_v_caps.append(v_cor_cap)

    pts_arr = np.asarray(fine_pts, dtype=np.float64)
    v_caps = np.asarray(fine_v_caps, dtype=np.float64)
    v_caps[0] = 0.0
    v_caps[-1] = 0.0
    ds_arr = np.linalg.norm(np.diff(pts_arr, axis=0), axis=1)
    eff_a = q.path_tangential_acc_mm_s2 / (1.0 + 0.45 * q.bell_acc_shape_factor)
    for i in range(len(ds_arr)):
        v_caps[i + 1] = min(v_caps[i + 1], math.sqrt(v_caps[i] ** 2 + 2.0 * eff_a * ds_arr[i]))
    for i in range(len(ds_arr) - 1, -1, -1):
        v_caps[i] = min(v_caps[i], math.sqrt(v_caps[i + 1] ** 2 + 2.0 * eff_a * ds_arr[i]))

    seg_dt = ds_arr / np.maximum(0.5 * (v_caps[:-1] + v_caps[1:]), 0.5)
    node_t = np.concatenate([[0.0], np.cumsum(seg_dt)])
    jerk_tail = 1.25 * q.path_tangential_acc_mm_s2 / max(q.path_tangential_jerk_mm_s3, 1000.0)
    node_t = node_t * ((node_t[-1] + jerk_tail) / max(node_t[-1], 1e-9))
    node_s = np.concatenate([[0.0], np.cumsum(ds_arr)])
    n_base = max(6, int(math.ceil(node_t[-1] / dt)) + 1)
    t_grid = np.arange(n_base, dtype=np.float64) * dt
    s_grid = np.interp(t_grid, node_t, node_s)

    n_scurve = min(12, max(2, int(round((0.40 * eff_a / max(q.path_tangential_jerk_mm_s3, 1000.0)) / dt))))
    if n_scurve > 1:
        ker_j = np.ones(n_scurve, dtype=np.float64) / n_scurve
        for _ in range(2):
            padded_s = np.concatenate([np.repeat(s_grid[:1], n_scurve - 1), s_grid, np.repeat(s_grid[-1:], n_scurve - 1)])
            s_grid = np.convolve(padded_s, ker_j, mode="valid")
        s_grid[0] = 0.0
        s_grid[-1] = node_s[-1]

    cmd_pos = np.column_stack([np.interp(s_grid, node_s, pts_arr[:, ax]) for ax in range(3)])

    # Causal boxcar FIR
    n_fir = max(1, int(round(q.fir_time_s / dt)))
    if n_fir > 1:
        padded = np.vstack([np.repeat(cmd_pos[:1, :], n_fir - 1, axis=0), cmd_pos, np.repeat(cmd_pos[-1:, :], n_fir - 1, axis=0)])
        ker = np.ones(n_fir, dtype=np.float64) / n_fir
        cmd_pos = np.column_stack([np.convolve(padded[:, ax], ker, mode="valid") for ax in range(3)])

    # True underdamped 2nd-order biquad command lowpass (zeta = 0.62 -> complex poles & overshoot!)
    f_lp = q.lowpass_cutoff_hz
    b_lp: tuple[float, float, float] | None = None
    a_lp: tuple[float, float] | None = None
    if f_lp is not None and 2.0 < f_lp < 0.45 / dt:
        w0_lp = 2.0 * math.pi * f_lp * dt
        zeta_lp = 0.62
        alpha_b = math.sin(w0_lp) * zeta_lp
        cw = math.cos(w0_lp)
        a0_l = 1.0 + alpha_b
        b0_l = (0.5 * (1.0 - cw)) / a0_l
        b1_l = (1.0 - cw) / a0_l
        b2_l = b0_l
        a1_l = (-2.0 * cw) / a0_l
        a2_l = (1.0 - alpha_b) / a0_l
        b_lp = (b0_l, b1_l, b2_l)
        a_lp = (a1_l, a2_l)

        # Append settling tail so the underdamped biquad reaches the endpoint cleanly
        n_tail = min(35, max(6, int(round(2.5 / (f_lp * dt)))))
        cmd_ext = np.vstack([cmd_pos, np.repeat(raw_vertices[-1:], n_tail, axis=0)])
        lp_out = np.empty_like(cmd_ext)
        for ax in range(3):
            x0 = float(cmd_ext[0, ax])
            x1 = x2 = y1 = y2 = x0
            for k in range(len(cmd_ext)):
                xk = float(cmd_ext[k, ax])
                yk = b0_l * xk + b1_l * x1 + b2_l * x2 - a1_l * y1 - a2_l * y2
                x2, x1, y2, y1 = x1, xk, y1, yk
                lp_out[k, ax] = yk
        lp_out[0] = raw_vertices[0]
        lp_out[-1] = raw_vertices[-1]
        cmd_pos = lp_out

    n_total = len(cmd_pos)
    t_full = np.arange(n_total, dtype=np.float64) * dt

    act_pos: np.ndarray | None = None
    if source_kind == "controller-trace":
        kp_arr = np.array(q.servo_kp_1_s, dtype=np.float64)
        vff_arr = np.array(q.vel_feedforward_ratio, dtype=np.float64)
        aff_arr = np.array(q.acc_feedforward_ratio, dtype=np.float64)
        fric_comp = np.array([q.friction_comp_amp_mm[0], q.friction_comp_amp_mm[1], 0.0], dtype=np.float64)

        cmd_vel = np.gradient(cmd_pos, dt, axis=0)
        cmd_acc = np.gradient(cmd_vel, dt, axis=0)

        # Strongly asymmetric velocity-loop ratios + P-PI velocity integrator + continuous Stribeck ODE
        psi_v_mismatched = np.array([2.7, 5.8, 3.4], dtype=np.float64)
        stiction_acc = np.array([42.0, 26.0, 0.0], dtype=np.float64)  # mm/s^2 inside acceleration loop
        coulomb_acc = np.array([22.0, 14.0, 0.0], dtype=np.float64)
        act_pos = np.zeros_like(cmd_pos)
        n_sub_ode = max(6, int(math.ceil(dt * float(np.max(kp_arr * psi_v_mismatched)) * 5.0)))
        h = dt / n_sub_ode

        for ax in range(3):
            pos_s = float(cmd_pos[0, ax])
            vel_s = 0.0
            xi_v = 0.0  # Velocity-loop PI integrator state!
            kp_a = float(kp_arr[ax])
            wv_a = float(psi_v_mismatched[ax]) * kp_a
            kiv_a = 0.22 * wv_a * wv_a
            vff_a = float(vff_arr[ax])
            aff_a = float(aff_arr[ax])
            st_a = float(stiction_acc[ax])
            co_a = float(coulomb_acc[ax])
            # Controller friction feedforward compensation converted to acceleration pulse
            fc_gain = float(fric_comp[ax]) / 0.011 * st_a if st_a > 0 else 0.0
            act_pos[0, ax] = pos_s

            for k in range(n_total - 1):
                for sub in range(n_sub_ode):
                    frac = (sub + 1) / n_sub_ode
                    qc = float(cmd_pos[k, ax] + frac * (cmd_pos[k + 1, ax] - cmd_pos[k, ax]))
                    vc = float(cmd_vel[k, ax] + frac * (cmd_vel[k + 1, ax] - cmd_vel[k, ax]))
                    ac = float(cmd_acc[k, ax] + frac * (cmd_acc[k + 1, ax] - cmd_acc[k, ax]))

                    v_ref = kp_a * (qc - pos_s) + vff_a * vc
                    v_err = v_ref - vel_s
                    xi_v += h * kiv_a * v_err
                    xi_v = max(-1500.0, min(1500.0, xi_v))

                    # Continuous nonlinear Stribeck friction opposing actual velocity, minus NC friction feedforward
                    stribeck_mag = co_a + (st_a - co_a) * math.exp(-((vel_s / 3.5) ** 2))
                    f_opp = stribeck_mag * math.tanh(vel_s / 0.35)
                    f_comp = fc_gain * math.tanh(vc / 0.45)

                    acc_s = wv_a * v_err + xi_v + aff_a * ac - f_opp + f_comp
                    vel_s += h * acc_s
                    pos_s += h * vel_s
                act_pos[k + 1, ax] = pos_s

        # Dual-mode structural dynamics (168 Hz + 238 Hz) excited by trajectory motion
        s_end = float(node_s[-1]) if len(node_s) > 0 else 0.0
        if s_end > 1e-6 and 0.5 / dt > primary_resonance_hz * 1.12:
            taper = np.clip(np.minimum(s_grid / 0.5, (s_end - s_grid) / 0.5), 0.0, 1.0)
            m_idx = np.arange(1, 37, dtype=np.float64)
            k_sp = 1.2 + 4.8 * ((m_idx * 0.61803398875) % 1.0)
            max_ds = float(np.max(np.abs(np.diff(s_grid)))) if len(s_grid) > 1 else 0.0
            nyq_m = (k_sp * max_ds <= 0.42).astype(np.float64)
            n_act = max(1.0, float(np.sum(nyq_m)))
            ph = 2.0 * math.pi * ((m_idx * 0.2718281828) % 1.0)
            tex = 0.00038 * taper * np.sum(
                (np.sin(2.0 * math.pi * np.outer(s_grid, k_sp) + ph) * nyq_m) / math.sqrt(n_act), axis=1
            )
            if n_fir > 1:
                pad_t = np.concatenate([np.repeat(tex[:1], n_fir - 1), tex, np.repeat(tex[-1:], n_fir - 1)])
                tex = np.convolve(pad_t, np.ones(n_fir, dtype=np.float64) / n_fir, mode="valid")
            if len(tex) < n_total:
                tex = np.pad(tex, (0, n_total - len(tex)), mode="edge")
            else:
                tex = tex[:n_total]
            alpha_hp = math.exp(-dt / 0.003)
            tex_hp = np.zeros(n_total, dtype=np.float64)
            lp_s = float(tex[0])
            for k in range(n_total):
                xk = float(tex[k])
                lp_s = alpha_hp * lp_s + (1.0 - alpha_hp) * xk
                tex_hp[k] = xk - lp_s

            cmd_jrk = np.gradient(cmd_acc, dt, axis=0)
            raw_u = ((0.5 * (float(kp_arr[0]) + float(kp_arr[1])) / 60.0) ** 0.70) * (
                8.0e-10 * (cmd_jrk[:, 0] - 0.65 * cmd_jrk[:, 1]) + 1.0 * tex_hp
            )

            f_notch = q.notch_freq_hz
            if f_notch is not None and 1.0 < f_notch < 0.48 / dt:
                w0 = 2.0 * math.pi * f_notch * dt
                alpha_n = math.sin(w0) * math.sinh(
                    0.5 * math.log(2.0) * (2.0 * math.pi * 26.0 * dt) / max(math.sin(w0), 1e-6)
                )
                a0 = 1.0 + alpha_n
                b0, b1, b2 = 1.0 / a0, (-2.0 * math.cos(w0)) / a0, 1.0 / a0
                a1, a2 = (-2.0 * math.cos(w0)) / a0, (1.0 - alpha_n) / a0
                u_drv = np.zeros_like(raw_u)
                x1 = x2 = y1 = y2 = 0.0
                for k in range(n_total):
                    xk = float(raw_u[k])
                    yk = b0 * xk + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                    x2, x1, y2, y1 = x1, xk, y1, yk
                    u_drv[k] = yk
            else:
                u_drv = raw_u

            total_vib = np.zeros(n_total, dtype=np.float64)
            for f_mode, zeta_m, weight_m in (
                (primary_resonance_hz, 0.015, 1.0),
                (secondary_resonance_hz, 0.032, 0.25),
            ):
                if 0.5 / dt <= f_mode * 1.08:
                    continue
                wr = 2.0 * math.pi * f_mode
                z_p, z_v = 0.0, 0.0
                n_sub_r = max(4, int(math.ceil(dt * wr * 2.0)))
                hr = dt / n_sub_r
                w2 = wr * wr
                tzw = 2.0 * zeta_m * wr
                mode_disp = np.zeros(n_total, dtype=np.float64)
                for k in range(n_total):
                    uk = weight_m * float(u_drv[k])
                    for _ in range(n_sub_r):
                        k1z, k1v = z_v, w2 * (uk - z_p) - tzw * z_v
                        z2, v2 = z_p + 0.5 * hr * k1z, z_v + 0.5 * hr * k1v
                        k2z, k2v = v2, w2 * (uk - z2) - tzw * v2
                        z3, v3 = z_p + 0.5 * hr * k2z, z_v + 0.5 * hr * k2v
                        k3z, k3v = v3, w2 * (uk - z3) - tzw * v3
                        z4, v4 = z_p + hr * k3z, z_v + hr * k3v
                        k4z, k4v = v4, w2 * (uk - z4) - tzw * v4
                        z_p += (hr / 6.0) * (k1z + 2.0 * k2z + 2.0 * k3z + k4z)
                        z_v += (hr / 6.0) * (k1v + 2.0 * k2v + 2.0 * k3v + k4v)
                    mode_disp[k] = z_p
                total_vib += mode_disp
            total_vib[0] = 0.0
            total_vib[-1] = 0.0
            act_pos[:, 0] += total_vib
            act_pos[:, 1] -= 0.75 * total_vib

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
        algorithmId="test.adversarial-mismatched-plant",
        algorithmVersion="v1",
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


def test_simulator_galilean_translation_invariance_and_collinear_micro_segments() -> None:
    reg_prof = default_generic_controller_profile()
    params = default_parameter_values(reg_prof.registry)
    params["g1.small_seg_chord_tol_mm"] = 0.015
    params["g1.corner_tolerance_mm"] = 0.025
    params["g2.fir_moving_avg_time_ms"] = 4.0
    params["g3.notch_filter_freq_hz"] = 270.0

    shift = (520.0, -780.0, 135.0)
    for cname in ("small-segments", "corner90", "circle"):
        base_case = standard_case(cname)
        shifted_case = _translate_case(base_case, shift)

        exp_0 = simulate_realistic_cnc_controller(
            base_case, params, source_kind="controller-trace", controller_profile=reg_prof
        )
        exp_1 = simulate_realistic_cnc_controller(
            shifted_case, params, source_kind="controller-trace", controller_profile=reg_prof
        )
        rep_0 = evaluate_cnc_export(base_case, exp_0)
        rep_1 = evaluate_cnc_export(shifted_case, exp_1)
        assert rep_0.servo_metrics is not None and rep_1.servo_metrics is not None

        assert rep_1.kinematic_summary["durationSeconds"] == pytest.approx(
            rep_0.kinematic_summary["durationSeconds"], abs=1e-9
        )
        assert rep_1.analysis.metrics["sampledPathDeviationMaxMm"].value == pytest.approx(
            rep_0.analysis.metrics["sampledPathDeviationMaxMm"].value, abs=1e-6
        )
        assert rep_1.servo_metrics["actualPathDeviationMaxMm"].value == pytest.approx(
            rep_0.servo_metrics["actualPathDeviationMaxMm"].value, abs=1e-6
        )
        assert rep_1.servo_metrics["resonanceBandRmsMm"].value == pytest.approx(
            rep_0.servo_metrics["resonanceBandRmsMm"].value, abs=1e-6
        )

    # Collinear straight micro-segments at Y = -450 mm must NOT artificially bend toward Y = 0
    collinear_case = CncBenchmarkCase(
        caseId="test.collinear-micro-offset",
        coordinateFrame="workpiece",
        unit="mm",
        samplePeriodSeconds=0.001,
        programmedFeedMmMin=3000.0,
        referencePath=tuple((round(0.2 * i, 4), -450.0, 25.0) for i in range(101)),
        axisLimits=tuple(
            BenchmarkAxisLimits(
                axis=ax,
                minimumPositionMm=-1000.0,
                maximumPositionMm=1000.0,
                maximumVelocityMmS=500.0,
                maximumAccelerationMmS2=5000.0,
                maximumJerkMmS3=500_000.0,
            )
            for ax in AXES
        ),
        maximumPathDeviationMm=0.05,
        maximumEndpointErrorMm=0.001,
    )
    col_exp = simulate_realistic_cnc_controller(
        collinear_case, params, source_kind="algorithm-export", controller_profile=reg_prof
    )
    col_rep = evaluate_cnc_export(collinear_case, col_exp)
    assert (col_rep.analysis.metrics["sampledPathDeviationMaxMm"].value or 0.0) < 1e-6


def test_simulator_zero_vibration_when_quasi_stationary() -> None:
    # Micro-displacement hold (0.0002 mm total travel << 0.5 mm taper -> zero motion excitation)
    tiny_hold_case = CncBenchmarkCase(
        caseId="test.stationary-hold",
        coordinateFrame="workpiece",
        unit="mm",
        samplePeriodSeconds=0.001,
        programmedFeedMmMin=60.0,
        referencePath=((120.0, -85.0, 10.0), (120.0002, -85.0, 10.0)),
        axisLimits=tuple(
            BenchmarkAxisLimits(
                axis=ax,
                minimumPositionMm=-500.0,
                maximumPositionMm=500.0,
                maximumVelocityMmS=500.0,
                maximumAccelerationMmS2=5000.0,
                maximumJerkMmS3=500_000.0,
            )
            for ax in AXES
        ),
        maximumPathDeviationMm=0.05,
        maximumEndpointErrorMm=0.001,
    )
    params = default_parameter_values()
    params["g3.notch_filter_freq_hz"] = 290.0
    params["g2.fir_moving_avg_time_ms"] = 1.0
    exp = simulate_realistic_cnc_controller(
        tiny_hold_case, params, source_kind="controller-trace", machine_resonance_hz=135.0
    )
    # Motion is purely a 0.2 um step along X, so transverse Y (-0.7 * res_disp) isolates structural vibration:
    # under the old injected math.sin(omega_r * t), Y oscillated continuously at ~3 um even when holding still!
    y_osc = [
        abs((s.actual_position_mm or s.position_mm)[1] - (-85.0))
        for s in exp.samples
    ]
    assert max(y_osc) < 5e-5
    rep_hold = evaluate_cnc_export(tiny_hold_case, exp)
    assert rep_hold.servo_metrics is not None
    assert (rep_hold.servo_metrics["resonanceBandRmsMm"].value or 0.0) < 1e-5


def test_single_run_diagnoser_reduces_168hz_resonance_on_adversarial_mismatched_plant() -> None:
    tc = beckhoff_twincat_nc_profile()
    circle_case = standard_case("circle", StandardCaseSettings(sample_period_seconds=0.001))

    bad_params = default_parameter_values(tc.registry)
    bad_params["tc.moving_avg_filter_s"] = 0.002  # 2.0 ms in seconds
    bad_params["tc.ax5000_notch_hz"] = 310.0
    bad_params["tc.kv_factor_x_m_min_mm"] = 5.1  # 85 1/s
    bad_params["tc.kv_factor_y_m_min_mm"] = 2.7  # 45 1/s

    exp_before = simulate_adversarial_mismatched_plant(
        circle_case,
        bad_params,
        source_kind="controller-trace",
        controller_profile=tc,
        primary_resonance_hz=168.0,
    )
    diag = diagnose_single_run(
        circle_case,
        exp_before,
        controller_profile=tc,
        include_drive_side=False,
    )
    assert 1 <= len(diag.top_actions) <= 2
    res_finding = next(f for f in diag.findings if f.finding_id == "diag.structural-resonance")
    fir_sug = next(s for s in res_finding.suggestions if s.parameter_id == "tc.moving_avg_filter_s")
    # 1 / 168 Hz ~= 0.00595 s -> must target the actual 168 Hz mode in TwinCAT seconds, NOT 115 Hz!
    assert 0.0052 <= fir_sug.suggested_value <= 0.0068

    # Apply ONLY the NC-tunable diagnostic top_actions back onto the adversarial plant
    tuned_params = dict(bad_params)
    drive_or_ro = {
        b.vendor_parameter_id for b in tc.bindings if b.tunability in {"drive-side", "read-only"}
    }
    for act in diag.top_actions:
        assert act.parameter_id not in drive_or_ro
        tuned_params[act.parameter_id] = act.suggested_value

    exp_after = simulate_adversarial_mismatched_plant(
        circle_case,
        tuned_params,
        source_kind="controller-trace",
        controller_profile=tc,
        primary_resonance_hz=168.0,
    )
    rep_before = evaluate_cnc_export(circle_case, exp_before)
    rep_after = evaluate_cnc_export(circle_case, exp_after)
    assert rep_before.servo_metrics is not None and rep_after.servo_metrics is not None

    vib_before = rep_before.servo_metrics["resonanceBandRmsMm"].value or 0.0
    vib_after = rep_after.servo_metrics["resonanceBandRmsMm"].value or 0.0
    assert vib_before > 0.0008
    assert vib_after < 0.55 * vib_before


def test_adversarial_mismatched_plant_doe_recommendation_and_ledger_reconciliation() -> None:
    tc = beckhoff_twincat_nc_profile()
    train_cases = (
        standard_case("corner90"),
        standard_case("circle"),
        standard_case("small-segments"),
        standard_case("line"),
    )
    train_map = {c.case_id: c for c in train_cases}
    unseen_scurve = standard_case("s-curve")

    doe = generate_parameter_doe(
        offline_count=12,
        controller_count=8,
        seed=303,
        controller_profile=tc,
    )
    all_pts = (*doe.offline_samples, *doe.controller_samples)
    exports = [
        simulate_adversarial_mismatched_plant(
            train_map.get(pt.recommended_case_id or "", train_cases[idx % len(train_cases)]),
            pt.parameters,
            source_kind=pt.target_source,
            controller_profile=tc,
            primary_resonance_hz=168.0,
        )
        for idx, pt in enumerate(all_pts)
    ]

    surrogate = learn_parameter_surrogate(
        ParameterLearningRequest(
            registry=tc.registry,
            controllerProfile=tc,
            cases=train_cases,
            exports=tuple(exports),
        )
    )
    assert surrogate.cross_toolpath_validation is not None
    assert surrogate.cross_toolpath_validation.evaluated_case_count == 4

    # Recommend NC-only parameters for unseen s-curve with realistic shop-floor tolerance
    base_params = default_parameter_values(tc.registry)
    rec = recommend_parameters(
        surrogate,
        ParameterRecommendationRequest(
            targetCase=unseen_scurve,
            baselineParameters=base_params,
            includeDriveSideParameters=False,
            maximumPathDeviationMm=0.075,
            maximumActualPathDeviationMm=0.095,
            candidatePoolSize=160,
            seed=55,
        ),
    )
    assert len(rec.presets) >= 1
    chosen = rec.presets[0]

    # Replay on the adversarial plant across 3 distinct cases & reconcile via R3 holdout ledger
    holdout_entries = []
    for idx, hold_case in enumerate((unseen_scurve, train_cases[0], train_cases[1]), 1):
        rec_h = recommend_parameters(
            surrogate,
            ParameterRecommendationRequest(
                targetCase=hold_case,
                baselineParameters=base_params,
                includeDriveSideParameters=False,
                maximumPathDeviationMm=0.080,
                maximumActualPathDeviationMm=0.105,
                candidatePoolSize=140,
                seed=60 + idx,
            ),
        )
        cand_h = rec_h.presets[0] if rec_h.presets else chosen
        ver_exp = simulate_adversarial_mismatched_plant(
            hold_case,
            cand_h.full_parameters,
            source_kind="controller-trace",
            controller_profile=tc,
            primary_resonance_hz=168.0,
        )
        ver_rep = evaluate_cnc_export(hold_case, ver_exp)
        assert ver_rep.servo_metrics is not None
        assert (ver_rep.servo_metrics["actualPathDeviationMaxMm"].value or 0.0) <= 0.105

        r3_trace = _wrap_as_r3_telemetry(hold_case, ver_exp, trace_id=f"adv.r3.{idx}")
        holdout_entries.append(
            record_prediction_verification(
                hold_case,
                surrogate,
                r3_trace,
                applied_parameters=cand_h.full_parameters,
                entry_id=f"adv.holdout.{idx:03d}",
            )
        )

    ledger = build_prediction_verification_ledger(holdout_entries, surrogate=surrogate)
    assert ledger.summary.distinct_real_r3_trace_count == 3
    assert ledger.summary.empirical_coverage_rate is not None

    # Governance must evaluate R4/R5 empirically (never Inconclusive once >= 3 R3 holdouts exist)
    last_exp = simulate_adversarial_mismatched_plant(
        unseen_scurve,
        chosen.full_parameters,
        source_kind="controller-trace",
        controller_profile=tc,
        primary_resonance_hz=168.0,
    )
    gov = assess_cnc_greybox_governance(
        unseen_scurve,
        export=last_exp,
        surrogate=surrogate,
        recommendation_report=rec,
        verification_ledger=ledger,
    )
    claims = {c.claim_definition_id: c for c in gov.run_bundle.claims}
    assert claims["cnc-greybox.r4-calibration-claim@1"].status in {"Supported", "Refuted"}
    assert claims["cnc-greybox.r5-epistemic-claim@1"].status in {"Supported", "Refuted"}

    # Conversely, if the real machine experiences unmodeled structural/thermal drift (+0.085 mm Y deflection)
    # beyond the surrogate's declared LOO/LOCO bounds, governance MUST refute R4 & R5!
    drifted_entries = [
        record_prediction_verification(
            hold_case,
            surrogate,
            _wrap_as_r3_telemetry(
                hold_case,
                simulate_adversarial_mismatched_plant(
                    hold_case,
                    chosen.full_parameters,
                    source_kind="controller-trace",
                    controller_profile=tc,
                    primary_resonance_hz=168.0,
                ),
                trace_id=f"adv.bad.r3.{idx}",
                actual_y_bias_mm=0.085,
            ),
            applied_parameters=chosen.full_parameters,
            entry_id=f"adv.bad.{idx:03d}",
        )
        for idx, hold_case in enumerate((unseen_scurve, train_cases[0], train_cases[1]), 1)
    ]
    bad_ledger = build_prediction_verification_ledger(drifted_entries, surrogate=surrogate)
    assert (bad_ledger.summary.empirical_coverage_rate or 1.0) < 0.70

    bad_gov = assess_cnc_greybox_governance(
        unseen_scurve,
        export=last_exp,
        surrogate=surrogate,
        recommendation_report=rec,
        verification_ledger=bad_ledger,
    )
    bad_claims = {c.claim_definition_id: c for c in bad_gov.run_bundle.claims}
    assert bad_claims["cnc-greybox.r4-calibration-claim@1"].status == "Refuted"
    assert bad_claims["cnc-greybox.r5-epistemic-claim@1"].status == "Refuted"
