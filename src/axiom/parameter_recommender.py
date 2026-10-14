"""Constrained Multi-Objective CNC Parameter Recommender & Active DoE Engine.

Operates on a LearnedParameterSurrogate to provide:
1. Top-K Sparse Delta Recommendation (only modifying <= K_max most impactful parameters from baseline,
   keeping the remaining 25+ parameters untouched for safe field verification).
2. Conservative Safety & Epistemic Gate (FeatureEnvelope OOD rejection + Split Conformal upper bound
   enforcement: mean + kappa * radius <= limit).
3. Weight-free Pareto Front extraction across (durationSeconds, contourErrorMm, discreteJerkRms) and
   automatic selection of 3 engineering presets:
   - EfficiencyOptimal (高速粗加工/节拍优先档)
   - PrecisionOptimal (高精精加工/轮廓优先档)
   - BalancedKneePoint (柔顺低冲击/均衡拐点档)
4. Active Learning Next-Experiment Suggestions (Constrained Expected Improvement + Uncertainty exploration).
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
    BenchmarkSample,
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncQualityReport,
    benchmark_case_hash,
    evaluate_cnc_export,
)
from .benchmark_standard import StandardCaseSettings, standard_case
from .models import AxiomModel
from .parameter_learner import (
    LearnedParameterSurrogate,
    learn_parameter_surrogate,
    predict_metric_for_parameters,
)
from .parameter_space import (
    CncParameterRegistry,
    ParameterGroup,
    SourceKind,
    default_cnc_parameter_registry,
    default_parameter_values,
    denormalize_parameter_value,
    generate_parameter_doe,
    normalize_parameter_value,
)

PresetRole = Literal["EfficiencyOptimal", "PrecisionOptimal", "BalancedKneePoint"]


def _canonical_hash(payload: AxiomModel | Mapping[str, Any]) -> str:
    data = (
        payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(payload, AxiomModel)
        else dict(payload)
    )
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ParameterDeltaItem(AxiomModel):
    parameter_id: str = Field(alias="parameterId")
    display_name: str = Field(alias="displayName")
    group: ParameterGroup
    unit: str
    baseline_value: float = Field(alias="baselineValue")
    recommended_value: float = Field(alias="recommendedValue")
    delta: float
    relative_change_pct: float = Field(alias="relativeChangePct")
    rationale: str


class PredictedMetricSummary(AxiomModel):
    metric_id: str = Field(alias="metricId")
    unit: str
    baseline_predicted: float = Field(alias="baselinePredicted")
    predicted_mean: float = Field(alias="predictedMean")
    uncertainty_radius: float = Field(alias="uncertaintyRadius")
    conservative_upper_bound: float = Field(alias="conservativeUpperBound")
    delta_from_baseline: float = Field(alias="deltaFromBaseline")
    relative_change_pct: float = Field(alias="relativeChangePct")
    hard_limit: float | None = Field(default=None, alias="hardLimit")
    within_conservative_limit: bool = Field(alias="withinConservativeLimit")


class ParameterRecommendationCandidate(AxiomModel):
    candidate_id: str = Field(alias="candidateId")
    preset_role: PresetRole | None = Field(default=None, alias="presetRole")
    preset_title: str | None = Field(default=None, alias="presetTitle")
    changed_parameter_count: int = Field(alias="changedParameterCount")
    changed_parameters: tuple[ParameterDeltaItem, ...] = Field(alias="changedParameters")
    full_parameters: dict[str, float] = Field(alias="fullParameters")
    predicted_metrics: dict[str, PredictedMetricSummary] = Field(alias="predictedMetrics")
    in_domain: bool = Field(alias="inDomain")
    hard_constraints_satisfied: bool = Field(alias="hardConstraintsSatisfied")
    pareto_optimal: bool = Field(alias="paretoOptimal")
    permission_level: Literal["OfflineAdvisory"] = Field(default="OfflineAdvisory", alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(default=False, alias="deviceWriteAllowed")
    tradeoff_explanation: str = Field(alias="tradeoffExplanation")


class ActiveExperimentSuggestion(AxiomModel):
    suggestion_id: str = Field(alias="suggestionId")
    target_source: SourceKind = Field(alias="targetSource")
    changed_parameter_ids: tuple[str, ...] = Field(alias="changedParameterIds")
    parameters: dict[str, float]
    acquisition_score: float = Field(alias="acquisitionScore")
    uncertainty_score: float = Field(alias="uncertaintyScore")
    rationale: str


class ParameterRecommendationRequest(AxiomModel):
    baseline_parameters: dict[str, float] | None = Field(default=None, alias="baselineParameters")
    locked_parameter_ids: tuple[str, ...] = Field(default=(), alias="lockedParameterIds")
    max_changed_parameters: int = Field(default=4, ge=1, le=12, alias="maxChangedParameters")
    maximum_path_deviation_mm: float | None = Field(default=0.035, ge=0.0, alias="maximumPathDeviationMm")
    maximum_actual_path_deviation_mm: float | None = Field(default=0.045, ge=0.0, alias="maximumActualPathDeviationMm")
    maximum_following_error_mm: float | None = Field(default=0.030, ge=0.0, alias="maximumFollowingErrorMm")
    maximum_jerk_rms_mm_s3: float | None = Field(default=None, ge=0.0, alias="maximumJerkRmsMmS3")
    maximum_duration_seconds: float | None = Field(default=None, ge=0.0, alias="maximumDurationSeconds")
    safety_kappa: float = Field(default=1.0, ge=0.0, le=3.0, alias="safetyKappa")
    candidate_pool_size: int = Field(default=240, ge=40, le=2000, alias="candidatePoolSize")
    seed: int = 42


class ParameterRecommendationReport(AxiomModel):
    schema_id: Literal["axiom.cnc-parameter-recommendation-report@1"] = Field(
        default="axiom.cnc-parameter-recommendation-report@1", alias="schemaId"
    )
    case_id: str = Field(alias="caseId")
    surrogate_model_hash: str = Field(alias="surrogateModelHash")
    primary_accuracy_metric_id: str = Field(alias="primaryAccuracyMetricId")
    max_changed_parameters: int = Field(alias="maxChangedParameters")
    evaluated_candidate_count: int = Field(alias="evaluatedCandidateCount")
    feasible_candidate_count: int = Field(alias="feasibleCandidateCount")
    pareto_candidate_count: int = Field(alias="paretoCandidateCount")
    presets: tuple[ParameterRecommendationCandidate, ...]
    pareto_front: tuple[ParameterRecommendationCandidate, ...] = Field(alias="paretoFront")
    active_doe_suggestions: tuple[ActiveExperimentSuggestion, ...] = Field(alias="activeDoeSuggestions")
    permission_level: Literal["OfflineAdvisory"] = Field(default="OfflineAdvisory", alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(default=False, alias="deviceWriteAllowed")
    report_content_hash: str = Field(alias="reportContentHash")


class CncParameterClosedLoopDemo(AxiomModel):
    schema_id: Literal["axiom.cnc-parameter-closed-loop-demo@1"] = Field(
        default="axiom.cnc-parameter-closed-loop-demo@1", alias="schemaId"
    )
    case: CncBenchmarkCase
    sample_quality_report: CncQualityReport = Field(alias="sampleQualityReport")
    surrogate: LearnedParameterSurrogate
    recommendation_report: ParameterRecommendationReport = Field(alias="recommendationReport")


def _dominates(obj_a: tuple[float, float, float], obj_b: tuple[float, float, float]) -> bool:
    return all(a <= b for a, b in zip(obj_a, obj_b)) and any(a < b for a, b in zip(obj_a, obj_b))


def recommend_parameters(
    surrogate: LearnedParameterSurrogate | Mapping[str, Any],
    request: ParameterRecommendationRequest | Mapping[str, Any] | None = None,
) -> ParameterRecommendationReport:
    """Search the active parameter subspace under sparse delta and conservative hard constraints."""
    model = (
        surrogate
        if isinstance(surrogate, LearnedParameterSurrogate)
        else LearnedParameterSurrogate.model_validate(surrogate)
    )
    req = (
        ParameterRecommendationRequest()
        if request is None
        else request
        if isinstance(request, ParameterRecommendationRequest)
        else ParameterRecommendationRequest.model_validate(request)
    )

    reg = model.registry
    param_map = {p.parameter_id: p for p in reg.parameters}
    base_params = dict(model.baseline_parameters)
    if req.baseline_parameters:
        for k, v in req.baseline_parameters.items():
            if k in param_map:
                base_params[k] = float(v)

    primary_acc_metric = (
        "actualPathDeviationMaxMm"
        if "actualPathDeviationMaxMm" in model.metric_heads
        else "sampledPathDeviationMaxMm"
    )
    objective_metrics = ("durationSeconds", primary_acc_metric, "discreteJerkRms")
    available_metrics = tuple(m for m in model.metric_heads if m in {
        "durationSeconds",
        "sampledPathDeviationMaxMm",
        "discreteJerkRms",
        "cornerSpeedMinMmS",
        "followingErrorMaxMm",
        "actualPathDeviationMaxMm",
    })

    # Rank active parameters by aggregate importance across key metrics
    agg_importance: dict[str, float] = {p.parameter_id: 0.0 for p in reg.parameters}
    for m_id in available_metrics:
        head = model.metric_heads[m_id]
        w_m = 1.5 if m_id in objective_metrics else 0.8
        for s in head.sensitivities:
            if s.status == "Active" and s.parameter_id in agg_importance:
                agg_importance[s.parameter_id] += w_m * s.contribution_ratio

    locked_set = set(req.locked_parameter_ids)
    tunable_ids = [
        pid
        for pid, score in sorted(agg_importance.items(), key=lambda kv: kv[1], reverse=True)
        if pid not in locked_set and score > 0
    ]
    if not tunable_ids:
        tunable_ids = [p.parameter_id for p in reg.parameters if p.parameter_id not in locked_set][:6]
    top_pool = tunable_ids[: min(10, len(tunable_ids))]
    k_max = min(req.max_changed_parameters, len(top_pool))

    # Baseline predictions
    base_preds: dict[str, tuple[float, float, bool]] = {
        m_id: predict_metric_for_parameters(model, m_id, base_params)
        for m_id in available_metrics
    }

    limits_map: dict[str, float | None] = {
        "sampledPathDeviationMaxMm": req.maximum_path_deviation_mm,
        "actualPathDeviationMaxMm": req.maximum_actual_path_deviation_mm,
        "followingErrorMaxMm": req.maximum_following_error_mm,
        "discreteJerkRms": req.maximum_jerk_rms_mm_s3,
        "durationSeconds": req.maximum_duration_seconds,
    }

    rng = np.random.default_rng(req.seed)
    candidate_dicts: list[dict[str, float]] = [dict(base_params)]

    # 1. Single-parameter and pair grid probes around knee points and bounds
    for pid in top_pool[: min(6, len(top_pool))]:
        p_def = param_map[pid]
        for norm_v in (-0.75, -0.40, 0.0, 0.40, 0.75):
            cand = dict(base_params)
            cand[pid] = denormalize_parameter_value(p_def, norm_v)
            candidate_dicts.append(cand)

    # 2. Sparse K_max subset LHS + trust-region perturbations
    while len(candidate_dicts) < req.candidate_pool_size:
        n_change = int(rng.integers(1, k_max + 1))
        probs = np.asarray([agg_importance.get(pid, 0.1) + 0.05 for pid in top_pool], dtype=np.float64)
        probs /= np.sum(probs)
        chosen_ids = rng.choice(top_pool, size=min(n_change, len(top_pool)), replace=False, p=probs)
        cand = dict(base_params)
        for pid in chosen_ids:
            p_def = param_map[pid]
            # Sample inside [-0.85, 0.85] to stay well within trusted training envelope
            norm_v = float(rng.uniform(-0.85, 0.85))
            cand[str(pid)] = denormalize_parameter_value(p_def, norm_v)
        candidate_dicts.append(cand)

    evaluated_candidates: list[ParameterRecommendationCandidate] = []
    raw_uncertainty_records: list[tuple[float, float, dict[str, float], list[str]]] = []

    for idx, cand_params in enumerate(candidate_dicts):
        changed_items: list[ParameterDeltaItem] = []
        changed_ids: list[str] = []
        for p in reg.parameters:
            pid = p.parameter_id
            b_val = float(base_params[pid])
            c_val = float(cand_params[pid])
            if abs(c_val - b_val) > 1e-9:
                changed_ids.append(pid)
                delta = c_val - b_val
                rel_pct = (delta / abs(b_val) * 100.0) if abs(b_val) > 1e-9 else 0.0
                changed_items.append(
                    ParameterDeltaItem(
                        parameterId=pid,
                        displayName=p.display_name,
                        group=p.group,
                        unit=p.unit,
                        baselineValue=round(b_val, 6),
                        recommendedValue=round(c_val, 6),
                        delta=round(delta, 6),
                        relativeChangePct=round(rel_pct, 2),
                        rationale=f"活跃度权重 {agg_importance.get(pid, 0.0):.1%}，在安全包络内调整以优化目标权衡",
                    )
                )

        if len(changed_items) > req.max_changed_parameters:
            continue

        pred_summaries: dict[str, PredictedMetricSummary] = {}
        all_in_domain = True
        all_limits_ok = True
        total_rel_unc = 0.0

        for m_id in available_metrics:
            head = model.metric_heads[m_id]
            mean_val, rad_val, is_ood = predict_metric_for_parameters(model, m_id, cand_params)
            if is_ood:
                all_in_domain = False
            b_mean = base_preds[m_id][0]
            upper_bound = mean_val + req.safety_kappa * rad_val
            lim = limits_map.get(m_id)
            within_lim = True if lim is None else (upper_bound <= lim)
            if not within_lim:
                all_limits_ok = False
            delta_m = mean_val - b_mean
            rel_m = (delta_m / abs(b_mean) * 100.0) if abs(b_mean) > 1e-9 else 0.0
            total_rel_unc += rad_val / max(abs(b_mean), 1e-6)
            pred_summaries[m_id] = PredictedMetricSummary(
                metricId=m_id,
                unit=head.unit,
                baselinePredicted=round(b_mean, 6),
                predictedMean=round(mean_val, 6),
                uncertaintyRadius=round(rad_val, 6),
                conservativeUpperBound=round(upper_bound, 6),
                deltaFromBaseline=round(delta_m, 6),
                relativeChangePct=round(rel_m, 2),
                hardLimit=lim,
                withinConservativeLimit=within_lim,
            )

        dur_imp = (
            (base_preds["durationSeconds"][0] - pred_summaries["durationSeconds"].predicted_mean)
            / max(base_preds["durationSeconds"][0], 1e-6)
            if "durationSeconds" in pred_summaries
            else 0.0
        )
        err_imp = (
            (base_preds[primary_acc_metric][0] - pred_summaries[primary_acc_metric].predicted_mean)
            / max(base_preds[primary_acc_metric][0], 1e-6)
            if primary_acc_metric in pred_summaries
            else 0.0
        )
        acq_score = float(0.5 * dur_imp + 0.5 * err_imp + 0.35 * total_rel_unc)
        if changed_ids:
            raw_uncertainty_records.append((acq_score, total_rel_unc, cand_params, changed_ids))

        hard_ok = all_in_domain and all_limits_ok
        evaluated_candidates.append(
            ParameterRecommendationCandidate(
                candidateId=f"rec.cand.{idx + 1:03d}",
                changedParameterCount=len(changed_items),
                changedParameters=tuple(changed_items),
                fullParameters=cand_params,
                predictedMetrics=pred_summaries,
                inDomain=all_in_domain,
                hardConstraintsSatisfied=hard_ok,
                paretoOptimal=False,
                tradeoffExplanation="",
            )
        )

    feasible = [c for c in evaluated_candidates if c.hard_constraints_satisfied]
    if not feasible:
        # Fallback to in-domain candidates if user limits were tighter than all samples
        feasible = [c for c in evaluated_candidates if c.in_domain] or evaluated_candidates[:5]

    def _obj_tuple(cand: ParameterRecommendationCandidate) -> tuple[float, float, float]:
        d_val = cand.predicted_metrics["durationSeconds"].predicted_mean if "durationSeconds" in cand.predicted_metrics else 0.0
        e_val = cand.predicted_metrics[primary_acc_metric].predicted_mean if primary_acc_metric in cand.predicted_metrics else 0.0
        j_val = cand.predicted_metrics["discreteJerkRms"].predicted_mean if "discreteJerkRms" in cand.predicted_metrics else 0.0
        return (d_val, e_val, j_val)

    pareto_front: list[ParameterRecommendationCandidate] = []
    for cand in feasible:
        obj_c = _obj_tuple(cand)
        if not any(_dominates(_obj_tuple(other), obj_c) for other in feasible if other.candidate_id != cand.candidate_id):
            pareto_front.append(cand.model_copy(update={"pareto_optimal": True}))

    pareto_front.sort(key=_obj_tuple)

    # Select 3 distinct representative engineering presets from Pareto front
    eff_cand = min(pareto_front, key=lambda c: _obj_tuple(c)[0])
    prec_cand = min(pareto_front, key=lambda c: _obj_tuple(c)[1])

    # Utopia distance for BalancedKneePoint (prefer distinct interior candidate when available)
    objs = np.asarray([_obj_tuple(c) for c in pareto_front], dtype=np.float64)
    mins = np.min(objs, axis=0)
    spans = np.maximum(np.max(objs, axis=0) - mins, 1e-9)
    norm_objs = (objs - mins) / spans
    utopia_dists = np.sqrt(1.0 * (norm_objs[:, 0] ** 2) + 1.0 * (norm_objs[:, 1] ** 2) + 1.35 * (norm_objs[:, 2] ** 2))
    order_indices = np.argsort(utopia_dists)
    bal_cand = pareto_front[int(order_indices[0])]
    for idx_c in order_indices:
        cand_c = pareto_front[int(idx_c)]
        if cand_c.candidate_id not in {eff_cand.candidate_id, prec_cand.candidate_id}:
            bal_cand = cand_c
            break

    def _format_preset(
        cand: ParameterRecommendationCandidate,
        role: PresetRole,
        title: str,
    ) -> ParameterRecommendationCandidate:
        d_pct = cand.predicted_metrics["durationSeconds"].relative_change_pct if "durationSeconds" in cand.predicted_metrics else 0.0
        e_pct = cand.predicted_metrics[primary_acc_metric].relative_change_pct if primary_acc_metric in cand.predicted_metrics else 0.0
        j_pct = cand.predicted_metrics["discreteJerkRms"].relative_change_pct if "discreteJerkRms" in cand.predicted_metrics else 0.0
        changed_names = ", ".join(f"{item.parameter_id}={item.recommended_value:g}{item.unit}" for item in cand.changed_parameters) or "保持基线不变"
        explanation = (
            f"【{title}】仅微调 {cand.changed_parameter_count} 个关键参数（{changed_names}），"
            f"其余 {len(reg.parameters) - cand.changed_parameter_count} 个参数保持基线不变："
            f"预计加工时间变化 {d_pct:+.1f}%，{primary_acc_metric} 变化 {e_pct:+.1f}%，RMS Jerk 变化 {j_pct:+.1f}%。"
        )
        return cand.model_copy(
            update={
                "preset_role": role,
                "preset_title": title,
                "tradeoff_explanation": explanation,
            }
        )

    presets = (
        _format_preset(eff_cand, "EfficiencyOptimal", "高速效率优先档（粗加工/节拍优先）"),
        _format_preset(prec_cand, "PrecisionOptimal", "高精轮廓优先档（精加工/清根优先）"),
        _format_preset(bal_cand, "BalancedKneePoint", "柔顺均衡拐点档（表面质量/低冲击均衡）"),
    )

    # Select top 3 Active DoE suggestions with diverse parameter combinations
    raw_uncertainty_records.sort(key=lambda item: item[0], reverse=True)
    doe_suggestions: list[ActiveExperimentSuggestion] = []
    seen_sets: list[set[str]] = []
    target_src: SourceKind = "controller-trace" if model.controller_run_count > 0 else "algorithm-export"
    for acq, unc, c_params, c_ids in raw_uncertainty_records:
        id_set = set(c_ids)
        if any(len(id_set & prev) == len(id_set) and len(id_set) == len(prev) for prev in seen_sets):
            continue
        seen_sets.append(id_set)
        sug_idx = len(doe_suggestions) + 1
        doe_suggestions.append(
            ActiveExperimentSuggestion(
                suggestionId=f"active-doe.{sug_idx:02d}",
                targetSource=target_src,
                changedParameterIds=tuple(c_ids),
                parameters=c_params,
                acquisitionScore=round(acq, 4),
                uncertaintyScore=round(unc, 4),
                rationale=(
                    f"主动补采建议 #{sug_idx}：针对参数 ({', '.join(c_ids)}) 的高潜力折中区进行采样，"
                    f"综合期望改进与不确定性得分 {acq:.3f}，可显著收紧该区域的 Conformal 预测半径。"
                ),
            )
        )
        if len(doe_suggestions) >= 3:
            break

    report = ParameterRecommendationReport(
        caseId=model.case_id,
        surrogateModelHash=model.model_content_hash,
        primaryAccuracyMetricId=primary_acc_metric,
        maxChangedParameters=req.max_changed_parameters,
        evaluatedCandidateCount=len(evaluated_candidates),
        feasibleCandidateCount=len(feasible),
        paretoCandidateCount=len(pareto_front),
        presets=presets,
        paretoFront=tuple(pareto_front[:15]),
        activeDoeSuggestions=tuple(doe_suggestions),
        reportContentHash="",
    )
    content = report.model_dump(mode="json", by_alias=True, exclude_none=True)
    content.pop("reportContentHash")
    return report.model_copy(update={"report_content_hash": _canonical_hash(content)})


def simulate_parametric_cnc_export(
    case: CncBenchmarkCase,
    parameters: Mapping[str, float],
    *,
    source_kind: SourceKind = "algorithm-export",
    registry: CncParameterRegistry | None = None,
    algorithm_version: str = "parametric-sim-v1",
) -> CncAlgorithmExport:
    """Synthesize a physically grounded 3D CNC trajectory export from a 32-parameter dict.

    This deterministic physics-inspired generator models how G1 (corner tolerance, lookahead),
    G2 (tangential acc/jerk, centripetal acc, FIR filter time constant), and G3 (servo Kp,
    velocity/acceleration feedforward, friction compensation) govern the sampled command
    stream and actual servo feedback stream.
    """
    reg = registry or default_cnc_parameter_registry()
    p = {**default_parameter_values(reg), **dict(parameters)}

    corner_tol = float(p["g1.corner_tolerance_mm"])
    small_tol = float(p["g1.small_seg_chord_tol_mm"])
    lookahead = float(p["g1.lookahead_block_count"])
    curv_clamp = float(p["g1.curvature_speed_clamp_factor"])
    feed_ovr = float(p["g2.path_max_feed_override"])
    tang_acc = float(p["g2.path_tangential_acc_mm_s2"])
    tang_jerk = float(p["g2.path_tangential_jerk_mm_s3"])
    cent_acc = float(p["g2.centripetal_acc_limit_mm_s2"])
    fir_ms = float(p["g2.fir_moving_avg_time_ms"])
    bell_shape = float(p["g2.bell_acc_shape_factor"])

    path = np.asarray(case.reference_path, dtype=float)
    segs = path[1:] - path[:-1]
    seg_lengths = np.linalg.norm(segs, axis=1)
    total_len = float(np.sum(seg_lengths))
    cum_len = np.concatenate([[0.0], np.cumsum(seg_lengths)])

    base_feed_mm_s = (case.programmed_feed_mm_min or 3000.0) / 60.0
    # Effective cruise speed governed by feed override, lookahead, and acceleration/jerk capability
    lookahead_factor = 0.82 + 0.18 * min(1.0, (lookahead - 20.0) / 250.0)
    corner_speed_factor = 0.55 + 0.42 * min(1.0, math.sqrt(corner_tol / 0.08) * (cent_acc / 4000.0) * curv_clamp)
    acc_factor = 0.75 + 0.25 * min(1.0, tang_acc / 8000.0)
    jerk_factor = 0.85 + 0.15 * min(1.0, tang_jerk / 400000.0)
    eff_speed = max(
        5.0,
        min(
            base_feed_mm_s * feed_ovr * lookahead_factor * acc_factor * jerk_factor,
            0.85 * min(lim.maximum_velocity_mm_s for lim in case.axis_limits),
        ),
    )

    # Total motion duration includes cruise time + S-curve ramp time + corner slowdown + FIR filter tail
    ramp_time = (eff_speed / max(tang_acc, 500.0)) * (1.25 + 0.35 * bell_shape) + (
        tang_acc / max(tang_jerk, 10000.0)
    )
    corner_penalty = 0.035 / max(corner_speed_factor, 0.25)
    total_duration = (total_len / eff_speed) + ramp_time + corner_penalty + (fir_ms * 0.001)
    period = case.sample_period_seconds
    n_samples = max(12, int(round(total_duration / period)) + 1)

    t_arr = np.arange(n_samples, dtype=np.float64) * period
    tau = np.linspace(0.0, 1.0, n_samples)
    # Smooth S-curve progress profile (quintic polynomial 10u^3 - 15u^4 + 6u^5)
    s_prog = (10.0 * (tau ** 3) - 15.0 * (tau ** 4) + 6.0 * (tau ** 5)) * total_len

    # Interpolate nominal points along piecewise linear reference path
    raw_pos = np.zeros((n_samples, 3), dtype=np.float64)
    for idx_s, s_val in enumerate(s_prog):
        seg_i = int(np.searchsorted(cum_len[1:], s_val, side="right"))
        seg_i = min(seg_i, len(seg_lengths) - 1)
        l_seg = max(float(seg_lengths[seg_i]), 1e-12)
        u_local = np.clip((s_val - cum_len[seg_i]) / l_seg, 0.0, 1.0)
        raw_pos[idx_s] = path[seg_i] + u_local * segs[seg_i]

    # Apply physically calibrated corner rounding + FIR smoothing so peak path deviation is in [0.003, 0.055] mm
    cmd_pos = raw_pos.copy()
    if n_samples > 10:
        weights = np.hanning(7)[1:-1]
        weights /= np.sum(weights)
        smoothed = np.empty_like(raw_pos)
        for axis in range(3):
            padded = np.pad(raw_pos[:, axis], (2, 2), mode="edge")
            smoothed[:, axis] = np.convolve(padded, weights, mode="valid")
        diff_vec = smoothed - raw_pos
        max_raw_dev = float(np.max(np.linalg.norm(diff_vec, axis=1)))
        target_dev_mm = (
            0.38 * corner_tol
            + 0.00035 * fir_ms
            + 0.22 * small_tol
            + 0.0025 * (feed_ovr ** 2)
        )
        if max_raw_dev > 1e-9:
            cmd_pos = raw_pos + diff_vec * (target_dev_mm / max_raw_dev)
        cmd_pos[0] = path[0]
        cmd_pos[-1] = path[-1]

    # Add subtle high-frequency interpolation ripple inversely proportional to FIR filter and bell shape
    ripple_amp = max(
        0.0,
        (1.0 - min(0.85, fir_ms / 48.0))
        * (tang_jerk / 800000.0)
        * 0.0006
        * (1.0 - 0.45 * bell_shape),
    )
    if ripple_amp > 0 and n_samples > 6:
        phase = np.linspace(0.0, 8.0 * math.pi, n_samples)
        envelope_sin = np.sin(np.pi * tau) ** 2
        cmd_pos[:, 0] += ripple_amp * np.sin(phase) * envelope_sin
        cmd_pos[:, 1] += ripple_amp * np.cos(phase) * envelope_sin
        cmd_pos[0] = path[0]
        cmd_pos[-1] = path[-1]

    actual_pos: np.ndarray | None = None
    if source_kind == "controller-trace":
        kp_vec = np.array([float(p["g3.servo_kp_x"]), float(p["g3.servo_kp_y"]), float(p["g3.servo_kp_z"])])
        vff_vec = np.array(
            [float(p["g3.vel_feedforward_x"]), float(p["g3.vel_feedforward_y"]), float(p["g3.vel_feedforward_z"])]
        )
        aff_vec = np.array([float(p["g3.acc_feedforward_x"]), float(p["g3.acc_feedforward_y"]), 0.70])
        fric_vec = np.array([float(p["g3.friction_comp_amp_x"]), float(p["g3.friction_comp_amp_y"]), 0.005])

        cmd_vel = np.gradient(cmd_pos, period, axis=0)
        cmd_acc = np.gradient(cmd_vel, period, axis=0)
        vel_lag = 0.035 * (1.02 - vff_vec[None, :]) * cmd_vel / np.maximum(kp_vec[None, :], 20.0)
        acc_lag = 0.08 * (1.0 - aff_vec[None, :]) * cmd_acc / np.maximum(kp_vec[None, :] ** 2, 400.0)
        kp_mismatch_mm = abs(float(kp_vec[0] - kp_vec[1])) * 0.00018
        mismatch_offset = np.zeros_like(cmd_pos)
        mismatch_offset[:, 0] = kp_mismatch_mm * np.sin(np.pi * tau)
        mismatch_offset[:, 1] = -kp_mismatch_mm * np.sin(np.pi * tau)
        uncomp_fric = 0.15 * np.maximum(0.0, 0.015 - fric_vec[None, :]) * np.tanh(cmd_acc / 2500.0)
        actual_pos = cmd_pos - vel_lag - acc_lag - uncomp_fric + mismatch_offset
        actual_pos[0] = cmd_pos[0]
        actual_pos[-1] = cmd_pos[-1]

    samples = tuple(
        BenchmarkSample(
            sampleIndex=i,
            t=round(float(t_arr[i]), 9),
            positionMm=(
                round(float(cmd_pos[i, 0]), 7),
                round(float(cmd_pos[i, 1]), 7),
                round(float(cmd_pos[i, 2]), 7),
            ),
            actualPositionMm=(
                (
                    round(float(actual_pos[i, 0]), 7),
                    round(float(actual_pos[i, 1]), 7),
                    round(float(actual_pos[i, 2]), 7),
                )
                if actual_pos is not None
                else None
            ),
        )
        for i in range(n_samples)
    )
    return CncAlgorithmExport(
        algorithmId="axiom.cnc-planner",
        algorithmVersion=algorithm_version,
        sourceKind=source_kind,
        caseContentHash=benchmark_case_hash(case),
        coordinateFrame=case.coordinate_frame,
        unit="mm",
        samplePeriodSeconds=case.sample_period_seconds,
        parameterRegistryId=reg.registry_id,
        parameters={k: round(float(v), 6) for k, v in p.items()},
        samples=samples,
    )


def build_cnc_parameter_closed_loop_demo(
    *,
    offline_count: int = 24,
    controller_count: int = 10,
    seed: int = 42,
) -> CncParameterClosedLoopDemo:
    """Build an end-to-end 32-parameter closed-loop demonstration on the V1 corner90 case."""
    reg = default_cnc_parameter_registry()
    case = standard_case("corner90", StandardCaseSettings(sample_period_seconds=0.005, maximum_path_deviation_mm=0.05))
    doe = generate_parameter_doe(reg, offline_count=offline_count, controller_count=controller_count, seed=seed)

    exports: list[CncAlgorithmExport] = []
    for sample in doe.offline_samples:
        exports.append(
            simulate_parametric_cnc_export(
                case,
                sample.parameters,
                source_kind="algorithm-export",
                registry=reg,
                algorithm_version=sample.sample_id,
            )
        )
    for sample in doe.controller_samples:
        exports.append(
            simulate_parametric_cnc_export(
                case,
                sample.parameters,
                source_kind="controller-trace",
                registry=reg,
                algorithm_version=sample.sample_id,
            )
        )

    sample_quality_report = evaluate_cnc_export(case, exports[-1])
    surrogate = learn_parameter_surrogate(case, exports, registry=reg)
    rec_report = recommend_parameters(
        surrogate,
        ParameterRecommendationRequest(
            maxChangedParameters=4,
            maximumPathDeviationMm=0.035,
            maximumActualPathDeviationMm=0.042,
            maximumFollowingErrorMm=0.025,
            seed=seed,
        ),
    )
    return CncParameterClosedLoopDemo(
        case=case,
        sampleQualityReport=sample_quality_report,
        surrogate=surrogate,
        recommendationReport=rec_report,
    )


def _pad(text: str, width: int, *, right: bool = False) -> str:
    shown = sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)
    fill = " " * max(width - shown, 1 if right else 0)
    return fill + text if right else text + fill


def render_recommendation_table(report: ParameterRecommendationReport) -> str:
    """Render a readable CLI table of the 3 Pareto presets and Active DoE suggestions."""
    lines = [
        f"案例 {report.case_id} · 受约束多目标参数推荐报告（Top-{report.max_changed_parameters} 稀疏微调）",
        f"评估候选：{report.evaluated_candidate_count} 组 | 满足保守硬约束：{report.feasible_candidate_count} 组 | Pareto 最优前沿：{report.pareto_candidate_count} 组",
        f"主精度目标：{report.primary_accuracy_metric_id} | 权限级别：{report.permission_level} (禁止自动写设备)",
        "",
    ]
    for preset in report.presets:
        lines.append(preset.tradeoff_explanation)
        if preset.changed_parameters:
            lines.append(
                "  "
                + _pad("调整参数ID", 32)
                + _pad("参数名称", 22)
                + _pad("基线值", 12, right=True)
                + _pad("推荐值", 12, right=True)
                + _pad("变化幅度", 12, right=True)
            )
            for item in preset.changed_parameters:
                lines.append(
                    "  "
                    + _pad(item.parameter_id, 32)
                    + _pad(item.display_name[:10], 22)
                    + _pad(f"{item.baseline_value:g}", 12, right=True)
                    + _pad(f"{item.recommended_value:g}", 12, right=True)
                    + _pad(f"{item.relative_change_pct:+.1f}%", 12, right=True)
                )
        lines.append("")

    if report.active_doe_suggestions:
        lines.append("下一批高价值主动补采参数建议（Active DoE）：")
        for sug in report.active_doe_suggestions:
            lines.append(f"  - [{sug.suggestion_id} / {sug.target_source}] {sug.rationale}")
    return "\n".join(lines) + "\n"
