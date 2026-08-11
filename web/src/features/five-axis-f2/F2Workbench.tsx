import { useEffect, useMemo, useState } from "react";

import type { Catalog, Claim, MetricResult } from "../../types";
import { AxisPlot } from "./AxisPlot";
import { executeF2Example, loadF2Example, loadF2Scenarios } from "./api";
import type {
  CollisionEvaluation,
  F2ExamplePayload,
  F2RunBundle,
  F2ScenarioSummary,
} from "./types";
import "./styles.css";

type F2View = "kinematics" | "branches" | "collision" | "evidence";

const KINEMATICS_METRIC = "five-axis.kinematically-feasible@1";
const COLLISION_METRIC = "five-axis.configuration-collision-free@1";
const POSITION_METRIC = "five-axis.position-residual.max@1";
const ORIENTATION_METRIC = "five-axis.orientation-residual.max@1";
const MARGIN_METRIC = "five-axis.axis-limit-margin.min@1";
const SINGULARITY_METRIC = "five-axis.singularity.minimum-singular-value@1";

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 20 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value;
}

function formatValue(value: unknown, unit?: string): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value !== "number") return "—";
  const rendered = Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)
    ? value.toExponential(3)
    : value.toFixed(5).replace(/\.?0+$/, "");
  return unit ? `${rendered} ${unit}` : rendered;
}

function statusClass(value?: string | boolean): string {
  if (value === true || ["Supported", "Passed", "Succeeded", "Computed", "safe", "active", "complete"].includes(String(value))) {
    return "f2-status-pass";
  }
  if (value === false || ["Refuted", "Failed", "collision", "terminated", "Invalid"].includes(String(value))) {
    return "f2-status-fail";
  }
  return "f2-status-uncertain";
}

function metric(bundle: F2RunBundle | null, metricId: string): MetricResult | undefined {
  return bundle?.report.metricResults.find((item) => item.metricId === metricId);
}

function claim(bundle: F2RunBundle | null, metricId: string): Claim | undefined {
  return bundle?.claims.find((item) => item.metricId === metricId);
}

