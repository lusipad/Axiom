import { ChangeEvent, useEffect, useRef, useState } from "react";

import type { Catalog } from "../../types";
import {
  assessR7BEvidence,
  loadR7BExample,
  loadR7BManifest,
  loadR7BScenarios,
} from "./api";
import type {
  R7BEvidenceSet,
  R7BExamplePayload,
  R7BManifest,
  R7BScenarioSummary,
} from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return `${value.slice(0, 9)}…${value.slice(-7)}`;
}

function statusClass(value?: string): string {
  if (value === "Passed" || value === "Verified" || value === "Selected") return "status-positive";
  if (value === "Blocked" || value === "Failed") return "status-negative";
  return "status-neutral";
}

function importedEvidence(value: unknown): R7BEvidenceSet {
  if (!value || typeof value !== "object") throw new Error("JSON 必须是对象。");
  if ("evidenceSet" in value) {
    const nested = (value as { evidenceSet?: unknown }).evidenceSet;
    if (nested) return nested as R7BEvidenceSet;
  }
  if ((value as { schemaId?: string }).schemaId === "axiom.control.deployment-shadow-evidence-set@1") {
    return value as R7BEvidenceSet;
  }
  throw new Error("没有找到 deployment-shadow-evidence-set@1。");
}

export function ControlR7BWorkbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<R7BManifest | null>(null);
  const [scenarios, setScenarios] = useState<R7BScenarioSummary[]>([]);
  const [payload, setPayload] = useState<R7BExamplePayload | null>(null);
  const [selectedId, setSelectedId] = useState("deployment-shadow-readiness-open");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const evidenceInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextScenarios, nextPayload] = await Promise.all([
          loadR7BManifest(), loadR7BScenarios(), loadR7BExample(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setScenarios(nextScenarios);
        setPayload(nextPayload);
        setSelectedId(nextManifest.defaultScenarioId);
      } catch (reason) {
        if (active.value) setError(reason instanceof Error ? reason.message : "R7-B 初始化失败。");
      } finally {
        if (active.value) setBusy(false);
      }
    })();
    return () => { active.value = false; };
  }, []);

  const runtimeBound = Boolean(catalog?.domainPacks.find((item) => item.domainPackId === "control.domain-pack@2")?.runtimeBound);
  const evidence = payload?.evidenceSet;

  const loadScenario = async () => {
    setBusy(true);
    setError(null);
    try {
      setPayload(await loadR7BExample(selectedId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法载入 R7-B 证据案例。");
    } finally {
      setBusy(false);
    }
  };

  const importEvidence = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const evidenceSet = importedEvidence(JSON.parse(await file.text()) as unknown);
      setPayload(await assessR7BEvidence(evidenceSet));
    } catch (reason) {
      setError(reason instanceof Error ? `证据导入失败：${reason.message}` : "证据导入失败。");
    } finally {
      setBusy(false);
    }
  };

  const downloadAudit = () => {
    if (!payload) return;
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${payload.readinessAudit.auditId.replace(/[^a-z0-9.-]+/gi, "-")}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>R7-B 未完成</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      <main className="workspace control-r7b-workspace">
        <aside className="config-panel control-r7b-config">
          <div className="panel-heading">
            <div><span className="eyebrow">DEPLOYMENT SHADOW · R7-B</span><h1>真实接入就绪性</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="notice-card control-r7b-boundary" role="note">
              <strong>READINESS ONLY · NO DEVICE WRITE</strong>
              <p>这里只验证外部证据、控制器端只读权限和采集完整性；不会连接、控制或授权机床。</p>
            </div>
            <div className="chip-row"><span className="chip">windows-only</span><span className="chip">vendor-unselected</span><span className={`chip ${runtimeBound ? "status-positive" : "status-neutral"}`}>{runtimeBound ? "runtime-bound" : "runtime-pending"}</span></div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>权限阶梯</h2><em>ceiling: Shadow</em></div>
            <ol className="control-r7b-ladder" aria-label="R7-B 权限阶梯">
              <li className="done"><b>01</b><span>Offline</span><small>evidence</small></li>
              <li className="done"><b>02</b><span>Advisory</span><small>display only</small></li>
              <li className="active"><b>03</b><span>Shadow readiness</span><small>current</small></li>
              <li><b>04</b><span>Deployment Shadow</span><small>Open</small></li>
              <li><b>05</b><span>Controlled Trial</span><small>Open</small></li>
              <li><b>06</b><span>Closed Loop</span><small>Open</small></li>
            </ol>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>证据输入</h2><em>JSON only</em></div>
            <label className="field-label" htmlFor="r7b-scenario">内置合同案例</label>
            <select id="r7b-scenario" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              {scenarios.map((scenario) => <option key={scenario.scenarioId} value={scenario.scenarioId}>{scenario.title}</option>)}
            </select>
            <p>{scenarios.find((item) => item.scenarioId === selectedId)?.description ?? "正在加载场景…"}</p>
            <button className="button button-secondary control-r7b-action" type="button" onClick={() => void loadScenario()} disabled={busy}>载入合同案例</button>
            <input ref={evidenceInput} type="file" accept="application/json,.json" aria-label="导入外部证据 JSON" hidden onChange={(event) => void importEvidence(event)} />
            <button className="button button-primary control-r7b-action" type="button" onClick={() => evidenceInput.current?.click()} disabled={busy}>{busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">⇧</span>}{busy ? "校验中…" : "导入外部证据"}</button>
            <small className="control-r7b-help">导入只触发 schema、哈希和就绪性校验；任何 JSON 都不能自行声明现实门已闭合。</small>
          </section>

          <section className="config-section">
            <div className="section-title"><span>03</span><h2>控制器目标</h2><em>{evidence?.controllerProfile.targetStatus ?? "Unselected"}</em></div>
            <dl className="data-list">
              <div><dt>Vendor</dt><dd>{evidence?.controllerProfile.vendor ?? "未选择"}</dd></div>
              <div><dt>Family</dt><dd>{evidence?.controllerProfile.controllerFamily ?? "—"}</dd></div>
              <div><dt>Interface</dt><dd>{evidence?.controllerProfile.interfaceType ?? "—"}</dd></div>
              <div><dt>Device write</dt><dd className="status-negative">FORBIDDEN</dd></div>
            </dl>
          </section>
        </aside>

        <section className="analysis-panel control-r7b-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Readiness Audit</span><span>/</span><span>External Evidence</span></div>
            <div className="run-state"><span className={statusClass(payload?.readinessAudit.readinessOutcome)}>{payload?.readinessAudit.readinessOutcome ?? "Loading"}</span><span className="status-neutral">reality: Open</span></div>
          </div>

          <div className="control-r7b-body">
            <section className="report-card control-r7b-hero">
              <div><span className="eyebrow">VENDOR-NEUTRAL READINESS GATE</span><h2>先证明“只能以最小权限只读采集”，再谈真实部署</h2><p>目标控制器、控制器强制的最小权限、版本化 Adapter、时间与信号映射缺一不可。当前结果不产生 DeviceSafe、ProcessSafe 或上机许可。</p></div>
              <div className="control-r7b-verdict"><strong className={statusClass(payload?.readinessAudit.readinessOutcome)}>{payload?.readinessAudit.readinessOutcome ?? "—"}</strong><span>{payload?.readinessAudit.permissionCeiling ?? "Shadow"}</span><small>reality evidence: None</small></div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>七项就绪检查</h2><em>{payload?.readinessAudit.checks.length ?? 0}/7</em></div>
              <div className="control-r7b-checks">
                {(payload?.readinessAudit.checks ?? []).map((check, index) => <article key={check.checkId} className={statusClass(check.status)}><b>{String(index + 1).padStart(2, "0")}</b><div><strong>{check.title}</strong><small>{check.reasonCode ?? check.checkId}</small></div><span>{check.status}</span></article>)}
              </div>
            </section>

            <div className="control-r7b-grid">
              <section className="report-card">
                <div className="section-title compact"><span>02</span><h2>只读权限证据</h2><em>{evidence?.authority.verificationStatus ?? "missing"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Enforcement</dt><dd>{evidence?.authority.enforcementPoint ?? "controller required"}</dd></div>
                  <div><dt>Principal</dt><dd>{evidence?.authority.principalId ?? "—"}</dd></div>
                  <div><dt>Granted</dt><dd>{evidence?.authority.grantedOperations.join(" · ") ?? "—"}</dd></div>
                  <div><dt>Denied</dt><dd>{evidence?.authority.deniedOperations.length ?? 0} operations</dd></div>
                </dl>
              </section>
              <section className="report-card">
                <div className="section-title compact"><span>03</span><h2>Adapter receipt</h2><em>{evidence?.adapterReceipt.status ?? "missing"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Adapter</dt><dd>{evidence?.adapterReceipt.adapterId ?? "—"}</dd></div>
                  <div><dt>Access</dt><dd>{evidence?.adapterReceipt.accessMode ?? "—"}</dd></div>
                  <div><dt>Read / write</dt><dd>{evidence ? `${evidence.adapterReceipt.readOperationCount} / ${evidence.adapterReceipt.writeOperationCount}` : "—"}</dd></div>
                  <div><dt>Samples / drop</dt><dd>{evidence ? `${evidence.adapterReceipt.receivedSampleCount} / ${evidence.adapterReceipt.droppedSampleCount}` : "—"}</dd></div>
                </dl>
              </section>
            </div>

            <div className="control-r7b-grid">
              <section className="report-card">
                <div className="section-title compact"><span>04</span><h2>采集来源</h2><em>{evidence?.capture.sourceKind ?? "missing"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Declared real</dt><dd className={statusClass(evidence?.capture.declaredReal ? "Verified" : "Open")}>{String(evidence?.capture.declaredReal ?? false)}</dd></div>
                  <div><dt>Frames</dt><dd>{evidence?.capture.frames.length ?? 0}</dd></div>
                  <div><dt>External</dt><dd>{String(evidence?.provenance.capturedOutsideRepository ?? false)}</dd></div>
                  <div><dt>Authorized</dt><dd>{String(evidence?.provenance.evaluationAuthorized ?? false)}</dd></div>
                </dl>
              </section>
              <section className="report-card">
                <div className="section-title compact"><span>05</span><h2>时钟与信号</h2><em>{evidence?.clockSignalBinding.clockMethod ?? "missing"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Coverage</dt><dd>{evidence ? `${(evidence.clockSignalBinding.coverageFraction * 100).toFixed(1)}%` : "—"}</dd></div>
                  <div><dt>Observed gap</dt><dd>{evidence ? `${evidence.clockSignalBinding.maximumObservedGapMs} ms` : "—"}</dd></div>
                  <div><dt>Required max</dt><dd>{evidence ? `${evidence.clockSignalBinding.requiredMaximumGapMs} ms` : "—"}</dd></div>
                  <div><dt>Mappings</dt><dd>{evidence?.clockSignalBinding.signalMappings.length ?? 0}</dd></div>
                </dl>
              </section>
            </div>

            <section className="report-card control-r7b-gates">
              <div className="section-title compact"><span>06</span><h2>阶段门</h2><button type="button" className="icon-button" onClick={downloadAudit} disabled={!payload} title="下载就绪性证据">⇩</button></div>
              <div><article><strong>Typed contract</strong><span className="status-positive">Passed</span></article><article><strong>Vendor adapter</strong><span className="status-neutral">Open</span></article><article><strong>Deployment Shadow</strong><span className="status-neutral">Open</span></article><article><strong>Controlled Trial</strong><span className="status-neutral">Open</span></article><article><strong>Closed Loop</strong><span className="status-neutral">Open</span></article></div>
            </section>
          </div>
        </section>
      </main>
      <footer className="statusbar control-r7b-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domain: <code>{manifest?.domainPackId ?? "control.domain-pack@2"}</code></span><span className="statusbar-right">{shortHash(payload?.readinessAudit.contentHash)} · READINESS ONLY · NO DEVICE WRITE · REALITY OPEN</span></footer>
    </>
  );
}
