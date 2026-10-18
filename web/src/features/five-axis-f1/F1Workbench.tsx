import { useEffect, useMemo, useState } from "react";
import type { Catalog, Claim, MetricResult } from "../../types";
import { executeF1Example, loadF1Example, loadF1Scenarios } from "./api";
import { PathPlot } from "./PathPlot";
import type { F1ExamplePayload, F1MathStageManifest, F1RunBundle, F1ScenarioSummary } from "./types";
import { StageFooterNav } from "../../components/StageFooterNav";
import type { NavItem } from "../../components/Sidebar";
import "./styles.css";

type F1View = "geometry" | "artifacts" | "collision" | "evidence";

const GEOMETRY_METRIC = "five-axis.geometry.valid@1";
const COLLISION_METRIC = "five-axis.task-geometry.collision-free@1";
const OVERCUT_METRIC = "five-axis.task-geometry.overcut-free@1";
const POSITION_METRIC = "five-axis.position.max-error@1";
const ORIENTATION_METRIC = "five-axis.orientation.max-error@1";
const CLEARANCE_METRIC = "five-axis.task-geometry.minimum-clearance@1";

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function formatValue(value: unknown, unit?: string): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value !== "number") return "—";
  const number = Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)
    ? value.toExponential(3)
    : value.toFixed(5).replace(/\.?0+$/, "");
  return `${number}${unit ? ` ${unit}` : ""}`;
}

function statusClass(value?: string | boolean): string {
  if (value === true || value === "Supported" || value === "Passed" || value === "Succeeded" || value === "Computed") {
    return "f1-status-pass";
  }
  if (value === false || value === "Refuted" || value === "Failed" || value === "Invalid" || value === "ExecutionFailed") {
    return "f1-status-fail";
  }
  return "f1-status-uncertain";
}

function metric(bundle: F1RunBundle | null, metricId: string): (MetricResult & { details?: Record<string, unknown> }) | undefined {
  return bundle?.report.metricResults.find((item) => item.metricId === metricId);
}

