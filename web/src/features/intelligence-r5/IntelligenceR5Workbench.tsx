import { useEffect, useMemo, useState } from "react";

import type { Catalog } from "../../types";
import { loadR5Example, loadR5Manifest, loadR5Scenarios } from "./api";
import type {
  AxisEvaluation,
  R5ExamplePayload,
  R5Manifest,
  R5ScenarioSummary,
} from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function formatNumber(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) > 0 && Math.abs(value) < 0.001) return value.toExponential(3);
  return value.toFixed(digits).replace(/\.?0+$/, "");
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function statusClass(value?: string): string {
  if (value === "Passed" || value === "Supported" || value === "Validated") {
    return "status-positive";
  }
  if (value === "Failed" || value === "Refuted") return "status-negative";
  return "status-neutral";
}

function statusLabel(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, "$1 $2");
}

function axisMetric(axis: AxisEvaluation): string {
  if (axis.status !== "Validated") return statusLabel(axis.reasonCode ?? axis.status);
  return `${formatNumber(axis.baselineRmse)} → ${formatNumber(axis.modelRmse)} residual RMSE`;
}

export function IntelligenceR5Workbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<R5Manifest | null>(null);
  const [scenarios, setScenarios] = useState<R5ScenarioSummary[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [example, setExample] = useState<R5ExamplePayload | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const displayedManifest = example?.manifest ?? manifest;
  const runtimeBound = Boolean(
    displayedManifest?.domainPackId &&
      catalog?.domainPacks.find((item) => item.domainPackId === displayedManifest.domainPackId)?.runtimeBound,
  );
  const validatedAxis = useMemo(
    () => example?.evaluation?.axisResults.find((axis) => axis.status === "Validated"),
    [example],
  );
  const isCounterexample = example?.scenario.expectedExecutionStatus === "Skipped";

  const loadScenario = async (nextId: string, active?: { value: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      const next = await loadR5Example(nextId);
      if (active && !active.value) return;
      setExample(next);
      setManifest(next.manifest);
      setScenarioId(nextId);
    } catch (reason) {
      if (!active || active.value) {
        setExample(null);
        setError(reason instanceof Error ? reason.message : "R5 场景加载失败。");
      }
    } finally {
      if (!active || active.value) setBusy(false);
    }
  };

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextScenarios] = await Promise.all([
          loadR5Manifest(),
          loadR5Scenarios(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setScenarios(nextScenarios);
        const defaultId = nextScenarios.some((item) => item.scenarioId === nextManifest.defaultScenarioId)
          ? nextManifest.defaultScenarioId
          : nextScenarios[0]?.scenarioId;
        if (!defaultId) throw new Error("R5 场景目录为空。");
        await loadScenario(defaultId, active);
      } catch (reason) {
        if (active.value) {
          setError(reason instanceof Error ? reason.message : "R5 初始化失败。");
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
          <strong>R5 未完成</strong><span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="关闭错误">×</button>
        </div>
      )}

      <main className="workspace intelligence-r5-workspace">
        <aside className="config-panel">
          <div className="panel-heading">
            <div><span className="eyebrow">INTELLIGENCE R5-A LAB</span><h1>可信学习工作台</h1></div>
            <span className="schema-badge">v{displayedManifest?.schemaVersion ?? 1}</span>
          </div>

          <section className="config-section">
            <div className="notice-card intelligence-r5-banner" role="note">
              <strong>{displayedManifest?.safetyBanner ?? "SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE"}</strong>
              <strong>{displayedManifest?.learningBanner ?? "SYNTHETIC LEARNING CONTRACT / REAL-WORLD GENERALIZATION OPEN"}</strong>
              <p>Windows 原生、离线训练、只读证据。没有设备写入、在线学习或参数应用入口。</p>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>场景</h2><em>{scenarios.length || "—"}</em></div>
            <label className="field-label" htmlFor="r5-scenario">验收场景</label>
            <select
              id="r5-scenario"
              value={scenarioId}
              disabled={busy}
              onChange={(event) => void loadScenario(event.target.value)}
            >
              {scenarios.map((scenario) => (
                <option key={scenario.scenarioId} value={scenario.scenarioId}>{scenario.title}</option>
              ))}
            </select>
            <p>{example?.scenario.description ?? "正在加载学习合同…"}</p>
            <div className="chip-row">
              <span className="chip">windows-only</span>
              <span className="chip">offline-only</span>
              <span className={`chip ${statusClass(runtimeBound ? "Passed" : "Open")}`}>
                {runtimeBound ? "runtime-bound" : "runtime-pending"}
              </span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>DatasetSnapshot</h2><em>{example?.dataset.samples.length ?? 0} rows</em></div>
            <dl className="data-list">
              <div><dt>Identity</dt><dd title={example?.dataset.contentHash}>{shortHash(example?.dataset.contentHash)}</dd></div>
              <div><dt>Source</dt><dd>{example?.dataset.governance.sourceKind ?? "—"}</dd></div>
              <div><dt>Axes</dt><dd>{example?.dataset.axisIds.join(", ") ?? "—"}</dd></div>
              <div><dt>Governance</dt><dd>{example?.dataset.governance.governanceId ?? "—"}</dd></div>
              <div><dt>License</dt><dd>{example?.dataset.governance.licenseId ?? "—"}</dd></div>
              <div><dt>Allowed use</dt><dd>{example?.dataset.governance.allowedUses.join(", ") ?? "—"}</dd></div>
            </dl>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>分组切分</h2><em>anti-leakage</em></div>
            <div className="intelligence-r5-split-grid">
              {(example?.splitManifest.partitions ?? []).map((partition) => (
                <article key={partition.splitId}>
                  <strong>{partition.splitId}</strong>
                  <span>{partition.sampleIds.length} rows</span>
                  <small>{partition.connectedGroupIds.length} isolated group(s)</small>
                </article>
              ))}
            </div>
            <div className="findings-list top-gap">
              <article>
                <header>
                  <strong>connected-identity-disjoint</strong>
                  <span className={isCounterexample ? "status-negative" : "status-positive"}>
                    {isCounterexample ? "Expected rejection" : "Passed"}
                  </span>
                </header>
                <p>
                  {isCounterexample
                    ? "该反例故意破坏输入合同；基准 DatasetSnapshot 仅用于构造反例，不代表该场景通过切分门。"
                    : "trajectory、task、device batch 与 pair identity 均按 split 隔离，并保持时间前向。"}
                </p>
              </article>
            </div>
          </section>
        </aside>

        <section className="analysis-panel intelligence-r5-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Residual Model</span><span>/</span><span>OOD &amp; UQ</span></div>
            <div className="run-state">
              {isCounterexample ? (
                <span className="status-negative">counterexample: expected Invalid</span>
              ) : (
                <>
                    <span className={statusClass(example?.evaluation?.syntheticLearningContractStatus)}>
                      synthetic: {example?.evaluation?.syntheticLearningContractStatus ?? "Pending"}
                    </span>
                    <span className={statusClass(example?.evaluation?.realWorldGeneralizationStatus)}>
                      reality: {example?.evaluation?.realWorldGeneralizationStatus ?? "Open"}
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="intelligence-r5-analysis-body">
            {isCounterexample ? (
              <>
                <section className="report-card intelligence-r5-hero">
                  <span className="eyebrow">NEGATIVE ACCEPTANCE CASE</span>
                  <div>
                    <strong className="status-negative">{example?.scenario.expectedExecutionStatus}</strong>
                    <h2>Expected outcome: {example?.scenario.expectedOutcome}</h2>
                    <p>{example?.scenario.description}</p>
                  </div>
                </section>
                <section className="report-card">
                  <div className="section-title compact"><span>01</span><h2>门禁语义</h2><em>no positive claim</em></div>
                  <p>
                    该场景只验证篡改或泄漏输入会被拒绝。正向场景的模型分数、Claims 与 Evidence
                    不属于本次反例结果，因此不会在这里展示。
                  </p>
                </section>
              </>
            ) : (
              <>
            <section className="report-card intelligence-r5-hero">
              <span className="eyebrow">VALIDATED TARGET</span>
              <div>
                <strong>{validatedAxis?.axisId ?? "—"}</strong>
                <h2>{formatPercent(validatedAxis?.improvementRatio)} RMSE improvement</h2>
                <p>{validatedAxis ? axisMetric(validatedAxis) : "没有通过独立测试的残差头。"}</p>
              </div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>按轴验收</h2><em>no universal score</em></div>
              <div className="intelligence-r5-axis-grid">
                {(example?.evaluation?.axisResults ?? []).map((axis) => (
                  <article key={axis.axisId}>
                    <header><strong>{axis.axisId}</strong><span className={statusClass(axis.status)}>{statusLabel(axis.status)}</span></header>
                    <p>{axisMetric(axis)}</p>
                    {axis.improvementRatio !== null && axis.improvementRatio !== undefined && (
                      <small>{formatPercent(axis.improvementRatio)} improvement</small>
                    )}
                  </article>
                ))}
              </div>
            </section>

            <section className="intelligence-r5-gate-grid">
              <article className="report-card">
                <span className="eyebrow">OOD DETECTION</span>
                <strong>{formatPercent(example?.evaluation?.oodDetectionRate)}</strong>
                <p>域外探针必须弃权，不输出正向预测声明。</p>
              </article>
              <article className="report-card">
                <span className="eyebrow">CONFORMAL COVERAGE</span>
                <strong>{formatPercent(example?.evaluation?.conformalCoverage)}</strong>
                <p>区间只对声明适用域内的 X 轴测试样本有效。</p>
              </article>
              <article className="report-card">
                <span className="eyebrow">TARGET PARITY</span>
                <strong>{formatNumber(example?.evaluation?.targetParityMaxAbsGap, 12)}</strong>
                <p>NumPy 训练端与独立纯 Python Windows 推理端的最大绝对差。</p>
              </article>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>02</span><h2>ModelBundle</h2><em>candidate</em></div>
              <dl className="data-list intelligence-r5-bundle-list">
                <div><dt>Target</dt><dd>{example?.modelBundle.xAxisHead.axisId ?? "—"} · ridge residual</dd></div>
                <div><dt>Input contract</dt><dd>{example?.modelBundle.inputContractId ?? "—"}</dd></div>
                <div><dt>Inputs</dt><dd>{example?.modelBundle.xAxisHead.featureOrder.join(", ") ?? "—"}</dd></div>
                <div><dt>Preprocess</dt><dd>{example?.modelBundle.preprocessorId ?? "—"}</dd></div>
                <div><dt>Output contract</dt><dd>{example?.modelBundle.outputContractId ?? "—"}</dd></div>
                <div><dt>Uncertainty</dt><dd>split conformal · r={formatNumber(example?.modelBundle.xAxisHead.conformalRadius)}</dd></div>
                <div><dt>OOD</dt><dd>train envelope + {formatPercent(example?.modelBundle.xAxisHead.featureEnvelope.marginFraction)}</dd></div>
                <div><dt>Runtime</dt><dd>{example?.modelBundle.targetInterpreterId ?? "—"}</dd></div>
                <div><dt>Online learning</dt><dd className="status-negative">disabled</dd></div>
                <div><dt>Features</dt><dd>{example?.modelBundle.resourceBudget.featureCount ?? "—"}</dd></div>
              </dl>
            </section>
              </>
            )}
          </div>
        </section>

        <aside className="evidence-panel">
          <div className="panel-heading evidence-heading">
            <div><span className="eyebrow">SEALED R5-A OUTPUT</span><h2>Claims / Evidence</h2></div>
            <span className="schema-badge">{displayedManifest?.stage ?? "R5-A"}</span>
          </div>

          <section className="verdict-card">
            <span className="eyebrow">DUAL EXIT GATE</span>
            {isCounterexample ? (
              <>
                <div className="verdict-rule"><i /><span>Expected execution</span><b className="status-negative">{example?.scenario.expectedExecutionStatus ?? "—"}</b></div>
                <div className="verdict-rule"><i /><span>Expected outcome</span><b className="status-negative">{example?.scenario.expectedOutcome ?? "—"}</b></div>
                <div className="verdict-rule"><i /><span>Positive Claims</span><b className="status-positive">none</b></div>
              </>
            ) : (
              <>
                <div className="verdict-rule"><i /><span>Synthetic contract</span><b className={statusClass(example?.evaluation?.syntheticLearningContractStatus)}>{example?.evaluation?.syntheticLearningContractStatus ?? "—"}</b></div>
                <div className="verdict-rule"><i /><span>Real generalization</span><b className={statusClass(example?.evaluation?.realWorldGeneralizationStatus)}>{example?.evaluation?.realWorldGeneralizationStatus ?? "Open"}</b></div>
                <div className="verdict-rule"><i /><span>Bundle hash</span><b title={example?.modelBundle.contentHash}>{shortHash(example?.modelBundle.contentHash)}</b></div>
              </>
            )}
            <div className="verdict-rule"><i /><span>Device write surface</span><b className="status-negative">absent</b></div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>01</span><h2>Claims</h2></div>
            <div className="claims-list">
              {isCounterexample ? (
                <article>
                  <div><strong>No positive claim emitted</strong><em className="status-negative">Invalid</em></div>
                  <p>反例在输入完整性或防泄漏门被拒绝，不能继承基准场景的正向声明。</p>
                  <footer><code>counterexample.expected-rejection</code><span>Skipped</span></footer>
                </article>
              ) : (
                (example?.evaluation?.claims ?? []).map((claim) => (
                  <article key={claim.claimId}>
                    <div><strong>{claim.title}</strong><em className={statusClass(claim.status)}>{claim.status}</em></div>
                    <p>{claim.statement}</p>
                    <footer><code>{claim.claimId}</code><span>{claim.reasonCode ?? claim.evidenceLevel ?? "—"}</span></footer>
                  </article>
                ))
              )}
            </div>
          </section>

          <section className="evidence-section">
            <div className="section-title compact"><span>02</span><h2>Evidence</h2></div>
            <div className="claims-list">
              {isCounterexample ? (
                <article>
                  <div><strong>Scenario mutation</strong><em className="status-neutral">declared</em></div>
                  <p>{example?.scenario.description}</p>
                  <footer><code>{example?.scenario.scenarioId}</code><span>{example?.scenario.expectedExecutionStatus}</span></footer>
                </article>
              ) : (
                (example?.evaluation?.evidence ?? []).map((item) => (
                  <article key={item.evidenceId}>
                    <div><strong>{item.title}</strong><em className="status-neutral">sealed</em></div>
                    <p>{item.summary}</p>
                    <footer><code>{item.evidenceId}</code><span title={item.contentHash ?? undefined}>{shortHash(item.contentHash ?? undefined)}</span></footer>
                  </article>
                ))
              )}
            </div>
          </section>
        </aside>
      </main>
    </>
  );
}
