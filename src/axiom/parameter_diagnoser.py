"""Single-run CNC trajectory & servo diagnostic advisor (zero-DoE shop-floor workflow).

Designed for CNC commissioning and process engineers who want immediate, explainable
guidance from ONE captured trace (`CncBenchmarkCase` + `CncAlgorithmExport` or
`CncQualityReport`) without running a 30+ run Design of Experiments first:

1. Separates error sources by physical mechanism:
   - Structural resonance (`dominantResonanceFreqHz`, `resonanceBandRmsMm`) -> closed-form
     FIR sinc spectral zero `T_fir = 1 / f_res` and/or drive notch alignment `f_notch = f_res`.
   - Quadrant crossing stiction (`quadrantGlitchExcessMm`) -> friction compensation step.
   - Circular arc inward shrink vs outward wide-swing (`signedRadialOffsetMeanMm`) ->
     separates command filter shrink (`sampledPathDeviationMaxMm`) from servo lag/feedforward.
   - Command corner / micro-segment over-tolerance (`sampledPathDeviationMaxMm` > limit) ->
     proportional geometric tolerance tightening.
   - XY servo gain / velocity feedforward mismatch -> axis equalization.
   - Cycle-time headroom -> conservative corner tolerance or tangential acceleration step
     when contour error is well below specification.
2. Translates all recommendations through `ControllerProfile` into the target CNC vendor's
   native parameter IDs, units (`mm`, `um`, `ms`, `s`, `(m/min)/mm`, `%`, `m/s^2`), bounds,
   and tunability (`nc-tunable` vs `drive-side`).
3. Attaches explicit confidence labels (`High`, `Medium`, `TrendOnly`) and restricts
   `topActions` to at most 2 parameters so the next test cut stays attributable.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any, Literal, Mapping

from pydantic import Field

from .benchmark import (
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncQualityReport,
    evaluate_cnc_export,
)
from .controller_profile import (
    CanonicalSlotId,
    ControllerProfile,
    ParameterTunability,
    default_generic_controller_profile,
)
from .greybox_model import extract_case_geometry_profile
from .models import AxiomModel
from .parameter_space import SourceKind, default_parameter_values

PredictionConfidenceLevel = Literal["High", "Medium", "TrendOnly"]
DiagnosticErrorSource = Literal[
    "PlanningOrFilter",
    "ServoTracking",
    "StructuralResonance",
    "QuadrantFriction",
    "HeadroomAvailable",
]


def _canonical_hash(payload: AxiomModel | Mapping[str, Any]) -> str:
    data = (
        payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(payload, AxiomModel)
        else dict(payload)
    )
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SingleRunParameterSuggestion(AxiomModel):
    """One explainable parameter adjustment derived from physical diagnostic laws."""

    parameter_id: str = Field(alias="parameterId")
    display_name: str = Field(alias="displayName")
    unit: str
    tunability: ParameterTunability
    current_value: float = Field(alias="currentValue")
    suggested_value: float = Field(alias="suggestedValue")
    delta: float
    mechanism_formula: str = Field(alias="mechanismFormula")
    expected_effect: str = Field(alias="expectedEffect")
    confidence_level: PredictionConfidenceLevel = Field(alias="confidenceLevel")
    verification_note: str = Field(alias="verificationNote")


class SingleRunDiagnosticFinding(AxiomModel):
    """One diagnosed bottleneck or anomaly from a single CNC evaluation report."""

    finding_id: str = Field(alias="findingId")
    severity: Literal["Critical", "Warning", "Info"]
    symptom: str
    dominant_primitive: str = Field(alias="dominantPrimitive")
    error_source: DiagnosticErrorSource = Field(alias="errorSource")
    observed_metric_id: str = Field(alias="observedMetricId")
    observed_value: float = Field(alias="observedValue")
    unit: str
    suggestions: tuple[SingleRunParameterSuggestion, ...] = ()


class CncSingleRunDiagnosticReport(AxiomModel):
    """Shop-floor single-run diagnostic report with <= 2 prioritized next-cut adjustments."""

    schema_id: Literal["axiom.cnc-single-run-diagnostic-report@1"] = Field(
        default="axiom.cnc-single-run-diagnostic-report@1", alias="schemaId"
    )
    case_id: str = Field(alias="caseId")
    controller_profile_id: str = Field(alias="controllerProfileId")
    source_kind: SourceKind = Field(alias="sourceKind")
    summary_headline: str = Field(alias="summaryHeadline")
    cycle_time_confidence: PredictionConfidenceLevel = Field(
        default="High", alias="cycleTimeConfidence"
    )
    contour_error_confidence: PredictionConfidenceLevel = Field(
        default="TrendOnly", alias="contourErrorConfidence"
    )
    confidence_statement: str = Field(alias="confidenceStatement")
    findings: tuple[SingleRunDiagnosticFinding, ...]
    top_actions: tuple[SingleRunParameterSuggestion, ...] = Field(alias="topActions")
    permission_level: Literal["OfflineAdvisory"] = Field(
        default="OfflineAdvisory", alias="permissionLevel"
    )
    device_write_allowed: Literal[False] = Field(default=False, alias="deviceWriteAllowed")
    report_content_hash: str = Field(alias="reportContentHash")


def _metric_val(metrics: Mapping[str, Any] | None, key: str) -> float | None:
    if not metrics or key not in metrics:
        return None
    m = metrics[key]
    val = getattr(m, "value", None)
    return float(val) if val is not None else None


def _dominant_primitive(report: CncQualityReport, use_actual: bool) -> str:
    if not report.geometry_slices:
        return "global"
    best_kind = "global"
    best_err = -1.0
    for sl in report.geometry_slices:
        act_v = sl.metrics.get("actualPathDeviationMaxMm")
        cmd_v = sl.metrics.get("sampledPathDeviationMaxMm")
        err = float(act_v if (use_actual and act_v is not None) else (cmd_v or 0.0))
        if err > best_err:
            best_err = err
            best_kind = sl.primitive_kind
    return best_kind


def diagnose_single_run(
    case: CncBenchmarkCase,
    export_or_report: CncAlgorithmExport | CncQualityReport,
    *,
    parameters: Mapping[str, float] | None = None,
    controller_profile: ControllerProfile | None = None,
    include_drive_side: bool = True,
    max_top_actions: int = 2,
) -> CncSingleRunDiagnosticReport:
    """Diagnose a single CNC run and emit 1-2 formula-grounded vendor parameter suggestions."""
    prof = controller_profile or default_generic_controller_profile()
    reg = prof.registry
    param_map = {p.parameter_id: p for p in reg.parameters}
    binding_map = {b.vendor_parameter_id: b for b in prof.bindings}
    allowed_ids = prof.tunable_parameter_ids(include_drive_side=include_drive_side)

    if isinstance(export_or_report, CncAlgorithmExport):
        quality_report = evaluate_cnc_export(case, export_or_report)
        raw_params = parameters if parameters is not None else export_or_report.parameters
    else:
        quality_report = export_or_report
        raw_params = parameters

    base_params = default_parameter_values(reg)
    if raw_params:
        unknown = sorted(set(raw_params) - set(param_map))
        if unknown:
            raise ValueError(
                f"parameters contain IDs not in controller profile {prof.profile_id} "
                f"({reg.registry_id}): {', '.join(unknown[:6])}"
            )
        for k, v in raw_params.items():
            base_params[k] = float(v)

    q = prof.to_canonical(base_params)
    geom = extract_case_geometry_profile(case)
    has_servo = quality_report.servo_metrics is not None
    dom_prim = _dominant_primitive(quality_report, use_actual=has_servo)

    def _make_suggestion(
        slot: CanonicalSlotId,
        target_canonical: float,
        *,
        formula: str,
        effect: str,
        confidence: PredictionConfidenceLevel,
        note: str,
    ) -> SingleRunParameterSuggestion | None:
        mapped = prof.from_canonical_value(slot, target_canonical)
        if mapped is None:
            return None
        pid, sug_val = mapped
        if pid not in allowed_ids:
            return None
        cur_val = float(base_params[pid])
        p_def = param_map[pid]
        span = float(p_def.bounds[1] - p_def.bounds[0])
        if abs(sug_val - cur_val) <= max(1e-7, 0.005 * span):
            return None
        tun = binding_map[pid].tunability if pid in binding_map else "nc-tunable"
        return SingleRunParameterSuggestion(
            parameterId=pid,
            displayName=p_def.display_name,
            unit=p_def.unit,
            tunability=tun,
            currentValue=round(cur_val, 6),
            suggestedValue=round(sug_val, 6),
            delta=round(sug_val - cur_val, 6),
            mechanismFormula=formula,
            expectedEffect=effect,
            confidenceLevel=confidence,
            verificationNote=note,
        )

    findings: list[SingleRunDiagnosticFinding] = []
    limit_mm = float(case.maximum_path_deviation_mm or 0.05)
    cmd_dev = float(quality_report.kinematic_summary["sampledPathDeviationMaxMm"])
    dur_s = float(quality_report.kinematic_summary["durationSeconds"])
    act_dev = _metric_val(quality_report.servo_metrics, "actualPathDeviationMaxMm")

    # 1. Structural Resonance Peak -> exact FIR sinc spectral zero & drive notch
    f_res = _metric_val(quality_report.servo_metrics, "dominantResonanceFreqHz")
    res_rms = _metric_val(quality_report.servo_metrics, "resonanceBandRmsMm")
    if f_res is not None and f_res >= 25.0 and res_rms is not None and res_rms > 0.0007:
        res_sugs: list[SingleRunParameterSuggestion] = []
        if prof.capabilities.has_fir_filter:
            t_zero_s = 1.0 / f_res
            # If 1/f_res is shorter than current FIR and contour allows, or close to 1/f_res;
            # check if 1/f_res or 2/f_res is closer to current FIR window to avoid unnecessary cycle lag
            if q.fir_time_s > 1.6 * t_zero_s:
                t_zero_s = 2.0 / f_res
            s_fir = _make_suggestion(
                "fir_time_s",
                t_zero_s,
                formula=f"FIR 频谱零点对齐：T_fir = k / f_res (f_res = {f_res:.1f} Hz)",
                effect=f"在 {f_res:.1f} Hz 处形成精确 sinc 陷波零点，从插补源头切断机械谐振激励",
                confidence="High",
                note="线性滑动平均滤波器零点频率属确定性白盒关系（高置信度）；调整后复核圆弧内缩是否超限",
            )
            if s_fir is not None:
                res_sugs.append(s_fir)
        if prof.capabilities.has_drive_notch_filter:
            s_notch = _make_suggestion(
                "notch_freq_hz",
                f_res,
                formula=f"伺服陷波中心频率对齐：f_notch = f_res = {f_res:.1f} Hz",
                effect=f"抑制驱动环路在 {f_res:.1f} Hz 附近的结构谐振纹波（当前 RMS={res_rms * 1000:.1f} um）",
                confidence="High",
                note="谐振中心频率由实测残差 FFT 直接定位；驱动侧修改后需确认速度环相位裕度稳定",
            )
            if s_notch is not None:
                res_sugs.append(s_notch)
        findings.append(
            SingleRunDiagnosticFinding(
                findingId="diag.structural-resonance",
                severity="Critical" if res_rms > 0.0025 else "Warning",
                symptom=f"检测到 {f_res:.1f} Hz 机械结构谐振峰（频带残差 RMS = {res_rms * 1000:.1f} um）",
                dominantPrimitive=dom_prim,
                errorSource="StructuralResonance",
                observedMetricId="resonanceBandRmsMm",
                observedValue=round(res_rms, 6),
                unit="mm",
                suggestions=tuple(res_sugs),
            )
        )

    # 2. Command planning / filtering over-tolerance
    if cmd_dev > limit_mm:
        scale_tol = max(0.25, min(0.85, 0.85 * (limit_mm / max(cmd_dev, 1e-6))))
        plan_sugs: list[SingleRunParameterSuggestion] = []
        if dom_prim == "micro-segment-cluster" or (geom.has_micro_segments and not geom.has_corners):
            s_ch = _make_suggestion(
                "small_seg_chord_tol_mm",
                q.small_seg_chord_tol_mm * scale_tol,
                formula=f"弦高容差按超限比缩放：tol_new ~= 0.85 * ({limit_mm:.3f} / {cmd_dev:.3f}) * tol_cur",
                effect="收紧密集小线段样条压缩几何偏差，使指令轮廓回到容差门限内",
                confidence="Medium",
                note="指令几何误差无需实机试切即可在离线导出轨迹上先行验证",
            )
            if s_ch is not None:
                plan_sugs.append(s_ch)
        else:
            if geom.has_corners and prof.capabilities.has_corner_blending:
                s_cor = _make_suggestion(
                    "corner_tolerance_mm",
                    q.corner_tolerance_mm * scale_tol,
                    formula=f"拐角公差按超限比缩放：eps_new ~= 0.85 * ({limit_mm:.3f} / {cmd_dev:.3f}) * eps_cur",
                    effect="减小拐角内切过渡削角量，直接压低指令最大轮廓偏差",
                    confidence="Medium",
                    note="收紧拐角公差会同步降低过弯速度（周期略增，周期变化置信度高）",
                )
                if s_cor is not None:
                    plan_sugs.append(s_cor)
            if prof.capabilities.has_fir_filter and q.fir_time_s > 0.006:
                s_fir_shrink = _make_suggestion(
                    "fir_time_s",
                    max(0.002, q.fir_time_s * 0.65),
                    formula="圆弧/拐角滤波内缩近似：dR_fir ~= (v^2 / R) * T_fir^2 / 24",
                    effect="缩短插补后 FIR 滤波时间常数，显著降低圆弧内缩与拐角拖尾削角",
                    confidence="High",
                    note="FIR 内缩量与窗口平方成正比（高置信度），但缩短窗口会提高离散冲击 Jerk",
                )
                if s_fir_shrink is not None:
                    plan_sugs.append(s_fir_shrink)
        findings.append(
            SingleRunDiagnosticFinding(
                findingId="diag.command-over-tolerance",
                severity="Critical",
                symptom=f"指令规划轮廓偏差 {cmd_dev * 1000:.1f} um 已超出案例门限 {limit_mm * 1000:.1f} um（主导基元：{dom_prim}）",
                dominantPrimitive=dom_prim,
                errorSource="PlanningOrFilter",
                observedMetricId="sampledPathDeviationMaxMm",
                observedValue=round(cmd_dev, 6),
                unit="mm",
                suggestions=tuple(plan_sugs),
            )
        )

    # 3. Quadrant Crossing Glitch Excess
    quad_ex = _metric_val(quality_report.servo_metrics, "quadrantGlitchExcessMm")
    if quad_ex is not None and quad_ex > 0.0025 and (geom.has_arcs or geom.has_xy_reversals):
        q_sugs: list[SingleRunParameterSuggestion] = []
        if prof.capabilities.has_friction_compensation:
            step_mm = 0.70 * quad_ex
            for slot_f in ("friction_comp_amp_x_mm", "friction_comp_amp_y_mm"):
                idx_f = 0 if slot_f.endswith("x_mm") else 1
                s_fr = _make_suggestion(
                    slot_f,  # type: ignore[arg-type]
                    q.friction_comp_amp_mm[idx_f] + step_mm,
                    formula=f"过象限残差增量补偿：A_fric_new = A_fric_cur + 0.7 * excess ({quad_ex * 1000:.1f} um)",
                    effect="抵消轴向速度过零反向时的静摩擦突跳突起",
                    confidence="TrendOnly",
                    note="摩擦受导轨润滑与温升影响，幅值仅看趋势，必须整圆单刀复测防止过补偿凹陷",
                )
                if s_fr is not None and all(x.parameter_id != s_fr.parameter_id for x in q_sugs):
                    q_sugs.append(s_fr)
                    break
        findings.append(
            SingleRunDiagnosticFinding(
                findingId="diag.quadrant-glitch",
                severity="Warning" if quad_ex <= 0.006 else "Critical",
                symptom=f"轴过象限反向存在明显摩擦突跳超量（quadrantGlitchExcess = {quad_ex * 1000:.1f} um）",
                dominantPrimitive="arc" if geom.has_arcs else dom_prim,
                errorSource="QuadrantFriction",
                observedMetricId="quadrantGlitchExcessMm",
                observedValue=round(quad_ex, 6),
                unit="mm",
                suggestions=tuple(q_sugs),
            )
        )

    # 4. Circular Arc Signed Radial Offset (Inward Shrink vs Outward Wide-Swing)
    rad_off = _metric_val(quality_report.servo_metrics, "signedRadialOffsetMeanMm")
    if rad_off is not None and abs(rad_off) > 0.0025 and geom.has_arcs:
        rad_sugs: list[SingleRunParameterSuggestion] = []
        if rad_off < 0.0:
            inward_mm = -rad_off
            if cmd_dev >= 0.60 * inward_mm and prof.capabilities.has_fir_filter and q.fir_time_s > 0.004:
                s_fir_arc = _make_suggestion(
                    "fir_time_s",
                    max(0.002, q.fir_time_s * 0.65),
                    formula="整圆内缩分解：指令滤波内缩占比 >= 60%，dR_cmd ~= (v^2 / R) * T_fir^2 / 24",
                    effect="降低插补 FIR 窗口引起的稳态圆弧半径内缩",
                    confidence="High",
                    note="指令侧圆弧内缩与实际伺服解耦，调整后可在指令层直接确认半径恢复",
                )
                if s_fir_arc is not None:
                    rad_sugs.append(s_fir_arc)
            elif prof.capabilities.has_acceleration_feedforward:
                s_aff = _make_suggestion(
                    "acc_feedforward_x_ratio",
                    min(0.95, q.acc_feedforward_ratio[0] + 0.15),
                    formula="伺服法向稳态偏移：dR_servo ~= -c_a * (v^2 / R)，提高加速度前馈减小二阶滞后内缩",
                    effect=f"补偿圆弧平均向内缩径（当前 signedRadialOffset = {rad_off * 1000:+.1f} um）",
                    confidence="TrendOnly",
                    note="真实驱动含速度环积分与电流环延迟，前馈仅作方向建议，需上机试切一刀校核圆度",
                )
                if s_aff is not None:
                    rad_sugs.append(s_aff)
        else:
            if prof.capabilities.has_acceleration_feedforward and q.acc_feedforward_ratio[0] > 0.15:
                s_aff_down = _make_suggestion(
                    "acc_feedforward_x_ratio",
                    max(0.0, q.acc_feedforward_ratio[0] - 0.12),
                    formula="整圆向外扩径（signedRadialOffset > 0）提示加速度/扭矩前馈过补偿或惯量外甩",
                    effect=f"抑制圆弧向外扩径/拐角过冲（当前 signedRadialOffset = {rad_off * 1000:+.1f} um）",
                    confidence="TrendOnly",
                    note="幅值取决于各轴真实速度环带宽与负载惯量比，仅作方向参考，需上机单刀验证",
                )
                if s_aff_down is not None:
                    rad_sugs.append(s_aff_down)
            s_an = _make_suggestion(
                "centripetal_acc_limit_mm_s2",
                q.centripetal_acc_limit_mm_s2 * 0.80,
                formula="向心加速度 v^2 / R 下调 20%，直接按比例压低惯量外甩力",
                effect="通过NC通道限幅降低弯道法向过冲（无需改动伺服驱动参数）",
                confidence="Medium",
                note="NC 侧安全调优手段；弯道降速对周期的影响可精确预测",
            )
            if s_an is not None:
                rad_sugs.append(s_an)

        findings.append(
            SingleRunDiagnosticFinding(
                findingId="diag.arc-radial-shift",
                severity="Warning",
                symptom=(
                    f"圆弧存在系统性{'向内缩径' if rad_off < 0 else '向外扩径/外甩'} "
                    f"（signedRadialOffsetMean = {rad_off * 1000:+.1f} um）"
                ),
                dominantPrimitive="arc",
                errorSource="PlanningOrFilter" if (rad_off < 0 and cmd_dev >= 0.60 * (-rad_off)) else "ServoTracking",
                observedMetricId="signedRadialOffsetMeanMm",
                observedValue=round(rad_off, 6),
                unit="mm",
                suggestions=tuple(rad_sugs),
            )
        )

    # 5. XY Servo Gain / Velocity Feedforward Mismatch
    norm_servo = _metric_val(quality_report.servo_metrics, "normalServoErrorMaxMm")
    if norm_servo is not None and norm_servo > 0.003:
        kp_diff = abs(q.servo_kp_1_s[0] - q.servo_kp_1_s[1])
        vff_diff = abs(q.vel_feedforward_ratio[0] - q.vel_feedforward_ratio[1])
        mis_sugs: list[SingleRunParameterSuggestion] = []
        if kp_diff > 3.0:
            target_kp = 0.5 * (q.servo_kp_1_s[0] + q.servo_kp_1_s[1])
            slot_mis: CanonicalSlotId = (
                "servo_kp_x_1_s" if abs(q.servo_kp_1_s[0] - target_kp) >= abs(q.servo_kp_1_s[1] - target_kp) else "servo_kp_y_1_s"
            )
            s_kp = _make_suggestion(
                slot_mis,
                target_kp,
                formula="双轴联动斜线/圆弧法向偏差：e_mis ~= v * u_x * u_y * |c_v,x - c_v,y|",
                effect=f"消除 X/Y 位置环增益失配（当前差值 {kp_diff:.1f} 1/s）引起的椭圆畸变",
                confidence="Medium",
                note="联动插补轴必须保持等效位置环增益一致；改动驱动增益后请复测整圆球杆仪/光栅轨迹",
            )
            if s_kp is not None:
                mis_sugs.append(s_kp)
        elif vff_diff > 0.01:
            target_vff = max(q.vel_feedforward_ratio[0], q.vel_feedforward_ratio[1])
            slot_vff: CanonicalSlotId = (
                "vel_feedforward_x_ratio"
                if q.vel_feedforward_ratio[0] < q.vel_feedforward_ratio[1]
                else "vel_feedforward_y_ratio"
            )
            s_vff = _make_suggestion(
                slot_vff,
                target_vff,
                formula="双轴速度前馈对齐：V_ff,x = V_ff,y，消除斜线恒速段法向比例偏差",
                effect="对齐双轴速度前馈系数，压低联动法向伺服误差",
                confidence="Medium",
                note="双轴前馈对称性是联动轮廓精度的基础前提，修改后建议试切斜线/整圆确认",
            )
            if s_vff is not None:
                mis_sugs.append(s_vff)
        if mis_sugs:
            findings.append(
                SingleRunDiagnosticFinding(
                    findingId="diag.xy-servo-mismatch",
                    severity="Warning",
                    symptom=f"检测到 X/Y 双轴伺服参数不对称，法向伺服误差峰值达 {norm_servo * 1000:.1f} um",
                    dominantPrimitive=dom_prim,
                    errorSource="ServoTracking",
                    observedMetricId="normalServoErrorMaxMm",
                    observedValue=round(norm_servo, 6),
                    unit="mm",
                    suggestions=tuple(mis_sugs),
                )
            )

    # 6. Cycle-Time Efficiency Headroom when accuracy is comfortably within spec
    worst_contour = act_dev if act_dev is not None else cmd_dev
    if not findings and worst_contour <= 0.55 * limit_mm:
        eff_sugs: list[SingleRunParameterSuggestion] = []
        if geom.has_corners and prof.capabilities.has_corner_blending:
            s_relax = _make_suggestion(
                "corner_tolerance_mm",
                min(0.80 * limit_mm, q.corner_tolerance_mm * 1.30),
                formula="过弯速度包络：v_cor propto sqrt(a_n * eps_cor)，当前精度裕度充足（< 55% 门限）",
                effect="在精度门限安全裕度内适度放宽拐角公差，提高过弯最低速度并缩短加工周期",
                confidence="High",
                note="周期缩短幅度由运动学前瞻白盒决定（高置信度）；实测轮廓增量需上机验证一刀",
            )
            if s_relax is not None:
                eff_sugs.append(s_relax)
        max_ax_acc = min(float(lim.maximum_acceleration_mm_s2) for lim in case.axis_limits)
        if q.path_tangential_acc_mm_s2 < 0.90 * max_ax_acc:
            s_acc = _make_suggestion(
                "path_tangential_acc_mm_s2",
                min(max_ax_acc, q.path_tangential_acc_mm_s2 * 1.20),
                formula="加减速斜坡耗时：t_ramp = dV / a_t，上调 20% 切向加速度压降短线段启停耗时",
                effect="在不超机床单轴加速度上限的前提下缩短启停过渡时间",
                confidence="High",
                note="周期预测置信度高；上调加速度后请留意机台冲击噪声与跟随误差峰值",
            )
            if s_acc is not None:
                eff_sugs.append(s_acc)
        findings.append(
            SingleRunDiagnosticFinding(
                findingId="diag.efficiency-headroom",
                severity="Info",
                symptom=(
                    f"当前轮廓误差 {worst_contour * 1000:.1f} um 远低于门限 {limit_mm * 1000:.1f} um "
                    f"（周期 {dur_s:.3f} s），具备提速裕度"
                ),
                dominantPrimitive=dom_prim,
                errorSource="HeadroomAvailable",
                observedMetricId="durationSeconds",
                observedValue=round(dur_s, 6),
                unit="s",
                suggestions=tuple(eff_sugs),
            )
        )

    severity_rank = {"Critical": 0, "Warning": 1, "Info": 2}
    ordered_findings = sorted(findings, key=lambda f: severity_rank[f.severity])

    top_actions: list[SingleRunParameterSuggestion] = []
    seen_pids: set[str] = set()
    for f in ordered_findings:
        for sug in f.suggestions:
            if sug.parameter_id not in seen_pids and len(top_actions) < max(1, max_top_actions):
                seen_pids.add(sug.parameter_id)
                top_actions.append(sug)

    if not ordered_findings:
        headline = (
            f"案例 {case.case_id}（{prof.vendor_name} / {prof.profile_id}）单刀运行正常："
            f"周期 {dur_s:.3f} s，最大轮廓偏差 {worst_contour * 1000:.1f} um（门限 {limit_mm * 1000:.1f} um），无需调参。"
        )
    else:
        headline = (
            f"案例 {case.case_id}（{prof.vendor_name} / {prof.profile_id}）识别出 {len(ordered_findings)} 项机理问题，"
            f"优先建议单次调整 {len(top_actions)} 个参数后试切验证。"
        )

    confidence_stmt = (
        "加工周期与FIR陷波零点频率：基于确定性运动学/频谱白盒公式（高置信度）；"
        "实测轮廓与伺服误差数值：受未建模速度环积分、温升摩擦及负载惯量影响，仅作调整方向参考，必须上机验证一刀。"
    )

    report = CncSingleRunDiagnosticReport(
        caseId=case.case_id,
        controllerProfileId=prof.profile_id,
        sourceKind=quality_report.analysis.source_kind,  # type: ignore[arg-type]
        summaryHeadline=headline,
        cycleTimeConfidence="High",
        contourErrorConfidence="TrendOnly",
        confidenceStatement=confidence_stmt,
        findings=tuple(ordered_findings),
        topActions=tuple(top_actions),
        reportContentHash="",
    )
    content = report.model_dump(mode="json", by_alias=True, exclude_none=True)
    content.pop("reportContentHash", None)
    return report.model_copy(update={"report_content_hash": _canonical_hash(content)})


def _pad(text: str, width: int, *, right: bool = False) -> str:
    shown = sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)
    fill = " " * max(width - shown, 1 if right else 0)
    return fill + text if right else text + fill


def render_diagnostic_table(report: CncSingleRunDiagnosticReport) -> str:
    """Render a concise shop-floor CLI table for single-run diagnostics."""
    lines = [
        f"【单刀机理诊断顾问】{report.summary_headline}",
        f"置信度声明：{report.confidence_statement}",
        "",
    ]
    for idx, f in enumerate(report.findings, 1):
        lines.append(f"  {idx}. [{f.severity} / {f.error_source}] {f.symptom}")
    if report.top_actions:
        lines.append("")
        lines.append(f"下一刀优先试切动作（最多改 {len(report.top_actions)} 项，便于归因）：")
        lines.append(
            "  "
            + _pad("参数ID", 34)
            + _pad("当前值", 12, right=True)
            + _pad("建议值", 12, right=True)
            + _pad("单位", 12, right=True)
            + _pad("调节位置", 12, right=True)
            + _pad("置信度", 10, right=True)
        )
        for act in report.top_actions:
            lines.append(
                "  "
                + _pad(act.parameter_id, 34)
                + _pad(f"{act.current_value:g}", 12, right=True)
                + _pad(f"{act.suggested_value:g}", 12, right=True)
                + _pad(act.unit, 12, right=True)
                + _pad(act.tunability, 12, right=True)
                + _pad(act.confidence_level, 10, right=True)
            )
            lines.append(f"     机理依据：{act.mechanism_formula}")
            lines.append(f"     预期效果：{act.expected_effect}")
            lines.append(f"     验证要求：{act.verification_note}")
    return "\n".join(lines) + "\n"
