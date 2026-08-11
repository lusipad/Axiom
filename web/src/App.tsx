import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  executeExperiment,
  executeRun,
  loadCatalog,
  loadContourExample,
  loadFiveAxisExample,
  loadFiveAxisManifest,
} from "./api";
import type {
  ArtifactAdapterDescriptor,
  Catalog,
  Claim,
  DomainFailure,
  ExperimentArmResult,
  ExperimentReport,
  ExperimentSpec,
  FiveAxisSampledCartesianView,
  MathStageManifest,
  MetricComparison,
  Point,
  RunBundle,
  RunSpec,
  StageEnvelope,
} from "./types";

type Lab = "point" | "five-axis";
type PointView = "geometry" | "metrics";
type FiveAxisView = "manifest" | "report";

const futureLabs = ["Machine", "Intelligence", "Optimization"];

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

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
  if (value === true || value === "Passed" || value === "Succeeded" || value === "Accepted" || value === "Supported") {
    return "status-positive";
  }
  if (
    value === false ||
    value === "Failed" ||
    value === "ExecutionFailed" ||
    value === "Rejected" ||
    value === "Invalid" ||
    value === "Unsupported"
  ) {
    return "status-negative";
  }
  return "status-neutral";
}

function metricThreshold(spec: ExperimentSpec): number {
  for (const metric of spec.evaluation.case.requiredMetrics) {
    if (typeof metric !== "string" && metric.metricId === "paired.euclidean.max") {
      return metric.threshold?.value ?? 0.03;
    }
  }
  return 0.03;
}

function setMetricThreshold(spec: ExperimentSpec, value: number): void {
  for (const metric of spec.evaluation.case.requiredMetrics) {
    if (typeof metric !== "string" && metric.metricId === "paired.euclidean.max" && metric.threshold) {
      metric.threshold.value = value;
    }
  }
}

function parseFiniteVector(value: string): number[] {
  const vector = value.split(",").map((item) => Number(item.trim()));
  if (vector.length === 0 || vector.some((item) => !Number.isFinite(item))) {
    throw new Error("误差向量必须是以逗号分隔的有限数字。例：0, 0.08");
  }
  return vector;
}

function parsePoints(value: string): Point[] {
  const points = JSON.parse(value) as unknown;
  if (!Array.isArray(points) || points.length < 2) {
    throw new Error("点序列必须是至少包含两个点的 JSON 数组。");
  }
  const dimension = Array.isArray(points[0]) ? points[0].length : 0;
  if (dimension < 2) throw new Error("每个点至少需要 X、Y 两个坐标。");
  if (
    !points.every(
      (point) => Array.isArray(point) && point.length === dimension && point.every(Number.isFinite),
    )
  ) {
    throw new Error("所有点必须具有相同维数，且坐标必须是有限数字。");
  }
  return points as Point[];
}

interface ProjectedPath {
  key: string;
  label: string;
  tone: "reference" | "baseline" | "candidate";
  d: string;
  dots: Array<[number, number]>;
}

function isOrderedPointArtifact(value: unknown): value is { points: Point[] } {
  return Boolean(
    value &&
    typeof value === "object" &&
    "artifactType" in value &&
    (value as { artifactType?: string }).artifactType === "ordered-point-sequence" &&
    Array.isArray((value as { points?: unknown }).points),
  );
}

function isFiveAxisArtifact(value: unknown): value is FiveAxisSampledCartesianView {
  return Boolean(
    value &&
    typeof value === "object" &&
    "artifactType" in value &&
    (value as { artifactType?: string }).artifactType === "five-axis.sampled-cartesian-position-view",
  );
}

function projectPaths(spec: ExperimentSpec, report: ExperimentReport | null): ProjectedPath[] {
  const sources = [
    { key: "reference", label: "共享输入", tone: "reference" as const, points: spec.sharedInput.points },
    ...(report?.armResults ?? []).flatMap((arm, index) => {
      const artifact = arm.runBundle?.observation?.artifact;
      return isOrderedPointArtifact(artifact)
        ? [{
            key: arm.armId,
            label: arm.armId,
            tone: index === 0 ? "baseline" as const : "candidate" as const,
            points: artifact.points,
          }]
        : [];
    }),
  ];
  const all = sources.flatMap((source) => source.points);
  if (all.length === 0) return [];
  const xValues = all.map((point) => point[0] ?? 0);
  const yValues = all.map((point) => point[1] ?? 0);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const project = (point: Point): [number, number] => [
    54 + (((point[0] ?? 0) - minX) / spanX) * 532,
    306 - (((point[1] ?? 0) - minY) / spanY) * 240,
  ];

  return sources.map((source) => {
    const dots = source.points.map(project);
    return {
      key: source.key,
      label: source.label,
      tone: source.tone,
      d: dots.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" "),
      dots,
    };
  });
}

