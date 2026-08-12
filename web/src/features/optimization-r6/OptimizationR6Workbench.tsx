import { useEffect, useMemo, useState } from "react";

import type { Catalog } from "../../types";
import { loadR6Example, loadR6Manifest, loadR6Scenarios, runR6Search } from "./api";
import type { OptimizationSearchRequest, R6ExamplePayload, R6Manifest, R6ScenarioSummary } from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return `${value.slice(0, 9)}…${value.slice(-7)}`;
}

function number(value: number, digits = 3): string {
  return value.toFixed(digits).replace(/\.?0+$/, "");
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function optionalPositive(value: string, label: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`${label}必须是正数。`);
  return parsed;
}

function optionalPositiveInteger(value: string, label: string): number | undefined {
  const parsed = optionalPositive(value, label);
  if (parsed !== undefined && !Number.isInteger(parsed)) {
    throw new Error(`${label}必须是正整数。`);
  }
  return parsed;
}

export function OptimizationR6Workbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<R6Manifest | null>(null);
  const [scenarios, setScenarios] = useState<R6ScenarioSummary[]>([]);
  const [example, setExample] = useState<R6ExamplePayload | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [maxCycle, setMaxCycle] = useState("");
  const [maxError, setMaxError] = useState("");
  const [maxSamples, setMaxSamples] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const recommendations = example?.recommendationSet;
  const selected = useMemo(
    () => recommendations?.candidates.find((candidate) => candidate.candidateId === selectedId)
      ?? recommendations?.candidates.find((candidate) => candidate.paretoOptimal)
      ?? recommendations?.candidates[0],
    [recommendations, selectedId],
  );
  const runtimeBound = Boolean(
    catalog?.domainPacks.find((item) => item.domainPackId === "optimization.domain-pack@1")?.runtimeBound,
  );

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextScenarios, nextExample] = await Promise.all([
          loadR6Manifest(),
          loadR6Scenarios(),
          loadR6Example(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setScenarios(nextScenarios);
        setExample(nextExample);
        setSelectedId(nextExample.recommendationSet.paretoCandidateIds[0] ?? "");
      } catch (reason) {
        if (active.value) setError(reason instanceof Error ? reason.message : "R6 初始化失败。");
      } finally {
        if (active.value) setBusy(false);
      }
    })();
    return () => { active.value = false; };
  }, []);

  const search = async () => {
    if (!example) return;
    setBusy(true);
    setError(null);
    try {
      const request: OptimizationSearchRequest = {
        ...example.searchRequest,
        goal: {
          ...example.searchRequest.goal,
          maximumCycleTimeSeconds: optionalPositive(maxCycle, "最大周期"),
          maximumLinearFollowingErrorMm: optionalPositive(maxError, "最大跟随误差"),
          maximumCommandSampleCount: optionalPositiveInteger(maxSamples, "最大样本数"),
        },
      };
      const next = await runR6Search(request);
      setExample(next);
      setSelectedId(next.recommendationSet.paretoCandidateIds[0] ?? next.recommendationSet.candidates[0]?.candidateId ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R6 搜索失败。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>R6 未完成</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      <main className="workspace optimization-r6-workspace">
        <aside className="config-panel optimization-r6-config">
          <div className="panel-heading">
            <div><span className="eyebrow">OPTIMIZATION R6 LAB</span><h1>受约束参数推荐</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="notice-card optimization-r6-banner" role="note">
              <strong>OFFLINE RECOMMENDATION</strong>
              <p>数学硬门先于目标排序。没有设备写入、自动接受或安全上机声明。</p>
            </div>
            <div className="chip-row">
              <span className="chip">windows-only</span><span className="chip">offline-only</span>
              <span className={`chip ${runtimeBound ? "status-positive" : "status-neutral"}`}>{runtimeBound ? "runtime-bound" : "runtime-pending"}</span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>目标与约束</h2><em>3 objectives</em></div>
            <p>{scenarios[0]?.description ?? "正在加载冻结场景…"}</p>
            <div className="optimization-r6-field-grid">
              <label><span>最大周期 · s</span><input aria-label="最大周期" inputMode="decimal" placeholder="不限" value={maxCycle} onChange={(event) => setMaxCycle(event.target.value)} /></label>
              <label><span>最大跟随误差 · mm</span><input aria-label="最大跟随误差" inputMode="decimal" placeholder="不限" value={maxError} onChange={(event) => setMaxError(event.target.value)} /></label>
              <label><span>最大指令样本数</span><input aria-label="最大样本数" inputMode="numeric" placeholder="不限" value={maxSamples} onChange={(event) => setMaxSamples(event.target.value)} /></label>
            </div>
            <button className="button button-primary optimization-r6-run" type="button" onClick={() => void search()} disabled={busy || !example}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◆</span>}{busy ? "重放证据链…" : "搜索 Pareto 候选"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>参数平面</h2><em>6 points</em></div>
            <dl className="data-list">
              <div><dt>feedOverride</dt><dd>{example?.searchRequest.grid.feedOverrides.join(" / ") ?? "—"}</dd></div>
              <div><dt>samplePeriod</dt><dd>{example?.searchRequest.grid.samplePeriods.map((item) => `${item}s`).join(" / ") ?? "—"}</dd></div>
              <div><dt>Search</dt><dd>deterministic grid</dd></div>
              <div><dt>Ranking</dt><dd>unweighted Pareto</dd></div>
            </dl>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>物理适用性</h2><em>{recommendations?.physicalApplicabilityEvidence.status ?? "—"}</em></div>
            <div className="optimization-r6-endpoints">
              {(recommendations?.physicalApplicabilityEvidence.endpointEvaluations ?? []).map((point) => (
                <article key={point.samplePeriodSeconds}>
                  <strong>{point.samplePeriodSeconds}s</strong><span>{percent(point.improvementRatio)}</span><small>holdout improvement</small>
                </article>
              ))}
            </div>
            <p className="optimization-r6-footnote">Independent two-stage-lag oracle · reality validation remains Open.</p>
          </section>
        </aside>

        <section className="analysis-panel optimization-r6-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Pareto Frontier</span><span>/</span><span>Gate Evidence</span></div>
            <div className="run-state"><span className="status-positive">{recommendations?.paretoCandidateIds.length ?? 0} Pareto</span><span className="status-neutral">reality: Open</span></div>
          </div>

          <div className="optimization-r6-body">
            <section className="report-card optimization-r6-hero">
              <div><span className="eyebrow">UNWEIGHTED MULTI-OBJECTIVE SEARCH</span><h2>快、准、少采样，不压成一个总分</h2><p>秒、毫米与样本数保持独立；只有通过七个数学硬门和物理适用性门的候选才进入前沿。</p></div>
              <div className="optimization-r6-count"><strong>{recommendations?.candidates.length ?? 0}</strong><span>evaluated</span><small>{recommendations?.paretoCandidateIds.length ?? 0} non-dominated</small></div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>候选矩阵</h2><em>click to inspect</em></div>
              <div className="optimization-r6-table-wrap">
                <table className="optimization-r6-table">
                  <thead><tr><th>参数</th><th>周期</th><th>线性误差</th><th>样本</th><th>OOD</th><th>状态</th></tr></thead>
                  <tbody>
                    {(recommendations?.candidates ?? []).map((candidate) => (
                      <tr key={candidate.candidateId} className={candidate.candidateId === selected?.candidateId ? "selected" : ""} onClick={() => setSelectedId(candidate.candidateId)}>
                        <td><button type="button" onClick={() => setSelectedId(candidate.candidateId)}>F{number(candidate.parameterSet.values.feedOverride, 2)} · {number(candidate.parameterSet.values.samplePeriod, 2)}s</button></td>
                        <td>{number(candidate.objectives.cycleTimeSeconds)}s</td>
                        <td>{number(candidate.objectives.linearFollowingErrorMaxMm)}mm</td>
                        <td>{candidate.objectives.commandSampleCount}</td>
                        <td>{percent(candidate.oodFraction)}</td>
                        <td><span className={candidate.paretoOptimal ? "status-positive" : candidate.goalFeasible ? "status-neutral" : "status-negative"}>{candidate.paretoOptimal ? "Pareto" : candidate.goalFeasible ? "Dominated" : "Goal blocked"}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {selected && <div className="optimization-r6-detail-grid">
              <section className="report-card">
                <div className="section-title compact"><span>02</span><h2>七个数学硬门</h2><em>7 / 7</em></div>
                <div className="optimization-r6-gates">
                  {selected.gateReceipts.map((gate) => <article key={gate.claimId}><span className={gate.status === "Supported" ? "status-positive" : "status-negative"}>●</span><div><strong>{gate.claimId.replace("five-axis.", "").replace("-claim@1", "")}</strong><small title={gate.evidenceContentHash}>{shortHash(gate.evidenceContentHash)}</small></div></article>)}
                </div>
              </section>
              <section className="report-card">
                <div className="section-title compact"><span>03</span><h2>推荐解释</h2><em>{selected.permissionLevel}</em></div>
                <p>{selected.explanation}</p>
                <dl className="data-list compact-list">
                  <div><dt>Goal feasible</dt><dd className={selected.goalFeasible ? "status-positive" : "status-negative"}>{String(selected.goalFeasible)}</dd></div>
                  <div><dt>Epistemic</dt><dd>{selected.epistemicStatus}</dd></div>
                  <div><dt>Promotion</dt><dd className="status-neutral">blocked</dd></div>
                  <div><dt>Device write</dt><dd className="status-negative">false</dd></div>
                </dl>
              </section>
            </div>}

            <section className="report-card optimization-r6-plan">
              <div className="section-title compact"><span>04</span><h2>验证与回滚计划</h2><em>not an acceptance record</em></div>
              <div className="optimization-r6-plan-grid">
                <div><strong>Remaining gates</strong><ol>{recommendations?.validationPlan.remainingGates.map((item) => <li key={item}>{item}</li>)}</ol></div>
                <div><strong>Stop conditions</strong><ol>{recommendations?.validationPlan.stopConditions.map((item) => <li key={item}>{item}</li>)}</ol></div>
              </div>
              <footer><span>Rollback</span><code>{recommendations?.validationPlan.rollbackParameterSetId ?? "—"}</code><strong>OFFLINE · NO WRITE</strong></footer>
            </section>
          </div>
        </section>
      </main>
      <footer className="statusbar optimization-r6-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domain: <code>{manifest?.domainPackId ?? "optimization.domain-pack@1"}</code></span><span className="statusbar-right">{recommendations ? shortHash(recommendations.contentHash) : "loading"} · Offline only</span></footer>
    </>
  );
}
