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
interface MetricHead { metricId: string; unit: string; modelingMode: string; r2Score: number; looR2Score?: number | null; residualEnabled?: boolean; cvRmse: number; conformalRadius: number; sensitivities: SensitivityItem[] }
interface ParameterDelta { parameterId: string; displayName: string; group: string; unit: string; baselineValue: number; recommendedValue: number; relativeChangePct: number }
interface PresetCandidate { candidateId: string; presetRole: string; presetTitle: string; changedParameterCount: number; changedParameters: ParameterDelta[]; tradeoffExplanation: string }
interface ActiveDoeItem { suggestionId: string; targetSource: string; changedParameterIds: string[]; acquisitionScore: number; rationale: string }
interface ClosedLoopDemo {
  case: { caseId: string };
  sampleQualityReport: { outcome: string; scope: string; analysis: Analysis; servoMetrics?: Record<string, Metric>; geometrySlices: Array<{ sliceId: string; primitiveKind: string; startSampleIndex: number; endSampleIndex: number; metrics: Record<string, number | null> }> };
  surrogate: { offlineRunCount: number; controllerRunCount: number; totalSliceSampleCount: number; globalActiveParameterIds: string[]; metricHeads: Record<string, MetricHead> };
  recommendationReport: { maxChangedParameters: number; evaluatedCandidateCount: number; feasibleCandidateCount: number; paretoCandidateCount: number; presets: PresetCandidate[]; activeDoeSuggestions: ActiveDoeItem[]; noFeasibleReason?: string | null };
}

const roleTitles: Record<Role, string> = {
  case: "01 · 刀路参考与约束门禁",
  baseline: "02 · 基线版本 A",
  candidate: "03 · 候选版本 B",
};

const roleHints: Record<Role, string> = {
  case: "上传刀路参考折线与速度/加速度/Jerk 门禁 JSON",
  baseline: "上传当前生产或上一版插补规划导出的采样轨迹",
  candidate: "上传待验收的新版插补规划导出的采样轨迹",
};

const labels: Record<Role, string> = { case: "刀路与约束", baseline: "基线 A", candidate: "候选 B" };

const metricLabels: Record<string, string> = {
  sampledPathDeviationMaxMm: "最大路径偏差",
  sampledPathDeviationMeanMm: "平均路径偏差",
  sampledPathDeviationRmsMm: "路径偏差有效值 RMS",
  sampledPathDeviationP95Mm: "P95 路径偏差",
  sampledPathDeviationP99Mm: "P99 路径偏差",
  endpointErrorMaxMm: "首尾端点最大误差",
  durationSeconds: "运动时间",
  computationSeconds: "单周期计算耗时",
  discreteVelocityMax: "最大离散轴速度",
  discreteAccelerationMax: "最大离散轴加速度",
  discreteJerkMax: "最大离散 Jerk",
  discreteJerkRms: "离散冲击 Jerk RMS",
  sampledJerkMaxMmPerSec3: "最大 Jerk",
  smoothedJerkRmsMmS3: "平滑冲击 Jerk RMS",
  cornerSpeedMinMmS: "最低拐角过弯速度",
  feedUtilization: "编程进给利用率",
  feedUtilizationRatio: "编程进给利用率",
  actualPathDeviationMaxMm: "实测最大轮廓误差",
  actualContourErrorMaxMm: "最大伺服轮廓误差",
  followingErrorMaxMm: "最大伺服跟随误差",
  trackingErrorRmsMm: "伺服跟随误差 RMS",
  tangentialLagMaxMm: "最大切向跟随滞后",
  normalServoErrorMaxMm: "双轴法向伺服失配峰值",
  quadrantGlitchExcessMm: "过象限摩擦突跳超量",
  quadrantPeakGlitchMm: "过象限摩擦尖峰",
  resonanceBandRmsMm: "谐振频带残差 RMS",
  highFreqVibrationEnergyRatio: "高频振动能量占比",
  commandBandLimitedEnergyRatio: "规划器高频激励占比",
};

