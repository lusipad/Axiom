import { useEffect, useMemo, useState } from "react";

import type { Catalog, Claim } from "../../types";
import {
  executeF4Example,
  loadF4Example,
  loadF4Manifest,
  loadF4Scenarios,
} from "./api";
import type {
  F4ExamplePayload,
  F4MathStageManifest,
  F4RunBundle,
  F4ScenarioSummary,
  M5CollisionIntervalResult,
} from "./types";
import "./styles.css";

const GATE_CLAIM_IDS = [
  "five-axis.geometry-valid-claim@1",
  "five-axis.task-geometry-collision-free-claim@1",
  "five-axis.kinematically-feasible-claim@1",
  "five-axis.configuration-collision-free-claim@1",
  "five-axis.continuously-feasible-claim@1",
  "five-axis.interval-certified-claim@1",
  "five-axis.model-collision-free-claim@1",
] as const;

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function formatValue(value: unknown, digits = 4): string {
  if (typeof value !== "number") return "—";
  if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)) {
    return value.toExponential(3);
  }
  return value.toFixed(digits).replace(/\.?0+$/, "");
}

function resultClass(value?: string | boolean): string {
  if (
    value === true ||
    value === "Passed" ||
    value === "Succeeded" ||
    value === "Supported" ||
    value === "safe" ||
    value === "complete"
  ) {
    return "f3-status-positive";
  }
  if (
    value === false ||
    value === "Failed" ||
    value === "Unsupported" ||
    value === "Refuted" ||
    value === "collision" ||
    value === "unresolved" ||
    value === "Inconclusive"
  ) {
    return "f3-status-negative";
  }
  return "f3-status-neutral";
}

function downloadJson(filename: string, value: unknown): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function claimById(bundle: F4RunBundle | null, claimId: string): Claim | undefined {
  return bundle?.claims.find((item) => item.claimDefinitionId === claimId);
}

function intervalWitness(interval: M5CollisionIntervalResult): string {
  if (interval.witnessTime === undefined || interval.witnessTime === null) return "—";
  return `${formatValue(interval.witnessTime, 5)} s`;
}

function sortedIntervals(example: F4ExamplePayload | null): M5CollisionIntervalResult[] {
  return [...(example?.evidence.collisionVerification?.intervalEvaluations ?? [])].sort((left, right) => left.tStart - right.tStart);
}