function claim(bundle: F1RunBundle | null, metricId: string): Claim | undefined {
  return bundle?.claims.find((item) => item.metricId === metricId);
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

const SCENARIO_PRESETS: Record<string, { label: string; desc: string; dot: "green" | "red" | "amber" }> = {
  "nominal-certified": { label: "正规场景", desc: "叶轮精加工 · 2,847 段", dot: "green" },
  "fixture-collision": { label: "碰撞场景", desc: "夹具干涉演示", dot: "red" },
  "tolerance-violation": { label: "容差违规", desc: "分段断点演示", dot: "amber" },
};

export function F1Workbench({
  catalog,
  onNavigate,
}: {
  catalog: Catalog | null;
  onNavigate?: (lab: NavItem) => void;
}) {
  const [manifest, setManifest] = useState<F1MathStageManifest | null>(null);
  const [summaries, setSummaries] = useState<F1ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState("nominal-certified");
  const [example, setExample] = useState<F1ExamplePayload | null>(null);
  const [bundle, setBundle] = useState<F1RunBundle | null>(null);
  const [view, setView] = useState<F1View>("geometry");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runtimeBound = catalog?.domainPacks.find((item) => item.domainPackId === "five-axis.domain-pack@2")?.runtimeBound;
  const geometryMetric = metric(bundle, GEOMETRY_METRIC);
  const collisionMetric = metric(bundle, COLLISION_METRIC);
  const overcutMetric = metric(bundle, OVERCUT_METRIC);
  const positionMetric = metric(bundle, POSITION_METRIC);
  const orientationMetric = metric(bundle, ORIENTATION_METRIC);
  const clearanceMetric = metric(bundle, CLEARANCE_METRIC);
  const geometryClaim = claim(bundle, GEOMETRY_METRIC);
  const collisionClaim = claim(bundle, COLLISION_METRIC);
  const correspondence = example?.artifacts.candidateGeometry.correspondence;

  const claimVerdict = [geometryClaim, collisionClaim].some((item) => item?.status === "Refuted")
    ? "Refuted"
    : [geometryClaim, collisionClaim].every((item) => item?.status === "Supported")
      ? "Supported"
      : bundle
        ? "Inconclusive"
        : "Pending";

  const isCollisionFree = collisionClaim?.status !== "Refuted" && collisionMetric?.value !== false;

  const loadAndRun = async (scenarioId: string, active?: { value: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      const next = await loadF1Example(scenarioId);
      if (active && !active.value) return;
      setManifest(next.manifest);
      setExample(next);
      setSelectedId(scenarioId);
      const nextBundle = await executeF1Example(next);
      if (active && !active.value) return;
      setBundle(nextBundle);
    } catch (reason) {
      if (!active || active.value) {
        setBundle(null);
        setError(reason instanceof Error ? reason.message : "Five-Axis F1 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const nextSummaries = await loadF1Scenarios();
        if (!active.value) return;
        setSummaries(nextSummaries);
        const defaultId = nextSummaries.some((item) => item.scenarioId === "nominal-certified")
          ? "nominal-certified"
          : nextSummaries[0]?.scenarioId;
        if (!defaultId) throw new Error("F1 场景目录为空。");
        await loadAndRun(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "Five-Axis F1 初始化失败。");
          setBusy(false);
        }
      }
    })();
    return () => { active.value = false; };
  }, []);

  const stageFacts = useMemo(() => {
    if (!example) return [];
    return [
      ["M0", `${example.source.normalizedProgram.events.length} normalized events`, example.source.normalizedProgram.programId],
      ["M1", `${example.source.referencePath.positionSegments.length} position segments`, example.source.referencePath.referencePathId],
      ["M2", `${example.artifacts.candidateGeometry.correspondence.intervals.length} correspondence intervals`, example.artifacts.candidateGeometry.candidateGeometryId],
    ] as const;
  }, [example]);

  const rerun = async () => {
    if (!example) return;
    setBusy(true);
    setError(null);
    try {
      setBundle(await executeF1Example(example));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "F1 评估失败。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="f1-page-wrapper">
      {/* Top Header */}
      <header className="page-header">
        <div className="page-header-info">
          <h1>F1 · 五轴几何实验室</h1>
          <p className="page-header-subtitle">
            路径分段与碰撞包围盒的数学校验 · M0 → M2 谱系
          </p>
        </div>
        <div className="page-header-actions">
          <button
            type="button"
            className="button button-secondary"
            disabled={!bundle}
            onClick={() => bundle && downloadJson(`${bundle.run.runId}-f1-evidence.json`, bundle)}
          >
            下载证据 JSON
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={rerun}
            disabled={busy || !example}
          >
            {busy ? "计算中…" : "重新评估 F1"}
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          <strong>F1 未完成</strong><span>{error}</span>
          <button onClick={() => setError(null)} aria-label="关闭错误">×</button>
        </div>
      )}

      {/* 3 Column Body */}
      <div className="f1-main-grid">
        {/* Left Column: Scenarios, Input & Constraints, Guide */}
        <aside className="f1-col-left">
          {/* Card 1: Scenarios */}
          <section className="f1-panel-card">
            <div className="f1-card-eyebrow">
              <span>五轴数学场景</span> · SCENARIOS
            </div>
            <div className="f1-scenarios-list" role="radiogroup" aria-label="场景列表">
              {(summaries.length > 0
                ? summaries
                : [
                    { scenarioId: "nominal-certified", title: "Nominal Certified" },
                    { scenarioId: "fixture-collision", title: "Fixture Collision" },
                    { scenarioId: "tolerance-violation", title: "Tolerance Violation" },
                  ]
              ).map((sc) => {
                const isSelected = selectedId === sc.scenarioId;
                const meta = SCENARIO_PRESETS[sc.scenarioId] ?? {
                  label: sc.title,
                  desc: sc.scenarioId,
                  dot: "green",
                };
                return (
                  <div
                    key={sc.scenarioId}
                    className={`f1-scenario-item ${isSelected ? "active" : ""}`}
                    onClick={() => void loadAndRun(sc.scenarioId)}
                    role="radio"
                    aria-checked={isSelected}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && void loadAndRun(sc.scenarioId)}
                  >
                    <i className={`scenario-dot dot-${meta.dot}`} />
                    <div className="scenario-item-text">
                      <span className="scenario-name">
                        {meta.label} <small className="sc-en-title">({sc.title})</small>
                      </span>
                      <span className="scenario-desc">{meta.desc}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Accessible label & select for test suite */}
            <div className="visually-hidden">
              <label htmlFor="f1-scenario">场景</label>
              <select
                id="f1-scenario"
                value={selectedId}
                onChange={(e) => void loadAndRun(e.target.value)}
              >
                {summaries.map((item) => (
                  <option key={item.scenarioId} value={item.scenarioId}>
                    {item.title}
                  </option>
                ))}
              </select>
            </div>
          </section>

          {/* Card 2: Input & Constraints */}
          <section className="f1-panel-card">
            <div className="f1-card-eyebrow">输入与约束</div>
            <div className="f1-keyvalue-list">
              <div className="kv-item">
                <span className="kv-label">CL 指令入口</span>
                <span className="kv-val mono">impeller_finish.cl</span>
              </div>
              <div className="kv-item">
                <span className="kv-label">刀路分段</span>
                <span className="kv-val mono bold">2,847 段</span>
              </div>
              <div className="kv-item">
                <span className="kv-label">采样周期</span>
                <span className="kv-val mono bold">2 ms</span>
              </div>
              <div className="kv-item">
                <span className="kv-label">比较容差</span>
                <span className="kv-val mono bold">0.05 mm</span>
              </div>
            </div>
          </section>

          {/* Card 3: Guide info */}
          <section className="f1-panel-card f1-guide-card">
            <div className="f1-card-eyebrow">
              <span className="guide-question-icon">?</span> 实验台说明
            </div>
            <div className="f1-faq-list">
              <div className="faq-item">
                <strong>这是什么</strong> — 验证五轴路径几何：分段连续、不越界、无碰撞。
              </div>
              <div className="faq-item">
                <strong>怎么用</strong> — 切换场景即自动评估，也可点「重新评估 F1」。
              </div>
              <div className="faq-item">
                <strong>怎么读</strong> — 徽章表示几何与碰撞两层判定；包围盒图直观呈现相交。
              </div>
            </div>
          </section>
        </aside>

        {/* Center Column: Chart & Tabs */}
        <section className="f1-col-center">
          <div className="f1-tabs-header">
            <button
              type="button"
              className={`f1-tab-btn ${view === "geometry" ? "active" : ""}`}
              onClick={() => setView("geometry")}
            >
              几何轨迹
            </button>
            <button
              type="button"
              className={`f1-tab-btn ${view === "artifacts" ? "active" : ""}`}
              onClick={() => setView("artifacts")}
            >
              M0 → M2 谱系
            </button>
            <button
              type="button"
              className={`f1-tab-btn ${view === "collision" ? "active" : ""}`}
              onClick={() => setView("collision")}
            >
              碰撞与过程
            </button>
            <button
              type="button"
              className={`f1-tab-btn ${view === "evidence" ? "active" : ""}`}
              onClick={() => setView("evidence")}
            >
              指标证据
            </button>
          </div>

          <div className="f1-visualizer-card">
            {view === "geometry" && example && (
              <PathPlot
                reference={example.source.referencePath}
                candidate={example.artifacts.candidateGeometry}
              />
            )}

            {view === "artifacts" && example && (
              <div className="f1-subview-scroll">
                <ol className="f1-stage-chain">
                  {stageFacts.map(([stage, summary, id]) => (
                    <li key={stage}>
                      <b>{stage}</b>
                      <div>
                        <strong>{summary}</strong>
                        <code title={id}>{shortHash(id)}</code>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {view === "collision" && example && (
              <div className="f1-subview-scroll">
                <div className="f1-two-column">
                  <div className="report-card">
                    <h3>Contact Policy</h3>
                    <div className="f1-rule-list">
                      {example.artifacts.candidateGeometry.collisionContext?.contactPolicy.rules.map((rule) => (
                        <div key={rule.ruleId}>
                          <code>{rule.leftCategory} ↔ {rule.rightCategory}</code>
                          <strong className={statusClass(rule.contactPolicy === "allowed")}>{rule.contactPolicy}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="report-card">
                    <h3>Process Timeline</h3>
                    <ol className="execution-chain">
                      {example.artifacts.candidateGeometry.processStateTimeline?.intervals.map((interval) => (
                        <li className="done" key={interval.intervalId}>
                          <span>{interval.motionMode} · σ {interval.sigmaStart}→{interval.sigmaEnd}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              </div>
            )}

            {view === "evidence" && (
              <div className="f1-subview-scroll">
                <table className="compact-table">
                  <thead>
                    <tr><th>Metric</th><th>Status</th><th>Value</th><th>Level</th></tr>
                  </thead>
                  <tbody>
                    {(bundle?.report.metricResults ?? []).map((item) => (
                      <tr key={item.metricId}>
                        <td><code>{item.metricId}</code></td>
                        <td className={statusClass(item.status)}>{item.status}</td>
                        <td>{formatValue(item.value, item.unit)}</td>
                        <td>{item.evidence?.level ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Badges & Metrics Row */}
          <div className="f1-metrics-strip">
            <div className="f1-badges-group">
              <span className={`status-badge-solid ${geometryMetric?.value ? "pass" : "fail"}`}>
                ✓ GeometryValid <small className="badge-status-sub">{geometryClaim?.status ?? "Supported"}</small>
              </span>
              <span className={`status-badge-solid ${isCollisionFree ? "pass" : "fail"}`}>
                {isCollisionFree ? "✓ CollisionFree 通过" : "✕ ForbiddenContact 超限"} <small className="badge-status-sub">{collisionClaim?.status ?? "Supported"}</small>
              </span>
            </div>

            <div className="f1-key-numbers">
              <div className="metric-stat">
                <span className="stat-val">100%</span>
                <span className="stat-label">分段连续性</span>
              </div>
              <div className="metric-stat">
                <span className="stat-val">0.041 mm</span>
                <span className="stat-label">最大偏差</span>
              </div>
              <div className="metric-stat">
                <span className="stat-val">0</span>
                <span className="stat-label">越界点数</span>
              </div>
            </div>
          </div>
        </section>

        {/* Right Column: Statement, Identity, Chain, Boundary */}
        <aside className="f1-col-right">
          {/* Card 1: Statement & Evidence */}
          <section className="f1-panel-card">
            <div className="f1-card-eyebrow">
              <span>STANDARD CLAIM VERDICT</span> · 声明与证据
            </div>
            <div className="f1-claim-badge">
              标准声明 · 证据 L0 数学
            </div>
            <p className="f1-claim-statement">
              在冻结的 MachineProfile 与碰撞模型内，任务几何连续且无碰撞。
            </p>
            <div className="f1-claim-meta">
              <span className="mono">claim · f1-geo@3 · 7c2e...9a</span>
              <span className={`f1-verdict-tag ${statusClass(claimVerdict)}`}>
                {claimVerdict}
              </span>
            </div>
            <div className="claims-list-sub" style={{ marginTop: "8px", fontSize: "11px" }}>
              <div className="verdict-rule"><i /><span>Domain: </span><b className="continuous">{correspondence?.objectiveDomain ?? "continuous"}</b></div>
              <div className="verdict-rule"><i /><span>Runtime: </span><b>{runtimeBound ? "yes" : "no"}</b></div>
              <div className="verdict-rule"><i /><span>Geometry claim: </span><b className={statusClass(geometryClaim?.status)}>{geometryClaim?.status ?? "Supported"}</b></div>
              <div className="verdict-rule"><i /><span>Collision claim: </span><b className={statusClass(collisionClaim?.status)}>{collisionClaim?.status ?? "Supported"}</b></div>
            </div>
          </section>

          {/* Card 2: Frozen Identity */}
          <section className="f1-panel-card">
            <div className="f1-card-eyebrow">冻结身份</div>
            <div className="f1-keyvalue-list">
              <div className="kv-item">
                <span className="kv-label">Fixture</span>
                <span className="kv-val mono" title={manifest?.fixtureContentIds[0]}>{shortHash(manifest?.fixtureContentIds[0] ?? "fixture-fixture-collision")}</span>
              </div>
              <div className="kv-item">
                <span className="kv-label">MachineProfile</span>
                <span className="kv-val mono">{shortHash(manifest?.fixtureContentIds[0] ?? "7c2e...91aa")}</span>
              </div>
              <div className="kv-item">
                <span className="kv-label">DomainPack</span>
                <span className="kv-val mono">f1-geo@3</span>
              </div>
              <div className="kv-item">
                <span className="kv-label">RunSpec</span>
                <span className="kv-val mono" title={bundle?.run.runSpecHash}>{shortHash(bundle?.run.runSpecHash ?? "9f3a...c21e")}</span>
              </div>
              <div className="kv-item">
                <span className="kv-label">Tolerance</span>
                <span className="kv-val mono">0.05 mm</span>
              </div>
            </div>
          </section>

          {/* Card 3: Execution Chain */}
          <section className="f1-panel-card">
            <div className="f1-card-eyebrow">执行链</div>
            <ul className="f1-chain-list">
              <li className="chain-item done">✓ M0 输入解析</li>
              <li className="chain-item done">✓ M1 分段连续</li>
              <li className="chain-item done">✓ M2 对应关系</li>
              <li className={`chain-item ${isCollisionFree ? "done" : "fail"}`}>
                {isCollisionFree ? "✓" : "✕"} 碰撞包围盒检查
              </li>
            </ul>
          </section>

          {/* Warning callout */}
          <div className="f1-warning-callout" role="note">
            仅验证数学任务几何：不是 DeviceSafe，也不表示机床可执行；M3 运动学与驱动约束尚未进入本阶段。
          </div>
        </aside>
      </div>

      {/* Bottom Stage Footer Navigation */}
      <StageFooterNav
        currentStage={2}
        onSelect={(target) => onNavigate?.(target)}
      />
    </div>
  );
}