const metricUnits: Record<string, string> = {
  sampledPathDeviationMaxMm: "mm",
  sampledPathDeviationMeanMm: "mm",
  sampledPathDeviationRmsMm: "mm",
  sampledPathDeviationP95Mm: "mm",
  sampledPathDeviationP99Mm: "mm",
  endpointErrorMaxMm: "mm",
  durationSeconds: "s",
  computationSeconds: "s",
  sampledJerkMaxMmPerSec3: "mm/s³",
  discreteJerkRms: "mm/s³",
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
  Passed: "通过",
  Failed: "未通过",
  Violated: "超限",
  InsufficientSamples: "样本不足",
};

const checkLabels: Record<string, string> = {
  "sampled-path-deviation": "路径偏差限制",
  "endpoints": "首尾端点误差限制",
  "sampled-velocity": "速度限制",
  "sampled-acceleration": "加速度限制",
  "sampled-jerk": "Jerk 限制",
  "axis-stroke": "轴行程范围",
};

const axisCheckLabels: Record<string, string> = {
  "position-range": "轴行程范围",
  "discrete-velocity": "轴采样速度限制",
  "discrete-acceleration": "轴采样加速度限制",
  "discrete-jerk": "轴采样 Jerk 限制",
};

const modelingModeLabels: Record<string, string> = {
  "greybox-physics-gp": "灰盒物理先验 + 残差 GP",
  "multi-fidelity-residual-fusion": "多保真残差融合",
  "single-fidelity-surrogate": "单保真代理模型",
};

const presetRoleLabels: Record<string, string> = {
  EfficiencyOptimal: "效率最优",
  PrecisionOptimal: "精度最优",
  BalancedKneePoint: "均衡拐点",
  efficiency: "效率最优",
  accuracy: "精度最优",
  balanced: "均衡拐点",
};

const directionLabels: Record<string, string> = {
  positive: "正相关",
  negative: "负相关",
  nonlinear: "非线性",
  neutral: "弱相关",
};

const targetSourceLabels: Record<string, string> = {
  "controller-trace": "机床试切采集",
  "algorithm-export": "离线插补预筛",
  "synthetic-example": "合成示例",
};

const differenceReasonLabels: Record<string, string> = {
  "Both exports must include this measurement": "基线与候选均需包含该项测量值",
  "Both computation times must be positive": "两份计算耗时均须为正数",
  "Computation environments do not match": "两份计算耗时运行环境声明不一致",
  "At least one metric has insufficient samples": "至少一份轨迹采样点数不足以计算差分",
};

function formatCheckLabel(checkId: string): string {
  if (checkLabels[checkId]) return checkLabels[checkId]!;
  const axisMatch = /^([A-Za-z]+)\.(.+)$/.exec(checkId);
  if (axisMatch) {
    const [, axis, kind] = axisMatch;
    if (axis && kind && axisCheckLabels[kind]) {
      return `${axis} ${axisCheckLabels[kind]}`;
    }
  }
  return checkId;
}

const caveatReasonMap: Record<string, string> = {
  "Discrete V/A/J differences do not certify continuous velocity, acceleration or jerk":
    "离散采样差分仅校验采样时刻的 V/A/J，不等同于采样点间连续运动学证明",
  "Computation timing is producer-reported; a single observation does not establish statistical significance":
    "计算耗时由导出端自行上报，单次观测不构成统计显著性结论",
  "Synthetic example data: this report is not evidence about a production algorithm":
    "当前使用内置合成示例数据，仅用于回归定位演示，不作为生产算法验收证据",
};

const primaryReasonMap: Record<string, string> = {
  "Candidate violates one or more sampled-command limits":
    "候选版本违反了一项或多项采样运动学/轮廓硬约束限制，请先根据下方超限样本位置修复。",
  "A/B quality comparison requires a valid baseline and enough samples for every requested check":
    "A/B 质量对比要求基线版本满足约束限制，且采样点数足以完成全部运动学差分检查。",
  "Synthetic examples and algorithm exports cannot establish one A/B result":
    "合成示例数据不能与真实算法导出轨迹混用进行 A/B 验收判定。",
  "Lower duration, sampled path deviation and comparable reported computation time are preferred; no weighted score is used":
    "评估原则：运动时间更短、路径偏差更小、同环境计算耗时更低者优先（不使用主观加权总分）。",
};

