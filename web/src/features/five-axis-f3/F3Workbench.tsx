import { useEffect, useMemo, useState } from "react";

import type { Catalog, Claim } from "../../types";
import { executeF3Example, loadF3Example, loadF3Manifest, loadF3Scenarios } from "./api";
import type {
  ContinuousTrajectorySpan,
  F3ExamplePayload,
  F3MathStageManifest,
  F3RunBundle,
  F3ScenarioSummary,
  M4ContinuousTrajectory,
  M5DiscreteCommand,
  M5ErrorLedgerEntry,
  M5SampledTrajectory,
  M5Sample,
} from "./types";
import "./styles.css";

const CONTINUOUS_CLAIM_ID = "five-axis.continuously-feasible-claim@1";
const INTERVAL_CLAIM_ID = "five-axis.interval-certified-claim@1";
const RECONSTRUCTION_POSITION_METRIC_ID = "five-axis.reconstruction-position-error.max@1";
const RECONSTRUCTION_ORIENTATION_METRIC_ID = "five-axis.reconstruction-orientation-error.max@1";

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
  if (value === true || value === "Supported" || value === "Succeeded" || value === "Accepted" || value === "Certified" || value === "ProvenOptimal") {
    return "f3-status-positive";
  }
  if (value === false || value === "Failed" || value === "Refuted" || value === "Unsupported" || value === "Inconclusive") {
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

function claimById(bundle: F3RunBundle | null, claimId: string): Claim | undefined {
  return bundle?.claims.find((item) => item.claimId === claimId);
}

function isM5ErrorLedgerEntry(value: unknown): value is M5ErrorLedgerEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Partial<M5ErrorLedgerEntry>;
  return typeof entry.quantity === "string"
    && typeof entry.unit === "string"
    && typeof entry.source === "string"
    && typeof entry.method === "string"
    && typeof entry.bound === "number";
}

function ledgerEntries(bundle: F3RunBundle | null): Array<M5ErrorLedgerEntry & { metricId: string }> {
  return bundle?.report.metricResults.flatMap((metric) => {
    if (metric.metricId !== RECONSTRUCTION_POSITION_METRIC_ID && metric.metricId !== RECONSTRUCTION_ORIENTATION_METRIC_ID) {
      return [];
    }
    const details = metric.details as { entries?: unknown } | undefined;
    if (!Array.isArray(details?.entries)) return [];
    return details.entries.filter(isM5ErrorLedgerEntry).map((entry) => ({ ...entry, metricId: metric.metricId }));
  }) ?? [];
}

function kinematicsLimits(profile?: F3ExamplePayload["artifacts"]["motionConstraintProfile"]) {
  return profile?.axisConstraints ?? [];
}

function timeSpanPoints(trajectory?: M4ContinuousTrajectory): Array<[number, number]> {
  if (!trajectory?.spans.length) return [];
  const points: Array<[number, number]> = [];
  trajectory.spans.forEach((span, index) => {
    if (index === 0) points.push([span.startTimeSeconds, span.sigmaStart]);
    points.push([span.endTimeSeconds, span.sigmaEnd]);
  });
  return points;
}

