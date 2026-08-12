import { useEffect, useMemo, useState } from "react";

import type { Catalog } from "../../types";
import {
  loadPhysicalR4Example,
  loadPhysicalR4Manifest,
  loadPhysicalR4Scenarios,
} from "./api";
import type {
  PhysicalR4Axis,
  PhysicalR4ExamplePayload,
  PhysicalR4Manifest,
  PhysicalR4MetricResult,
  PhysicalR4ScenarioSummary,
  PhysicalR4SignalSample,
} from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function formatValue(value: number | string | boolean | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    const rendered = Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)
      ? value.toExponential(3)
      : value.toFixed(4).replace(/\.?0+$/, "");
    return unit ? `${rendered} ${unit}` : rendered;
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  return unit ? `${value} ${unit}` : value;
}

function resultClass(value?: string | boolean): string {
  if (
    value === true ||
    value === "Supported" ||
    value === "Passed" ||
    value === "Succeeded" ||
    value === "Computed" ||
    value === "pass" ||
    value === "excited"
  ) {
    return "status-positive";
  }
  if (
    value === false ||
    value === "Refuted" ||
    value === "Failed" ||
    value === "Invalid" ||
    value === "ExecutionFailed" ||
    value === "InvalidObservation" ||
    value === "NumericalFailure" ||
    value === "blocked" ||
    value === "insufficient"
  ) {
    return "status-negative";
  }
  return "status-neutral";
}

