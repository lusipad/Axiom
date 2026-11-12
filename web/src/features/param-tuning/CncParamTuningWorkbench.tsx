import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { XYChart } from "../../charts";
import type { ChartSeries } from "../../charts";
import "./styles.css";

type StageTab = "diagnose" | "surrogate" | "ledger";
type BadgeTone = "pass" | "info" | "warning" | "danger" | "neutral";

interface RegistryParameter {
  parameterId: string;
  displayName: string;
  group: string;
  unit: string;
  valueType: string;
  bounds: [number, number];
  defaultValue: number;
  axisScope: string;
  description: string;
}

interface ParameterBinding {
  vendorParameterId: string;
  canonicalTargets: string[];
  transform: string;
  scale: number;
  offset: number;
  tunability: "nc-tunable" | "drive-side" | "read-only";
}

interface ControllerProfile {
  profileId: string;
  vendorName: string;
  controllerFamily: string;
  registry: {
    registryId: string;
    parameters: RegistryParameter[];
  };
  capabilities: Record<string, boolean>;
  bindings: ParameterBinding[];
  profileContentHash: string;
}

interface ParameterAdjustmentSuggestion {
  parameterId: string;
  displayName: string;
  unit: string;
  tunability: "nc-tunable" | "drive-side" | "read-only";
  currentValue: number;
  suggestedValue: number;
  delta: number;
  mechanismFormula: string;
  expectedEffect: string;
  confidenceLevel: "High" | "Medium" | "TrendOnly";
  verificationNote: string;
}

interface DiagnosticFinding {
  findingId: string;
  severity: "Critical" | "Warning" | "Info";
  symptom: string;
  dominantPrimitive: string;
  errorSource: string;
  observedMetricId: string;
  observedValue: number;
  unit: string;
  suggestions: ParameterAdjustmentSuggestion[];
}

interface SingleRunDiagnosticReport {
  caseId: string;
  controllerProfileId: string;
  sourceKind: string;
  summaryHeadline: string;
  cycleTimeConfidence: string;
  contourErrorConfidence: string;
  confidenceStatement: string;
  findings: DiagnosticFinding[];
  topActions: ParameterAdjustmentSuggestion[];
  permissionLevel: string;
  deviceWriteAllowed: boolean;
  reportContentHash: string;
}

interface DiagnosticScenario {
  scenarioId: string;
  title: string;
  subtitle: string;
  caseId: string;
  badgeTone: "danger" | "warning" | "info" | "pass";
  preview: {
    magnification: number;
    reference: [number, number][];
    command: [number, number][];
    actualMagnified: [number, number][];
  };
  reportsByProfile: Record<
    string,
    {
      full: SingleRunDiagnosticReport;
      ncOnly: SingleRunDiagnosticReport;
    }
  >;
}

interface LedgerMetricRecord {
  metricId: string;
  unit: string;
  baselineObserved?: number | null;
  predictedMean: number;
  uncertaintyRadius: number;
  conservativeUpperBound: number;
  observedValue: number;
  absError: number;
  relativeErrorPct: number;
  withinConservativeBound: boolean;
  improvedOverBaseline?: boolean | null;
}

interface LedgerEntry {
  entryId: string;
  caseId: string;
  candidateId?: string | null;
  inDomain: boolean;
  evidenceOrigin: string;
  r3ReceiptId?: string | null;
  r3DeviceId?: string | null;
  r3TraceContentHash?: string | null;
  metricRecords: Record<string, LedgerMetricRecord>;
  allConservativeBoundsHeld: boolean;
}

interface PredictionVerificationLedger {
  ledgerId: string;
  controllerProfileId?: string;
  entries: LedgerEntry[];
  summary: {
    totalEntryCount: number;
    realR3EntryCount: number;
    externalTraceEntryCount: number;
    syntheticEntryCount: number;
    distinctRealR3TraceCount: number;
    allInDomain: boolean;
    durationRmseS: number;
    durationMapePct: number;
    actualDeviationRmseMm?: number | null;
    empiricalCoverageRate: number;
    entryLevelCoverageRate: number;
  };
  ledgerContentHash: string;
}

interface GovernanceClaim {
  claimId: string;
  claimDefinitionId: string;
  status: string;
  predicate: string;
  metricId?: string | null;
  reasonCode?: string | null;
  evidence: {
    level: string;
    method: string;
  };
}

interface GovernanceScenario {
  stateId: string;
  title: string;
  subtitle: string;
  badgeTone: "warning" | "pass" | "danger";
  governance: {
    caseId: string;
    permissionCeiling: string;
    deviceWriteAllowed: boolean;
    runBundle: {
      run: {
        caseOutcome: string;
        executionStatus: string;
      };
      claims: GovernanceClaim[];
      bundleHash: string;
    };
  };
  ledger: PredictionVerificationLedger | null;
}

interface ParamWorkbenchBundle {
  controllerProfiles: ControllerProfile[];
  diagnosticScenarios: DiagnosticScenario[];
  governanceScenarios: GovernanceScenario[];
}

interface SensitivityItem {
  parameterId: string;
  displayName: string;
  group: string;
  status: string;
  contributionRatio: number;
  direction: string;
}

interface MetricHead {
  metricId: string;
  unit: string;
  modelingMode: string;
  r2Score: number;
  looR2Score?: number | null;
  conformalRadius: number;
  sensitivities: SensitivityItem[];
}

interface ParameterDelta {
  parameterId: string;
  displayName: string;
  unit: string;
  baselineValue: number;
  recommendedValue: number;
  relativeChangePct: number;
}

interface PresetCandidate {
  candidateId: string;
  presetRole: string;
  presetTitle: string;
  changedParameterCount: number;
  changedParameters: ParameterDelta[];
  tradeoffExplanation: string;
}

interface ActiveDoeItem {
  suggestionId: string;
  targetSource: string;
  changedParameterIds: string[];
  acquisitionScore: number;
  rationale: string;
}

interface ClosedLoopDemo {
  case: { caseId: string };
  surrogate: {
    offlineRunCount: number;
    controllerRunCount: number;
    totalSliceSampleCount: number;
    globalActiveParameterIds: string[];
    metricHeads: Record<string, MetricHead>;
  };
  recommendationReport: {
    evaluatedCandidateCount: number;
    feasibleCandidateCount: number;
    paretoCandidateCount: number;
    presets: PresetCandidate[];
    activeDoeSuggestions: ActiveDoeItem[];
  };
}

const PROFILE_LABELS: Record<string, string> = {
  "siemens-sinumerik-840d@1": "西门子 SINUMERIK 840D sl",
  "beckhoff-twincat-nc@1": "倍福 TwinCAT 3 NC",
  "generic-fir-biquad@1": "通用 32 维标准层档案",
};

const GROUP_LABELS: Record<string, string> = {
  G1_GeometryLookahead: "G1 几何与前瞻",
  G2_KinematicsFilter: "G2 加减速与滤波",
  G3_ServoControl: "G3 伺服与补偿",
};

