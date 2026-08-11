import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

import { executeExperiment, loadCatalog, loadContourExample } from "./api";
import type {
  Catalog,
  ExperimentArmResult,
  ExperimentReport,
  ExperimentSpec,
  MetricComparison,
  Point,
} from "./types";

type View = "geometry" | "metrics";

const futureLabs = ["Five-Axis", "Machine", "Intelligence", "Optimization"];

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
  if (value === true || value === "Passed" || value === "Succeeded" || value === "Accepted") {
    return "status-positive";
  }
  if (value === false || value === "Failed" || value === "ExecutionFailed" || value === "Rejected") {
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
  if (dimension < 2) throw new Error("每个点至少需要 X、Y 两个坐标。\n");
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

function projectPaths(spec: ExperimentSpec, report: ExperimentReport | null): ProjectedPath[] {
  const sources = [
    { key: "reference", label: "共享输入", tone: "reference" as const, points: spec.sharedInput.points },
    ...(report?.armResults ?? []).flatMap((arm, index) => {
      const points = arm.runBundle?.observation?.artifact.points;
      return points
        ? [{
            key: arm.armId,
            label: arm.armId,
            tone: index === 0 ? "baseline" as const : "candidate" as const,
            points,
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

export function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [spec, setSpec] = useState<ExperimentSpec | null>(null);
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const [pointsText, setPointsText] = useState("[]");
  const [errorVector, setErrorVector] = useState("0, 0.08");
  const [gain, setGain] = useState("0.75");
  const [threshold, setThreshold] = useState("0.03");
  const [view, setView] = useState<View>("geometry");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const importInput = useRef<HTMLInputElement>(null);

  const hydrate = (next: ExperimentSpec) => {
    setSpec(next);
    setPointsText(JSON.stringify(next.sharedInput.points, null, 2));
    const vector = next.parameterSet.values.errorVector;
    setErrorVector(Array.isArray(vector) ? vector.join(", ") : "0, 0.08");
    setGain(String(next.parameterSet.values.compensationGain ?? 0.75));
    setThreshold(String(metricThreshold(next)));
  };

  useEffect(() => {
    let active = true;
    Promise.all([loadCatalog(), loadContourExample()])
      .then(async ([nextCatalog, example]) => {
        if (!active) return;
        setCatalog(nextCatalog);
        hydrate(example);
        const initialReport = await executeExperiment(example);
        if (active) setReport(initialReport);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "工作台初始化失败。");
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const paths = useMemo(() => (spec ? projectPaths(spec, report) : []), [spec, report]);
  const baseline = report?.armResults[0];
  const candidate = report?.armResults[1];
  const compatible = report?.comparison?.compatibility.compatible;
  const unit = spec?.sharedInput.semantics?.unit ?? "coordinate-unit";
  const dimension = spec?.sharedInput.points[0]?.length ?? 0;
  const runnerLabel = [...new Set(spec?.arms.map((arm) => arm.runnerId ?? "unknown-runner") ?? [])].join(", ");

  const buildSpec = (): ExperimentSpec => {
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

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = buildSpec();
      setSpec(next);
      setReport(await executeExperiment(next));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "实验执行失败。");
    } finally {
      setBusy(false);
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
      hydrate(next);
      setReport(null);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? `无法导入：${reason.message}` : "无法导入实验文件。");
    }
  };

  const downloadEvidence = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${report.experimentSpec.experimentId}-evidence.json`;
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
            <span>Experiment Workbench</span>
          </div>
        </div>
        <div className="topbar-context">
          <span className={`connection-dot ${error ? "offline" : ""}`} />
          <span className="context-label">{error ? "需要检查" : "本地 API 可用"}</span>
          <code>{spec?.experimentId ?? "loading"}</code>
        </div>
        <div className="topbar-actions">
          <input ref={importInput} type="file" accept="application/json,.json" hidden onChange={importSpec} />
          <button className="button button-secondary" type="button" onClick={() => importInput.current?.click()}>
            导入 JSON
          </button>
          <button className="button button-primary" type="button" onClick={run} disabled={busy || !spec}>
            {busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▶</span>}
            {busy ? "执行中" : "运行实验"}
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <strong>未完成</strong><span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="关闭错误">×</button>
        </div>
      )}

      <div className="lab-switcher" aria-label="领域实验室">
        <button className="lab active" type="button"><span>01</span>Point Lab</button>
        {futureLabs.map((lab, index) => (
          <button className="lab" type="button" disabled key={lab} title="领域包尚未接入">
            <span>0{index + 2}</span>{lab}<small>planned</small>
          </button>
        ))}
      </div>

      <main className="workspace">
        <aside className="config-panel">
          <div className="panel-heading">
            <div><span className="eyebrow">EXPERIMENT SPEC</span><h1>双臂实验配置</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>共享输入</h2><em>{spec?.sharedInput.points.length ?? 0} pts</em></div>
            <label className="field-label" htmlFor="points">有序离散点（JSON）</label>
            <textarea id="points" className="code-input points-input" value={pointsText} onChange={(event) => setPointsText(event.target.value)} spellCheck={false} />
            <div className="input-meta">
              <span>{spec?.sharedInput.semantics?.coordinateFrame ?? "frame unknown"}</span>
              <span>{unit}</span>
              <span>{spec?.sharedInput.semantics?.closed ? "closed" : "open"}</span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>参数集</h2><em>frozen</em></div>
            <label className="field-label" htmlFor="error-vector">误差向量（{unit}）</label>
            <input id="error-vector" className="text-input mono" value={errorVector} onChange={(event) => setErrorVector(event.target.value)} />
            <div className="gain-row">
              <label className="field-label" htmlFor="gain">补偿增益</label><output>{gain}</output>
            </div>
            <input id="gain" type="range" min="0" max="1" step="0.01" value={gain} onChange={(event) => setGain(event.target.value)} />
            <label className="field-label threshold-label" htmlFor="threshold">最大偏差硬门槛（{unit}）</label>
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
              <button role="tab" aria-selected={view === "geometry"} onClick={() => setView("geometry")}>几何轨迹</button>
              <button role="tab" aria-selected={view === "metrics"} onClick={() => setView("metrics")}>指标比较</button>
            </div>
            <div className="run-state">
              <span className={resultClass(report?.executionStatus)}>{report?.executionStatus ?? "Not run"}</span>
              <span className={resultClass(compatible)}>{compatible === undefined ? "等待比较" : compatible ? "Strict compatible" : "Incompatible"}</span>
            </div>
          </div>

          {view === "geometry" ? (
            <div className="geometry-view">
              <div className="plot-toolbar">
                <div className="legend">
                  {paths.map((path) => <span className={`legend-${path.tone}`} key={path.key}><i />{path.label}</span>)}
                </div>
                <code>
                  {spec?.sharedInput.semantics?.coordinateFrame ?? "unknown frame"} · XY
                  {dimension > 2 ? ` projection of ${dimension}D` : ""} · {unit}
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
                  {paths.map((path) => (
                    <g className={`path-series path-${path.tone}`} key={path.key}>
                      <path d={path.d} />
                      {path.dots.map(([x, y], index) => <circle key={`${path.key}-${index}`} cx={x} cy={y} r={path.tone === "reference" ? 2.5 : 3.5} />)}
                    </g>
                  ))}
                  <text x="600" y="326" className="axis-label">X</text>
                  <text x="37" y="42" className="axis-label">Y</text>
                </svg>
                {!report && !busy && <div className="empty-overlay">配置已加载，运行实验以生成双臂观测。</div>}
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
                      <td>{comparisonWinner(metric, report!)}</td>
                    </tr>
                  ))}
                  {!report?.comparison?.metricComparisons.length && <tr><td colSpan={5} className="empty-row">尚无可比较指标</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          <div className="metric-strip">
            <div><span>BASELINE MAX</span><strong>{armMetric(baseline, "paired.euclidean.max")}</strong><small className={resultClass(baseline?.caseOutcome)}>{baseline?.caseOutcome ?? "—"}</small></div>
            <div><span>CANDIDATE MAX</span><strong>{armMetric(candidate, "paired.euclidean.max")}</strong><small className={resultClass(candidate?.caseOutcome)}>{candidate?.caseOutcome ?? "—"}</small></div>
            <div><span>THRESHOLD</span><strong>≤ {threshold} {unit}</strong><small>hard gate</small></div>
            <div><span>COMPARISON</span><strong className={resultClass(compatible)}>{compatible ? "Compatible" : compatible === false ? "Blocked" : "—"}</strong><small>lineage strict</small></div>
          </div>
        </section>

        <aside className="evidence-panel">
          <div className="panel-heading evidence-heading">
            <div><span className="eyebrow">SEALED OUTPUT</span><h2>证据与谱系</h2></div>
            <button type="button" className="icon-button" onClick={downloadEvidence} disabled={!report} title="下载证据 JSON">⇩</button>
          </div>

          <section className="verdict-card">
            <span className="eyebrow">EXPERIMENT VERDICT</span>
            <div className="verdict-row">
              <strong className={resultClass(report?.caseOutcome)}>{report?.caseOutcome ?? "Pending"}</strong>
              <span>{report ? "证据包已封存" : "等待执行"}</span>
            </div>
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
              <li className={report ? "done" : ""}><span>Subjects executed</span><code>{runnerLabel || "pending"}</code></li>
              <li className={compatible ? "done" : ""}><span>Strict comparison</span><code>{report?.comparison?.policyId ?? "pending"}</code></li>
            </ol>
          </section>
        </aside>
      </main>

      <footer className="statusbar">
        <span><i className={error ? "status-error" : ""} /> {error ? "1 error" : "0 errors"}</span>
        <span>domain: <code>ordered-point.domain-pack@1</code></span>
        <span>runner: <code>{runnerLabel || "pending"}</code></span>
        <span className="statusbar-right">{report?.armResults.length ?? 0}/2 arms · local static registry</span>
      </footer>
    </div>
  );
}
