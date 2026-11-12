import { ChangeEvent, useRef, useState } from "react";
import "./styles.css";
import { DiagnosticPlots, Diagnostics, FocusLocation } from "./DiagnosticPlots";

type JsonObject = Record<string, unknown>;
type Role = "case" | "baseline" | "candidate";
type Inputs = Record<Role, JsonObject | null>;
interface Location { sampleIndex: number; t: number; axis?: string; referenceSegmentIndex?: number }
interface Metric { value?: number | null; unit: string; location?: Location }
interface Check extends Metric { checkId: string; status: string; limit: number; reason?: string }
interface Analysis { algorithmId: string; algorithmVersion: string; sourceKind: string; sampleCount: number; metrics: Record<string, Metric>; checks: Check[] }
interface Difference { metricId: string; baseline?: number | null; candidate?: number | null; delta?: number | null; unit: string; tolerance: number; status: string; reason?: string }
interface Report { caseId: string; caseContentHash: string; scope: string; outcome: string; baseline: Analysis; candidate: Analysis; differences: Difference[]; reasons: string[]; reportContentHash: string; uncheckedProperties: string[] }
interface Scenario { id: string; title: string; category: string; purpose: string; expectedOutcome: string }

const labels: Record<Role, string> = { case: "刀路与约束", baseline: "基线 A", candidate: "候选 B" };
const metricLabels: Record<string, string> = { durationSeconds: "运动时间", sampledPathDeviationMaxMm: "采样路径偏差", computationSeconds: "算法计算耗时" };
const statusLabels: Record<string, string> = { Improved: "改善", Regressed: "退步", Tradeoff: "存在取舍", WithinTolerance: "容差内无变化", CandidateViolatesLimits: "候选超限", Inconclusive: "证据不足", NotComparable: "不可比较", WithinLimit: "满足采样限制", Violated: "超限", InsufficientSamples: "样本不足", NotAssessed: "未评估", InputRejected: "输入拒绝" };

async function requestJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1/benchmarks/cnc/${path}`, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const payload = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.join(".") ?? "input"}: ${item.msg ?? "invalid"}`).join("\n")
      : String(payload.detail ?? "请检查输入文件。");
    throw new Error(`比较未完成（${response.status}）：${detail}`);
  }
  return payload as T;
}

function download(value: unknown, filename: string): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function number(value: number | null | undefined): string {
  if (value == null) return "未提供";
  return value === 0 ? "0" : Number(value.toPrecision(6)).toString();
}

function locate(location?: Location): string {
  if (!location) return "—";
  return `样本 ${location.sampleIndex} · ${number(location.t)} s${location.axis ? ` · ${location.axis} 轴` : ""}${location.referenceSegmentIndex !== undefined ? ` · 路径段 ${location.referenceSegmentIndex}` : ""}`;
}

function object(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("文件内容必须是一个 JSON 对象。");
  return value as JsonObject;
}

function previewPoints(value: JsonObject | null, reference = false): [number, number, number][] {
  const raw = reference ? value?.referencePath : value?.samples;
  if (!Array.isArray(raw)) return [];
  const stride = Math.max(1, Math.ceil(raw.length / 1500));
  return raw.filter((_, index) => index % stride === 0 || index === raw.length - 1).map((item: unknown) => {
    if (!reference && item && typeof item === "object") return (item as { positionMm?: unknown }).positionMm;
    return item;
  }).filter((item): item is [number, number, number] => Array.isArray(item) && item.length === 3 && item.every(value => typeof value === "number" && Number.isFinite(value)));
}

function PathPreview({ inputs }: { inputs: Inputs }) {
  const [plane, setPlane] = useState("XY");
  const axes: [0 | 1 | 2, 0 | 1 | 2] = plane === "XY" ? [0, 1] : plane === "XZ" ? [0, 2] : [1, 2];
  const paths = [previewPoints(inputs.case, true), previewPoints(inputs.baseline), previewPoints(inputs.candidate)];
  const all = paths.flat();
  if (!all.length) return null;
  const xs = all.map(point => point[axes[0]]);
  const ys = all.map(point => point[axes[1]]);
  const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
  const scale = Math.min(640 / Math.max(xmax - xmin, 0.001), 150 / Math.max(ymax - ymin, 0.001));
  const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2;
  return <figure className="cnc-preview">
    <figcaption><strong>{plane} 轨迹预览</strong><label>投影 <select aria-label="轨迹投影" value={plane} onChange={event => setPlane(event.target.value)}>{["XY", "XZ", "YZ"].map(name => <option key={name}>{name}</option>)}</select></label><span>参考路点 <i className="reference" /> 基线 A <i className="baseline" /> 候选 B <i className="candidate" /></span></figcaption>
    <svg viewBox="0 0 700 200" role="img" aria-label={`参考路点与 A/B 指令的 ${plane} 投影`}>
      <path d="M20 100H680M350 10V190" className="cnc-grid" />
      {paths.map((points, index) => <polyline key={index} className={["reference", "baseline", "candidate"][index]} points={points.map(point => `${350 + (point[axes[0]] - cx) * scale},${100 - (point[axes[1]] - cy) * scale}`).join(" ")} />)}
    </svg>
    <p>预览最多显示每条轨迹约 1,500 个点；报告使用所有导入样本。参考路点只作直线连接，不绘制圆弧；连接线不代表采样间运动。</p>
  </figure>;
}

