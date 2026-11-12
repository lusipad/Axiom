"""Grey-box backbone + optional low-dimensional residual GP CNC parameter learner.

1. Layer 1/2: the `generic-fir-biquad@1` grey-box backbone from `greybox_model` with
   constants fitted across all supplied cases (fitting coefficients, not identified
   physical quantities).
2. Layer 3: a 3D-6D ARD Matern-5/2 residual GP per metric, kept only when it lowers the
   leave-one-out error relative to the backbone alone (`residualEnabled`).
3. Uncertainty: a leave-one-out residual quantile at rank ceil((n + 1)(1 - alpha)); it is
   never shrunk afterwards and is inflated outside the observed feature envelope. Its
   empirical coverage on unseen machines is unverified until real verification runs exist.
4. Leave-One-Case-Out (LOCO) report of backbone transfer across the supplied toolpaths.

Registries must define every kernel parameter id; unknown export parameters are rejected
instead of silently defaulting.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from pydantic import Field, model_validator

from .benchmark import (
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncQualityReport,
    benchmark_case_hash,
    evaluate_cnc_export,
)
from .greybox_model import (
    GREYBOX_KERNEL_ID,
    CaseGeometryProfile,
    GreyBoxPhysicalConstants,
    calibrate_greybox_constants,
    evaluate_greybox_backbone,
    extract_case_geometry_profile,
    fit_mle_ard_matern52_gp,
    matern52_kernel,
    missing_greybox_parameter_ids,
)
from .models import AxiomModel
from .parameter_space import (
    PLANNING_METRIC_IDS,
    SERVO_METRIC_IDS,
    CncParameterRegistry,
    DerivedFeatureDefinition,
    ParameterDefinition,
    ParameterGroup,
    causal_mask_for_metric,
    compute_derived_feature_value,
    default_cnc_parameter_registry,
    default_parameter_values,
    denormalize_parameter_value,
    normalize_parameter_value,
    verify_registry_content_hash,
)

DEFAULT_TARGET_METRICS = (
    "durationSeconds",
    "sampledPathDeviationMaxMm",
    "discreteJerkRms",
    "cornerSpeedMinMmS",
    "followingErrorMaxMm",
    "actualPathDeviationMaxMm",
    "quadrantGlitchExcessMm",
)
EXTENDED_TARGET_METRICS = (
    "durationSeconds",
    "sampledPathDeviationMaxMm",
    "discreteJerkRms",
    "smoothedJerkRmsMmS3",
    "cornerSpeedMinMmS",
    "feedUtilizationRatio",
    "followingErrorMaxMm",
    "tangentialLagMaxMm",
    "normalServoErrorMaxMm",
    "actualPathDeviationMaxMm",
    "quadrantGlitchExcessMm",
    "resonanceBandRmsMm",
)
KINEMATIC_BRIDGE_FEATURES = (
    "velocityMaxMmS",
    "accelerationMaxMmS2",
    "jerkRmsMmS3",
    "cornerSpeedMinMmS",
)
CONFORMAL_ALPHA = 0.10
OOD_MARGIN_FRACTION = 0.25


def _canonical_hash(payload: AxiomModel | Mapping[str, Any]) -> str:
    data = (
        payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(payload, AxiomModel)
        else dict(payload)
    )
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ParameterSensitivityItem(AxiomModel):
    parameter_id: str = Field(alias="parameterId")
    display_name: str = Field(alias="displayName")
    group: ParameterGroup
    status: Literal["Active", "Inert", "CausalMasked"]
    contribution_ratio: float = Field(alias="contributionRatio")
    direction: Literal["positive", "negative", "nonlinear", "neutral"]
    linear_slope: float = Field(alias="linearSlope")
    quadratic_curvature: float = Field(alias="quadraticCurvature")
    rank_correlation: float = Field(alias="rankCorrelation")


class PairwiseParameterInteraction(AxiomModel):
    parameter_a: str = Field(alias="parameterA")
    parameter_b: str = Field(alias="parameterB")
    interaction_weight: float = Field(alias="interactionWeight")
    relative_strength: float = Field(alias="relativeStrength")
    engineering_note: str = Field(alias="engineeringNote")


class MarginalCurvePoint(AxiomModel):
    parameter_value: float = Field(alias="parameterValue")
    predicted_mean: float = Field(alias="predictedMean")
    uncertainty_radius: float = Field(alias="uncertaintyRadius")


class ParameterMarginalKnee(AxiomModel):
    parameter_id: str = Field(alias="parameterId")
    display_name: str = Field(alias="displayName")
    unit: str
    knee_value: float = Field(alias="kneeValue")
    min_prediction: float = Field(alias="minPrediction")
    max_prediction: float = Field(alias="maxPrediction")
    curve: tuple[MarginalCurvePoint, ...]
    tradeoff_summary: str = Field(alias="tradeoffSummary")


class ParameterFeatureEnvelope(AxiomModel):
    feature_ids: tuple[str, ...] = Field(alias="featureIds")
    minimums: tuple[float, ...]
    maximums: tuple[float, ...]
    margin_fraction: float = Field(default=OOD_MARGIN_FRACTION, alias="marginFraction")


class MetricSurrogateHead(AxiomModel):
    metric_id: str = Field(alias="metricId")
    unit: str
    modeling_mode: Literal[
        "greybox-physics-gp",
        "multi-fidelity-residual-fusion",
        "single-fidelity-surrogate",
    ] = Field(alias="modelingMode")
    base_metric_id: str | None = Field(default=None, alias="baseMetricId")
    uses_greybox_backbone: bool = Field(default=True, alias="usesGreyboxBackbone")
    active_feature_ids: tuple[str, ...] = Field(alias="activeFeatureIds")
    interaction_pairs: tuple[tuple[int, int], ...] = Field(default=(), alias="interactionPairs")
    poly_weights: tuple[float, ...] = Field(default=(), alias="polyWeights")
    gp_length_scales: tuple[float, ...] = Field(alias="gpLengthScales")
    gp_train_x: tuple[tuple[float, ...], ...] = Field(alias="gpTrainX")
    gp_alpha: tuple[float, ...] = Field(alias="gpAlpha")
    gp_signal_variance: float = Field(alias="gpSignalVariance")
    gp_noise_variance: float = Field(alias="gpNoiseVariance")
    conformal_radius: float = Field(alias="conformalRadius")
    greybox_only_rmse: float = Field(default=0.0, alias="greyboxOnlyRmse")
    train_rmse: float = Field(alias="trainRmse")
    cv_rmse: float = Field(alias="cvRmse")
    r2_score: float = Field(alias="r2Score")
    # Out-of-sample fidelity (leave-one-out). `r2Score` is in-sample and must not gate claims.
    loo_r2_score: float | None = Field(default=None, alias="looR2Score")
    # Residual GP is used only when it beats the grey-box backbone on leave-one-out error.
    residual_enabled: bool = Field(default=True, alias="residualEnabled")
    uncertainty_method: str = Field(default="loo-residual-quantile", alias="uncertaintyMethod")
    nominal_coverage: float | None = Field(default=None, alias="nominalCoverage")
    calibration_sample_count: int | None = Field(default=None, alias="calibrationSampleCount")
    envelope: ParameterFeatureEnvelope
    sensitivities: tuple[ParameterSensitivityItem, ...]
    interactions: tuple[PairwiseParameterInteraction, ...]
    marginal_knees: tuple[ParameterMarginalKnee, ...] = Field(alias="marginalKnees")


class CrossToolpathValidationItem(AxiomModel):
    held_out_case_id: str = Field(alias="heldOutCaseId")
    sample_count: int = Field(alias="sampleCount")
    duration_zero_shot_rmse_s: float = Field(alias="durationZeroShotRmseS")
    duration_zero_shot_mape_pct: float = Field(alias="durationZeroShotMapePct")
    command_deviation_zero_shot_rmse_mm: float = Field(alias="commandDeviationZeroShotRmseMm")
    actual_deviation_zero_shot_rmse_mm: float | None = Field(
        default=None, alias="actualDeviationZeroShotRmseMm"
    )


class CrossToolpathValidationSummary(AxiomModel):
    evaluated_case_count: int = Field(alias="evaluatedCaseCount")
    mean_duration_mape_pct: float = Field(alias="meanDurationMapePct")
    mean_command_deviation_rmse_mm: float = Field(alias="meanCommandDeviationRmseMm")
    mean_actual_deviation_rmse_mm: float | None = Field(
        default=None, alias="meanActualDeviationRmseMm"
    )
    items: tuple[CrossToolpathValidationItem, ...]


class LearnedParameterSurrogate(AxiomModel):
    schema_id: Literal["axiom.cnc-parameter-surrogate@1"] = Field(
        default="axiom.cnc-parameter-surrogate@1", alias="schemaId"
    )
    engine_mode: Literal["greybox-physics-gp", "blackbox-poly-gp"] = Field(
        default="greybox-physics-gp", alias="engineMode"
    )
    case_id: str = Field(alias="caseId")
    case_content_hash: str = Field(alias="caseContentHash")
    calibrated_case_ids: tuple[str, ...] = Field(default=(), alias="calibratedCaseIds")
    default_case: CncBenchmarkCase | None = Field(default=None, alias="defaultCase")
    greybox_constants: GreyBoxPhysicalConstants | None = Field(default=None, alias="greyboxConstants")
    physical_diagnostics: tuple[str, ...] = Field(default=(), alias="physicalDiagnostics")
    cross_toolpath_validation: CrossToolpathValidationSummary | None = Field(
        default=None, alias="crossToolpathValidation"
    )
    registry: CncParameterRegistry
    offline_run_count: int = Field(alias="offlineRunCount")
    controller_run_count: int = Field(alias="controllerRunCount")
    total_slice_sample_count: int = Field(alias="totalSliceSampleCount")
    global_active_parameter_ids: tuple[str, ...] = Field(alias="globalActiveParameterIds")
    baseline_parameters: dict[str, float] = Field(alias="baselineParameters")
    metric_heads: dict[str, MetricSurrogateHead] = Field(alias="metricHeads")
    kinematic_bridge_heads: dict[str, MetricSurrogateHead] = Field(default_factory=dict, alias="kinematicBridgeHeads")
    model_content_hash: str = Field(alias="modelContentHash")


class ParameterLearningRequest(AxiomModel):
    case: CncBenchmarkCase | None = None
    cases: tuple[CncBenchmarkCase, ...] | None = None
    registry: CncParameterRegistry | None = None
    exports: tuple[CncAlgorithmExport, ...] = Field(min_length=4, max_length=2000)
    target_metrics: tuple[str, ...] = Field(default=DEFAULT_TARGET_METRICS, alias="targetMetrics")
    max_active_parameters_per_metric: int = Field(default=6, ge=2, le=15, alias="maxActiveParametersPerMetric")

    @model_validator(mode="after")
    def require_at_least_one_case(self) -> ParameterLearningRequest:
        if self.case is None and not self.cases:
            raise ValueError("either `case` or non-empty `cases` must be provided")
        return self


def _rank_array(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(len(x), dtype=np.float64)
    return ranks


def _spearman_corr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or float(np.std(x)) < 1e-12 or float(np.std(y)) < 1e-12:
        return 0.0
    rx = _rank_array(x) - np.mean(_rank_array(x))
    ry = _rank_array(y) - np.mean(_rank_array(y))
    denom = float(np.linalg.norm(rx) * np.linalg.norm(ry))
    return float(np.dot(rx, ry) / denom) if denom > 1e-12 else 0.0


def _extract_feature_value(
    fid: str,
    params: Mapping[str, float],
    param_map: Mapping[str, ParameterDefinition],
    derived_map: Mapping[str, DerivedFeatureDefinition],
    gb_pred: Mapping[str, float] | None = None,
) -> float:
    if fid in param_map:
        p_def = param_map[fid]
        return normalize_parameter_value(p_def, float(params.get(fid, p_def.default_value)))
    if fid in derived_map:
        return compute_derived_feature_value(derived_map[fid], params, param_map)
    if fid.startswith("phys.") and gb_pred is not None:
        key = fid.split("phys.", 1)[1]
        if key == "firResonanceGain":
            return float(np.clip(2.0 * gb_pred.get("firResonanceGain", 0.5) - 1.0, -1.0, 1.0))
        if key == "notchSuppression":
            return float(np.clip(2.0 * gb_pred.get("notchSuppressionFactor", 1.0) - 1.0, -1.0, 1.0))
        if key == "revAccNorm":
            return float(np.clip(gb_pred.get("accelerationMaxMmS2", 2500.0) / 6000.0 - 1.0, -1.0, 1.5))
    return 0.0


def _residual_feature_ids_for_metric(
    metric_id: str,
    active_param_ids: Sequence[str],
    has_controller_traces: bool,
) -> list[str]:
    """Select compact, physically grounded 3D-6D feature subspace for the residual ARD-GP."""
    if metric_id == "quadrantGlitchExcessMm":
        return ["g3.friction_comp_amp_x", "g3.friction_comp_amp_y", "g3.servo_kp_x", "phys.revAccNorm"]
    if metric_id == "resonanceBandRmsMm":
        return ["g3.notch_filter_freq_hz", "g2.fir_moving_avg_time_ms", "phys.firResonanceGain", "phys.notchSuppression"]
    if metric_id in ("actualPathDeviationMaxMm", "normalServoErrorMaxMm") and has_controller_traces:
        chosen = list(active_param_ids[:4])
        for extra in ("derived.kp_xy_mismatch", "phys.firResonanceGain", "phys.notchSuppression"):
            if extra not in chosen and len(chosen) < 6:
                chosen.append(extra)
        return chosen
    if metric_id == "cornerSpeedMinMmS":
        chosen = list(active_param_ids[:4])
        for extra in ("g2.fir_moving_avg_time_ms", "g2.biquad_lowpass_freq_hz"):
            if extra not in chosen and len(chosen) < 5:
                chosen.append(extra)
        return chosen
    return list(active_param_ids[:5])


def _predict_residual_gp(head: MetricSurrogateHead, z_vec: Sequence[float] | np.ndarray) -> tuple[float, float, bool]:
    """Evaluate residual mean (linear intercept + GP), conformal uncertainty radius, and OOD status."""
    z = np.asarray(z_vec, dtype=np.float64).reshape(1, -1)
    k_dim = z.shape[1]
    mins = np.asarray(head.envelope.minimums, dtype=np.float64)
    maxs = np.asarray(head.envelope.maximums, dtype=np.float64)
    spans = np.maximum(maxs - mins, 0.25)
    margin = head.envelope.margin_fraction * spans
    in_dom = bool(np.all(z[0] >= (mins - margin)) and np.all(z[0] <= (maxs + margin)))

    intercept = float(head.poly_weights[0]) if len(head.poly_weights) >= 1 else 0.0
    lin_part = 0.0
    if len(head.poly_weights) >= 1 + k_dim:
        lin_w = np.asarray(head.poly_weights[1 : 1 + k_dim], dtype=np.float64)
        lin_part = float(np.dot(z[0], lin_w))

    X_tr = np.asarray(head.gp_train_x, dtype=np.float64)
    radius = float(head.conformal_radius)
    if not in_dom:
        # Outside the observed feature range the calibration quantile no longer applies;
        # inflate rather than shrink, and the caller must treat the point as OOD.
        radius *= 1.75
    if not head.residual_enabled:
        return 0.0, radius, not in_dom
    if len(X_tr) == 0:
        return intercept + lin_part, radius, not in_dom

    ls = np.asarray(head.gp_length_scales, dtype=np.float64)
    alpha = np.asarray(head.gp_alpha, dtype=np.float64)
    k_star = matern52_kernel(z, X_tr, ls, head.gp_signal_variance)
    gp_mean = float((k_star @ alpha)[0])
    return intercept + lin_part + gp_mean, radius, (not in_dom)


TRANSFER_Z_SCORE = 1.645


def _transfer_radius(
    surrogate: LearnedParameterSurrogate,
    metric_id: str,
    predicted: float,
    case: CncBenchmarkCase | None,
) -> float:
    """Uncertainty floor for toolpaths the model was NOT calibrated on.

    The in-sample quantile says nothing about a new geometry. The LOCO report measures the
    backbone's zero-shot error on each held-out calibration toolpath, so its worst case is
    the floor (about 90% under a normal approximation). Without a LOCO report a new
    toolpath gets no floor here and the caller must treat transfer as unverified."""
    if case is None or case.case_id in surrogate.calibrated_case_ids:
        return 0.0
    loco = surrogate.cross_toolpath_validation
    if loco is None or not loco.items:
        return 0.0
    if metric_id == "durationSeconds":
        worst_pct = max(it.duration_zero_shot_mape_pct for it in loco.items)
        return TRANSFER_Z_SCORE * worst_pct / 100.0 * abs(predicted)
    if metric_id == "sampledPathDeviationMaxMm":
        return TRANSFER_Z_SCORE * max(it.command_deviation_zero_shot_rmse_mm for it in loco.items)
    if metric_id in ("actualPathDeviationMaxMm", "normalServoErrorMaxMm"):
        vals = [it.actual_deviation_zero_shot_rmse_mm for it in loco.items if it.actual_deviation_zero_shot_rmse_mm is not None]
        return TRANSFER_Z_SCORE * max(vals) if vals else 0.0
    return 0.0


def predict_metric_for_parameters(
    surrogate: LearnedParameterSurrogate,
    metric_id: str,
    parameters: Mapping[str, float],
    *,
    target_case: CncBenchmarkCase | None = None,
) -> tuple[float, float, bool]:
    """Predict `(mean, uncertainty_radius, is_ood)` for `metric_id` on `target_case` (or `default_case`)."""
    full_params = {**surrogate.baseline_parameters, **{k: float(v) for k, v in parameters.items()}}
    active_case = target_case or surrogate.default_case

    gb_pred: dict[str, float] = {}
    if active_case is not None and surrogate.greybox_constants is not None:
        prof = extract_case_geometry_profile(active_case)
        gb_pred = evaluate_greybox_backbone(prof, full_params, surrogate.greybox_constants)

    if metric_id not in surrogate.metric_heads:
        raw_gb = float(gb_pred.get(metric_id, 0.0))
        if metric_id != "signedRadialOffsetMeanMm":
            raw_gb = max(0.0, raw_gb)
        return raw_gb, 0.0, False

    head = surrogate.metric_heads[metric_id]
    param_map = {p.parameter_id: p for p in surrogate.registry.parameters}
    derived_map = {d.feature_id: d for d in surrogate.registry.derived_features}
    z_vec = [
        _extract_feature_value(fid, full_params, param_map, derived_map, gb_pred)
        for fid in head.active_feature_ids
    ]
    res_mean, radius, is_ood = _predict_residual_gp(head, z_vec)

    if head.uses_greybox_backbone and gb_pred:
        base_phys = float(gb_pred.get(metric_id, 0.0))
        if target_case is not None and surrogate.default_case is not None and target_case.case_id != surrogate.default_case.case_id:
            if metric_id == "durationSeconds":
                def_prof = extract_case_geometry_profile(surrogate.default_case)
                tgt_prof = extract_case_geometry_profile(target_case)
                scale_len = tgt_prof.total_length_mm / max(def_prof.total_length_mm, 1e-6)
                res_mean *= min(2.5, max(0.25, scale_len))
                # Never shrink the calibrated radius when transferring to another toolpath.
                radius *= min(2.5, max(1.0, scale_len))
        pred_total = base_phys + res_mean
        if metric_id != "signedRadialOffsetMeanMm":
            pred_total = max(0.0, pred_total)
        radius = max(radius, _transfer_radius(surrogate, metric_id, pred_total, active_case))
        return pred_total, radius, is_ood

    return max(0.0, res_mean), radius, is_ood


def _compute_physics_sensitivities(
    metric_id: str,
    profiles: Sequence[CaseGeometryProfile],
    consts: GreyBoxPhysicalConstants,
    registry: CncParameterRegistry,
    baseline_params: Mapping[str, float],
    observed_params: Sequence[Mapping[str, float]],
    observed_y: np.ndarray,
    *,
    has_controller_traces: bool,
    max_active: int,
) -> tuple[list[str], tuple[ParameterSensitivityItem, ...], tuple[PairwiseParameterInteraction, ...]]:
    """Compute exact variance-based physical sensitivity & bilinear coupling on active case geometries."""
    mask = causal_mask_for_metric(registry, metric_id, has_controller_traces=has_controller_traces)
    param_map = {p.parameter_id: p for p in registry.parameters}

    grid_u = np.linspace(-0.85, 0.85, 7)
    raw_scores: dict[str, float] = {}
    slopes: dict[str, float] = {}
    curvatures: dict[str, float] = {}
    rank_corrs: dict[str, float] = {}

    y_obs_std = max(float(np.std(observed_y)), 1e-9)

    for p in registry.parameters:
        pid = p.parameter_id
        if not mask.get(pid, False):
            continue

        sweep_vals: list[float] = []
        for u_val in grid_u:
            probe = dict(baseline_params)
            probe[pid] = denormalize_parameter_value(p, float(u_val))
            gb_across_cases = [
                evaluate_greybox_backbone(prof, probe, consts).get(metric_id, 0.0)
                for prof in profiles
            ]
            sweep_vals.append(float(np.mean(gb_across_cases)))

        arr_s = np.asarray(sweep_vals, dtype=np.float64)
        phys_span = float(np.max(arr_s) - np.min(arr_s))
        quad_fit = np.polyfit(grid_u, arr_s, deg=2)
        c2, c1, _ = float(quad_fit[0]), float(quad_fit[1]), float(quad_fit[2])

        obs_col = np.asarray([normalize_parameter_value(p, float(pd.get(pid, p.default_value))) for pd in observed_params])
        rho = _spearman_corr(obs_col, observed_y) if float(np.std(obs_col)) > 0.05 else 0.0

        phys_rel = phys_span / max(y_obs_std * 2.5, phys_span, 1e-9)
        if phys_span <= 1e-11:
            score = 0.05 * max(0.0, abs(rho) - 0.55)
        else:
            score = 0.78 * phys_rel + 0.22 * abs(rho)

        raw_scores[pid] = float(score)
        slopes[pid] = c1
        curvatures[pid] = c2
        rank_corrs[pid] = rho

    total_score = sum(raw_scores.values()) or 1.0
    ranked_ids = sorted(raw_scores.keys(), key=lambda k: raw_scores[k], reverse=True)

    active_ids: list[str] = []
    cum = 0.0
    for pid in ranked_ids:
        ratio = raw_scores[pid] / total_score
        if len(active_ids) < max_active and ((len(active_ids) < 2 and raw_scores[pid] > 1e-6) or (ratio >= 0.045 and cum < 0.94)):
            active_ids.append(pid)
            cum += ratio
    if not active_ids and ranked_ids:
        active_ids = ranked_ids[: min(2, len(ranked_ids))]

    active_set = set(active_ids)
    sens_items: list[ParameterSensitivityItem] = []
    for p in registry.parameters:
        pid = p.parameter_id
        if not mask.get(pid, False):
            sens_items.append(
                ParameterSensitivityItem(
                    parameterId=pid,
                    displayName=p.display_name,
                    group=p.group,
                    status="CausalMasked",
                    contributionRatio=0.0,
                    direction="neutral",
                    linearSlope=0.0,
                    quadraticCurvature=0.0,
                    rankCorrelation=0.0,
                )
            )
            continue
        c_ratio = round(float(raw_scores.get(pid, 0.0) / total_score), 6)
        slp = slopes.get(pid, 0.0)
        crv = curvatures.get(pid, 0.0)
        rc = rank_corrs.get(pid, 0.0)
        if pid not in active_set or c_ratio < 0.02:
            direction: Literal["positive", "negative", "nonlinear", "neutral"] = "neutral"
        elif abs(crv) > 1.35 * abs(slp) and abs(slp) < 1e-4:
            direction = "nonlinear"
        elif slp > 1e-9 or (abs(slp) <= 1e-9 and rc > 0):
            direction = "positive"
        elif slp < -1e-9 or (abs(slp) <= 1e-9 and rc < 0):
            direction = "negative"
        else:
            direction = "neutral"

        sens_items.append(
            ParameterSensitivityItem(
                parameterId=pid,
                displayName=p.display_name,
                group=p.group,
                status="Active" if pid in active_set else "Inert",
                contributionRatio=c_ratio,
                direction=direction,
                linearSlope=round(slp, 8),
                quadraticCurvature=round(crv, 8),
                rankCorrelation=round(rc, 6),
            )
        )
    sens_items.sort(key=lambda item: (item.status == "Active", item.contribution_ratio), reverse=True)

    interactions: list[PairwiseParameterInteraction] = []
    probe_ids = active_ids[:5]
    raw_inters: list[tuple[str, str, float]] = []
    delta_u = 0.75
    for idx_a in range(len(probe_ids)):
        for idx_b in range(idx_a + 1, len(probe_ids)):
            pa, pb = probe_ids[idx_a], probe_ids[idx_b]
            da, db = param_map[pa], param_map[pb]

            def _eval_pair(ua: float, ub: float) -> float:
                pr = dict(baseline_params)
                pr[pa] = denormalize_parameter_value(da, ua)
                pr[pb] = denormalize_parameter_value(db, ub)
                return float(np.mean([evaluate_greybox_backbone(prof, pr, consts).get(metric_id, 0.0) for prof in profiles]))

            f_pp = _eval_pair(+delta_u, +delta_u)
            f_pm = _eval_pair(+delta_u, -delta_u)
            f_mp = _eval_pair(-delta_u, +delta_u)
            f_mm = _eval_pair(-delta_u, -delta_u)
            cross = (f_pp - f_pm - f_mp + f_mm) / (4.0 * delta_u * delta_u)
            if abs(cross) > 1e-8:
                raw_inters.append((pa, pb, cross))

    max_w = max((abs(x[2]) for x in raw_inters), default=1.0) or 1.0
    for pa, pb, w_val in sorted(raw_inters, key=lambda x: abs(x[2]), reverse=True)[:5]:
        note_dir = "物理瓶颈耦合（木桶联动/协同放大）" if w_val > 0 else "物理相互制约/反向补偿"
        interactions.append(
            PairwiseParameterInteraction(
                parameterA=pa,
                parameterB=pb,
                interactionWeight=round(w_val, 8),
                relativeStrength=round(abs(w_val) / max_w, 4),
                engineeringNote=f"{pa} × {pb} 在 {metric_id} 上存在{note_dir}（交叉敏感度 {w_val:+.4g}）",
            )
        )

    return active_ids, tuple(sens_items), tuple(interactions)


def _fit_greybox_residual_head(
    metric_id: str,
    unit: str,
    y_obs: np.ndarray,
    records_subset: Sequence[tuple[CaseGeometryProfile, dict[str, float]]],
    all_profiles: Sequence[CaseGeometryProfile],
    consts: GreyBoxPhysicalConstants,
    registry: CncParameterRegistry,
    baseline_params: Mapping[str, float],
    *,
    has_controller_traces: bool,
    max_active: int,
    modeling_mode: Literal["greybox-physics-gp", "multi-fidelity-residual-fusion"] = "greybox-physics-gp",
    base_metric_id: str | None = None,
) -> MetricSurrogateHead:
    param_map = {p.parameter_id: p for p in registry.parameters}
    derived_map = {d.feature_id: d for d in registry.derived_features}

    obs_params = [r[1] for r in records_subset]
    gb_preds_list = [evaluate_greybox_backbone(prof, p_dict, consts) for prof, p_dict in records_subset]
    y_gb = np.asarray([g.get(metric_id, 0.0) for g in gb_preds_list], dtype=np.float64)
    residuals = y_obs - y_gb
    gb_rmse = float(math.sqrt(np.mean(residuals ** 2)))

    active_param_ids, sensitivities, interactions = _compute_physics_sensitivities(
        metric_id,
        all_profiles,
        consts,
        registry,
        baseline_params,
        obs_params,
        y_obs,
        has_controller_traces=has_controller_traces,
        max_active=max_active,
    )

    feat_ids = _residual_feature_ids_for_metric(metric_id, active_param_ids, has_controller_traces)
    if not feat_ids:
        feat_ids = [registry.parameters[0].parameter_id]

    n_samples = len(y_obs)
    k_dim = len(feat_ids)
    Z_mat = np.zeros((n_samples, k_dim), dtype=np.float64)
    for i, (p_dict, gb_p) in enumerate(zip(obs_params, gb_preds_list)):
        for j, fid in enumerate(feat_ids):
            Z_mat[i, j] = _extract_feature_value(fid, p_dict, param_map, derived_map, gb_p)

    Design1 = np.hstack([np.ones((n_samples, 1)), Z_mat])
    reg_d = np.full(k_dim + 1, 0.25, dtype=np.float64)
    reg_d[0] = 1e-6
    lin_beta = np.linalg.solve(Design1.T @ Design1 + np.diag(reg_d), Design1.T @ residuals)
    lin_trend = Design1 @ lin_beta
    gp_target = residuals - lin_trend

    ls_opt, sig_var, noi_var, gp_alpha = fit_mle_ard_matern52_gp(Z_mat, gp_target)

    loo_abs_errors: list[float] = []
    for i in range(n_samples):
        idx_tr = [idx for idx in range(n_samples) if idx != i]
        D_tr = Design1[idx_tr]
        r_tr = residuals[idx_tr]
        try:
            b_i = np.linalg.solve(D_tr.T @ D_tr + np.diag(reg_d), D_tr.T @ r_tr)
            rem_tr = r_tr - D_tr @ b_i
            K_tr = matern52_kernel(Z_mat[idx_tr], Z_mat[idx_tr], ls_opt, sig_var) + noi_var * np.eye(len(idx_tr))
            a_i = np.linalg.solve(K_tr, rem_tr)
            k_s = matern52_kernel(Z_mat[i : i + 1], Z_mat[idx_tr], ls_opt, sig_var)
            res_pred_i = float((Design1[i : i + 1] @ b_i)[0] + (k_s @ a_i)[0])
        except np.linalg.LinAlgError:
            res_pred_i = float(lin_trend[i])
        loo_abs_errors.append(abs(float(y_obs[i]) - (float(y_gb[i]) + res_pred_i)))

    gb_abs_errors = [abs(float(r)) for r in residuals]
    loo_rmse_with_residual = float(math.sqrt(np.mean(np.square(loo_abs_errors)))) if loo_abs_errors else gb_rmse
    # Gate: keep the residual GP only if it beats the fixed grey-box backbone out of sample.
    residual_enabled = bool(loo_abs_errors) and loo_rmse_with_residual < 0.98 * gb_rmse
    calib_errors = loo_abs_errors if residual_enabled else gb_abs_errors

    # Leave-one-out residual quantile at the finite-sample rank ceil((n + 1)(1 - alpha)).
    # When n is too small for that rank, fall back to the largest observed error.
    sorted_err = sorted(calib_errors)
    n_cal = len(sorted_err)
    rank = math.ceil((n_cal + 1) * (1.0 - CONFORMAL_ALPHA))
    conformal_rad = float(sorted_err[min(rank, n_cal) - 1]) if sorted_err else 0.0

    if residual_enabled:
        full_res_pred = lin_trend + (matern52_kernel(Z_mat, Z_mat, ls_opt, sig_var) @ gp_alpha)
    else:
        full_res_pred = np.zeros(n_samples, dtype=np.float64)
        lin_beta = np.zeros_like(lin_beta)
        gp_alpha = np.zeros_like(gp_alpha)
    full_pred = y_gb + full_res_pred
    train_rmse = float(math.sqrt(np.mean((y_obs - full_pred) ** 2)))
    cv_rmse = loo_rmse_with_residual if residual_enabled else gb_rmse
    ss_tot = float(np.sum((y_obs - np.mean(y_obs)) ** 2))
    ss_res = float(np.sum((y_obs - full_pred) ** 2))
    r2 = float(max(0.0, 1.0 - ss_res / ss_tot)) if ss_tot > 1e-12 else 1.0
    ss_loo = float(np.sum(np.square(calib_errors)))
    loo_r2 = float(1.0 - ss_loo / ss_tot) if ss_tot > 1e-12 else None

    # Feature envelope = observed training range (no artificial widening); the margin is
    # applied at prediction time.
    env_mins: list[float] = []
    env_maxs: list[float] = []
    for j in range(len(feat_ids)):
        env_mins.append(round(float(np.min(Z_mat[:, j])), 6))
        env_maxs.append(round(float(np.max(Z_mat[:, j])), 6))

    envelope = ParameterFeatureEnvelope(
        featureIds=tuple(feat_ids),
        minimums=tuple(env_mins),
        maximums=tuple(env_maxs),
        marginFraction=OOD_MARGIN_FRACTION,
    )

    provisional = MetricSurrogateHead(
        metricId=metric_id,
        unit=unit,
        modelingMode=modeling_mode,
        baseMetricId=base_metric_id,
        usesGreyboxBackbone=True,
        activeFeatureIds=tuple(feat_ids),
        interactionPairs=(),
        polyWeights=tuple(round(float(v), 12) for v in lin_beta),
        gpLengthScales=tuple(round(float(v), 8) for v in ls_opt),
        gpTrainX=tuple(tuple(round(float(v), 8) for v in row) for row in Z_mat),
        gpAlpha=tuple(round(float(v), 12) for v in gp_alpha),
        gpSignalVariance=round(sig_var, 12),
        gpNoiseVariance=round(noi_var, 12),
        conformalRadius=round(conformal_rad, 8),
        greyboxOnlyRmse=round(gb_rmse, 8),
        trainRmse=round(train_rmse, 8),
        cvRmse=round(cv_rmse, 8),
        r2Score=round(r2, 6),
        looR2Score=round(loo_r2, 6) if loo_r2 is not None else None,
        residualEnabled=residual_enabled,
        uncertaintyMethod="loo-residual-quantile",
        nominalCoverage=round(1.0 - CONFORMAL_ALPHA, 4),
        calibrationSampleCount=n_cal,
        envelope=envelope,
        sensitivities=sensitivities,
        interactions=interactions,
        marginalKnees=(),
    )

    ref_prof = all_profiles[0]
    knees: list[ParameterMarginalKnee] = []
    grid_norm = np.linspace(-1.0, 1.0, 13)
    for pid in active_param_ids:
        if pid not in param_map:
            continue
        p_def = param_map[pid]
        pts: list[MarginalCurvePoint] = []
        preds: list[float] = []
        raw_vals: list[float] = []
        for g_val in grid_norm:
            r_val = denormalize_parameter_value(p_def, float(g_val))
            probe_p = dict(baseline_params)
            probe_p[pid] = r_val
            gb_p = evaluate_greybox_backbone(ref_prof, probe_p, consts)
            z_probe = [_extract_feature_value(f_id, probe_p, param_map, derived_map, gb_p) for f_id in feat_ids]
            rm, rr, _ = _predict_residual_gp(provisional, z_probe)
            pm = float(gb_p.get(metric_id, 0.0)) + rm
            if metric_id != "signedRadialOffsetMeanMm":
                pm = max(0.0, pm)
            raw_vals.append(r_val)
            preds.append(pm)
            pts.append(
                MarginalCurvePoint(
                    parameterValue=r_val,
                    predictedMean=round(pm, 6),
                    uncertaintyRadius=round(rr, 6),
                )
            )
        arr_p = np.asarray(preds, dtype=np.float64)
        if len(arr_p) >= 3 and (np.max(arr_p) - np.min(arr_p)) > 1e-9:
            second_diff = np.abs(np.diff(arr_p, n=2))
            knee_idx = int(np.argmax(second_diff)) + 1
        else:
            knee_idx = len(arr_p) // 2
        knee_val = raw_vals[knee_idx]
        knees.append(
            ParameterMarginalKnee(
                parameterId=pid,
                displayName=p_def.display_name,
                unit=p_def.unit,
                kneeValue=knee_val,
                minPrediction=round(float(np.min(arr_p)), 6),
                maxPrediction=round(float(np.max(arr_p)), 6),
                curve=tuple(pts),
                tradeoffSummary=(
                    f"{p_def.display_name} ({pid}) 在 {knee_val:g} {p_def.unit} 附近触及物理瓶颈饱和拐点 "
                    f"（{metric_id} 响应范围 {np.min(arr_p):.4g} ~ {np.max(arr_p):.4g} {unit}）"
                ),
            )
        )

    return provisional.model_copy(update={"marginal_knees": tuple(knees)})


def _compute_loco_cross_toolpath_validation(
    case_list: Sequence[CncBenchmarkCase],
    full_records: Sequence[tuple[CaseGeometryProfile, CncBenchmarkCase, CncAlgorithmExport, CncQualityReport, dict[str, float]]],
) -> CrossToolpathValidationSummary | None:
    """Evaluate Leave-One-Case-Out (LOCO) zero-shot physical transfer error across distinct toolpath geometries."""
    if len(case_list) < 2:
        return None

    items: list[CrossToolpathValidationItem] = []
    for held_case in case_list:
        train_recs = [r for r in full_records if r[1].case_id != held_case.case_id]
        val_recs = [r for r in full_records if r[1].case_id == held_case.case_id]
        if len(train_recs) < 3 or len(val_recs) < 1:
            continue
        loco_consts, _ = calibrate_greybox_constants(train_recs)
        dur_sq: list[float] = []
        dur_ape: list[float] = []
        cmd_sq: list[float] = []
        act_sq: list[float] = []
        for prof, _, _, rep, p_dict in val_recs:
            pred = evaluate_greybox_backbone(prof, p_dict, loco_consts)
            obs_d = float(rep.kinematic_summary["durationSeconds"])
            obs_cmd = float(rep.kinematic_summary["sampledPathDeviationMaxMm"])
            dur_sq.append((pred["durationSeconds"] - obs_d) ** 2)
            dur_ape.append(abs(pred["durationSeconds"] - obs_d) / max(obs_d, 1e-6) * 100.0)
            cmd_sq.append((pred["sampledPathDeviationMaxMm"] - obs_cmd) ** 2)
            if rep.servo_metrics is not None and rep.servo_metrics.get("actualPathDeviationMaxMm") is not None:
                obs_act = float(rep.servo_metrics["actualPathDeviationMaxMm"].value or 0.0)
                act_sq.append((pred["actualPathDeviationMaxMm"] - obs_act) ** 2)

        items.append(
            CrossToolpathValidationItem(
                heldOutCaseId=held_case.case_id,
                sampleCount=len(val_recs),
                durationZeroShotRmseS=round(math.sqrt(float(np.mean(dur_sq))), 6),
                durationZeroShotMapePct=round(float(np.mean(dur_ape)), 3),
                commandDeviationZeroShotRmseMm=round(math.sqrt(float(np.mean(cmd_sq))), 6),
                actualDeviationZeroShotRmseMm=(
                    round(math.sqrt(float(np.mean(act_sq))), 6) if act_sq else None
                ),
            )
        )

    if not items:
        return None
    act_vals = [it.actual_deviation_zero_shot_rmse_mm for it in items if it.actual_deviation_zero_shot_rmse_mm is not None]
    return CrossToolpathValidationSummary(
        evaluatedCaseCount=len(items),
        meanDurationMapePct=round(float(np.mean([it.duration_zero_shot_mape_pct for it in items])), 3),
        meanCommandDeviationRmseMm=round(float(np.mean([it.command_deviation_zero_shot_rmse_mm for it in items])), 6),
        meanActualDeviationRmseMm=round(float(np.mean(act_vals)), 6) if act_vals else None,
        items=tuple(items),
    )


def learn_parameter_surrogate(
    request_or_case: ParameterLearningRequest | CncBenchmarkCase | Sequence[CncBenchmarkCase] | Mapping[str, Any],
    exports: Sequence[CncAlgorithmExport | Mapping[str, Any]] | None = None,
    *,
    registry: CncParameterRegistry | None = None,
    target_metrics: Sequence[str] = DEFAULT_TARGET_METRICS,
    max_active_parameters_per_metric: int = 6,
) -> LearnedParameterSurrogate:
    """Calibrate the 3-layer Grey-Box + MLE ARD-GP surrogate on single-case or multi-case exports."""
    if exports is None:
        req = (
            request_or_case
            if isinstance(request_or_case, ParameterLearningRequest)
            else ParameterLearningRequest.model_validate(request_or_case)
        )
    else:
        resolved_exports = tuple(
            item if isinstance(item, CncAlgorithmExport) else CncAlgorithmExport.model_validate(item)
            for item in exports
        )
        if isinstance(request_or_case, (list, tuple)):
            resolved_cases = tuple(
                c if isinstance(c, CncBenchmarkCase) else CncBenchmarkCase.model_validate(c)
                for c in request_or_case
            )
            req = ParameterLearningRequest(
                case=resolved_cases[0],
                cases=resolved_cases,
                registry=registry,
                exports=resolved_exports,
                targetMetrics=tuple(target_metrics),
                maxActiveParametersPerMetric=max_active_parameters_per_metric,
            )
        else:
            resolved_case = (
                request_or_case
                if isinstance(request_or_case, CncBenchmarkCase)
                else CncBenchmarkCase.model_validate(request_or_case)
            )
            req = ParameterLearningRequest(
                case=resolved_case,
                cases=(resolved_case,),
                registry=registry,
                exports=resolved_exports,
                targetMetrics=tuple(target_metrics),
                maxActiveParametersPerMetric=max_active_parameters_per_metric,
            )

    case_list: list[CncBenchmarkCase] = []
    if req.cases:
        case_list.extend(req.cases)
    if req.case is not None and all(c.case_id != req.case.case_id for c in case_list):
        case_list.insert(0, req.case)
    primary_case = req.case or case_list[0]

    case_by_hash = {benchmark_case_hash(c): c for c in case_list}
    profile_by_hash = {h: extract_case_geometry_profile(c) for h, c in case_by_hash.items()}
    unique_profiles = list(profile_by_hash.values())

    reg = req.registry or default_cnc_parameter_registry()
    verify_registry_content_hash(reg)
    missing_ids = missing_greybox_parameter_ids(reg)
    if missing_ids:
        raise ValueError(
            f"registry {reg.registry_id} is not compatible with grey-box kernel {GREYBOX_KERNEL_ID}: "
            f"missing {', '.join(missing_ids)}. Map the controller's parameters onto the kernel "
            "parameter ids (controller profile) instead of renaming them; unmapped parameters "
            "would otherwise silently fall back to defaults."
        )
    default_params = default_parameter_values(reg)
    registry_ids = set(default_params)

    full_records: list[tuple[CaseGeometryProfile, CncBenchmarkCase, CncAlgorithmExport, CncQualityReport, dict[str, float]]] = []
    for exp in req.exports:
        if not exp.parameters:
            raise ValueError("All exports supplied to learn_parameter_surrogate must include parameters")
        unknown_ids = sorted(set(exp.parameters) - registry_ids)
        if unknown_ids:
            raise ValueError(
                f"export {exp.algorithm_id} {exp.algorithm_version} reports parameters not in registry "
                f"{reg.registry_id}: {', '.join(unknown_ids[:8])}{' ...' if len(unknown_ids) > 8 else ''}"
            )
        matched_case = case_by_hash.get(exp.case_content_hash)
        if matched_case is None:
            raise ValueError(
                f"export caseContentHash {exp.case_content_hash[:12]}... does not match any supplied CncBenchmarkCase"
            )
        rep = evaluate_cnc_export(matched_case, exp)
        merged_p = {**default_params, **{k: float(v) for k, v in exp.parameters.items()}}
        full_records.append((profile_by_hash[exp.case_content_hash], matched_case, exp, rep, merged_p))

    offline_records = [r for r in full_records if r[3].servo_metrics is None]
    ctrl_records = [r for r in full_records if r[3].servo_metrics is not None]
    total_slices = sum(len(r[3].geometry_slices) for r in full_records)

    # Layer 2: Calibrate Grey-Box Physical Constants across all supplied cases & traces
    gb_consts, phys_notes = calibrate_greybox_constants(full_records)
    loco_summary = _compute_loco_cross_toolpath_validation(case_list, full_records)

    # Layer 3: Fit compact residual GP heads per metric
    metric_heads: dict[str, MetricSurrogateHead] = {}
    for m_id in req.target_metrics:
        if m_id in PLANNING_METRIC_IDS:
            vals: list[float] = []
            sub_recs: list[tuple[CaseGeometryProfile, dict[str, float]]] = []
            unit = "mm"
            for prof, _, _, rep, p_dict in full_records:
                if m_id == "sampledPathDeviationMaxMm" and not (prof.has_corners or prof.has_arcs or prof.has_micro_segments):
                    continue
                if m_id == "cornerSpeedMinMmS" and not prof.has_corners:
                    continue
                m_obj = rep.analysis.metrics.get(m_id)
                if m_obj is not None and m_obj.value is not None:
                    vals.append(float(m_obj.value))
                    sub_recs.append((prof, p_dict))
                    unit = m_obj.unit
            if len(vals) >= 4:
                metric_heads[m_id] = _fit_greybox_residual_head(
                    m_id,
                    unit,
                    np.asarray(vals, dtype=np.float64),
                    sub_recs,
                    unique_profiles,
                    gb_consts,
                    reg,
                    default_params,
                    has_controller_traces=False,
                    max_active=req.max_active_parameters_per_metric,
                )
        elif m_id in SERVO_METRIC_IDS and len(ctrl_records) >= 4:
            vals_c: list[float] = []
            sub_c: list[tuple[CaseGeometryProfile, dict[str, float]]] = []
            unit = "mm"
            for prof, _, _, rep, p_dict in ctrl_records:
                if m_id == "quadrantGlitchExcessMm" and not (prof.has_arcs or prof.has_xy_reversals):
                    continue
                if m_id in ("actualPathDeviationMaxMm", "normalServoErrorMaxMm") and not (prof.has_corners or prof.has_arcs or prof.has_micro_segments):
                    continue
                assert rep.servo_metrics is not None
                m_obj = rep.servo_metrics.get(m_id)
                if m_obj is not None and m_obj.value is not None:
                    vals_c.append(float(m_obj.value))
                    sub_c.append((prof, p_dict))
                    unit = m_obj.unit
            if len(vals_c) >= 4:
                is_fusion = m_id == "actualPathDeviationMaxMm" and len(offline_records) >= 2
                metric_heads[m_id] = _fit_greybox_residual_head(
                    m_id,
                    unit,
                    np.asarray(vals_c, dtype=np.float64),
                    sub_c,
                    unique_profiles,
                    gb_consts,
                    reg,
                    default_params,
                    has_controller_traces=True,
                    max_active=req.max_active_parameters_per_metric,
                    modeling_mode="multi-fidelity-residual-fusion" if is_fusion else "greybox-physics-gp",
                    base_metric_id="sampledPathDeviationMaxMm" if is_fusion else None,
                )

    param_id_set = {p.parameter_id for p in reg.parameters}
    global_active: list[str] = []
    for head in metric_heads.values():
        for s_item in head.sensitivities:
            if s_item.status == "Active" and s_item.parameter_id in param_id_set and s_item.parameter_id not in global_active:
                global_active.append(s_item.parameter_id)

    surrogate = LearnedParameterSurrogate(
        engineMode="greybox-physics-gp",
        caseId=primary_case.case_id,
        caseContentHash=benchmark_case_hash(primary_case),
        calibratedCaseIds=tuple(c.case_id for c in case_list),
        defaultCase=primary_case,
        greyboxConstants=gb_consts,
        physicalDiagnostics=phys_notes,
        crossToolpathValidation=loco_summary,
        registry=reg,
        offlineRunCount=len(offline_records),
        controllerRunCount=len(ctrl_records),
        totalSliceSampleCount=total_slices,
        globalActiveParameterIds=tuple(global_active),
        baselineParameters=default_params,
        metricHeads=metric_heads,
        kinematicBridgeHeads={},
        modelContentHash="",
    )
    content = surrogate.model_dump(mode="json", by_alias=True, exclude_none=True)
    content.pop("modelContentHash")
    return surrogate.model_copy(update={"model_content_hash": _canonical_hash(content)})


def _pad(text: str, width: int, *, right: bool = False) -> str:
    shown = sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)
    fill = " " * max(width - shown, 1 if right else 0)
    return fill + text if right else text + fill


def render_parameter_impact_table(surrogate: LearnedParameterSurrogate) -> str:
    """Render a concise grey-box physical calibration, LOCO audit & 30+ parameter attribution report."""
    cases_str = ", ".join(surrogate.calibrated_case_ids) if surrogate.calibrated_case_ids else surrogate.case_id
    lines = [
        f"案例 {cases_str} · 30+ 参数自动学习与敏感度归因报告（引擎：{surrogate.engine_mode}）",
        f"训练样本：离线规划 {surrogate.offline_run_count} 组 + 控制器实采 {surrogate.controller_run_count} 组（共提取 {surrogate.total_slice_sample_count} 个几何基元切片）",
        f"全局识别出的核心活跃参数（共 {len(surrogate.global_active_parameter_ids)}/{len(surrogate.registry.parameters)} 个）：{', '.join(surrogate.global_active_parameter_ids)}",
    ]
    for diag in surrogate.physical_diagnostics:
        lines.append(f"  [灰盒标定] {diag}")
    if surrogate.cross_toolpath_validation is not None:
        loco = surrogate.cross_toolpath_validation
        act_str = f"，实测轮廓 RMSE={loco.mean_actual_deviation_rmse_mm:.4g}mm" if loco.mean_actual_deviation_rmse_mm is not None else ""
        lines.append(
            f"  [跨刀路留一验证 LOCO] 覆盖 {loco.evaluated_case_count} 条独立刀路：零样本时长 MAPE={loco.mean_duration_mape_pct:.2f}%，"
            f"指令轮廓 RMSE={loco.mean_command_deviation_rmse_mm:.4g}mm{act_str}"
        )
    lines.append("")

    for m_id, head in surrogate.metric_heads.items():
        loo_r2_txt = f"{head.loo_r2_score:.3f}" if head.loo_r2_score is not None else "-"
        residual_txt = "启用" if head.residual_enabled else "关闭（留一误差不优于纯灰盒）"
        cov_txt = f"名义覆盖 {head.nominal_coverage:.0%}，" if head.nominal_coverage is not None else ""
        lines.append(
            f"【指标 {m_id} ({head.unit})】留一 R²={loo_r2_txt}（训练 R²={head.r2_score:.3f}），"
            f"纯灰盒RMSE={head.greybox_only_rmse:.4g}, 留一RMSE={head.cv_rmse:.4g}, 残差GP={residual_txt}, "
            f"不确定性半径=±{head.conformal_radius:.4g}（{cov_txt}实机覆盖率未验证）"
        )
        lines.append(
            "  "
            + _pad("排名/参数ID", 32)
            + _pad("名称", 24)
            + _pad("分组", 22)
            + _pad("贡献率", 10, right=True)
            + _pad("方向", 10, right=True)
        )
        active_items = [s for s in head.sensitivities if s.status == "Active"][:6]
        for rank, s in enumerate(active_items, 1):
            lines.append(
                "  "
                + _pad(f"#{rank} {s.parameter_id}", 32)
                + _pad(s.display_name[:11], 24)
                + _pad(s.group, 22)
                + _pad(f"{s.contribution_ratio:.1%}", 10, right=True)
                + _pad(s.direction, 10, right=True)
            )
        if head.interactions:
            lines.append(f"  * 主导耦合项：{head.interactions[0].engineering_note}")
        if head.marginal_knees:
            lines.append(f"  * 边际收益拐点：{head.marginal_knees[0].tradeoff_summary}")
        lines.append("")
    return "\n".join(lines)