function buildPath(
  samples: PhysicalR4SignalSample[],
  width: number,
  height: number,
  padding: { left: number; right: number; top: number; bottom: number },
  xMin: number,
  xSpan: number,
  yMin: number,
  ySpan: number,
): string {
  return samples
    .map((sample, index) => {
      const x = padding.left + ((sample.time - xMin) / xSpan) * (width - padding.left - padding.right);
      const y = height - padding.bottom - ((sample.value - yMin) / ySpan) * (height - padding.top - padding.bottom);
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function SignalPlot({
  axis,
  curveMode,
  curveNotice,
}: {
  axis: PhysicalR4Axis | null;
  curveMode: "canonical-analysis" | "diagnostic-preview";
  curveNotice?: string | null;
}) {
  if (!axis) {
    return <div className="empty-state">当前场景没有可视化轴。</div>;
  }

  const width = 720;
  const height = 280;
  const padding = { left: 52, right: 20, top: 16, bottom: 30 };
  const allSamples = [
    ...axis.series.command,
    ...axis.series.simulation,
    ...axis.series.observation,
  ];
  const times = allSamples.map((sample) => sample.time);
  const values = allSamples.map((sample) => sample.value);
  const xMin = Math.min(...times);
  const xMax = Math.max(...times);
  const yMinRaw = Math.min(...values);
  const yMaxRaw = Math.max(...values);
  const xSpan = xMax - xMin || 1;
  const yPad = (yMaxRaw - yMinRaw || 1) * 0.15;
  const yMin = yMinRaw - yPad;
  const yMax = yMaxRaw + yPad;
  const ySpan = yMax - yMin || 1;

  return (
    <figure className="physical-r4-signal-card" role="img" aria-label="选定轴的 command / simulation / observation 曲线">
      <header>
        <div>
          <span className="eyebrow">AXIS CURVES</span>
          <h3>{axis.axisId} · {axis.family}</h3>
          <p className={resultClass(curveMode === "canonical-analysis" ? "Supported" : "Inconclusive")}>
            {curveMode === "canonical-analysis" ? "canonical analysis" : "diagnostic preview"}
          </p>
        </div>
        <code>{axis.unit}</code>
      </header>
      {curveNotice && <p className="f3-scenario-description">{curveNotice}</p>}
      <div className="physical-r4-legend" aria-hidden="true">
        <span><i className="command" />command</span>
        <span><i className="simulation" />simulation</span>
        <span><i className="observation" />observation</span>
      </div>
      <svg className="physical-r4-plot" viewBox={`0 0 ${width} ${height}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const x = padding.left + tick * (width - padding.left - padding.right);
          return (
            <g key={tick}>
              <line className="physical-r4-grid-line" x1={x} x2={x} y1={padding.top} y2={height - padding.bottom} />
              <text x={x} y={height - 10} textAnchor="middle">{(xMin + tick * xSpan).toFixed(2)} s</text>
            </g>
          );
        })}
        {[0, 0.5, 1].map((tick) => {
          const y = height - padding.bottom - tick * (height - padding.top - padding.bottom);
          return (
            <g key={tick}>
              <line className="physical-r4-grid-line" x1={padding.left} x2={width - padding.right} y1={y} y2={y} />
              <text x={8} y={y + 4}>{(yMin + tick * ySpan).toFixed(3)}</text>
            </g>
          );
        })}
        <line className="physical-r4-axis-line" x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} />
        <line className="physical-r4-axis-line" x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} />
        <path
          className="physical-r4-series command"
          d={buildPath(axis.series.command, width, height, padding, xMin, xSpan, yMin, ySpan)}
        />
        <path
          className="physical-r4-series simulation"
          d={buildPath(axis.series.simulation, width, height, padding, xMin, xSpan, yMin, ySpan)}
        />
        <path
          className="physical-r4-series observation"
          d={buildPath(axis.series.observation, width, height, padding, xMin, xSpan, yMin, ySpan)}
        />
      </svg>
    </figure>
  );
}

function metricGroup(metrics: PhysicalR4MetricResult[], group: "linear-mm" | "rotary-rad") {
  return metrics.filter((metric) => metric.group === group);
}

export function PhysicalR4Workbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<PhysicalR4Manifest | null>(null);
  const [summaries, setSummaries] = useState<PhysicalR4ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState("in-domain-synthetic-sil");
  const [selectedAxisId, setSelectedAxisId] = useState("");
  const [example, setExample] = useState<PhysicalR4ExamplePayload | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const displayedManifest = example?.manifest ?? manifest;
  const runtimeBound = Boolean(
    displayedManifest?.domainPackId &&
    catalog?.domainPacks.find((item) => item.domainPackId === displayedManifest.domainPackId)?.runtimeBound,
  );
  const selectedAxis = useMemo(
    () => example?.analysis.axes.find((axis) => axis.axisId === selectedAxisId) ?? example?.analysis.axes[0] ?? null,
    [example, selectedAxisId],
  );
  const linearMetrics = useMemo(() => metricGroup(example?.analysis.metricResults ?? [], "linear-mm"), [example]);
  const rotaryMetrics = useMemo(() => metricGroup(example?.analysis.metricResults ?? [], "rotary-rad"), [example]);

  const loadScenario = async (scenarioId: string, active?: { value: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      const next = await loadPhysicalR4Example(scenarioId);
      if (active && !active.value) return;
      setExample(next);
      setManifest(next.manifest);
      setSelectedId(scenarioId);
      setSelectedAxisId(next.analysis.axes[0]?.axisId ?? "");
    } catch (reason) {
      if (!active || active.value) {
        setExample(null);
        setSelectedAxisId("");
        setError(reason instanceof Error ? reason.message : "Physical R4 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextSummaries] = await Promise.all([
          loadPhysicalR4Manifest(),
          loadPhysicalR4Scenarios(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setSummaries(nextSummaries);
        const defaultId = nextSummaries.some((item) => item.scenarioId === "in-domain-synthetic-sil")
          ? "in-domain-synthetic-sil"
          : nextSummaries[0]?.scenarioId;
        if (!defaultId) throw new Error("Physical R4 场景目录为空。");
        await loadScenario(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "Physical R4 初始化失败。");
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
          <strong>R4 未完成</strong><span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="关闭错误">×</button>
        </div>
      )}

      <main className="workspace physical-r4-workspace">
        <aside className="config-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">PHYSICAL R4 LAB</span>
              <h1>Physical R4 工作台</h1>
            </div>
            <span className="schema-badge">v{displayedManifest?.schemaVersion ?? 1}</span>
          </div>

          <section className="config-section">
            <div className="notice-card physical-r4-banner-stack" role="note">
              <strong>{displayedManifest?.safetyBanner ?? "MODEL VALIDATION / NOT DEVICE SAFE"}</strong>
              <strong>{displayedManifest?.validationBanner ?? "SYNTHETIC SIL / REALITY VALIDATION OPEN"}</strong>
              <p>仅支持 Windows 文件链路。这里做模型验证、残差拆分和证据审阅，不暴露设备写入、控制或参数应用按钮。</p>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>场景</h2><em>{summaries.length || "—"}</em></div>
            <label className="field-label" htmlFor="physical-r4-scenario">场景</label>
            <select
              id="physical-r4-scenario"
              value={selectedId}
              onChange={(event) => void loadScenario(event.target.value)}
              disabled={busy}
            >
              {summaries.map((item) => (
                <option key={item.scenarioId} value={item.scenarioId}>{item.title}</option>
              ))}
            </select>
            <p className="f3-scenario-description">{example?.scenario.description ?? "正在加载 Physical R4 场景…"}</p>
            <div className="chip-row">
              <span className="chip">windows-only</span>
              <span className="chip">exact-zoh</span>
              <span className={`chip ${resultClass(runtimeBound)}`}>{runtimeBound ? "runtime-bound" : "runtime-pending"}</span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>模型合同</h2><em>{displayedManifest?.stage ?? "—"}</em></div>
            <dl className="data-list">
              <div><dt>方程</dt><dd>{example?.model.equations.length ?? displayedManifest?.model.equations.length ?? 0} frozen</dd></div>
              <div><dt>状态</dt><dd>{example?.model.stateIds.join(", ") ?? displayedManifest?.model.stateIds.join(", ") ?? "—"}</dd></div>
              <div><dt>输入</dt><dd>{example?.model.inputIds.join(", ") ?? displayedManifest?.model.inputIds.join(", ") ?? "—"}</dd></div>
              <div><dt>输出</dt><dd>{example?.model.outputIds.join(", ") ?? displayedManifest?.model.outputIds.join(", ") ?? "—"}</dd></div>
              <div><dt>离散化</dt><dd>{example?.model.discretization ?? displayedManifest?.model.discretization ?? "—"}</dd></div>
            </dl>
            <div className="findings-list top-gap">
              <article>
                <header><strong>equations</strong><span className="status-neutral">frozen</span></header>
                <p>{example?.model.equations.join(" · ") ?? displayedManifest?.model.equations.join(" · ") ?? "—"}</p>
              </article>
              <article>
                <header><strong>applicable devices / conditions</strong><span className="status-neutral">scope</span></header>
                <p>{example?.model.supportedDevices.join(", ") ?? displayedManifest?.model.supportedDevices.join(", ") ?? "—"}</p>
                <footer>{example?.model.operatingConditions.join(" · ") ?? displayedManifest?.model.operatingConditions.join(" · ") ?? "—"}</footer>
              </article>
              <article>
                <header><strong>unmodeled factors</strong><span className="status-negative">watch list</span></header>
                <p>{example?.model.unmodeledFactors.join(" · ") ?? displayedManifest?.model.unmodeledFactors.join(" · ") ?? "—"}</p>
              </article>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>Calibration vs Validation</h2><em>anti-leakage</em></div>
            <div className="physical-r4-identity-grid">
              <article className="physical-r4-identity-card">
                <header><h3>Calibration</h3><span className="status-neutral">{example?.calibration.scenarioRole ?? "—"}</span></header>
                <p><code>{example?.calibration.datasetId ?? "—"}</code></p>
                <p>{example?.calibration.traceId ?? "—"}</p>
              </article>
              <article className="physical-r4-identity-card">
                <header><h3>Validation</h3><span className="status-positive">{example?.validation.scenarioRole ?? "—"}</span></header>
                <p><code>{example?.validation.datasetId ?? "—"}</code></p>
                <p>{example?.validation.traceId ?? "—"}</p>
              </article>
            </div>
            <div className="findings-list top-gap">
              {(example?.validation.leakageGuards ?? []).map((guard) => (
                <article key={guard.checkId}>
                  <header><strong>{guard.checkId}</strong><span className={resultClass(guard.status)}>{guard.status}</span></header>
                  <p>{guard.message}</p>
                </article>
              ))}
            </div>
          </section>
        </aside>

        <section className="analysis-panel physical-r4-analysis">
          <div className="analysis-heading">
            <div className="view-tabs" aria-label="Physical R4 视图">
              <span>Validation Curves</span>
              <span className="physical-r4-view-divider">/</span>
              <span>Residuals</span>
            </div>
            <div className="run-state">
              <span className={resultClass(example?.analysis.run?.caseOutcome)}>{example?.analysis.run?.caseOutcome ?? "Pending"}</span>
              <span className={resultClass(example?.analysis.run?.executionStatus)}>{example?.analysis.run?.executionStatus ?? "Pending"}</span>
              <span className={resultClass(runtimeBound)}>{runtimeBound ? "runtime: bound" : "runtime: pending"}</span>
              <span>{example?.analysis.traceArtifactType ?? "five-axis.physical-response-trace"}</span>
            </div>
          </div>

          <div className="physical-r4-analysis-body">
            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>选轴</h2><em>{example?.analysis.axes.length ?? 0}</em></div>
              <div className="physical-r4-axis-picker">
                {(example?.analysis.axes ?? []).map((axis) => (
                  <button
                    key={axis.axisId}
                    className={`physical-r4-axis-button ${selectedAxis?.axisId === axis.axisId ? "active" : ""}`}
                    type="button"
                    onClick={() => setSelectedAxisId(axis.axisId)}
                  >
                    <strong>{axis.axisId}</strong>
                    <small>{axis.family} · {axis.excitationStatus}</small>
                  </button>
                ))}
              </div>
            </section>

            <SignalPlot
              axis={selectedAxis}
              curveMode={example?.analysis.curveMode ?? "canonical-analysis"}
              curveNotice={example?.analysis.curveNotice}
            />

            <section className="physical-r4-metric-groups">
              <article className="physical-r4-metric-group">
                <span className="eyebrow">LINEAR-MM</span>
                <h3>linear-mm 分组指标</h3>
                <div className="physical-r4-metric-grid">
                  {linearMetrics.map((metric) => (
                    <div key={metric.metricId} className="physical-r4-metric-card">
                      <code>{metric.metricId}</code>
                      <strong>{formatValue(metric.value, metric.unit)}</strong>
                      <p>{metric.label}</p>
                      <small className={resultClass(metric.status)}>
                        {metric.status}{metric.reasonCode ? ` · ${metric.reasonCode}` : ""}
                      </small>
                    </div>
                  ))}
                  {!linearMetrics.length && <div className="empty-state">无 linear-mm 指标。</div>}
                </div>
              </article>
              <article className="physical-r4-metric-group">
                <span className="eyebrow">ROTARY-RAD</span>
                <h3>rotary-rad 分组指标</h3>
                <div className="physical-r4-metric-grid">
                  {rotaryMetrics.map((metric) => (
                    <div key={metric.metricId} className="physical-r4-metric-card">
                      <code>{metric.metricId}</code>
                      <strong>{formatValue(metric.value, metric.unit)}</strong>
                      <p>{metric.label}</p>
                      <small className={resultClass(metric.status)}>
                        {metric.status}{metric.reasonCode ? ` · ${metric.reasonCode}` : ""}
                      </small>
                    </div>
                  ))}
                  {!rotaryMetrics.length && <div className="empty-state">无 rotary-rad 指标。</div>}
                </div>
              </article>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>02</span><h2>Residual Decomposition</h2><em>{selectedAxis?.axisId ?? "—"}</em></div>
              <table className="compact-table physical-r4-residual-table">
                <thead>
                  <tr>
                    <th>component</th>
                    <th>value</th>
                    <th>source</th>
                  </tr>
                </thead>
                <tbody>
                  {(selectedAxis?.residualDecomposition ?? []).map((component) => (
                    <tr key={component.componentId}>
                      <td><code>{component.label}</code></td>
                      <td>{formatValue(component.value, component.unit)}</td>
                      <td>{component.source}</td>
                    </tr>
                  ))}
                  {!selectedAxis?.residualDecomposition.length && (
                    <tr><td colSpan={3} className="empty-row">无 residual decomposition。</td></tr>
                  )}
                </tbody>
              </table>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>03</span><h2>轴激励状态</h2><em>validation coverage</em></div>
              <div className="physical-r4-excitation-grid">
                {(example?.analysis.axes ?? []).map((axis) => (
                  <article key={axis.axisId} className="physical-r4-excitation-card">
                    <header>
                      <h3>{axis.axisId}</h3>
                      <span className={resultClass(axis.excitationStatus)}>{axis.excitationStatus}</span>
                    </header>
                    <p>{axis.family} · {axis.unit}</p>
                  </article>
                ))}
              </div>
            </section>
          </div>
        </section>

        <aside className="evidence-panel">
          <div className="panel-heading evidence-heading">
            <div>
              <span className="eyebrow">SEALED R4 OUTPUT</span>
              <h2>Claims / Evidence</h2>
            </div>
            <span className="schema-badge">{displayedManifest?.manifestId ?? "physical.r4-manifest@1"}</span>
          </div>

          <section className="verdict-card">
            <span className="eyebrow">VALIDATION BOUNDARY</span>
            <div className="verdict-row">
              <strong className={resultClass(example?.analysis.run?.caseOutcome)}>{example?.analysis.run?.caseOutcome ?? "Pending"}</strong>
              <span>{example?.scenario.title ?? "held-out validation only"}</span>
            </div>
            <div className="verdict-rule"><i /><span>Execution</span><b className={resultClass(example?.analysis.run?.executionStatus)}>{example?.analysis.run?.executionStatus ?? "—"}</b></div>
            <div className="verdict-rule"><i /><span>Calibration hash</span><b title={example?.calibration.contentHash}>{shortHash(example?.calibration.contentHash)}</b></div>
            <div className="verdict-rule"><i /><span>Validation hash</span><b title={example?.validation.contentHash}>{shortHash(example?.validation.contentHash)}</b></div>
            <div className="verdict-rule"><i /><span>Write surface</span><b className="status-negative">absent</b></div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>01</span><h2>冻结身份</h2></div>
            <dl className="identity-list">
              <div><dt>Manifest</dt><dd title={displayedManifest?.manifestId}>{shortHash(displayedManifest?.manifestId)}</dd></div>
              <div><dt>Calibration</dt><dd>{example?.calibration.traceId ?? "—"}</dd></div>
              <div><dt>Validation</dt><dd>{example?.validation.traceId ?? "—"}</dd></div>
              <div><dt>Source</dt><dd>{example?.validation.sourceId ?? "—"}</dd></div>
            </dl>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>02</span><h2>Claims</h2></div>
            <div className="claims-list">
              {(example?.analysis.claims ?? []).map((claim) => (
                <article key={claim.claimId}>
                  <div><strong>{claim.title}</strong><em className={resultClass(claim.status)}>{claim.status}</em></div>
                  <p>{claim.statement}</p>
                  <footer>
                    <code>{claim.claimDefinitionId}</code>
                    <span>{claim.reasonCode ?? claim.evidenceLevel ?? claim.evidenceIds.join(", ")}</span>
                  </footer>
                </article>
              ))}
              {!example?.analysis.claims.length && <div className="empty-state">尚无 claims。</div>}
            </div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>03</span><h2>Evidence</h2></div>
            <div className="claims-list">
              {(example?.analysis.evidence ?? []).map((item) => (
                <article key={item.evidenceId}>
                  <div><strong>{item.title}</strong><em className="status-neutral">{item.kind}</em></div>
                  <p>{item.summary}</p>
                  <footer><code>{item.evidenceId}</code><span title={item.contentHash ?? undefined}>{shortHash(item.contentHash ?? undefined)}</span></footer>
                </article>
              ))}
              {!example?.analysis.evidence.length && <div className="empty-state">尚无 evidence。</div>}
            </div>
          </section>
        </aside>
      </main>
    </>
  );
}
