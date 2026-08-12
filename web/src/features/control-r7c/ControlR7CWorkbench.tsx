import { ChangeEvent, useEffect, useRef, useState } from "react";

import type { Catalog } from "../../types";
import {
  assessR7CTransport,
  loadR7CExample,
  loadR7CManifest,
  loadR7CScenarios,
} from "./api";
import type {
  OpcUaTransportEvidence,
  R7CExamplePayload,
  R7CManifest,
  R7CScenarioSummary,
} from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return `${value.slice(0, 9)}…${value.slice(-7)}`;
}

function statusClass(value?: string): string {
  if (value === "Passed") return "status-positive";
  if (value === "Blocked") return "status-negative";
  return "status-neutral";
}

function importedEvidence(value: unknown): OpcUaTransportEvidence {
  if (!value || typeof value !== "object") throw new Error("JSON 必须是对象。");
  if ("transportEvidence" in value) {
    const nested = (value as { transportEvidence?: unknown }).transportEvidence;
    if (nested) return nested as OpcUaTransportEvidence;
  }
  if ((value as { schemaId?: string }).schemaId === "axiom.control.opcua-transport-evidence@1") {
    return value as OpcUaTransportEvidence;
  }
  throw new Error("没有找到 opcua-transport-evidence@1。");
}

