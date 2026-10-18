import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { CncBenchmarkWorkbench } from "./features/benchmark/CncBenchmarkWorkbench";
import { XYChart } from "./charts";
import type { ChartSeries } from "./charts";
import { LabIntro } from "./guide/LabIntro";
import { PipelineMap } from "./guide/PipelineMap";
import { PipelineView } from "./guide/PipelineView";
import { WelcomeOverlay } from "./guide/WelcomeOverlay";
import { Sidebar } from "./components/Sidebar";
import type { NavItem } from "./components/Sidebar";
import { GlobalFooter } from "./components/GlobalFooter";
import "./guide/styles.css";

import {
  executeExperiment,
  loadCatalog,
  loadContourExample,
} from "./api";
import { ControlR7Workbench } from "./features/control-r7/ControlR7Workbench";
import { ControlR7BWorkbench } from "./features/control-r7b/ControlR7BWorkbench";
import { ControlR7CWorkbench } from "./features/control-r7c/ControlR7CWorkbench";
import { ControlR7DWorkbench } from "./features/control-r7d/ControlR7DWorkbench";
import { FieldEvidenceWorkbench } from "./features/field-evidence/FieldEvidenceWorkbench";
import { F1Workbench } from "./features/five-axis-f1/F1Workbench";
import { F2Workbench } from "./features/five-axis-f2/F2Workbench";
import { F3Workbench } from "./features/five-axis-f3/F3Workbench";
import { F4Workbench } from "./features/five-axis-f4/F4Workbench";
import { IntelligenceR5BWorkbench } from "./features/intelligence-r5b/IntelligenceR5BWorkbench";
import { IntelligenceR5Workbench } from "./features/intelligence-r5/IntelligenceR5Workbench";
import { MachineR3Workbench } from "./features/machine-r3/MachineR3Workbench";
import { OptimizationR6Workbench } from "./features/optimization-r6/OptimizationR6Workbench";
import { PhysicalR4Workbench } from "./features/physical-r4/PhysicalR4Workbench";
import type {
  Catalog,
  ExperimentArmResult,
  ExperimentReport,
  ExperimentSpec,
  MetricComparison,
  Point,
} from "./types";

type Lab = NavItem;
type PointView = "geometry" | "metrics";

interface LabMeta {
  title: string;
  manifest: string;
  boundary: string;
}

const LAB_META: Record<Lab, LabMeta> = {
  benchmark: { title: "CNC 算法对比", manifest: "XYZ · 采样命令评估", boundary: "同一案例 · 两个算法版本" },
  pipeline: { title: "验证路径", manifest: "validation-pipeline@2", boundary: "8-STAGE PIPELINE · AUDITABLE STATEMENTS" },
  point: { title: "Experiment Workbench", manifest: "", boundary: "" },
  "five-axis-f1": { title: "Five-Axis Geometry Reference Workbench", manifest: "five-axis.f1-math-stage-manifest@1", boundary: "MATH ONLY · NOT DEVICE SAFE" },
  "five-axis-f2": { title: "Five-Axis Kinematics Reference Workbench", manifest: "five-axis.f2-math-stage-manifest@1", boundary: "MATH ONLY · NOT DEVICE SAFE" },
  "five-axis-f3": { title: "Five-Axis Time & Sampling Lab", manifest: "five-axis.f3-math-stage-manifest@1", boundary: "MATH ONLY · NOT DEVICE SAFE" },
  "five-axis-f4": { title: "Five-Axis Gate Acceptance Lab", manifest: "five-axis.f4-math-stage-manifest@1", boundary: "MATH ONLY · NOT DEVICE SAFE" },
  "machine-r3": { title: "Machine Read-only Lab", manifest: "machine.r3-manifest@1", boundary: "READ ONLY · NOT DEVICE SAFE" },
  "physical-r4": { title: "Physical R4 Validation Workbench", manifest: "physical.r4-manifest@1", boundary: "MODEL VALIDATION · NOT DEVICE SAFE" },
  "intelligence-r5": { title: "Intelligence R5 Evidence Lab", manifest: "intelligence.r5-manifest@1", boundary: "SYNTHETIC LEARNING · REAL GENERALIZATION OPEN · NOT DEVICE SAFE" },
  "intelligence-r5b": { title: "Intelligence R5-B Reality Gate", manifest: "intelligence.r5b-manifest@1", boundary: "REAL HOLDOUT VALIDATION · REAL GENERALIZATION OPEN · NOT DEVICE SAFE" },
  "optimization-r6": { title: "Optimization R6 Recommendation Lab", manifest: "optimization.r6-manifest@1", boundary: "OFFLINE RECOMMENDATION · NO DEVICE WRITE · REALITY OPEN" },
  "control-r7": { title: "Controlled Runtime R7-A", manifest: "control.r7-manifest@1", boundary: "SHADOW ONLY · NO DEVICE AUTHORITY · DEPLOYMENT OPEN" },
  "control-r7b": { title: "Deployment Shadow Readiness R7-B", manifest: "control.r7b-manifest@1", boundary: "READINESS ONLY · VENDOR UNSELECTED · NO DEVICE WRITE · REALITY OPEN" },
  "control-r7c": { title: "Windows OPC UA Transport R7-C", manifest: "control.r7c-manifest@1", boundary: "VIRTUAL OPC UA ONLY · ZERO WRITE · VENDOR OPEN · REALITY OPEN" },
  "control-r7d": { title: "Beckhoff TwinCAT Vendor Gate R7-D", manifest: "control.r7d-manifest@1", boundary: "BECKHOFF PROFILE · READ ONLY · VENDOR GATE · REALITY OPEN" },
  "field-evidence": { title: "Beckhoff Field Evidence R7-E / R4.1", manifest: "control.r7e-manifest@1 + physical.r4.1-manifest@1", boundary: "FIELD EVIDENCE · ZERO WRITE · REALITY OPEN · NOT DEVICE SAFE" },
};

