import { useEffect, useMemo, useState } from "react";

import type { Catalog } from "../../types";
import { approveR5ESyntheticCampaign, assessR5FCandidateImpact, executeR5ESyntheticCampaign, loadR5CExample, loadR5CManifest, loadR5CScenarios, loadR5DManifest, loadR5EManifest, loadR5FManifest, loadR5GManifest, loadR5HManifest, prepareR5GPromotionReadiness, requestR5CPrediction, requestR5DExperimentPlan } from "./api";
import { R5HCandidateHoldoutPanel } from "./R5HCandidateHoldoutPanel";
import { R5ILifecyclePanel } from "./R5ILifecyclePanel";
import type { ConditionalEffectPrediction, R5CExamplePayload, R5CManifest, R5CScenarioSummary, R5DManifest, R5EManifest, R5ESyntheticCampaignReport, R5FCandidateImpactReport, R5FManifest, R5GManifest, R5GModelPromotionReadinessDossier, R5HManifest, SimulationExperimentPlan } from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return `${value.slice(0, 9)}…${value.slice(-7)}`;
}

function number(value: number | undefined, digits = 5): string {
  if (value === undefined) return "—";
  if (Math.abs(value) > 0 && Math.abs(value) < 0.0001) return value.toExponential(3);
  return value.toFixed(digits).replace(/\.?0+$/, "");
}

function percent(value: number | undefined): string {
  return value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
}

function targetLabel(targetId: string): string {
  return targetId === "cycleTimeSeconds" ? "加工周期" : "线性跟随误差";
}

function objectiveLabel(targetId: string): string {
  if (targetId === "cycleTimeSeconds") return "最短周期";
  if (targetId === "linearFollowingErrorMaxMm") return "最小线性误差";
  return "最少指令数";
}

