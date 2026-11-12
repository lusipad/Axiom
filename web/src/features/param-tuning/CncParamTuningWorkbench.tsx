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

const FAMILY_LABELS: Record<string, string> = {
  "SINUMERIK 840D sl (CYCLE832 + SINAMICS S120)": "西门子 840D sl · CYCLE832 高精加工 + S120 驱动",
  "TwinCAT 3 NC I + AX5000": "倍福 TwinCAT 3 NC 插补 + AX5000 伺服驱动",
  "32D Spline + FIR/Biquad + P-P Cascade": "32 维样条插补 + FIR/陷波滤波 + 双环级联伺服",
};

const CASE_LABELS: Record<string, string> = {
  "axiom.v1.circle": "整圆精铣基准刀路",
  "axiom.v1.corner90": "90° 直角轮廓刀路",
  "axiom.v1.s-curve": "S 型自由曲面刀路",
};

const ENTRY_LABELS: Record<string, string> = {
  "cut.001.corner90": "第 1 刀复切 · 90° 直角轮廓",
  "cut.002.circle": "第 2 刀复切 · 整圆精铣",
  "cut.003.s-curve": "第 3 刀复切 · S 型自由曲面",
  "drift.001.corner90": "第 1 刀热漂移复切 · 90° 直角轮廓",
  "drift.002.circle": "第 2 刀热漂移复切 · 整圆精铣",
  "drift.003.s-curve": "第 3 刀热漂移复切 · S 型自由曲面",
};

const LEDGER_ID_LABELS: Record<string, string> = {
  "cnc.ledger.r3-verified@1": "真机三刀复切达标台账",
  "cnc.ledger.thermal-drift@1": "导轨热漂移失准告警台账",
};

const RECEIPT_LABELS: Record<string, string> = {
  "rcpt.ok.1": "只读回执 #01",
  "rcpt.ok.2": "只读回执 #02",
  "rcpt.ok.3": "只读回执 #03",
  "rcpt.drift.1": "只读回执 #01（温升偏移）",
  "rcpt.drift.2": "只读回执 #02（温升偏移）",
  "rcpt.drift.3": "只读回执 #03（温升偏移）",
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
  discreteJerkRms: "离散冲击有效值",
  resonanceBandRmsMm: "谐振频带残差有效值",
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
    "采样 XYZ 轨迹满足各轴行程、首尾端点、轮廓公差与离散速度/加速度/跃度硬约束限制。",
  "cnc-greybox.r4-calibration-claim@1":
    "灰盒物理标定模型对独立留出的真机复切样本具备在声明不确定度内的预测精度（缺少真机留出样本时保持「待真机实证」）。",
  "cnc-greybox.r5-epistemic-claim@1":
    "推荐预设落入训练特征安全包络内，且其共形不确定度上界在真机复切样本上达到标称经验覆盖率（缺少真机留出样本时保持「待真机实证」）。",
  "cnc-greybox.r7-zero-write-advisory-claim@1":
    "系统权限严格锁定为离线参数建议（零设备写权限）；设备级安全认证保持未开启状态，由现场工程师人工核验。",
};

