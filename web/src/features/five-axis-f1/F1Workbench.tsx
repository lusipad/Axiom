import { useEffect, useMemo, useState } from "react";

import type { Catalog, Claim, MetricResult } from "../../types";
import { executeF1Example, loadF1Example, loadF1Scenarios } from "./api";
import { PathPlot } from "./PathPlot";
import type { F1ExamplePayload, F1MathStageManifest, F1RunBundle, F1ScenarioSummary } from "./types";
import "./styles.css";

type F1View = "geometry" | "artifacts" | "collision" | "evidence";

const GEOMETRY_METRIC = "five-axis.geometry.valid@1";
const COLLISION_METRIC = "five-axis.task-geometry.collision-free@1";
const OVERCUT_METRIC = "five-axis.task-geometry.overcut-free@1";
const POSITION_METRIC = "five-axis.position.max-error@1";
const ORIENTATION_METRIC = "five-axis.orientation.max-error@1";
const CLEARANCE_METRIC = "five-axis.task-geometry.minimum-clearance@1";

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function formatValue(value: unknown, unit?: string): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value !== "number") return "—";
  const number = Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)
    ? value.toExponential(3)
    : value.toFixed(5).replace(/\.?0+$/, "");
  return `${number}${unit ? ` ${unit}` : ""}`;
}

function statusClass(value?: string | boolean): string {
  if (value === true || value === "Supported" || value === "Passed" || value === "Succeeded" || value === "Computed") {
    return "f1-status-pass";
  }
  if (value === false || value === "Refuted" || value === "Failed" || value === "Invalid" || value === "ExecutionFailed") {
    return "f1-status-fail";
  }
  return "f1-status-uncertain";
}

function metric(bundle: F1RunBundle | null, metricId: string): (MetricResult & { details?: Record<string, unknown> }) | undefined {
  return bundle?.report.metricResults.find((item) => item.metricId === metricId);
}

function metricLabel(item: MetricResult | undefined): string {
  if (!item) return "Pending";
  if (item.status !== "Computed") return item.reasonCode ?? item.status;
  return formatValue(item.value, item.unit);
}

function claim(bundle: F1RunBundle | null, metricId: string): Claim | undefined {
  return bundle?.claims.find((item) => item.metricId === metricId);
}