function formatReportReasons(reasons: string[]): { primary: string[]; caveats: string[] } {
  const primary: string[] = [];
  const caveats: string[] = [];
  for (const raw of reasons) {
    const trimmed = raw.trim();
    if (!trimmed) continue;
    if (caveatReasonMap[trimmed]) {
      caveats.push(caveatReasonMap[trimmed]!);
      continue;
    }
    if (primaryReasonMap[trimmed]) {
      primary.push(primaryReasonMap[trimmed]!);
      continue;
    }
    const tolPrefix = "Case-declared tolerances also compare ";
    if (trimmed.startsWith(tolPrefix)) {
      const rest = trimmed.slice(tolPrefix.length).replace(/;\s*lower is preferred\.?$/i, "");
      const localizedMetrics = rest
        .split(",")
        .map((m) => m.trim())
        .filter(Boolean)
        .map((m) => metricLabels[m] ?? m)
        .join("、");
      primary.push(`案例声明容差同时对比了 ${localizedMetrics}（数值更小者优先）。`);
      continue;
    }
    primary.push(trimmed);
  }
  return { primary, caveats };
}

function localizeClosedLoopCopy(text: string): string {
  return text
    .replace(/actualPathDeviationMaxMm=/g, "实测最大轮廓误差=")
    .replace(/sampledPathDeviationMaxMm=/g, "最大路径偏差=")
    .replace(/\bcontroller-trace\b/g, "机床试切采集")
    .replace(/\balgorithm-export\b/g, "离线插补预筛")
    .replace(/\bCEI=/g, "期望改进分=");
}

async function requestJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    `/api/v1/benchmarks/cnc/${path}`,
    body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
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

function kpiNumber(value: number | null | undefined, unit: string): string {
  if (value == null) return "—";
  const formatted = value === 0 ? "0" : Number(value.toPrecision(4)).toString();
  return `${formatted} ${unit}`.trim();
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
  return raw
    .filter((_, index) => index % stride === 0 || index === raw.length - 1)
    .map((item: unknown) => {
      if (!reference && item && typeof item === "object") return (item as { positionMm?: unknown }).positionMm;
      return item;
    })
    .filter((item): item is [number, number, number] => Array.isArray(item) && item.length === 3 && item.every((v) => typeof v === "number" && Number.isFinite(v)));
}

function PathPreview({ inputs }: { inputs: Inputs }) {
  const paths = [previewPoints(inputs.case, true), previewPoints(inputs.baseline), previewPoints(inputs.candidate)];
  const hasPoints = paths.some((points) => points.length > 0);

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
        <strong>XY 采样轨迹叠加投影</strong>
        <span className="cnc-preview-sub">抽样上限 1,500 点</span>
      </div>
      <div className="cnc-chart-body">
        <XYChart series={series} ariaLabel="参考路径与 A/B 指令的 XY 投影" height={236} xLabel="X (mm)" yLabel="Y (mm)" legend={false} />
      </div>
      <div className="cnc-preview-legend">
        <span className="legend-ref"><i className="legend-line line-gray" /> 参考路径</span>
        <span className="legend-base"><i className="legend-line line-blue" /> 基线 A</span>
        <span className="legend-cand"><i className="legend-line line-green" /> 候选 B</span>
      </div>
      <div className="cnc-preview-caption">悬停图表可读取任意采样点处的 X / Y 精确坐标（mm）</div>
    </div>
  );
}

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