const CANONICAL_TARGET_LABELS: Record<string, string> = {
  "g1.corner_tolerance_mm": "G1 拐角平滑公差",
  "g1.chord_error_max_mm": "G1 弦高误差上限",
  "g1.lookahead_horizon_blocks": "G1 前瞻程序段数",
  "g1.min_corner_speed_ratio": "G1 拐角最低速度比",
  "g1.centripetal_acc_limit_mm_s2": "G1 向心加速度上限",
  "g1.bspline_smoothing_weight": "G1 样条平滑权重",
  "g1.micro_segment_merge_mm": "G1 微小段合并阈值",
  "g2.path_tangential_acc_mm_s2": "G2 切向合成加速度",
  "g2.path_tangential_jerk_mm_s3": "G2 切向合成跃度",
  "g2.axis_acc_x_mm_s2": "G2 X 轴最大加速度",
  "g2.axis_acc_y_mm_s2": "G2 Y 轴最大加速度",
  "g2.axis_acc_z_mm_s2": "G2 Z 轴最大加速度",
  "g2.axis_jerk_x_mm_s3": "G2 X 轴最大跃度",
  "g2.axis_jerk_y_mm_s3": "G2 Y 轴最大跃度",
  "g2.axis_jerk_z_mm_s3": "G2 Z 轴最大跃度",
  "g2.fir_moving_avg_time_ms": "G2 FIR 滑动滤波时间",
  "g2.biquad_lowpass_cutoff_hz": "G2 二阶低通截止频率",
  "g2.scurve_bell_shape_ratio": "G2 S 型钟形平滑率",
  "g3.servo_kp_x": "G3 X 轴位置环增益 Kv",
  "g3.servo_kp_y": "G3 Y 轴位置环增益 Kv",
  "g3.servo_kp_z": "G3 Z 轴位置环增益 Kv",
  "g3.velocity_ff_gain_x": "G3 X 轴速度前馈增益",
  "g3.velocity_ff_gain_y": "G3 Y 轴速度前馈增益",
  "g3.acc_ff_gain_x": "G3 X 轴加速度前馈增益",
  "g3.acc_ff_gain_y": "G3 Y 轴加速度前馈增益",
  "g3.notch_filter_freq_hz": "G3 谐振陷波中心频率",
  "g3.notch_filter_bw_hz": "G3 谐振陷波带宽",
  "g3.friction_comp_amp_x": "G3 X 轴过象限摩擦补偿",
  "g3.friction_comp_amp_y": "G3 Y 轴过象限摩擦补偿",
  "g3.friction_comp_decay_ms": "G3 摩擦补偿衰减常数",
};

function localizeTuningCopy(text: string): string {
  return text
    .replace(/[（(]Siemens\s*\/\s*siemens-sinumerik-840d@1[）)]/g, "（西门子 840D sl）")
    .replace(/[（(]Beckhoff\s*\/\s*beckhoff-twincat-nc@1[）)]/g, "（倍福 TwinCAT 3 NC）")
    .replace(
      /[（(]Generic(?:\s+Reference\s+CNC)?\s*\/\s*generic-fir-biquad@1[）)]/g,
      "（通用 32 维标准层）",
    )
    .replace(/案例\s*axiom\.v1\.circle/g, "「整圆精铣」案例")
    .replace(/案例\s*axiom\.v1\.corner90/g, "「90° 直角轮廓」案例")
    .replace(/案例\s*axiom\.v1\.s-curve/g, "「S 型自由曲面」案例")
    .replace(/axiom\.v1\.circle/g, "整圆精铣案例")
    .replace(/axiom\.v1\.corner90/g, "90° 直角轮廓案例")
    .replace(/axiom\.v1\.s-curve/g, "S 型自由曲面案例")
    .replace(
      /quadrantGlitchExcess\s*=\s*([0-9.]+)\s*um/gi,
      "过象限突跳超量 $1 µm",
    )
    .replace(/主导基元：line/g, "主导轨迹段：直线段")
    .replace(/主导基元：arc/g, "主导轨迹段：圆弧段")
    .replace(/主导基元：corner/g, "主导轨迹段：拐角段")
    .replace(/主导基元：spline/g, "主导轨迹段：自由曲线段")
    .replace(/actualPathDeviationMaxMm=/g, "实测伺服轮廓偏差=")
    .replace(/sampledPathDeviationMaxMm=/g, "指令最大轮廓偏差=")
    .replace(/\bcontroller-trace\b/g, "机床试切采集")
    .replace(/\balgorithm-export\b/g, "离线插补预筛")
    .replace(/\bCEI=/g, "期望改进分=")
    .replace(/\bInconclusive\b/g, "待真机实证")
    .replace(/\bSupported\b/g, "已证实")
    .replace(/\bRefuted\b/g, "已证伪")
    .replace(/\bsinc\s*陷波零点/gi, "滑动平均频谱陷波零点")
    .replace(/\bFIR\s*频谱零点对齐/gi, "滑动平均滤波零点对齐")
    .replace(/频带残差\s*RMS\s*=/gi, "频带残差有效值 =")
    .replace(/\bum\b/g, "µm");
}

