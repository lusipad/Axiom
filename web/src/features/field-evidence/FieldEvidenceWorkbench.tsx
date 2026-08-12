import { ChangeEvent, useEffect, useRef, useState } from "react";

import type { Catalog } from "../../types";
import {
  assessR41,
  assessR7E,
  loadR41Example,
  loadR41Manifest,
  loadR7EExample,
  loadR7EManifest,
} from "./api";
import type {
  GateStatus,
  R41AssessmentRequest,
  R41ExamplePayload,
  R41Manifest,
  R7EAssessmentRequest,
  R7EExamplePayload,
  R7EManifest,
} from "./types";
import "./styles.css";

function shortHash(value?: string): string {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function statusClass(value?: string): string {
  if (value === "Passed") return "status-positive";
  if (value === "Blocked" || value === "Refuted") return "status-negative";
  return "status-neutral";
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function r7eAssessment(value: unknown): R7EAssessmentRequest {
  if (!isObject(value)) throw new Error("R7-E JSON 必须是对象。");
  if (!isObject(value.readinessAudit)) return value as R7EAssessmentRequest;
  return {
    vendorProfile: isObject(value.vendorProfile) ? value.vendorProfile : null,
    runtimeEvidence: isObject(value.runtimeEvidence) ? value.runtimeEvidence : null,
    witnessProfile: isObject(value.witnessProfile) ? value.witnessProfile : null,
    controllerProfile: isObject(value.controllerProfile) ? value.controllerProfile : null,
    authority: isObject(value.authority) ? value.authority : null,
    captureAuthorization: isObject(value.captureAuthorization) ? value.captureAuthorization : null,
    command: isObject(value.command) ? value.command : null,
    shadowEvidence: isObject(value.shadowEvidence) ? value.shadowEvidence : null,
  };
}

function r41Assessment(value: unknown): R41AssessmentRequest {
  if (!isObject(value)) throw new Error("R4.1 JSON 必须是对象。");
  return {
    calibrationPair: isObject(value.calibrationPair) ? value.calibrationPair : null,
    validationPair: isObject(value.validationPair) ? value.validationPair : null,
    ...(typeof value.fitImprovementMinimum === "number"
      ? { fitImprovementMinimum: value.fitImprovementMinimum }
      : {}),
    ...(typeof value.excitationSpanMinimum === "number"
      ? { excitationSpanMinimum: value.excitationSpanMinimum }
      : {}),
    ...(typeof value.decompositionTolerance === "number"
      ? { decompositionTolerance: value.decompositionTolerance }
      : {}),
  };
}

function formatRatio(value?: number | null): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function gateLabel(status: GateStatus | undefined): string {
  return status ?? "Open";
}

export function FieldEvidenceWorkbench({ catalog }: { catalog: Catalog | null }) {
  const [r7eManifest, setR7EManifest] = useState<R7EManifest | null>(null);
  const [r7e, setR7E] = useState<R7EExamplePayload | null>(null);
  const [r41Manifest, setR41Manifest] = useState<R41Manifest | null>(null);
  const [r41, setR41] = useState<R41ExamplePayload | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const r7eInput = useRef<HTMLInputElement>(null);
  const r41Input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const active = { value: true };
    (async () => {
      try {
        const [nextR7EManifest, nextR7E, nextR41Manifest, nextR41] = await Promise.all([
          loadR7EManifest(), loadR7EExample(), loadR41Manifest(), loadR41Example(),
        ]);
        if (!active.value) return;
        setR7EManifest(nextR7EManifest);
        setR7E(nextR7E);
        setR41Manifest(nextR41Manifest);
        setR41(nextR41);
      } catch (reason) {
        if (active.value) setError(reason instanceof Error ? reason.message : "现场证据工作台初始化失败。");
      } finally {
        if (active.value) setBusy(false);
      }
    })();
    return () => { active.value = false; };
  }, []);

  const importR7E = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setR7E(await assessR7E(r7eAssessment(JSON.parse(await file.text()) as unknown)));
    } catch (reason) {
      setError(reason instanceof Error ? `R7-E 证据校验失败：${reason.message}` : "R7-E 证据校验失败。");
    } finally {
      setBusy(false);
    }
  };

  const importR41 = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setR41(await assessR41(r41Assessment(JSON.parse(await file.text()) as unknown)));
    } catch (reason) {
      setError(reason instanceof Error ? `R4.1 双运行校验失败：${reason.message}` : "R4.1 双运行校验失败。");
    } finally {
      setBusy(false);
    }
  };

  const r7eBound = Boolean(
    catalog?.domainPacks.find((item) => item.domainPackId === "control.domain-pack@5")?.runtimeBound,
  );
  const r41Bound = Boolean(
    catalog?.domainPacks.find((item) => item.domainPackId === "five-axis.domain-pack@7")?.runtimeBound,
  );
  const capture = r7e?.shadowEvidence;
  const calibrationReady = Boolean(r41?.calibrationPair);
  const validationReady = Boolean(r41?.validationPair);

  return (
    <>
      {error && <div className="error-banner" role="alert"><strong>现场证据未闭合</strong><span>{error}</span><button type="button" onClick={() => setError(null)}>×</button></div>}
      <main className="workspace field-evidence-workspace">
        <aside className="config-panel field-evidence-config">
          <div className="panel-heading">
            <div><span className="eyebrow">FIELD EVIDENCE · R7-E / R4.1</span><h1>现场证据工作台</h1></div>
            <span className="schema-badge">WIN</span>
          </div>

          <section className="config-section">
            <div className="notice-card field-boundary" role="note">
              <strong>READ / SUBSCRIBE ONLY · NOT DEVICE SAFE</strong>
              <p>此工作台只导入并核验证据，不写 PLC、不调用方法，也不授予试切或闭环控制权限。</p>
            </div>
            <div className="chip-row">
              <span className="chip">TwinCAT 3</span><span className="chip">Build 4026+</span><span className="chip">TF6100</span>
              <span className={`chip ${r7eBound && r41Bound ? "status-positive" : "status-neutral"}`}>{r7eBound && r41Bound ? "evaluators-bound" : "binding-open"}</span>
            </div>
          </section>

          <section className="config-section">
            <div className="section-title"><span>01</span><h2>证据入口</h2><em>JSON only</em></div>
            <input ref={r7eInput} hidden type="file" accept="application/json,.json" aria-label="导入 R7-E Shadow 证据 JSON" onChange={(event) => void importR7E(event)} />
            <button className="button button-primary field-action" type="button" disabled={busy} onClick={() => r7eInput.current?.click()}>{busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">⇧</span>}导入 R7-E Shadow 包</button>
            <small>接受完整 R7-E assessment 或 API 返回的 evidence payload；内容身份会在服务端重验。</small>
            <input ref={r41Input} hidden type="file" accept="application/json,.json" aria-label="导入 R4.1 双运行证据 JSON" onChange={(event) => void importR41(event)} />
            <button className="button button-secondary field-action" type="button" disabled={busy} onClick={() => r41Input.current?.click()}><span aria-hidden="true">⇧</span>导入 R4.1 双运行包</button>
            <small>必须包含不同采集授权、不同时间窗的 calibration 与 validation pair；不允许插值或重拟合 holdout。</small>
          </section>

          <section className="config-section">
            <div className="section-title"><span>02</span><h2>冻结协议</h2><em>exact index</em></div>
            <dl className="data-list compact-list">
              <div><dt>Platform</dt><dd>{r7eManifest?.supportedPlatforms.join(", ") ?? "Windows"}</dd></div>
              <div><dt>Capture</dt><dd>{r7eManifest?.capturePolicy ?? "sample-index-triggered-batch-read"}</dd></div>
              <div><dt>Alignment</dt><dd>{r7eManifest?.intervalPolicy ?? "exact-sample-index-no-interpolation"}</dd></div>
              <div><dt>Independent runs</dt><dd>{r41Manifest?.requiredIndependentRuns ?? 2}</dd></div>
              <div><dt>Write / Call</dt><dd className="status-positive">0 / 0</dd></div>
              <div><dt>Safety</dt><dd>NotAssessed</dd></div>
            </dl>
          </section>
        </aside>

        <section className="analysis-panel field-evidence-analysis">
          <div className="analysis-heading">
            <div className="view-tabs"><span>Shadow Witness</span><span>→</span><span>Reality Holdout</span></div>
            <div className="run-state"><span className={statusClass(r7e?.readinessAudit.deploymentShadowStatus)}>R7-E: {r7e?.readinessAudit.deploymentShadowStatus ?? "Open"}</span><span className={statusClass(r41?.analysis.realityValidationStatus)}>Reality: {r41?.analysis.realityValidationStatus ?? "Open"}</span></div>
          </div>

          <div className="field-evidence-body">
            <section className="report-card field-hero">
              <div><span className="eyebrow">WINDOWS · BECKHOFF · OBSERVATION ONLY</span><h2>从一条真实只读轨迹，到一项受限的现实声明</h2><p>R7-E 证明采集合同和部署 Shadow；R4.1 用独立校准/验证运行检验物理模型。两者都不等于 DeviceSafe。</p></div>
              <div className="field-verdict"><strong className={statusClass(r41?.analysis.realityValidationStatus)}>{r41?.analysis.realityValidationStatus ?? "Open"}</strong><span>Reality gate</span><small>{r41?.analysis.countsTowardReality ? "case-scoped evidence" : "external evidence missing"}</small></div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>证据链</h2><em>no implicit upgrade</em></div>
              <div className="field-chain" role="list">
                <article className={statusClass(r7e?.readinessAudit.deploymentShadowStatus)}><b>R7-D</b><strong>Vendor runtime</strong><span>{r7e?.runtimeEvidence ? "Bound" : "Open"}</span><small>TwinCAT / TF6100 / ACL</small></article>
                <article className={statusClass(r7e?.readinessAudit.deploymentShadowStatus)}><b>R7-E</b><strong>Shadow capture</strong><span>{r7e?.readinessAudit.deploymentShadowStatus ?? "Open"}</span><small>exact sample index</small></article>
                <article className={calibrationReady ? "status-positive" : "status-neutral"}><b>CAL</b><strong>Calibration run</strong><span>{calibrationReady ? "Bound" : "Missing"}</span><small>{shortHash(r41?.calibrationPair?.pairContentHash)}</small></article>
                <article className={validationReady ? "status-positive" : "status-neutral"}><b>VAL</b><strong>Holdout run</strong><span>{validationReady ? "Bound" : "Missing"}</span><small>{shortHash(r41?.validationPair?.pairContentHash)}</small></article>
                <article className={statusClass(r41?.analysis.realityValidationStatus)}><b>R4.1</b><strong>Reality gate</strong><span>{r41?.analysis.realityValidationStatus ?? "Open"}</span><small>single device / case scoped</small></article>
              </div>
            </section>

            <div className="field-grid">
              <section className="report-card">
                <div className="section-title compact"><span>02</span><h2>Shadow 收据</h2><em>{capture?.sourceKind ?? "no capture"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Witness binding</dt><dd>{r7e?.witnessProfile.bindingStatus ?? "Open"}</dd></div>
                  <div><dt>Frames</dt><dd>{capture?.frames.length ?? 0}</dd></div>
                  <div><dt>Batch reads</dt><dd>{capture?.receipt.readOperationCount ?? 0}</dd></div>
                  <div><dt>Dropped indices</dt><dd>{capture?.receipt.droppedSampleIndexCount ?? 0}</dd></div>
                  <div><dt>Writes</dt><dd className="status-positive">{capture?.receipt.writeOperationCount ?? 0}</dd></div>
                  <div><dt>Method calls</dt><dd className="status-positive">{capture?.receipt.methodCallOperationCount ?? 0}</dd></div>
                  <div><dt>Evidence</dt><dd title={capture?.contentHash}>{shortHash(capture?.contentHash)}</dd></div>
                </dl>
              </section>
              <section className="report-card">
                <div className="section-title compact"><span>03</span><h2>现实拟合</h2><em>separate units</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Alignment coverage</dt><dd>{((r41?.analysis.alignmentCoverage ?? 0) * 100).toFixed(0)}%</dd></div>
                  <div><dt>Linear improvement</dt><dd>{formatRatio(r41?.analysis.linearImprovementRatio)}</dd></div>
                  <div><dt>Rotary improvement</dt><dd>{formatRatio(r41?.analysis.rotaryImprovementRatio)}</dd></div>
                  <div><dt>Model fit</dt><dd className={statusClass(r41?.analysis.fitStatus)}>{r41?.analysis.fitStatus ?? "Open"}</dd></div>
                  <div><dt>Controlled trial</dt><dd>Open</dd></div>
                  <div><dt>Closed loop</dt><dd>Open</dd></div>
                  <div><dt>Analysis</dt><dd title={r41?.analysis.contentHash}>{shortHash(r41?.analysis.contentHash)}</dd></div>
                </dl>
              </section>
            </div>

            <section className="report-card">
              <div className="section-title compact"><span>04</span><h2>R7-E 采集门</h2><em>{r7e?.readinessAudit.checks.filter((check) => check.status === "Passed").length ?? 0}/{r7e?.readinessAudit.checks.length ?? 0}</em></div>
              <div className="field-checks">
                {(r7e?.readinessAudit.checks ?? []).map((check) => <article key={check.checkId} className={statusClass(check.status)}><strong>{check.title}</strong><span>{check.status}</span><small>{check.reasonCode ?? check.checkId}</small></article>)}
                {!r7e?.readinessAudit.checks.length && <p>正在载入采集合同…</p>}
              </div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>05</span><h2>R4.1 双运行门</h2><em>{r41?.analysis.checks.filter((check) => check.status === "Passed").length ?? 0}/8</em></div>
              <div className="field-checks reality-checks">
                {(r41?.analysis.checks ?? []).map((check) => <article key={check.checkId} className={statusClass(check.status)}><strong>{check.title}</strong><span>{gateLabel(check.status)}</span><small>{check.reasonCode ?? check.checkId}</small></article>)}
              </div>
            </section>

            <section className="report-card field-safety">
              <strong>NOT DEVICE SAFE</strong><span>Reality evidence is model-fit evidence, not execution authority.</span><small>Controlled trial: Open · Closed loop: Open · Device safety: NotAssessed · Process safety: NotAssessed</small>
            </section>
          </div>
        </section>
      </main>
      <footer className="statusbar field-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domains: <code>{r7eManifest?.domainPackId ?? "control.domain-pack@5"}</code> + <code>{r41Manifest?.domainPackId ?? "five-axis.domain-pack@7"}</code></span><span className="statusbar-right">{shortHash(r7e?.readinessAudit.contentHash)} · SHADOW {r7e?.readinessAudit.deploymentShadowStatus.toUpperCase() ?? "OPEN"} · REALITY {r41?.analysis.realityValidationStatus.toUpperCase() ?? "OPEN"}</span></footer>
    </>
  );
}