const TUNABILITY_META: Record<
  ParameterBinding["tunability"],
  { label: string; tone: BadgeTone }
> = {
  "nc-tunable": { label: "NC 规划可调", tone: "pass" },
  "drive-side": { label: "伺服驱动侧", tone: "warning" },
  "read-only": { label: "机械只读", tone: "neutral" },
};

const CONFIDENCE_META: Record<string, { label: string; tone: BadgeTone }> = {
  High: { label: "高置信度 · 白盒机理", tone: "pass" },
  Medium: { label: "中置信度 · 耦合缩放", tone: "info" },
  TrendOnly: { label: "趋势参考 · 需单刀复测", tone: "warning" },
};

const CONFIDENCE_SHORT: Record<string, string> = {
  High: "高置信度",
  Medium: "中置信度",
  TrendOnly: "趋势参考",
};

const SEVERITY_LABELS: Record<string, string> = {
  Critical: "严重超差",
  Warning: "机理预警",
  Info: "提速裕量",
};

const ERROR_SOURCE_LABELS: Record<string, string> = {
  QuadrantFriction: "过象限换向摩擦",
  ServoTracking: "双轴伺服跟随失配",
  StructuralResonance: "机械结构谐振",
  PlanningOrFilter: "插补平滑与滤波",
  HeadroomAvailable: "加减速节拍裕量",
};

const DIRECTION_LABELS: Record<string, string> = {
  positive: "正相关",
  negative: "负相关",
  nonlinear: "非线性",
  neutral: "弱相关",
};

const OUTCOME_LABELS: Record<string, string> = {
  Passed: "实证通过",
  Failed: "失准熔断",
  Inconclusive: "待真机实证",
  Invalid: "输入无效",
};

const PERMISSION_LABELS: Record<string, string> = {
  OfflineAdvisory: "离线参数建议（零写权限）",
};

const CLAIM_STATUS_LABELS: Record<string, string> = {
  Supported: "已证实",
  Passed: "通过",
  Inconclusive: "待真机实证",
  Refuted: "已证伪",
  Failed: "未通过",
};

const EVIDENCE_LEVEL_LABELS: Record<string, string> = {
  Observed: "采样观测核验",
  Validated: "真机留出实证",
};

const METRIC_LABELS: Record<string, string> = {
  durationSeconds: "运动周期",
  sampledPathDeviationMaxMm: "指令最大轮廓偏差",
  actualPathDeviationMaxMm: "实测伺服轮廓偏差",
  actualContourErrorMaxMm: "实测伺服轮廓偏差",
  followingErrorMaxMm: "动态跟随误差峰值",
  quadrantGlitchExcessMm: "过象限摩擦突跳超量",
  discreteJerkRms: "离散冲击 Jerk RMS",
  resonanceBandRmsMm: "谐振频带残差 RMS",
  normalServoErrorMaxMm: "双轴法向伺服失配峰值",
};

const CLAIM_TITLES: Record<string, string> = {
  "cnc-greybox.sampled-limits-claim@1": "L0 · 采样轨迹硬限幅门禁",
  "cnc-greybox.r4-calibration-claim@1": "R4 · 灰盒物理模型真机留出标定",
  "cnc-greybox.r5-epistemic-claim@1": "R5 · 共形预测不确定度包络覆盖",
  "cnc-greybox.r7-zero-write-advisory-claim@1": "R7 · 零写权限离线建议安全红线",
};

const CLAIM_PREDICATE_LABELS: Record<string, string> = {
  "cnc-greybox.sampled-limits-claim@1":
    "采样 XYZ 轨迹满足各轴行程、首尾端点、轮廓公差与离散速度/加速度/Jerk 硬约束限制。",
  "cnc-greybox.r4-calibration-claim@1":
    "灰盒物理标定模型对独立留出的真机复切样本具备在声明不确定度内的预测精度（缺少真机留出样本时保持「待真机实证」）。",
  "cnc-greybox.r5-epistemic-claim@1":
    "推荐预设落入训练特征安全包络内，且其共形不确定度上界在真机复切样本上达到标称经验覆盖率（缺少真机留出样本时保持「待真机实证」）。",
  "cnc-greybox.r7-zero-write-advisory-claim@1":
    "系统权限严格锁定为离线参数建议（零设备写权限）；设备级安全认证保持未开启状态，由现场工程师人工核验。",
};

function localizeTuningCopy(text: string): string {
  return text
    .replace(/\(Siemens\s*\/\s*siemens-sinumerik-840d@1\)/g, "（西门子 840D sl）")
    .replace(/\(Beckhoff\s*\/\s*beckhoff-twincat-nc@1\)/g, "（倍福 TwinCAT 3 NC）")
    .replace(/\(Generic\s*\/\s*generic-fir-biquad@1\)/g, "（通用 32 维标准层）")
    .replace(/actualPathDeviationMaxMm=/g, "实测伺服轮廓偏差=")
    .replace(/sampledPathDeviationMaxMm=/g, "指令最大轮廓偏差=")
    .replace(/\bcontroller-trace\b/g, "机床试切采集")
    .replace(/\balgorithm-export\b/g, "离线插补预筛")
    .replace(/\bCEI=/g, "期望改进分=");
}

function fmtNum(value: number | null | undefined, digits = 4): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  return Number(value.toPrecision(digits)).toString();
}