function collisionEvaluation(bundle: F2RunBundle | null): CollisionEvaluation | undefined {
  const result = bundle?.report.metricResults.find((item) => item.metricId === COLLISION_METRIC) as (
    MetricResult & { details?: { collisionEvaluation?: CollisionEvaluation } }
  ) | undefined;
  return result?.details?.collisionEvaluation;
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

function BoundaryBanner() {
  return (
    <section className="f2-boundary-banner" role="note">
      <div><span>F2 MATH BOUNDARY</span><strong>M3 运动学与配置空间证据</strong></div>
      <p>结论只在冻结的 MachineProfile、分支策略与碰撞模型内成立；不是 DeviceSafe、ProcessSafe，也不是上机许可。</p>
    </section>
  );
}

function MetricCard({ title, item, claimStatus }: { title: string; item?: MetricResult; claimStatus?: string }) {
  const state = claimStatus ?? (typeof item?.value === "boolean" ? item.value : item?.status);
  return (
    <article className={`f2-metric-card ${statusClass(state)}`}>
      <span>{title}</span>
      <strong>{claimStatus ?? formatValue(item?.value, item?.unit)}</strong>
      <small>{item?.evidence?.level ?? "No evidence"} · {item?.reasonCode ?? "closed"}</small>
    </article>
  );
}

export function F2Workbench({ catalog }: { catalog: Catalog | null }) {
  const [summaries, setSummaries] = useState<F2ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState("canonical-table-table");
  const [example, setExample] = useState<F2ExamplePayload | null>(null);
  const [bundle, setBundle] = useState<F2RunBundle | null>(null);
  const [view, setView] = useState<F2View>("kinematics");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAndRun = async (scenarioId: string, active?: { value: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      const next = await loadF2Example(scenarioId);
      if (active && !active.value) return;
      setExample(next);
      setSelectedId(scenarioId);
      const nextBundle = await executeF2Example(next);
      if (active && !active.value) return;
      setBundle(nextBundle);
    } catch (reason) {
      if (!active || active.value) {
        setBundle(null);
        setError(reason instanceof Error ? reason.message : "Five-Axis F2 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const nextSummaries = await loadF2Scenarios();
        if (!active.value) return;
        setSummaries(nextSummaries);
        const defaultId = nextSummaries.some((item) => item.scenarioId === "canonical-table-table")
          ? "canonical-table-table"
          : nextSummaries[0]?.scenarioId;
        if (!defaultId) throw new Error("F2 场景目录为空。");
        await loadAndRun(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "Five-Axis F2 初始化失败。");
          setBusy(false);
        }
      }
    })();
    return () => { active.value = false; };
  }, []);

  const kinematicsMetric = metric(bundle, KINEMATICS_METRIC);
  const collisionMetric = metric(bundle, COLLISION_METRIC);
  const positionMetric = metric(bundle, POSITION_METRIC);
  const orientationMetric = metric(bundle, ORIENTATION_METRIC);
  const marginMetric = metric(bundle, MARGIN_METRIC);
  const singularityMetric = metric(bundle, SINGULARITY_METRIC);
  const kinematicsClaim = claim(bundle, KINEMATICS_METRIC);
  const configurationClaim = claim(bundle, COLLISION_METRIC);
  const collision = collisionEvaluation(bundle);
  const axisPath = example?.artifacts.axisPath;
  const profile = example?.artifacts.machineProfile;
  const certificate = axisPath?.kinematicsCertificate;
  const runtimeBound = catalog?.domainPacks.find((item) => item.domainPackId === "five-axis.domain-pack@3")?.runtimeBound;

  const selectedSolutions = useMemo(() => {
    if (!axisPath || !certificate) return [];
    return axisPath.ikSolutions
      .filter((item) => item.branchId === certificate.selectedBranchId)
      .sort((left, right) => left.sigma - right.sigma);
  }, [axisPath, certificate]);

  const selectedSegments = useMemo(() => {
    if (!axisPath || !certificate) return [];
    return axisPath.jointSegments.filter((item) => item.branchId === certificate.selectedBranchId);
  }, [axisPath, certificate]);

  const rerun = async () => {
    if (!example) return;
    setBusy(true);
    setError(null);
    try {
      setBundle(await executeF2Example(example));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "F2 评估失败。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>F2 未完成</strong><span>{error}</span><button onClick={() => setError(null)} aria-label="关闭错误">×</button></div>}
      <main className="workspace f2-workspace">
        <aside className="config-panel f2-config-panel">
          <div className="panel-heading">
            <div><span className="eyebrow">F2 KINEMATICS STACK</span><h1>五轴运动学实验室</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>版本化场景</h2><em>{summaries.length || "—"}</em></div>
            <label className="field-label" htmlFor="f2-scenario">场景</label>
            <select id="f2-scenario" value={selectedId} onChange={(event) => void loadAndRun(event.target.value)} disabled={busy}>
              {summaries.map((item) => <option key={item.scenarioId} value={item.scenarioId}>{item.title}</option>)}
            </select>
            <p className="f2-scenario-description">{example?.scenario.description ?? "正在加载 F2 运动学场景…"}</p>
            <button className="button button-primary f2-run-button" type="button" onClick={rerun} disabled={busy || !example}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
              {busy ? "独立复算中" : "重新验证 M3"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>MachineProfile</h2><em>{profile?.topology ?? "—"}</em></div>
            <code className="f2-profile-id" title={profile?.profileId}>{profile?.profileId ?? "profile pending"}</code>
            <ol className="f2-axis-list">
              {(profile?.axes ?? []).map((axis) => (
                <li key={axis.axisId}>
                  <b>{axis.axisId}</b>
                  <div><strong>{axis.semanticRole}</strong><span>{axis.installationSide} · {axis.jointType}</span></div>
                  <code>{axis.limits.lower.toFixed(2)}…{axis.limits.upper.toFixed(2)} {axis.limits.unit}</code>
                </li>
              ))}
            </ol>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>CL 输入</h2><em>strict</em></div>
            <pre className="f2-source-code">{example?.source.sourceText ?? "UNITS/MM\nFROM/...\nGOTO/..."}</pre>
          </section>
        </aside>

        <section className="analysis-panel f2-analysis-panel">
          <div className="analysis-heading">
            <div className="view-tabs" role="tablist" aria-label="Five-Axis F2 视图">
              {([
                ["kinematics", "连续轴路径"],
                ["branches", "分支 / Wrap"],
                ["collision", "Q_free 碰撞"],
                ["evidence", "证据与契约"],
              ] as const).map(([id, label]) => (
                <button key={id} role="tab" aria-selected={view === id} onClick={() => setView(id)}>{label}</button>
              ))}
            </div>
            <div className="run-state">
              <span className={statusClass(bundle?.run.executionStatus)}>execution: {bundle?.run.executionStatus ?? "Not run"}</span>
              <span className={statusClass(bundle?.run.caseOutcome)}>case: {bundle?.run.caseOutcome ?? "Not run"}</span>
              <button className="f2-sealed-chip" type="button" onClick={() => setView("evidence")}>
                M3 sealed · {bundle?.claims.length ?? 0}
              </button>
            </div>
          </div>

          <div className="f2-analysis-body">
            <BoundaryBanner />

            {view === "kinematics" && axisPath && profile && (
              <div className="f2-scroll-view">
                <div className="f2-summary-grid">
                  <MetricCard title="KinematicallyFeasible" item={kinematicsMetric} claimStatus={kinematicsClaim?.status} />
                  <MetricCard title="ConfigurationCollisionFree" item={collisionMetric} claimStatus={configurationClaim?.status} />
                </div>
                <section className="f2-plot-card">
                  <header>
                    <div><span className="eyebrow">SELECTED LIFT</span><h2>{certificate?.selectedBranchId}</h2></div>
                    <div><span>{selectedSegments.length} interval(s)</span><code>{certificate?.evidenceLevel}</code></div>
                  </header>
                  <AxisPlot axes={profile.axes} segments={selectedSegments} />
                </section>
                <div className="f2-bound-strip">
                  <div><span>Position replay</span><strong>{formatValue(positionMetric?.value, positionMetric?.unit)}</strong></div>
                  <div><span>Orientation replay</span><strong>{formatValue(orientationMetric?.value, orientationMetric?.unit)}</strong></div>
                  <div><span>Limit margin</span><strong>{formatValue(marginMetric?.value, marginMetric?.unit)}</strong></div>
                  <div><span>Singular value</span><strong>{formatValue(singularityMetric?.value)}</strong></div>
                </div>
              </div>
            )}

            {view === "branches" && axisPath && (
              <div className="f2-scroll-view">
                <section className="f2-branch-map">
                  {axisPath.branchGraph.branches.map((branch) => (
                    <article key={branch.branchId} className={`${statusClass(branch.status)} ${branch.branchId === certificate?.selectedBranchId ? "selected" : ""}`}>
                      <header><strong>{branch.branchId}</strong><span>{branch.status}</span></header>
                      <div className="f2-branch-track"><i style={{ left: `${branch.sigmaStart * 100}%`, width: `${(branch.sigmaEnd - branch.sigmaStart) * 100}%` }} /></div>
                      <footer><code>σ {branch.sigmaStart.toFixed(3)} → {branch.sigmaEnd.toFixed(3)}</code><span>{branch.solutionIds.length} knots</span></footer>
                    </article>
                  ))}
                </section>
                <section className="report-card">
                  <h3>选定分支端点解</h3>
                  <div className="f2-table-wrap"><table className="compact-table"><thead><tr><th>σ</th><th>Joint values</th><th>Wrap</th><th>Singularity</th><th>Limits</th></tr></thead>
                    <tbody>{selectedSolutions.map((solution) => (
                      <tr key={solution.solutionId}>
                        <td>{solution.sigma.toFixed(3)}</td>
                        <td><code>{solution.jointValues.map((value) => value.toFixed(4)).join(" · ")}</code></td>
                        <td>{solution.wrapState.map((item) => `${item.axisId}:${item.turns}`).join(", ") || "none"}</td>
                        <td className={statusClass(solution.singularity.status === "regular")}>{solution.singularity.status}</td>
                        <td className={statusClass(solution.withinLimits)}>{solution.withinLimits ? "within" : "violated"}</td>
                      </tr>
                    ))}</tbody>
                  </table></div>
                </section>
              </div>
            )}

            {view === "collision" && example && (
              <div className="f2-scroll-view">
                <section className="f2-collision-verdict">
                  <div>
                    <span className="eyebrow">CONTINUOUS Q_FREE</span>
                    <strong className={statusClass(collision?.status)}>{collision?.status ?? "Pending"}</strong>
                    <p>{collision?.reasonCode ?? "等待路径级配置空间验证"}</p>
                  </div>
                  <dl>
                    <div><dt>Coverage</dt><dd>{example.artifacts.collisionModel.coverageStatus}</dd></div>
                    <div><dt>Certificate</dt><dd>{collision?.certificateKind ?? "—"}</dd></div>
                    <div><dt>Clearance lower</dt><dd>{formatValue(collision?.minimumClearanceLowerBound, collision?.clearanceUnit)}</dd></div>
                    <div><dt>Subdivisions</dt><dd>{collision?.subdivisionCount ?? "—"}</dd></div>
                  </dl>
                </section>
                <section className="report-card">
                  <h3>显式碰撞对与区间证据</h3>
                  <div className="f2-table-wrap"><table className="compact-table"><thead><tr><th>Pair</th><th>Kind</th><th>Status</th><th>Clearance lower</th><th>Witness σ</th></tr></thead>
                    <tbody>{(collision?.pairResults ?? []).map((pair) => (
                      <tr key={pair.pairId}>
                        <td><code>{pair.pairId}</code></td><td>{pair.pairKind}</td>
                        <td className={statusClass(pair.status)}>{pair.status}</td>
                        <td>{formatValue(pair.minimumClearanceLowerBound, collision?.clearanceUnit)}</td>
                        <td className={pair.witnessSigma !== undefined ? "f2-status-fail" : ""}>{pair.witnessSigma?.toFixed(6) ?? "—"}</td>
                      </tr>
                    ))}</tbody>
                  </table></div>
                </section>
                <section className="f2-model-grid">
                  {example.artifacts.collisionModel.entities.map((entity) => (
                    <article key={entity.entityId}><span>{entity.entityKind}</span><strong>{entity.entityId}</strong><small>{entity.anchorType}{entity.anchorAxisId ? ` · ${entity.anchorAxisId}` : ""}</small></article>
                  ))}
                </section>
              </div>
            )}

            {view === "evidence" && example && (
              <div className="f2-scroll-view">
                <section className="f2-artifact-grid">
                  {example.manifest.artifactDescriptors.map((descriptor) => (
                    <article key={descriptor.stage}><b>{descriptor.stage}</b><div><strong>{descriptor.artifactType}</strong><code>{descriptor.schemaId}</code></div></article>
                  ))}
                </section>
                <section className="report-card">
                  <h3>Evaluator recomputation results</h3>
                  <div className="f2-table-wrap"><table className="compact-table"><thead><tr><th>Metric</th><th>Status</th><th>Value</th><th>Evidence</th><th>Reason</th></tr></thead>
                    <tbody>{(bundle?.report.metricResults ?? []).map((item) => (
                      <tr key={item.metricId}><td><code>{item.metricId}</code></td><td className={statusClass(item.status)}>{item.status}</td><td>{formatValue(item.value, item.unit)}</td><td>{item.evidence?.level ?? "—"}</td><td>{item.reasonCode ?? "—"}</td></tr>
                    ))}</tbody>
                  </table></div>
                </section>
                <section className="f2-policy-list">
                  <h3>Frozen methods and policies</h3>
                  {[certificate?.continuousMethod, ...(certificate?.policyIds ?? []), example.artifacts.collisionModel.policyId].filter(Boolean).map((item) => <code key={item}>{item}</code>)}
                </section>
              </div>
            )}
          </div>
        </section>

        <aside className="evidence-panel f2-evidence-panel">
          <div className="panel-heading evidence-heading">
            <div><span className="eyebrow">SEALED M3 OUTPUT</span><h2>声明与身份</h2></div>
            <button className="icon-button" type="button" onClick={() => bundle && downloadJson(`${selectedId}-f2-run-bundle.json`, bundle)} disabled={!bundle} title="下载 F2 证据 JSON">⇩</button>
          </div>
          <section className="verdict-card">
            <span className="eyebrow">STANDARD CLAIM VERDICT</span>
            <div className="verdict-row"><strong className={statusClass(bundle?.run.caseOutcome)}>{bundle?.run.caseOutcome ?? "Pending"}</strong><span>{bundle ? "独立复算完成" : "等待运行"}</span></div>
            <div className="verdict-rule"><i /><span>Runtime binding</span><b className={statusClass(runtimeBound)}>{runtimeBound ? "Bound" : "Missing"}</b></div>
            <div className="verdict-rule"><i /><span>Safety boundary</span><b>NOT DEVICE SAFE</b></div>
          </section>
          <section className="evidence-section">
            <div className="section-title compact"><span>01</span><h2>内容身份</h2></div>
            <dl className="identity-list">
              <div><dt>M2 geometry</dt><dd title={axisPath?.sourceCandidateGeometryContentId}>{shortHash(axisPath?.sourceCandidateGeometryContentId)}</dd></div>
              <div><dt>Machine</dt><dd title={axisPath?.machineProfileContentId}>{shortHash(axisPath?.machineProfileContentId)}</dd></div>
              <div><dt>Collision</dt><dd title={example?.artifacts.collisionModel.contentId}>{shortHash(example?.artifacts.collisionModel.contentId)}</dd></div>
              <div><dt>Bundle</dt><dd title={bundle?.bundleHash}>{shortHash(bundle?.bundleHash)}</dd></div>
            </dl>
          </section>
          <section className="evidence-section">
            <div className="section-title compact"><span>02</span><h2>标准声明</h2></div>
            <div className="f2-claim-list">
              {(bundle?.claims ?? []).filter((item) => item.metricId === KINEMATICS_METRIC || item.metricId === COLLISION_METRIC).map((item) => (
                <article key={item.claimId}><header><strong className={statusClass(item.status)}>{item.status}</strong><span>{item.evidence?.level ?? "—"}</span></header><p>{item.predicate}</p><code>{item.evidence?.method ?? "no method"}</code></article>
              ))}
              {!bundle && <div className="placeholder-lines"><i /><i /><i /></div>}
            </div>
          </section>
          <section className="evidence-section">
            <div className="section-title compact"><span>03</span><h2>证明闭包</h2></div>
            <ol className="execution-chain">
              <li className={axisPath ? "done" : ""}><span>Content hashes rebound</span><code>M2 + Profile</code></li>
              <li className={kinematicsMetric?.value === true ? "done" : ""}><span>FK replay + branch continuity</span><code>{certificate?.intervalCount ?? 0} interval(s)</code></li>
              <li className={collision?.queryKind === "path" ? "done" : ""}><span>Path-wide Q_free</span><code>{collision?.continuousMethod ?? "pending"}</code></li>
              <li><span>Device / controller</span><code>out of scope</code></li>
            </ol>
          </section>
        </aside>
      </main>
      <footer className="statusbar f2-statusbar">
        <span><i className={error ? "status-error" : ""} /> {error ? "1 error" : "0 errors"}</span>
        <span>domain: <code>five-axis.domain-pack@3</code></span>
        <span>stage: <code>Math F2 / M3</code></span>
        <span className="statusbar-right">{profile?.topology ?? "pending"} · mathematical evidence only</span>
      </footer>
    </>
  );
}