export function ControlR7CWorkbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<R7CManifest | null>(null);
  const [scenarios, setScenarios] = useState<R7CScenarioSummary[]>([]);
  const [payload, setPayload] = useState<R7CExamplePayload | null>(null);
  const [selectedId, setSelectedId] = useState("opcua-transport-evidence-open");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const evidenceInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextScenarios, nextPayload] = await Promise.all([
          loadR7CManifest(), loadR7CScenarios(), loadR7CExample(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setScenarios(nextScenarios);
        setPayload(nextPayload);
        setSelectedId(nextManifest.defaultScenarioId);
      } catch (reason) {
        if (active.value) setError(reason instanceof Error ? reason.message : "R7-C 初始化失败。");
      } finally {
        if (active.value) setBusy(false);
      }
    })();
    return () => { active.value = false; };
  }, []);

  const runtimeBound = Boolean(
    catalog?.domainPacks.find((item) => item.domainPackId === "control.domain-pack@3")?.runtimeBound,
  );
  const evidence = payload?.transportEvidence;

  const loadScenario = async () => {
    setBusy(true);
    setError(null);
    try {
      setPayload(await loadR7CExample(selectedId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法载入 R7-C 合同案例。");
    } finally {
      setBusy(false);
    }
  };

  const importTransportEvidence = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const transportEvidence = importedEvidence(JSON.parse(await file.text()) as unknown);
      setPayload(await assessR7CTransport(transportEvidence));
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
    link.download = `${payload.readinessAudit.auditId}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>R7-C 未完成</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      <main className="workspace control-r7c-workspace">
        <aside className="config-panel control-r7c-config">
          <div className="panel-heading">
            <div><span className="eyebrow">OPC UA SHADOW · R7-C</span><h1>Windows 传输验收</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="notice-card control-r7c-boundary" role="note">
              <strong>VIRTUAL OPC UA ONLY · NO DEVICE WRITE</strong>
              <p>只证明 localhost 加密订阅合同；不代表厂商兼容、真实设备验证或上机安全。</p>
            </div>
            <div className="chip-row">
              <span className="chip">windows-only</span>
              <span className="chip">SignAndEncrypt</span>
              <span className={`chip ${runtimeBound ? "status-positive" : "status-neutral"}`}>{runtimeBound ? "runtime-bound" : "runtime-pending"}</span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>传输证据</h2><em>JSON only</em></div>
            <label className="field-label" htmlFor="r7c-scenario">内置边界案例</label>
            <select id="r7c-scenario" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              {scenarios.map((scenario) => <option key={scenario.scenarioId} value={scenario.scenarioId}>{scenario.title}</option>)}
            </select>
            <p>{scenarios.find((item) => item.scenarioId === selectedId)?.description ?? "正在加载场景…"}</p>
            <button className="button button-secondary control-r7c-action" type="button" onClick={() => void loadScenario()} disabled={busy}>恢复开放基线</button>
            <input ref={evidenceInput} type="file" accept="application/json,.json" aria-label="导入 OPC UA 传输证据 JSON" hidden onChange={(event) => void importTransportEvidence(event)} />
            <button className="button button-primary control-r7c-action" type="button" onClick={() => evidenceInput.current?.click()} disabled={busy}>{busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">⇧</span>}{busy ? "校验中…" : "导入 .NET 传输证据"}</button>
            <small className="control-r7c-help">只接受哈希闭合的 X/Y/Z/B/C 五轴证据；上传不能关闭现实门。</small>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>冻结实现</h2><em>v{manifest?.adapterVersion ?? "0.1.0"}</em></div>
            <dl className="data-list">
              <div><dt>Adapter</dt><dd>{manifest?.adapterId ?? "—"}</dd></div>
              <div><dt>Stack</dt><dd>{manifest?.protocolStack ?? "—"}</dd></div>
              <div><dt>Permission</dt><dd>Shadow</dd></div>
              <div><dt>Device write</dt><dd className="status-negative">FORBIDDEN</dd></div>
            </dl>
          </section>
        </aside>

        <section className="analysis-panel control-r7c-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Transport Audit</span><span>/</span><span>Reality Gate</span></div>
            <div className="run-state"><span className={statusClass(payload?.readinessAudit.virtualTransportStatus)}>{payload?.readinessAudit.virtualTransportStatus ?? "Loading"}</span><span className="status-neutral">vendor: Open</span><span className="status-neutral">reality: Open</span></div>
          </div>

          <div className="control-r7c-body">
            <section className="report-card control-r7c-hero">
              <div><span className="eyebrow">WINDOWS VIRTUAL TRANSPORT CONFORMANCE</span><h2>先证明安全地读到，再选择真实控制器</h2><p>固定证书、加密会话、非匿名身份、五轴完整订阅和零写操作共同构成传输证据；它只处于 Shadow 权限层。</p></div>
              <div className="control-r7c-verdict"><strong className={statusClass(payload?.readinessAudit.virtualTransportStatus)}>{payload?.readinessAudit.virtualTransportStatus ?? "—"}</strong><span>Shadow</span><small>reality evidence: None</small></div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>七项门禁</h2><em>{payload?.readinessAudit.checks.length ?? 0}/7</em></div>
              <div className="control-r7c-checks">
                {(payload?.readinessAudit.checks ?? []).map((check, index) => <article key={check.checkId} className={statusClass(check.status)}><b>{String(index + 1).padStart(2, "0")}</b><div><strong>{check.title}</strong><small>{check.reasonCode ?? check.checkId}</small></div><span>{check.status}</span></article>)}
              </div>
            </section>

            <div className="control-r7c-grid">
              <section className="report-card">
                <div className="section-title compact"><span>02</span><h2>Secure endpoint</h2><em>{evidence?.endpoint.messageSecurityMode ?? "missing"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Endpoint</dt><dd title={evidence?.endpoint.endpointUrl}>{evidence?.endpoint.endpointUrl ?? "—"}</dd></div>
                  <div><dt>Policy</dt><dd>{evidence?.endpoint.securityPolicyUri.split("#").at(-1) ?? "—"}</dd></div>
                  <div><dt>Identity</dt><dd>{evidence ? `${evidence.endpoint.identityType} · non-anonymous` : "—"}</dd></div>
                  <div><dt>Server pin</dt><dd>{shortHash(evidence?.endpoint.serverCertificateSha256)}</dd></div>
                </dl>
              </section>
              <section className="report-card">
                <div className="section-title compact"><span>03</span><h2>Subscription receipt</h2><em>{evidence?.receipt.status ?? "missing"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Items / frames</dt><dd>{evidence ? `${evidence.subscription.monitoredItemCount} / ${evidence.receipt.receivedFrameCount}` : "—"}</dd></div>
                  <div><dt>Samples / drops</dt><dd>{evidence ? `${evidence.receipt.receivedSampleCount} / ${evidence.receipt.droppedNotificationCount}` : "—"}</dd></div>
                  <div><dt>Subscribe / write</dt><dd>{evidence ? `${evidence.receipt.subscribeOperationCount} / ${evidence.receipt.writeOperationCount}` : "—"}</dd></div>
                  <div><dt>Method calls</dt><dd className={evidence ? "status-positive" : ""}>{evidence?.receipt.methodCallOperationCount ?? "—"}</dd></div>
                </dl>
              </section>
            </div>

            <section className="report-card">
              <div className="section-title compact"><span>04</span><h2>五轴通道合同</h2><em>{evidence?.channels.length ?? 0}/5</em></div>
              <div className="control-r7c-channels">
                {(evidence?.channels ?? ["X", "Y", "Z", "B", "C"].map((axis) => ({ axisId: axis, unit: ["X", "Y", "Z"].includes(axis) ? "mm" : "rad", channelId: "pending", canonicalSignalId: "pending" }))).map((channel) => <article key={channel.axisId}><strong>{channel.axisId}</strong><span>{channel.unit}</span><small>{channel.channelId}</small></article>)}
              </div>
            </section>

            <section className="report-card control-r7c-gates">
              <div className="section-title compact"><span>05</span><h2>证据边界</h2><button type="button" className="icon-button" onClick={downloadAudit} disabled={!payload} title="下载 R7-C 审计">⇩</button></div>
              <div><article><strong>Adapter contract</strong><span className="status-positive">Passed</span></article><article><strong>Virtual OPC UA</strong><span className={statusClass(payload?.readinessAudit.virtualTransportStatus)}>{payload?.readinessAudit.virtualTransportStatus ?? "Open"}</span></article><article><strong>Vendor adapter</strong><span className="status-neutral">Open</span></article><article><strong>Reality validation</strong><span className="status-neutral">Open</span></article><article><strong>Device / process safety</strong><span className="status-neutral">NotAssessed</span></article></div>
            </section>
          </div>
        </section>
      </main>
      <footer className="statusbar control-r7c-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domain: <code>{manifest?.domainPackId ?? "control.domain-pack@3"}</code></span><span className="statusbar-right">{shortHash(payload?.readinessAudit.contentHash)} · VIRTUAL ONLY · ZERO WRITE · REALITY OPEN</span></footer>
    </>
  );
}
