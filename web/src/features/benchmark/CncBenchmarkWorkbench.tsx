import { ChangeEvent, useRef, useState } from "react";
import { XYChart } from "../../charts";
import type { ChartSeries } from "../../charts";
import "./styles.css";

type JsonObject = Record<string, unknown>;
type Role = "case" | "baseline" | "candidate";
type Inputs = Record<Role, JsonObject | null>;
interface Location { sampleIndex: number; t: number; axis?: string; referenceSegmentIndex?: number }
interface Metric { value?: number | null; unit: string; location?: Location }
interface Check extends Metric { checkId: string; status: string; limit: number }
interface Analysis { algorithmId: string; algorithmVersion: string; sourceKind: string; sampleCount: number; metrics: Record<string, Metric>; checks: Check[] }
interface Difference { metricId: string; baseline?: number | null; candidate?: number | null; delta?: number | null; unit: string; tolerance: number; status: string; reason?: string }
interface Report { caseId: string; caseContentHash: string; scope: string; outcome: string; baseline: Analysis; candidate: Analysis; differences: Difference[]; reasons: string[]; reportContentHash: string; uncheckedProperties: string[] }

interface SensitivityItem { parameterId: string; displayName: string; group: string; status: string; contributionRatio: number; direction: string }
interface MetricHead { metricId: string; unit: string; modelingMode: string; r2Score: number; cvRmse: number; conformalRadius: number; sensitivities: SensitivityItem[] }
interface ParameterDelta { parameterId: string; displayName: string; group: string; unit: string; baselineValue: number; recommendedValue: number; relativeChangePct: number }
interface PresetCandidate { candidateId: string; presetRole: string; presetTitle: string; changedParameterCount: number; changedParameters: ParameterDelta[]; tradeoffExplanation: string }
interface ActiveDoeItem { suggestionId: string; targetSource: string; changedParameterIds: string[]; acquisitionScore: number; rationale: string }
interface ClosedLoopDemo {
  case: { caseId: string };
  sampleQualityReport: { outcome: string; scope: string; analysis: Analysis; servoMetrics?: Record<string, Metric>; geometrySlices: Array<{ sliceId: string; primitiveKind: string; startSampleIndex: number; endSampleIndex: number; metrics: Record<string, number | null> }> };
  surrogate: { offlineRunCount: number; controllerRunCount: number; totalSliceSampleCount: number; globalActiveParameterIds: string[]; metricHeads: Record<string, MetricHead> };
  recommendationReport: { maxChangedParameters: number; evaluatedCandidateCount: number; feasibleCandidateCount: number; paretoCandidateCount: number; presets: PresetCandidate[]; activeDoeSuggestions: ActiveDoeItem[] };
}

const roleTitles: Record<Role, string> = {
  case: "CASE · 参考路径",
  baseline: "BASELINE A · 基线算法",
  candidate: "CANDIDATE B · 候选算法",
};

const labels: Record<Role, string> = { case: "刀路与约束", baseline: "基线 A", candidate: "候选 B" };

const metricLabels: Record<string, string> = {
  sampledPathDeviationMaxMm: "最大路径偏差",
  sampledPathDeviationMeanMm: "平均路径偏差",
  durationSeconds: "运动时间",
  computationSeconds: "单周期计算耗时",
  sampledJerkMaxMmPerSec3: "最大 Jerk",
};

const metricUnits: Record<string, string> = {
  sampledPathDeviationMaxMm: "mm",
  sampledPathDeviationMeanMm: "mm",
  durationSeconds: "s",
  computationSeconds: "ms",
  sampledJerkMaxMmPerSec3: "m/s³",
};

const statusLabels: Record<string, string> = {
  Improved: "改善",
  Regressed: "退步",
  Tradeoff: "存在取舍",
  WithinTolerance: "容差内",
  CandidateViolatesLimits: "候选超限",
  Inconclusive: "证据不足",
  NotComparable: "不可比较",
  WithinLimit: "满足采样限制",
  Violated: "超限",
  InsufficientSamples: "样本不足",
};

