"""Constrained multi-objective CNC parameter recommender (offline advisory only).

Operates on a `LearnedParameterSurrogate`:
1. Optional `target_case`: evaluates candidates on another toolpath through the grey-box
   backbone. Duration transfer has been checked on synthetic data only; contour-error
   transfer is unverified and every preset must be validated on the machine.
2. Top-K sparse deltas (<= K parameters changed) sampled inside the observed training
   envelope; feed override is capped at `maximumFeedOverride` (default 1.0).
3. Gates: in-envelope check plus `mean + kappa * radius <= limit`, where the radius is a
   leave-one-out residual quantile whose real-machine coverage is not yet verified.
4. Pareto front over (durationSeconds, contour error, discreteJerkRms) and up to three
   distinct presets; when nothing passes the gates no preset is emitted
   (`noFeasibleReason`).
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any, Literal, Mapping

import numpy as np
from pydantic import Field

from .benchmark import (
    CncAlgorithmExport,
    CncBenchmarkCase,
    CncQualityReport,
    evaluate_cnc_export,
)
from .benchmark_standard import StandardCaseSettings, standard_case, standard_cases
from .greybox_model import (
    evaluate_greybox_backbone,
    extract_case_geometry_profile,
    simulate_realistic_cnc_controller,
)
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
    denormalize_parameter_value,
    generate_parameter_doe,
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
    target_case: CncBenchmarkCase | None = Field(default=None, alias="targetCase")
    baseline_parameters: dict[str, float] | None = Field(default=None, alias="baselineParameters")
    locked_parameter_ids: tuple[str, ...] = Field(default=(), alias="lockedParameterIds")
    max_changed_parameters: int = Field(default=4, ge=1, le=12, alias="maxChangedParameters")
    maximum_path_deviation_mm: float | None = Field(default=0.035, ge=0.0, alias="maximumPathDeviationMm")
    maximum_actual_path_deviation_mm: float | None = Field(default=0.045, ge=0.0, alias="maximumActualPathDeviationMm")
    maximum_following_error_mm: float | None = Field(default=None, ge=0.0, alias="maximumFollowingErrorMm")
    maximum_jerk_rms_mm_s3: float | None = Field(default=None, ge=0.0, alias="maximumJerkRmsMmS3")
    maximum_duration_seconds: float | None = Field(default=None, ge=0.0, alias="maximumDurationSeconds")
    safety_kappa: float = Field(default=1.0, ge=0.0, le=3.0, alias="safetyKappa")
    candidate_pool_size: int = Field(default=280, ge=40, le=2000, alias="candidatePoolSize")
    # Recommendations never exceed the programmed feed unless the caller explicitly allows it.
    maximum_feed_override: float = Field(default=1.0, ge=0.05, le=2.0, alias="maximumFeedOverride")
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
    # Empty when no candidate satisfies the gates; see `noFeasibleReason`.
    presets: tuple[ParameterRecommendationCandidate, ...]
    pareto_front: tuple[ParameterRecommendationCandidate, ...] = Field(alias="paretoFront")
    active_doe_suggestions: tuple[ActiveExperimentSuggestion, ...] = Field(alias="activeDoeSuggestions")
    no_feasible_reason: str | None = Field(default=None, alias="noFeasibleReason")
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


def _target_geometry_leverage(
    model: LearnedParameterSurrogate,
    eval_case: CncBenchmarkCase | None,
    base_params: Mapping[str, float],
    objective_metrics: tuple[str, ...],
) -> dict[str, float]:
    """Rank tunable parameters on the *actual target toolpath geometry* using the Grey-Box physics kernel."""
    reg = model.registry
    scores: dict[str, float] = {p.parameter_id: 0.0 for p in reg.parameters}

    if eval_case is not None and model.greybox_constants is not None:
        prof = extract_case_geometry_profile(eval_case)
        base_gb = evaluate_greybox_backbone(prof, base_params, model.greybox_constants)
        for p in reg.parameters:
            pid = p.parameter_id
            p_lo = dict(base_params)
            p_hi = dict(base_params)
            p_lo[pid] = denormalize_parameter_value(p, -0.75)
            p_hi[pid] = denormalize_parameter_value(p, +0.75)
            gb_lo = evaluate_greybox_backbone(prof, p_lo, model.greybox_constants)
            gb_hi = evaluate_greybox_backbone(prof, p_hi, model.greybox_constants)
            rel_gain = 0.0
            for m_id in objective_metrics:
                denom = max(abs(base_gb.get(m_id, 0.0)), 1e-4)
                rel_gain += abs(gb_hi.get(m_id, 0.0) - gb_lo.get(m_id, 0.0)) / denom
            scores[pid] += 1.5 * rel_gain

    for m_id, head in model.metric_heads.items():
        w_m = 1.2 if m_id in objective_metrics else 0.6
        for s in head.sensitivities:
            if s.status == "Active" and s.parameter_id in scores:
                scores[s.parameter_id] += w_m * s.contribution_ratio
    return scores


def _parameter_sampling_bounds(model: LearnedParameterSurrogate) -> dict[str, tuple[float, float]]:
    """Normalized sampling range per parameter: the intersection of every metric head's
    observed feature envelope (plus margin) in which that parameter is a feature.

    Sampling outside it only produces out-of-domain candidates that the gates reject."""
    bounds: dict[str, tuple[float, float]] = {}
    for head in model.metric_heads.values():
        env = head.envelope
        for fid, lo, hi in zip(env.feature_ids, env.minimums, env.maximums):
            if fid not in {p.parameter_id for p in model.registry.parameters}:
                continue
            margin = env.margin_fraction * max(hi - lo, 0.25)
            lo_m, hi_m = max(-1.0, lo - margin), min(1.0, hi + margin)
            if fid in bounds:
                prev_lo, prev_hi = bounds[fid]
                lo_m, hi_m = max(prev_lo, lo_m), min(prev_hi, hi_m)
                if lo_m > hi_m:
                    lo_m = hi_m = 0.5 * (lo_m + hi_m)
            bounds[fid] = (lo_m, hi_m)
    return bounds


def recommend_parameters(
    surrogate: LearnedParameterSurrogate | Mapping[str, Any],
    request: ParameterRecommendationRequest | Mapping[str, Any] | None = None,
    *,
    target_case: CncBenchmarkCase | None = None,
) -> ParameterRecommendationReport:
    """Search active parameter subspace under sparse Top-K delta and conservative safety gates."""
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

    eval_case = target_case or req.target_case or model.default_case
    report_case_id = eval_case.case_id if eval_case is not None else model.case_id

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
    available_metrics = tuple(m for m in model.metric_heads.keys())
    missing_heads = [m for m in ("durationSeconds", primary_acc_metric) if m not in model.metric_heads]
    if missing_heads:
        raise ValueError(
            f"surrogate has no metric head for {', '.join(missing_heads)}; "
            "learn with more runs (>= 4 per metric) before requesting recommendations"
        )

    agg_importance = _target_geometry_leverage(model, eval_case, base_params, objective_metrics)
    locked_set = set(req.locked_parameter_ids)
    tunable_ids = [
        pid
        for pid, score in sorted(agg_importance.items(), key=lambda kv: kv[1], reverse=True)
        if pid not in locked_set and score > 1e-6
    ]
    if not tunable_ids:
        tunable_ids = [p.parameter_id for p in reg.parameters if p.parameter_id not in locked_set][:6]
    top_pool = tunable_ids[: min(10, len(tunable_ids))]
    k_max = min(req.max_changed_parameters, len(top_pool))

    base_preds: dict[str, tuple[float, float, bool]] = {
        m_id: predict_metric_for_parameters(model, m_id, base_params, target_case=eval_case)
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

    feed_param = param_map.get("g2.path_max_feed_override")
    sampling_bounds = _parameter_sampling_bounds(model)

    def _clip_value(pid: str, val: float) -> float:
        p_def = param_map[pid]
        lo, hi = float(p_def.bounds[0]), float(p_def.bounds[1])
        if feed_param is not None and pid == feed_param.parameter_id:
            hi = min(hi, req.maximum_feed_override)
        clipped_v = max(lo, min(hi, float(val)))
        return float(round(clipped_v)) if p_def.value_type == "integer" else round(clipped_v, 6)

    def _apply_seed_override(seed_override: Mapping[str, float]) -> dict[str, float]:
        cand = dict(base_params)
        applied = 0
        for pid, val in seed_override.items():
            if pid in param_map and pid not in locked_set and applied < k_max:
                cand[pid] = _clip_value(pid, val)
                applied += 1
        return cand

    # Only physics-derived seeds: align the FIR spectral zero and the notch with the
    # resonance actually measured by FFT on controller traces. No hand-picked "answers".
    if model.greybox_constants is not None and model.controller_run_count > 0:
        f_res = model.greybox_constants.identified_resonance_hz
        fir_notch_ms = round(min(48.0, max(4.0, 1000.0 / max(f_res, 25.0))), 3)
        notch_hz = round(min(400.0, max(40.0, f_res)), 2)
        for seed_override in (
            {"g2.fir_moving_avg_time_ms": fir_notch_ms},
            {"g3.notch_filter_freq_hz": notch_hz},
            {"g2.fir_moving_avg_time_ms": fir_notch_ms, "g3.notch_filter_freq_hz": notch_hz},
        ):
            candidate_dicts.append(_apply_seed_override(seed_override))

    for _ in range(max(0, req.candidate_pool_size - len(candidate_dicts))):
        k_choose = int(rng.integers(1, k_max + 1))
        chosen_ids = rng.choice(top_pool, size=k_choose, replace=False)
        cand = dict(base_params)
        for pid_raw in chosen_ids:
            pid = str(pid_raw)
            p_def = param_map[pid]
            lo_n, hi_n = sampling_bounds.get(pid, (-0.92, 0.92))
            u_norm = float(rng.uniform(lo_n, hi_n))
            cand[pid] = _clip_value(pid, denormalize_parameter_value(p_def, u_norm))
        candidate_dicts.append(cand)

    evaluated_candidates: list[ParameterRecommendationCandidate] = []
    gate_failures: dict[str, int] = {}
    uncertainty_records: list[tuple[float, float, dict[str, float], tuple[str, ...]]] = []

    for idx_c, cand_p in enumerate(candidate_dicts):
        changed_items: list[ParameterDeltaItem] = []
        changed_ids: list[str] = []
        for pid in reg.parameters:
            p_key = pid.parameter_id
            b_v = float(base_params[p_key])
            c_v = float(cand_p[p_key])
            if abs(c_v - b_v) > 1e-7:
                changed_ids.append(p_key)
                rel_pct = ((c_v - b_v) / max(abs(b_v), 1e-6)) * 100.0
                changed_items.append(
                    ParameterDeltaItem(
                        parameterId=p_key,
                        displayName=pid.display_name,
                        group=pid.group,
                        unit=pid.unit,
                        baselineValue=round(b_v, 6),
                        recommendedValue=round(c_v, 6),
                        delta=round(c_v - b_v, 6),
                        relativeChangePct=round(rel_pct, 2),
                        rationale=f"灰盒机理敏感度主导项（调幅 {rel_pct:+.1f}%）",
                    )
                )
        if len(changed_items) > req.max_changed_parameters:
            continue

        pred_summaries: dict[str, PredictedMetricSummary] = {}
        any_ood = False
        all_gates_ok = True
        unc_norm_sum = 0.0

        for m_id in available_metrics:
            head = model.metric_heads[m_id]
            b_mean = base_preds[m_id][0]
            p_mean, p_rad, m_ood = predict_metric_for_parameters(model, m_id, cand_p, target_case=eval_case)
            if m_ood:
                any_ood = True
            upper_b = p_mean + req.safety_kappa * p_rad
            lim = limits_map.get(m_id)
            within_lim = True if lim is None else (upper_b <= lim)
            if not within_lim:
                all_gates_ok = False
                gate_failures[f"{m_id} 上界超限"] = gate_failures.get(f"{m_id} 上界超限", 0) + 1

            delta_b = p_mean - b_mean
            rel_b = (delta_b / max(abs(b_mean), 1e-9)) * 100.0
            unc_norm_sum += p_rad / max(abs(b_mean), 1e-6)
            pred_summaries[m_id] = PredictedMetricSummary(
                metricId=m_id,
                unit=head.unit,
                baselinePredicted=round(b_mean, 6),
                predictedMean=round(p_mean, 6),
                uncertaintyRadius=round(p_rad, 6),
                conservativeUpperBound=round(upper_b, 6),
                deltaFromBaseline=round(delta_b, 6),
                relativeChangePct=round(rel_b, 2),
                hardLimit=lim,
                withinConservativeLimit=within_lim,
            )

        if eval_case is not None and model.greybox_constants is not None:
            max_case_acc = min(float(lim.maximum_acceleration_mm_s2) for lim in eval_case.axis_limits)
            declared_jerks = [float(lim.maximum_jerk_mm_s3) for lim in eval_case.axis_limits if lim.maximum_jerk_mm_s3 is not None]
            max_case_jrk = min(declared_jerks) if declared_jerks else float("inf")
            cand_at = float(cand_p.get("g2.path_tangential_acc_mm_s2", 5000.0))
            cand_jt = float(cand_p.get("g2.path_tangential_jerk_mm_s3", 200000.0))
            cand_an = float(cand_p.get("g2.centripetal_acc_limit_mm_s2", 3000.0))
            cand_fir_s = max(float(cand_p.get("g2.fir_moving_avg_time_ms", 12.0)) * 1e-3, eval_case.sample_period_seconds)
            cand_flp = max(float(cand_p.get("g2.biquad_lowpass_freq_hz", 80.0)), 2.0)
            corner_jrk_est = (1.25 * cand_an) / max(cand_fir_s, eval_case.sample_period_seconds) if extract_case_geometry_profile(eval_case).has_corners else 0.0
            if cand_at > max_case_acc or cand_jt > max_case_jrk or corner_jrk_est > max_case_jrk:
                all_gates_ok = False
                gate_failures["轴加速度/Jerk 上限"] = gate_failures.get("轴加速度/Jerk 上限", 0) + 1

        in_dom = not any_ood
        feasible_flag = in_dom and all_gates_ok

        dur_gain = (base_preds["durationSeconds"][0] - pred_summaries["durationSeconds"].predicted_mean) / max(
            base_preds["durationSeconds"][0], 1e-6
        )
        acc_gain = (base_preds[primary_acc_metric][0] - pred_summaries[primary_acc_metric].predicted_mean) / max(
            base_preds[primary_acc_metric][0], 1e-6
        )
        acq_score = 0.55 * unc_norm_sum + 0.45 * max(0.0, dur_gain + acc_gain)
        if changed_ids:
            uncertainty_records.append((acq_score, unc_norm_sum, cand_p, tuple(changed_ids)))

        evaluated_candidates.append(
            ParameterRecommendationCandidate(
                candidateId=f"cand.{idx_c + 1:04d}",
                changedParameterCount=len(changed_items),
                changedParameters=tuple(changed_items),
                fullParameters={k: round(float(v), 6) for k, v in cand_p.items()},
                predictedMetrics=pred_summaries,
                inDomain=in_dom,
                hardConstraintsSatisfied=feasible_flag,
                paretoOptimal=False,
                tradeoffExplanation="候选评估完成",
            )
        )

    feasible = [c for c in evaluated_candidates if c.hard_constraints_satisfied]
    pool_for_pareto = feasible

    obj_tuples = [
        (
            c.predicted_metrics["durationSeconds"].predicted_mean,
            c.predicted_metrics[primary_acc_metric].predicted_mean,
            c.predicted_metrics["discreteJerkRms"].predicted_mean
            if "discreteJerkRms" in c.predicted_metrics
            else 0.0,
        )
        for c in pool_for_pareto
    ]

    pareto_front: list[ParameterRecommendationCandidate] = []
    for i, cand_i in enumerate(pool_for_pareto):
        dominated = any(
            j != i and _dominates(obj_tuples[j], obj_tuples[i])
            for j in range(len(pool_for_pareto))
        )
        if not dominated:
            pareto_front.append(cand_i.model_copy(update={"pareto_optimal": True}))

    pareto_front.sort(key=lambda c: c.predicted_metrics["durationSeconds"].predicted_mean)

    no_feasible_reason: str | None = None
    presets: tuple[ParameterRecommendationCandidate, ...] = ()
    if not pareto_front:
        ood_count = sum(1 for c in evaluated_candidates if not c.in_domain)
        top_fail = sorted(gate_failures.items(), key=lambda kv: kv[1], reverse=True)[:3]
        fail_txt = "；".join(f"{name} {cnt} 次" for name, cnt in top_fail) or "无"
        no_feasible_reason = (
            f"{len(evaluated_candidates)} 个候选均未通过门禁（超出训练数据覆盖范围 {ood_count} 个；主要失败项：{fail_txt}）。"
            "请放宽约束、减少锁定参数，或按 activeDoeSuggestions 补采数据后重试；不输出推荐档位。"
        )
    else:
        presets = _select_presets(pareto_front, primary_acc_metric)

    uncertainty_records.sort(key=lambda item: item[0], reverse=True)
    doe_suggestions: list[ActiveExperimentSuggestion] = []
    has_ctrl = model.controller_run_count > 0
    for idx_s, (acq, unc, s_params, c_ids) in enumerate(uncertainty_records[:3]):
        uses_g3 = any(param_map[cid].group == "G3_ServoControl" for cid in c_ids if cid in param_map)
        tgt_src: SourceKind = "controller-trace" if (uses_g3 or has_ctrl) else "algorithm-export"
        doe_suggestions.append(
            ActiveExperimentSuggestion(
                suggestionId=f"active-doe.{idx_s + 1:02d}",
                targetSource=tgt_src,
                changedParameterIds=c_ids,
                parameters={k: round(float(v), 6) for k, v in s_params.items()},
                acquisitionScore=round(float(acq), 6),
                uncertaintyScore=round(float(unc), 6),
                rationale=(
                    f"建议在 {tgt_src} 补采调整 ({', '.join(c_ids)})：该区域逼近灰盒物理瓶颈边界但残差不确定性较高 "
                    f"(CEI={acq:.3f})，补采 1 组即可收紧保守置信上界"
                ),
            )
        )

    report = ParameterRecommendationReport(
        caseId=report_case_id,
        surrogateModelHash=model.model_content_hash,
        primaryAccuracyMetricId=primary_acc_metric,
        maxChangedParameters=req.max_changed_parameters,
        evaluatedCandidateCount=len(evaluated_candidates),
        feasibleCandidateCount=len(feasible),
        paretoCandidateCount=len(pareto_front),
        presets=presets,
        paretoFront=tuple(pareto_front[:15]),
        activeDoeSuggestions=tuple(doe_suggestions),
        noFeasibleReason=no_feasible_reason,
        reportContentHash="",
    )
    content = report.model_dump(mode="json", by_alias=True, exclude_none=True)
    content.pop("reportContentHash")
    return report.model_copy(update={"report_content_hash": _canonical_hash(content)})


def _select_presets(
    pareto_front: list[ParameterRecommendationCandidate],
    primary_acc_metric: str,
) -> tuple[ParameterRecommendationCandidate, ...]:
    """Pick up to three DISTINCT presets from a non-empty feasible Pareto front."""

    def _dur(c: ParameterRecommendationCandidate) -> float:
        return c.predicted_metrics["durationSeconds"].predicted_mean

    def _err(c: ParameterRecommendationCandidate) -> float:
        return c.predicted_metrics[primary_acc_metric].predicted_mean

    def _jrk(c: ParameterRecommendationCandidate) -> float:
        m = c.predicted_metrics.get("discreteJerkRms")
        return m.predicted_mean if m is not None else 0.0

    prec_cand = min(pareto_front, key=_err)
    eff_cand = min(pareto_front, key=_dur)
    durs = np.asarray([_dur(c) for c in pareto_front])
    errs = np.asarray([_err(c) for c in pareto_front])
    jrks = np.asarray([_jrk(c) for c in pareto_front])
    d_norm = (durs - np.min(durs)) / max(float(np.ptp(durs)), 1e-9)
    e_norm = (errs - np.min(errs)) / max(float(np.ptp(errs)), 1e-9)
    j_norm = (jrks - np.min(jrks)) / max(float(np.ptp(jrks)), 1e-9)
    order_knee = np.argsort(np.sqrt(d_norm ** 2 + e_norm ** 2 + 0.75 * (j_norm ** 2)))
    taken = {eff_cand.candidate_id, prec_cand.candidate_id}
    knee_cand = next((pareto_front[int(i)] for i in order_knee if pareto_front[int(i)].candidate_id not in taken), None)

    def _label(cand: ParameterRecommendationCandidate, role: PresetRole, title: str) -> ParameterRecommendationCandidate:
        dur_m = cand.predicted_metrics["durationSeconds"]
        acc_m = cand.predicted_metrics[primary_acc_metric]
        jrk_m = cand.predicted_metrics.get("discreteJerkRms")
        jrk_txt = f"，冲击 RMS {jrk_m.relative_change_pct:+.1f}%" if jrk_m else ""
        desc = (
            f"【{title}】微调 {cand.changed_parameter_count} 个参数：预计周期 {dur_m.predicted_mean:.4g}s "
            f"({dur_m.relative_change_pct:+.1f}%)，{primary_acc_metric}={acc_m.predicted_mean:.4g}mm "
            f"(上界 {acc_m.conservative_upper_bound:.4g}mm，实机覆盖率未验证，需上机验证){jrk_txt}"
        )
        return cand.model_copy(update={"preset_role": role, "preset_title": title, "tradeoff_explanation": desc})

    roles: tuple[tuple[ParameterRecommendationCandidate | None, PresetRole, str], ...] = (
        (eff_cand, "EfficiencyOptimal", "高速效率优先档"),
        (prec_cand, "PrecisionOptimal", "高精轮廓优先档"),
        (knee_cand, "BalancedKneePoint", "柔顺均衡拐点档"),
    )
    chosen: list[ParameterRecommendationCandidate] = []
    seen: set[str] = set()
    for cand, role, title in roles:
        if cand is None or cand.candidate_id in seen:
            continue
        seen.add(cand.candidate_id)
        chosen.append(_label(cand, role, title))
    return tuple(chosen)


def simulate_parametric_cnc_export(
    case: CncBenchmarkCase,
    parameters: Mapping[str, float],
    *,
    source_kind: SourceKind = "algorithm-export",
    registry: CncParameterRegistry | None = None,
    algorithm_version: str = "realistic-cnc-kernel-v1",
) -> CncAlgorithmExport:
    """Synthesize a physically faithful 32-parameter CNC trajectory export (delegates to realistic kernel)."""
    return simulate_realistic_cnc_controller(
        case,
        parameters,
        source_kind=source_kind,
        registry=registry,
        algorithm_version=algorithm_version,
    )


def build_cnc_parameter_closed_loop_demo(
    *,
    offline_count: int = 24,
    controller_count: int = 10,
    seed: int = 42,
    multi_case_calibration: bool = False,
) -> CncParameterClosedLoopDemo:
    """Build an end-to-end 32-parameter grey-box calibration & recommendation demonstration."""
    reg = default_cnc_parameter_registry()
    settings = StandardCaseSettings(sample_period_seconds=0.002, maximum_path_deviation_mm=0.06)
    corner_case = standard_case("corner90", settings)
    doe = generate_parameter_doe(
        reg,
        offline_count=offline_count,
        controller_count=controller_count,
        seed=seed,
        mode="orthogonal-greybox",
    )

    if multi_case_calibration:
        suite = {c.case_id: c for c in standard_cases(settings)}
    else:
        suite = {corner_case.case_id: corner_case}

    exports: list[CncAlgorithmExport] = []
    for sample in doe.offline_samples:
        c_use = suite.get(sample.recommended_case_id or "", corner_case) if multi_case_calibration else corner_case
        exports.append(
            simulate_realistic_cnc_controller(
                c_use,
                sample.parameters,
                source_kind="algorithm-export",
                registry=reg,
                algorithm_version=sample.sample_id,
            )
        )
    for sample in doe.controller_samples:
        c_use = suite.get(sample.recommended_case_id or "", corner_case) if multi_case_calibration else corner_case
        exports.append(
            simulate_realistic_cnc_controller(
                c_use,
                sample.parameters,
                source_kind="controller-trace",
                registry=reg,
                algorithm_version=sample.sample_id,
            )
        )

    sample_quality_report = evaluate_cnc_export(
        suite.get(doe.controller_samples[-1].recommended_case_id or "", corner_case) if (multi_case_calibration and doe.controller_samples) else corner_case,
        exports[-1],
    )
    surrogate = learn_parameter_surrogate(
        list(suite.values()) if multi_case_calibration else corner_case,
        exports,
        registry=reg,
    )
    rec_report = recommend_parameters(
        surrogate,
        ParameterRecommendationRequest(
            maxChangedParameters=4,
            # Contour limits come from the case; following error is not a contour-quality limit.
            maximumPathDeviationMm=corner_case.maximum_path_deviation_mm,
            maximumActualPathDeviationMm=corner_case.maximum_path_deviation_mm,
            maximumFollowingErrorMm=None,
            seed=seed,
        ),
        target_case=corner_case,
    )
    return CncParameterClosedLoopDemo(
        case=corner_case,
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
    if report.no_feasible_reason:
        lines.append(f"未输出推荐档位：{report.no_feasible_reason}")
        lines.append("")
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
