import { useEffect, useMemo, useState } from "react";

import type { Catalog } from "../../types";
import {
  loadR6V2Example,
  loadR6V2Manifest,
  loadR6V2Scenarios,
  rehearseGoalToShadow,
  runR6V2Search,
} from "./api";
import {
  OptimizationVersionSwitch,
  type OptimizationVersion,
} from "./OptimizationVersionSwitch";
import type {
  R6V2ExamplePayload,
  GoalToShadowReport,
  R6V2Intent,
  R6V2PrimaryObjective,
  R6V2ScenarioSummary,
  R6V2SearchRequest,
} from "./types";

const SCENARIO_BY_OBJECTIVE: Record<R6V2PrimaryObjective, string> = {
  cycleTimeSeconds: "canonical-goal-conditioned-speed",
  linearFollowingErrorMaxMm: "canonical-goal-conditioned-quality",
  commandSampleCount: "canonical-goal-conditioned-compact-command",
};

const OBJECTIVE_LABELS: Record<R6V2PrimaryObjective, string> = {
  cycleTimeSeconds: "速度优先 · 最短周期",
  linearFollowingErrorMaxMm: "质量优先 · 最小误差",
  commandSampleCount: "紧凑指令 · 最少样本",
};

function shortHash(value?: string): string {
  return value ? `${value.slice(0, 9)}…${value.slice(-7)}` : "—";
}

function formatNumber(value: number, digits = 4): string {
  return value.toFixed(digits).replace(/\.?0+$/, "");
}

function positive(value: string, label: string, integer = false): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0 || (integer && !Number.isInteger(parsed))) {
    throw new Error(`${label}必须是${integer ? "正整数" : "正数"}。`);
  }
  return parsed;
}

function intentFields(intent: R6V2Intent): { cycle: string; error: string; count: string } {
  return {
    cycle: "maximumCycleTimeSeconds" in intent ? String(intent.maximumCycleTimeSeconds) : "",
    error: "maximumLinearFollowingErrorMm" in intent ? String(intent.maximumLinearFollowingErrorMm) : "",
    count: "maximumCommandSampleCount" in intent ? String(intent.maximumCommandSampleCount) : "",
  };
}