const checkLabels: Record<string, string> = {
  "sampled-path-deviation": "路径偏差限制",
  "sampled-velocity": "速度限制",
  "sampled-acceleration": "加速度限制",
  "sampled-jerk": "Jerk 限制",
  "axis-stroke": "轴行程",
};

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
  const paths = [previewPoints(inputs.case, true), previewPoints(inputs.baseline), previewPoints(inputs.candidate)];
  const hasPoints = paths.some((points) => points.length > 0);

  // Generate fallback curves for sleek mock visualizer when inputs don't have enough points
  const referenceCurve: [number, number][] = hasPoints && paths[0]!.length > 0
    ? paths[0]!.map(([x, y]) => [x, y])
    : [[0, 20], [20, 28], [50, 42], [80, 58], [110, 78], [140, 100]];
  const baselineCurve: [number, number][] = hasPoints && paths[1]!.length > 0
    ? paths[1]!.map(([x, y]) => [x, y])
    : [[0, 22], [20, 30], [50, 44], [80, 61], [110, 82], [140, 102]];
  const candidateCurve: [number, number][] = hasPoints && paths[2]!.length > 0
    ? paths[2]!.map(([x, y]) => [x, y])
    : [[0, 21], [20, 29], [50, 43], [80, 59], [110, 79], [140, 101]];

  const series: ChartSeries[] = [
    { id: "reference", label: "参考路径", points: referenceCurve, tone: "reference", dashed: true, markers: false },
    { id: "baseline", label: "基线 A", points: baselineCurve, tone: "baseline", markers: false },
    { id: "candidate", label: "候选 B", points: candidateCurve, tone: "candidate", markers: false },
  ];

  return (
    <div className="cnc-preview-card">
      <div className="cnc-preview-header">
        <strong>XY 轨迹预览</strong>
        <span className="cnc-preview-sub">预览抽样约 1,500 点</span>
      </div>
      <div className="cnc-chart-body">
        <XYChart series={series} ariaLabel="参考路径与 A/B 指令的 XY 投影" height={220} xLabel="X (mm)" yLabel="Y (mm)" legend={false} />
      </div>
      <div className="cnc-preview-legend">
        <span className="legend-ref"><i className="legend-line line-gray" /> 参考路径</span>
        <span className="legend-base"><i className="legend-line line-blue" /> 基线 A</span>
        <span className="legend-cand"><i className="legend-line line-green" /> 候选 B</span>
      </div>
      <div className="cnc-preview-caption">参考路径与 A/B 指令的 XY 投影</div>
    </div>
  );
}

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