function armMetric(arm: ExperimentArmResult | undefined, metricId: string): string {
  const metric = arm?.runBundle?.report.metricResults.find((item) => item.metricId === metricId);
  return metric ? `${formatValue(metric.value)} ${metric.unit ?? ""}`.trim() : "—";
}

function comparisonWinner(metric: MetricComparison, report: ExperimentReport): string {
  const arm = report.armResults.find((item) => item.subjectId === metric.preferredSubjectId);
  return arm?.armId ?? "—";
}

function detailRows(entries: Array<[string, string]>) {
  return (
    <dl className="data-list">
      {entries.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function envelopeTitle(envelope: StageEnvelope): string {
  return `${envelope.stage} · ${envelope.envelopeType}`;
}

function renderFindings(items: DomainFailure[] | undefined) {
  if (!items?.length) {
    return <div className="empty-state">当前没有 domain failure / finding。</div>;
  }
  return (
    <div className="findings-list">
      {items.map((item) => (
        <article key={`${item.code}:${item.path ?? "root"}`}>
          <header>
            <strong>{item.code}</strong>
            <span className={resultClass(item.severity === "error" ? "Failed" : "Skipped")}>{item.severity ?? "finding"}</span>
          </header>
          <p>{item.message}</p>
          <footer>{item.path ?? "—"}</footer>
        </article>
      ))}
    </div>
  );
}

function renderClaims(items: Claim[]) {
  if (!items.length) {
    return <div className="empty-state">没有可展示的 claim。</div>;
  }
  return (
    <div className="claims-list">
      {items.map((claim) => (
        <article key={claim.claimId}>
          <div>
            <strong>{claim.metricId ?? "case-outcome"}</strong>
            <em className={resultClass(claim.status)}>{claim.status}</em>
          </div>
          <p>{claim.predicate}</p>
          <footer>
            <code>{shortHash(claim.claimId)}</code>
            <span>{claim.evidence?.method ?? "—"}</span>
          </footer>
        </article>
      ))}
    </div>
  );
}

export function App() {
  const [activeLab, setActiveLab] = useState<Lab>("point");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [spec, setSpec] = useState<ExperimentSpec | null>(null);
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const [manifest, setManifest] = useState<MathStageManifest | null>(null);
  const [fiveAxisSpec, setFiveAxisSpec] = useState<RunSpec | null>(null);
  const [fiveAxisRun, setFiveAxisRun] = useState<RunBundle | null>(null);
  const [pointsText, setPointsText] = useState("[]");
  const [errorVector, setErrorVector] = useState("0, 0.08");
  const [gain, setGain] = useState("0.75");
  const [threshold, setThreshold] = useState("0.03");
  const [pointView, setPointView] = useState<PointView>("geometry");
  const [fiveAxisView, setFiveAxisView] = useState<FiveAxisView>("manifest");
  const [loading, setLoading] = useState(true);
  const [fiveAxisLoading, setFiveAxisLoading] = useState(true);
  const [pointBusy, setPointBusy] = useState(false);
  const [fiveAxisBusy, setFiveAxisBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fiveAxisLoadError, setFiveAxisLoadError] = useState<string | null>(null);
  const importInput = useRef<HTMLInputElement>(null);

  const hydratePointSpec = (next: ExperimentSpec) => {
    setSpec(next);
    setPointsText(JSON.stringify(next.sharedInput.points, null, 2));
    const vector = next.parameterSet.values.errorVector;
    setErrorVector(Array.isArray(vector) ? vector.join(", ") : "0, 0.08");
    setGain(String(next.parameterSet.values.compensationGain ?? 0.75));
    setThreshold(String(metricThreshold(next)));
  };

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [nextCatalog, pointExample] = await Promise.all([
          loadCatalog(),
          loadContourExample(),
        ]);
        if (!active) return;
        setCatalog(nextCatalog);
        hydratePointSpec(pointExample);
        const initialReport = await executeExperiment(pointExample);
        if (active) setReport(initialReport);
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "工作台初始化失败。");
      } finally {
        if (active) setLoading(false);
      }
    })();
    (async () => {
      try {
        const [nextManifest, nextFiveAxisSpec] = await Promise.all([
          loadFiveAxisManifest(),
          loadFiveAxisExample(),
        ]);
        if (!active) return;
        setManifest(nextManifest);
        setFiveAxisSpec(nextFiveAxisSpec);
      } catch (reason) {
        if (active) {
          setFiveAxisLoadError(
            reason instanceof Error ? reason.message : "Five-Axis F0 入口初始化失败。",
          );
        }
      } finally {
        if (active) setFiveAxisLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const pointPaths = useMemo(() => (spec ? projectPaths(spec, report) : []), [spec, report]);
  const baseline = report?.armResults[0];
  const candidate = report?.armResults[1];
  const compatible = report?.comparison?.compatibility.compatible;
  const pointUnit = spec?.sharedInput.semantics?.unit ?? "coordinate-unit";
  const pointDimension = spec?.sharedInput.points[0]?.length ?? 0;
  const pointRunnerLabel = [...new Set(spec?.arms.map((arm) => arm.runnerId ?? "unknown-runner") ?? [])].join(", ");
  const exampleArtifact = fiveAxisSpec?.request["artifact"];
  const fiveAxisArtifact = isFiveAxisArtifact(fiveAxisRun?.observation?.artifact)
    ? fiveAxisRun.observation.artifact
    : isFiveAxisArtifact(exampleArtifact)
      ? exampleArtifact
      : null;
  const fiveAxisAdapters = (catalog?.artifactAdapters ?? []).filter(
    (adapter) =>
      adapter.sourceArtifactType === "five-axis.sampled-cartesian-position-view" ||
      adapter.targetArtifactType === "five-axis.sampled-cartesian-position-view",
  );
  const fiveAxisDomainPack = catalog?.domainPacks.find((item) => item.domainPackId === fiveAxisSpec?.domainPackId);
  const fiveAxisBusyState = fiveAxisLoading || fiveAxisBusy;
  const pointBusyState = loading || pointBusy;
  const visibleError = error ?? (activeLab === "five-axis" ? fiveAxisLoadError : null);

  const buildPointSpec = (): ExperimentSpec => {
    if (!spec) throw new Error("实验模板尚未加载。");
    const next = clone(spec);
    const points = parsePoints(pointsText);
    const vector = parseFiniteVector(errorVector);
    if (vector.length !== points[0]!.length) {
      throw new Error(`误差向量是 ${vector.length} 维，但点序列是 ${points[0]!.length} 维。`);
    }
    const gainValue = Number(gain);
    const thresholdValue = Number(threshold);
    if (!Number.isFinite(gainValue) || gainValue < 0 || gainValue > 1) {
      throw new Error("补偿增益必须位于 0 到 1 之间。");
    }
    if (!Number.isFinite(thresholdValue) || thresholdValue < 0) {
      throw new Error("最大偏差阈值必须是非负有限数字。");
    }
    next.sharedInput.points = points;
    next.parameterSet.values.errorVector = vector;
    next.parameterSet.values.compensationGain = gainValue;
    setMetricThreshold(next, thresholdValue);
    return next;
  };

  const runPointExperiment = async () => {
    setPointBusy(true);
    setError(null);
    try {
      const next = buildPointSpec();
      setSpec(next);
      setReport(await executeExperiment(next));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "实验执行失败。");
    } finally {
      setPointBusy(false);
    }
  };

  const runFiveAxisContract = async () => {
    if (!fiveAxisSpec) {
      setError("Five-Axis F0 示例尚未加载。");
      return;
    }
    setFiveAxisBusy(true);
    setError(null);
    try {
      setFiveAxisRun(await executeRun(fiveAxisSpec));
      setFiveAxisView("report");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "F0 契约执行失败。");
    } finally {
      setFiveAxisBusy(false);
    }
  };

  const selectSubject = (armIndex: number, catalogIndex: number) => {
    if (!spec || !catalog) return;
    const subject = catalog.subjects[catalogIndex];
    if (!subject) return;
    const next = clone(spec);
    next.arms[armIndex]!.subjectId = subject.subjectId;
    next.arms[armIndex]!.subjectVersion = subject.subjectVersion;
    setSpec(next);
  };

  const importSpec = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const next = JSON.parse(await file.text()) as ExperimentSpec;
      hydratePointSpec(next);
      setReport(null);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? `无法导入：${reason.message}` : "无法导入实验文件。");
    }
  };

  const downloadPointEvidence = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${report.experimentSpec.experimentId}-evidence.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const downloadFiveAxisEvidence = () => {
    if (!fiveAxisRun) return;
    const blob = new Blob([JSON.stringify(fiveAxisRun, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${fiveAxisRun.run.runId}-bundle.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="workbench">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">A</div>
          <div>
            <strong>AXIOM</strong>
            <span>{activeLab === "point" ? "Experiment Workbench" : "Five-Axis Contract Workbench"}</span>
          </div>
        </div>
        <div className="topbar-context">
          <span className={`connection-dot ${visibleError ? "offline" : ""}`} />
          <span className="context-label">{visibleError ? "需要检查" : "本地 API 可用"}</span>
          <code>{activeLab === "point" ? spec?.experimentId ?? "loading" : manifest?.manifestId ?? "loading"}</code>
        </div>
        <div className="topbar-actions">
          {activeLab === "point" ? (
            <>
              <input ref={importInput} type="file" accept="application/json,.json" hidden onChange={importSpec} />
              <button className="button button-secondary" type="button" onClick={() => importInput.current?.click()}>
                导入 JSON
              </button>
              <button className="button button-primary" type="button" onClick={runPointExperiment} disabled={pointBusyState || !spec}>
                {pointBusyState ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
                {pointBusyState ? "执行中" : "运行实验"}
              </button>
            </>
          ) : (
            <button className="button button-primary" type="button" onClick={runFiveAxisContract} disabled={fiveAxisBusyState || !fiveAxisSpec}>
              {fiveAxisBusyState ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
              {fiveAxisBusyState ? "验证中" : "验证 F0 契约"}
            </button>
          )}
        </div>
      </header>

      {visibleError && (
        <div className="error-banner" role="alert">
          <strong>未完成</strong><span>{visibleError}</span>
          <button
            type="button"
            onClick={() => (error ? setError(null) : setFiveAxisLoadError(null))}
            aria-label="关闭错误"
          >×</button>
        </div>
      )}

      <div className="lab-switcher" aria-label="领域实验室">
        <button className={`lab ${activeLab === "point" ? "active" : ""}`} type="button" onClick={() => setActiveLab("point")}>
          <span>01</span>Point Lab
        </button>
        <button className={`lab ${activeLab === "five-axis" ? "active" : ""}`} type="button" onClick={() => setActiveLab("five-axis")}>
          <span>02</span>Five-Axis<small>F0</small>
        </button>
        {futureLabs.map((lab, index) => (
          <button className="lab" type="button" disabled key={lab} title="领域包尚未接入">
            <span>0{index + 3}</span>{lab}<small>planned</small>
          </button>
        ))}
      </div>

      {activeLab === "point" ? (
        <main className="workspace">
          <aside className="config-panel">
            <div className="panel-heading">
              <div><span className="eyebrow">EXPERIMENT SPEC</span><h1>双臂实验配置</h1></div>
              <span className="schema-badge">@1</span>
            </div>

            <section className="config-section">
              <div className="section-title"><span>01</span><h2>共享输入</h2><em>{spec?.sharedInput.points.length ?? 0} pts</em></div>
              <label className="field-label" htmlFor="points">有序离散点（JSON）</label>
              <textarea
                id="points"
                className="code-input points-input"
                value={pointsText}
                onChange={(event) => setPointsText(event.target.value)}
                spellCheck={false}
              />
              <div className="input-meta">
                <span>{spec?.sharedInput.semantics?.coordinateFrame ?? "frame unknown"}</span>
                <span>{pointUnit}</span>
                <span>{spec?.sharedInput.semantics?.closed ? "closed" : "open"}</span>
              </div>
            </section>

            <section className="config-section">
              <div className="section-title"><span>02</span><h2>参数集</h2><em>frozen</em></div>
              <label className="field-label" htmlFor="error-vector">误差向量（{pointUnit}）</label>
              <input id="error-vector" className="text-input mono" value={errorVector} onChange={(event) => setErrorVector(event.target.value)} />
              <div className="gain-row">
                <label className="field-label" htmlFor="gain">补偿增益</label><output>{gain}</output>
              </div>
              <input id="gain" type="range" min="0" max="1" step="0.01" value={gain} onChange={(event) => setGain(event.target.value)} />
              <label className="field-label threshold-label" htmlFor="threshold">最大偏差硬门槛（{pointUnit}）</label>
              <input id="threshold" className="text-input mono" inputMode="decimal" value={threshold} onChange={(event) => setThreshold(event.target.value)} />
            </section>

            <section className="config-section arms-section">
              <div className="section-title"><span>03</span><h2>实验双臂</h2><em>strict</em></div>
              {spec?.arms.map((arm, index) => (
                <div className={`arm-card arm-${index}`} key={arm.armId}>
                  <div className="arm-card-head"><span className="arm-swatch" /><strong>{arm.armId}</strong><code>{arm.runnerId ?? "unknown-runner"}</code></div>
                  <label className="visually-hidden" htmlFor={`arm-${index}`}>{arm.armId} Subject</label>
                  <select
                    id={`arm-${index}`}
                    value={String(catalog?.subjects.findIndex(
                      (subject) => subject.subjectId === arm.subjectId && subject.subjectVersion === arm.subjectVersion,
                    ) ?? -1)}
                    onChange={(event) => selectSubject(index, Number(event.target.value))}
                  >
                    {catalog?.subjects.map((subject, subjectIndex) => (
                      <option key={`${subject.subjectId}@${subject.subjectVersion}`} value={subjectIndex}>
                        {subject.displayName} @{subject.subjectVersion}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </section>
          </aside>

          <section className="analysis-panel">
            <div className="analysis-heading">
              <div className="view-tabs" role="tablist" aria-label="结果视图">
                <button role="tab" aria-selected={pointView === "geometry"} onClick={() => setPointView("geometry")}>几何轨迹</button>
                <button role="tab" aria-selected={pointView === "metrics"} onClick={() => setPointView("metrics")}>指标比较</button>
              </div>
              <div className="run-state">
                <span className={resultClass(report?.executionStatus)}>{report?.executionStatus ?? "Not run"}</span>
                <span className={resultClass(compatible)}>{compatible === undefined ? "等待比较" : compatible ? "Strict compatible" : "Incompatible"}</span>
              </div>
            </div>

            {pointView === "geometry" ? (
              <div className="geometry-view">
                <div className="plot-toolbar">
                  <div className="legend">
                    {pointPaths.map((path) => <span className={`legend-${path.tone}`} key={path.key}><i />{path.label}</span>)}
                  </div>
                  <code>
                    {spec?.sharedInput.semantics?.coordinateFrame ?? "unknown frame"} · XY
                    {pointDimension > 2 ? ` projection of ${pointDimension}D` : ""} · {pointUnit}
                  </code>
                </div>
                <div className="plot-stage">
                  <svg viewBox="0 0 640 360" role="img" aria-label="共享输入与两个 Subject 输出的轨迹比较">
                    <defs>
                      <pattern id="minor-grid" width="32" height="32" patternUnits="userSpaceOnUse">
                        <path d="M 32 0 L 0 0 0 32" fill="none" className="minor-grid" />
                      </pattern>
                    </defs>
                    <rect width="640" height="360" fill="url(#minor-grid)" />
                    <line x1="32" y1="306" x2="610" y2="306" className="axis-line" />
                    <line x1="54" y1="32" x2="54" y2="328" className="axis-line" />
                    {pointPaths.map((path) => (
                      <g className={`path-series path-${path.tone}`} key={path.key}>
                        <path d={path.d} />
                        {path.dots.map(([x, y], index) => <circle key={`${path.key}-${index}`} cx={x} cy={y} r={path.tone === "reference" ? 2.5 : 3.5} />)}
                      </g>
                    ))}
                    <text x="600" y="326" className="axis-label">X</text>
                    <text x="37" y="42" className="axis-label">Y</text>
                  </svg>
                  {!report && !pointBusyState && <div className="empty-overlay">配置已加载，运行实验以生成双臂观测。</div>}
                </div>
              </div>
            ) : (
              <div className="metrics-view">
                <table>
                  <thead><tr><th>指标定义</th><th>{baseline?.armId ?? "baseline"}</th><th>{candidate?.armId ?? "candidate"}</th><th>Δ (B−A)</th><th>优选</th></tr></thead>
                  <tbody>
                    {(report?.comparison?.metricComparisons ?? []).map((metric) => (
                      <tr key={metric.metricId}>
                        <td><code>{metric.metricId}</code><small>{metric.unit ?? "dimensionless"}</small></td>
                        <td>{formatValue(metric.left)}</td><td>{formatValue(metric.right)}</td>
                        <td className={typeof metric.delta === "number" && metric.delta < 0 ? "status-positive" : ""}>{formatValue(metric.delta)}</td>
                        <td>{report ? comparisonWinner(metric, report) : "—"}</td>
                      </tr>
                    ))}
                    {!report?.comparison?.metricComparisons.length && (
                      <tr><td colSpan={5} className="empty-row">尚无可比较指标</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}

            <div className="metric-strip">
              <div><span>BASELINE MAX</span><strong>{armMetric(baseline, "paired.euclidean.max")}</strong><small className={resultClass(baseline?.caseOutcome)}>{baseline?.caseOutcome ?? "—"}</small></div>
              <div><span>CANDIDATE MAX</span><strong>{armMetric(candidate, "paired.euclidean.max")}</strong><small className={resultClass(candidate?.caseOutcome)}>{candidate?.caseOutcome ?? "—"}</small></div>
              <div><span>THRESHOLD</span><strong>≤ {threshold} {pointUnit}</strong><small>hard gate</small></div>
              <div><span>COMPARISON</span><strong className={resultClass(compatible)}>{compatible ? "Compatible" : compatible === false ? "Blocked" : "—"}</strong><small>lineage strict</small></div>
            </div>
          </section>

          <aside className="evidence-panel">
            <div className="panel-heading evidence-heading">
              <div><span className="eyebrow">SEALED OUTPUT</span><h2>证据与谱系</h2></div>
              <button type="button" className="icon-button" onClick={downloadPointEvidence} disabled={!report} title="下载证据 JSON">⇩</button>
            </div>

            <section className="verdict-card">
              <span className="eyebrow">EXPERIMENT VERDICT</span>
              <div className="verdict-row"><strong className={resultClass(report?.caseOutcome)}>{report?.caseOutcome ?? "Pending"}</strong><span>{report ? "证据包已封存" : "等待执行"}</span></div>
              <div className="verdict-rule"><i /><span>Execution</span><b className={resultClass(report?.executionStatus)}>{report?.executionStatus ?? "—"}</b></div>
              <div className="verdict-rule"><i /><span>Compatibility</span><b className={resultClass(compatible)}>{compatible === undefined ? "—" : compatible ? "Accepted" : "Rejected"}</b></div>
            </section>

            <section className="evidence-section">
              <div className="section-title compact"><span>01</span><h2>冻结身份</h2></div>
              <dl className="identity-list">
                <div><dt>Input</dt><dd title={report?.sharedInputHash}>{shortHash(report?.sharedInputHash)}</dd></div>
                <div><dt>Parameters</dt><dd title={report?.parameterSetHash}>{shortHash(report?.parameterSetHash)}</dd></div>
                <div><dt>Experiment</dt><dd title={report?.experimentSpecHash}>{shortHash(report?.experimentSpecHash)}</dd></div>
                <div><dt>Bundle</dt><dd title={report?.contentHash}>{shortHash(report?.contentHash)}</dd></div>
              </dl>
            </section>

            <section className="evidence-section">
              <div className="section-title compact"><span>02</span><h2>声明</h2></div>
              <div className="claims-list">
                {(report?.armResults ?? []).map((arm) => (
                  <article key={arm.armId}>
                    <div><span className={`arm-swatch ${arm.armId === candidate?.armId ? "candidate" : ""}`} /><strong>{arm.armId}</strong><em className={resultClass(arm.caseOutcome)}>{arm.caseOutcome}</em></div>
                    <p>{arm.runBundle?.claims[0]?.predicate ?? arm.failure?.message ?? "没有可发布声明"}</p>
                    <footer><code>{arm.subjectId}@{arm.subjectVersion}</code><span>{arm.runBundle?.claims[0]?.evidence?.level ?? "—"}</span></footer>
                  </article>
                ))}
                {!report && <div className="placeholder-lines"><i /><i /><i /></div>}
              </div>
            </section>

            <section className="evidence-section">
              <div className="section-title compact"><span>03</span><h2>执行链</h2></div>
              <ol className="execution-chain">
                <li className={spec ? "done" : ""}><span>Spec validated</span><code>experiment-spec@1</code></li>
                <li className={report ? "done" : ""}><span>Shared input frozen</span><code>{shortHash(report?.sharedInputHash)}</code></li>
                <li className={report ? "done" : ""}><span>Subjects executed</span><code>{pointRunnerLabel || "pending"}</code></li>
                <li className={compatible ? "done" : ""}><span>Strict comparison</span><code>{report?.comparison?.policyId ?? "pending"}</code></li>
              </ol>
            </section>
          </aside>
        </main>
      ) : (
        <main className="workspace">
          <aside className="config-panel">
            <div className="panel-heading">
              <div><span className="eyebrow">F0 CONTRACT</span><h1>Five-Axis 机器契约</h1></div>
              <span className="schema-badge">@1</span>
            </div>

            <section className="config-section">
              <div className="section-title"><span>01</span><h2>Manifest</h2><em>{manifest?.stage ?? "F0"}</em></div>
              {detailRows([
                ["Manifest ID", manifest?.manifestId ?? "loading"],
                ["Expected Status", manifest?.expectedStatus ?? "—"],
                ["Fixture Hash", shortHash(manifest?.fixtureContentIds[0])],
                ["Runtime Bound", fiveAxisDomainPack?.runtimeBound ? "true" : "false"],
              ])}
              <div className="chip-row">
                {(manifest?.capabilityIds ?? []).map((item) => <span className="chip" key={item}>{item}</span>)}
              </div>
            </section>

            <section className="config-section">
              <div className="section-title"><span>02</span><h2>Derived View</h2><em>{fiveAxisArtifact?.samples.length ?? "—"}</em></div>
              {detailRows([
                ["Domain Pack", fiveAxisSpec?.domainPackId ?? "—"],
                ["Runner", fiveAxisSpec?.runnerId ?? "—"],
                ["Artifact", fiveAxisArtifact?.artifactType ?? "—"],
                ["Source Mode", fiveAxisArtifact?.sourceCoordinateMode ?? "—"],
                ["Coordinate Frame", fiveAxisArtifact?.coordinateSpec.coordinateFrame ?? "—"],
                ["Unit", fiveAxisArtifact?.coordinateSpec.unit ?? "—"],
              ])}
            </section>

            <section className="config-section">
              <div className="section-title"><span>03</span><h2>Adapter Route</h2><em>{fiveAxisAdapters.length}</em></div>
              {fiveAxisAdapters.length ? (
                <div className="adapter-list">
                  {fiveAxisAdapters.map((adapter: ArtifactAdapterDescriptor) => (
                    <article key={adapter.adapterId}>
                      <strong>{adapter.adapterId}</strong>
                      <code>{adapter.sourceArtifactType} → {adapter.targetArtifactType}</code>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">catalog 尚未公开 artifact adapter。</div>
              )}
            </section>
          </aside>

          <section className="analysis-panel">
            <div className="analysis-heading">
              <div className="view-tabs" role="tablist" aria-label="Five-Axis 视图">
                <button role="tab" aria-selected={fiveAxisView === "manifest"} onClick={() => setFiveAxisView("manifest")}>M0–M5 Contract</button>
                <button role="tab" aria-selected={fiveAxisView === "report"} onClick={() => setFiveAxisView("report")}>Evaluation Report</button>
              </div>
              <div className="run-state">
                <span className={resultClass(fiveAxisRun?.run.executionStatus)}>{fiveAxisRun?.run.executionStatus ?? "Not run"}</span>
                <span className={resultClass(fiveAxisRun?.run.caseOutcome)}>{fiveAxisRun?.run.caseOutcome ?? "No claim"}</span>
              </div>
            </div>

            {fiveAxisView === "manifest" ? (
              <div className="manifest-view">
                <section className="notice-card">
                  <strong>F0 边界</strong>
                  <p>当前页面只验证机器契约、派生视图和适配器暴露，不发布几何、运动学、碰撞、设备可执行声明。</p>
                </section>

                <section className="stage-grid" aria-label="M0 到 M5 envelope map">
                  {(manifest?.envelopes ?? []).map((envelope) => (
                    <article className="stage-card" key={envelope.envelopeId}>
                      <header>
                        <span>{envelope.stage}</span>
                        <strong>{envelopeTitle(envelope)}</strong>
                      </header>
                      <code>{envelope.envelopeId}</code>
                      <p>{envelope.schemaId}</p>
                      <dl>
                        <div><dt>contentId</dt><dd title={envelope.contentId}>{shortHash(envelope.contentId)}</dd></div>
                        <div><dt>capabilities</dt><dd>{envelope.capabilityIds.length}</dd></div>
                        <div><dt>frame</dt><dd>{envelope.coordinateSpec?.coordinateFrame ?? "—"}</dd></div>
                      </dl>
                    </article>
                  ))}
                </section>

                <section className="manifest-meta">
                  <div>
                    <h3>Policy Versions</h3>
                    {detailRows(Object.entries(manifest?.policyVersions ?? {}).map(([key, value]) => [key, value]))}
                  </div>
                  <div>
                    <h3>Numeric Environment</h3>
                    {detailRows(Object.entries(manifest?.numericEnvironment ?? {}).map(([key, value]) => [key, value]))}
                  </div>
                  <div>
                    <h3>Tolerances</h3>
                    {(manifest?.tolerances.length ?? 0) > 0 ? (
                      <div className="adapter-list">
                        {manifest?.tolerances.map((item) => (
                          <article key={item.metricId}>
                            <strong>{item.metricId}</strong>
                            <code>{formatValue(item.value)} {item.unit}</code>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className="empty-state">manifest 没有公开 tolerance。</div>
                    )}
                  </div>
                </section>
              </div>
            ) : (
              <div className="report-view">
                <section className="notice-card">
                  <strong>通过范围：仅 F0 契约</strong>
                  <p>Passed 只表示 manifest、schema 与运行绑定验证完成；碰撞上下文和区间重建仍是 finding，不代表几何、运动学、碰撞或设备可执行。</p>
                </section>
                {!fiveAxisRun ? (
                  <div className="empty-overlay static-empty">尚未执行 F0 契约。点击“验证 F0 契约”后展示真实返回。</div>
                ) : (
                  <>
                    <section className="metric-strip single-row">
                      <div><span>RUN ID</span><strong>{shortHash(fiveAxisRun.run.runId)}</strong><small>{fiveAxisRun.run.runnerId}</small></div>
                      <div><span>REPORT HASH</span><strong>{shortHash(fiveAxisRun.run.reportContentHash)}</strong><small>{fiveAxisRun.report.evaluatorVersion ?? "—"}</small></div>
                      <div><span>BUNDLE HASH</span><strong>{shortHash(fiveAxisRun.bundleHash)}</strong><small>{fiveAxisRun.observation?.source ?? "—"}</small></div>
                    </section>

                    <div className="report-columns">
                      <section className="report-card">
                        <h3>Metric Results</h3>
                        <table className="compact-table">
                          <thead><tr><th>Metric</th><th>Status</th><th>Reason</th><th>Requires</th></tr></thead>
                          <tbody>
                            {fiveAxisRun.report.metricResults.map((metric) => (
                              <tr key={metric.metricId}>
                                <td><code>{metric.metricId}</code></td>
                                <td className={resultClass(metric.status)}>{metric.status}</td>
                                <td>{metric.reasonCode ?? "—"}</td>
                                <td>{metric.requires?.join(", ") ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </section>

                      <section className="report-card">
                        <h3>Domain Failures / Findings</h3>
                        {renderFindings(fiveAxisRun.report.domainFailures)}
                      </section>
                    </div>
                  </>
                )}
              </div>
            )}
          </section>

          <aside className="evidence-panel">
            <div className="panel-heading evidence-heading">
              <div><span className="eyebrow">RUNTIME EVIDENCE</span><h2>F0 状态与边界</h2></div>
              <button type="button" className="icon-button" onClick={downloadFiveAxisEvidence} disabled={!fiveAxisRun} title="下载 RunBundle JSON">⇩</button>
            </div>

            <section className="verdict-card">
              <span className="eyebrow">F0 VERDICT</span>
              <div className="verdict-row"><strong className={resultClass(fiveAxisRun?.run.caseOutcome)}>{fiveAxisRun?.run.caseOutcome ?? "Pending"}</strong><span>{fiveAxisRun ? "真实 RunBundle 已封存" : "等待执行"}</span></div>
              <div className="verdict-rule"><i /><span>Execution</span><b className={resultClass(fiveAxisRun?.run.executionStatus)}>{fiveAxisRun?.run.executionStatus ?? "—"}</b></div>
              <div className="verdict-rule"><i /><span>Contract Metric</span><b className={resultClass(fiveAxisRun?.report.metricResults[0]?.status)}>{fiveAxisRun?.report.metricResults[0]?.status ?? "—"}</b></div>
            </section>

            <section className="evidence-section">
              <div className="section-title compact"><span>01</span><h2>内容哈希</h2></div>
              <dl className="identity-list">
                    <div><dt>Sample Fixture</dt><dd title={manifest?.fixtureContentIds[0]}>{shortHash(manifest?.fixtureContentIds[0])}</dd></div>
                <div><dt>Run Spec</dt><dd title={fiveAxisRun?.run.runSpecHash}>{shortHash(fiveAxisRun?.run.runSpecHash)}</dd></div>
                <div><dt>Report</dt><dd title={fiveAxisRun?.run.reportContentHash}>{shortHash(fiveAxisRun?.run.reportContentHash)}</dd></div>
                <div><dt>Bundle</dt><dd title={fiveAxisRun?.bundleHash}>{shortHash(fiveAxisRun?.bundleHash)}</dd></div>
              </dl>
            </section>

            <section className="evidence-section">
              <div className="section-title compact"><span>02</span><h2>Claim / Capabilities</h2></div>
              {fiveAxisRun ? renderClaims(fiveAxisRun.claims) : <div className="placeholder-lines"><i /><i /><i /></div>}
              <div className="chip-row top-gap">
                {(fiveAxisRun?.report.capabilities ?? manifest?.capabilityIds.map((capabilityId) => ({ capabilityId, source: "Manifest" })) ?? []).map((item) => (
                  <span className="chip" key={`${item.capabilityId}:${item.source}`}>{item.capabilityId} · {item.source}</span>
                ))}
              </div>
            </section>

            <section className="evidence-section">
              <div className="section-title compact"><span>03</span><h2>执行链</h2></div>
              <ol className="execution-chain">
                <li className={Boolean(manifest) ? "done" : ""}><span>Manifest loaded</span><code>{manifest?.manifestId ?? "pending"}</code></li>
                <li className={Boolean(fiveAxisSpec) ? "done" : ""}><span>Derived view prepared</span><code>{fiveAxisSpec?.domainPackId ?? "pending"}</code></li>
                <li className={Boolean(fiveAxisRun) ? "done" : ""}><span>Contract evaluated</span><code>{fiveAxisRun?.run.runnerId ?? "pending"}</code></li>
                <li className={Boolean(fiveAxisRun?.claims.length) ? "done" : ""}><span>Core case claim only</span><code>{fiveAxisRun?.claims[0]?.claimId ? shortHash(fiveAxisRun.claims[0].claimId) : "pending"}</code></li>
              </ol>
            </section>
          </aside>
        </main>
      )}

      <footer className="statusbar">
        <span><i className={error ? "status-error" : ""} /> {error ? "1 error" : "0 errors"}</span>
        <span>domain: <code>{activeLab === "point" ? "ordered-point.domain-pack@1" : fiveAxisSpec?.domainPackId ?? "five-axis.domain-pack@1"}</code></span>
        <span>runner: <code>{activeLab === "point" ? pointRunnerLabel || "pending" : fiveAxisSpec?.runnerId ?? "pending"}</code></span>
        <span className="statusbar-right">{activeLab === "point" ? `${report?.armResults.length ?? 0}/2 arms` : `${fiveAxisAdapters.length} adapter route`} · local static registry</span>
      </footer>
    </div>
  );
}