function localizeFormula(formula: string): string {
  return formula
    .replace(
      /A_fric_new\s*=\s*A_fric_cur\s*\+\s*0\.7\s*\*\s*excess\s*\(([0-9.]+)\s*um\)/gi,
      "建议补偿量 = 当前设定 + 0.7 × 过象限突跳超量 ($1 µm)",
    )
    .replace(
      /T_fir\s*=\s*k\s*\/\s*f_res\s*\(f_res\s*=\s*([0-9.]+)\s*Hz\)/gi,
      "滑动滤波时间 = 零点阶数 k / 实测谐振频率 ($1 Hz)",
    )
    .replace(
      /f_notch\s*=\s*f_res\s*=\s*([0-9.]+)\s*Hz/gi,
      "陷波中心频率 = 实测谐振主频 ($1 Hz)",
    )
    .replace(
      /eps_new\s*~=\s*0\.85\s*\*\s*\(([^)]+)\)\s*\*\s*eps_cur/gi,
      "建议平滑公差 ≈ 0.85 × ($1) × 当前公差",
    )
    .replace(
      /dR_fir\s*~=\s*\(v\^2\s*\/\s*R\)\s*\*\s*T_fir\^2\s*\/\s*24/gi,
      "圆弧滤波内缩量 ΔR ≈ (进给速度² / 半径 R) × 滤波窗口² / 24",
    )
    .replace(
      /t_ramp\s*=\s*dV\s*\/\s*a_t/gi,
      "加减速斜坡耗时 = 速度阶跃量 ΔV / 切向加速度",
    )
    .replace(/~=/g, "≈")
    .replace(/\s*\*\s*/g, " × ")
    .replace(/\bum\b/g, "µm");
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
      {/* Unified Modern Sticky App Header */}
      <header className="pt-topbar">
        <div className="pt-topbar-left">
          <div className="pt-title-group">
            <h1>现场调参与单刀快诊</h1>
            <span className="pt-safety-pill">
              <i className="pt-safety-dot" />
              离线只读 · 零写权限
            </span>
          </div>
          <p className="pt-topbar-sub">
            切 1 刀白盒机理快诊 → 多保真三档推荐 → 复切遥测逐刀对账与门禁晋升
          </p>
        </div>

        {/* Center Segmented Workflow Switcher */}
        <div
          className="pt-segmented-tabs"
          role="tablist"
          aria-label="调参三阶段流程"
        >
          <button
            type="button"
            role="tab"
            className="pt-seg-tab"
            aria-selected={stage === "diagnose"}
            onClick={() => setStage("diagnose")}
          >
            <span className="pt-seg-num">01</span>
            <span>单刀快诊顾问</span>
          </button>

          <button
            type="button"
            role="tab"
            className="pt-seg-tab"
            aria-selected={stage === "surrogate"}
            onClick={() => setStage("surrogate")}
          >
            <span className="pt-seg-num">02</span>
            <span>多保真敏感度与三档推荐</span>
          </button>

          <button
            type="button"
            role="tab"
            className="pt-seg-tab"
            aria-selected={stage === "ledger"}
            onClick={() => setStage("ledger")}
          >
            <span className="pt-seg-num">03</span>
            <span>预测-实测对账与真机门禁</span>
          </button>
        </div>

        <div className="pt-topbar-actions">
          {onOpenBenchmark && (
            <button
              type="button"
              className="button button-secondary pt-btn-compact"
              onClick={onOpenBenchmark}
            >
              ← 算法 A/B 对比
            </button>
          )}
          {onOpenGuide && (
            <button
              type="button"
              className="button button-secondary pt-btn-compact"
              onClick={onOpenGuide}
            >
              使用引导
            </button>
          )}
        </div>
      </header>

      <div className="pt-workspace-shell">
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

        {/* Compact Single-Line Studio Control Bar: Controller System + Permission Lock + Mapping Trigger */}
        <section
          className="pt-control-bar"
          aria-label="目标数控系统与权限设置"
        >
          <div className="pt-vendor-group">
            <span className="pt-bar-label">数控系统</span>
            <div className="pt-vendor-pills">
              {(bundle?.controllerProfiles ?? []).map((prof) => {
                const isSelected = prof.profileId === activeProfile?.profileId;
                const label =
                  PROFILE_LABELS[prof.profileId] ??
                  `${prof.vendorName} · ${prof.controllerFamily}`;
                return (
                  <button
                    key={prof.profileId}
                    type="button"
                    className={`pt-vendor-pill ${isSelected ? "active" : ""}`}
                    aria-pressed={isSelected}
                    title={
                      FAMILY_LABELS[prof.controllerFamily] ??
                      prof.controllerFamily
                    }
                    onClick={() => {
                      setSelectedProfileId(prof.profileId);
                      setCustomReport(null);
                    }}
                  >
                    <span className="pt-vendor-name">{label}</span>
                    <span className="pt-profile-dim">
                      {prof.registry.parameters.length} 维参数
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="pt-permission-group">
            <label className={`pt-switch-pill ${ncOnly ? "checked" : ""}`}>
              <input
                type="checkbox"
                checked={ncOnly}
                onChange={(e) => {
                  setNcOnly(e.target.checked);
                  setCustomReport(null);
                }}
              />
              <span className="pt-switch-track" aria-hidden="true">
                <i className="pt-switch-thumb" />
              </span>
              <span className="pt-switch-label">
                仅调 NC 规划参数（锁死伺服驱动器）
              </span>
            </label>

            <button
              type="button"
              className="button button-secondary pt-btn-compact"
              aria-expanded={showMappingDrawer}
              onClick={() => setShowMappingDrawer((prev) => !prev)}
            >
              {showMappingDrawer
                ? "收起厂商参数映射表"
                : `查看厂商参数映射表 (${activeProfile?.registry.parameters.length ?? 0} 项)`}
            </button>
          </div>
        </section>

        {/* Collapsible / Elevated Parameter Mapping Sheet */}
        {showMappingDrawer && activeProfile && (
          <section className="pt-mapping-sheet" aria-label="厂商参数映射表">
            <div className="pt-mapping-head">
              <div>
                <strong>
                  {PROFILE_LABELS[activeProfile.profileId] ??
                    activeProfile.vendorName}{" "}
                  ↔ Axiom 标准运动学内核映射表
                </strong>
                <span className="pt-mapping-sub">
                  {FAMILY_LABELS[activeProfile.controllerFamily] ??
                    activeProfile.controllerFamily}{" "}
                  · 档案标识 {activeProfile.profileContentHash.slice(0, 10)}
                </span>
              </div>
              <button
                type="button"
                className="button button-secondary pt-btn-compact"
                onClick={() => setShowMappingDrawer(false)}
              >
                关闭映射表
              </button>
            </div>
            <div className="pt-table-scroll">
              <table className="pt-table">
                <thead>
                  <tr>
                    <th>现场参数名称</th>
                    <th>厂商参数代码</th>
                    <th>功能分层</th>
                    <th>默认与安全范围</th>
                    <th>标准内核映射关系</th>
                    <th>调参权限分级</th>
                  </tr>
                </thead>
                <tbody>
                  {activeProfile.registry.parameters.map((param) => {
                    const bind = bindingByParamId.get(param.parameterId);
                    const tuneMeta = bind
                      ? TUNABILITY_META[bind.tunability]
                      : TUNABILITY_META["nc-tunable"];
                    const targetText =
                      (bind?.canonicalTargets ?? [])
                        .map((t) => `${CANONICAL_TARGET_LABELS[t] ?? t} (${t})`)
                        .join("、") || "—";
                    return (
                      <tr key={param.parameterId}>
                        <td>
                          <strong>{param.displayName}</strong>
                        </td>
                        <td>
                          <code>{param.parameterId}</code>
                        </td>
                        <td>{GROUP_LABELS[param.group] ?? param.group}</td>
                        <td>
                          <code>
                            {param.defaultValue} [{param.bounds[0]} ~{" "}
                            {param.bounds[1]}] {param.unit}
                          </code>
                        </td>
                        <td>
                          <span className="pt-target-cell">{targetText}</span>{" "}
                          <code>
                            (
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
          </section>
        )}

        {loading && (
          <div className="pt-empty-box">正在加载跨数控系统现场调参工作台数据…</div>
        )}

        {/* =================================================================
            STAGE 01: SINGLE-CUT DIAGNOSTIC ADVISOR (ABOVE-THE-FOLD STUDIO)
           ================================================================= */}
        {!loading && stage === "diagnose" && (
          <>
            {/* Compact 1-Line Scenario Selector Bar */}
            <section className="pt-scenario-bar" aria-label="现场试切问题场景">
              <span className="pt-bar-label">典型工况</span>
              <div className="pt-scenario-pills">
                {(bundle?.diagnosticScenarios ?? []).map((sc) => {
                  const active =
                    !customMode && sc.scenarioId === activeScenario?.scenarioId;
                  return (
                    <button
                      key={sc.scenarioId}
                      type="button"
                      className={`pt-scenario-pill ${active ? "active" : ""}`}
                      onClick={() => {
                        setCustomMode(false);
                        setSelectedScenarioId(sc.scenarioId);
                      }}
                    >
                      <span className={`pt-scenario-dot ${sc.badgeTone}`} />
                      <span className="pt-scenario-pill-title">{sc.title}</span>
                      <span className="pt-scenario-pill-mag">
                        ×{sc.preview.magnification}
                      </span>
                    </button>
                  );
                })}

                <button
                  type="button"
                  className={`pt-scenario-pill ${customMode ? "active" : ""}`}
                  onClick={() => setCustomMode(true)}
                >
                  <span className="pt-scenario-dot info" />
                  <span className="pt-scenario-pill-title">
                    + 导入自有单刀数据快诊
                  </span>
                </button>
              </div>
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
                      : "① 选择刀路约束文件 (.json)"}
                  </button>
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={() => exportInputRef.current?.click()}
                  >
                    {customExportName
                      ? `已选轨迹：${customExportName}`
                      : "② 选择单刀采样轨迹 (.json)"}
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

            {/* Studio Split Workspace: Left Contour & Findings | Right Priority Prescription Cards */}
            <div className="pt-diag-grid">
              {/* Left Column: Ballbar Contour Studio + Compact Confidence + Mechanism Findings */}
              <div className="pt-diag-left-col">
                <section className="pt-card pt-chart-studio-card">
                  <div className="pt-card-head">
                    <div>
                      <div className="pt-card-title-row">
                        <h2>
                          {customMode
                            ? "导入刀路与采样轨迹 XY 投影"
                            : "球杆仪级法向误差放大轮廓图"}
                        </h2>
                        {!customMode && activeScenario && (
                          <span className="pt-pill warning">
                            法向误差 ×{activeScenario.preview.magnification}
                          </span>
                        )}
                      </div>
                      <p className="pt-card-sub">
                        {customMode
                          ? "叠加对比参考路径与采样轨迹坐标"
                          : `${activeScenario?.subtitle ?? ""} · 微米级偏差放大 ${activeScenario?.preview.magnification ?? 50} 倍直观定位`}
                      </p>
                    </div>

                    <div className="pt-chart-legend">
                      <span>
                        <i className="pt-legend-dot ref" /> 参考刀路
                      </span>
                      <span>
                        <i className="pt-legend-dot cmd" /> NC 插补指令
                      </span>
                      {!customMode && (
                        <span>
                          <i className="pt-legend-dot act" /> 实测伺服轨迹
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="pt-chart-canvas">
                    <XYChart
                      series={contourSeries}
                      ariaLabel="参考刀路、插补指令与误差放大实测轮廓对比"
                      xLabel="X (mm)"
                      yLabel="Y (mm)"
                      height={268}
                      legend={false}
                    />
                  </div>

                  {activeDiagnosticReport && (
                    <div className="pt-epistemic-strip">
                      <div className="pt-epistemic-badge-row">
                        <div className="pt-epistemic-chip">
                          <span className="pt-epistemic-label">
                            节拍与滤波零点
                          </span>
                          <span
                            className={`pt-pill ${
                              CONFIDENCE_META[
                                activeDiagnosticReport.cycleTimeConfidence
                              ]?.tone ?? "pass"
                            }`}
                          >
                            {CONFIDENCE_SHORT[
                              activeDiagnosticReport.cycleTimeConfidence
                            ] ?? activeDiagnosticReport.cycleTimeConfidence}{" "}
                            · 白盒确定性公式
                          </span>
                        </div>
                        <div className="pt-epistemic-chip">
                          <span className="pt-epistemic-label">
                            轮廓误差幅值
                          </span>
                          <span
                            className={`pt-pill ${
                              CONFIDENCE_META[
                                activeDiagnosticReport.contourErrorConfidence
                              ]?.tone ?? "warning"
                            }`}
                          >
                            {CONFIDENCE_SHORT[
                              activeDiagnosticReport.contourErrorConfidence
                            ] ?? activeDiagnosticReport.contourErrorConfidence}{" "}
                            · 仅作方向参考
                          </span>
                        </div>
                      </div>
                      <p className="pt-epistemic-note">
                        {localizeTuningCopy(
                          activeDiagnosticReport.confidenceStatement,
                        )}
                      </p>
                    </div>
                  )}
                </section>

                {/* Detailed Mechanism Findings under the Chart */}
                {activeDiagnosticReport && (
                  <section className="pt-card">
                    <div className="pt-card-head">
                      <div>
                        <h3>
                          诊断识别的工艺机理瓶颈（
                          {activeDiagnosticReport.findings.length} 项）
                        </h3>
                        <p className="pt-card-sub">
                          自动解耦几何拐角、插补滤波与伺服驱动三层误差来源
                        </p>
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
                              <strong>
                                {localizeTuningCopy(finding.symptom)}
                              </strong>
                              <div className="pt-action-badges">
                                <span className={`pt-pill ${sevTone}`}>
                                  {SEVERITY_LABELS[finding.severity] ??
                                    finding.severity}
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
                  </section>
                )}
              </div>

              {/* Right Column: Priority Prescription Cards (<= 2) */}
              <section className="pt-card pt-rx-panel">
                {!activeDiagnosticReport ? (
                  <div className="pt-empty-box">
                    请先上传刀路约束文件与单刀采样轨迹文件，点击「执行单刀机理快诊」生成厂商原生调参建议。
                  </div>
                ) : (
                  <>
                    <div className="pt-card-head">
                      <div>
                        <div className="pt-card-title-row">
                          <h2>优先单刀调参方案（上限 2 项）</h2>
                          <span className="pt-pill pass">
                            单次微调 ≤ 2 项以隔离因果
                          </span>
                        </div>
                        <p className="pt-card-sub">
                          {localizeTuningCopy(
                            activeDiagnosticReport.summaryHeadline,
                          )}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="button button-secondary pt-btn-compact"
                        onClick={() =>
                          downloadJson(
                            activeDiagnosticReport,
                            `${activeDiagnosticReport.caseId}-${activeDiagnosticReport.controllerProfileId}-diagnostic.json`,
                          )
                        }
                      >
                        导出调参单 JSON
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
                                <div className="pt-action-title-group">
                                  <span className="pt-rank-badge">
                                    方案 #{idx + 1}
                                  </span>
                                  <h4>{act.displayName}</h4>
                                </div>
                                <div className="pt-action-badges">
                                  <span className={`pt-pill ${tune.tone}`}>
                                    {tune.label}
                                  </span>
                                  <span className={`pt-pill ${conf.tone}`}>
                                    {conf.label}
                                  </span>
                                </div>
                              </div>

                              <div className="pt-param-id-row">
                                <span>控制器参数标识：</span>
                                <code>{act.parameterId}</code>
                              </div>

                              <div className="pt-value-transition">
                                <div className="pt-val-box">
                                  <span>当前机床设定</span>
                                  <strong>
                                    {fmtNum(act.currentValue, 4)} {act.unit}
                                  </strong>
                                </div>
                                <span
                                  className="pt-val-arrow"
                                  aria-hidden="true"
                                >
                                  →
                                </span>
                                <div className="pt-val-box target">
                                  <span>建议试切设定</span>
                                  <strong>
                                    {fmtNum(act.suggestedValue, 4)} {act.unit}
                                  </strong>
                                </div>
                                <span className="pt-val-delta">
                                  调整量 {fmtSigned(act.delta, act.unit)}
                                </span>
                              </div>

                              <div className="pt-action-meta">
                                <div className="pt-meta-row">
                                  <span className="pt-meta-tag pass">
                                    预期改善
                                  </span>
                                  <span>
                                    {localizeTuningCopy(act.expectedEffect)}
                                  </span>
                                </div>
                                <div className="pt-meta-row">
                                  <span className="pt-meta-tag info">
                                    复切核验
                                  </span>
                                  <span>
                                    {localizeTuningCopy(act.verificationNote)}
                                  </span>
                                </div>
                                <div className="pt-formula-line">
                                  <span className="pt-formula-label">
                                    物理依据：
                                  </span>
                                  <span>
                                    {localizeFormula(act.mechanismFormula)}
                                  </span>
                                </div>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    )}
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
          <section className="pt-card">
            <div className="pt-card-head">
              <div>
                <h2>多保真灰盒代理建模与帕累托三档推荐</h2>
                <p className="pt-card-sub">
                  融合白盒运动学/频域先验 + 稀疏残差学习：自动筛除不敏感参数，并在共形不确定度安全包络内求解三档参数包。
                </p>
              </div>
              <div className="pt-custom-files">
                <button
                  type="button"
                  className="button button-secondary pt-btn-compact"
                  disabled={surrogateBusy}
                  onClick={() => void loadSurrogateDemo()}
                >
                  {surrogateBusy ? "正在更新灰盒模型…" : "重新运行多保真灰盒建模"}
                </button>
                {closedLoop && (
                  <button
                    type="button"
                    className="button button-primary pt-btn-compact"
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
                    <span>低成本离线预筛样本</span>
                    <strong>{closedLoop.surrogate.offlineRunCount} 组</strong>
                    <small>快速探索规划与滤波几何边界</small>
                  </div>
                  <div className="pt-kpi-card">
                    <span>机床级高保真样本</span>
                    <strong>
                      {closedLoop.surrogate.controllerRunCount} 组
                    </strong>
                    <small>锚定伺服跟随与换向摩擦残差</small>
                  </div>
                  <div className="pt-kpi-card">
                    <span>自动识别关键敏感参数</span>
                    <strong>
                      {closedLoop.surrogate.globalActiveParameterIds.length} 项
                    </strong>
                    <small>从高维参数空间自动剥离冗余项</small>
                  </div>
                  <div className="pt-kpi-card">
                    <span>安全包络内可行 / 帕累托解</span>
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

                <div className="pt-card-head" style={{ marginTop: 4 }}>
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
                        <div className="pt-preset-inner">
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

                <div className="pt-card-head" style={{ marginTop: 6 }}>
                  <div>
                    <h3>关键加工指标敏感度分解与留一交叉验证精度</h3>
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
                              拟合度 R² ={" "}
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
                              Math.max(
                                4,
                                Math.round(sens.contributionRatio * 100),
                              ),
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
                                      (
                                      {DIRECTION_LABELS[sens.direction] ??
                                        sens.direction}
                                      )
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
                    <div className="pt-card-head" style={{ marginTop: 6 }}>
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
                    className={`pt-gov-card ${active ? "active" : ""}`}
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
                        {govItem.ledger?.summary.distinctRealR3TraceCount ?? 0}{" "}
                        / 3 刀
                      </span>
                    </div>
                    <strong>{localizeTuningCopy(govItem.title)}</strong>
                    <p>{localizeTuningCopy(govItem.subtitle)}</p>
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
                    "实证晋升通过：直角、整圆、S 曲线 3 刀独立 R3 机床只读遥测全部完成预测-实测对账，周期误差 1.43%（≤ 8%）、轮廓均方根误差 7.6 µm（≤ 15 µm）、保守上界覆盖率 88.9%（≥ 80%），R4/R5 自动晋升为「已证实」。"}
                  {activeGovScenario.stateId === "drift-refuted" &&
                    "失准熔断告警：现场导轨温升引发 +0.085 mm 热漂移，切后实测轮廓误差突破 95% 保守上界（轮廓均方根误差 68.1 µm > 15 µm 门限，覆盖率跌至 66.7%），R4/R5 自动降级为「已证伪」，提示重新采集基准刀标定。"}
                </p>
              </div>
              <button
                type="button"
                className="button button-secondary pt-btn-compact"
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
                <span>运动周期预测误差</span>
                <strong>
                  {activeGovScenario.ledger
                    ? `${fmtNum(activeGovScenario.ledger.summary.durationMapePct, 3)}%`
                    : "待复切"}
                </strong>
                <small>晋升硬门限 ≤ 8.0%</small>
              </div>
              <div className="pt-kpi-card">
                <span>实测轮廓预测均方根误差</span>
                <strong>
                  {activeGovScenario.ledger?.summary.actualDeviationRmseMm !=
                  null
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
                    {LEDGER_ID_LABELS[activeGovScenario.ledger.ledgerId] ??
                      activeGovScenario.ledger.ledgerId}
                  </span>
                )}
              </div>

              {!activeGovScenario.ledger ? (
                <div className="pt-empty-box">
                  当前处于「阶段 A · 仅离线/合成建模」，尚无真机复切记录入账。可点击上方「阶段
                  B · 满 3 刀独立 R3 真机复切对账达标」查看完整逐刀对账表。
                </div>
              ) : (
                <div className="pt-findings-list">
                  {activeGovScenario.ledger.entries.map((entry) => (
                    <div className="pt-ledger-cut" key={entry.entryId}>
                      <div className="pt-ledger-cut-head">
                        <div className="pt-action-badges">
                          <strong>
                            {ENTRY_LABELS[entry.entryId] ?? entry.entryId}
                          </strong>
                          <span className="pt-pill info">
                            {CASE_LABELS[entry.caseId] ?? entry.caseId}
                          </span>
                          {entry.r3DeviceId && (
                            <span className="pt-pill neutral">
                              设备：{entry.r3DeviceId} ·{" "}
                              {entry.r3ReceiptId
                                ? (RECEIPT_LABELS[entry.r3ReceiptId] ??
                                  entry.r3ReceiptId)
                                : "只读回执"}
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
                                      {METRIC_LABELS[rec.metricId] ??
                                        rec.metricId}
                                    </strong>
                                  </td>
                                  <td>
                                    <code>
                                      {fmtNum(rec.baselineObserved, 4)}{" "}
                                      {rec.unit}
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
                  <h2>形式化可审计声明矩阵（R0–R7 治理门禁）</h2>
                  <p className="pt-card-sub">
                    每条结论均与输入案例、代理模型、推荐报告及对账台账的加密谱系指纹严格绑定。
                  </p>
                </div>
                <span className="pt-pill neutral">
                  证据包指纹：
                  {activeGovScenario.governance.runBundle.bundleHash.slice(
                    0,
                    12,
                  )}
                  …
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
                          <span
                            className={`pt-pill ${claimTone(claim.status)}`}
                          >
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
      </div>
    </main>
  );
}