function fmtSigned(value: number, unit: string): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${fmtNum(value, 3)} ${unit}`.trim();
}

function downloadJson(payload: unknown, filename: string): void {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function claimTone(status: string): BadgeTone {
  if (status === "Supported" || status === "Passed") return "pass";
  if (status === "Refuted" || status === "Failed") return "danger";
  if (status === "Inconclusive") return "warning";
  return "neutral";
}

export function CncParamTuningWorkbench({
  onOpenGuide,
  onOpenBenchmark,
}: {
  onOpenGuide?: () => void;
  onOpenBenchmark?: () => void;
}) {
  const [bundle, setBundle] = useState<ParamWorkbenchBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedProfileId, setSelectedProfileId] = useState<string>(
    "siemens-sinumerik-840d@1",
  );
  const [ncOnly, setNcOnly] = useState<boolean>(false);
  const [showMappingDrawer, setShowMappingDrawer] = useState<boolean>(false);
  const [stage, setStage] = useState<StageTab>("diagnose");

  // Tab 1 state
  const [selectedScenarioId, setSelectedScenarioId] =
    useState<string>("resonance-circle");
  const [customMode, setCustomMode] = useState<boolean>(false);
  const [customCase, setCustomCase] = useState<Record<string, unknown> | null>(
    null,
  );
  const [customExport, setCustomExport] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [customCaseName, setCustomCaseName] = useState<string>("");
  const [customExportName, setCustomExportName] = useState<string>("");
  const [customReport, setCustomReport] =
    useState<SingleRunDiagnosticReport | null>(null);
  const [customBusy, setCustomBusy] = useState<boolean>(false);
  const caseInputRef = useRef<HTMLInputElement>(null);
  const exportInputRef = useRef<HTMLInputElement>(null);

  // Tab 2 state
  const [closedLoop, setClosedLoop] = useState<ClosedLoopDemo | null>(null);
  const [surrogateBusy, setSurrogateBusy] = useState<boolean>(false);

  // Tab 3 state
  const [selectedGovStateId, setSelectedGovStateId] =
    useState<string>("synthetic-only");

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/v1/benchmarks/cnc/param-workbench");
        const payload = await res.json();
        if (!res.ok) {
          throw new Error(String(payload?.detail ?? "现场调参工作台数据加载失败"));
        }
        if (!active) return;
        const next = payload as ParamWorkbenchBundle;
        setBundle(next);
        if (next.controllerProfiles[0]) {
          setSelectedProfileId(next.controllerProfiles[0].profileId);
        }
        if (next.diagnosticScenarios[0]) {
          setSelectedScenarioId(next.diagnosticScenarios[0].scenarioId);
        }
        if (next.governanceScenarios[0]) {
          setSelectedGovStateId(next.governanceScenarios[0].stateId);
        }
      } catch (reason) {
        if (active) {
          setError(
            reason instanceof Error ? reason.message : "现场调参工作台数据加载失败",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function loadSurrogateDemo() {
    setSurrogateBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/benchmarks/cnc/param-demo");
      const payload = await res.json();
      if (!res.ok) {
        throw new Error(String(payload?.detail ?? "多保真灰盒推荐加载失败"));
      }
      setClosedLoop(payload as ClosedLoopDemo);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "多保真灰盒推荐加载失败",
      );
    } finally {
      setSurrogateBusy(false);
    }
  }

  useEffect(() => {
    if (stage === "surrogate" && !closedLoop && !surrogateBusy) {
      void loadSurrogateDemo();
    }
  }, [stage, closedLoop, surrogateBusy]);

  const activeProfile = useMemo(
    () =>
      bundle?.controllerProfiles.find(
        (item) => item.profileId === selectedProfileId,
      ) ?? bundle?.controllerProfiles[0] ?? null,
    [bundle, selectedProfileId],
  );

  const bindingByParamId = useMemo(() => {
    const map = new Map<string, ParameterBinding>();
    for (const b of activeProfile?.bindings ?? []) {
      map.set(b.vendorParameterId, b);
    }
    return map;
  }, [activeProfile]);

  const activeScenario = useMemo(
    () =>
      bundle?.diagnosticScenarios.find(
        (item) => item.scenarioId === selectedScenarioId,
      ) ?? bundle?.diagnosticScenarios[0] ?? null,
    [bundle, selectedScenarioId],
  );

  const activeDiagnosticReport: SingleRunDiagnosticReport | null = useMemo(() => {
    if (customMode) return customReport;
    if (!activeScenario || !activeProfile) return null;
    const pair = activeScenario.reportsByProfile[activeProfile.profileId];
    if (!pair) return null;
    return ncOnly ? pair.ncOnly : pair.full;
  }, [customMode, customReport, activeScenario, activeProfile, ncOnly]);

  const contourSeries: ChartSeries[] = useMemo(() => {
    if (customMode && customCase && customExport) {
      const refRaw = Array.isArray(customCase.referencePath)
        ? customCase.referencePath
        : [];
      const sampRaw = Array.isArray(customExport.samples)
        ? customExport.samples
        : [];
      const refPts: [number, number][] = refRaw
        .filter((p): p is number[] => Array.isArray(p) && p.length >= 2)
        .map((p) => [Number(p[0] ?? 0), Number(p[1] ?? 0)]);
      const cmdPts: [number, number][] = sampRaw
        .map((s) =>
          s && typeof s === "object"
            ? (s as { positionMm?: unknown }).positionMm
            : null,
        )
        .filter((p): p is number[] => Array.isArray(p) && p.length >= 2)
        .map((p) => [Number(p[0] ?? 0), Number(p[1] ?? 0)]);
      return [
        {
          id: "ref",
          label: "参考刀路",
          points: refPts.length >= 2 ? refPts : [[0, 0], [10, 10]],
          tone: "reference",
          dashed: true,
          markers: false,
        },
        {
          id: "cmd",
          label: "导入采样轨迹",
          points: cmdPts.length >= 2 ? cmdPts : [[0, 0], [10, 10]],
          tone: "baseline",
          markers: false,
        },
      ];
    }
    if (!activeScenario) return [];
    return [
      {
        id: "ref",
        label: "参考刀路",
        points: activeScenario.preview.reference,
        tone: "reference",
        dashed: true,
        markers: false,
      },
      {
        id: "cmd",
        label: "NC 插补指令",
        points: activeScenario.preview.command,
        tone: "baseline",
        markers: false,
      },
      {
        id: "act",
        label: `实测伺服轨迹（误差放大 ${activeScenario.preview.magnification}×）`,
        points: activeScenario.preview.actualMagnified,
        tone: "s3",
        markers: false,
      },
    ];
  }, [customMode, customCase, customExport, activeScenario]);

  const activeGovScenario = useMemo(
    () =>
      bundle?.governanceScenarios.find(
        (item) => item.stateId === selectedGovStateId,
      ) ?? bundle?.governanceScenarios[0] ?? null,
    [bundle, selectedGovStateId],
  );

  async function handleCustomFile(
    kind: "case" | "export",
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const parsed = JSON.parse(
        (await file.text()).replace(/^\uFEFF/, ""),
      ) as Record<string, unknown>;
      if (kind === "case") {
        setCustomCase(parsed);
        setCustomCaseName(file.name);
      } else {
        setCustomExport(parsed);
        setCustomExportName(file.name);
      }
      setCustomReport(null);
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error ? `文件解析失败：${reason.message}` : "无法解析 JSON",
      );
    }
  }

  async function runCustomDiagnose() {
    if (!customCase || !customExport || !activeProfile) return;
    setCustomBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/benchmarks/cnc/param-diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case: customCase,
          export: customExport,
          profileId: activeProfile.profileId,
          includeDriveSide: !ncOnly,
        }),
      });
      const payload = await res.json();
      if (!res.ok) {
        throw new Error(String(payload?.detail ?? "单刀机理快诊执行失败"));
      }
      setCustomReport(payload as SingleRunDiagnosticReport);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "单刀机理快诊执行失败",
      );
    } finally {
      setCustomBusy(false);
    }
  }

  return (
    <main className="param-tuning-page" aria-label="现场调参与单刀快诊工作台">
      {/* Studio Hero Header */}
      <header className="pt-hero">
        <div className="pt-hero-main">
          <div className="pt-eyebrow-row">
            <span className="pt-eyebrow">现场数控调参工作台</span>
            <span className="pt-safety-pill">
              离线参数建议 · 零设备写权限
            </span>
          </div>
          <h1>现场调参与单刀快诊</h1>
          <p>
            面向一线数控工艺与调试工程师：切 1 刀即可按白盒机理定位瓶颈并映射为西门子 /
            倍福原生参数；切少量样本可跨刀路建立不确定度包络；复切遥测逐刀入账，满 3
            刀独立 R3 实证自动晋升可信门禁。
          </p>
        </div>
        <div className="pt-hero-actions">
          {onOpenBenchmark && (
            <button
              type="button"
              className="button button-secondary"
              onClick={onOpenBenchmark}
            >
              ← 算法 A/B 对比
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
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <strong>提示</strong>
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            aria-label="关闭提示"
          >
            ×
          </button>
        </div>
      )}

      {/* Persistent Multi-Vendor Controller Profile & Permission Strip */}
      <section className="pt-profile-strip" aria-label="目标数控系统与权限设置">
        <div className="pt-profile-top">
          <div className="pt-profile-cards">
            {(bundle?.controllerProfiles ?? []).map((prof) => {
              const ncCount = prof.bindings.filter(
                (b) => b.tunability === "nc-tunable",
              ).length;
              const driveCount = prof.bindings.filter(
                (b) => b.tunability === "drive-side",
              ).length;
              const isSelected = prof.profileId === activeProfile?.profileId;
              const label =
                PROFILE_LABELS[prof.profileId] ??
                `${prof.vendorName} · ${prof.controllerFamily}`;
              return (
                <button
                  key={prof.profileId}
                  type="button"
                  className={`pt-profile-btn ${isSelected ? "active" : ""}`}
                  aria-pressed={isSelected}
                  onClick={() => {
                    setSelectedProfileId(prof.profileId);
                    setCustomReport(null);
                  }}
                >
                  <div className="pt-profile-btn-head">
                    <span className="pt-profile-vendor">{label}</span>
                    <span className="pt-profile-dim">
                      {prof.registry.parameters.length} 维参数
                    </span>
                  </div>
                  <span className="pt-profile-family">
                    {prof.controllerFamily}
                  </span>
                  <div className="pt-profile-counts">
                    <span>NC 规划 {ncCount} 项</span>
                    <span>·</span>
                    <span>驱动伺服 {driveCount} 项</span>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="pt-profile-controls">
            <label className={`pt-nc-toggle ${ncOnly ? "checked" : ""}`}>
              <input
                type="checkbox"
                checked={ncOnly}
                onChange={(e) => {
                  setNcOnly(e.target.checked);
                  setCustomReport(null);
                }}
              />
              <span className="pt-nc-toggle-copy">
                <strong>仅调 NC 规划参数（锁死伺服驱动器）</strong>
                <span>
                  工艺员权限：自动过滤电流环陷波、Kv 增益与摩擦补偿项
                </span>
              </span>
            </label>

            <button
              type="button"
              className="button button-secondary pt-drawer-btn"
              aria-expanded={showMappingDrawer}
              onClick={() => setShowMappingDrawer((prev) => !prev)}
            >
              {showMappingDrawer
                ? "收起厂商参数映射表"
                : `查看厂商参数映射表 (${activeProfile?.registry.parameters.length ?? 0} 项)`}
            </button>
          </div>
        </div>

        {showMappingDrawer && activeProfile && (
          <div className="pt-mapping-drawer">
            <div className="pt-mapping-head">
              <strong>
                {PROFILE_LABELS[activeProfile.profileId] ??
                  activeProfile.vendorName}{" "}
                ↔ Axiom 标准运动学内核映射表
              </strong>
              <span>
                档案哈希：{activeProfile.profileContentHash.slice(0, 12)}…
              </span>
            </div>
            <div className="pt-table-scroll">
              <table className="pt-table">
                <thead>
                  <tr>
                    <th>厂商参数 ID</th>
                    <th>现场参数名称</th>
                    <th>分层</th>
                    <th>默认与边界</th>
                    <th>标准核映射关系</th>
                    <th>现场可调权限</th>
                  </tr>
                </thead>
                <tbody>
                  {activeProfile.registry.parameters.map((param) => {
                    const bind = bindingByParamId.get(param.parameterId);
                    const tuneMeta = bind
                      ? TUNABILITY_META[bind.tunability]
                      : TUNABILITY_META["nc-tunable"];
                    return (
                      <tr key={param.parameterId}>
                        <td>
                          <code>{param.parameterId}</code>
                        </td>
                        <td>
                          <strong>{param.displayName}</strong>
                        </td>
                        <td>{GROUP_LABELS[param.group] ?? param.group}</td>
                        <td>
                          <code>
                            {param.defaultValue} [{param.bounds[0]}..
                            {param.bounds[1]}] {param.unit}
                          </code>
                        </td>
                        <td>
                          <code>
                            {bind?.canonicalTargets.join(", ") ?? "—"} (
                            {bind?.transform === "reciprocal_2pi"
                              ? "1/(2π·τ)"
                              : `×${fmtNum(bind?.scale ?? 1, 3)}`}
                            )
                          </code>
                        </td>
                        <td>
                          <span className={`pt-pill ${tuneMeta.tone}`}>
                            {tuneMeta.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* 3-Stage Workflow Stepper Tabs */}
      <div className="pt-stage-tabs" role="tablist" aria-label="调参三阶段流程">
        <button
          type="button"
          role="tab"
          className="pt-stage-tab"
          aria-selected={stage === "diagnose"}
          onClick={() => setStage("diagnose")}
        >
          <span className="pt-stage-num">01</span>
          <span className="pt-stage-copy">
            <strong>单刀快诊顾问</strong>
            <span>1 刀起用 · 零 DoE 试切 · 单次改 ≤ 2 个参数</span>
          </span>
        </button>

        <button
          type="button"
          role="tab"
          className="pt-stage-tab"
          aria-selected={stage === "surrogate"}
          onClick={() => setStage("surrogate")}
        >
          <span className="pt-stage-num">02</span>
          <span className="pt-stage-copy">
            <strong>多保真敏感度与三档推荐</strong>
            <span>灰盒残差代理 · 关键参数排序 · 精度/均衡/效率三档</span>
          </span>
        </button>

        <button
          type="button"
          role="tab"
          className="pt-stage-tab"
          aria-selected={stage === "ledger"}
          onClick={() => setStage("ledger")}
        >
          <span className="pt-stage-num">03</span>
          <span className="pt-stage-copy">
            <strong>预测-实测对账与真机门禁</strong>
            <span>复切遥测入账 · 满 3 刀 R3 晋升 · 热漂移熔断</span>
          </span>
        </button>
      </div>

      {/* Loading Skeleton */}
      {loading && (
        <div className="pt-empty-box">正在加载跨数控系统现场调参工作台数据…</div>
      )}

      {/* =================================================================
          STAGE 01: SINGLE-CUT DIAGNOSTIC ADVISOR
         ================================================================= */}
      {!loading && stage === "diagnose" && (
        <>
          <section className="pt-scenario-grid" aria-label="现场试切问题场景">
            {(bundle?.diagnosticScenarios ?? []).map((sc) => {
              const active = !customMode && sc.scenarioId === activeScenario?.scenarioId;
              return (
                <button
                  key={sc.scenarioId}
                  type="button"
                  className={`pt-scenario-card ${active ? "active" : ""}`}
                  onClick={() => {
                    setCustomMode(false);
                    setSelectedScenarioId(sc.scenarioId);
                  }}
                >
                  <div className="pt-scenario-top">
                    <span className={`pt-pill ${sc.badgeTone}`}>
                      {sc.caseId}
                    </span>
                    <span className="pt-pill neutral">
                      误差放大 {sc.preview.magnification}×
                    </span>
                  </div>
                  <strong>{sc.title}</strong>
                  <p>{sc.subtitle}</p>
                </button>
              );
            })}

            <button
              type="button"
              className={`pt-scenario-card ${customMode ? "active" : ""}`}
              onClick={() => setCustomMode(true)}
            >
              <div className="pt-scenario-top">
                <span className="pt-pill info">自定义导入</span>
                <span className="pt-pill neutral">JSON</span>
              </div>
              <strong>导入自有单刀数据快诊</strong>
              <p>上传现场刀路 Case 与单次采样轨迹 JSON，即时生成厂商原生调参单</p>
            </button>
          </section>

          {customMode && (
            <section className="pt-custom-upload-card">
              <div className="pt-custom-files">
                <input
                  ref={caseInputRef}
                  type="file"
                  accept="application/json,.json"
                  hidden
                  onChange={(e) => void handleCustomFile("case", e)}
                />
                <input
                  ref={exportInputRef}
                  type="file"
                  accept="application/json,.json"
                  hidden
                  onChange={(e) => void handleCustomFile("export", e)}
                />
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => caseInputRef.current?.click()}
                >
                  {customCaseName
                    ? `已选刀路：${customCaseName}`
                    : "1. 选择刀路 Case JSON"}
                </button>
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => exportInputRef.current?.click()}
                >
                  {customExportName
                    ? `已选轨迹：${customExportName}`
                    : "2. 选择单刀轨迹 Export JSON"}
                </button>
              </div>
              <div className="pt-custom-files">
                <button
                  type="button"
                  className="button button-primary"
                  disabled={!customCase || !customExport || customBusy}
                  onClick={() => void runCustomDiagnose()}
                >
                  {customBusy ? "正在诊断机理…" : "执行单刀机理快诊"}
                </button>
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => setCustomMode(false)}
                >
                  返回预置典型场景
                </button>
              </div>
            </section>
          )}

          <div className="pt-diag-grid">
            {/* Left Column: Ballbar-style Error-Magnified Contour + Epistemic Banner */}
            <section className="pt-card">
              <div className="pt-card-head">
                <div>
                  <h2>
                    {customMode
                      ? "导入刀路与采样轨迹 XY 投影"
                      : "球杆仪级法向误差放大轮廓图"}
                  </h2>
                  <p className="pt-card-sub">
                    {customMode
                      ? "叠加对比参考路径与采样轨迹坐标"
                      : `将微米级伺服动态偏差沿法向放大 ${activeScenario?.preview.magnification ?? 50} 倍，直观暴露过象限尖峰、拐角内缩与高频振纹`}
                  </p>
                </div>
                {!customMode && activeScenario && (
                  <span className="pt-pill warning">
                    法向误差 ×{activeScenario.preview.magnification}
                  </span>
                )}
              </div>

              <XYChart
                series={contourSeries}
                ariaLabel="参考刀路、插补指令与误差放大实测轮廓对比"
                xLabel="X (mm)"
                yLabel="Y (mm)"
                height={300}
                legend={false}
              />

              <div className="pt-chart-legend">
                <span>
                  <i className="pt-legend-dot ref" /> 参考刀路
                </span>
                <span>
                  <i className="pt-legend-dot cmd" /> NC 插补指令
                </span>
                {!customMode && (
                  <span>
                    <i className="pt-legend-dot act" /> 实测伺服轨迹（误差放大）
                  </span>
                )}
              </div>

              {activeDiagnosticReport && (
                <div className="pt-epistemic-box">
                  <div className="pt-epistemic-row">
                    <div className="pt-epistemic-item">
                      <span>节拍与 FIR 零点置信度</span>
                      <strong>
                        <span
                          className={`pt-pill ${
                            CONFIDENCE_META[
                              activeDiagnosticReport.cycleTimeConfidence
                            ]?.tone ?? "pass"
                          }`}
                        >
                          {CONFIDENCE_SHORT[activeDiagnosticReport.cycleTimeConfidence] ??
                            activeDiagnosticReport.cycleTimeConfidence}{" "}
                          · 白盒确定性公式
                        </span>
                      </strong>
                    </div>
                    <div className="pt-epistemic-item">
                      <span>实测轮廓误差幅值置信度</span>
                      <strong>
                        <span
                          className={`pt-pill ${
                            CONFIDENCE_META[
                              activeDiagnosticReport.contourErrorConfidence
                            ]?.tone ?? "warning"
                          }`}
                        >
                          {CONFIDENCE_SHORT[activeDiagnosticReport.contourErrorConfidence] ??
                            activeDiagnosticReport.contourErrorConfidence}{" "}
                          · 仅作方向参考
                        </span>
                      </strong>
                    </div>
                  </div>
                  <p className="pt-epistemic-note">
                    {activeDiagnosticReport.confidenceStatement}
                  </p>
                </div>
              )}
            </section>

            {/* Right Column: <= 2 Priority Parameter Cards + Mechanism Findings */}
            <section className="pt-card">
              {!activeDiagnosticReport ? (
                <div className="pt-empty-box">
                  请先上传刀路 Case JSON 与单刀轨迹 Export JSON，点击「执行单刀机理快诊」生成厂商原生调参建议。
                </div>
              ) : (
                <>
                  <div className="pt-card-head">
                    <div>
                      <h2>优先单刀调参动作单（上限 2 项）</h2>
                      <p className="pt-card-sub">
                        {localizeTuningCopy(activeDiagnosticReport.summaryHeadline)}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="button button-secondary"
                      onClick={() =>
                        downloadJson(
                          activeDiagnosticReport,
                          `${activeDiagnosticReport.caseId}-${activeDiagnosticReport.controllerProfileId}-diagnostic.json`,
                        )
                      }
                    >
                      导出单刀调参单 JSON
                    </button>
                  </div>

                  {activeDiagnosticReport.topActions.length === 0 ? (
                    <div className="pt-empty-box">
                      当前权限条件下无需要改动的 NC 规划参数（或瓶颈仅位于被锁定的伺服驱动侧）。
                    </div>
                  ) : (
                    <div className="pt-action-list">
                      {activeDiagnosticReport.topActions.map((act, idx) => {
                        const tune =
                          TUNABILITY_META[act.tunability] ??
                          TUNABILITY_META["nc-tunable"];
                        const conf =
                          CONFIDENCE_META[act.confidenceLevel] ??
                          CONFIDENCE_META.Medium!;
                        return (
                          <article
                            className="pt-action-card"
                            key={act.parameterId}
                          >
                            <div className="pt-action-top">
                              <div className="pt-action-badges">
                                <span className="pt-rank-badge">
                                  优先 #{idx + 1}
                                </span>
                                <span className={`pt-pill ${tune.tone}`}>
                                  {tune.label}
                                </span>
                                <span className={`pt-pill ${conf.tone}`}>
                                  {conf.label}
                                </span>
                              </div>
                            </div>

                            <div className="pt-action-title-row">
                              <h4>{act.displayName}</h4>
                              <code>{act.parameterId}</code>
                            </div>

                            <div className="pt-value-transition">
                              <div className="pt-val-box">
                                <span>当前设定值</span>
                                <strong>
                                  {fmtNum(act.currentValue, 4)} {act.unit}
                                </strong>
                              </div>
                              <span className="pt-val-arrow" aria-hidden="true">
                                →
                              </span>
                              <div className="pt-val-box target">
                                <span>建议试切值</span>
                                <strong>
                                  {fmtNum(act.suggestedValue, 4)} {act.unit}
                                </strong>
                              </div>
                              <span className="pt-val-delta">
                                Δ {fmtSigned(act.delta, act.unit)}
                              </span>
                            </div>

                            <div className="pt-action-meta">
                              <div className="pt-formula-line">
                                {act.mechanismFormula}
                              </div>
                              <div>
                                <strong>预期改善：</strong>
                                {act.expectedEffect}
                              </div>
                              <div>
                                <strong>复切核验：</strong>
                                {act.verificationNote}
                              </div>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}

                  <div className="pt-card-head" style={{ marginTop: 6 }}>
                    <div>
                      <h3>诊断识别的全部机理问题（{activeDiagnosticReport.findings.length} 项）</h3>
                    </div>
                  </div>

                  <div className="pt-findings-list">
                    {activeDiagnosticReport.findings.map((finding) => {
                      const sevTone: BadgeTone =
                        finding.severity === "Critical"
                          ? "danger"
                          : finding.severity === "Warning"
                            ? "warning"
                            : "info";
                      return (
                        <div
                          className="pt-finding-item"
                          key={finding.findingId}
                        >
                          <div className="pt-finding-head">
                            <strong>{finding.symptom}</strong>
                            <div className="pt-action-badges">
                              <span className={`pt-pill ${sevTone}`}>
                                {SEVERITY_LABELS[finding.severity] ?? finding.severity}
                              </span>
                              <span className="pt-pill neutral">
                                {METRIC_LABELS[finding.observedMetricId] ??
                                  finding.observedMetricId}
                                ：{fmtNum(finding.observedValue, 4)}{" "}
                                {finding.unit}
                              </span>
                            </div>
                          </div>
                          {ncOnly && finding.suggestions.length === 0 && (
                            <p className="pt-finding-LockNote">
                              已开启「仅调 NC 规划参数」：该问题属于驱动器伺服侧机理（
                              {ERROR_SOURCE_LABELS[finding.errorSource] ??
                                finding.errorSource}
                              ），驱动增益/摩擦补偿建议已按权限自动屏蔽。
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </section>
          </div>
        </>
      )}

      {/* =================================================================
          STAGE 02: MULTI-FIDELITY SENSITIVITY & 3 PARETO PRESETS
         ================================================================= */}
      {!loading && stage === "surrogate" && (
        <>
          <section className="pt-card">
            <div className="pt-card-head">
              <div>
                <h2>多保真灰盒代理建模与帕累托三档推荐</h2>
                <p className="pt-card-sub">
                  融合白盒运动学/频域先验 + Group-ARD 稀疏残差学习：自动筛除不敏感参数，并在共形不确定度安全包络内求解三档参数包。
                </p>
              </div>
              <div className="pt-custom-files">
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={surrogateBusy}
                  onClick={() => void loadSurrogateDemo()}
                >
                  {surrogateBusy ? "正在更新灰盒模型…" : "重新运行多保真灰盒建模"}
                </button>
                {closedLoop && (
                  <button
                    type="button"
                    className="button button-primary"
                    onClick={() =>
                      downloadJson(
                        closedLoop.recommendationReport,
                        `${closedLoop.case.caseId}-pareto-presets.json`,
                      )
                    }
                  >
                    导出三档推荐 JSON
                  </button>
                )}
              </div>
            </div>

            {surrogateBusy && !closedLoop && (
              <div className="pt-empty-box">
                正在执行离线几何预筛 + 控制器高保真残差校准与帕累托搜索…
              </div>
            )}

            {closedLoop && (
              <>
                <div className="pt-kpi-grid">
                  <div className="pt-kpi-card">
                    <span>低成本离线样本</span>
                    <strong>{closedLoop.surrogate.offlineRunCount} 组</strong>
                    <small>快速探索规划与滤波几何边界</small>
                  </div>
                  <div className="pt-kpi-card">
                    <span>机床级高保真样本</span>
                    <strong>{closedLoop.surrogate.controllerRunCount} 组</strong>
                    <small>锚定伺服跟随与换向摩擦残差</small>
                  </div>
                  <div className="pt-kpi-card">
                    <span>Group-ARD 活跃参数</span>
                    <strong>
                      {closedLoop.surrogate.globalActiveParameterIds.length} 项
                    </strong>
                    <small>从高维参数空间自动剥离冗余项</small>
                  </div>
                  <div className="pt-kpi-card">
                    <span>包络内可行 / 帕累托解</span>
                    <strong>
                      {closedLoop.recommendationReport.feasibleCandidateCount} /{" "}
                      {closedLoop.recommendationReport.paretoCandidateCount}
                    </strong>
                    <small>
                      总评估{" "}
                      {closedLoop.recommendationReport.evaluatedCandidateCount}{" "}
                      组候选
                    </small>
                  </div>
                </div>

                <div className="pt-card-head" style={{ marginTop: 6 }}>
                  <div>
                    <h3>帕累托前沿三档预设（单套限改 ≤ 5 个关键参数）</h3>
                  </div>
                </div>

                <div className="pt-presets-grid">
                  {closedLoop.recommendationReport.presets.map((preset) => {
                    const isBalanced =
                      preset.presetRole === "BalancedKneePoint" ||
                      preset.presetRole === "balanced";
                    return (
                      <article
                        key={preset.candidateId}
                        className={`pt-preset-card ${
                          isBalanced ? "balanced" : ""
                        }`}
                      >
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                          <div className="pt-action-top">
                            <strong>{preset.presetTitle}</strong>
                            <span
                              className={`pt-pill ${
                                isBalanced ? "pass" : "info"
                              }`}
                            >
                              改动 {preset.changedParameterCount} 项
                            </span>
                          </div>
                          <p className="pt-card-sub" style={{ margin: 0 }}>
                            {localizeTuningCopy(preset.tradeoffExplanation)}
                          </p>
                          <div className="pt-preset-deltas">
                            {preset.changedParameters.map((delta) => (
                              <div
                                className="pt-delta-item"
                                key={delta.parameterId}
                              >
                                <div className="pt-delta-item-top">
                                  <span>{delta.displayName}</span>
                                  <span className="pt-pill neutral">
                                    {delta.relativeChangePct > 0 ? "+" : ""}
                                    {fmtNum(delta.relativeChangePct, 3)}%
                                  </span>
                                </div>
                                <div className="pt-delta-item-vals">
                                  {fmtNum(delta.baselineValue, 4)} →{" "}
                                  <strong>
                                    {fmtNum(delta.recommendedValue, 4)}{" "}
                                    {delta.unit}
                                  </strong>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>

                <div className="pt-card-head" style={{ marginTop: 8 }}>
                  <div>
                    <h3>关键加工指标敏感度分解与 LOO 交叉验证精度</h3>
                  </div>
                </div>

                <div className="pt-sens-grid">
                  {Object.values(closedLoop.surrogate.metricHeads)
                    .slice(0, 6)
                    .map((head) => (
                      <div className="pt-sens-card" key={head.metricId}>
                        <div className="pt-action-top">
                          <strong>
                            {METRIC_LABELS[head.metricId] ?? head.metricId}
                          </strong>
                          <div className="pt-action-badges">
                            <span className="pt-pill info">
                              LOO R² ={" "}
                              {fmtNum(head.looR2Score ?? head.r2Score, 3)}
                            </span>
                            <span className="pt-pill neutral">
                              共形半径 ±{fmtNum(head.conformalRadius, 3)}{" "}
                              {head.unit}
                            </span>
                          </div>
                        </div>
                        <div className="pt-sens-bars">
                          {head.sensitivities.slice(0, 3).map((sens) => {
                            const pct = Math.min(
                              100,
                              Math.max(4, Math.round(sens.contributionRatio * 100)),
                            );
                            return (
                              <div
                                className="pt-sens-bar-row"
                                key={sens.parameterId}
                              >
                                <div className="pt-sens-bar-label">
                                  <span>
                                    {sens.displayName}{" "}
                                    <code>
                                      ({DIRECTION_LABELS[sens.direction] ?? sens.direction})
                                    </code>
                                  </span>
                                  <strong>{pct}%</strong>
                                </div>
                                <div className="pt-sens-bar-track">
                                  <div
                                    className="pt-sens-bar-fill"
                                    style={{ width: `${pct}%` }}
                                  />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                </div>

                {closedLoop.recommendationReport.activeDoeSuggestions.length >
                  0 && (
                  <>
                    <div className="pt-card-head" style={{ marginTop: 8 }}>
                      <div>
                        <h3>主动补点建议（下一刀测哪里信息量最大）</h3>
                      </div>
                    </div>
                    <div className="pt-presets-grid">
                      {closedLoop.recommendationReport.activeDoeSuggestions
                        .slice(0, 3)
                        .map((item) => (
                          <div
                            className="pt-finding-item"
                            key={item.suggestionId}
                          >
                            <div className="pt-finding-head">
                              <strong>
                                {item.suggestionId.replace(
                                  /^active-doe\.0?(\d+)$/,
                                  "补采建议 #$1",
                                )}
                              </strong>
                              <span className="pt-pill info">
                                {item.targetSource === "controller-trace"
                                  ? "建议机床试切采集"
                                  : "建议离线插补预筛"}
                              </span>
                            </div>
                            <p className="pt-card-sub" style={{ margin: 0 }}>
                              {localizeTuningCopy(item.rationale)}
                            </p>
                          </div>
                        ))}
                    </div>
                  </>
                )}
              </>
            )}
          </section>
        </>
      )}

      {/* =================================================================
          STAGE 03: PREDICTION-VERIFICATION LEDGER & R3 HOLDOUT GOVERNANCE
         ================================================================= */}
      {!loading && stage === "ledger" && activeGovScenario && (
        <>
          <section
            className="pt-gov-selector"
            aria-label="真机留出对账演进阶段切换"
          >
            {(bundle?.governanceScenarios ?? []).map((govItem) => {
              const active = govItem.stateId === activeGovScenario.stateId;
              return (
                <button
                  key={govItem.stateId}
                  type="button"
                  className={`pt-scenario-card ${active ? "active" : ""}`}
                  aria-pressed={active}
                  onClick={() => setSelectedGovStateId(govItem.stateId)}
                >
                  <div className="pt-scenario-top">
                    <span className={`pt-pill ${govItem.badgeTone}`}>
                      结论：
                      {OUTCOME_LABELS[
                        govItem.governance.runBundle.run.caseOutcome
                      ] ?? govItem.governance.runBundle.run.caseOutcome}
                    </span>
                    <span className="pt-pill neutral">
                      R3 留出{" "}
                      {govItem.ledger?.summary.distinctRealR3TraceCount ?? 0} / 3
                      刀
                    </span>
                  </div>
                  <strong>{govItem.title}</strong>
                  <p>{govItem.subtitle}</p>
                </button>
              );
            })}
          </section>

          <section className={`pt-gov-banner ${activeGovScenario.badgeTone}`}>
            <div>
              <strong>
                当前治理判定：
                {OUTCOME_LABELS[
                  activeGovScenario.governance.runBundle.run.caseOutcome
                ] ?? activeGovScenario.governance.runBundle.run.caseOutcome}
                （权限上限：
                {PERMISSION_LABELS[
                  activeGovScenario.governance.permissionCeiling
                ] ?? activeGovScenario.governance.permissionCeiling}
                ）
              </strong>
              <p>
                {activeGovScenario.stateId === "synthetic-only" &&
                  "诚实性门禁生效：当前仅有离线/合成校准样本（0 刀真机留出），R4 物理标定与 R5 认知包络拒绝自封「已证实」，保持「待真机实证」直至至少 3 刀独立 R3 遥测复切对账达标。"}
                {activeGovScenario.stateId === "r3-promoted" &&
                  "实证晋升通过：直角、整圆、S 曲线 3 刀独立 R3 机床只读遥测全部完成预测-实测对账，周期 MAPE 1.43%（≤ 8%）、轮廓 RMSE 7.6 µm（≤ 15 µm）、保守上界覆盖率 88.9%（≥ 80%），R4/R5 自动晋升为「已证实」。"}
                {activeGovScenario.stateId === "drift-refuted" &&
                  "失准熔断告警：现场导轨温升引发 +0.085 mm 热漂移，切后实测轮廓误差突破 95% 保守上界（轮廓 RMSE 68.1 µm > 15 µm 门限，覆盖率跌至 66.7%），R4/R5 自动降级为「已证伪」，提示重新采集基准刀标定。"}
              </p>
            </div>
            <button
              type="button"
              className="button button-secondary"
              onClick={() =>
                downloadJson(
                  activeGovScenario,
                  `axiom-governance-${activeGovScenario.stateId}.json`,
                )
              }
            >
              导出对账与门禁证据包 JSON
            </button>
          </section>

          <div className="pt-kpi-grid">
            <div className="pt-kpi-card">
              <span>独立 R3 真机对账进度</span>
              <strong>
                {activeGovScenario.ledger?.summary.distinctRealR3TraceCount ??
                  0}{" "}
                / 3 刀
              </strong>
              <small>带只读设备回执与内容哈希验真</small>
            </div>
            <div className="pt-kpi-card">
              <span>运动周期预测 MAPE</span>
              <strong>
                {activeGovScenario.ledger
                  ? `${fmtNum(activeGovScenario.ledger.summary.durationMapePct, 3)}%`
                  : "待复切"}
              </strong>
              <small>晋升硬门限 ≤ 8.0%</small>
            </div>
            <div className="pt-kpi-card">
              <span>实测轮廓误差预测 RMSE</span>
              <strong>
                {activeGovScenario.ledger?.summary.actualDeviationRmseMm != null
                  ? `${fmtNum(
                      activeGovScenario.ledger.summary.actualDeviationRmseMm *
                        1000,
                      3,
                    )} µm`
                  : "待复切"}
              </strong>
              <small>晋升硬门限 ≤ 15.0 µm</small>
            </div>
            <div className="pt-kpi-card">
              <span>95% 保守上界经验覆盖率</span>
              <strong>
                {activeGovScenario.ledger
                  ? `${fmtNum(
                      activeGovScenario.ledger.summary.empiricalCoverageRate *
                        100,
                      3,
                    )}%`
                  : "待复切"}
              </strong>
              <small>晋升硬门限 ≥ 80.0%</small>
            </div>
          </div>

          {/* Per-Cut Prediction vs Observed Reconciliation Ledger */}
          <section className="pt-card">
            <div className="pt-card-head">
              <div>
                <h2>预测-实测逐刀对账台账</h2>
                <p className="pt-card-sub">
                  每次按建议参数在机床上复切后，将只读采集的 R3 轨迹回传台账，逐项比对「切前灰盒预测区间」与「切后真机实测值」。
                </p>
              </div>
              {activeGovScenario.ledger && (
                <span className="pt-pill neutral">
                  台账 ID：{activeGovScenario.ledger.ledgerId}
                </span>
              )}
            </div>

            {!activeGovScenario.ledger ? (
              <div className="pt-empty-box">
                当前处于「阶段 A · 仅离线/合成建模」，尚无真机复切记录入账。可点击上方「阶段
                B · 满 3 刀独立 R3 真机复切对账达标」查看完整逐刀对账表，或通过{" "}
                <code>POST /api/v1/benchmarks/cnc/param-ledger</code>{" "}
                追加现场复切遥测。
              </div>
            ) : (
              <div className="pt-findings-list">
                {activeGovScenario.ledger.entries.map((entry) => (
                  <div className="pt-ledger-cut" key={entry.entryId}>
                    <div className="pt-ledger-cut-head">
                      <div className="pt-action-badges">
                        <strong>{entry.entryId}</strong>
                        <span className="pt-pill info">{entry.caseId}</span>
                        {entry.r3DeviceId && (
                          <span className="pt-pill neutral">
                            设备：{entry.r3DeviceId} · 回执 {entry.r3ReceiptId}
                          </span>
                        )}
                      </div>
                      <span
                        className={`pt-pill ${
                          entry.allConservativeBoundsHeld ? "pass" : "danger"
                        }`}
                      >
                        {entry.allConservativeBoundsHeld
                          ? "核心指标全部命中保守上界"
                          : "存在指标超出保守上界"}
                      </span>
                    </div>

                    <div className="pt-table-scroll">
                      <table className="pt-table">
                        <thead>
                          <tr>
                            <th>考核指标</th>
                            <th>切前基线</th>
                            <th>灰盒预测均值 ± 共形半径</th>
                            <th>95% 保守上界门禁</th>
                            <th>切后真机实测值</th>
                            <th>绝对预测误差</th>
                            <th>包络命中判定</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            "durationSeconds",
                            "sampledPathDeviationMaxMm",
                            "actualPathDeviationMaxMm",
                            "followingErrorMaxMm",
                          ]
                            .map((key) => entry.metricRecords[key])
                            .filter(
                              (rec): rec is LedgerMetricRecord => Boolean(rec),
                            )
                            .map((rec) => (
                              <tr key={rec.metricId}>
                                <td>
                                  <strong>
                                    {METRIC_LABELS[rec.metricId] ?? rec.metricId}
                                  </strong>
                                </td>
                                <td>
                                  <code>
                                    {fmtNum(rec.baselineObserved, 4)} {rec.unit}
                                  </code>
                                </td>
                                <td>
                                  <code>
                                    {fmtNum(rec.predictedMean, 4)} ±{" "}
                                    {fmtNum(rec.uncertaintyRadius, 3)}{" "}
                                    {rec.unit}
                                  </code>
                                </td>
                                <td>
                                  <code>
                                    ≤ {fmtNum(rec.conservativeUpperBound, 4)}{" "}
                                    {rec.unit}
                                  </code>
                                </td>
                                <td>
                                  <strong>
                                    {fmtNum(rec.observedValue, 4)} {rec.unit}
                                  </strong>
                                </td>
                                <td>
                                  <code>
                                    {fmtNum(rec.absError, 3)} {rec.unit}
                                  </code>
                                </td>
                                <td>
                                  <span
                                    className={`pt-pill ${
                                      rec.withinConservativeBound
                                        ? "pass"
                                        : "danger"
                                    }`}
                                  >
                                    {rec.withinConservativeBound
                                      ? "包络内命中"
                                      : "越界告警"}
                                  </span>
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Formal Auditable Claims Matrix */}
          <section className="pt-card">
            <div className="pt-card-head">
              <div>
                <h2>Axiom 形式化可审计声明矩阵（R0–R7 治理门禁）</h2>
                <p className="pt-card-sub">
                  每条结论均与输入案例、代理模型、推荐报告及对账台账的 SHA-256 谱系哈希严格绑定。
                </p>
              </div>
              <span className="pt-pill neutral">
                证据包哈希：{activeGovScenario.governance.runBundle.bundleHash.slice(0, 12)}…
              </span>
            </div>

            <div className="pt-claims-grid">
              {activeGovScenario.governance.runBundle.claims
                .filter((claim) => claim.claimDefinitionId in CLAIM_TITLES)
                .map((claim) => (
                  <article className="pt-claim-card" key={claim.claimId}>
                    <div className="pt-finding-head">
                      <strong>
                        {CLAIM_TITLES[claim.claimDefinitionId] ??
                          claim.claimDefinitionId}
                      </strong>
                      <div className="pt-action-badges">
                        <span className={`pt-pill ${claimTone(claim.status)}`}>
                          {CLAIM_STATUS_LABELS[claim.status] ?? claim.status}
                        </span>
                        <span className="pt-pill neutral">
                          {EVIDENCE_LEVEL_LABELS[claim.evidence.level] ??
                            claim.evidence.level}
                        </span>
                      </div>
                    </div>
                    <p>
                      {CLAIM_PREDICATE_LABELS[claim.claimDefinitionId] ??
                        claim.predicate}
                    </p>
                  </article>
                ))}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