interface LabEntry {
  id: Lab;
  index: string;
  name: string;
  tag?: string;
  desc: string;
}

const LAB_GROUPS: Array<{ id: string; label: string; labs: LabEntry[] }> = [
  {
    id: "foundation",
    label: "基础",
    labs: [{ id: "point", index: "01", name: "Point Lab", tag: "点序列实验", desc: "同一输入跑两版算法，严格比较指标与证据" }],
  },
  {
    id: "five-axis",
    label: "五轴",
    labs: [
      { id: "five-axis-f1", index: "02", name: "Five-Axis", tag: "F1 几何", desc: "路径分段与碰撞包围盒的数学校验" },
      { id: "five-axis-f2", index: "03", name: "Five-Axis", tag: "F2 运动学", desc: "关节坐标随路径进度 σ 的连续曲线" },
      { id: "five-axis-f3", index: "04", name: "Five-Axis", tag: "F3 时间", desc: "σ(t) 时间分段与采样重建记录" },
      { id: "five-axis-f4", index: "05", name: "Five-Axis", tag: "F4 验收", desc: "门槛指标的通过判定与封存证据" },
    ],
  },
  {
    id: "physical",
    label: "机床与物理",
    labs: [
      { id: "machine-r3", index: "06", name: "Machine", tag: "R3 画像", desc: "机床结构与轴参数，只读" },
      { id: "physical-r4", index: "07", name: "Physical", tag: "R4 验证", desc: "指令 / 仿真 / 实测信号对比" },
    ],
  },
  {
    id: "intelligence",
    label: "智能",
    labs: [
      { id: "intelligence-r5", index: "08", name: "Intelligence", tag: "R5-A 合成", desc: "合成数据学习的证据评估" },
      { id: "intelligence-r5b", index: "09", name: "Intelligence", tag: "R5-B 真实门", desc: "真实留出集上的泛化判定" },
    ],
  },
  {
    id: "optimization",
    label: "优化",
    labs: [{ id: "optimization-r6", index: "10", name: "Optimization", tag: "R6 推荐", desc: "离线参数推荐，不写设备" }],
  },
  {
    id: "control",
    label: "控制",
    labs: [
      { id: "control-r7", index: "11", name: "Controlled", tag: "R7-A 运行", desc: "影子模式受控运行，无设备权限" },
      { id: "control-r7b", index: "12", name: "Deployment", tag: "R7-B 就绪", desc: "部署影子就绪评估，未定厂商" },
      { id: "control-r7c", index: "13", name: "OPC UA", tag: "R7-C 传输", desc: "Windows OPC UA 虚拟传输验证" },
      { id: "control-r7d", index: "14", name: "Beckhoff", tag: "R7-D 厂商门", desc: "TwinCAT 厂商准入评估，只读" },
    ],
  },
  {
    id: "field",
    label: "现场",
    labs: [{ id: "field-evidence", index: "15", name: "Field Evidence", tag: "R7-E 现场", desc: "Beckhoff 现场证据评估，只读采集" }],
  },
];

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

