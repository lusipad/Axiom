import { ChangeEvent, useEffect, useRef, useState } from "react";

import type { Catalog } from "../../types";
import {
  assessR7DEvidence,
  loadR7DExample,
  loadR7DManifest,
  loadR7DScenarios,
} from "./api";
import type {
  BeckhoffRuntimeEvidence,
  BeckhoffTwinCatProfile,
  R7DAssessmentRequest,
  R7DExamplePayload,
  R7DManifest,
  R7DScenarioSummary,
} from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function statusClass(value?: string): string {
  if (value === "Passed" || value === "Rejected" || value === "Full") return "status-positive";
  if (value === "Blocked" || value === "Accepted" || value === "Missing") return "status-negative";
  return "status-neutral";
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asProfile(value: unknown): BeckhoffTwinCatProfile {
  if (!isObject(value) || value.schemaId !== "axiom.control.beckhoff-twincat-profile@1") {
    throw new Error("证据包缺少 beckhoff-twincat-profile@1。");
  }
  return value as unknown as BeckhoffTwinCatProfile;
}

function asRuntimeEvidence(value: unknown): BeckhoffRuntimeEvidence {
  if (!isObject(value) || value.schemaId !== "axiom.control.beckhoff-runtime-evidence@1") {
    throw new Error("没有找到 beckhoff-runtime-evidence@1。");
  }
  return value as unknown as BeckhoffRuntimeEvidence;
}

function importedAssessment(
  value: unknown,
  current: R7DExamplePayload,
): R7DAssessmentRequest {
  if (!isObject(value)) throw new Error("JSON 必须是对象。");
  if (value.schemaId === "axiom.control.beckhoff-runtime-evidence@1") {
    return {
      profile: current.profile,
      runtimeEvidence: asRuntimeEvidence(value),
      transportEvidence: current.transportEvidence,
    };
  }
  if ("profile" in value) {
    return {
      profile: asProfile(value.profile),
      runtimeEvidence: value.runtimeEvidence == null
        ? null
        : asRuntimeEvidence(value.runtimeEvidence),
      transportEvidence: value.transportEvidence ?? null,
    };
  }
  throw new Error("请导入完整 R7-D 证据包，或单独的运行时证据。");
}

function downloadJson(value: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

export function ControlR7DWorkbench({ catalog }: { catalog: Catalog | null }) {
  const [manifest, setManifest] = useState<R7DManifest | null>(null);
  const [scenarios, setScenarios] = useState<R7DScenarioSummary[]>([]);
  const [payload, setPayload] = useState<R7DExamplePayload | null>(null);
  const [selectedId, setSelectedId] = useState("beckhoff-twincat-runtime-open");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const evidenceInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextManifest, nextScenarios, nextPayload] = await Promise.all([
          loadR7DManifest(), loadR7DScenarios(), loadR7DExample(),
        ]);
        if (!active.value) return;
        setManifest(nextManifest);
        setScenarios(nextScenarios);
        setPayload(nextPayload);
        setSelectedId(nextManifest.defaultScenarioId);
      } catch (reason) {
        if (active.value) setError(reason instanceof Error ? reason.message : "R7-D 初始化失败。");
      } finally {
        if (active.value) setBusy(false);
      }
    })();
    return () => { active.value = false; };
  }, []);

  const evaluatorBound = Boolean(
    catalog?.domainPacks.find((item) => item.domainPackId === "control.domain-pack@4")?.runtimeBound,
  );
  const profile = payload?.profile;
  const evidence = payload?.runtimeEvidence;

  const loadScenario = async () => {
    setBusy(true);
    setError(null);
    try {
      setPayload(await loadR7DExample(selectedId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法载入 R7-D 合同案例。");
    } finally {
      setBusy(false);
    }
  };

  const importEvidence = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !payload) return;
    setBusy(true);
    setError(null);
    try {
      const request = importedAssessment(JSON.parse(await file.text()) as unknown, payload);
      setPayload(await assessR7DEvidence(request));
    } catch (reason) {
      setError(reason instanceof Error ? `证据导入失败：${reason.message}` : "证据导入失败。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>R7-D 未完成</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      <main className="workspace control-r7d-workspace">
        <aside className="config-panel control-r7d-config">
          <div className="panel-heading">
            <div><span className="eyebrow">BECKHOFF VENDOR GATE · R7-D</span><h1>TwinCAT 厂商验收</h1></div>
            <span className="schema-badge">@1</span>
          </div>

          <section className="config-section">
            <div className="notice-card control-r7d-boundary" role="note">
              <strong>READ / SUBSCRIBE ONLY · REALITY OPEN</strong>
              <p>厂商 Profile 已冻结；没有真实 TwinCAT 证据时，运行时、部署 Shadow 与现实门始终保持 Open。</p>
            </div>
            <div className="chip-row">
              <span className="chip">Windows</span>
              <span className="chip">Build 4026+</span>
              <span className="chip">TF6100</span>
              <span className={`chip ${evaluatorBound ? "status-positive" : "status-neutral"}`}>{evaluatorBound ? "evaluator-bound" : "evaluator-pending"}</span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>证据入口</h2><em>JSON only</em></div>
            <label className="field-label" htmlFor="r7d-scenario">内置边界案例</label>
            <select id="r7d-scenario" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              {scenarios.map((scenario) => <option key={scenario.scenarioId} value={scenario.scenarioId}>{scenario.title}</option>)}
            </select>
            <p>{scenarios.find((item) => item.scenarioId === selectedId)?.description ?? "正在加载场景…"}</p>
            <button className="button button-secondary control-r7d-action" type="button" onClick={() => void loadScenario()} disabled={busy}>恢复开放基线</button>
            <input ref={evidenceInput} type="file" accept="application/json,.json" aria-label="导入 Beckhoff R7-D 证据 JSON" hidden onChange={(event) => void importEvidence(event)} />
            <button className="button button-primary control-r7d-action" type="button" onClick={() => evidenceInput.current?.click()} disabled={busy || !payload}>{busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">⇧</span>}{busy ? "校验中…" : "导入厂商证据包"}</button>
            <small className="control-r7d-help">开放 Profile 可配合 preflight 输出；绑定环境必须同时携带精确 Profile、runtime 与 R7-C transport 证据。</small>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>冻结目标</h2><em>v{manifest?.verifierVersion ?? "0.2.0"}</em></div>
            <dl className="data-list">
              <div><dt>Vendor</dt><dd>{manifest?.targetVendor ?? "—"}</dd></div>
              <div><dt>Controller</dt><dd>{manifest?.targetControllerFamily ?? "—"}</dd></div>
              <div><dt>Interface</dt><dd>{manifest?.targetInterface ?? "—"}</dd></div>
              <div><dt>Endpoint</dt><dd>{profile?.defaultEndpointUrl ?? "—"}</dd></div>
              <div><dt>Permission</dt><dd>Shadow</dd></div>
              <div><dt>Device write</dt><dd className="status-negative">FORBIDDEN</dd></div>
            </dl>
            <div className="control-r7d-downloads">
              <button type="button" className="icon-button" disabled={!profile} onClick={() => profile && downloadJson(profile, "beckhoff-twincat-profile.json")}>⇩ Profile</button>
              <button type="button" className="icon-button" disabled={!payload} onClick={() => payload && downloadJson(payload, `${payload.readinessAudit.auditId}.json`)}>⇩ Audit</button>
            </div>
          </section>
        </aside>

        <section className="analysis-panel control-r7d-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Vendor Audit</span><span>/</span><span>Reality Gate</span></div>
            <div className="run-state"><span className="status-positive">profile: Passed</span><span className={statusClass(payload?.readinessAudit.vendorRuntimeStatus)}>runtime: {payload?.readinessAudit.vendorRuntimeStatus ?? "Open"}</span><span className="status-neutral">reality: Open</span></div>
          </div>

          <div className="control-r7d-body">
            <section className="report-card control-r7d-hero">
              <div><span className="eyebrow">WINDOWS · TWINCAT 3 · TF6100</span><h2>把“支持 OPC UA”收紧为可审计的厂商事实</h2><p>安装包、许可证、BuildInfo、五轴节点访问级别、独立拒写收据与 R7-C 加密传输必须同时闭合；任何一项缺失都不会升级运行时结论。</p></div>
              <div className="control-r7d-verdict"><strong className={statusClass(payload?.readinessAudit.vendorRuntimeStatus)}>{payload?.readinessAudit.vendorRuntimeStatus ?? "Open"}</strong><span>Vendor runtime</span><small>reality evidence: none</small></div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>九项厂商门禁</h2><em>{payload?.readinessAudit.checks.filter((item) => item.status === "Passed").length ?? 0}/{payload?.readinessAudit.checks.length ?? 9}</em></div>
              <div className="control-r7d-checks">
                {(payload?.readinessAudit.checks ?? []).map((check, index) => <article key={check.checkId} className={statusClass(check.status)}><b>{String(index + 1).padStart(2, "0")}</b><div><strong>{check.title}</strong><small>{check.reasonCode ?? check.checkId}</small></div><span>{check.status}</span></article>)}
              </div>
            </section>

            <div className="control-r7d-grid">
              <section className="report-card">
                <div className="section-title compact"><span>02</span><h2>安装与许可</h2><em>{evidence?.installation.status ?? "missing"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>tcpkg</dt><dd>{evidence ? (evidence.installation.tcpkgAvailable ? "available" : "missing") : "—"}</dd></div>
                  <div><dt>TwinCAT build</dt><dd>{evidence?.installation.twinCatBuild ?? "—"}</dd></div>
                  <div><dt>Runtime packages</dt><dd>{evidence?.installation.packages.length ?? 0}/2</dd></div>
                  <div><dt>TF6100 license</dt><dd className={statusClass(evidence?.license.state)}>{evidence?.license.state ?? "Unknown"}</dd></div>
                  <div><dt>Probe reason</dt><dd>{evidence?.installation.reasonCode ?? "—"}</dd></div>
                </dl>
              </section>
              <section className="report-card">
                <div className="section-title compact"><span>03</span><h2>Server BuildInfo</h2><em>{evidence?.serverIdentity ? "bound" : "missing"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Product</dt><dd>{evidence?.serverIdentity?.productName ?? profile?.opcUaServerProduct ?? "—"}</dd></div>
                  <div><dt>Manufacturer</dt><dd>{evidence?.serverIdentity?.manufacturerName ?? "—"}</dd></div>
                  <div><dt>Software</dt><dd>{evidence?.serverIdentity?.softwareVersion ?? "—"}</dd></div>
                  <div><dt>Build</dt><dd>{evidence?.serverIdentity?.buildNumber ?? "—"}</dd></div>
                  <div><dt>Profile binding</dt><dd>{profile?.bindingStatus ?? "Open"}</dd></div>
                </dl>
              </section>
            </div>

            <section className="report-card">
              <div className="section-title compact"><span>04</span><h2>五轴只读节点</h2><em>{evidence?.channelAccess?.length ?? 0}/5 observed</em></div>
              <div className="control-r7d-channels">
                {(profile?.channels ?? []).map((channel) => {
                  const access = evidence?.channelAccess?.find((item) => item.axisId === channel.axisId);
                  return <article key={channel.axisId}><strong>{channel.axisId}</strong><span>{channel.unit}</span><small>{access?.identifier ?? channel.nodeBinding?.identifier ?? "binding open"}</small><b className={access?.accessLevel === 1 && access.userAccessLevel === 1 ? "status-positive" : "status-neutral"}>{access ? `A${access.accessLevel}/U${access.userAccessLevel}` : "not observed"}</b></article>;
                })}
              </div>
            </section>

            <section className="report-card control-r7d-permission">
              <div className="section-title compact"><span>05</span><h2>权限与证据边界</h2><em>independent verifier</em></div>
              <div className="control-r7d-permission-grid">
                <article><strong>Production adapter</strong><span className="status-positive">ZERO WRITE</span><small>read / subscribe only</small></article>
                <article><strong>Canary rejection</strong><span className={statusClass(evidence?.writeRejection.status)}>{evidence?.writeRejection.status ?? "NotRun"}</span><small>{evidence?.writeRejection.statusCode ?? "dedicated non-actuating node only"}</small></article>
                <article><strong>Deployment Shadow</strong><span className="status-neutral">Open</span><small>independent real capture missing</small></article>
                <article><strong>Reality validation</strong><span className="status-neutral">Open</span><small>countsTowardReality=false</small></article>
                <article><strong>Device / process safety</strong><span className="status-neutral">NotAssessed</span><small>no execution authority</small></article>
              </div>
            </section>
          </div>
        </section>
      </main>
      <footer className="statusbar control-r7d-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domain: <code>{manifest?.domainPackId ?? "control.domain-pack@4"}</code></span><span className="statusbar-right">{shortHash(payload?.readinessAudit.contentHash)} · BECKHOFF PROFILE · VENDOR {payload?.readinessAudit.vendorRuntimeStatus?.toUpperCase() ?? "OPEN"} · REALITY OPEN</span></footer>
    </>
  );
}
