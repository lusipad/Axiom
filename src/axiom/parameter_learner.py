"""Two-Stage High-Dimensional CNC Parameter Learner & Multi-Fidelity Surrogate Engine.

Solves the 30+ parameter learning and attribution problem via:
1. Stage 1 (Causal Masking + Sparse Active Subspace Screening):
   - Applies physical group causal masks (G3 servo parameters masked to 0 on planning metrics).
   - Fits coordinate-descent ElasticNet (L1 + L2) on normalized linear + pure quadratic main effects,
     combined with Spearman rank correlation to isolate the Top-K Active Parameters per metric.
2. Stage 2 (Active Subspace Quadratic Response Surface + ARD Matérn-5/2 GP + Multi-Fidelity Residual Fusion):
   - Fits a second-order response surface (including pairwise interactions) plus an anisotropic
     Matérn-5/2 Gaussian Process on the active subspace.
   - When both offline exports and controller traces are supplied, fuses them by learning the
     servo residual delta_servo(z_kin, theta_G3) on top of the offline planning surrogate.
   - Calibrates Split Conformal / LOO-CV prediction intervals and FeatureEnvelope OOD bounds.
3. Parameter Impact & Attribution Report:
   - Ranked main-effect sensitivity matrix, pairwise interaction discovery, and 1D marginal knee points.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from pydantic import Field

from .benchmark import (
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncQualityReport,
    benchmark_case_hash,
    evaluate_cnc_export,
)
from .models import AxiomModel
from .parameter_space import (
    PLANNING_METRIC_IDS,
    SERVO_METRIC_IDS,
    CncParameterRegistry,
    ParameterDefinition,
    ParameterGroup,
    causal_mask_for_metric,
    compute_derived_feature_value,
    default_cnc_parameter_registry,
    default_parameter_values,
    denormalize_parameter_value,
    normalize_parameter_value,
)

DEFAULT_TARGET_METRICS = (
    "durationSeconds",
    "sampledPathDeviationMaxMm",
    "discreteJerkRms",
    "cornerSpeedMinMmS",
    "followingErrorMaxMm",
    "actualPathDeviationMaxMm",
)
KINEMATIC_BRIDGE_FEATURES = (
    "velocityMaxMmS",
    "accelerationMaxMmS2",
    "jerkRmsMmS3",
    "cornerSpeedMinMmS",
)
CONFORMAL_ALPHA = 0.10
OOD_MARGIN_FRACTION = 0.20


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
    modeling_mode: Literal["single-fidelity-surrogate", "multi-fidelity-residual-fusion"] = Field(
        alias="modelingMode"
    )
    base_metric_id: str | None = Field(default=None, alias="baseMetricId")
    active_feature_ids: tuple[str, ...] = Field(alias="activeFeatureIds")
    interaction_pairs: tuple[tuple[int, int], ...] = Field(alias="interactionPairs")
    poly_weights: tuple[float, ...] = Field(alias="polyWeights")
    gp_length_scales: tuple[float, ...] = Field(alias="gpLengthScales")
    gp_train_x: tuple[tuple[float, ...], ...] = Field(alias="gpTrainX")
    gp_alpha: tuple[float, ...] = Field(alias="gpAlpha")
    gp_signal_variance: float = Field(alias="gpSignalVariance")
    gp_noise_variance: float = Field(alias="gpNoiseVariance")
    conformal_radius: float = Field(alias="conformalRadius")
    train_rmse: float = Field(alias="trainRmse")
    cv_rmse: float = Field(alias="cvRmse")
    r2_score: float = Field(alias="r2Score")
    envelope: ParameterFeatureEnvelope
    sensitivities: tuple[ParameterSensitivityItem, ...]
    interactions: tuple[PairwiseParameterInteraction, ...]
    marginal_knees: tuple[ParameterMarginalKnee, ...] = Field(alias="marginalKnees")


class LearnedParameterSurrogate(AxiomModel):
    schema_id: Literal["axiom.cnc-parameter-surrogate@1"] = Field(
        default="axiom.cnc-parameter-surrogate@1", alias="schemaId"
    )
    case_id: str = Field(alias="caseId")
    case_content_hash: str = Field(alias="caseContentHash")
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
    case: CncBenchmarkCase
    registry: CncParameterRegistry | None = None
    exports: tuple[CncAlgorithmExport, ...] = Field(min_length=4, max_length=2000)
    target_metrics: tuple[str, ...] = Field(default=DEFAULT_TARGET_METRICS, alias="targetMetrics")
    max_active_parameters_per_metric: int = Field(default=6, ge=2, le=15, alias="maxActiveParametersPerMetric")


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


def _elastic_net_fit(
    X: np.ndarray,
    y: np.ndarray,
    *,
    l1_ratio: float = 0.65,
    alpha: float = 0.03,
    max_iter: int = 250,
) -> tuple[float, np.ndarray]:
    """Deterministic coordinate-descent ElasticNet solver on standardized columns."""
    n_samples, n_features = X.shape
    if n_samples == 0 or n_features == 0:
        return float(np.mean(y)) if len(y) else 0.0, np.zeros(n_features, dtype=np.float64)
    y_mean = float(np.mean(y))
    y_centered = y - y_mean
    y_scale = float(np.std(y_centered))
    if y_scale < 1e-12:
        return y_mean, np.zeros(n_features, dtype=np.float64)
    y_norm = y_centered / y_scale

    col_means = np.mean(X, axis=0)
    col_stds = np.std(X, axis=0)
    active_cols = col_stds > 1e-10
    X_std = np.zeros_like(X, dtype=np.float64)
    X_std[:, active_cols] = (X[:, active_cols] - col_means[active_cols]) / col_stds[active_cols]

    w = np.zeros(n_features, dtype=np.float64)
    l1_pen = alpha * l1_ratio
    l2_pen = alpha * (1.0 - l1_ratio)
    residual = y_norm.copy()

    for _ in range(max_iter):
        max_delta = 0.0
        for j in range(n_features):
            if not active_cols[j]:
                continue
            xj = X_std[:, j]
            old_wj = w[j]
            rho = float(np.dot(xj, residual + xj * old_wj) / n_samples)
            if rho > l1_pen:
                new_wj = (rho - l1_pen) / (1.0 + l2_pen)
            elif rho < -l1_pen:
                new_wj = (rho + l1_pen) / (1.0 + l2_pen)
            else:
                new_wj = 0.0
            if new_wj != old_wj:
                residual -= xj * (new_wj - old_wj)
                w[j] = new_wj
                max_delta = max(max_delta, abs(new_wj - old_wj))
        if max_delta < 1e-6:
            break

    # Rescale weights back to original X units
    w_unscaled = np.zeros(n_features, dtype=np.float64)
    w_unscaled[active_cols] = w[active_cols] * (y_scale / col_stds[active_cols])
    intercept = y_mean - float(np.dot(col_means, w_unscaled))
    return intercept, w_unscaled


def _poly2_basis(X: np.ndarray, pairs: Sequence[tuple[int, int]]) -> np.ndarray:
    """Construct [1, x_1..x_k, x_1^2..x_k^2, x_i * x_j] design matrix."""
    n = X.shape[0]
    cols = [np.ones((n, 1), dtype=np.float64), X, X * X]
    for i, j in pairs:
        cols.append((X[:, i] * X[:, j])[:, None])
    return np.hstack(cols)


def _matern52_kernel(X1: np.ndarray, X2: np.ndarray, length_scales: np.ndarray, signal_var: float) -> np.ndarray:
    ls = np.maximum(length_scales, 1e-3)
    diff = (X1[:, None, :] - X2[None, :, :]) / ls[None, None, :]
    r = np.sqrt(np.sum(diff * diff, axis=2))
    sqrt5_r = math.sqrt(5.0) * r
    return signal_var * (1.0 + sqrt5_r + (5.0 / 3.0) * (r * r)) * np.exp(-sqrt5_r)


def _extract_feature_value(
    feature_id: str,
    params: Mapping[str, float],
    param_map: Mapping[str, ParameterDefinition],
    derived_map: Mapping[str, Any],
    kinematic_context: Mapping[str, float] | None = None,
) -> float:
    if feature_id in param_map:
        p_def = param_map[feature_id]
        raw = float(params.get(feature_id, p_def.default_value))
        return normalize_parameter_value(p_def, raw)
    if feature_id in derived_map:
        return compute_derived_feature_value(derived_map[feature_id], params, param_map)
    if kinematic_context is not None and feature_id in kinematic_context:
        return float(kinematic_context[feature_id])
    return 0.0


def predict_head(
    head: MetricSurrogateHead,
    feature_vector: Sequence[float] | np.ndarray,
) -> tuple[float, float, bool]:
    """Predict (mean, uncertainty_radius, is_ood) for a normalized active feature vector."""
    x = np.asarray(feature_vector, dtype=np.float64).reshape(1, -1)
    mins = np.asarray(head.envelope.minimums, dtype=np.float64)
    maxs = np.asarray(head.envelope.maximums, dtype=np.float64)
    spans = np.maximum(maxs - mins, 0.20)
    margin = head.envelope.margin_fraction * spans
    is_ood = bool(np.any(x[0] < mins - margin) or np.any(x[0] > maxs + margin))

    phi = _poly2_basis(x, head.interaction_pairs)
    beta = np.asarray(head.poly_weights, dtype=np.float64)
    trend = float((phi @ beta)[0])

    if len(head.gp_train_x) > 0:
        X_train = np.asarray(head.gp_train_x, dtype=np.float64)
        ls = np.asarray(head.gp_length_scales, dtype=np.float64)
        alpha_vec = np.asarray(head.gp_alpha, dtype=np.float64)
        k_star = _matern52_kernel(x, X_train, ls, head.gp_signal_variance)
        gp_mean = float((k_star @ alpha_vec)[0])
        K_train = _matern52_kernel(X_train, X_train, ls, head.gp_signal_variance) + head.gp_noise_variance * np.eye(
            len(X_train)
        )
        try:
            v = np.linalg.solve(K_train, k_star.T)
            post_var = max(0.0, float(head.gp_signal_variance - (k_star @ v)[0, 0]))
        except np.linalg.LinAlgError:
            post_var = head.gp_signal_variance
        gp_std = math.sqrt(post_var)
    else:
        gp_mean = 0.0
        gp_std = 0.0

    pred_mean = trend + gp_mean
    radius = max(head.conformal_radius, 0.5 * head.conformal_radius + gp_std)
    return float(pred_mean), float(radius), is_ood


def predict_metric_for_parameters(
    surrogate: LearnedParameterSurrogate,
    metric_id: str,
    parameters: Mapping[str, float],
) -> tuple[float, float, bool]:
    """Predict (mean, uncertainty_radius, is_ood) for a full 30+ parameter dict."""
    if metric_id not in surrogate.metric_heads:
        raise KeyError(f"Metric {metric_id!r} is not modeled in surrogate")
    head = surrogate.metric_heads[metric_id]
    param_map = {p.parameter_id: p for p in surrogate.registry.parameters}
    derived_map = {d.feature_id: d for d in surrogate.registry.derived_features}

    kin_ctx: dict[str, float] = {}
    if head.modeling_mode == "multi-fidelity-residual-fusion":
        for k_id, k_head in surrogate.kinematic_bridge_heads.items():
            k_vec = [
                _extract_feature_value(fid, parameters, param_map, derived_map)
                for fid in k_head.active_feature_ids
            ]
            k_mean, _, _ = predict_head(k_head, k_vec)
            kin_ctx[f"kin.{k_id}"] = k_mean

    x_vec = [
        _extract_feature_value(fid, parameters, param_map, derived_map, kin_ctx)
        for fid in head.active_feature_ids
    ]
    val, radius, is_ood = predict_head(head, x_vec)
    if head.modeling_mode == "multi-fidelity-residual-fusion" and head.base_metric_id:
        base_val, base_rad, base_ood = predict_metric_for_parameters(surrogate, head.base_metric_id, parameters)
        return max(0.0, base_val + val), math.hypot(base_rad, radius), (is_ood or base_ood)
    return max(0.0, val), radius, is_ood


def _interaction_note(param_a: str, param_b: str, weight: float, metric_id: str) -> str:
    direction = "协同放大" if weight > 0 else "相互制约/抵消"
    return f"{param_a} 与 {param_b} 在 {metric_id} 上存在显著二阶耦合（{direction}，系数 {weight:+.4g}）"


def _fit_single_head(
    metric_id: str,
    unit: str,
    y_values: np.ndarray,
    exports_params: Sequence[Mapping[str, float]],
    registry: CncParameterRegistry,
    *,
    has_controller_traces: bool,
    max_active: int,
    modeling_mode: Literal["single-fidelity-surrogate", "multi-fidelity-residual-fusion"] = "single-fidelity-surrogate",
    base_metric_id: str | None = None,
    extra_kinematic_columns: dict[str, np.ndarray] | None = None,
) -> MetricSurrogateHead:
    param_map = {p.parameter_id: p for p in registry.parameters}
    derived_map = {d.feature_id: d for d in registry.derived_features}
    mask = causal_mask_for_metric(registry, metric_id, has_controller_traces=has_controller_traces)

    candidate_ids: list[str] = []
    for p in registry.parameters:
        if mask.get(p.parameter_id, False):
            if modeling_mode == "multi-fidelity-residual-fusion" and p.group == "G1_GeometryLookahead":
                # In multi-fidelity residual mode, G1 geometry effects are captured via base offline prediction + kinematic bridge
                continue
            candidate_ids.append(p.parameter_id)
    for d in registry.derived_features:
        if mask.get(d.feature_id, False):
            candidate_ids.append(d.feature_id)

    n_samples = len(y_values)
    X_cand = np.zeros((n_samples, len(candidate_ids)), dtype=np.float64)
    for i, p_dict in enumerate(exports_params):
        for j, fid in enumerate(candidate_ids):
            X_cand[i, j] = _extract_feature_value(fid, p_dict, param_map, derived_map)

    # Stage 1: ElasticNet main-effect screening (linear + quadratic) + Spearman rank correlation
    X_main = np.hstack([X_cand, X_cand * X_cand])
    _, w_main = _elastic_net_fit(X_main, y_values, l1_ratio=0.65, alpha=0.025)
    d_cand = len(candidate_ids)
    w_lin = w_main[:d_cand]
    w_quad = w_main[d_cand:]

    raw_scores: dict[str, float] = {}
    slopes: dict[str, float] = {}
    curvatures: dict[str, float] = {}
    rank_corrs: dict[str, float] = {}

    y_std = max(float(np.std(y_values)), 1e-9)
    for j, fid in enumerate(candidate_ids):
        col = X_cand[:, j]
        col_std = float(np.std(col))
        if col_std < 1e-8:
            raw_scores[fid] = 0.0
            slopes[fid] = 0.0
            curvatures[fid] = 0.0
            rank_corrs[fid] = 0.0
            continue
        rho = _spearman_corr(col, y_values)
        lin_effect = abs(float(w_lin[j])) * col_std / y_std
        quad_effect = abs(float(w_quad[j])) * float(np.std(col * col)) / y_std
        score = 0.65 * (lin_effect + 0.75 * quad_effect) + 0.35 * abs(rho)
        raw_scores[fid] = float(score)
        slopes[fid] = float(w_lin[j])
        curvatures[fid] = float(w_quad[j])
        rank_corrs[fid] = float(rho)

    total_score = sum(raw_scores.values()) or 1.0
    ranked_cands = sorted(candidate_ids, key=lambda fid: raw_scores[fid], reverse=True)

    active_param_ids: list[str] = []
    cum_ratio = 0.0
    for fid in ranked_cands:
        ratio = raw_scores[fid] / total_score
        if len(active_param_ids) < max_active and (len(active_param_ids) < 2 or (ratio >= 0.04 and cum_ratio < 0.92)):
            active_param_ids.append(fid)
            cum_ratio += ratio

    if not active_param_ids:
        active_param_ids = ranked_cands[: min(3, len(ranked_cands))]

    # Build sensitivity list across all 32 registry parameters
    sensitivities: list[ParameterSensitivityItem] = []
    active_set = set(active_param_ids)
    for p in registry.parameters:
        pid = p.parameter_id
        if not mask.get(pid, False) or pid not in raw_scores:
            sensitivities.append(
                ParameterSensitivityItem(
                    parameterId=pid,
                    displayName=p.display_name,
                    group=p.group,
                    status="CausalMasked" if not mask.get(pid, False) else "Inert",
                    contributionRatio=0.0,
                    direction="neutral",
                    linearSlope=0.0,
                    quadraticCurvature=0.0,
                    rankCorrelation=0.0,
                )
            )
            continue
        c_ratio = round(float(raw_scores[pid] / total_score), 6)
        slp = slopes[pid]
        crv = curvatures[pid]
        rc = rank_corrs[pid]
        if pid not in active_set or c_ratio < 0.02:
            direction: Literal["positive", "negative", "nonlinear", "neutral"] = "neutral"
        elif abs(crv) > 1.5 * abs(slp) and abs(rc) < 0.25:
            direction = "nonlinear"
        elif slp > 0 or (abs(slp) <= 1e-9 and rc > 0):
            direction = "positive"
        else:
            direction = "negative"
        sensitivities.append(
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
    sensitivities.sort(key=lambda item: (item.status == "Active", item.contribution_ratio), reverse=True)

    # Stage 2: Active subspace design matrix (include kinematic bridge features if multi-fidelity)
    active_feature_ids = list(active_param_ids)
    kin_cols_list: list[np.ndarray] = []
    if extra_kinematic_columns:
        for k_name, k_arr in extra_kinematic_columns.items():
            active_feature_ids.append(f"kin.{k_name}")
            kin_cols_list.append(k_arr.reshape(-1, 1))

    X_act_params = np.column_stack([X_cand[:, candidate_ids.index(fid)] for fid in active_param_ids])
    X_act = np.hstack([X_act_params] + kin_cols_list) if kin_cols_list else X_act_params
    k_dim = X_act.shape[1]

    interaction_pairs = [(i, j) for i in range(len(active_param_ids)) for j in range(i + 1, len(active_param_ids))]
    Phi2 = _poly2_basis(X_act, interaction_pairs)
    reg_diag = np.full(Phi2.shape[1], 0.05, dtype=np.float64)
    reg_diag[0] = 1e-8
    beta = np.linalg.solve(Phi2.T @ Phi2 + np.diag(reg_diag), Phi2.T @ y_values)

    trend_pred = Phi2 @ beta
    trend_res = y_values - trend_pred

    # ARD length scales inversely weighted by importance
    length_scales = np.ones(k_dim, dtype=np.float64)
    for idx_f, fid in enumerate(active_feature_ids):
        imp = raw_scores.get(fid, 0.15) / total_score
        length_scales[idx_f] = float(np.clip(0.85 / math.sqrt(max(imp, 0.04)), 0.45, 3.0))

    signal_var = max(float(np.var(trend_res)), 1e-8 * (y_std ** 2))
    noise_var = max(0.08 * signal_var, 1e-10)
    K_mat = _matern52_kernel(X_act, X_act, length_scales, signal_var) + noise_var * np.eye(n_samples)
    gp_alpha = np.linalg.solve(K_mat, trend_res)

    # Leave-One-Out / Split Conformal residual calibration
    loo_errors: list[float] = []
    for i in range(n_samples):
        mask_idx = [idx for idx in range(n_samples) if idx != i]
        Phi_tr = Phi2[mask_idx]
        y_tr = y_values[mask_idx]
        try:
            beta_i = np.linalg.solve(Phi_tr.T @ Phi_tr + np.diag(reg_diag), Phi_tr.T @ y_tr)
            res_tr = y_tr - Phi_tr @ beta_i
            K_tr = _matern52_kernel(X_act[mask_idx], X_act[mask_idx], length_scales, signal_var) + noise_var * np.eye(
                len(mask_idx)
            )
            alpha_i = np.linalg.solve(K_tr, res_tr)
            k_s = _matern52_kernel(X_act[i : i + 1], X_act[mask_idx], length_scales, signal_var)
            pred_i = float((Phi2[i : i + 1] @ beta_i)[0] + (k_s @ alpha_i)[0])
        except np.linalg.LinAlgError:
            pred_i = float(trend_pred[i])
        loo_errors.append(abs(float(y_values[i]) - pred_i))

    sorted_abs = sorted(loo_errors)
    rank_idx = min(len(sorted_abs) - 1, max(0, math.ceil((len(sorted_abs) + 1) * (1.0 - CONFORMAL_ALPHA)) - 1))
    conformal_radius = float(sorted_abs[rank_idx]) if sorted_abs else 0.0

    full_pred = trend_pred + (_matern52_kernel(X_act, X_act, length_scales, signal_var) @ gp_alpha)
    train_rmse = float(math.sqrt(np.mean((y_values - full_pred) ** 2)))
    cv_rmse = float(math.sqrt(np.mean(np.square(loo_errors)))) if loo_errors else train_rmse
    ss_tot = float(np.sum((y_values - np.mean(y_values)) ** 2))
    ss_res = float(np.sum((y_values - full_pred) ** 2))
    r2 = float(max(0.0, 1.0 - ss_res / ss_tot)) if ss_tot > 1e-12 else 1.0

    envelope = ParameterFeatureEnvelope(
        featureIds=tuple(active_feature_ids),
        minimums=tuple(round(float(np.min(X_act[:, j])), 6) for j in range(k_dim)),
        maximums=tuple(round(float(np.max(X_act[:, j])), 6) for j in range(k_dim)),
        marginFraction=OOD_MARGIN_FRACTION,
    )

    # Extract top pairwise interactions
    interactions: list[PairwiseParameterInteraction] = []
    offset_inter = 1 + 2 * k_dim
    inter_weights = [abs(float(beta[offset_inter + idx])) for idx in range(len(interaction_pairs))]
    max_inter = max(inter_weights, default=0.0) or 1.0
    for idx_pair, (i_a, i_b) in enumerate(interaction_pairs):
        w_val = float(beta[offset_inter + idx_pair])
        if abs(w_val) < 1e-9:
            continue
        pa, pb = active_feature_ids[i_a], active_feature_ids[i_b]
        interactions.append(
            PairwiseParameterInteraction(
                parameterA=pa,
                parameterB=pb,
                interactionWeight=round(w_val, 8),
                relativeStrength=round(abs(w_val) / max_inter, 4),
                engineeringNote=_interaction_note(pa, pb, w_val, metric_id),
            )
        )
    interactions.sort(key=lambda item: abs(item.interaction_weight), reverse=True)
    interactions = interactions[:5]

    provisional_head = MetricSurrogateHead(
        metricId=metric_id,
        unit=unit,
        modelingMode=modeling_mode,
        baseMetricId=base_metric_id,
        activeFeatureIds=tuple(active_feature_ids),
        interactionPairs=tuple(interaction_pairs),
        polyWeights=tuple(round(float(v), 12) for v in beta),
        gpLengthScales=tuple(round(float(v), 8) for v in length_scales),
        gpTrainX=tuple(tuple(round(float(v), 8) for v in row) for row in X_act),
        gpAlpha=tuple(round(float(v), 12) for v in gp_alpha),
        gpSignalVariance=round(signal_var, 12),
        gpNoiseVariance=round(noise_var, 12),
        conformalRadius=round(conformal_radius, 8),
        trainRmse=round(train_rmse, 8),
        cvRmse=round(cv_rmse, 8),
        r2Score=round(r2, 6),
        envelope=envelope,
        sensitivities=tuple(sensitivities),
        interactions=tuple(interactions),
        marginalKnees=(),
    )

    # Compute 1D Marginal Response & Knee-Point for each active parameter in param_map
    baseline_vec = np.mean(X_act, axis=0)
    knees: list[ParameterMarginalKnee] = []
    grid_norm = np.linspace(-1.0, 1.0, 11)
    for idx_p, fid in enumerate(active_param_ids):
        if fid not in param_map:
            continue
        p_def = param_map[fid]
        pts: list[MarginalCurvePoint] = []
        preds: list[float] = []
        raw_vals: list[float] = []
        for g_val in grid_norm:
            probe = baseline_vec.copy()
            probe[idx_p] = float(g_val)
            pm, pr, _ = predict_head(provisional_head, probe)
            r_val = denormalize_parameter_value(p_def, float(g_val))
            raw_vals.append(r_val)
            preds.append(pm)
            pts.append(
                MarginalCurvePoint(
                    parameterValue=r_val,
                    predictedMean=round(pm, 6),
                    uncertaintyRadius=round(pr, 6),
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
                parameterId=fid,
                displayName=p_def.display_name,
                unit=p_def.unit,
                kneeValue=knee_val,
                minPrediction=round(float(np.min(arr_p)), 6),
                maxPrediction=round(float(np.max(arr_p)), 6),
                curve=tuple(pts),
                tradeoffSummary=(
                    f"{p_def.display_name} ({fid}) 在 {knee_val:g} {p_def.unit} 附近出现边际收益拐点 "
                    f"（{metric_id} 响应范围 {np.min(arr_p):.4g} ~ {np.max(arr_p):.4g} {unit}）"
                ),
            )
        )

    return provisional_head.model_copy(update={"marginal_knees": tuple(knees)})


def learn_parameter_surrogate(
    request_or_case: ParameterLearningRequest | CncBenchmarkCase | Mapping[str, Any],
    exports: Sequence[CncAlgorithmExport | Mapping[str, Any]] | None = None,
    *,
    registry: CncParameterRegistry | None = None,
    target_metrics: Sequence[str] = DEFAULT_TARGET_METRICS,
    max_active_parameters_per_metric: int = 6,
) -> LearnedParameterSurrogate:
    """Train the two-stage parameter surrogate model and generate attribution reports."""
    if exports is None:
        req = (
            request_or_case
            if isinstance(request_or_case, ParameterLearningRequest)
            else ParameterLearningRequest.model_validate(request_or_case)
        )
    else:
        resolved_case = (
            request_or_case
            if isinstance(request_or_case, CncBenchmarkCase)
            else CncBenchmarkCase.model_validate(request_or_case)
        )
        resolved_exports = tuple(
            item if isinstance(item, CncAlgorithmExport) else CncAlgorithmExport.model_validate(item)
            for item in exports
        )
        req = ParameterLearningRequest(
            case=resolved_case,
            registry=registry,
            exports=resolved_exports,
            targetMetrics=tuple(target_metrics),
            maxActiveParametersPerMetric=max_active_parameters_per_metric,
        )

    reg = req.registry or default_cnc_parameter_registry()
    default_params = default_parameter_values(reg)

    reports: list[CncQualityReport] = []
    for exp in req.exports:
        if not exp.parameters:
            raise ValueError("All exports supplied to learn_parameter_surrogate must include parameters")
        reports.append(evaluate_cnc_export(req.case, exp))

    offline_reports = [r for r in reports if r.servo_metrics is None]
    ctrl_reports = [r for r in reports if r.servo_metrics is not None]
    total_slices = sum(len(r.geometry_slices) for r in reports)
    all_params = [{**default_params, **(r.parameters or {})} for r in reports]
    ctrl_params = [{**default_params, **(r.parameters or {})} for r in ctrl_reports]

    # Fit kinematic bridge heads on all reports for multi-fidelity transfer
    kinematic_bridge_heads: dict[str, MetricSurrogateHead] = {}
    for k_feat in KINEMATIC_BRIDGE_FEATURES:
        y_kin = np.asarray([r.kinematic_summary.get(k_feat, 0.0) for r in reports], dtype=np.float64)
        if float(np.std(y_kin)) > 1e-10:
            kinematic_bridge_heads[k_feat] = _fit_single_head(
                k_feat,
                "unit",
                y_kin,
                all_params,
                reg,
                has_controller_traces=False,
                max_active=4,
            )

    metric_heads: dict[str, MetricSurrogateHead] = {}
    for m_id in req.target_metrics:
        if m_id in PLANNING_METRIC_IDS:
            vals: list[float] = []
            valid_params: list[dict[str, float]] = []
            unit = "mm"
            for r, p_dict in zip(reports, all_params):
                m_obj = r.analysis.metrics.get(m_id)
                if m_obj is not None and m_obj.value is not None:
                    vals.append(float(m_obj.value))
                    valid_params.append(p_dict)
                    unit = m_obj.unit
            if len(vals) >= 4:
                metric_heads[m_id] = _fit_single_head(
                    m_id,
                    unit,
                    np.asarray(vals, dtype=np.float64),
                    valid_params,
                    reg,
                    has_controller_traces=False,
                    max_active=req.max_active_parameters_per_metric,
                )
        elif m_id in SERVO_METRIC_IDS and len(ctrl_reports) >= 4:
            vals_ctrl: list[float] = []
            unit = "mm"
            for r in ctrl_reports:
                assert r.servo_metrics is not None
                m_obj = r.servo_metrics.get(m_id)
                if m_obj is not None and m_obj.value is not None:
                    vals_ctrl.append(float(m_obj.value))
                    unit = m_obj.unit
            if len(vals_ctrl) < 4:
                continue
            y_ctrl = np.asarray(vals_ctrl, dtype=np.float64)
            # Multi-fidelity residual fusion when offline runs also exist and m_id == actualPathDeviationMaxMm
            if (
                m_id == "actualPathDeviationMaxMm"
                and "sampledPathDeviationMaxMm" in metric_heads
                and len(offline_reports) >= 4
            ):
                base_head = metric_heads["sampledPathDeviationMaxMm"]
                param_map = {p.parameter_id: p for p in reg.parameters}
                derived_map = {d.feature_id: d for d in reg.derived_features}
                base_preds = np.asarray(
                    [
                        predict_head(
                            base_head,
                            [
                                _extract_feature_value(fid, p_dict, param_map, derived_map)
                                for fid in base_head.active_feature_ids
                            ],
                        )[0]
                        for p_dict in ctrl_params
                    ],
                    dtype=np.float64,
                )
                residual_y = y_ctrl - base_preds
                metric_heads[m_id] = _fit_single_head(
                    m_id,
                    unit,
                    residual_y,
                    ctrl_params,
                    reg,
                    has_controller_traces=True,
                    max_active=req.max_active_parameters_per_metric,
                    modeling_mode="multi-fidelity-residual-fusion",
                    base_metric_id="sampledPathDeviationMaxMm",
                    extra_kinematic_columns=None,
                )
            else:
                metric_heads[m_id] = _fit_single_head(
                    m_id,
                    unit,
                    y_ctrl,
                    ctrl_params,
                    reg,
                    has_controller_traces=True,
                    max_active=req.max_active_parameters_per_metric,
                )

    param_id_set = {p.parameter_id for p in reg.parameters}
    global_active: list[str] = []
    for head in metric_heads.values():
        for fid in head.active_feature_ids:
            if fid in param_id_set and fid not in global_active:
                global_active.append(fid)

    surrogate = LearnedParameterSurrogate(
        caseId=req.case.case_id,
        caseContentHash=benchmark_case_hash(req.case),
        registry=reg,
        offlineRunCount=len(offline_reports),
        controllerRunCount=len(ctrl_reports),
        totalSliceSampleCount=total_slices,
        globalActiveParameterIds=tuple(global_active),
        baselineParameters=default_params,
        metricHeads=metric_heads,
        kinematicBridgeHeads=kinematic_bridge_heads,
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
    """Render a concise engineering attribution report for 30+ CNC parameters."""
    lines = [
        f"案例 {surrogate.case_id} · 30+ 参数自动学习与敏感度归因报告",
        f"训练样本：离线规划 {surrogate.offline_run_count} 组 + 控制器实采 {surrogate.controller_run_count} 组（共提取 {surrogate.total_slice_sample_count} 个几何基元切片）",
        f"全局识别出的核心活跃参数（共 {len(surrogate.global_active_parameter_ids)}/{len(surrogate.registry.parameters)} 个）：{', '.join(surrogate.global_active_parameter_ids)}",
        "",
    ]
    for m_id, head in surrogate.metric_heads.items():
        lines.append(
            f"【指标 {m_id} ({head.unit})】模式={head.modeling_mode}, R²={head.r2_score:.3f}, "
            f"CV-RMSE={head.cv_rmse:.4g}, Conformal区间=±{head.conformal_radius:.4g}"
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
            top_i = head.interactions[0]
            lines.append(f"  * 主导耦合项：{top_i.engineering_note}")
        if head.marginal_knees:
            top_k = head.marginal_knees[0]
            lines.append(f"  * 边际收益拐点：{top_k.tradeoff_summary}")
        lines.append("")
    return "\n".join(lines)