export function F4Workbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<F4MathStageManifest | null>(null);
  const [summaries, setSummaries] = useState<F4ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState("canonical-dual-table-solver");
  const [example, setExample] = useState<F4ExamplePayload | null>(null);
  const [bundle, setBundle] = useState<F4RunBundle | null>(null);
  const [busy, setBusy] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runtimeBound = catalog?.domainPacks.find((item) => item.domainPackId === "five-axis.domain-pack@5")?.runtimeBound;
  const displayedManifest = example?.manifest ?? manifest;
  const canExecute = Boolean(example?.runSpec);
  const scenarioResult = example?.evidence.scenarioResult;
  const acceptanceReport = example?.acceptanceReport;
  const intervals = useMemo(() => sortedIntervals(example), [example]);
  const gateClaims = GATE_CLAIM_IDS.map((claimId) => claimById(bundle, claimId)).filter(Boolean) as Claim[];

  const loadScenario = async (scenarioId: string, active?: { value: boolean }) => {
    setBusy(true);
    setError(null);
    setBundle(null);
    try {
      const next = await loadF4Example(scenarioId);
      if (active && !active.value) return;
      setExample(next);
      setManifest(next.manifest);
      setSelectedId(scenarioId);
    } catch (reason) {
      if (!active || active.value) {
        setExample(null);
        setError(reason instanceof Error ? reason.message : "Five-Axis F4 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  const executeGate = async () => {
    if (!example?.runSpec) return;
    setExecuting(true);
    setError(null);
    try {
      const next = await executeF4Example(example);
      setBundle(next);
    } catch (reason) {
      setBundle(null);
      setError(reason instanceof Error ? reason.message : "F4 门禁执行失败。");
    } finally {
      setExecuting(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextSummaries] = await Promise.all([loadF4Manifest(), loadF4Scenarios()]);
        if (!active.value) return;
        setManifest(nextManifest);
        setSummaries(nextSummaries);
        const defaultId = nextSummaries.some((item) => item.scenarioId === "canonical-dual-table-solver")
          ? "canonical-dual-table-solver"
          : nextSummaries[0]?.scenarioId;
        if (!defaultId) throw new Error("F4 场景目录为空。");
        await loadScenario(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "Five-Axis F4 初始化失败。");
          setBusy(false);
        }
      }
    })();
    return () => {
      active.value = false;
    };
  }, []);

  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          <strong>F4 未完成</strong><span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="关闭错误">×</button>
        </div>
      )}

      <main className="workspace f3-workspace f4-workspace">
        <aside className="config-panel f3-config-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">F4 GATE LAB</span>
              <h1>F4 门禁工作台</h1>
            </div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>版本化场景</h2><em>{summaries.length || "—"}</em></div>
            <label className="field-label" htmlFor="f4-scenario">场景</label>
            <select id="f4-scenario" value={selectedId} onChange={(event) => void loadScenario(event.target.value)} disabled={busy || executing}>
              {summaries.map((item) => (
                <option key={item.scenarioId} value={item.scenarioId}>{item.title}</option>
              ))}
            </select>
            <p className="f3-scenario-description">{example?.scenario.description ?? "正在加载 F4 solver 门禁场景…"}</p>
            <button
              className="button button-primary f3-run-button"
              type="button"
              onClick={() => void executeGate()}
              disabled={busy || executing || !canExecute}
            >
              {executing ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
              {executing ? "门禁执行中" : "执行 F4 门禁"}
            </button>
            {canExecute ? (
              <p className="f4-scenario-note f4-note-positive">正向场景会提交 frozen RunSpec，并返回七个数学 claim 的 RunBundle。</p>
            ) : (
              <p className="f4-scenario-note">只验证失败行为，不计入闭环。</p>
            )}
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>Stage Acceptance</h2><em>{acceptanceReport?.status ?? "—"}</em></div>
            <div className="f4-coverage-grid">
              {(acceptanceReport?.topologyCoverage ?? []).map((item) => (
                <article key={item.topology} className="f4-coverage-card">
                  <span>topology</span>
                  <strong>{item.topology}</strong>
                  <small className={resultClass(item.covered)}>{item.covered ? "covered" : "missing"}</small>
                </article>
              ))}
              {(acceptanceReport?.counterexampleCoverage ?? []).map((item) => (
                <article key={item.counterexampleId} className="f4-coverage-card">
                  <span>counterexample</span>
                  <strong>{item.counterexampleId}</strong>
                  <small className={resultClass(item.covered)}>{item.covered ? "covered" : "missing"}</small>
                </article>
              ))}
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>Adapter Subjects</h2><em>{scenarioResult?.sutMode ?? "—"}</em></div>
            <div className="f4-subject-grid">
              <article className="f4-subject-card">
                <span>reference</span>
                <strong>{example?.artifacts.referenceInvocation.descriptor.subjectId ?? "—"}</strong>
                <small className={resultClass(example?.evidence.referenceReceipt.status)}>
                  {example?.evidence.referenceReceipt.status ?? "Not run"}
                </small>
                <code>{example?.artifacts.referenceInvocation.descriptor.subjectVersion ?? "—"}</code>
              </article>
              <article className="f4-subject-card">
                <span>sut</span>
                <strong>{example?.artifacts.sutInvocation.descriptor.subjectId ?? "—"}</strong>
                <small className={resultClass(example?.evidence.sutReceipt.status)}>
                  {example?.evidence.sutReceipt.status ?? "Not run"}
                </small>
                <code>{example?.artifacts.sutInvocation.descriptor.subjectVersion ?? "—"}</code>
              </article>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>04</span><h2>Manifest 绑定</h2><em>{displayedManifest?.stage ?? "—"}</em></div>
            <dl className="f3-manifest-list">
              <div><dt>Manifest</dt><dd title={displayedManifest?.manifestId}>{shortHash(displayedManifest?.manifestId)}</dd></div>
              <div><dt>Fixture</dt><dd title={displayedManifest?.fixtureContentIds[0]}>{shortHash(displayedManifest?.fixtureContentIds[0])}</dd></div>
              <div><dt>Policy</dt><dd title={displayedManifest?.policyIds.join(", ")}>{shortHash(displayedManifest?.policyIds[0])}</dd></div>
              <div><dt>RunSpec</dt><dd>{canExecute ? "available" : "counterexample only"}</dd></div>
            </dl>
          </section>
        </aside>

        <section className="analysis-panel f3-analysis-panel">
          <div className="analysis-heading f3-analysis-heading">
            <div className="f3-heading-copy">
              <span className="eyebrow">REFERENCE / SUT / COLLISION GATE</span>
              <h2>{example?.scenario.title ?? "F4 Gate Lab"}</h2>
            </div>
            <div className="run-state f3-run-state">
              <span className={resultClass(acceptanceReport?.status)}>stage: {acceptanceReport?.status ?? "Pending"}</span>
              <span className={resultClass(bundle?.run.executionStatus)}>{bundle?.run.executionStatus ? `execution: ${bundle.run.executionStatus}` : "execution: Not run"}</span>
              <span className="f3-boundary-chip">MATH ONLY / NOT DEVICE SAFE</span>
            </div>
          </div>

          <div className="f3-analysis-body">
            <section className="f3-boundary-banner" role="note">
              <div>
                <span>REFERENCE/SUT CROSS GATE</span>
                <strong>F4 只验证 solver 适配器、一致性与重建碰撞门禁</strong>
              </div>
              <p>正向场景闭合三拓扑与七个数学门；反例只证明失败行为，不生成闭环通过结论。</p>
            </section>

            <section className="f3-hero-card">
              <header>
                <div>
                  <span className="eyebrow">STAGE ACCEPTANCE</span>
                  <h3>{acceptanceReport?.status ?? "Pending"}</h3>
                </div>
                <div className="f3-hero-meta">
                  <span className={resultClass(scenarioResult?.outcome)}>{scenarioResult?.outcome ?? "—"}</span>
                  <code>{scenarioResult?.scenarioId ?? "—"}</code>
                </div>
              </header>
              <div className="f4-gap-grid">
                <article className="f4-gap-card">
                  <span>position gap</span>
                  <strong>{formatValue(example?.evidence.crossValidation?.maxPositionGap, 6)}</strong>
                  <code>{example?.evidence.crossValidation?.status ?? "—"}</code>
                </article>
                <article className="f4-gap-card">
                  <span>velocity gap</span>
                  <strong>{formatValue(example?.evidence.crossValidation?.maxVelocityGap, 6)}</strong>
                  <code>{example?.evidence.crossValidation?.status ?? "—"}</code>
                </article>
                <article className="f4-gap-card">
                  <span>acceleration gap</span>
                  <strong>{formatValue(example?.evidence.crossValidation?.maxAccelerationGap, 6)}</strong>
                  <code>{example?.evidence.crossValidation?.status ?? "—"}</code>
                </article>
                <article className="f4-gap-card">
                  <span>jerk gap</span>
                  <strong>{formatValue(example?.evidence.crossValidation?.maxJerkGap, 6)}</strong>
                  <code>{example?.evidence.crossValidation?.status ?? "—"}</code>
                </article>
              </div>
            </section>

            <section className="f3-section">
              <div className="section-title compact"><span>02</span><h2>Receipts</h2><em>{scenarioResult?.topology ?? "—"}</em></div>
              <div className="f4-subject-grid">
                <article className="f4-subject-card">
                  <span>reference receipt</span>
                  <strong>{example?.evidence.referenceReceipt.descriptor.adapterId ?? "—"}</strong>
                  <small className={resultClass(example?.evidence.referenceReceipt.status)}>
                    {example?.evidence.referenceReceipt.status ?? "—"}
                  </small>
                  <code>{shortHash(example?.evidence.referenceReceipt.outputContentHash)}</code>
                </article>
                <article className="f4-subject-card">
                  <span>sut receipt</span>
                  <strong>{example?.evidence.sutReceipt.descriptor.adapterId ?? "—"}</strong>
                  <small className={resultClass(example?.evidence.sutReceipt.status)}>
                    {example?.evidence.sutReceipt.status ?? "—"}
                  </small>
                  <code>{shortHash(example?.evidence.sutReceipt.outputContentHash)}</code>
                </article>
              </div>
            </section>

            <section className="f3-section">
              <div className="section-title compact"><span>03</span><h2>M5 Collision</h2><em>{example?.evidence.collisionVerification?.status ?? "—"}</em></div>
              <div className="f3-policy-strip">
                <div><span>status</span><strong className={resultClass(example?.evidence.collisionVerification?.status)}>{example?.evidence.collisionVerification?.status ?? "—"}</strong></div>
                <div><span>coverage</span><strong>{example?.evidence.collisionVerification?.coverageStatus ?? "—"}</strong></div>
                <div><span>aggregate</span><strong>{example?.evidence.collisionVerification?.supportsModelCollisionAggregation ? "supported" : "blocked"}</strong></div>
                <div><span>evidence</span><strong>{example?.evidence.collisionVerification?.evidenceLevel ?? "—"}</strong></div>
              </div>
              <div className="f3-table-wrap">
                <table className="compact-table f4-collision-table">
                  <thead>
                    <tr>
                      <th>interval</th>
                      <th>t</th>
                      <th>status</th>
                      <th>witness</th>
                      <th>clearance lb</th>
                      <th>reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {intervals.map((interval) => (
                      <tr key={interval.intervalId}>
                        <td><code>{interval.intervalId}</code></td>
                        <td>{formatValue(interval.tStart, 4)} → {formatValue(interval.tEnd, 4)}</td>
                        <td className={resultClass(interval.status)}>{interval.status}</td>
                        <td>{intervalWitness(interval)}</td>
                        <td>{formatValue(interval.minimumClearanceLowerBound, 6)}</td>
                        <td>{interval.reasonCode ?? "—"}</td>
                      </tr>
                    ))}
                    {!intervals.length && <tr><td className="f3-empty-row" colSpan={6}>暂无 M5 collision interval。</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="f3-section">
              <div className="section-title compact"><span>04</span><h2>RunBundle Claims</h2><em>{gateClaims.length}/7</em></div>
              {bundle ? (
                <div className="claims-list f4-claims-list">
                  {gateClaims.map((claim) => (
                    <article key={claim.claimDefinitionId}>
                      <header>
                        <strong className={resultClass(claim.status)}>{claim.status}</strong>
                        <span>{claim.evidence?.level ?? "—"}</span>
                      </header>
                      <p>{claim.predicate}</p>
                      <footer>
                        <code>{claim.claimDefinitionId}</code>
                        <span>{claim.evidence?.method ?? claim.metricId ?? "—"}</span>
                      </footer>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="f3-empty-panel">执行 F4 门禁后才会显示七个数学 claim。</div>
              )}
            </section>
          </div>

          <section className="f3-summary-strip" aria-label="F4 核心结论">
            <article className={`f3-metric-card ${resultClass(acceptanceReport?.status)}`}>
              <span>StageAcceptance</span>
              <strong>{acceptanceReport?.status ?? "Pending"}</strong>
              <small>{acceptanceReport?.scenarioResults.length ?? 0} scenarios</small>
            </article>
            <article className={`f3-metric-card ${resultClass(example?.evidence.crossValidation?.status)}`}>
              <span>CrossValidation</span>
              <strong>{example?.evidence.crossValidation?.status ?? "—"}</strong>
              <small>{example?.evidence.crossValidation?.method ?? "no cross result"}</small>
            </article>
            <article className={`f3-metric-card ${resultClass(example?.evidence.collisionVerification?.status)}`}>
              <span>M5Collision</span>
              <strong>{example?.evidence.collisionVerification?.status ?? "—"}</strong>
              <small>{example?.evidence.collisionVerification?.method ?? "no collision result"}</small>
            </article>
            <article className={`f3-metric-card ${resultClass(canExecute)}`}>
              <span>Closure</span>
              <strong>{scenarioResult?.countsTowardClosure ? "counts" : "excluded"}</strong>
              <small>{canExecute ? "runSpec available" : "counterexample only"}</small>
            </article>
          </section>
        </section>

        <aside className="evidence-panel f3-evidence-panel">
          <div className="panel-heading evidence-heading">
            <div>
              <span className="eyebrow">SEALED F4 OUTPUT</span>
              <h2>门禁证据</h2>
            </div>
            <button
              className="icon-button"
              type="button"
              onClick={() => example && downloadJson(`${selectedId}-f4-example.json`, example)}
              disabled={!example}
              title="下载 F4 证据 JSON"
            >
              ⇩
            </button>
          </div>

          <section className="verdict-card f3-verdict-card">
            <span className="eyebrow">F4 VERDICT</span>
            <div className="verdict-row"><strong className={resultClass(scenarioResult?.outcome)}>{scenarioResult?.outcome ?? "Pending"}</strong><span>{example?.scenario.title ?? "等待场景"}</span></div>
            <div className="verdict-rule"><i /><span>Runtime binding</span><b className={resultClass(runtimeBound)}>{runtimeBound ? "Bound" : "Missing"}</b></div>
            <div className="verdict-rule"><i /><span>Stage acceptance</span><b className={resultClass(acceptanceReport?.status)}>{acceptanceReport?.status ?? "—"}</b></div>
            <div className="verdict-rule"><i /><span>Closure</span><b>{scenarioResult?.countsTowardClosure ? "Counts toward closure" : "Counterexample only"}</b></div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>01</span><h2>冻结身份</h2></div>
            <dl className="identity-list">
              <div><dt>Manifest</dt><dd title={displayedManifest?.manifestId}>{shortHash(displayedManifest?.manifestId)}</dd></div>
              <div><dt>AxisPath</dt><dd title={example?.artifacts.axisPath.axisPathId}>{shortHash(example?.artifacts.axisPath.axisPathId)}</dd></div>
              <div><dt>Reference M5</dt><dd title={example?.artifacts.referenceCommand?.contentId}>{shortHash(example?.artifacts.referenceCommand?.contentId)}</dd></div>
              <div><dt>SUT M5</dt><dd title={example?.artifacts.sutCommand?.contentId}>{shortHash(example?.artifacts.sutCommand?.contentId)}</dd></div>
            </dl>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>02</span><h2>Stage Coverage</h2></div>
            <div className="claims-list f4-claims-list">
              {(acceptanceReport?.topologyCoverage ?? []).map((item) => (
                <article key={item.topology}>
                  <header>
                    <strong className={resultClass(item.covered)}>{item.covered ? "covered" : "missing"}</strong>
                    <span>topology</span>
                  </header>
                  <p>{item.topology}</p>
                  <footer><code>{item.topology}</code><span>{acceptanceReport?.status ?? "—"}</span></footer>
                </article>
              ))}
              {(acceptanceReport?.counterexampleCoverage ?? []).map((item) => (
                <article key={item.counterexampleId}>
                  <header>
                    <strong className={resultClass(item.covered)}>{item.covered ? "covered" : "missing"}</strong>
                    <span>counterexample</span>
                  </header>
                  <p>{item.counterexampleId}</p>
                  <footer><code>{item.counterexampleId}</code><span>negative path</span></footer>
                </article>
              ))}
            </div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>03</span><h2>Gate Claims</h2></div>
            <div className="claims-list f4-claims-list">
              {(bundle?.claims ?? []).filter((item) => GATE_CLAIM_IDS.includes(item.claimDefinitionId as typeof GATE_CLAIM_IDS[number])).map((item) => (
                <article key={item.claimDefinitionId}>
                  <header>
                    <strong className={resultClass(item.status)}>{item.status}</strong>
                    <span>{item.evidence?.level ?? "—"}</span>
                  </header>
                  <p>{item.predicate}</p>
                  <footer><code>{item.claimDefinitionId}</code><span>{item.evidence?.method ?? "—"}</span></footer>
                </article>
              ))}
              {!bundle && <div className="f3-empty-panel">尚未执行 F4 RunBundle。</div>}
            </div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>04</span><h2>执行链</h2></div>
            <ol className="execution-chain">
              <li className={displayedManifest ? "done" : ""}><span>Manifest loaded</span><code>{shortHash(displayedManifest?.manifestId)}</code></li>
              <li className={example ? "done" : ""}><span>Scenario materialized</span><code>{example?.scenario.scenarioId ?? "pending"}</code></li>
              <li className={example?.evidence.crossValidation ? "done" : ""}><span>Reference/SUT cross checked</span><code>{example?.evidence.crossValidation?.status ?? "pending"}</code></li>
              <li className={example?.evidence.collisionVerification ? "done" : ""}><span>M5 collision verified</span><code>{example?.evidence.collisionVerification?.status ?? "pending"}</code></li>
            </ol>
            {!canExecute && <span className="f4-counterexample-chip">只验证失败行为，不计入闭环</span>}
          </section>
        </aside>
      </main>

      <footer className="statusbar f3-statusbar">
        <span><i className={error ? "status-error" : ""} /> {error ? "1 error" : "0 errors"}</span>
        <span>domain: <code>five-axis.domain-pack@5</code></span>
        <span>runner: <code>five-axis.solver-adapter@1</code></span>
        <span className="statusbar-right">reference/sut · stage acceptance · M5 collision gate</span>
      </footer>
    </>
  );
}