export function OptimizationR6V2Workbench({
  catalog,
  onVersionChange,
}: {
  catalog: Catalog | null;
  onVersionChange: (value: OptimizationVersion) => void;
}) {
  const [scenarios, setScenarios] = useState<R6V2ScenarioSummary[]>([]);
  const [payload, setPayload] = useState<R6V2ExamplePayload | null>(null);
  const [primary, setPrimary] = useState<R6V2PrimaryObjective>("cycleTimeSeconds");
  const [maxCycle, setMaxCycle] = useState("");
  const [maxError, setMaxError] = useState("");
  const [maxCount, setMaxCount] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [shadowReport, setShadowReport] = useState<GoalToShadowReport | null>(null);
  const [shadowBusy, setShadowBusy] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const recommendations = payload?.recommendationSet;
  const selected = useMemo(
    () => recommendations?.exactCandidates.find((item) => item.candidateId === selectedId)
      ?? recommendations?.exactCandidates.find((item) => item.bestObserved)
      ?? recommendations?.exactCandidates[0],
    [recommendations, selectedId],
  );
  const runtimeBound = Boolean(
    catalog?.domainPacks.find((item) => item.domainPackId === "optimization.domain-pack@2")?.runtimeBound,
  );

  const applyPayload = (next: R6V2ExamplePayload) => {
    const fields = intentFields(next.searchRequest.intent);
    setPayload(next);
    setPrimary(next.searchRequest.intent.primaryObjectiveId);
    setMaxCycle(fields.cycle);
    setMaxError(fields.error);
    setMaxCount(fields.count);
    setSelectedId(next.recommendationSet.bestObservedCandidateIds[0]
      ?? next.recommendationSet.exactCandidates[0]?.candidateId
      ?? "");
    setShadowReport(null);
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [, nextScenarios, nextPayload] = await Promise.all([
          loadR6V2Manifest(),
          loadR6V2Scenarios(),
          loadR6V2Example(SCENARIO_BY_OBJECTIVE.cycleTimeSeconds),
        ]);
        if (!active.value) return;
        setScenarios(nextScenarios);
        applyPayload(nextPayload);
      } catch (reason) {
        if (active.value) setError(reason instanceof Error ? reason.message : "R6 v2 初始化失败。");
      } finally {
        if (active.value) setBusy(false);
      }
    })();
    return () => { active.value = false; };
  }, []);

  const chooseObjective = async (nextPrimary: R6V2PrimaryObjective) => {
    setBusy(true);
    setError(null);
    try {
      applyPayload(await loadR6V2Example(SCENARIO_BY_OBJECTIVE[nextPrimary]));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "目标预设加载失败。");
    } finally {
      setBusy(false);
    }
  };

  const search = async () => {
    if (!payload) return;
    setBusy(true);
    setError(null);
    try {
      let intent: R6V2Intent;
      if (primary === "cycleTimeSeconds") {
        intent = {
          intentId: "optimization.r6v2.speed-intent@1",
          primaryObjectiveId: primary,
          maximumLinearFollowingErrorMm: positive(maxError, "最大线性误差"),
          maximumCommandSampleCount: positive(maxCount, "最大指令样本数", true),
        };
      } else if (primary === "linearFollowingErrorMaxMm") {
        intent = {
          intentId: "optimization.r6v2.quality-intent@1",
          primaryObjectiveId: primary,
          maximumCycleTimeSeconds: positive(maxCycle, "最大周期"),
          maximumCommandSampleCount: positive(maxCount, "最大指令样本数", true),
        };
      } else {
        intent = {
          intentId: "optimization.r6v2.compact-command-intent@1",
          primaryObjectiveId: primary,
          maximumCycleTimeSeconds: positive(maxCycle, "最大周期"),
          maximumLinearFollowingErrorMm: positive(maxError, "最大线性误差"),
        };
      }
      const request: R6V2SearchRequest = { ...payload.searchRequest, intent };
      applyPayload(await runR6V2Search(request));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R6 v2 搜索失败。");
    } finally {
      setBusy(false);
    }
  };

  const scenario = scenarios.find((item) => item.primaryObjectiveId === primary);
  const screening = recommendations?.screeningReceipt;
  const selectCandidate = (candidateId: string) => {
    setSelectedId(candidateId);
    setShadowReport(null);
  };
  const rehearseShadow = async () => {
    if (!payload || !selected) return;
    setShadowBusy(true);
    setError(null);
    try {
      setShadowReport(await rehearseGoalToShadow(payload.searchRequest, selected.candidateId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Synthetic Shadow 预演失败。");
    } finally {
      setShadowBusy(false);
    }
  };
  const shadowAudit = shadowReport?.runtimeAudit;
  const shadowProjection = shadowReport?.physicalShadowProjection;
  const shadowBreachCount = shadowAudit?.monitorFindings.filter((item) => item.status === "Breach").length ?? 0;

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>R6 v2 未完成</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      <main className="workspace optimization-r6-workspace">
        <aside className="config-panel optimization-r6-config">
          <OptimizationVersionSwitch value="v2" onChange={onVersionChange} />
          <div className="panel-heading">
            <div><span className="eyebrow">OPTIMIZATION R6 V2 LAB</span><h1>目标驱动参数搜索</h1></div>
            <span className="schema-badge">@2</span>
          </div>

          <section className="config-section">
            <div className="notice-card optimization-r6-banner" role="note">
              <strong>SCREEN → EXACT REPLAY</strong>
              <p>代理模型只负责提议；最终推荐必须经过精确 F3/F4/R4 回放。</p>
            </div>
            <div className="chip-row">
              <span className="chip">windows-only</span><span className="chip">offline-only</span>
              <span className={`chip ${runtimeBound ? "status-positive" : "status-neutral"}`}>{runtimeBound ? "runtime-bound" : "runtime-pending"}</span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>主目标</h2><em>1 + 2 ε limits</em></div>
            <label className="optimization-r6-select"><span>优化意图</span><select aria-label="优化意图" value={primary} onChange={(event) => void chooseObjective(event.target.value as R6V2PrimaryObjective)} disabled={busy}>{Object.entries(OBJECTIVE_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
            <p>{scenario?.description ?? "正在加载目标预设…"}</p>
            <div className="optimization-r6-field-grid">
              {primary !== "cycleTimeSeconds" && <label><span>最大周期 · s</span><input aria-label="最大周期" inputMode="decimal" value={maxCycle} onChange={(event) => setMaxCycle(event.target.value)} /></label>}
              {primary !== "linearFollowingErrorMaxMm" && <label><span>最大线性误差 · mm</span><input aria-label="最大线性误差" inputMode="decimal" value={maxError} onChange={(event) => setMaxError(event.target.value)} /></label>}
              {primary !== "commandSampleCount" && <label><span>最大指令样本数</span><input aria-label="最大指令样本数" inputMode="numeric" value={maxCount} onChange={(event) => setMaxCount(event.target.value)} /></label>}
            </div>
            <button className="button button-primary optimization-r6-run" type="button" onClick={() => void search()} disabled={busy || !payload}>{busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◆</span>}{busy ? "精确回放中…" : "运行目标搜索"}</button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>冻结搜索合同</h2><em>budgeted</em></div>
            <dl className="data-list">
              <div><dt>Dense grid</dt><dd>15 × 9 = 135</dd></div>
              <div><dt>Exact budget</dt><dd>≤ 27</dd></div>
              <div><dt>Surrogate</dt><dd>R5-C conditional effect</dd></div>
              <div><dt>Global optimum</dt><dd className="status-neutral">NotClaimed</dd></div>
            </dl>
          </section>
        </aside>

        <section className="analysis-panel optimization-r6-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Evidence Funnel</span><span>/</span><span>Exact Candidates</span></div>
            <div className="run-state"><span className="status-positive">best observed</span><span className="status-neutral">reality: Open</span></div>
          </div>

          <div className="optimization-r6-body">
            <section className="report-card optimization-r6-hero">
              <div><span className="eyebrow">GOAL-CONDITIONED SURROGATE SEARCH</span><h2>先用小模型缩小搜索，再用数学与物理模型裁决</h2><p>目标不混成权重总分；一个主目标配两个明确约束，代理候选不能直接成为推荐。</p></div>
              <div className="optimization-r6-count"><strong>{recommendations?.bestObservedCandidateIds.length ?? 0}</strong><span>best observed</span><small>global optimum: NotClaimed</small></div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>证据漏斗</h2><em>surrogate ≠ verdict</em></div>
              <div className="optimization-r6-funnel">
                <article><strong>{screening?.candidateCount ?? 0}</strong><span>代理评估</span><small>dense grid</small></article>
                <i aria-hidden="true">→</i>
                <article><strong>{screening?.possiblyFeasibleCount ?? 0}</strong><span>可能可行</span><small>lower-bound screen</small></article>
                <i aria-hidden="true">→</i>
                <article><strong>{screening?.selectedCount ?? 0}</strong><span>精确回放</span><small>budget ≤ 27</small></article>
                <i aria-hidden="true">→</i>
                <article><strong>{recommendations?.exactFeasibleCandidateIds.length ?? 0}</strong><span>精确可行</span><small>all gates + ε</small></article>
              </div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>02</span><h2>精确验证候选</h2><em>{recommendations?.exactCandidates.length ?? 0} replayed</em></div>
              <div className="optimization-r6-table-wrap">
                <table className="optimization-r6-table">
                  <thead><tr><th>排名 / 参数</th><th>周期</th><th>线性误差</th><th>样本</th><th>代理误差</th><th>结论</th></tr></thead>
                  <tbody>{(recommendations?.exactCandidates ?? []).map((candidate) => <tr key={candidate.candidateId} className={candidate.candidateId === selected?.candidateId ? "selected" : ""} onClick={() => selectCandidate(candidate.candidateId)}><td><button type="button" onClick={() => selectCandidate(candidate.candidateId)}>#{candidate.screeningRank} · F{formatNumber(candidate.parameterSet.values.feedOverride, 3)} · {formatNumber(candidate.parameterSet.values.samplePeriod, 3)}s</button></td><td>{formatNumber(candidate.objectives.cycleTimeSeconds, 5)}s</td><td>{formatNumber(candidate.objectives.linearFollowingErrorMaxMm, 5)}mm</td><td>{candidate.objectives.commandSampleCount}</td><td>{formatNumber(candidate.cycleTimePredictionAbsoluteError, 6)}s / {formatNumber(candidate.linearErrorPredictionAbsoluteError, 5)}mm</td><td><span className={candidate.bestObserved ? "status-positive" : candidate.recommendationEligible ? "status-neutral" : "status-negative"}>{candidate.bestObserved ? "Best observed" : candidate.recommendationEligible ? "Exact feasible" : "Constraint blocked"}</span></td></tr>)}</tbody>
                </table>
              </div>
            </section>

            {selected && <div className="optimization-r6-detail-grid">
              <section className="report-card"><div className="section-title compact"><span>03</span><h2>七个数学硬门</h2><em>{selected.gateReceipts.filter((item) => item.status === "Supported").length} / 7</em></div><div className="optimization-r6-gates">{selected.gateReceipts.map((gate) => <article key={gate.claimId}><span className={gate.status === "Supported" ? "status-positive" : "status-negative"}>●</span><div><strong>{gate.claimId.replace("five-axis.", "").replace("-claim@1", "")}</strong><small>{shortHash(gate.evidenceContentHash)}</small></div></article>)}</div></section>
              <section className="report-card"><div className="section-title compact"><span>04</span><h2>精确裁决</h2><em>{selected.bestObserved ? "BEST OBSERVED" : "VALIDATED"}</em></div><p>{selected.explanation}</p><dl className="data-list compact-list"><div><dt>Hard gates</dt><dd className={selected.hardConstraintsSatisfied ? "status-positive" : "status-negative"}>{String(selected.hardConstraintsSatisfied)}</dd></div><div><dt>ε constraints</dt><dd className={selected.exactConstraintsSatisfied ? "status-positive" : "status-negative"}>{String(selected.exactConstraintsSatisfied)}</dd></div><div><dt>Global optimum</dt><dd className="status-neutral">NotClaimed</dd></div><div><dt>Device write</dt><dd className="status-negative">false</dd></div></dl></section>
            </div>}

            <section className="report-card optimization-r6-shadow">
              <div className="section-title compact"><span>05</span><h2>Synthetic Shadow 预演</h2><em>exact R4 response</em></div>
              <div className="optimization-r6-shadow-action">
                <div><strong>用当前 exact candidate 重建真实来源的 SIL 轨迹</strong><p>服务器会重新执行 F3/F4/R4，逐项核对 M4、M5、响应哈希和采样时间，再进入既有 R7-A fail-closed 状态机。</p></div>
                <button className="button button-primary" type="button" onClick={() => void rehearseShadow()} disabled={busy || shadowBusy || !selected?.recommendationEligible}>{shadowBusy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▷</span>}{shadowBusy ? "正在重放物理响应…" : selected?.recommendationEligible ? "进入 Synthetic Shadow" : "候选不可入场"}</button>
              </div>
              {shadowReport ? (
                <div className="optimization-r6-shadow-result" data-status={shadowReport.status.toLowerCase()}>
                  <div className="optimization-r6-shadow-verdict"><span className={shadowReport.status === "Passed" ? "status-positive" : "status-negative"}>{shadowReport.status}</span><strong>{shadowAudit?.finalState ?? "未入场"}</strong><small>{shadowReport.reasonCodes.join(" · ") || "exact identity chain verified"}</small></div>
                  {shadowProjection && <div className="optimization-r6-shadow-metrics"><article><strong>{shadowProjection.sampleCount}</strong><span>exact samples</span><small>no interpolation</small></article><article><strong>{formatNumber(shadowProjection.maximumLinearFollowingErrorMm, 5)}</strong><span>max linear error · mm</span><small>X/Y/Z only</small></article><article><strong>{shadowBreachCount}</strong><span>envelope breaches</span><small>{shadowAudit?.stopReceipt.effect ?? "not admitted"}</small></article><article><strong>{formatNumber(shadowProjection.candidateOodFraction, 4)}</strong><span>candidate OOD</span><small>constant projection</small></article></div>}
                  <dl className="data-list compact-list"><div><dt>R4 response</dt><dd title={shadowProjection?.sourcePhysicalResponseContentHash}>{shortHash(shadowProjection?.sourcePhysicalResponseContentHash)}</dd></div><div><dt>Shadow trace</dt><dd title={shadowProjection?.shadowTrace.contentHash}>{shortHash(shadowProjection?.shadowTrace.contentHash)}</dd></div><div><dt>Admission</dt><dd className={shadowAudit?.admissionDecision.status === "Admitted" ? "status-positive" : "status-negative"}>{shadowAudit?.admissionDecision.status ?? "Blocked"}</dd></div><div><dt>Device write</dt><dd className="status-negative">false</dd></div></dl>
                </div>
              ) : <div className="optimization-r6-shadow-boundary"><span>SYNTHETIC SIL</span><span>DEPLOYMENT SHADOW · OPEN</span><span>REALITY · OPEN</span><span>DEVICE SAFETY · NOT ASSESSED</span></div>}
              <footer className="optimization-r6-shadow-footer"><span>Synthetic replay only</span><strong>NOT DEVICE SAFE · NO WRITE · NO AUTO ACCEPT</strong></footer>
            </section>

            <section className="report-card optimization-r6-plan"><div className="section-title compact"><span>06</span><h2>后续验证边界</h2><em>not reality validated</em></div><div className="optimization-r6-plan-grid"><div><strong>Remaining gates</strong><ol>{recommendations?.validationPlan.remainingGates.map((item) => <li key={item}>{item}</li>)}</ol></div><div><strong>Stop conditions</strong><ol>{recommendations?.validationPlan.stopConditions.map((item) => <li key={item}>{item}</li>)}</ol></div></div><footer><span>Rollback</span><code>{recommendations?.validationPlan.rollbackParameterSetId ?? "—"}</code><strong>OFFLINE · NO WRITE</strong></footer></section>
          </div>
        </section>
      </main>
      <footer className="statusbar optimization-r6-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domain: <code>{payload?.manifest.domainPackId ?? "optimization.domain-pack@2"}</code></span><span className="statusbar-right">{recommendations ? shortHash(recommendations.contentHash) : "loading"} · Best observed only</span></footer>
    </>
  );
}