function sigmaPath(trajectory?: M4ContinuousTrajectory): string {
  const points = timeSpanPoints(trajectory);
  if (!points.length) return "";
  const times = points.map(([time]) => time);
  const sigmas = points.map(([, sigma]) => sigma);
  const minT = Math.min(...times);
  const maxT = Math.max(...times) || 1;
  const minSigma = Math.min(...sigmas);
  const maxSigma = Math.max(...sigmas) || 1;
  const spanT = maxT - minT || 1;
  const spanSigma = maxSigma - minSigma || 1;
  return points
    .map(([time, sigma], index) => {
      const x = 44 + ((time - minT) / spanT) * 556;
      const y = 250 - ((sigma - minSigma) / spanSigma) * 170;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function timeForSigma(trajectory: M4ContinuousTrajectory | undefined, sigma: number): number {
  if (!trajectory?.spans.length) return 0;
  const span = trajectory.spans.find((item) => sigma >= item.sigmaStart && sigma <= item.sigmaEnd)
    ?? trajectory.spans.find((item) => item.spanKind === "dwell")
    ?? trajectory.spans[trajectory.spans.length - 1]!;
  if (span.spanKind === "dwell" || Math.abs(span.sigmaEnd - span.sigmaStart) < 1e-12) return span.startTimeSeconds;
  const local = (sigma - span.sigmaStart) / (span.sigmaEnd - span.sigmaStart);
  return span.startTimeSeconds + local * (span.endTimeSeconds - span.startTimeSeconds);
}

function markerKind(eventType: string, boundaryMode?: string): "start" | "move" | "dwell" | "stop" | "restart" | "end" {
  if (boundaryMode === "dwell" || eventType.includes("dwell")) return "dwell";
  if (boundaryMode === "mandatory-stop" || eventType.includes("stop")) return "stop";
  if (eventType.includes("restart") || eventType.includes("resume")) return "restart";
  if (eventType.includes("start")) return "start";
  if (eventType.includes("end")) return "end";
  return "move";
}

function BoundaryBanner() {
  return (
    <section className="f3-boundary-banner" role="note">
      <div>
        <span>MATH ONLY / NOT DEVICE SAFE</span>
        <strong>F3 只证明连续时间与离散重建证书</strong>
      </div>
      <p>这不是设备安全、过程安全或控制器许可；所有结论都绑定冻结的时间律、重建策略、误差账本和 provenance。</p>
    </section>
  );
}

function MetricCard({ label, value, detail }: { label: string; value?: string; detail?: string }) {
  return (
    <article className={`f3-metric-card ${resultClass(value)}`}>
      <span>{label}</span>
      <strong>{value ?? "—"}</strong>
      <small>{detail ?? "closed"}</small>
    </article>
  );
}

function AxisCard({
  axis,
  usage,
}: {
  axis: NonNullable<ReturnType<typeof kinematicsLimits>>[number];
  usage?: M4ContinuousTrajectory["verification"]["axisConstraintUsage"][number];
}) {
  const peakV = usage?.maximumVelocity ?? 0;
  const peakA = usage?.maximumAcceleration ?? 0;
  const peakJ = usage?.maximumJerk ?? 0;
  const utilization = Math.max(
    usage ? peakV / axis.maximumVelocity : 0,
    usage ? peakA / axis.maximumAcceleration : 0,
    usage && axis.maximumJerk ? peakJ / axis.maximumJerk : 0,
  );
  return (
    <article className="f3-axis-card">
      <header>
        <div>
          <span>{axis.axisId}</span>
          <strong>{axis.unit}</strong>
        </div>
        <code>{formatValue(utilization * 100, 1)}%</code>
      </header>
      <div className="f3-axis-meter" aria-hidden="true">
        <span style={{ width: `${Math.min(100, utilization * 100)}%` }} />
      </div>
      <dl>
        <div><dt>V</dt><dd>{formatValue(peakV)} / {formatValue(axis.maximumVelocity)}</dd></div>
        <div><dt>A</dt><dd>{formatValue(peakA)} / {formatValue(axis.maximumAcceleration)}</dd></div>
        <div><dt>J</dt><dd>{formatValue(peakJ)} / {formatValue(axis.maximumJerk ?? 0)}</dd></div>
      </dl>
    </article>
  );
}

function TimelineRail({
  trajectory,
  axisPath,
}: {
  trajectory?: M4ContinuousTrajectory;
  axisPath?: F3ExamplePayload["artifacts"]["axisPath"];
}) {
  const nodes = axisPath?.nodeEvents ?? [];
  const maxTime = trajectory?.spans.at(-1)?.endTimeSeconds ?? 1;
  return (
    <div className="f3-timeline-rail" aria-hidden="true">
      {nodes.map((node) => (
        <div
          key={node.nodeId}
          className={`f3-timeline-marker kind-${markerKind(node.eventType)}`}
          style={{ left: `${(timeForSigma(trajectory, node.sigma) / maxTime) * 100}%` }}
          title={`${node.eventType} @ σ=${node.sigma}`}
        />
      ))}
      {(trajectory?.spans ?? []).filter((item) => item.spanKind === "dwell").map((span) => (
        <div
          key={span.spanId}
          className="f3-timeline-marker kind-dwell"
          style={{ left: `${(span.startTimeSeconds / maxTime) * 100}%`, width: `${((span.endTimeSeconds - span.startTimeSeconds) / maxTime) * 100}%` }}
          title={`dwell ${span.spanId}`}
        />
      ))}
      <span className="f3-timeline-start">0</span>
      <span className="f3-timeline-end">{formatValue(maxTime, 2)} s</span>
    </div>
  );
}

function samplesToLabel(sample: M5Sample): string {
  return `q=[${sample.q.map((item) => formatValue(item, 4)).join(", ")}]`;
}

export function F3Workbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<F3MathStageManifest | null>(null);
  const [summaries, setSummaries] = useState<F3ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState("canonical-table-table-jerk");
  const [example, setExample] = useState<F3ExamplePayload | null>(null);
  const [bundle, setBundle] = useState<F3RunBundle | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runtimeBound = catalog?.domainPacks.find((item) => item.domainPackId === "five-axis.domain-pack@4")?.runtimeBound;
  const displayedManifest = example?.manifest ?? manifest;
  const axisPath = example?.artifacts.axisPath;
  const profile = example?.artifacts.motionConstraintProfile;
  const trajectory = example?.artifacts.continuousTrajectory;
  const sampledTrajectory = example?.artifacts.sampledTrajectory;
  const discreteCommand = example?.artifacts.discreteCommand;
  const m5Artifact = sampledTrajectory ?? discreteCommand;
  const m5ArtifactId = sampledTrajectory?.sampledTrajectoryId ?? discreteCommand?.discreteCommandId;
  const continuousClaim = claimById(bundle, CONTINUOUS_CLAIM_ID);
  const intervalClaim = claimById(bundle, INTERVAL_CLAIM_ID);

  const loadAndRun = async (scenarioId: string, active?: { value: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      const next = await loadF3Example(scenarioId);
      if (active && !active.value) return;
      setExample(next);
      setManifest(next.manifest);
      setSelectedId(scenarioId);
      const nextBundle = await executeF3Example(next);
      if (active && !active.value) return;
      setBundle(nextBundle);
    } catch (reason) {
      if (!active || active.value) {
        setBundle(null);
        setError(reason instanceof Error ? reason.message : "Five-Axis F3 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextSummaries] = await Promise.all([loadF3Manifest(), loadF3Scenarios()]);
        if (!active.value) return;
        setManifest(nextManifest);
        setSummaries(nextSummaries);
        const defaultId = nextSummaries.some((item) => item.scenarioId === "canonical-table-table-jerk")
          ? "canonical-table-table-jerk"
          : nextSummaries[0]?.scenarioId;
        if (!defaultId) throw new Error("F3 场景目录为空。");
        await loadAndRun(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "Five-Axis F3 初始化失败。");
          setBusy(false);
        }
      }
    })();
    return () => { active.value = false; };
  }, []);

  const topLabel = example?.scenario.title ?? "Time & Sampling Lab";
  const claimVerdict = [continuousClaim, intervalClaim].some((item) => item?.status === "Refuted")
    ? "Refuted"
    : [continuousClaim, intervalClaim].every((item) => item?.status === "Supported")
      ? "Supported"
      : bundle
        ? "Inconclusive"
        : "Pending";
  const effectivePath = sigmaPath(trajectory);
  const nodeCards = axisPath?.nodeEvents.map((node) => {
    const nodeConstraint = profile?.nodeConstraints.find((item) => item.nodeId === node.nodeId || Math.abs(item.sigma - node.sigma) < 1e-9);
    return {
      ...node,
      kind: markerKind(node.eventType, nodeConstraint?.boundaryMode),
      boundaryMode: nodeConstraint?.boundaryMode,
      dwellSeconds: nodeConstraint?.dwellSeconds,
      rationale: nodeConstraint?.rationale,
      timeSeconds: timeForSigma(trajectory, node.sigma),
    };
  }) ?? [];
  const dwellSpans = trajectory?.spans.filter((item) => item.spanKind === "dwell") ?? [];
  const axisUsageMap = new Map(trajectory?.verification.axisConstraintUsage.map((item) => [item.axisId, item]) ?? []);

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>F3 未完成</strong><span>{error}</span><button type="button" onClick={() => setError(null)} aria-label="关闭错误">×</button></div>}
      <main className="workspace f3-workspace">
        <aside className="config-panel f3-config-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">F3 TIME & SAMPLING LAB</span>
              <h1>时域与采样实验室</h1>
            </div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>版本化场景</h2><em>{summaries.length || "—"}</em></div>
            <label className="field-label" htmlFor="f3-scenario">场景</label>
            <select id="f3-scenario" value={selectedId} onChange={(event) => void loadAndRun(event.target.value)} disabled={busy}>
              {summaries.map((item) => <option key={item.scenarioId} value={item.scenarioId}>{item.title}</option>)}
            </select>
            <p className="f3-scenario-description">{example?.scenario.description ?? "正在加载 F3 时间律场景…"}</p>
            <button className="button button-primary f3-run-button" type="button" onClick={() => void loadAndRun(selectedId)} disabled={busy || !selectedId}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
              {busy ? "计算中" : "重新评估 F3"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>约束绑定</h2><em>{profile?.profileId ?? "—"}</em></div>
            <code className="f3-profile-id" title={profile?.machineProfileContentId}>{shortHash(profile?.machineProfileContentId)}</code>
            <ol className="f3-axis-list">
              {kinematicsLimits(profile).map((axis) => (
                <li key={axis.axisId}>
                  <b>{axis.axisId}</b>
                  <div>
                    <strong>{axis.unit}</strong>
                    <span>mch {shortHash(profile?.machineProfileId)}</span>
                  </div>
                  <code>V {formatValue(axis.maximumVelocity)} · A {formatValue(axis.maximumAcceleration)} · J {formatValue(axis.maximumJerk ?? 0)}</code>
                </li>
              ))}
            </ol>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>M4 / M5 概要</h2><em>{trajectory?.timingMode ?? "—"}</em></div>
            <div className="f3-policy-card">
              <div>
                <span>solver</span>
                <strong>{trajectory?.solverId ?? "—"}</strong>
              </div>
              <div>
                <span>duration</span>
                <strong>{formatValue(trajectory?.verification.totalDurationSeconds ?? m5Artifact?.duration, 4)} s</strong>
              </div>
              <div>
                <span>sample period</span>
                <strong>{formatValue(m5Artifact?.samplePeriod, 5)} s</strong>
              </div>
              <div>
                <span>final hold</span>
                <strong>{m5Artifact ? (m5Artifact.finalHold ? "hold" : "drop") : "—"}</strong>
              </div>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>04</span><h2>Manifest 绑定</h2><em>{displayedManifest?.stage ?? "—"}</em></div>
            <dl className="f3-manifest-list">
              <div><dt>Manifest</dt><dd title={displayedManifest?.manifestId}>{shortHash(displayedManifest?.manifestId)}</dd></div>
              <div><dt>Fixture</dt><dd title={displayedManifest?.fixtureContentIds[0]}>{shortHash(displayedManifest?.fixtureContentIds[0])}</dd></div>
              <div><dt>Policy</dt><dd title={displayedManifest?.policyIds.join(", ")}>{shortHash(displayedManifest?.policyIds[0])}</dd></div>
              <div><dt>Claims</dt><dd>{displayedManifest?.expectedClaims.length ?? 0}</dd></div>
            </dl>
          </section>
        </aside>

        <section className="analysis-panel f3-analysis-panel">
          <div className="analysis-heading f3-analysis-heading">
            <div className="f3-heading-copy">
              <span className="eyebrow">TIME LAW / RECONSTRUCTION / ERROR LEDGER</span>
              <h2>{topLabel}</h2>
            </div>
            <div className="run-state f3-run-state">
              <span className={resultClass(bundle?.run.executionStatus)}>execution: {bundle?.run.executionStatus ?? "Not run"}</span>
              <span className={resultClass(bundle?.run.caseOutcome)}>case: {bundle?.run.caseOutcome ?? "Not run"}</span>
              <span className="f3-boundary-chip">MATH ONLY / NOT DEVICE SAFE</span>
            </div>
          </div>

          <div className="f3-analysis-body">
            <BoundaryBanner />

            <section className="f3-hero-card">
              <header>
                <div>
                  <span className="eyebrow">σ(t)</span>
                  <h3>{trajectory?.timingMode ?? "trajectory pending"}</h3>
                </div>
                <div className="f3-hero-meta">
                  <span className={resultClass(trajectory?.verification.overallStatus)}>{trajectory?.verification.overallStatus ?? "—"}</span>
                  <code>{trajectory?.trajectoryId ?? "—"}</code>
                </div>
              </header>
              <div className="f3-time-grid">
                <div className="f3-time-plot">
                  <svg viewBox="0 0 640 280" role="img" aria-label="sigma(t) 与时间分段">
                    <defs>
                      <pattern id="f3-grid" width="32" height="32" patternUnits="userSpaceOnUse">
                        <path d="M 32 0 L 0 0 0 32" className="f3-minor-grid" fill="none" />
                      </pattern>
                      <linearGradient id="f3-line" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor="var(--f3-accent-2)" />
                        <stop offset="100%" stopColor="var(--f3-accent)" />
                      </linearGradient>
                    </defs>
                    <rect width="640" height="280" fill="url(#f3-grid)" />
                    <line x1="40" y1="232" x2="604" y2="232" className="f3-axis-line" />
                    <line x1="44" y1="28" x2="44" y2="244" className="f3-axis-line" />
                    <path d={effectivePath} className="f3-time-path" />
                    {axisPath?.nodeEvents.map((node) => (
                      <circle
                        key={node.nodeId}
                        cx={44 + ((timeForSigma(trajectory, node.sigma) - (trajectory?.spans[0]?.startTimeSeconds ?? 0)) / (((trajectory?.spans.at(-1)?.endTimeSeconds ?? 1) - (trajectory?.spans[0]?.startTimeSeconds ?? 0)) || 1)) * 556}
                        cy={250 - (node.sigma / (Math.max(...(trajectory?.spans.flatMap((span) => [span.sigmaStart, span.sigmaEnd]) ?? [1])) || 1)) * 170}
                        r="3"
                        className={`f3-node-dot kind-${markerKind(node.eventType)}`}
                      />
                    ))}
                    <text x="592" y="250" className="f3-axis-label">t</text>
                    <text x="34" y="38" className="f3-axis-label">σ</text>
                  </svg>
                  <div className="f3-time-stats">
                    <div><span>duration</span><strong>{formatValue(trajectory?.verification.totalDurationSeconds ?? m5Artifact?.duration, 4)} s</strong></div>
                    <div><span>moving</span><strong>{formatValue((trajectory?.spans ?? []).filter((item) => item.spanKind === "move").reduce((sum, span) => sum + (span.endTimeSeconds - span.startTimeSeconds), 0), 4)} s</strong></div>
                    <div><span>dwell</span><strong>{formatValue((trajectory?.spans ?? []).filter((item) => item.spanKind === "dwell").reduce((sum, span) => sum + (span.endTimeSeconds - span.startTimeSeconds), 0), 4)} s</strong></div>
                    <div><span>samples</span><strong>{m5Artifact?.samples.length ?? 0}</strong></div>
                  </div>
                </div>

                <div className="f3-axis-stack">
                  {kinematicsLimits(profile).map((axis) => (
                    <AxisCard key={axis.axisId} axis={axis} usage={axisUsageMap.get(axis.axisId)} />
                  ))}
                </div>
              </div>
            </section>

            <section className="f3-section">
              <div className="section-title compact"><span>02</span><h2>Node / dwell 时间线</h2><em>{nodeCards.length} nodes</em></div>
              <TimelineRail trajectory={trajectory} axisPath={axisPath} />
              <div className="f3-node-grid">
                {nodeCards.map((item) => (
                  <article key={item.nodeId} className={`f3-node-card kind-${item.kind}`}>
                    <header>
                      <div>
                        <span>{item.kind}</span>
                        <strong>{item.eventType}</strong>
                      </div>
                      <code>{formatValue(item.timeSeconds, 3)} s</code>
                    </header>
                    <p>σ {formatValue(item.sigma, 5)}{item.dwellSeconds !== undefined ? ` · dwell ${formatValue(item.dwellSeconds, 3)} s` : ""}</p>
                    <footer>
                      <code>{item.leftSegmentId ?? "—"} → {item.rightSegmentId ?? "—"}</code>
                      <span>{item.rationale ?? item.boundaryMode ?? "profile"}</span>
                    </footer>
                  </article>
                ))}
              </div>
              {!!dwellSpans.length && (
                <div className="f3-dwell-strip">
                  {dwellSpans.map((span) => (
                    <article key={span.spanId}>
                      <span>{span.spanId}</span>
                      <strong>{formatValue(span.startTimeSeconds, 3)} s → {formatValue(span.endTimeSeconds, 3)} s</strong>
                      <small>σ {formatValue(span.sigmaStart, 5)} = {formatValue(span.sigmaEnd, 5)}</small>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="f3-section">
              <div className="section-title compact"><span>03</span><h2>采样 / 重建</h2><em>{m5Artifact?.samples.length ?? 0} samples</em></div>
              <div className="f3-policy-strip">
                <div><span>policy</span><strong>{m5Artifact?.reconstructionPolicy.policyId ?? "—"}</strong></div>
                <div><span>artifact</span><strong>{sampledTrajectory ? "sampled trajectory" : discreteCommand ? "discrete command" : "—"}</strong></div>
                <div><span>terminal</span><strong>{m5Artifact?.terminalSampleIncluded ? "included" : "missing"}</strong></div>
                <div><span>remainder</span><strong>{formatValue(m5Artifact?.remainderDuration, 5)} s</strong></div>
              </div>
              <div className="f3-table-wrap">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>t</th>
                      <th>cycle</th>
                      <th>σ</th>
                      <th>q</th>
                      <th>task pose</th>
                      <th>provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(m5Artifact?.samples ?? []).map((row) => (
                      <tr key={row.sampleId}>
                        <td>{row.sampleIndex}</td>
                        <td>{formatValue(row.t, 4)}</td>
                        <td>{row.cycle}</td>
                        <td>{formatValue(row.sigma, 5)}</td>
                        <td><code>{samplesToLabel(row)}</code></td>
                        <td><code>{row.taskPose.position.map((item) => formatValue(item, 4)).join(", ")}</code></td>
                        <td title={row.provenance.map((item) => `${item.sourceStage}:${item.sourceId}`).join(" | ")}>
                          {shortHash(row.provenance[0]?.sourceId)}
                        </td>
                      </tr>
                    ))}
                    {!m5Artifact?.samples.length && <tr><td className="f3-empty-row" colSpan={7}>暂无采样记录</td></tr>}
                  </tbody>
                </table>
              </div>
              <div className="f3-table-wrap top-gap">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>interval</th>
                      <th>t</th>
                      <th>σ</th>
                      <th>law</th>
                      <th>coefficients</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(m5Artifact?.intervals ?? []).map((interval) => (
                      <tr key={interval.intervalId}>
                        <td><code>{interval.intervalId}</code></td>
                        <td>{formatValue(interval.tStart, 4)} → {formatValue(interval.tEnd, 4)}</td>
                        <td>{formatValue(m5Artifact?.samples[interval.startSampleIndex]?.sigma ?? 0, 5)} → {formatValue(m5Artifact?.samples[interval.endSampleIndex]?.sigma ?? 0, 5)}</td>
                        <td>{interval.intervalSemantics}</td>
                        <td><code>{interval.certificateCoefficients[0].map((item) => formatValue(item, 3)).join(", ")} …</code></td>
                      </tr>
                    ))}
                    {!m5Artifact?.intervals.length && <tr><td className="f3-empty-row" colSpan={5}>暂无区间证书</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="f3-section">
              <div className="section-title compact"><span>04</span><h2>误差账本</h2><em>{ledgerEntries(bundle).length} items</em></div>
              <div className="f3-ledger-grid">
                {ledgerEntries(bundle).map((entry, index) => (
                  <article key={`${entry.metricId}-${entry.quantity}-${entry.source}-${index}`}>
                    <div>
                      <span>{entry.quantity}</span>
                      <strong>{formatValue(entry.bound, 6)} {entry.unit}</strong>
                    </div>
                    <p>{entry.method}</p>
                    <footer>
                      <code title={entry.metricId}>{shortHash(entry.metricId)}</code>
                      <span>{entry.axis !== undefined ? `axis ${entry.axis}` : entry.source}</span>
                    </footer>
                  </article>
                ))}
                {!ledgerEntries(bundle).length && <div className="f3-empty-panel">误差账本为空。</div>}
              </div>
            </section>
          </div>

          <section className="f3-summary-strip" aria-label="F3 核心结论">
            <MetricCard label="ContinuouslyFeasible" value={continuousClaim?.status ?? trajectory?.verification.overallStatus} detail={trajectory?.verification.evidenceLevel ?? "M4"} />
            <MetricCard label="IntervalCertified" value={intervalClaim?.status ?? m5Artifact?.reconstructionPolicy.policyId} detail={m5Artifact?.reconstructionPolicy.policyId} />
            <MetricCard label="Optimality" value={trajectory?.verification.optimality.classification} detail={trajectory?.verification.optimality.rationale} />
            <MetricCard label="Timing mode" value={trajectory?.timingMode} detail={trajectory?.solverId} />
          </section>
        </section>

        <aside className="evidence-panel f3-evidence-panel">
          <div className="panel-heading evidence-heading">
            <div>
              <span className="eyebrow">SEALED F3 OUTPUT</span>
              <h2>声明与 provenance</h2>
            </div>
            <button className="icon-button" type="button" onClick={() => bundle && downloadJson(`${selectedId}-f3-run-bundle.json`, bundle)} disabled={!bundle} title="下载 F3 证据 JSON">⇩</button>
          </div>

          <section className="verdict-card f3-verdict-card">
            <span className="eyebrow">CLAIM VERDICT</span>
            <div className="verdict-row"><strong className={resultClass(claimVerdict)}>{claimVerdict}</strong><span>范围：M4–M5</span></div>
            <div className="verdict-rule"><i /><span>Runtime binding</span><b className={resultClass(runtimeBound)}>{runtimeBound ? "Bound" : "Missing"}</b></div>
            <div className="verdict-rule"><i /><span>Safety boundary</span><b className="f3-status-negative">NOT DEVICE SAFE</b></div>
            <div className="verdict-rule"><i /><span>Manifest</span><b>{displayedManifest?.manifestId ?? "—"}</b></div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>01</span><h2>内容身份</h2></div>
            <dl className="identity-list">
              <div><dt>AxisPath</dt><dd title={axisPath?.axisPathId}>{shortHash(axisPath?.axisPathId)}</dd></div>
              <div><dt>M4</dt><dd title={trajectory?.trajectoryId}>{shortHash(trajectory?.trajectoryId)}</dd></div>
              <div><dt>M4 content</dt><dd title={m5Artifact?.sourceM4ContentId}>{shortHash(m5Artifact?.sourceM4ContentId)}</dd></div>
              <div><dt>M5 content</dt><dd title={m5Artifact?.contentId}>{shortHash(m5Artifact?.contentId)}</dd></div>
              <div><dt>M5 artifact</dt><dd title={m5ArtifactId}>{shortHash(m5ArtifactId)}</dd></div>
            </dl>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>02</span><h2>标准声明</h2></div>
            <div className="claims-list f3-claims-list">
              {(bundle?.claims ?? []).map((item) => (
                <article key={item.claimId}>
                  <header>
                    <strong className={resultClass(item.status)}>{item.status}</strong>
                    <span>{item.evidence?.level ?? "—"}</span>
                  </header>
                  <p>{item.predicate}</p>
                  <code>{item.evidence?.method ?? item.metricId ?? "no method"}</code>
                </article>
              ))}
              {!bundle && <div className="placeholder-lines"><i /><i /><i /></div>}
            </div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>03</span><h2>Manifest</h2></div>
            <dl className="f3-manifest-list">
              <div><dt>Manifest</dt><dd title={displayedManifest?.manifestId}>{shortHash(displayedManifest?.manifestId)}</dd></div>
              <div><dt>Profile</dt><dd title={displayedManifest?.motionConstraintProfileContentId}>{shortHash(displayedManifest?.motionConstraintProfileContentId)}</dd></div>
              <div><dt>Policies</dt><dd title={displayedManifest?.policyIds.join(", ")}>{shortHash(displayedManifest?.policyIds[0])}</dd></div>
              <div><dt>Claims</dt><dd>{displayedManifest?.expectedClaims.length ?? 0}</dd></div>
            </dl>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>04</span><h2>执行链</h2></div>
            <ol className="execution-chain">
              <li className={displayedManifest ? "done" : ""}><span>Manifest loaded</span><code>{shortHash(displayedManifest?.manifestId)}</code></li>
              <li className={profile ? "done" : ""}><span>Constraint profile bound</span><code>{shortHash(profile?.machineProfileContentId)}</code></li>
              <li className={trajectory ? "done" : ""}><span>Continuous trajectory evaluated</span><code>{trajectory?.timingMode ?? "pending"}</code></li>
              <li className={m5Artifact ? "done" : ""}><span>Sampling lane replayed</span><code>{m5Artifact?.reconstructionPolicy.policyId ?? "pending"}</code></li>
            </ol>
          </section>

          {discreteCommand && (
            <section className="evidence-section">
              <div className="section-title compact"><span>05</span><h2>Discrete command</h2></div>
              <dl className="identity-list">
                <div><dt>Command</dt><dd title={discreteCommand.discreteCommandId}>{shortHash(discreteCommand.discreteCommandId)}</dd></div>
                <div><dt>Policy</dt><dd>{discreteCommand.reconstructionPolicy.policyId}</dd></div>
                <div><dt>Final hold</dt><dd>{discreteCommand.finalHold ? "true" : "false"}</dd></div>
                <div><dt>Source M4</dt><dd title={discreteCommand.sourceM4ContentId}>{shortHash(discreteCommand.sourceM4ContentId)}</dd></div>
              </dl>
            </section>
          )}
        </aside>
      </main>
      <footer className="statusbar f3-statusbar">
        <span><i className={error ? "status-error" : ""} /> {error ? "1 error" : "0 errors"}</span>
        <span>domain: <code>five-axis.domain-pack@4</code></span>
        <span>runner: <code>artifact-import@1</code></span>
        <span className="statusbar-right">MATH ONLY / NOT DEVICE SAFE · σ(t) · V/A/J · interval proof</span>
      </footer>
    </>
  );
}