function evidenceLevel(item: MetricResult | undefined): string {
  return item?.evidence?.level ?? "No evidence";
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

function SummaryCard({ label, item, claimStatus }: { label: string; item?: MetricResult; claimStatus?: string }) {
  const status = claimStatus ?? (typeof item?.value === "boolean" ? item.value : item?.status);
  return (
    <article className={`f1-summary-card ${statusClass(status)}`}>
      <span>{label}</span>
      <strong>{claimStatus ?? metricLabel(item)}</strong>
      <small>{evidenceLevel(item)} · {item?.reasonCode ?? "closed"}</small>
    </article>
  );
}

function MetricTable({ bundle }: { bundle: F1RunBundle | null }) {
  return (
    <div className="f1-table-wrap">
      <table className="compact-table">
        <thead><tr><th>Metric</th><th>Status</th><th>Value</th><th>Evidence</th><th>Reason</th></tr></thead>
        <tbody>
          {(bundle?.report.metricResults ?? []).map((item) => (
            <tr key={item.metricId}>
              <td><code>{item.metricId}</code></td>
              <td className={statusClass(item.status)}>{item.status}</td>
              <td>{formatValue(item.value, item.unit)}</td>
              <td>{item.evidence?.level ?? "—"}</td>
              <td>{item.reasonCode ?? "—"}</td>
            </tr>
          ))}
          {!bundle && <tr><td colSpan={5} className="f1-empty-row">等待运行结果</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function BoundaryBanner() {
  return (
    <section className="f1-boundary-banner" role="note">
      <div><span>F1 MATH BOUNDARY</span><strong>仅验证数学任务几何</strong></div>
      <p>不是 DeviceSafe，也不表示机床可执行；M3 运动学、配置空间碰撞、驱动器与控制器约束尚未进入本阶段。</p>
    </section>
  );
}

export function F1Workbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<F1MathStageManifest | null>(null);
  const [summaries, setSummaries] = useState<F1ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState("nominal-certified");
  const [example, setExample] = useState<F1ExamplePayload | null>(null);
  const [bundle, setBundle] = useState<F1RunBundle | null>(null);
  const [view, setView] = useState<F1View>("geometry");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runtimeBound = catalog?.domainPacks.find((item) => item.domainPackId === "five-axis.domain-pack@2")?.runtimeBound;
  const geometryMetric = metric(bundle, GEOMETRY_METRIC);
  const collisionMetric = metric(bundle, COLLISION_METRIC);
  const overcutMetric = metric(bundle, OVERCUT_METRIC);
  const positionMetric = metric(bundle, POSITION_METRIC);
  const orientationMetric = metric(bundle, ORIENTATION_METRIC);
  const clearanceMetric = metric(bundle, CLEARANCE_METRIC);
  const geometryClaim = claim(bundle, GEOMETRY_METRIC);
  const collisionClaim = claim(bundle, COLLISION_METRIC);
  const correspondence = example?.artifacts.candidateGeometry.correspondence;
  const claimVerdict = [geometryClaim, collisionClaim].some((item) => item?.status === "Refuted")
    ? "Refuted"
    : [geometryClaim, collisionClaim].every((item) => item?.status === "Supported")
      ? "Supported"
      : bundle
        ? "Inconclusive"
        : "Pending";

  const loadAndRun = async (scenarioId: string, active?: { value: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      const next = await loadF1Example(scenarioId);
      if (active && !active.value) return;
      setManifest(next.manifest);
      setExample(next);
      setSelectedId(scenarioId);
      const nextBundle = await executeF1Example(next);
      if (active && !active.value) return;
      setBundle(nextBundle);
    } catch (reason) {
      if (!active || active.value) {
        setBundle(null);
        setError(reason instanceof Error ? reason.message : "Five-Axis F1 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const nextSummaries = await loadF1Scenarios();
        if (!active.value) return;
        setSummaries(nextSummaries);
        const defaultId = nextSummaries.some((item) => item.scenarioId === "nominal-certified")
          ? "nominal-certified"
          : nextSummaries[0]?.scenarioId;
        if (!defaultId) throw new Error("F1 场景目录为空。");
        await loadAndRun(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "Five-Axis F1 初始化失败。");
          setBusy(false);
        }
      }
    })();
    return () => { active.value = false; };
  }, []);

  const stageFacts = useMemo(() => {
    if (!example) return [];
    return [
      ["M0", `${example.source.normalizedProgram.events.length} normalized events`, example.source.normalizedProgram.programId],
      ["M1", `${example.source.referencePath.positionSegments.length} position / ${example.source.referencePath.orientationSegments.length} axis segments`, example.source.referencePath.referencePathId],
      ["M2", `${example.artifacts.candidateGeometry.correspondence.intervals.length} correspondence intervals`, example.artifacts.candidateGeometry.candidateGeometryId],
    ] as const;
  }, [example]);

  const rerun = async () => {
    if (!example) return;
    setBusy(true);
    setError(null);
    try {
      setBundle(await executeF1Example(example));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "F1 评估失败。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>F1 未完成</strong><span>{error}</span><button onClick={() => setError(null)} aria-label="关闭错误">×</button></div>}
      <main className="workspace f1-workspace">
        <aside className="config-panel">
          <div className="panel-heading">
            <div><span className="eyebrow">F1 REFERENCE STACK</span><h1>五轴数学场景</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>工程验证场景</h2><em>{summaries.length || "—"}</em></div>
            <label className="field-label" htmlFor="f1-scenario">场景</label>
            <select
              id="f1-scenario"
              value={selectedId}
              onChange={(event) => void loadAndRun(event.target.value)}
              disabled={busy}
            >
              {summaries.map((item) => <option key={item.scenarioId} value={item.scenarioId}>{item.title}</option>)}
            </select>
            <p className="f1-scenario-description">{example?.scenario.description ?? "正在加载版本化五轴场景…"}</p>
            <button className="button button-primary f1-run-button" type="button" onClick={rerun} disabled={busy || !example}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
              {busy ? "计算中" : "重新评估 F1"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>CL 指令入口</h2><em>{example?.source.normalizedProgram.sourceSyntaxId ?? "strict"}</em></div>
            <pre className="f1-source-code">{example?.source.sourceText ?? "UNITS/MM\nFROM/...\nGOTO/..."}</pre>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>M0 → M2 谱系</h2><em>typed</em></div>
            <ol className="f1-stage-chain">
              {stageFacts.map(([stage, summary, id]) => (
                <li key={stage}><b>{stage}</b><div><strong>{summary}</strong><code title={id}>{shortHash(id)}</code></div></li>
              ))}
            </ol>
          </section>
        </aside>

        <section className="analysis-panel f1-analysis-panel">
          <div className="analysis-heading">
            <div className="view-tabs" role="tablist" aria-label="Five-Axis F1 视图">
              {([
                ["geometry", "几何与对应"],
                ["artifacts", "M0 / M1 / M2"],
                ["collision", "碰撞与过程"],
                ["evidence", "指标证据"],
              ] as const).map(([id, label]) => (
                <button key={id} role="tab" aria-selected={view === id} onClick={() => setView(id)}>{label}</button>
              ))}
            </div>
            <div className="run-state">
              <span className={statusClass(bundle?.run.executionStatus)}>execution: {bundle?.run.executionStatus ?? "Not run"}</span>
              <span className={statusClass(bundle?.run.caseOutcome)}>case: {bundle?.run.caseOutcome ?? "Not run"}</span>
            </div>
          </div>

          <div className="f1-analysis-body">
            <BoundaryBanner />

            {view === "geometry" && example && (
              <div className="f1-geometry-view">
                <div className="f1-plot-toolbar">
                  <div>
                    <span className={`f1-domain-badge ${correspondence?.objectiveDomain === "continuous" ? "continuous" : "grid"}`}>
                      {correspondence?.objectiveDomain ?? "—"}
                    </span>
                    <span className="f1-evidence-badge">{correspondence?.evidenceLevel ?? "—"}</span>
                  </div>
                  <code>{correspondence?.policy.strategyId ?? "correspondence unavailable"}</code>
                </div>
                <PathPlot reference={example.source.referencePath} candidate={example.artifacts.candidateGeometry} />
                <div className="f1-correspondence-strip">
                  <div><span>Objective lower</span><strong>{formatValue(correspondence?.primaryObjectiveLower)}</strong></div>
                  <div><span>Objective upper</span><strong>{formatValue(correspondence?.primaryObjectiveUpper)}</strong></div>
                  <div><span>Intervals</span><strong>{correspondence?.intervals.length ?? "—"}</strong></div>
                  <div><span>Solver</span><strong title={correspondence?.solverVersion}>{shortHash(correspondence?.solverVersion)}</strong></div>
                </div>
              </div>
            )}

            {view === "artifacts" && example && (
              <div className="f1-scroll-view">
                <section className="f1-artifact-grid">
                  {manifest?.artifactDescriptors.map((descriptor) => (
                    <article key={descriptor.stage}>
                      <header><span>{descriptor.stage}</span><strong>{descriptor.artifactType}</strong></header>
                      <code>{descriptor.schemaId}</code>
                      <p>{stageFacts.find(([stage]) => stage === descriptor.stage)?.[1] ?? "—"}</p>
                    </article>
                  ))}
                </section>
                <section className="report-card">
                  <h3>M0 normalized events + lineage</h3>
                  <table className="compact-table"><thead><tr><th>#</th><th>Event</th><th>Position</th><th>Tool axis source</th><th>Statement</th></tr></thead>
                    <tbody>{example.source.normalizedProgram.events.map((event, index) => (
                      <tr key={event.eventId}><td>{index}</td><td>{event.eventType}</td><td>{event.position?.join(", ") ?? "—"}</td><td>{event.toolAxisSource ?? "—"}</td><td><code>{event.lineage.statementId}</code></td></tr>
                    ))}</tbody>
                  </table>
                </section>
                <section className="f1-fact-grid">
                  <article><span>PathProgress</span><strong>σ ∈ [0,1]</strong><small>{example.artifacts.candidateGeometry.pathProgress.mappings.length} gap-free mapping(s)</small></article>
                  <article><span>Regularity</span><strong>{example.artifacts.candidateGeometry.regularityCertificate?.requestedClass ?? "—"}</strong><small>{example.artifacts.candidateGeometry.nodeEvents.length} explicit node event(s)</small></article>
                  <article><span>Reference binding</span><strong>{shortHash(example.artifacts.candidateGeometry.sourceReferencePathContentId)}</strong><small>{example.artifacts.candidateGeometry.sourceReferencePathId}</small></article>
                </section>
              </div>
            )}

            {view === "collision" && example && (
              <div className="f1-scroll-view">
                <section className="f1-fact-grid">
                  {example.artifacts.candidateGeometry.collisionContext?.toolComponents.map((component) => (
                    <article key={component.componentId}><span>{component.componentKind}</span><strong>{component.shapeType} · r {component.radius}</strong><small>{component.componentId}</small></article>
                  ))}
                </section>
                <div className="f1-two-column">
                  <section className="report-card">
                    <h3>Explicit contact policy</h3>
                    <div className="f1-rule-list">
                      {example.artifacts.candidateGeometry.collisionContext?.contactPolicy.rules.map((rule) => (
                        <div key={rule.ruleId}><code>{rule.leftCategory} ↔ {rule.rightCategory}</code><strong className={statusClass(rule.contactPolicy === "allowed")}>{rule.contactPolicy}</strong></div>
                      ))}
                    </div>
                  </section>
                  <section className="report-card">
                    <h3>Process state chain</h3>
                    <ol className="execution-chain">
                      {example.artifacts.candidateGeometry.processStateTimeline?.intervals.map((interval) => (
                        <li className="done" key={interval.intervalId}><span>{interval.motionMode} · σ {interval.sigmaStart}→{interval.sigmaEnd}</span><code>{shortHash(interval.inputStockState.contentId)} → {shortHash(interval.outputStockState?.contentId)}</code></li>
                      ))}
                    </ol>
                  </section>
                </div>
                <section className="f1-fact-grid">
                  <SummaryCard label="Task collision free" item={collisionMetric} claimStatus={collisionClaim?.status} />
                  <SummaryCard label="Nominal overcut" item={overcutMetric} />
                  <SummaryCard label="Minimum clearance" item={clearanceMetric} />
                </section>
              </div>
            )}

            {view === "evidence" && <div className="f1-scroll-view"><MetricTable bundle={bundle} /></div>}
          </div>

          <section className="f1-summary-strip" aria-label="F1 核心结论">
            <SummaryCard label="GeometryValid" item={geometryMetric} claimStatus={geometryClaim?.status} />
            <SummaryCard label="TaskGeometryCollisionFree" item={collisionMetric} claimStatus={collisionClaim?.status} />
            <SummaryCard label="Position max" item={positionMetric} />
            <SummaryCard label="Orientation max" item={orientationMetric} />
            <SummaryCard label="Minimum clearance" item={clearanceMetric} />
          </section>
        </section>

        <aside className="evidence-panel">
          <div className="panel-heading evidence-heading">
            <div><span className="eyebrow">SEALED F1 OUTPUT</span><h2>声明与证据边界</h2></div>
            <button className="icon-button" type="button" title="下载 F1 RunBundle JSON" disabled={!bundle} onClick={() => bundle && downloadJson(`${bundle.run.runId}-f1.json`, bundle)}>⇩</button>
          </div>

          <section className="verdict-card f1-verdict-card">
            <span className="eyebrow">STANDARD CLAIM VERDICT</span>
            <div className="verdict-row"><strong className={statusClass(claimVerdict)}>{claimVerdict}</strong><span>范围：M0–M2</span></div>
            <div className="verdict-rule"><i /><span>Runtime bound</span><b className={statusClass(runtimeBound)}>{runtimeBound ? "yes" : "no"}</b></div>
            <div className="verdict-rule"><i /><span>Objective domain</span><b>{correspondence?.objectiveDomain ?? "—"}</b></div>
            <div className="verdict-rule"><i /><span>DeviceSafe</span><b className="f1-status-fail">NOT CLAIMED</b></div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>01</span><h2>标准声明</h2></div>
            <div className="claims-list">
              {[geometryClaim, collisionClaim].map((item, index) => item ? (
                <article key={item.claimId}><div><strong>{index ? "Task collision" : "Geometry"}</strong><em className={statusClass(item.status)}>{item.status}</em></div><p>{item.predicate}</p><footer><code>{shortHash(item.claimId)}</code><span>{item.evidence?.level ?? "—"}</span></footer></article>
              ) : <div className="empty-state" key={index}>声明尚未产生</div>)}
            </div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>02</span><h2>对应关系证书</h2></div>
            <dl className="identity-list">
              <div><dt>Certificate</dt><dd title={correspondence?.certificateId}>{shortHash(correspondence?.certificateId)}</dd></div>
              <div><dt>Source</dt><dd title={correspondence?.sourceGeometryId}>{shortHash(correspondence?.sourceGeometryId)}</dd></div>
              <div><dt>Reference</dt><dd title={correspondence?.targetReferencePathId}>{shortHash(correspondence?.targetReferencePathId)}</dd></div>
              <div><dt>Domain</dt><dd>{correspondence?.objectiveDomain ?? "—"}</dd></div>
              <div><dt>Evidence</dt><dd>{correspondence?.evidenceLevel ?? "—"}</dd></div>
            </dl>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>03</span><h2>冻结身份</h2></div>
            <dl className="identity-list">
              <div><dt>Fixture</dt><dd title={manifest?.fixtureContentIds[0]}>{shortHash(manifest?.fixtureContentIds[0])}</dd></div>
              <div><dt>Reference</dt><dd title={example?.artifacts.candidateGeometry.sourceReferencePathContentId}>{shortHash(example?.artifacts.candidateGeometry.sourceReferencePathContentId)}</dd></div>
              <div><dt>Run spec</dt><dd title={bundle?.run.runSpecHash}>{shortHash(bundle?.run.runSpecHash)}</dd></div>
              <div><dt>Report</dt><dd title={bundle?.run.reportContentHash}>{shortHash(bundle?.run.reportContentHash)}</dd></div>
              <div><dt>Bundle</dt><dd title={bundle?.bundleHash}>{shortHash(bundle?.bundleHash)}</dd></div>
            </dl>
          </section>
        </aside>
      </main>
      <footer className="statusbar f1-statusbar">
        <span><i className={error ? "status-error" : ""} /> {error ? "1 error" : "0 errors"}</span>
        <span>domain: <code>five-axis.domain-pack@2</code></span>
        <span>runner: <code>artifact-import@1</code></span>
        <span className="statusbar-right">F1 math only · M0/M1/M2 typed · no device claim</span>
      </footer>
    </>
  );
}
