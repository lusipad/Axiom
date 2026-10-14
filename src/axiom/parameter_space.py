"""30+ Dimensional CNC Parameter Space Taxonomy, Causal Masks, and Active DoE Generator.

Organizes CNC trajectory planning and servo loop parameters into three physical layers:
- G1_GeometryLookahead: toolpath smoothing, chord tolerance, corner rounding, lookahead window
- G2_KinematicsFilter: velocity/acceleration/jerk limits, centripetal clamp, FIR/Biquad interpolation filters
- G3_ServoControl: position loop Kp, velocity/acceleration feedforward, friction/quadrant glitch compensation, notch filter
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Any, Literal, Mapping

import numpy as np
from pydantic import BeforeValidator, Field, StrictInt, model_validator

from .models import AxiomModel, _require_json_number

Number = Annotated[float, BeforeValidator(_require_json_number), Field(allow_inf_nan=False)]
ParameterGroup = Literal["G1_GeometryLookahead", "G2_KinematicsFilter", "G3_ServoControl"]
SourceKind = Literal["algorithm-export", "controller-trace"]
PrimitiveScope = Literal["global", "line", "arc", "corner", "micro-segment-cluster"]

PLANNING_METRIC_IDS = frozenset(
    {
        "durationSeconds",
        "sampledPathDeviationMaxMm",
        "sampledPathDeviationRmsMm",
        "sampledPathDeviationP95Mm",
        "sampledPathDeviationP99Mm",
        "endpointErrorMaxMm",
        "discreteVelocityMax",
        "discreteAccelerationMax",
        "discreteJerkMax",
        "discreteJerkRms",
        "cornerSpeedMinMmS",
        "feedUtilization",
    }
)

SERVO_METRIC_IDS = frozenset(
    {
        "followingErrorMaxMm",
        "followingErrorRmsMm",
        "actualPathDeviationMaxMm",
        "actualPathDeviationRmsMm",
        "actualPathDeviationP99Mm",
        "quadrantGlitchMaxMm",
    }
)


def _canonical_hash(payload: AxiomModel | Mapping[str, Any]) -> str:
    data = (
        payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(payload, AxiomModel)
        else dict(payload)
    )
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ParameterDefinition(AxiomModel):
    parameter_id: str = Field(alias="parameterId", min_length=1, max_length=200)
    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    group: ParameterGroup
    unit: str = Field(min_length=1, max_length=60)
    value_type: Literal["continuous", "integer"] = Field(default="continuous", alias="valueType")
    bounds: tuple[Number, Number]
    default_value: Number = Field(alias="defaultValue")
    applies_to_sources: tuple[SourceKind, ...] = Field(alias="appliesToSources", min_length=1)
    axis_scope: Literal["path", "X", "Y", "Z"] = Field(default="path", alias="axisScope")
    applicable_primitives: tuple[PrimitiveScope, ...] = Field(
        default=("global", "line", "arc", "corner", "micro-segment-cluster"),
        alias="applicablePrimitives",
    )
    description: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_bounds(self) -> ParameterDefinition:
        lo, hi = float(self.bounds[0]), float(self.bounds[1])
        if lo >= hi:
            raise ValueError(f"parameter {self.parameter_id}: bounds[0] must be < bounds[1]")
        if not (lo <= float(self.default_value) <= hi):
            raise ValueError(f"parameter {self.parameter_id}: defaultValue must lie within bounds")
        return self


class DerivedFeatureDefinition(AxiomModel):
    feature_id: str = Field(alias="featureId", min_length=1, max_length=200)
    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    group: ParameterGroup
    source_parameters: tuple[str, str] = Field(alias="sourceParameters")
    formula: Literal["abs_diff", "mean", "product"] = "abs_diff"
    description: str = Field(default="", max_length=500)


class CncParameterRegistry(AxiomModel):
    schema_id: Literal["axiom.cnc-parameter-registry@1"] = Field(
        default="axiom.cnc-parameter-registry@1", alias="schemaId"
    )
    registry_id: str = Field(alias="registryId", min_length=1, max_length=200)
    parameters: tuple[ParameterDefinition, ...] = Field(min_length=1, max_length=200)
    derived_features: tuple[DerivedFeatureDefinition, ...] = Field(default=(), alias="derivedFeatures")
    registry_content_hash: str = Field(alias="registryContentHash")

    @model_validator(mode="after")
    def unique_ids(self) -> CncParameterRegistry:
        seen: set[str] = set()
        for p in self.parameters:
            if p.parameter_id in seen:
                raise ValueError(f"duplicate parameterId: {p.parameter_id}")
            seen.add(p.parameter_id)
        for d in self.derived_features:
            if d.feature_id in seen:
                raise ValueError(f"duplicate featureId: {d.feature_id}")
            for src in d.source_parameters:
                if src not in seen:
                    raise ValueError(f"derived feature {d.feature_id} references unknown parameter {src}")
            seen.add(d.feature_id)
        return self


class ParameterDoeSample(AxiomModel):
    sample_id: str = Field(alias="sampleId")
    target_source: SourceKind = Field(alias="targetSource")
    stage: Literal["offline-screening", "controller-calibration"]
    parameters: dict[str, float]


class ParameterDoePlan(AxiomModel):
    schema_id: Literal["axiom.cnc-parameter-doe-plan@1"] = Field(
        default="axiom.cnc-parameter-doe-plan@1", alias="schemaId"
    )
    registry_id: str = Field(alias="registryId")
    registry_content_hash: str = Field(alias="registryContentHash")
    seed: int
    offline_samples: tuple[ParameterDoeSample, ...] = Field(alias="offlineSamples")
    controller_samples: tuple[ParameterDoeSample, ...] = Field(alias="controllerSamples")
    plan_content_hash: str = Field(alias="planContentHash")


def default_cnc_parameter_registry() -> CncParameterRegistry:
    """Standard 32-parameter CNC trajectory planning & servo loop parameter registry."""
    both: tuple[SourceKind, ...] = ("algorithm-export", "controller-trace")
    ctrl_only: tuple[SourceKind, ...] = ("controller-trace",)
    params = (
        # G1: Path Geometry Smoothing & Lookahead (8 parameters)
        ParameterDefinition(
            parameterId="g1.corner_tolerance_mm",
            displayName="拐角平滑最大弦高允差",
            group="G1_GeometryLookahead",
            unit="mm",
            bounds=(0.001, 0.100),
            defaultValue=0.020,
            appliesToSources=both,
            applicablePrimitives=("global", "corner", "micro-segment-cluster"),
            description="决定拐角圆滑过渡内缩弧度与允许过弯速度上限",
        ),
        ParameterDefinition(
            parameterId="g1.small_seg_chord_tol_mm",
            displayName="小线段样条压缩拟合允差",
            group="G1_GeometryLookahead",
            unit="mm",
            bounds=(0.0005, 0.050),
            defaultValue=0.005,
            appliesToSources=both,
            applicablePrimitives=("global", "micro-segment-cluster"),
            description="控制CAM密集小线段拟合为高阶样条时的几何容差",
        ),
        ParameterDefinition(
            parameterId="g1.lookahead_block_count",
            displayName="前瞻缓冲区段数窗口",
            group="G1_GeometryLookahead",
            unit="blocks",
            valueType="integer",
            bounds=(20, 500),
            defaultValue=160,
            appliesToSources=both,
            applicablePrimitives=("global", "corner", "micro-segment-cluster"),
            description="速度规划器前瞻扫描的最大程序段数",
        ),
        ParameterDefinition(
            parameterId="g1.corner_angle_threshold_deg",
            displayName="拐角降速/过渡触发角阈值",
            group="G1_GeometryLookahead",
            unit="deg",
            bounds=(3.0, 45.0),
            defaultValue=10.0,
            appliesToSources=both,
            applicablePrimitives=("global", "corner"),
            description="相邻刀路段切向折角超过该值时插入局部过渡曲线",
        ),
        ParameterDefinition(
            parameterId="g1.collinear_merge_angle_deg",
            displayName="近似共线微线段合并角阈值",
            group="G1_GeometryLookahead",
            unit="deg",
            bounds=(0.05, 2.0),
            defaultValue=0.25,
            appliesToSources=both,
            applicablePrimitives=("global", "line", "micro-segment-cluster"),
            description="消除微线段方向量化抖动的共线合并角",
        ),
        ParameterDefinition(
            parameterId="g1.curvature_speed_clamp_factor",
            displayName="曲率限速安全裕度系数",
            group="G1_GeometryLookahead",
            unit="ratio",
            bounds=(0.50, 1.20),
            defaultValue=0.90,
            appliesToSources=both,
            applicablePrimitives=("global", "arc", "corner", "micro-segment-cluster"),
            description="基于局部曲率半径限制切向速度的比例系数",
        ),
        ParameterDefinition(
            parameterId="g1.min_segment_length_mm",
            displayName="极短微线段滤除最小长度",
            group="G1_GeometryLookahead",
            unit="mm",
            bounds=(0.001, 0.050),
            defaultValue=0.005,
            appliesToSources=both,
            applicablePrimitives=("global", "micro-segment-cluster"),
            description="低于此长度的冗余微线段在预处理阶段合并滤除",
        ),
        ParameterDefinition(
            parameterId="g1.spline_degree",
            displayName="小线段平滑样条阶数",
            group="G1_GeometryLookahead",
            unit="deg_order",
            valueType="integer",
            bounds=(3, 5),
            defaultValue=3,
            appliesToSources=both,
            applicablePrimitives=("global", "corner", "micro-segment-cluster"),
            description="3阶或5阶参数样条过渡",
        ),
        # G2: Kinematics Time Law & Interpolation Filtering (13 parameters)
        ParameterDefinition(
            parameterId="g2.path_max_feed_override",
            displayName="路径切向进给倍率上限",
            group="G2_KinematicsFilter",
            unit="ratio",
            bounds=(0.50, 1.20),
            defaultValue=1.00,
            appliesToSources=both,
            description="全局路径切向目标进给速度倍率",
        ),
        ParameterDefinition(
            parameterId="g2.path_tangential_acc_mm_s2",
            displayName="路径切向最大合成加速度",
            group="G2_KinematicsFilter",
            unit="mm/s^2",
            bounds=(1000.0, 15000.0),
            defaultValue=5000.0,
            appliesToSources=both,
            description="S曲线加减速规划的切向最大加速度",
        ),
        ParameterDefinition(
            parameterId="g2.path_tangential_jerk_mm_s3",
            displayName="路径切向最大合成 Jerk",
            group="G2_KinematicsFilter",
            unit="mm/s^3",
            bounds=(20000.0, 1000000.0),
            defaultValue=200000.0,
            appliesToSources=both,
            description="S曲线加减速规划的切向最大加加速度",
        ),
        ParameterDefinition(
            parameterId="g2.centripetal_acc_limit_mm_s2",
            displayName="圆弧/拐角法向向心加速度限幅",
            group="G2_KinematicsFilter",
            unit="mm/s^2",
            bounds=(500.0, 8000.0),
            defaultValue=3000.0,
            appliesToSources=both,
            applicablePrimitives=("global", "arc", "corner"),
            description="限制圆弧和拐角段法向离心加速度 v^2/R",
        ),
        ParameterDefinition(
            parameterId="g2.axis_vel_limit_x",
            displayName="X轴规划速度上限",
            group="G2_KinematicsFilter",
            unit="mm/s",
            bounds=(100.0, 1000.0),
            defaultValue=500.0,
            appliesToSources=both,
            axisScope="X",
        ),
        ParameterDefinition(
            parameterId="g2.axis_vel_limit_y",
            displayName="Y轴规划速度上限",
            group="G2_KinematicsFilter",
            unit="mm/s",
            bounds=(100.0, 1000.0),
            defaultValue=500.0,
            appliesToSources=both,
            axisScope="Y",
        ),
        ParameterDefinition(
            parameterId="g2.axis_vel_limit_z",
            displayName="Z轴规划速度上限",
            group="G2_KinematicsFilter",
            unit="mm/s",
            bounds=(100.0, 1000.0),
            defaultValue=400.0,
            appliesToSources=both,
            axisScope="Z",
        ),
        ParameterDefinition(
            parameterId="g2.axis_acc_limit_x",
            displayName="X轴规划加速度上限",
            group="G2_KinematicsFilter",
            unit="mm/s^2",
            bounds=(1000.0, 12000.0),
            defaultValue=5000.0,
            appliesToSources=both,
            axisScope="X",
        ),
        ParameterDefinition(
            parameterId="g2.axis_acc_limit_y",
            displayName="Y轴规划加速度上限",
            group="G2_KinematicsFilter",
            unit="mm/s^2",
            bounds=(1000.0, 12000.0),
            defaultValue=5000.0,
            appliesToSources=both,
            axisScope="Y",
        ),
        ParameterDefinition(
            parameterId="g2.axis_acc_limit_z",
            displayName="Z轴规划加速度上限",
            group="G2_KinematicsFilter",
            unit="mm/s^2",
            bounds=(1000.0, 12000.0),
            defaultValue=4000.0,
            appliesToSources=both,
            axisScope="Z",
        ),
        ParameterDefinition(
            parameterId="g2.fir_moving_avg_time_ms",
            displayName="插补后 FIR 滑动平均滤波时间常数",
            group="G2_KinematicsFilter",
            unit="ms",
            bounds=(0.0, 64.0),
            defaultValue=12.0,
            appliesToSources=both,
            description="平滑离散冲击 Jerk，但过大会引起圆弧内缩与拐角滞后",
        ),
        ParameterDefinition(
            parameterId="g2.biquad_lowpass_freq_hz",
            displayName="插补指令二阶低通滤波截止频率",
            group="G2_KinematicsFilter",
            unit="Hz",
            bounds=(10.0, 200.0),
            defaultValue=80.0,
            appliesToSources=both,
            description="抑制高频插补量化噪声的截止频率",
        ),
        ParameterDefinition(
            parameterId="g2.bell_acc_shape_factor",
            displayName="钟形加减速平滑形态因子",
            group="G2_KinematicsFilter",
            unit="ratio",
            bounds=(0.0, 1.0),
            defaultValue=0.50,
            appliesToSources=both,
            description="0为梯形加速度，1为纯正弦钟形加速度过渡",
        ),
        # G3: Servo Loop & Dynamic Compensation (11 parameters, controller-trace only)
        ParameterDefinition(
            parameterId="g3.servo_kp_x",
            displayName="X轴位置环比例增益 Kv",
            group="G3_ServoControl",
            unit="1/s",
            bounds=(20.0, 150.0),
            defaultValue=60.0,
            appliesToSources=ctrl_only,
            axisScope="X",
            description="决定X轴位置环带宽与跟随滞后，XY增益失配会引起轮廓误差",
        ),
        ParameterDefinition(
            parameterId="g3.servo_kp_y",
            displayName="Y轴位置环比例增益 Kv",
            group="G3_ServoControl",
            unit="1/s",
            bounds=(20.0, 150.0),
            defaultValue=60.0,
            appliesToSources=ctrl_only,
            axisScope="Y",
            description="决定Y轴位置环带宽与跟随滞后",
        ),
        ParameterDefinition(
            parameterId="g3.servo_kp_z",
            displayName="Z轴位置环比例增益 Kv",
            group="G3_ServoControl",
            unit="1/s",
            bounds=(20.0, 150.0),
            defaultValue=55.0,
            appliesToSources=ctrl_only,
            axisScope="Z",
        ),
        ParameterDefinition(
            parameterId="g3.vel_feedforward_x",
            displayName="X轴速度前馈系数",
            group="G3_ServoControl",
            unit="ratio",
            bounds=(0.80, 1.02),
            defaultValue=0.98,
            appliesToSources=ctrl_only,
            axisScope="X",
            description="补偿速度引起的稳态位置环跟随误差",
        ),
        ParameterDefinition(
            parameterId="g3.vel_feedforward_y",
            displayName="Y轴速度前馈系数",
            group="G3_ServoControl",
            unit="ratio",
            bounds=(0.80, 1.02),
            defaultValue=0.98,
            appliesToSources=ctrl_only,
            axisScope="Y",
        ),
        ParameterDefinition(
            parameterId="g3.vel_feedforward_z",
            displayName="Z轴速度前馈系数",
            group="G3_ServoControl",
            unit="ratio",
            bounds=(0.80, 1.02),
            defaultValue=0.95,
            appliesToSources=ctrl_only,
            axisScope="Z",
        ),
        ParameterDefinition(
            parameterId="g3.acc_feedforward_x",
            displayName="X轴加速度/扭矩前馈系数",
            group="G3_ServoControl",
            unit="ratio",
            bounds=(0.0, 1.00),
            defaultValue=0.70,
            appliesToSources=ctrl_only,
            axisScope="X",
            description="抑制高加速段与拐角处的动态跟随误差峰值",
        ),
        ParameterDefinition(
            parameterId="g3.acc_feedforward_y",
            displayName="Y轴加速度/扭矩前馈系数",
            group="G3_ServoControl",
            unit="ratio",
            bounds=(0.0, 1.00),
            defaultValue=0.70,
            appliesToSources=ctrl_only,
            axisScope="Y",
        ),
        ParameterDefinition(
            parameterId="g3.friction_comp_amp_x",
            displayName="X轴过象限摩擦补偿幅值",
            group="G3_ServoControl",
            unit="mm",
            bounds=(0.0, 0.020),
            defaultValue=0.005,
            appliesToSources=ctrl_only,
            axisScope="X",
            applicablePrimitives=("global", "arc"),
            description="抑制圆弧速度过零反向时的过象限突起",
        ),
        ParameterDefinition(
            parameterId="g3.friction_comp_amp_y",
            displayName="Y轴过象限摩擦补偿幅值",
            group="G3_ServoControl",
            unit="mm",
            bounds=(0.0, 0.020),
            defaultValue=0.005,
            appliesToSources=ctrl_only,
            axisScope="Y",
            applicablePrimitives=("global", "arc"),
        ),
        ParameterDefinition(
            parameterId="g3.notch_filter_freq_hz",
            displayName="伺服机械谐振陷波频率",
            group="G3_ServoControl",
            unit="Hz",
            bounds=(40.0, 400.0),
            defaultValue=180.0,
            appliesToSources=ctrl_only,
            description="抑制机械传动链特定频率谐振",
        ),
    )
    derived = (
        DerivedFeatureDefinition(
            featureId="derived.kp_xy_mismatch",
            displayName="XY双轴位置环增益失配度",
            group="G3_ServoControl",
            sourceParameters=("g3.servo_kp_x", "g3.servo_kp_y"),
            formula="abs_diff",
            description="|Kp_x - Kp_y|，直接引起斜线与圆弧的动态轮廓变形",
        ),
        DerivedFeatureDefinition(
            featureId="derived.vff_xy_mismatch",
            displayName="XY双轴速度前馈失配度",
            group="G3_ServoControl",
            sourceParameters=("g3.vel_feedforward_x", "g3.vel_feedforward_y"),
            formula="abs_diff",
            description="|Vff_x - Vff_y|，引起双轴联动稳态跟随比例偏差",
        ),
    )
    reg = CncParameterRegistry(
        registryId="cnc.planner-and-servo.32d@1",
        parameters=params,
        derivedFeatures=derived,
        registryContentHash="",
    )
    content = reg.model_dump(mode="json", by_alias=True, exclude_none=True)
    content.pop("registryContentHash")
    return reg.model_copy(update={"registry_content_hash": _canonical_hash(content)})


def default_parameter_values(registry: CncParameterRegistry | None = None) -> dict[str, float]:
    reg = registry or default_cnc_parameter_registry()
    return {p.parameter_id: float(p.default_value) for p in reg.parameters}


def causal_mask_for_metric(
    registry: CncParameterRegistry,
    metric_id: str,
    *,
    has_controller_traces: bool = False,
) -> dict[str, bool]:
    """Return prior causal mask (True = allowed to influence metric_id, False = hard zeroed).

    Key physical invariant:
    - Planning metrics (duration, command path deviation, discrete command V/A/J, corner speed)
      depend strictly on G1 (Geometry/Lookahead) and G2 (Kinematics/Filter) and have ZERO causal
      dependence on G3 (Servo loop gains/feedforward).
    - Servo & actual feedback metrics depend on G3 and active G1/G2 excitation parameters.
    """
    is_planning_metric = metric_id in PLANNING_METRIC_IDS or not (
        metric_id in SERVO_METRIC_IDS or metric_id.startswith("actual") or metric_id.startswith("following")
    )
    mask: dict[str, bool] = {}
    for p in registry.parameters:
        if is_planning_metric:
            mask[p.parameter_id] = p.group in {"G1_GeometryLookahead", "G2_KinematicsFilter"}
        else:
            mask[p.parameter_id] = has_controller_traces or ("controller-trace" in p.applies_to_sources)
    for d in registry.derived_features:
        mask[d.feature_id] = (not is_planning_metric) and has_controller_traces
    return mask


def compute_derived_feature_value(
    derived: DerivedFeatureDefinition,
    params: Mapping[str, float],
    param_map: Mapping[str, ParameterDefinition],
) -> float:
    a_id, b_id = derived.source_parameters
    a_def, b_def = param_map[a_id], param_map[b_id]
    a_val = float(params.get(a_id, a_def.default_value))
    b_val = float(params.get(b_id, b_def.default_value))
    span = max(float(a_def.bounds[1] - a_def.bounds[0]), float(b_def.bounds[1] - b_def.bounds[0]), 1e-9)
    if derived.formula == "abs_diff":
        return (abs(a_val - b_val) / span) * 2.0 - 1.0
    if derived.formula == "mean":
        return ((a_val - float(a_def.bounds[0])) / span + (b_val - float(b_def.bounds[0])) / span) - 1.0
    return ((a_val - float(a_def.bounds[0])) / span) * ((b_val - float(b_def.bounds[0])) / span)


def normalize_parameter_value(defn: ParameterDefinition, value: float) -> float:
    lo, hi = float(defn.bounds[0]), float(defn.bounds[1])
    return float(2.0 * (float(value) - lo) / (hi - lo) - 1.0)


def denormalize_parameter_value(defn: ParameterDefinition, norm_value: float) -> float:
    lo, hi = float(defn.bounds[0]), float(defn.bounds[1])
    clipped = max(-1.0, min(1.0, float(norm_value)))
    raw = lo + 0.5 * (clipped + 1.0) * (hi - lo)
    if defn.value_type == "integer":
        return float(round(raw))
    return float(round(raw, 6))


def _latin_hypercube(n_samples: int, n_dims: int, rng: np.random.Generator) -> np.ndarray:
    """Deterministic Latin Hypercube Sampling in [-1, 1]^n_dims with maximin candidate selection."""
    best_lhs = None
    best_min_dist = -1.0
    trials = 5 if n_samples <= 64 else 2
    for _ in range(trials):
        grid = np.empty((n_samples, n_dims), dtype=np.float64)
        for j in range(n_dims):
            perm = rng.permutation(n_samples)
            u = (perm + rng.uniform(0.15, 0.85, size=n_samples)) / n_samples
            grid[:, j] = 2.0 * u - 1.0
        if n_samples >= 2:
            diffs = grid[:, None, :] - grid[None, :, :]
            dists = np.sqrt(np.sum(diffs * diffs, axis=2))
            np.fill_diagonal(dists, np.inf)
            min_dist = float(np.min(dists))
        else:
            min_dist = 0.0
        if min_dist > best_min_dist:
            best_min_dist = min_dist
            best_lhs = grid
    assert best_lhs is not None
    return best_lhs


def generate_parameter_doe(
    registry: CncParameterRegistry | None = None,
    *,
    offline_count: int = 36,
    controller_count: int = 12,
    seed: int = 42,
    baseline_parameters: Mapping[str, float] | None = None,
    active_parameter_ids: tuple[str, ...] | None = None,
) -> ParameterDoePlan:
    """Generate a two-stage Latin Hypercube Design of Experiments (DoE) for 30+ CNC parameters."""
    reg = registry or default_cnc_parameter_registry()
    base = default_parameter_values(reg)
    if baseline_parameters:
        for k, v in baseline_parameters.items():
            if k in base:
                base[k] = float(v)

    rng = np.random.default_rng(seed)
    offline_defs = [
        p
        for p in reg.parameters
        if p.group in {"G1_GeometryLookahead", "G2_KinematicsFilter"}
        and (active_parameter_ids is None or p.parameter_id in active_parameter_ids)
    ]
    offline_Samples_list: list[ParameterDoeSample] = []
    if offline_count > 0 and offline_defs:
        lhs_off = _latin_hypercube(offline_count, len(offline_defs), rng)
        for idx in range(offline_count):
            row_params = dict(base)
            for j, p_def in enumerate(offline_defs):
                row_params[p_def.parameter_id] = denormalize_parameter_value(p_def, float(lhs_off[idx, j]))
            offline_Samples_list.append(
                ParameterDoeSample(
                    sampleId=f"doe.offline.{idx + 1:03d}",
                    targetSource="algorithm-export",
                    stage="offline-screening",
                    parameters=row_params,
                )
            )

    ctrl_defs = [
        p
        for p in reg.parameters
        if (active_parameter_ids is None or p.parameter_id in active_parameter_ids or p.group == "G3_ServoControl")
    ]
    ctrl_samples_list: list[ParameterDoeSample] = []
    if controller_count > 0 and ctrl_defs:
        lhs_ctrl = _latin_hypercube(controller_count, len(ctrl_defs), rng)
        for idx in range(controller_count):
            row_params = dict(base)
            for j, p_def in enumerate(ctrl_defs):
                row_params[p_def.parameter_id] = denormalize_parameter_value(p_def, float(lhs_ctrl[idx, j]))
            ctrl_samples_list.append(
                ParameterDoeSample(
                    sampleId=f"doe.controller.{idx + 1:03d}",
                    targetSource="controller-trace",
                    stage="controller-calibration",
                    parameters=row_params,
                )
            )

    plan = ParameterDoePlan(
        registryId=reg.registry_id,
        registryContentHash=reg.registry_content_hash,
        seed=seed,
        offlineSamples=tuple(offline_Samples_list),
        controllerSamples=tuple(ctrl_samples_list),
        planContentHash="",
    )
    content = plan.model_dump(mode="json", by_alias=True, exclude_none=True)
    content.pop("planContentHash")
    return plan.model_copy(update={"plan_content_hash": _canonical_hash(content)})