export function IntelligenceR5CWorkbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<R5CManifest | null>(null);
  const [scenarios, setScenarios] = useState<R5CScenarioSummary[]>([]);
  const [example, setExample] = useState<R5CExamplePayload | null>(null);
  const [prediction, setPrediction] = useState<ConditionalEffectPrediction | null>(null);
  const [r5dManifest, setR5DManifest] = useState<R5DManifest | null>(null);
  const [r5eManifest, setR5EManifest] = useState<R5EManifest | null>(null);
  const [r5fManifest, setR5FManifest] = useState<R5FManifest | null>(null);
  const [r5gManifest, setR5GManifest] = useState<R5GManifest | null>(null);
  const [r5hManifest, setR5HManifest] = useState<R5HManifest | null>(null);
  const [experimentPlan, setExperimentPlan] = useState<SimulationExperimentPlan | null>(null);
  const [campaignReport, setCampaignReport] = useState<R5ESyntheticCampaignReport | null>(null);
  const [impactReport, setImpactReport] = useState<R5FCandidateImpactReport | null>(null);
  const [readinessDossier, setReadinessDossier] = useState<R5GModelPromotionReadinessDossier | null>(null);
  const [feedOverride, setFeedOverride] = useState("0.82");
  const [samplePeriod, setSamplePeriod] = useState("0.055");
  const [batchSize, setBatchSize] = useState("5");
  const [accountableParty, setAccountableParty] = useState("");
  const [syntheticAcknowledged, setSyntheticAcknowledged] = useState(false);
  const [reviewPreparer, setReviewPreparer] = useState("");
  const [realityGateAcknowledged, setRealityGateAcknowledged] = useState(false);
  const [deviceSafetyAcknowledged, setDeviceSafetyAcknowledged] = useState(false);
  const [automaticDeploymentAcknowledged, setAutomaticDeploymentAcknowledged] = useState(false);
  const [busy, setBusy] = useState(true);
  const [planning, setPlanning] = useState(false);
  const [campaignBusy, setCampaignBusy] = useState(false);
  const [impactBusy, setImpactBusy] = useState(false);
  const [readinessBusy, setReadinessBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runtimeBound = Boolean(
    catalog?.domainPacks.find((item) => item.domainPackId === "intelligence.domain-pack@3")?.runtimeBound,
  );
  const splitCounts = useMemo(
    () => Object.fromEntries((example?.splitManifest.partitions ?? []).map((item) => [item.splitId, item.sampleIds.length])),
    [example],
  );

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextScenarios, nextR5DManifest, nextR5EManifest, nextR5FManifest, nextR5GManifest, nextR5HManifest] = await Promise.all([loadR5CManifest(), loadR5CScenarios(), loadR5DManifest(), loadR5EManifest(), loadR5FManifest(), loadR5GManifest(), loadR5HManifest()]);
        const nextExample = await loadR5CExample(nextManifest.defaultScenarioId);
        if (!active.value) return;
        setManifest(nextManifest);
        setScenarios(nextScenarios);
        setExample(nextExample);
        setPrediction(nextExample.predictionExample);
        setR5DManifest(nextR5DManifest);
        setR5EManifest(nextR5EManifest);
        setR5FManifest(nextR5FManifest);
        setR5GManifest(nextR5GManifest);
        setR5HManifest(nextR5HManifest);
        setBatchSize(String(nextR5DManifest.defaultBatchSize));
      } catch (reason) {
        if (active.value) setError(reason instanceof Error ? reason.message : "R5-C 初始化失败。");
      } finally {
        if (active.value) setBusy(false);
      }
    })();
    return () => { active.value = false; };
  }, []);

  const predict = async () => {
    if (!example) return;
    const feed = Number(feedOverride);
    const period = Number(samplePeriod);
    if (!Number.isFinite(feed) || !Number.isFinite(period)) {
      setError("feedOverride 与 samplePeriod 必须是有限数字。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setPrediction(await requestR5CPrediction({
        modelBundle: example.modelBundle,
        feedOverride: feed,
        samplePeriod: period,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R5-C 预测失败。");
    } finally {
      setBusy(false);
    }
  };

  const planExperiments = async () => {
    if (!example || !r5dManifest) return;
    const requested = Number(batchSize);
    if (!Number.isInteger(requested) || requested < 1 || requested > r5dManifest.maximumBatchSize) {
      setError(`batchSize 必须是 1–${r5dManifest.maximumBatchSize} 的整数。`);
      return;
    }
    setPlanning(true);
    setError(null);
    setExperimentPlan(null);
    setCampaignReport(null);
    setImpactReport(null);
    setReadinessDossier(null);
    try {
      setExperimentPlan(await requestR5DExperimentPlan({
        schemaId: "axiom.intelligence.simulation-experiment-plan-request@1",
        modelBundle: example.modelBundle,
        dataset: example.dataset,
        splitManifest: example.splitManifest,
        batchSize: requested,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R5-D 实验规划失败。");
    } finally {
      setPlanning(false);
    }
  };

  const runSyntheticCampaign = async () => {
    if (!example || !experimentPlan || !r5eManifest) return;
    if (experimentPlan.status !== "Planned" || experimentPlan.requestedBatchSize !== r5eManifest.fixedBatchSize) {
      setError(`R5-E 首版只接受完整的 ${r5eManifest.fixedBatchSize} 点计划。`);
      return;
    }
    if (!accountableParty.trim()) {
      setError("执行前必须填写 R5-E 责任方标识。");
      return;
    }
    if (!syntheticAcknowledged) {
      setError("执行前必须确认本次仅运行本地 synthetic SIL。");
      return;
    }
    setCampaignBusy(true);
    setCampaignReport(null);
    setImpactReport(null);
    setReadinessDossier(null);
    setError(null);
    try {
      const planRequest = {
        schemaId: "axiom.intelligence.simulation-experiment-plan-request@1" as const,
        modelBundle: example.modelBundle,
        dataset: example.dataset,
        splitManifest: example.splitManifest,
        batchSize: experimentPlan.requestedBatchSize,
      };
      const approved = await approveR5ESyntheticCampaign({
        planRequest,
        plan: experimentPlan,
        accountablePartyId: accountableParty.trim(),
        syntheticOnlyAcknowledged: true,
      });
      setCampaignReport(await executeR5ESyntheticCampaign(approved));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R5-E 合成实验批次失败。");
    } finally {
      setCampaignBusy(false);
    }
  };

  const assessCandidateImpact = async () => {
    if (!campaignReport) return;
    setImpactBusy(true);
    setImpactReport(null);
    setReadinessDossier(null);
    setError(null);
    try {
      setImpactReport(await assessR5FCandidateImpact(campaignReport));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R5-F 下游影响评估失败。");
    } finally {
      setImpactBusy(false);
    }
  };

  const preparePromotionReadiness = async () => {
    if (!impactReport) return;
    if (!reviewPreparer.trim()) {
      setError("生成 R5-G 审查包前必须填写准备人标识。");
      return;
    }
    if (!realityGateAcknowledged || !deviceSafetyAcknowledged || !automaticDeploymentAcknowledged) {
      setError("生成 R5-G 审查包前必须确认三项只读边界。");
      return;
    }
    setReadinessBusy(true);
    setReadinessDossier(null);
    setError(null);
    try {
      setReadinessDossier(await prepareR5GPromotionReadiness(impactReport, reviewPreparer.trim()));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R5-G 晋升就绪审查失败。");
    } finally {
      setReadinessBusy(false);
    }
  };

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>Intelligence 请求未完成</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      <main className="workspace intelligence-r5c-workspace">
        <aside className="config-panel intelligence-r5c-config">
          <div className="panel-heading">
            <div><span className="eyebrow">INTELLIGENCE R5-C LAB</span><h1>条件效应代理模型</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="notice-card intelligence-r5c-banner" role="note">
              <strong>{manifest?.safetyBanner ?? "SYNTHETIC CONDITIONAL EFFECT / NOT REALITY VALIDATED / NOT DEVICE SAFE"}</strong>
              <p>Windows 原生、离线只读。此处只回答参数变化对合成 SIL 结果的影响，不形成设备写入或上机许可。</p>
            </div>
            <div className="chip-row">
              <span className="chip">windows-only</span><span className="chip">offline-only</span>
              <span className={`chip ${runtimeBound ? "status-positive" : "status-neutral"}`}>{runtimeBound ? "runtime-bound" : "runtime-pending"}</span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>参数查询</h2><em>declared domain</em></div>
            <p>{scenarios[0]?.description ?? "正在加载条件效应场景…"}</p>
            <div className="intelligence-r5c-fields">
              <label><span>feedOverride · ratio</span><input aria-label="feedOverride" inputMode="decimal" value={feedOverride} onChange={(event) => setFeedOverride(event.target.value)} /></label>
              <label><span>samplePeriod · s</span><input aria-label="samplePeriod" inputMode="decimal" value={samplePeriod} onChange={(event) => setSamplePeriod(event.target.value)} /></label>
            </div>
            <small className="intelligence-r5c-domain">F ∈ [0.65, 1.00] · Δt ∈ [0.04, 0.08] s</small>
            <button className="button button-primary intelligence-r5c-run" type="button" onClick={() => void predict()} disabled={busy || !example}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◆</span>}{busy ? "计算中…" : "离线预测"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>空间切分</h2><em>25 points</em></div>
            <div className="intelligence-r5c-splits">
              {(["train", "validation", "test"] as const).map((split) => <article key={split}><i className={`split-${split}`} /><strong>{split}</strong><span>{splitCounts[split] ?? 0}</span></article>)}
            </div>
            <p>验证点与测试点不参与拟合；同一参数点只属于一个 partition。</p>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>模型合同</h2><em>pure Python</em></div>
            <dl className="data-list">
              <div><dt>Features</dt><dd>{example?.modelBundle.resourceBudget.featureCount ?? "—"}</dd></div>
              <div><dt>Outputs</dt><dd>{example?.modelBundle.resourceBudget.outputCount ?? "—"}</dd></div>
              <div><dt>Interpreter</dt><dd>pure-python</dd></div>
              <div><dt>Reality</dt><dd className="status-neutral">Open</dd></div>
              <div><dt>Device write</dt><dd className="status-negative">false</dd></div>
            </dl>
          </section>

          <section className="config-section intelligence-r5d-config">
            <div className="section-title"><span>04</span><h2>下一批仿真</h2><em>R5-D plan</em></div>
            <p>从 {r5dManifest?.defaultAvailableCandidateCount ?? 110} 个未观测参数点中，按线性设计不确定性顺序规划；只生成计划，不执行仿真。</p>
            <label><span>batchSize · 1–{r5dManifest?.maximumBatchSize ?? 10}</span><input aria-label="R5-D batchSize" inputMode="numeric" value={batchSize} onChange={(event) => setBatchSize(event.target.value)} /></label>
            <button className="button button-primary intelligence-r5c-run" type="button" onClick={() => void planExperiments()} disabled={busy || planning || !example || !r5dManifest}>
              {planning ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◇</span>}{planning ? "规划中…" : "规划下一批仿真"}
            </button>
            <small>Greedy G-optimal · global optimum not claimed · automatic execution false</small>
          </section>

          <section className="config-section intelligence-r5e-config">
            <div className="section-title"><span>05</span><h2>合成反馈闭环</h2><em>R5-E gated</em></div>
            <p>仅对完整 5 点计划执行本地 F3/F4/R4 synthetic SIL；新标签只追加到 train，候选模型不会自动晋升。</p>
            <label><span>accountablePartyId</span><input aria-label="R5-E accountable party" value={accountableParty} onChange={(event) => setAccountableParty(event.target.value)} placeholder="例如：local-reviewer" /></label>
            <label className="intelligence-r5e-ack"><input aria-label="确认仅执行本地 synthetic SIL" type="checkbox" checked={syntheticAcknowledged} onChange={(event) => setSyntheticAcknowledged(event.target.checked)} /><span>我确认：仅执行本地 synthetic SIL，不连接或写入设备。</span></label>
            <button className="button button-primary intelligence-r5c-run" type="button" onClick={() => void runSyntheticCampaign()} disabled={busy || planning || campaignBusy || !experimentPlan || experimentPlan.status !== "Planned" || experimentPlan.requestedBatchSize !== 5 || !accountableParty.trim() || !syntheticAcknowledged}>
              {campaignBusy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◆</span>}{campaignBusy ? "执行并重训中…" : "批准并执行合成 SIL 批次"}
            </button>
            <small>explicit approval · full batch only · device write false · promotion not performed</small>
          </section>
        </aside>

        <section className="analysis-panel intelligence-r5c-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Parameter → Outcome</span><span>/</span><span>UQ &amp; Abstention</span></div>
            <div className="run-state"><span className="status-positive">synthetic: {example?.evaluation.syntheticConditionalEffectContractStatus ?? "Pending"}</span><span className="status-neutral">reality: Open</span></div>
          </div>

          <div className="intelligence-r5c-body">
            <section className="report-card intelligence-r5c-hero">
              <div><span className="eyebrow">CONDITIONAL EFFECT, NOT A UNIVERSAL SCORE</span><h2>条件改变什么，不做万能总分</h2><p>加工周期保留秒，线性跟随误差保留毫米；两个输出分别验证、分别给区间。</p></div>
              <div className="intelligence-r5c-verdict"><strong className={prediction?.status === "Predicted" ? "status-positive" : "status-neutral"}>{prediction?.status ?? "Pending"}</strong><span>{prediction?.reasonCode ?? "inside declared domain"}</span></div>
            </section>

            {prediction?.status === "Abstained" ? (
              <section className="report-card intelligence-r5c-abstained" role="status"><strong>拒绝域外外推</strong><p>当前参数位于声明域之外，模型没有返回数值或伪造置信区间。</p><code>{prediction.reasonCode}</code></section>
            ) : (
              <section className="intelligence-r5c-output-grid" aria-label="双输出预测">
                {(prediction?.predictions ?? []).map((item) => <article className="report-card" key={item.targetId}><span className="eyebrow">{item.targetId}</span><h2>{targetLabel(item.targetId)}</h2><strong>{number(item.value)} <small>{item.unit}</small></strong><p>[{number(item.lower)}, {number(item.upper)}] {item.unit}</p><footer>split-conformal interval</footer></article>)}
              </section>
            )}

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>25 点参数平面</h2><em>feed × sample period</em></div>
              <div className="intelligence-r5c-grid" role="img" aria-label="25 个参数点的训练验证测试空间切分">
                {(example?.dataset.samples ?? []).map((sample) => <div className={`split-${sample.declaredSplitId}`} key={sample.sampleId} title={`F=${sample.feedOverride}, Δt=${sample.samplePeriod}s, ${sample.declaredSplitId}`}><span>{sample.feedOverride}</span><small>{sample.samplePeriod}s</small></div>)}
              </div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>02</span><h2>独立测试门</h2><em>separate targets</em></div>
              <div className="intelligence-r5c-table-wrap"><table className="intelligence-r5c-table"><thead><tr><th>Target</th><th>Unit</th><th>NRMSE</th><th>Improvement</th><th>Coverage</th></tr></thead><tbody>{(example?.evaluation.headResults ?? []).map((item) => <tr key={item.targetId}><td>{targetLabel(item.targetId)}</td><td>{item.unit}</td><td>{number(item.normalizedRmse, 8)}</td><td>{percent(item.improvementRatio)}</td><td>{percent(item.conformalCoverage)}</td></tr>)}</tbody></table></div>
            </section>

            <section className="report-card intelligence-r5d-plan" aria-label="R5-D 仿真实验计划">
              <div className="intelligence-r5d-heading">
                <div><span className="eyebrow">EXPERIMENT VALUE · PLAN ONLY</span><h2>R5-D 下一批仿真实验</h2><p>Design leverage 只表示线性模型在候选空间中的认知不确定性代理，不是误差概率或现实收益。</p></div>
                <div className="intelligence-r5d-status"><strong className={experimentPlan?.status === "Planned" ? "status-positive" : "status-neutral"}>{experimentPlan?.status ?? "Not planned"}</strong><span>{experimentPlan?.experimentExecutionStatus ?? "NotExecuted"}</span></div>
              </div>
              {experimentPlan?.status === "Planned" ? (
                <>
                  <div className="intelligence-r5d-summary">
                    <article><span>Max leverage · before</span><strong>{number(experimentPlan.maximumCandidateLeverageBefore, 7)}</strong></article>
                    <article><span>After planned batch</span><strong>{number(experimentPlan.maximumCandidateLeverageAfter, 7)}</strong></article>
                    <article><span>Relative reduction</span><strong>{percent(experimentPlan.relativeMaximumLeverageReduction)}</strong></article>
                    <article><span>Execution / update</span><strong>none / none</strong></article>
                  </div>
                  <div className="intelligence-r5c-table-wrap"><table className="intelligence-r5c-table intelligence-r5d-table"><thead><tr><th>#</th><th>feed</th><th>Δt</th><th>leverage</th><th>cycle · predicted</th><th>error · predicted</th><th>samples</th></tr></thead><tbody>{experimentPlan.proposals.map((proposal) => {
                    const cycle = proposal.predictedOutcomes.find((item) => item.targetId === "cycleTimeSeconds");
                    const errorPrediction = proposal.predictedOutcomes.find((item) => item.targetId === "linearFollowingErrorMaxMm");
                    return <tr key={proposal.experimentId}><td data-label="Rank">{proposal.rank}</td><td data-label="Feed">{number(proposal.feedOverride, 3)}</td><td data-label="Δt">{number(proposal.samplePeriod, 3)} s</td><td data-label="Leverage">{number(proposal.designLeverage, 7)}</td><td data-label="Cycle · predicted">{number(cycle?.value)} s</td><td data-label="Error · predicted">{number(errorPrediction?.value)} mm</td><td data-label="Samples">{proposal.estimatedCommandSampleCount}</td></tr>;
                  })}</tbody></table></div>
                  <footer className="intelligence-r5d-boundary"><span>标签尚未获取</span><span>新标签必须生成新 Dataset / Model 版本后再规划</span><span>设备写入：false</span></footer>
                </>
              ) : (
                <div className="intelligence-r5d-empty"><strong>尚未生成计划</strong><p>设置 batch size 后生成有内容身份的候选序列。该动作不会运行 F3/F4/R4，也不会更新模型。</p></div>
              )}
            </section>

            <section className="report-card intelligence-r5e-campaign" aria-label="R5-E 合成实验反馈闭环">
              <div className="intelligence-r5d-heading">
                <div><span className="eyebrow">EXPLICIT APPROVAL → SYNTHETIC SIL → CANDIDATE</span><h2>R5-E 离线合成反馈闭环</h2><p>批次成功、候选门禁与模型晋升分别记录。这里能形成新的数据和模型版本，但不能形成真实设备结论。</p></div>
                <div className="intelligence-r5d-status"><strong className={campaignReport ? "status-positive" : "status-neutral"}>{campaignReport?.campaignExecutionStatus ?? "Awaiting approval"}</strong><span>{campaignReport?.modelPromotionStatus ?? "NotPerformed"}</span></div>
              </div>
              {campaignReport ? (
                <>
                  <div className="intelligence-r5e-summary">
                    <article><span>Exact replay</span><strong>{campaignReport.acquisitionReceipt.resultCount} / 5</strong><small>Succeeded</small></article>
                    <article><span>Dataset</span><strong>25 → {campaignReport.dataset.samples.length}</strong><small>append-only</small></article>
                    <article><span>Train split</span><strong>15 → {campaignReport.splitManifest.partitions[0]?.sampleIds.length ?? 0}</strong><small>validation/test frozen</small></article>
                    <article><span>Candidate gate</span><strong className={campaignReport.candidateAssessment.candidateGateStatus === "Passed" ? "status-positive" : "status-negative"}>{campaignReport.candidateAssessment.candidateGateStatus}</strong><small>promotion {campaignReport.modelPromotionStatus}</small></article>
                    <article><span>Next pool</span><strong>{campaignReport.nextPlan.availableCandidateCount}</strong><small>{campaignReport.nextPlan.designSampleCount} design points</small></article>
                  </div>
                  <div className="intelligence-r5c-table-wrap"><table className="intelligence-r5c-table intelligence-r5d-table intelligence-r5e-table"><thead><tr><th>#</th><th>feed</th><th>Δt</th><th>cycle · actual</th><th>error · actual</th><th>samples</th><th>status</th></tr></thead><tbody>{campaignReport.acquisitionReceipt.results.map((result) => <tr key={result.experimentId}><td data-label="Rank">{result.rank}</td><td data-label="Feed">{number(result.feedOverride, 3)}</td><td data-label="Δt">{number(result.samplePeriod, 3)} s</td><td data-label="Cycle · actual">{number(result.cycleTimeSeconds)} s</td><td data-label="Error · actual">{number(result.linearFollowingErrorMaxMm)} mm</td><td data-label="Samples">{result.commandSampleCount}</td><td data-label="Status" className="status-positive">{result.executionStatus}</td></tr>)}</tbody></table></div>
                  <div className="intelligence-r5e-metrics">
                    {campaignReport.candidateAssessment.metricDeltas.map((metric) => <article key={metric.targetId}><span>{targetLabel(metric.targetId)}</span><strong className={metric.status === "Regressed" ? "status-negative" : "status-positive"}>{percent(metric.relativeImprovement)}</strong><small>{number(metric.baselineModelRmse, 8)} → {number(metric.candidateModelRmse, 8)} {metric.unit} RMSE · {metric.status}</small></article>)}
                  </div>
                  <footer className="intelligence-r5e-boundary"><strong>{campaignReport.safetyBanner}</strong><span>General improvement guarantee: {campaignReport.candidateAssessment.generalImprovementGuarantee}</span><span>Next plan: {campaignReport.nextPlan.proposals.length} points · NotExecuted</span></footer>
                </>
              ) : (
                <div className="intelligence-r5d-empty"><strong>需要显式批准</strong><p>先生成完整 5 点 R5-D 计划，再填写责任方并确认 synthetic-only。界面不会自动执行、递归采样或晋升模型。</p></div>
              )}
            </section>

            <section className="report-card intelligence-r5f-impact" aria-label="R5-F 候选下游影响评估">
              <div className="intelligence-r5d-heading">
                <div><span className="eyebrow">BASELINE @2 ↔ CANDIDATE @3 · EXACT TRUTH UNCHANGED</span><h2>R5-F 候选下游决策影响</h2><p>在相同 135 点网格与 27 次精确预算下，分别运行基线和候选模型。这里只评估筛选影响，不采用或晋升模型。</p></div>
                <div className="intelligence-r5d-status"><strong className={impactReport?.impactGateStatus === "Passed" ? "status-positive" : impactReport ? "status-negative" : "status-neutral"}>{impactReport?.impactGateStatus ?? (campaignReport ? "Ready" : "Awaiting candidate")}</strong><span>{impactReport?.candidateUseStatus ?? "EvaluatedOnly"}</span></div>
              </div>
              {impactReport ? (
                <>
                  <div className="intelligence-r5f-summary">
                    <article><span>Intent coverage</span><strong>{impactReport.scenarioImpacts.length} / 3</strong><small>speed · quality · compact</small></article>
                    <article><span>Screening grid</span><strong>{r5fManifest?.screeningCandidateCount ?? 135}</strong><small>per intent · both models</small></article>
                    <article><span>Exact budget</span><strong>{r5fManifest?.exactValidationBudget ?? 27}</strong><small>per intent · unchanged gates</small></article>
                    <article><span>Candidate use</span><strong>{impactReport.candidateUseStatus}</strong><small>promotion {impactReport.modelPromotionStatus}</small></article>
                  </div>
                  <div className="intelligence-r5c-table-wrap"><table className="intelligence-r5c-table intelligence-r5f-table"><thead><tr><th>Intent</th><th>Rank order</th><th>Exact overlap</th><th>Best · baseline → candidate</th><th>Impact</th><th>Shared prediction error</th></tr></thead><tbody>{impactReport.scenarioImpacts.map((impact) => <tr key={impact.scenarioId}><td data-label="Intent"><strong>{objectiveLabel(impact.primaryObjectiveId)}</strong><small>{impact.primaryObjectiveId}</small></td><td data-label="Rank order" className={impact.screeningOrderChanged ? "status-neutral" : "status-positive"}>{impact.screeningOrderChanged ? "changed" : "unchanged"}</td><td data-label="Exact overlap">{impact.selectedCandidateOverlapCount} / 27</td><td data-label="Best">{number(impact.baselineBestValue ?? undefined)} → {number(impact.candidateBestValue ?? undefined)} {impact.primaryObjectiveUnit}</td><td data-label="Impact" className={impact.primaryObjectiveStatus === "NoRegression" ? "status-positive" : "status-negative"}>{impact.primaryObjectiveStatus}</td><td data-label="Shared prediction error"><div className="intelligence-r5f-errors">{impact.sharedPredictionErrorDeltas.map((delta) => <span key={delta.targetId}><b>{delta.targetId === "cycleTimeSeconds" ? "cycle" : "linear"}</b>{number(delta.baselineMeanAbsoluteError, 7)} → {number(delta.candidateMeanAbsoluteError, 7)} {delta.unit}<em className={delta.status === "Regressed" ? "status-negative" : "status-positive"}>{delta.status}</em></span>)}</div></td></tr>)}</tbody></table></div>
                  <footer className="intelligence-r5e-boundary intelligence-r5f-boundary"><strong>{impactReport.safetyBanner}</strong><span>General improvement guarantee: {impactReport.generalImprovementGuarantee}</span><span>Automatic acceptance: false · device write: false</span></footer>
                </>
              ) : (
                <div className="intelligence-r5d-empty intelligence-r5f-empty"><strong>{campaignReport ? "候选已就绪，尚未评估下游影响" : "等待 R5-E 候选模型"}</strong><p>评估会重验完整 Campaign 谱系，并对三种意图各运行基线与候选的精确回放；不会更改默认模型。</p><button className="button button-primary intelligence-r5f-run" type="button" onClick={() => void assessCandidateImpact()} disabled={!campaignReport || campaignReport.candidateAssessment.candidateGateStatus !== "Passed" || impactBusy || !r5fManifest}>{impactBusy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◇</span>}{impactBusy ? "精确评估中…" : "评估候选下游影响"}</button></div>
              )}
            </section>

            <section className="report-card intelligence-r5g-readiness" aria-label="R5-G 模型晋升就绪审查">
              <div className="intelligence-r5d-heading">
                <div><span className="eyebrow">REPLAYED EVIDENCE → INDEPENDENT REVIEW · NO ACTIVATION</span><h2>R5-G 模型晋升就绪审查</h2><p>把 R5-E 候选与 R5-F 影响证据整理为可复核审查包。生成审查包不是批准、注册、激活或默认模型切换。</p></div>
                <div className="intelligence-r5d-status"><strong className={readinessDossier?.reviewReadinessStatus === "ReadyForIndependentReview" ? "status-positive" : readinessDossier ? "status-negative" : "status-neutral"}>{readinessDossier ? "Review ready" : impactReport ? "Ready to prepare" : "Awaiting impact"}</strong><span>{readinessDossier ? "Awaiting human decision" : "No decision"}</span></div>
              </div>
              {readinessDossier ? (
                <>
                  <div className="intelligence-r5g-summary">
                    <article><span>Evidence checks</span><strong>{readinessDossier.readinessChecks.filter((item) => item.status === "Passed").length} / {readinessDossier.readinessChecks.length}</strong><small>deterministic · lineage-bound</small></article>
                    <article><span>Remaining gates</span><strong>{readinessDossier.remainingGates.length} Open</strong><small>independent decision required</small></article>
                    <article><span>Candidate use</span><strong>{readinessDossier.candidateUseStatus}</strong><small>promotion {readinessDossier.modelPromotionStatus}</small></article>
                    <article><span>State mutation</span><strong>None</strong><small>registry · activation · default</small></article>
                  </div>
                  <div className="intelligence-r5g-columns">
                    <section><span className="eyebrow">READINESS CHECKS</span><div className="intelligence-r5g-checks">{readinessDossier.readinessChecks.map((check) => <article key={check.checkId}><div><strong>{check.checkId}</strong><em className={check.status === "Passed" ? "status-positive" : "status-negative"}>{check.status}</em></div><small>{check.reasonCode}</small><code title={check.evidenceHash}>{shortHash(check.evidenceHash)}</code></article>)}</div></section>
                    <section><span className="eyebrow">REMAINING GATES</span><div className="intelligence-r5g-gates">{readinessDossier.remainingGates.map((gate) => <article key={gate.gateId}><div><strong>{gate.gateId}</strong><em className="status-neutral">{gate.status}</em></div><small>{gate.reasonCode}</small></article>)}</div></section>
                  </div>
                  <div className="intelligence-r5g-identities"><span>rollback baseline <code title={readinessDossier.baselineModelBundleHash}>{shortHash(readinessDossier.baselineModelBundleHash)}</code></span><span>candidate <code title={readinessDossier.candidateModelBundleHash}>{shortHash(readinessDossier.candidateModelBundleHash)}</code></span><span>prepared by <code>{readinessDossier.request.preparedBy}</code></span></div>
                  <footer className="intelligence-r5e-boundary intelligence-r5g-boundary"><strong>{readinessDossier.safetyBanner}</strong><span>Readiness: {readinessDossier.reviewReadinessStatus}</span><span>Decision: {readinessDossier.reviewDecisionStatus}</span><span>Default changed: false · registry write: false · activation: false</span></footer>
                </>
              ) : (
                <div className="intelligence-r5g-form">
                  <strong>{impactReport ? "证据已就绪，等待准备审查包" : "等待 R5-F 影响评估"}</strong>
                  <p>审查包只冻结证据身份与未闭合门禁，不产生模型采用结论。</p>
                  <label className="intelligence-r5g-preparer"><span>Prepared by</span><input aria-label="R5-G prepared by" value={reviewPreparer} onChange={(event) => setReviewPreparer(event.target.value)} disabled={!impactReport} /></label>
                  <div className="intelligence-r5g-acknowledgements">
                    <label><input type="checkbox" aria-label="确认现实验证门仍为 Open" checked={realityGateAcknowledged} onChange={(event) => setRealityGateAcknowledged(event.target.checked)} disabled={!impactReport} /><span>现实验证门仍为 Open</span></label>
                    <label><input type="checkbox" aria-label="确认尚未建立设备安全性" checked={deviceSafetyAcknowledged} onChange={(event) => setDeviceSafetyAcknowledged(event.target.checked)} disabled={!impactReport} /><span>尚未建立设备安全性</span></label>
                    <label><input type="checkbox" aria-label="确认禁止自动部署" checked={automaticDeploymentAcknowledged} onChange={(event) => setAutomaticDeploymentAcknowledged(event.target.checked)} disabled={!impactReport} /><span>禁止自动部署与默认切换</span></label>
                  </div>
                  <button className="button button-primary intelligence-r5g-run" type="button" onClick={() => void preparePromotionReadiness()} disabled={!impactReport || impactReport.impactGateStatus !== "Passed" || !r5gManifest || !reviewPreparer.trim() || !realityGateAcknowledged || !deviceSafetyAcknowledged || !automaticDeploymentAcknowledged || readinessBusy}>{readinessBusy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◇</span>}{readinessBusy ? "确定性重放中…" : "生成晋升就绪审查包"}</button>
                </div>
              )}
            </section>

            <R5HCandidateHoldoutPanel manifest={r5hManifest} readinessDossier={readinessDossier} />

            <R5ILifecyclePanel />

            <section className="intelligence-r5c-gate-grid">
              <article className="report-card"><span className="eyebrow">OOD ABSTENTION</span><strong>{percent(example?.evaluation.oodAbstentionRate)}</strong><p>四个域外探针全部拒绝。</p></article>
              <article className="report-card"><span className="eyebrow">TARGET PARITY</span><strong>{number(example?.evaluation.targetParityMaxAbsGap, 12)}</strong><p>NumPy 与纯 Python 解释器最大绝对差。</p></article>
              <article className="report-card"><span className="eyebrow">SOURCE</span><strong>R4 SIL</strong><p>确定性五轴参数重放，不冒充真实机床。</p></article>
            </section>
          </div>
        </section>

        <aside className="evidence-panel">
          <div className="panel-heading evidence-heading"><div><span className="eyebrow">SEALED R5-C OUTPUT</span><h2>Claims / Evidence</h2></div><span className="schema-badge">R5-C</span></div>
          <section className="verdict-card">
            <span className="eyebrow">DUAL BOUNDARY</span>
            <div className="verdict-rule"><i /><span>Synthetic contract</span><b className="status-positive">{example?.evaluation.syntheticConditionalEffectContractStatus ?? "—"}</b></div>
            <div className="verdict-rule"><i /><span>Real generalization</span><b className="status-neutral">Open</b></div>
            <div className="verdict-rule"><i /><span>Device write</span><b className="status-negative">absent</b></div>
          </section>
          <section className="evidence-section">
            <div className="section-title compact"><span>01</span><h2>冻结身份</h2></div>
            <dl className="identity-list">
              <div><dt>Dataset</dt><dd title={example?.dataset.contentHash}>{shortHash(example?.dataset.contentHash)}</dd></div>
              <div><dt>Split</dt><dd title={example?.splitManifest.contentHash}>{shortHash(example?.splitManifest.contentHash)}</dd></div>
              <div><dt>Training</dt><dd title={example?.trainingReceipt.contentHash}>{shortHash(example?.trainingReceipt.contentHash)}</dd></div>
              <div><dt>Bundle</dt><dd title={example?.modelBundle.contentHash}>{shortHash(example?.modelBundle.contentHash)}</dd></div>
              <div><dt>R5-D Plan</dt><dd title={experimentPlan?.contentHash}>{shortHash(experimentPlan?.contentHash)}</dd></div>
              <div><dt>R5-E Receipt</dt><dd title={campaignReport?.acquisitionReceipt.contentHash}>{shortHash(campaignReport?.acquisitionReceipt.contentHash)}</dd></div>
              <div><dt>Candidate @2</dt><dd title={campaignReport?.modelBundle.contentHash}>{shortHash(campaignReport?.modelBundle.contentHash)}</dd></div>
              <div><dt>R5-E Report</dt><dd title={campaignReport?.contentHash}>{shortHash(campaignReport?.contentHash)}</dd></div>
              <div><dt>R5-F Impact</dt><dd title={impactReport?.contentHash}>{shortHash(impactReport?.contentHash)}</dd></div>
              <div><dt>R5-G Dossier</dt><dd title={readinessDossier?.contentHash}>{shortHash(readinessDossier?.contentHash)}</dd></div>
            </dl>
          </section>
          <section className="evidence-section">
            <div className="section-title compact"><span>02</span><h2>声明</h2></div>
            <div className="claims-list">{(example?.evaluation.claims ?? []).map((claim) => <article key={claim.claimId}><div><strong>{claim.title}</strong><em className={claim.status === "Supported" ? "status-positive" : "status-neutral"}>{claim.status}</em></div><p>{claim.statement}</p><footer><code>{claim.claimId}</code><span>{claim.reasonCode ?? "Observed"}</span></footer></article>)}</div>
          </section>
          <section className="evidence-section">
            <div className="section-title compact"><span>03</span><h2>已知覆盖缺口</h2></div>
            <ul className="intelligence-r5c-gaps">{(example?.dataset.coverageGaps ?? []).map((gap) => <li key={gap}>{gap}</li>)}</ul>
          </section>
        </aside>
      </main>
      <footer className="statusbar intelligence-r5c-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domain: <code>{manifest?.domainPackId ?? "intelligence.domain-pack@3"}</code></span><span>R5-D: {experimentPlan?.status ?? "Not planned"}</span><span>R5-E: {campaignReport?.campaignExecutionStatus ?? "Awaiting approval"}</span><span>R5-F: {impactReport?.impactGateStatus ?? "Not assessed"}</span><span>R5-G: {readinessDossier ? "Review ready" : "Not prepared"}</span><span className="statusbar-right">{shortHash(readinessDossier?.contentHash ?? impactReport?.contentHash ?? campaignReport?.contentHash ?? experimentPlan?.contentHash ?? example?.modelBundle.contentHash)} · Offline only</span></footer>
    </>
  );
}
