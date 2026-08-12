import { useEffect, useMemo, useState } from "react";

import type { Catalog } from "../../types";
import { loadR7Example, loadR7Manifest, loadR7Scenarios, replayR7Scenario } from "./api";
import type { R7ExamplePayload, R7Manifest, R7ScenarioSummary } from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return `${value.slice(0, 9)}…${value.slice(-7)}`;
}

function statusClass(value?: string): string {
  if (["Passed", "Admitted", "Completed", "WithinEnvelope", "BaselineRetained"].includes(value ?? "")) return "status-positive";
  if (["Blocked", "Breach", "RollbackVerified", "PromotionSuppressed"].includes(value ?? "")) return "status-negative";
  return "status-neutral";
}

export function ControlR7Workbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<R7Manifest | null>(null);
  const [scenarios, setScenarios] = useState<R7ScenarioSummary[]>([]);
  const [payload, setPayload] = useState<R7ExamplePayload | null>(null);
  const [selectedId, setSelectedId] = useState("synthetic-shadow-nominal");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextScenarios, nextPayload] = await Promise.all([
          loadR7Manifest(), loadR7Scenarios(), loadR7Example(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setScenarios(nextScenarios);
        setPayload(nextPayload);
      } catch (reason) {
        if (active.value) setError(reason instanceof Error ? reason.message : "R7 初始化失败。");
      } finally {
        if (active.value) setBusy(false);
      }
    })();
    return () => { active.value = false; };
  }, []);

  const runtimeBound = Boolean(catalog?.domainPacks.find((item) => item.domainPackId === "control.domain-pack@1")?.runtimeBound);
  const findings = useMemo(() => new Map(payload?.runtimeAudit.monitorFindings.map((item) => [item.sampleSequence, item])), [payload]);

  const replay = async () => {
    setBusy(true);
    setError(null);
    try {
      setPayload(await replayR7Scenario(selectedId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R7 Shadow 重放失败。");
    } finally {
      setBusy(false);
    }
  };

  const downloadAudit = () => {
    if (!payload) return;
    const blob = new Blob([JSON.stringify(payload.runtimeAudit, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${payload.runtimeAudit.auditId.replace(/[^a-z0-9.-]+/gi, "-")}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>R7 未完成</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      <main className="workspace control-r7-workspace">
        <aside className="config-panel control-r7-config">
          <div className="panel-heading">
            <div><span className="eyebrow">CONTROLLED RUNTIME · R7-A</span><h1>Shadow 安全合同</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="notice-card control-r7-boundary" role="note">
              <strong>NO DEVICE AUTHORITY</strong>
              <p>只重放、监控和审计。这里的 Stop 阻止晋级，不是机床急停或安全功能。</p>
            </div>
            <div className="chip-row"><span className="chip">windows-only</span><span className="chip">synthetic-shadow</span><span className={`chip ${runtimeBound ? "status-positive" : "status-neutral"}`}>{runtimeBound ? "runtime-bound" : "runtime-pending"}</span></div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>权限阶梯</h2><em>ceiling: Shadow</em></div>
            <ol className="control-r7-ladder" aria-label="权限阶梯">
              <li className="done"><b>01</b><span>Offline</span><small>R6 evidence</small></li>
              <li className="done"><b>02</b><span>Advisory</span><small>display only</small></li>
              <li className="active"><b>03</b><span>Shadow</span><small>synthetic contract</small></li>
              <li><b>04</b><span>Controlled Trial</span><small>Open</small></li>
              <li><b>05</b><span>Closed Loop</span><small>Open</small></li>
            </ol>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>故障场景</h2><em>{scenarios.length} cases</em></div>
            <label className="field-label" htmlFor="r7-scenario">冻结场景</label>
            <select id="r7-scenario" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              {scenarios.map((scenario) => <option key={scenario.scenarioId} value={scenario.scenarioId}>{scenario.title}</option>)}
            </select>
            <p>{scenarios.find((item) => item.scenarioId === selectedId)?.description ?? "正在加载场景…"}</p>
            <button className="button button-primary control-r7-replay" type="button" onClick={() => void replay()} disabled={busy || !payload}>
              {busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">▷</span>}{busy ? "重放状态机…" : "重放 Shadow 合同"}
            </button>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>控制包线</h2><em>fail closed</em></div>
            <dl className="data-list">
              <div><dt>线性误差</dt><dd>≤ {payload?.runtimeSpec.envelope.maximumLinearFollowingErrorMm ?? "—"} mm</dd></div>
              <div><dt>OOD fraction</dt><dd>≤ {payload?.runtimeSpec.envelope.maximumOodFraction ?? "—"}</dd></div>
              <div><dt>Monitor gap</dt><dd>≤ {payload?.runtimeSpec.envelope.maximumMonitorGapSeconds ?? "—"} s</dd></div>
              <div><dt>Device write</dt><dd className="status-negative">FORBIDDEN</dd></div>
            </dl>
          </section>
        </aside>

        <section className="analysis-panel control-r7-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Runtime Audit</span><span>/</span><span>Interlock Evidence</span></div>
            <div className="run-state"><span className={statusClass(payload?.runtimeAudit.finalState)}>{payload?.runtimeAudit.finalState ?? "Loading"}</span><span className="status-neutral">deployment: Open</span></div>
          </div>

          <div className="control-r7-body">
            <section className="report-card control-r7-hero">
              <div><span className="eyebrow">FAIL-CLOSED SHADOW REPLAY</span><h2>可执行的是证据状态机，不是机床安全功能</h2><p>AcceptanceRecord、控制包线、停止路径与基线保留都有独立身份；现实部署、受控试验与闭环授权仍保持 Open。</p></div>
              <div className="control-r7-verdict"><strong className={statusClass(payload?.runtimeAudit.admissionDecision.status)}>{payload?.runtimeAudit.admissionDecision.status ?? "—"}</strong><span>{payload?.runtimeAudit.acceptanceRecord.grantedPermission ?? "—"}</span><small>write = false</small></div>
            </section>

            <div className="control-r7-grid">
              <section className="report-card">
                <div className="section-title compact"><span>01</span><h2>状态迁移</h2><em>{payload?.runtimeAudit.transitions.length ?? 0} events</em></div>
                <ol className="control-r7-timeline">
                  {(payload?.runtimeAudit.transitions ?? []).map((item) => <li key={item.sequence} className={statusClass(item.toState)}><b>{String(item.sequence).padStart(2, "0")}</b><div><strong>{item.toState}</strong><small>{item.reasonCode}</small></div></li>)}
                </ol>
              </section>

              <section className="report-card">
                <div className="section-title compact"><span>02</span><h2>责任与批准</h2><em>independent record</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Disposition</dt><dd className={statusClass(payload?.runtimeAudit.acceptanceRecord.disposition)}>{payload?.runtimeAudit.acceptanceRecord.disposition ?? "—"}</dd></div>
                  <div><dt>Policy</dt><dd title={payload?.runtimeAudit.acceptanceRecord.responsibility.decisionPolicyId}>{payload?.runtimeAudit.acceptanceRecord.responsibility.decisionPolicyId ?? "—"}</dd></div>
                  <div><dt>Human approval</dt><dd>false</dd></div>
                  <div><dt>Device authority</dt><dd className="status-negative">false</dd></div>
                  <div><dt>Acceptance</dt><dd title={payload?.runtimeAudit.acceptanceRecord.contentHash}>{shortHash(payload?.runtimeAudit.acceptanceRecord.contentHash)}</dd></div>
                  <div><dt>Recommendation</dt><dd title={payload?.recommendationSet.contentHash}>{shortHash(payload?.recommendationSet.contentHash)}</dd></div>
                </dl>
              </section>
            </div>

            <section className="report-card">
              <div className="section-title compact"><span>03</span><h2>Shadow 监控</h2><em>{payload?.runtimeSpec.trace.sourceKind ?? "—"}</em></div>
              <div className="control-r7-samples">
                {(payload?.runtimeSpec.trace.samples ?? []).map((sample) => {
                  const finding = findings.get(sample.sequence);
                  return <article key={sample.sequence} className={finding?.status === "Breach" ? "breach" : ""}><span>t+{sample.timeSeconds.toFixed(2)}s</span><strong>{sample.linearFollowingErrorMm.toFixed(2)} mm</strong><small className={statusClass(finding?.status)}>{finding?.status ?? "Not evaluated"}</small></article>;
                })}
              </div>
            </section>

            <div className="control-r7-grid">
              <section className="report-card control-r7-receipt">
                <div className="section-title compact"><span>04</span><h2>Stop receipt</h2><em className={statusClass(payload?.runtimeAudit.stopReceipt.effect)}>{payload?.runtimeAudit.stopReceipt.effect ?? "—"}</em></div>
                <p>{payload?.runtimeAudit.stopReceipt.requested ? payload.runtimeAudit.stopReceipt.reasonCodes.join(" · ") : "本次重放没有触发包线越界。"}</p>
                <footer><span>device command</span><strong>false</strong><span>device ack</span><strong>false</strong></footer>
              </section>
              <section className="report-card control-r7-receipt">
                <div className="section-title compact"><span>05</span><h2>Rollback receipt</h2><em className={statusClass(payload?.runtimeAudit.rollbackReceipt.status)}>{payload?.runtimeAudit.rollbackReceipt.status ?? "—"}</em></div>
                <p>Shadow 不写设备；所谓回退只证明离线基线从未被修改。</p>
                <footer><span>write issued</span><strong>false</strong><span>readback</span><strong>false</strong></footer>
              </section>
            </div>

            <section className="report-card control-r7-gates">
              <div className="section-title compact"><span>06</span><h2>阶段门</h2><button type="button" className="icon-button" onClick={downloadAudit} disabled={!payload} title="下载审计 JSON">⇩</button></div>
              <div><article><strong>Synthetic contract</strong><span className="status-positive">Passed</span></article><article><strong>Deployment shadow</strong><span className="status-neutral">Open</span></article><article><strong>Controlled Trial</strong><span className="status-neutral">Open</span></article><article><strong>Closed Loop</strong><span className="status-neutral">Open</span></article><article><strong>Standards compliance</strong><span className="status-neutral">Not assessed</span></article></div>
            </section>
          </div>
        </section>
      </main>
      <footer className="statusbar control-r7-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domain: <code>{manifest?.domainPackId ?? "control.domain-pack@1"}</code></span><span className="statusbar-right">{shortHash(payload?.runtimeAudit.contentHash)} · SHADOW ONLY · NOT A DEVICE SAFETY CLAIM</span></footer>
    </>
  );
}