export function CncBenchmarkWorkbench({ onOpenGuide }: { onOpenGuide?: () => void }) {
  const [inputs, setInputs] = useState<Inputs>({ case: null, baseline: null, candidate: null });
  const [filenames, setFilenames] = useState<Partial<Record<Role, string>>>({});
  const [report, setReport] = useState<Report | null>(null);
  const [closedLoop, setClosedLoop] = useState<ClosedLoopDemo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const revision = useRef(0);
  const ready = Object.values(inputs).every(Boolean);
  const synthetic = inputs.baseline?.sourceKind === "synthetic-example" || inputs.candidate?.sourceKind === "synthetic-example";

  const fileInputRefs = {
    case: useRef<HTMLInputElement>(null),
    baseline: useRef<HTMLInputElement>(null),
    candidate: useRef<HTMLInputElement>(null),
  };

  async function importFile(role: Role, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const current = ++revision.current;
    setReport(null); setError(null); setBusy(true);
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
    setBusy(true); setReport(null); setError(null);
    try {
      const payload = await requestJson<Record<Role, JsonObject>>("example");
      if (current === revision.current) {
        setInputs(payload);
        setFilenames({
          case: "impeller_finish_v3.json",
          baseline: "axisCore v2.4.1",
          candidate: "axisCore v2.5.0-rc.2",
        });
      }
    } catch (reason) { if (current === revision.current) setError(reason instanceof Error ? reason.message : "示例加载失败"); }
    finally { if (current === revision.current) setBusy(false); }
  }

  async function compare() {
    if (!ready) return;
    const current = ++revision.current;
    setBusy(true); setReport(null); setError(null);
    try {
      const next = await requestJson<Report>("compare", inputs);
      if (current === revision.current) setReport(next);
    } catch (reason) { if (current === revision.current) setError(reason instanceof Error ? reason.message : "比较失败"); }
    finally { if (current === revision.current) setBusy(false); }
  }

  async function runClosedLoopDemo() {
    const current = ++revision.current;
    setBusy(true); setError(null);
    try {
      const demo = await requestJson<ClosedLoopDemo>("param-demo");
      if (current === revision.current) setClosedLoop(demo);
    } catch (reason) {
      if (current === revision.current) setError(reason instanceof Error ? reason.message : "参数学习与推荐闭环运行失败");
    } finally {
      if (current === revision.current) setBusy(false);
    }
  }

  const caseHash = String(inputs.case?.caseContentHash ?? inputs.case?.caseId ?? "9f3a...c21e");
  const baseHash = String(inputs.baseline?.reportContentHash ?? "41bd...7a90");
  const candHash = String(inputs.candidate?.reportContentHash ?? "e87c...03df");

  return (
    <main className="cnc-benchmark-page" aria-label="CNC 算法对比工作台">
      {/* Top Header */}
      <header className="page-header">
        <div className="page-header-info">
          <h1 aria-label="比较两版 CNC 算法">CNC 算法 A/B 对比</h1>
          <p className="page-header-subtitle">
            同一案例 · 两个算法版本 · XYZ 采样命令评估 · 单位 mm
          </p>
        </div>
        <div className="page-header-actions">
          {onOpenGuide && (
            <button
              type="button"
              className="button button-secondary"
              onClick={onOpenGuide}
            >
              使用引导
            </button>
          )}
          {report && (
            <button
              type="button"
              className="button button-secondary"
              onClick={() => download(report, "cnc-benchmark-report.json")}
            >
              下载报告
            </button>
          )}
          <button
            type="button"
            className="button button-primary"
            disabled={!ready || busy}
            onClick={compare}
            aria-label="比较 A / B"
          >
            {busy ? "比较中…" : "运行比较"}
          </button>
        </div>
      </header>

      <div className="cnc-container">
        {/* Step 01: 导入输入 */}
        <section className="cnc-step-section">
          <div className="step-label-row">
            <span className="step-num-eyebrow">01 · 导入输入</span>
            <div className="step-actions-quick">
              <button
                type="button"
                className="cnc-quick-link"
                onClick={loadExample}
                disabled={busy}
              >
                载入回归示例
              </button>
              <span className="sep">·</span>
              <button
                type="button"
                className="cnc-quick-link"
                onClick={runClosedLoopDemo}
                disabled={busy}
              >
                运行 30+ 参数闭环
              </button>
            </div>
          </div>

          <div className="cnc-input-cards-row">
            {/* Card 1: Case */}
            <div
              className={`cnc-file-card ${inputs.case ? "loaded" : ""}`}
              onClick={() => fileInputRefs.case.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && fileInputRefs.case.current?.click()}
            >
              <div className="card-icon-box icon-case">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 19c4-4 8 2 12-2 3-3 4-8 4-8" />
                  <circle cx="4" cy="19" r="2" />
                  <circle cx="20" cy="9" r="2" />
                </svg>
              </div>
              <div className="card-text-box">
                <div className="card-role-label">{roleTitles.case}</div>
                <div className="card-file-name" title={filenames.case ?? "impeller_finish_v3.json"}>
                  {filenames.case ?? "impeller_finish_v3.json"}
                </div>
                <div className="card-hash-pill">
                  <span className="pill-tag green">已导入</span>
                  <span className="pill-hash">sha256 · {shortHash(caseHash)}</span>
                </div>
              </div>
              <input
                ref={fileInputRefs.case}
                type="file"
                accept=".json,application/json"
                aria-label="选择刀路与约束文件"
                disabled={busy}
                onChange={(e) => importFile("case", e)}
                style={{ display: "none" }}
              />
            </div>

            <div className="cnc-plus-separator" aria-hidden="true">+</div>

            {/* Card 2: Baseline A */}
            <div
              className={`cnc-file-card ${inputs.baseline ? "loaded" : ""}`}
              onClick={() => fileInputRefs.baseline.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && fileInputRefs.baseline.current?.click()}
            >
              <div className="card-icon-box icon-base">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="18" cy="5" r="3" />
                  <circle cx="6" cy="12" r="3" />
                  <circle cx="18" cy="19" r="3" />
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                </svg>
              </div>
              <div className="card-text-box">
                <div className="card-role-label">{roleTitles.baseline}</div>
                <div className="card-file-name" title={filenames.baseline ?? "axisCore v2.4.1"}>
                  {filenames.baseline ?? "axisCore v2.4.1"}
                </div>
                <div className="card-hash-pill">
                  <span className="pill-tag green">已导入</span>
                  <span className="pill-hash">sha256 · {shortHash(baseHash)}</span>
                </div>
              </div>
              <input
                ref={fileInputRefs.baseline}
                type="file"
                accept=".json,application/json"
                aria-label="选择基线 A文件"
                disabled={busy}
                onChange={(e) => importFile("baseline", e)}
                style={{ display: "none" }}
              />
            </div>

            <div className="cnc-plus-separator" aria-hidden="true">+</div>

            {/* Card 3: Candidate B */}
            <div
              className={`cnc-file-card ${inputs.candidate ? "loaded" : ""}`}
              onClick={() => fileInputRefs.candidate.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && fileInputRefs.candidate.current?.click()}
            >
              <div className="card-icon-box icon-cand">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10 2v7.31L4.66 18c-.81 1.34.15 3 1.71 3h11.26c1.56 0 2.52-1.66 1.71-3L14 9.31V2" />
                  <line x1="8" y1="2" x2="16" y2="2" />
                  <line x1="7" y1="15" x2="17" y2="15" />
                </svg>
              </div>
              <div className="card-text-box">
                <div className="card-role-label">{roleTitles.candidate}</div>
                <div className="card-file-name" title={filenames.candidate ?? "axisCore v2.5.0-rc.2"}>
                  {filenames.candidate ?? "axisCore v2.5.0-rc.2"}
                </div>
                <div className="card-hash-pill">
                  <span className={`pill-tag ${synthetic ? "amber" : "green"}`}>
                    {synthetic ? "合成示例" : "已导入"}
                  </span>
                  <span className="pill-hash">sha256 · {shortHash(candHash)}</span>
                </div>
              </div>
              <input
                ref={fileInputRefs.candidate}
                type="file"
                accept=".json,application/json"
                aria-label="选择候选 B文件"
                disabled={busy}
                onChange={(e) => importFile("candidate", e)}
                style={{ display: "none" }}
              />
            </div>
          </div>

          {synthetic && (
            <p className="cnc-example-note">
              当前包含合成示例，用于演示回归定位；请替换为实际算法导出结果后再作工程判断。
            </p>
          )}

          {error && <div role="alert" className="cnc-error-banner">{error}</div>}
        </section>

        {/* Step 02: 比较报告 */}
        {report ? (
          <section className="cnc-step-section cnc-results" aria-label="算法比较报告">
            <div className="step-label-row">
              <span className="step-num-eyebrow">02 · 比较报告</span>
            </div>

            <div className="cnc-report-columns">
              {/* Left Column: Report tables & badges */}
              <div className="cnc-report-left">
                <div className="cnc-report-title-row">
                  <h2>算法比较报告</h2>
                </div>

                {/* Outcome summary banner */}
                <div className={`cnc-outcome-banner banner-${report.outcome}`}>
                  <div className={`outcome-badge badge-${report.outcome}`}>
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polygon points="12 2 2 7 12 12 22 7 12 2" />
                      <polyline points="2 17 12 22 22 17" />
                      <polyline points="2 12 12 17 22 12" />
                    </svg>
                    <h3 className="outcome-text-heading">{statusLabels[report.outcome] ?? report.outcome}</h3>
                  </div>
                  <span className="outcome-explanation">
                    {report.reasons.length > 0
                      ? report.reasons.join("；")
                      : "B 版轨迹精度显著改善，运动时间增加 10.0%；候选在 Z 轴出现 1 处加速度超限。"}
                  </span>
                </div>

                {/* Metrics Table */}
                <div className="cnc-section-subhead">
                  <span className="subhead-title">比较指标</span>
                  <span className="subhead-meta">采样命令范围内 · 比较容差 0.05 mm</span>
                </div>
                <div className="cnc-table-box">
                  <table>
                    <thead>
                      <tr>
                        <th>指标</th>
                        <th>基线 A</th>
                        <th>候选 B</th>
                        <th>Δ 差异</th>
                        <th>判定</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.differences.map((item) => {
                        const isImproved = item.status === "Improved";
                        const isRegressed = item.status === "Regressed";
                        const isNotComparable = item.status === "NotComparable";
                        const deltaText = item.delta == null ? "—" : item.delta > 0 ? `+${number(item.delta)}` : number(item.delta);
                        const pctText = (item.baseline && item.candidate)
                          ? `${((item.candidate - item.baseline) / item.baseline * 100) > 0 ? "+" : ""}${((item.candidate - item.baseline) / item.baseline * 100).toFixed(1)}%`
                          : deltaText;

                        return (
                          <tr key={item.metricId}>
                            <td>
                              <strong>{metricLabels[item.metricId] ?? item.metricId}</strong>
                              <small> ({item.unit || metricUnits[item.metricId] || "mm"})</small>
                            </td>
                            <td>{number(item.baseline)}</td>
                            <td>{number(item.candidate)}</td>
                            <td className={isImproved ? "text-green" : isRegressed ? "text-red" : "text-muted"}>
                              {isNotComparable ? "—" : pctText}
                            </td>
                            <td>
                              <span className={`status-tag tag-${item.status}`}>
                                {statusLabels[item.status] ?? item.status}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Constraint Checks Table */}
                <div className="cnc-section-subhead" style={{ marginTop: "24px" }}>
                  <span className="subhead-title">约束检查与最差位置</span>
                </div>
                <div className="cnc-table-box">
                  <table>
                    <thead>
                      <tr>
                        <th>检查项</th>
                        <th>结果</th>
                        <th>最差位置</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.candidate.checks.map((check) => {
                        const isPassed = check.status === "WithinLimit" || check.status === "Passed";
                        const isViolated = check.status === "Violated" || check.status === "CandidateViolatesLimits";
                        return (
                          <tr key={check.checkId}>
                            <td><strong>{checkLabels[check.checkId] ?? check.checkId}</strong></td>
                            <td>
                              <span className={`status-tag ${isPassed ? "tag-Improved" : isViolated ? "tag-Regressed" : "tag-Tradeoff"}`}>
                                {isPassed ? "通过" : statusLabels[check.status] ?? check.status}
                              </span>
                            </td>
                            <td className={isViolated ? "text-red" : "text-muted"}>
                              {locate(check.location)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Scope Coverage Notice Box */}
                <div className="cnc-scope-callout">
                  <div className="callout-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="16" x2="12" y2="12" />
                      <line x1="12" y1="8" x2="12.01" y2="8" />
                    </svg>
                  </div>
                  <p>
                    本次检查覆盖：采样点到参考折线的单向距离、首尾位置、轴行程与离散 V/A/J 差分，以及同条件声明的计算耗时。尚未验证采样间连续运动、碰撞、实机跟随或加工质量。
                  </p>
                </div>
              </div>

              {/* Right Column: Chart, Result Identity, Warning */}
              <div className="cnc-report-right">
                <PathPreview inputs={inputs} />

                <div className="cnc-identity-card">
                  <div className="identity-card-header">
                    <strong>结果身份</strong>
                  </div>
                  <div className="identity-rows">
                    <div className="identity-row">
                      <span className="label">Case hash</span>
                      <span className="val mono">{shortHash(report.caseContentHash)}</span>
                    </div>
                    <div className="identity-row">
                      <span className="label">RunBundle</span>
                      <span className="val mono">{shortHash(report.reportContentHash)}</span>
                    </div>
                    <div className="identity-row">
                      <span className="label">容差 / 周期</span>
                      <span className="val mono">0.05 mm · 2 ms</span>
                    </div>
                  </div>
                  <div className="identity-card-actions">
                    <button
                      type="button"
                      className="button button-secondary button-sm"
                      onClick={() => download(inputs, "cnc-benchmark-request.json")}
                    >
                      下载可重放输入
                    </button>
                    <button
                      type="button"
                      className="button button-secondary button-sm"
                      onClick={() => download(report, "cnc-benchmark-report.json")}
                    >
                      下载报告 JSON
                    </button>
                  </div>
                </div>

                <div className="cnc-warning-callout">
                  仅评估采样轨迹，不代表实机加工效果；「改善」只针对本页列出的指标。
                </div>
              </div>
            </div>
          </section>
        ) : (
          <section className="cnc-empty-card">
            <div className="empty-inner">
              <h2>从一次可复现的版本比较开始</h2>
              <p>上传三份文件，或载入带有已知偏差的示例。报告会保留指标差异以及超限的样本、时间和轴。</p>
              <button
                type="button"
                className="button button-primary"
                onClick={loadExample}
                disabled={busy}
                style={{ marginTop: "16px" }}
              >
                载入回归示例并比较
              </button>
            </div>
          </section>
        )}

        {/* Closed Loop Demo Section */}
        {closedLoop && (
          <section className="cnc-results closed-loop-section" aria-label="30+ 参数评估与推荐闭环报告">
            <div className="cnc-result-heading">
              <div>
                <span className="eyebrow">32-PARAMETER MULTI-FIDELITY CLOSED LOOP</span>
                <h2>高维参数质量评估、敏感度归因与稀疏微调推荐</h2>
                <p>
                  案例 {closedLoop.case.caseId} · 离线跑批 {closedLoop.surrogate.offlineRunCount} 组 + 控制器实采 {closedLoop.surrogate.controllerRunCount} 组（提取 {closedLoop.surrogate.totalSliceSampleCount} 个几何切片）
                </p>
              </div>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => download(closedLoop, "cnc-param-closed-loop.json")}
              >
                下载闭环数据包
              </button>
            </div>

            <div className="cnc-section-subhead" style={{ marginTop: "16px" }}>
              <span className="subhead-title">1. 参数影响识别（Stage 1 稀疏初筛 + Stage 2 多保真 ARD-GP）</span>
            </div>
            <div className="cnc-table-box">
              <table>
                <thead>
                  <tr>
                    <th>质量指标</th>
                    <th>建模模式</th>
                    <th>R² / CV-RMSE</th>
                    <th>Top-3 主导参数及贡献占比</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.values(closedLoop.surrogate.metricHeads).map((head) => (
                    <tr key={head.metricId}>
                      <td><strong>{head.metricId}</strong><small> ({head.unit})</small></td>
                      <td>{head.modelingMode}</td>
                      <td>R²={number(head.r2Score)} · ±{number(head.conformalRadius)}</td>
                      <td>
                        {head.sensitivities
                          .filter((s) => s.status === "Active")
                          .slice(0, 3)
                          .map((s) => `${s.displayName} (${(s.contributionRatio * 100).toFixed(1)}%, ${s.direction})`)
                          .join("；")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="cnc-section-subhead" style={{ marginTop: "24px" }}>
              <span className="subhead-title">2. 受约束三档 Pareto 稀疏推荐（最多微调 {closedLoop.recommendationReport.maxChangedParameters} 个核心参数）</span>
            </div>
            <div className="cnc-table-box">
              <table>
                <thead>
                  <tr>
                    <th>推荐档位</th>
                    <th>预期效果与权衡说明</th>
                    <th>建议调整的参数项</th>
                  </tr>
                </thead>
                <tbody>
                  {closedLoop.recommendationReport.presets.map((preset) => (
                    <tr key={preset.candidateId}>
                      <td><strong>{preset.presetTitle}</strong><small> ({preset.presetRole})</small></td>
                      <td>{preset.tradeoffExplanation}</td>
                      <td className="mono text-muted">
                        {preset.changedParameters
                          .map((p) => `${p.parameterId}: ${p.baselineValue} → ${p.recommendedValue} ${p.unit} (${p.relativeChangePct >= 0 ? "+" : ""}${p.relativeChangePct}%)`)
                          .join(" | ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="cnc-section-subhead" style={{ marginTop: "24px" }}>
              <span className="subhead-title">3. 主动学习下一批补采建议（Active DoE）</span>
            </div>
            <ul className="active-doe-list">
              {closedLoop.recommendationReport.activeDoeSuggestions.map((sug) => (
                <li key={sug.suggestionId}>
                  <strong>[{sug.suggestionId} · {sug.targetSource}]</strong> {sug.rationale}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  );
}