export function CncBenchmarkWorkbench({
  onOpenGuide,
  onOpenParamTuning,
}: {
  onOpenGuide?: () => void;
  onOpenParamTuning?: () => void;
}) {
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
    setInputs((previous) => ({ ...previous, [role]: null }));
    setFilenames((previous) => ({ ...previous, [role]: file.name }));
    try {
      if (file.size > 16 * 1024 * 1024) throw new Error("单个文件不能超过 16 MiB。");
      const parsed = object(JSON.parse((await file.text()).replace(/^\uFEFF/, "")));
      if (current === revision.current) setInputs((previous) => ({ ...previous, [role]: parsed }));
    } catch (reason) {
      if (current === revision.current) setError(`${labels[role]}：${reason instanceof Error ? reason.message : "无法读取文件"}`);
    } finally {
      if (current === revision.current) setBusy(false);
    }
  }

  async function loadExample() {
    const current = ++revision.current;
    setBusy(true); setReport(null); setError(null);
    try {
      const payload = await requestJson<Record<Role, JsonObject>>("example");
      if (current === revision.current) {
        setInputs(payload);
        setFilenames({
          case: `${String(payload.case?.caseId ?? "case")}.json`,
          baseline: `${String(payload.baseline?.algorithmId ?? "baseline")} (${String(payload.baseline?.algorithmVersion ?? "A")})`,
          candidate: `${String(payload.candidate?.algorithmId ?? "candidate")} (${String(payload.candidate?.algorithmVersion ?? "B")})`,
        });
      }
    } catch (reason) {
      if (current === revision.current) setError(reason instanceof Error ? reason.message : "示例加载失败");
    } finally {
      if (current === revision.current) setBusy(false);
    }
  }

  async function loadExampleAndCompare() {
    const current = ++revision.current;
    setBusy(true); setReport(null); setError(null);
    try {
      const payload = await requestJson<Record<Role, JsonObject>>("example");
      if (current !== revision.current) return;
      setInputs(payload);
      setFilenames({
        case: `${String(payload.case?.caseId ?? "case")}.json`,
        baseline: `${String(payload.baseline?.algorithmId ?? "baseline")} (${String(payload.baseline?.algorithmVersion ?? "A")})`,
        candidate: `${String(payload.candidate?.algorithmId ?? "candidate")} (${String(payload.candidate?.algorithmVersion ?? "B")})`,
      });
      const next = await requestJson<Report>("compare", payload);
      if (current === revision.current) setReport(next);
    } catch (reason) {
      if (current === revision.current) setError(reason instanceof Error ? reason.message : "示例对比运行失败");
    } finally {
      if (current === revision.current) setBusy(false);
    }
  }

  async function compare() {
    if (!ready) return;
    const current = ++revision.current;
    setBusy(true); setReport(null); setError(null);
    try {
      const next = await requestJson<Report>("compare", inputs);
      if (current === revision.current) setReport(next);
    } catch (reason) {
      if (current === revision.current) setError(reason instanceof Error ? reason.message : "比较失败");
    } finally {
      if (current === revision.current) setBusy(false);
    }
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

  const diffMap = new Map((report?.differences ?? []).map((d) => [d.metricId, d]));
  const maxDevDiff = diffMap.get("sampledPathDeviationMaxMm");
  const durDiff = diffMap.get("durationSeconds");
  const totalChecks = report?.candidate.checks.length ?? 0;
  const passedChecks = (report?.candidate.checks ?? []).filter((c) => c.status === "WithinLimit" || c.status === "Passed").length;
  const violatedChecks = totalChecks - passedChecks;
  const formattedReasons = formatReportReasons(report?.reasons ?? []);

  const renderCardMeta = (role: Role) => {
    const data = inputs[role];
    if (!data) {
      return (
        <>
          <div className="card-file-name unloaded">{filenames[role] ? `${filenames[role]}（读取未完成）` : "点击导入 JSON 文件"}</div>
          <div className="card-hash-pill">
            <span className="pill-tag neutral">待导入</span>
            <span className="pill-hash">{roleHints[role]}</span>
          </div>
        </>
      );
    }
    const isSynth = data.sourceKind === "synthetic-example";
    const hashSource = role === "case"
      ? String(data.caseContentHash ?? data.caseId ?? "已校验")
      : String(data.reportContentHash ?? `${data.algorithmId ?? role}@${data.algorithmVersion ?? "1"}`);
    const displayTitle = filenames[role] ?? String(data.caseId ?? data.algorithmId ?? "已导入 JSON");

    return (
      <>
        <div className="card-file-name" title={displayTitle}>{displayTitle}</div>
        <div className="card-hash-pill">
          <span className={`pill-tag ${isSynth ? "amber" : "green"}`}>
            {isSynth ? "合成示例" : "已就绪"}
          </span>
          <span className="pill-hash">标识 · {shortHash(hashSource)}</span>
        </div>
      </>
    );
  };

  return (
    <main className="cnc-benchmark-page" aria-label="CNC 算法对比工作台">
      <header className="page-header">
        <div className="page-header-info">
          <h1 aria-label="比较两版 CNC 算法">CNC 算法 A/B 对比</h1>
          <p className="page-header-subtitle">
            同一刀路案例 · 两版插补规划轨迹 · 采样误差与运动学硬约束门禁定位（单位 mm）
          </p>
        </div>
        <div className="page-header-actions">
          {onOpenParamTuning && (
            <button
              type="button"
              className="button button-secondary"
              onClick={onOpenParamTuning}
            >
              前往现场调参与快诊 →
            </button>
          )}
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
            {busy ? "比较中…" : "比较 A / B"}
          </button>
        </div>
      </header>

      <div className="cnc-container">
        {/* Step 01: 导入输入 */}
        <section className="cnc-step-section">
          <div className="step-label-row">
            <span className="step-num-eyebrow">步骤 01 · 导入对比输入（三选齐后激活对比）</span>
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
            <div
              className={`cnc-file-card ${inputs.case ? "loaded" : ""}`}
              onClick={() => fileInputRefs.case.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && fileInputRefs.case.current?.click()}
            >
              <div className="card-icon-box icon-case">
                <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 19c4-4 8 2 12-2 3-3 4-8 4-8" />
                  <circle cx="4" cy="19" r="2" />
                  <circle cx="20" cy="9" r="2" />
                </svg>
              </div>
              <div className="card-text-box">
                <div className="card-role-label">{roleTitles.case}</div>
                {renderCardMeta("case")}
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

            <div
              className={`cnc-file-card ${inputs.baseline ? "loaded" : ""}`}
              onClick={() => fileInputRefs.baseline.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && fileInputRefs.baseline.current?.click()}
            >
              <div className="card-icon-box icon-base">
                <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="18" cy="5" r="3" />
                  <circle cx="6" cy="12" r="3" />
                  <circle cx="18" cy="19" r="3" />
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                </svg>
              </div>
              <div className="card-text-box">
                <div className="card-role-label">{roleTitles.baseline}</div>
                {renderCardMeta("baseline")}
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

            <div
              className={`cnc-file-card ${inputs.candidate ? "loaded" : ""}`}
              onClick={() => fileInputRefs.candidate.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && fileInputRefs.candidate.current?.click()}
            >
              <div className="card-icon-box icon-cand">
                <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10 2v7.31L4.66 18c-.81 1.34.15 3 1.71 3h11.26c1.56 0 2.52-1.66 1.71-3L14 9.31V2" />
                  <line x1="8" y1="2" x2="16" y2="2" />
                  <line x1="7" y1="15" x2="17" y2="15" />
                </svg>
              </div>
              <div className="card-text-box">
                <div className="card-role-label">{roleTitles.candidate}</div>
                {renderCardMeta("candidate")}
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
              <span className="step-num-eyebrow">步骤 02 · 版本验收结论与超限样本定位</span>
            </div>

            {/* KPI Strip */}
            <div className="cnc-kpi-strip">
              <article className="cnc-kpi-card">
                <span className="kpi-label">候选最大路径偏差</span>
                <strong className="kpi-value">{kpiNumber(maxDevDiff?.candidate, maxDevDiff?.unit ?? "mm")}</strong>
                <span className="kpi-sub">
                  基线 A：{kpiNumber(maxDevDiff?.baseline, maxDevDiff?.unit ?? "mm")}
                </span>
              </article>
              <article className="cnc-kpi-card">
                <span className="kpi-label">候选运动总时长</span>
                <strong className="kpi-value">{kpiNumber(durDiff?.candidate, durDiff?.unit ?? "s")}</strong>
                <span className="kpi-sub">
                  基线 A：{kpiNumber(durDiff?.baseline, durDiff?.unit ?? "s")}
                </span>
              </article>
              <article className="cnc-kpi-card">
                <span className="kpi-label">运动学硬约束门禁</span>
                <strong className={`kpi-value ${violatedChecks > 0 ? "text-red" : "text-green"}`}>
                  {passedChecks} / {totalChecks} 通过
                </strong>
                <span className="kpi-sub">
                  {violatedChecks > 0 ? `${violatedChecks} 项超限需定位修复` : "全部满足采样限制"}
                </span>
              </article>
              <article className="cnc-kpi-card">
                <span className="kpi-label">样本规模与算法版本</span>
                <strong className="kpi-value">{report.candidate.sampleCount} 采样点</strong>
                <span className="kpi-sub">
                  {report.baseline.algorithmVersion} → {report.candidate.algorithmVersion}
                </span>
              </article>
            </div>

            <div className="cnc-report-columns">
              <div className="cnc-report-left">
                <div className="cnc-report-title-row">
                  <h2>算法比较报告</h2>
                </div>

                <div className={`cnc-outcome-banner banner-${report.outcome}`}>
                  <div className={`outcome-badge badge-${report.outcome}`}>
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polygon points="12 2 2 7 12 12 22 7 12 2" />
                      <polyline points="2 17 12 22 22 17" />
                      <polyline points="2 12 12 17 22 12" />
                    </svg>
                    <h3 className="outcome-text-heading">{statusLabels[report.outcome] ?? report.outcome}</h3>
                  </div>
                  <div className="outcome-body">
                    <span className="outcome-explanation">
                      {formattedReasons.primary.length > 0
                        ? formattedReasons.primary.join(" ")
                        : "已完成采样轨迹对比与硬约束门禁核验，请结合下方差异表与最差样本位置审阅。"}
                    </span>
                    {formattedReasons.caveats.length > 0 && (
                      <ul className="outcome-caveats" aria-label="评估边界说明">
                        {formattedReasons.caveats.map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>

                <div className="cnc-section-subhead">
                  <span className="subhead-title">比较指标明细</span>
                  <span className="subhead-meta">采样命令范围 · 绑定同源案例哈希</span>
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
                        const reasonHint = item.reason ? (differenceReasonLabels[item.reason] ?? item.reason) : undefined;

                        return (
                          <tr key={item.metricId}>
                            <td>
                              <strong>{metricLabels[item.metricId] ?? item.metricId}</strong>
                              <small> ({item.unit || metricUnits[item.metricId] || "mm"})</small>
                            </td>
                            <td className="mono">{number(item.baseline)}</td>
                            <td className="mono">{number(item.candidate)}</td>
                            <td className={isImproved ? "text-green" : isRegressed ? "text-red" : "text-muted"}>
                              {isNotComparable ? "—" : pctText}
                            </td>
                            <td>
                              <span className={`status-tag tag-${item.status}`} title={reasonHint}>
                                {statusLabels[item.status] ?? item.status}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="cnc-section-subhead" style={{ marginTop: "24px" }}>
                  <span className="subhead-title">约束检查与最差位置</span>
                  <span className="subhead-meta">精确到采样点序号、时刻与参考段</span>
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
                            <td><strong>{formatCheckLabel(check.checkId)}</strong></td>
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

              <div className="cnc-report-right">
                <PathPreview inputs={inputs} />

                <div className="cnc-identity-card">
                  <div className="identity-card-header">
                    <strong>可审计结果身份</strong>
                  </div>
                  <div className="identity-rows">
                    <div className="identity-row">
                      <span className="label">案例 ID</span>
                      <span className="val mono">{report.caseId}</span>
                    </div>
                    <div className="identity-row">
                      <span className="label">案例哈希</span>
                      <span className="val mono">{shortHash(report.caseContentHash)}</span>
                    </div>
                    <div className="identity-row">
                      <span className="label">报告哈希</span>
                      <span className="val mono">{shortHash(report.reportContentHash)}</span>
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
                  仅评估采样轨迹，不代表实机加工效果；若需结合西门子 840D / 倍福 TwinCAT 实测伺服跟踪做参数微调，请打开左侧「现场调参与快诊」。
                </div>
              </div>
            </div>
          </section>
        ) : (
          <section className="cnc-empty-card">
            <div className="empty-inner">
              <span className="empty-badge">可复现 A/B 算法基准核验</span>
              <h2>从一次可复现的算法版本比较开始</h2>
              <p>
                上传「刀路与约束 + 基线 A + 候选 B」三份 JSON 文件，或一键载入内置回归示例。报告将独立校验轨迹偏差与速度/加速度/Jerk 限制，并精确定位超限发生的样本序号、时刻与轴。
              </p>
              <div className="empty-actions">
                <button
                  type="button"
                  className="button button-primary"
                  onClick={loadExampleAndCompare}
                  disabled={busy}
                >
                  {busy ? "正在载入并对比…" : "一键载入示例并立即对比"}
                </button>
                {onOpenParamTuning && (
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={onOpenParamTuning}
                  >
                    体验单刀快诊与多系统调参 →
                  </button>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Closed Loop Demo Section */}
        {closedLoop && (
          <section className="cnc-results closed-loop-section" aria-label="30+ 参数评估与推荐闭环报告">
            <div className="cnc-result-heading">
              <div>
                <span className="eyebrow">32 维多保真灰盒调参闭环</span>
                <h2>高维参数质量评估、敏感度归因与稀疏微调推荐</h2>
                <p className="text-muted" style={{ margin: 0, fontSize: "13px" }}>
                  案例 {closedLoop.case.caseId} · 离线跑批 {closedLoop.surrogate.offlineRunCount} 组 + 实采切片 {closedLoop.surrogate.controllerRunCount} 组（共 {closedLoop.surrogate.totalSliceSampleCount} 个几何切片）
                </p>
              </div>
              <div style={{ display: "flex", gap: "8px" }}>
                {onOpenParamTuning && (
                  <button
                    className="button button-primary"
                    type="button"
                    onClick={onOpenParamTuning}
                  >
                    在交互式调参台中打开 →
                  </button>
                )}
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => download(closedLoop, "cnc-param-closed-loop.json")}
                >
                  下载闭环数据包
                </button>
              </div>
            </div>

            <div className="cnc-section-subhead" style={{ marginTop: "16px" }}>
              <span className="subhead-title">1. 参数影响识别（解析物理先验 + 保守残差 ARD-GP）</span>
            </div>
            <div className="cnc-table-box">
              <table>
                <thead>
                  <tr>
                    <th>质量指标</th>
                    <th>建模模式</th>
                    <th>留一 R² / 保守共形半径</th>
                    <th>前 3 主导参数及贡献占比</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.values(closedLoop.surrogate.metricHeads).map((head) => (
                    <tr key={head.metricId}>
                      <td>
                        <strong>{metricLabels[head.metricId] ?? head.metricId}</strong>
                        <small> ({head.unit})</small>
                      </td>
                      <td><span>{modelingModeLabels[head.modelingMode] ?? head.modelingMode}</span></td>
                      <td className="mono">
                        LOO R²={head.looR2Score == null ? "-" : number(head.looR2Score)} · ±{number(head.conformalRadius)}
                        {head.residualEnabled === false ? " · 仅物理先验" : ""}
                      </td>
                      <td>
                        {head.sensitivities
                          .filter((s) => s.status === "Active")
                          .slice(0, 3)
                          .map((s) => `${s.displayName} (${(s.contributionRatio * 100).toFixed(1)}%, ${directionLabels[s.direction] ?? s.direction})`)
                          .join("；")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="cnc-section-subhead" style={{ marginTop: "24px" }}>
              <span className="subhead-title">2. 受约束三档帕累托稀疏推荐（最多微调 {closedLoop.recommendationReport.maxChangedParameters} 个核心参数）</span>
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
                  {closedLoop.recommendationReport.presets.length === 0 && (
                    <tr>
                      <td colSpan={3}>未输出推荐档位：{closedLoop.recommendationReport.noFeasibleReason ?? "没有候选通过门禁"}</td>
                    </tr>
                  )}
                  {closedLoop.recommendationReport.presets.map((preset) => (
                    <tr key={preset.candidateId}>
                      <td><strong>{preset.presetTitle}</strong><small> ({presetRoleLabels[preset.presetRole] ?? preset.presetRole})</small></td>
                      <td>{localizeClosedLoopCopy(preset.tradeoffExplanation)}</td>
                      <td className="mono text-muted">
                        {preset.changedParameters
                          .map((p) => `${p.displayName}: ${p.baselineValue} → ${p.recommendedValue} ${p.unit} (${p.relativeChangePct >= 0 ? "+" : ""}${p.relativeChangePct}%)`)
                          .join(" | ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="cnc-section-subhead" style={{ marginTop: "24px" }}>
              <span className="subhead-title">3. 主动学习下一批补采建议</span>
            </div>
            <ul className="active-doe-list">
              {closedLoop.recommendationReport.activeDoeSuggestions.map((sug) => (
                <li key={sug.suggestionId}>
                  <strong>[{sug.suggestionId.replace(/^active-doe\.0?(\d+)$/, "补采方案 #$1")} · {targetSourceLabels[sug.targetSource] ?? sug.targetSource}]</strong> {localizeClosedLoopCopy(sug.rationale)}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  );
}