function isOrderedPointArtifact(value: unknown): value is { points: Point[] } {
  return Boolean(
    value &&
    typeof value === "object" &&
    "artifactType" in value &&
    (value as { artifactType?: string }).artifactType === "ordered-point-sequence" &&
    Array.isArray((value as { points?: unknown }).points),
  );
}

function buildChartSeries(spec: ExperimentSpec, report: ExperimentReport | null): ChartSeries[] {
  const sources = [
    { key: "reference", label: "共享输入", tone: "reference" as const, dashed: true, points: spec.sharedInput.points },
    ...(report?.armResults ?? []).flatMap((arm, index) => {
      const artifact = arm.runBundle?.observation?.artifact;
      return isOrderedPointArtifact(artifact)
        ? [{
            key: arm.armId,
            label: arm.armId,
            tone: index === 0 ? "baseline" as const : "candidate" as const,
            dashed: false,
            points: artifact.points,
          }]
        : [];
    }),
  ];
  return sources.map((source) => ({
    id: source.key,
    label: source.label,
    tone: source.tone,
    dashed: source.dashed,
    points: source.points.map((point) => [point[0] ?? 0, point[1] ?? 0] as [number, number]),
  }));
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
  const [activeLab, setActiveLab] = useState<Lab>("benchmark");
  const [showLegacy, setShowLegacy] = useState(false);
  const needsLegacy = activeLab !== "benchmark" && activeLab !== "pipeline";
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [spec, setSpec] = useState<ExperimentSpec | null>(null);
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const [pointsText, setPointsText] = useState("[]");
  const [errorVector, setErrorVector] = useState("0, 0.08");
  const [gain, setGain] = useState("0.75");
  const [threshold, setThreshold] = useState("0.03");
  const [pointView, setPointView] = useState<PointView>("geometry");
  const [loading, setLoading] = useState(true);
  const [pointBusy, setPointBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPipeline, setShowPipeline] = useState(false);
  const [showWelcome, setShowWelcome] = useState(false);
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
    if (!needsLegacy) return;
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
    return () => {
      active = false;
    };
  }, [needsLegacy]);

  const pointSeries = useMemo(() => (spec ? buildChartSeries(spec, report) : []), [spec, report]);
  const baseline = report?.armResults[0];
  const candidate = report?.armResults[1];
  const compatible = report?.comparison?.compatibility.compatible;
  const pointUnit = spec?.sharedInput.semantics?.unit ?? "coordinate-unit";
  const pointDimension = spec?.sharedInput.points[0]?.length ?? 0;
  const pointRunnerLabel = [...new Set(spec?.arms.map((arm) => arm.runnerId ?? "unknown-runner") ?? [])].join(", ");
  const pointBusyState = loading || pointBusy;
  const visibleError = (activeLab === "benchmark" || activeLab === "pipeline") ? null : error;
  const labMeta = LAB_META[activeLab] ?? LAB_META.benchmark;
  const workbenchTitle = labMeta.title;

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

  return (
    <div className="axiom-app-layout">
      {/* Left Navigation Sidebar */}
      <Sidebar
        active={activeLab}
        onSelect={(lab) => {
          setActiveLab(lab);
          setShowLegacy(false);
        }}
      />

      {/* Main Content Area */}
      <div className="axiom-main-area">
        {/* Error banner if visible */}
        {visibleError && (
          <div className="error-banner" role="alert">
            <strong>未完成</strong>
            <span>{visibleError}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              aria-label="关闭错误"
            >
              ×
            </button>
          </div>
        )}

        {/* Legacy Drawer Toggle Button for backward test compatibility */}
        <div className="legacy-drawer-bar">
          <button
            type="button"
            className="legacy-drawer-toggle"
            aria-expanded={showLegacy}
            onClick={() => setShowLegacy((v) => !v)}
          >
            参考与实验功能
          </button>
          <button
            type="button"
            className="legacy-drawer-toggle"
            onClick={() => setShowPipeline(true)}
          >
            实验路径
          </button>
        </div>

        {/* Legacy Lab Switcher dropdown when opened */}
        {showLegacy && (
          <div className="lab-switcher" aria-label="领域实验室">
            {LAB_GROUPS.map((group) => (
              <section className="lab-group" key={group.id}>
                <h3 className="lab-group-label">{group.label}</h3>
                <div className="lab-group-cards">
                  {group.labs.map((lab) => (
                    <button
                      key={lab.id}
                      className={`lab ${activeLab === lab.id ? "active" : ""}`}
                      type="button"
                      onClick={() => setActiveLab(lab.id)}
                    >
                      <span className="lab-head">
                        <span className="lab-index">{lab.index}</span>
                        <span className="lab-name">{lab.name}</span>
                        {lab.tag && <small>{lab.tag}</small>}
                      </span>
                      <span className="lab-desc">{lab.desc}</span>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}

        {activeLab !== "benchmark" && activeLab !== "pipeline" && activeLab !== "five-axis-f1" && (
          <LabIntro lab={activeLab} onOpenPipeline={() => setShowPipeline(true)} />
        )}

        {/* Top Header for non-custom pages */}
        {activeLab !== "benchmark" && activeLab !== "pipeline" && activeLab !== "five-axis-f1" && (
          <header className="page-header">
            <div className="page-header-info">
              <h1>{workbenchTitle}</h1>
              <p className="page-header-subtitle">
                {labMeta.manifest} · {labMeta.boundary}
              </p>
            </div>
            <div className="page-header-actions">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setShowWelcome(true)}
              >
                使用引导
              </button>
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
                <span className="boundary-badge">{labMeta.boundary}</span>
              )}
            </div>
          </header>
        )}

        {/* Main View Router */}
        {activeLab === "benchmark" ? (
          <CncBenchmarkWorkbench onOpenGuide={() => setShowWelcome(true)} />
        ) : activeLab === "pipeline" ? (
          <PipelineView
            onSelect={(lab) => {
              setActiveLab(lab);
              setShowLegacy(false);
            }}
            onOpenGuide={() => setShowWelcome(true)}
          />
        ) : activeLab === "five-axis-f1" ? (
          <F1Workbench
            catalog={catalog}
            onNavigate={(lab) => {
              setActiveLab(lab);
              setShowLegacy(false);
            }}
          />
        ) : activeLab === "point" ? (
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
                    <code>
                      {spec?.sharedInput.semantics?.coordinateFrame ?? "unknown frame"} · XY
                      {pointDimension > 2 ? ` projection of ${pointDimension}D` : ""} · {pointUnit}
                    </code>
                  </div>
                  <div className="plot-stage">
                    <XYChart
                      series={pointSeries}
                      ariaLabel="共享输入与两个 Subject 输出的轨迹比较"
                      xLabel="X"
                      yLabel="Y"
                      height={380}
                    />
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
        ) : activeLab === "five-axis-f2" ? (
          <F2Workbench catalog={catalog} />
        ) : activeLab === "five-axis-f3" ? (
          <F3Workbench catalog={catalog} />
        ) : activeLab === "five-axis-f4" ? (
          <F4Workbench catalog={catalog} />
        ) : activeLab === "intelligence-r5" ? (
          <IntelligenceR5Workbench catalog={catalog} />
        ) : activeLab === "intelligence-r5b" ? (
          <IntelligenceR5BWorkbench catalog={catalog} />
        ) : activeLab === "physical-r4" ? (
          <PhysicalR4Workbench catalog={catalog} />
        ) : activeLab === "optimization-r6" ? (
          <OptimizationR6Workbench catalog={catalog} />
        ) : activeLab === "control-r7" ? (
          <ControlR7Workbench catalog={catalog} />
        ) : activeLab === "control-r7b" ? (
          <ControlR7BWorkbench catalog={catalog} />
        ) : activeLab === "control-r7c" ? (
          <ControlR7CWorkbench catalog={catalog} />
        ) : activeLab === "control-r7d" ? (
          <ControlR7DWorkbench catalog={catalog} />
        ) : activeLab === "field-evidence" ? (
          <FieldEvidenceWorkbench catalog={catalog} />
        ) : (
          <MachineR3Workbench catalog={catalog} />
        )}

        {/* Global Footer */}
        <GlobalFooter />
      </div>

      <WelcomeOverlay
        forceOpen={showWelcome}
        onClose={() => setShowWelcome(false)}
      />

      {showPipeline && (
        <PipelineMap
          active={activeLab === "pipeline" ? "benchmark" : activeLab}
          onSelect={(lab) => {
            setActiveLab(lab);
            setShowLegacy(true);
            setShowPipeline(false);
          }}
          onClose={() => setShowPipeline(false)}
        />
      )}
    </div>
  );
}