export function CncBenchmarkWorkbench() {
  const [inputs, setInputs] = useState<Inputs>({ case: null, baseline: null, candidate: null });
  const [filenames, setFilenames] = useState<Partial<Record<Role, string>>>({});
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [experiment, setExperiment] = useState<{ definition: Scenario; provenance: unknown } | null>(null);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [diagnosticError, setDiagnosticError] = useState<string | null>(null);
  const [focus, setFocus] = useState<FocusLocation | null>(null);
  const revision = useRef(0);
  const ready = Object.values(inputs).every(Boolean);
  const synthetic = inputs.baseline?.sourceKind === "synthetic-example" || inputs.candidate?.sourceKind === "synthetic-example";
  const offlineSut = inputs.baseline?.sourceKind === "offline-sut" || inputs.candidate?.sourceKind === "offline-sut";

  async function importFile(role: Role, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const current = ++revision.current;
    setReport(null); setDiagnostics(null); setDiagnosticError(null); setFocus(null); setExperiment(null); setError(null); setBusy(true);
    // A failed replacement must not leave the old input looking current.
    setInputs(previous => ({ ...previous, [role]: null }));
    setFilenames(previous => ({ ...previous, [role]: file.name }));
    try {
      if (file.size > 16 * 1024 * 1024) throw new Error("单个文件不能超过 16 MiB。");
      const parsed = object(JSON.parse((await file.text()).replace(/^\uFEFF/, "")));
      if (current === revision.current) setInputs(previous => ({ ...previous, [role]: parsed }));
    } catch (reason) {
      if (current === revision.current) setError(`${labels[role]}：${reason instanceof Error ? reason.message : "无法读取文件"}`);
    } finally { if (current === revision.current) setBusy(false); }
  }

  async function loadExample() {
    const current = ++revision.current;
    setBusy(true); setReport(null); setDiagnostics(null); setDiagnosticError(null); setFocus(null); setExperiment(null); setError(null);
    try {
      const payload = await requestJson<Record<Role, JsonObject>>("example");
      if (current === revision.current) { setInputs(payload); setFilenames({ case: "example.case.json", baseline: "example.baseline.json", candidate: "example.candidate.json" }); }
    } catch (reason) { if (current === revision.current) setError(reason instanceof Error ? reason.message : "示例加载失败"); }
    finally { if (current === revision.current) setBusy(false); }
  }

  async function compare() {
    if (!ready) return;
    const current = ++revision.current;
    setBusy(true); setReport(null); setDiagnostics(null); setDiagnosticError(null); setFocus(null); setError(null);
    try {
      const next = await requestJson<Report>("compare", inputs);
      if (current === revision.current) setReport(next);
    } catch (reason) { if (current === revision.current) setError(reason instanceof Error ? reason.message : "比较失败"); }
    finally { if (current === revision.current) setBusy(false); }
  }

  async function browseCases() {
    const current = ++revision.current;
    setBusy(true); setError(null);
    try { const rows = await requestJson<Scenario[]>("validation-cases"); if (current === revision.current) { setScenarios(rows); setScenarioId(rows[0]?.id ?? ""); } }
    catch (reason) { if (current === revision.current) setError(reason instanceof Error ? reason.message : "用例加载失败"); }
    finally { if (current === revision.current) setBusy(false); }
  }

  async function loadCase() {
    const current = ++revision.current;
    setBusy(true); setReport(null); setDiagnostics(null); setDiagnosticError(null); setFocus(null); setError(null); setExperiment(null);
    setInputs({ case: null, baseline: null, candidate: null }); setFilenames({});
    try {
      const payload = await requestJson<{ request: Inputs; definition: Scenario; provenance: unknown }>(`validation-cases/${encodeURIComponent(scenarioId)}`);
      if (current === revision.current) { setInputs(payload.request); setExperiment(payload); setFilenames({ case: `${scenarioId}.case.json`, baseline: `${scenarioId}.baseline.json`, candidate: `${scenarioId}.candidate.json` }); }
    } catch (reason) { if (current === revision.current) setError(reason instanceof Error ? reason.message : "用例生成失败"); }
    finally { if (current === revision.current) setBusy(false); }
  }

  async function showDiagnostics() {
    const current = ++revision.current;
    setBusy(true); setDiagnosticError(null);
    try { const payload = await requestJson<Diagnostics>("diagnostics", inputs); if (current === revision.current) setDiagnostics(payload); }
    catch (reason) { if (current === revision.current) setDiagnosticError(reason instanceof Error ? reason.message : "诊断未完成"); }
    finally { if (current === revision.current) setBusy(false); }
  }

  return <main className="cnc-benchmark">
    <div className="cnc-content">
      <div className="cnc-heading">
        <div><span className="eyebrow">CNC ALGORITHM BENCHMARK</span><h1>比较两版 CNC 算法</h1><p>导入同一案例的 XYZ 指令轨迹，检查采样误差与约束，定位版本差异。</p></div>
        <button className="button button-secondary" type="button" onClick={loadExample} disabled={busy}>载入回归示例</button>
      </div>
      <section className="cnc-method" aria-label="V1 评估方法">
        <h2>离线评估 V1</h2>
        <ol><li>固定同一 Case：几何、周期、坐标系、限制及比较容差。</li><li>先做 A/A 重放，确认输入身份与确定性。</li><li>合同错误直接拒绝；候选超限优先，基线无效或遍历未评估则证据不足。</li><li>通过约束门后比较时间、误差及声明的指标：更快但更差是取舍，不做加权总分。</li><li>定位最差样本，查看时域曲线，再保存输入、来源及报告复核。</li></ol>
        <button className="button button-secondary" type="button" disabled={busy} onClick={browseCases}>浏览 V1 评估用例</button>
        {scenarios.length > 0 && <div className="cnc-chart-controls"><label>评估用例 <select aria-label="评估用例" value={scenarioId} disabled={busy} onChange={event => setScenarioId(event.target.value)}>{scenarios.map(item => <option key={item.id} value={item.id}>{item.title} · {item.category}</option>)}</select></label><button className="button button-secondary" type="button" disabled={busy || !scenarioId} onClick={loadCase}>生成并载入用例</button></div>}
        {experiment && <div className="cnc-experiment-note"><strong>{experiment.definition.title}</strong><p>{experiment.definition.purpose}</p><p>预期：{statusLabels[experiment.definition.expectedOutcome] ?? experiment.definition.expectedOutcome}。这是评估器测试预期，不是生产算法目标。</p><button className="cnc-link" type="button" onClick={() => download(experiment.provenance, "cnc-experiment-provenance.json")}>下载实验来源清单</button></div>}
      </section>
      <div className="cnc-inputs">
        {(["case", "baseline", "candidate"] as Role[]).map((role, index) => <section className="cnc-input-card" key={role}>
          <span className="cnc-step">0{index + 1}</span><h2>{labels[role]}</h2>
          <p>{role === "case" ? "参考折线、坐标系、固定周期与限制" : "算法名称、版本与固定周期 XYZ 位置"}</p>
          <label className="cnc-file-label">选择{labels[role]}文件<input type="file" accept=".json,application/json" aria-label={`选择${labels[role]}文件`} disabled={busy} onChange={event => importFile(role, event)} /></label>
          <strong className="cnc-filename">{filenames[role] ?? "尚未导入"}</strong>
          {inputs[role] && <div className="cnc-input-description"><span>{String(inputs[role]?.caseId ?? inputs[role]?.algorithmId ?? "待验证输入")}</span>{role !== "case" && <span>版本：{String(inputs[role]?.algorithmVersion ?? "未填写")}</span>}<button type="button" className="cnc-link" disabled={busy} onClick={() => download(inputs[role], `${role}.json`)}>下载此输入</button></div>}
        </section>)}
      </div>
      {synthetic && <p className="cnc-example-note">当前包含合成示例，用于演示回归定位；请替换为实际算法导出结果后再作工程判断。</p>}
      {offlineSut && <p className="cnc-example-note">当前包含离线 SUT 数据，用于验证评估器接入与重放；不是生产算法、控制器或加工质量证据。A/A 无差异不代表算法改善。</p>}
      <div className="cnc-action-row"><p>单位：mm · XYZ 线性轴 · 按声明的固定周期检查</p><div><button className="button button-secondary" type="button" disabled={!ready || busy} onClick={() => download(inputs, "cnc-benchmark-request.json")}>下载可重放输入</button><button className="button button-primary" type="button" disabled={!ready || busy} onClick={compare}>{busy ? "处理中…" : "比较 A / B"}</button></div></div>
      {error && <div role="alert" className="cnc-error">{error}</div>}
      <PathPreview inputs={inputs} />
      {report ? <section className="cnc-results" aria-label="算法比较报告">
        <div className="cnc-result-heading"><div><span className="eyebrow">采样命令范围内的比较</span><h2 className={`cnc-outcome ${report.outcome}`}>{statusLabels[report.outcome] ?? report.outcome}</h2><p>{report.baseline.algorithmId} {report.baseline.algorithmVersion} → {report.candidate.algorithmId} {report.candidate.algorithmVersion}</p></div><button className="button button-secondary" type="button" onClick={() => download(report, "cnc-benchmark-report.json")}>下载报告</button></div>
        <div className="cnc-table-scroll"><table><thead><tr><th>比较指标</th><th>基线 A</th><th>候选 B</th><th>B − A</th><th>结论</th></tr></thead><tbody>{report.differences.map(item => <tr key={item.metricId}><th>{metricLabels[item.metricId] ?? item.metricId}<small>{item.unit} · 比较容差 {number(item.tolerance)}</small></th><td>{number(item.baseline)}</td><td>{number(item.candidate)}</td><td>{item.delta == null ? "—" : number(item.delta)}</td><td className={item.status}>{statusLabels[item.status] ?? item.status}{item.reason && <small>{item.reason}</small>}</td></tr>)}</tbody></table></div>
        <h3>约束检查与最差位置</h3><p className="cnc-muted">速度、加速度与 Jerk 使用指令位置的离散差分。轨迹开头和结尾之外的状态不在输入中，未推断启停边界。</p>
        <button className="button button-secondary" type="button" disabled={busy} onClick={showDiagnostics}>载入时域诊断</button>
        {diagnosticError && <p role="alert" className="cnc-error">报告仍有效；{diagnosticError}</p>}
        {diagnostics && <><button className="cnc-link" type="button" onClick={() => download(diagnostics, "cnc-diagnostics.json")}>下载诊断序列</button><DiagnosticPlots key={report.reportContentHash} data={diagnostics} limits={inputs.case?.axisLimits as Parameters<typeof DiagnosticPlots>[0]["limits"] ?? []} pathLimit={Number(inputs.case?.maximumPathDeviationMm ?? 0)} focus={focus} /></>}
        <div className="cnc-table-scroll"><table><thead><tr><th>检查项</th><th>基线 A</th><th>候选 B</th><th>限制</th><th>候选最差位置</th></tr></thead><tbody>{report.candidate.checks.map((check, index) => <tr key={check.checkId}><th>{check.checkId}<small>{check.unit}</small></th><td className={report.baseline.checks[index]?.status}>{number(report.baseline.checks[index]?.value)}</td><td className={check.status}>{number(check.value)}<small>{statusLabels[check.status] ?? check.status}</small>{check.reason && <small>{check.reason}</small>}</td><td>{number(check.limit)}</td><td>{check.location ? <button className="cnc-link" type="button" disabled={busy} onClick={() => { setFocus(check.location!); if (!diagnostics) void showDiagnostics(); }}>{locate(check.location)}</button> : "—"}</td></tr>)}</tbody></table></div>
        <details className="cnc-report-details"><summary>结果身份与计算说明</summary><p>案例：{report.caseId}</p><p>报告：<code>{report.reportContentHash}</code></p><ul>{report.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></details>
      </section> : <section className="cnc-empty"><h2>从一次可复现的版本比较开始</h2><p>上传三份文件，或载入带有已知偏差的示例。报告会保留指标差异以及超限的样本、时间和轴。</p></section>}
      <aside className="cnc-scope"><strong>本次检查覆盖什么？</strong><p>采样点到参考路径的单向距离、首尾位置、轴行程和离散 V/A/J 差分，以及同条件下声明的计算耗时。单调直线另检查采样方向与完成性；圆弧、闭合路径和转弯的遍历未评估，不能据此给出强改善结论。尚未验证采样间连续运动、一般路径覆盖、碰撞、实机跟随或加工质量。采样结果中的“改善”只针对本页列出的指标。</p><p>算法导出格式、Case hash 生成方法与 CLI 用法见仓库的 CNC-BENCHMARK.md。</p></aside>
    </div>
  </main>;
}
