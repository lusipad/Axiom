import { ChangeEvent, useEffect, useRef, useState } from "react";

import type { Catalog } from "../../types";
import {
  assessFieldEvidence,
  assessR7E,
  loadR41Example,
  loadR41Manifest,
  loadR7EExample,
  loadR7EManifest,
} from "./api";
import type {
  FieldEvidenceAssessmentReport,
  GateStatus,
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
  const runSpec = isObject(value.runSpec) ? value.runSpec : null;
  const runRequest = runSpec && isObject(runSpec.request) ? runSpec.request : null;
  const runCase = runRequest && isObject(runRequest.case) ? runRequest.case : null;
  return {
    caseId: typeof runCase?.caseId === "string" ? runCase.caseId : null,
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

function formatRatio(value?: number | null): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function gateLabel(status: GateStatus | undefined): string {
  return status ?? "Open";
}

export function FieldEvidenceWorkbench({ catalog }: { catalog: Catalog | null }) {
  const [r7eManifest, setR7EManifest] = useState<R7EManifest | null>(null);
  const [r7e, setR7E] = useState<R7EExamplePayload | null>(null);
  const [validationR7E, setValidationR7E] = useState<R7EExamplePayload | null>(null);
  const [r41Manifest, setR41Manifest] = useState<R41Manifest | null>(null);
  const [r41, setR41] = useState<R41ExamplePayload | null>(null);
  const [fieldReport, setFieldReport] = useState<FieldEvidenceAssessmentReport | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const r7eInput = useRef<HTMLInputElement>(null);
  const validationR7EInput = useRef<HTMLInputElement>(null);

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
        setValidationR7E(nextR7E);
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

  const importR7E = async (
    event: ChangeEvent<HTMLInputElement>,
    role: "calibration" | "validation",
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    setFieldReport(null);
    setR41(null);
    try {
      const assessment = await assessR7E(
        r7eAssessment(JSON.parse(await file.text()) as unknown),
      );
      if (role === "calibration") setR7E(assessment);
      else setValidationR7E(assessment);
    } catch (reason) {
      setError(reason instanceof Error ? `R7-E 证据校验失败：${reason.message}` : "R7-E 证据校验失败。");
    } finally {
      setBusy(false);
    }
  };

  const runFieldAssessment = async () => {
    if (!r7e || !validationR7E) return;
    setBusy(true);
    setError(null);
    setFieldReport(null);
    setR41(null);
    try {
      const report = await assessFieldEvidence({
        schemaId: "axiom.field-evidence-assessment-request@1",
        schemaVersion: 1,
        assessmentId: "axiom.field-evidence.web-assessment@1",
        calibrationPairId: "axiom.field-evidence.calibration@1",
        validationPairId: "axiom.field-evidence.validation@1",
        calibration: r7eAssessment(r7e),
        validation: r7eAssessment(validationR7E),
      });
      setFieldReport(report);
      setR7E(report.calibrationAssessment);
      setValidationR7E(report.validationAssessment);
      setR41(report.realityAssessment);
    } catch (reason) {
      setError(reason instanceof Error ? `现场双运行校验失败：${reason.message}` : "现场双运行校验失败。");
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
  const validationCapture = validationR7E?.shadowEvidence;
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
            <input ref={r7eInput} hidden type="file" accept="application/json,.json" aria-label="导入校准 R7-E Shadow 证据 JSON" onChange={(event) => void importR7E(event, "calibration")} />
            <button className="button button-secondary field-action" type="button" disabled={busy} onClick={() => r7eInput.current?.click()}>{busy ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">⇧</span>}导入校准 Shadow 包</button>
            <small>第一次真实只读采集用于拟合；完整 R7-E payload 的 Case 身份会被保留并重验。</small>
            <input ref={validationR7EInput} hidden type="file" accept="application/json,.json" aria-label="导入验证 R7-E Shadow 证据 JSON" onChange={(event) => void importR7E(event, "validation")} />
            <button className="button button-secondary field-action" type="button" disabled={busy} onClick={() => validationR7EInput.current?.click()}><span aria-hidden="true">⇧</span>导入验证 Shadow 包</button>
            <small>第二次采集必须属于同一 Case，且使用独立授权、时间窗与证据身份。</small>
            <button className="button button-primary field-action" type="button" disabled={busy || !r7e || !validationR7E} onClick={() => void runFieldAssessment()}>运行双证据验收</button>
            <small>服务端依次重放两个 R7-E 门，再执行 R4.1 留出验证；不允许插值或验证集重拟合。</small>
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
            <div className="run-state"><span className={statusClass(r7e?.readinessAudit.deploymentShadowStatus)}>CAL: {r7e?.readinessAudit.deploymentShadowStatus ?? "Open"}</span><span className={statusClass(validationR7E?.readinessAudit.deploymentShadowStatus)}>VAL: {validationR7E?.readinessAudit.deploymentShadowStatus ?? "Open"}</span><span className={statusClass(fieldReport?.overallStatus ?? r41?.analysis.realityValidationStatus)}>Reality: {fieldReport?.overallStatus ?? r41?.analysis.realityValidationStatus ?? "Open"}</span></div>
          </div>

          <div className="field-evidence-body">
            <section className="report-card field-hero">
              <div><span className="eyebrow">WINDOWS · BECKHOFF · OBSERVATION ONLY</span><h2>从两次真实只读轨迹，到一项受限的现实声明</h2><p>两次 R7-E 分别证明校准和验证采集合同；R4.1 只在同一 Case 的独立留出运行上检验物理模型。三者都不等于 DeviceSafe。</p></div>
              <div className="field-verdict"><strong className={statusClass(fieldReport?.overallStatus ?? r41?.analysis.realityValidationStatus)}>{fieldReport?.overallStatus ?? r41?.analysis.realityValidationStatus ?? "Open"}</strong><span>Reality gate</span><small>{fieldReport?.countsTowardReality ? "case-scoped evidence" : "external evidence missing"}</small></div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>01</span><h2>证据链</h2><em>no implicit upgrade</em></div>
              <div className="field-chain" role="list">
                <article className={statusClass(r7e?.readinessAudit.deploymentShadowStatus)}><b>R7-D</b><strong>Vendor runtime</strong><span>{r7e?.runtimeEvidence ? "Bound" : "Open"}</span><small>TwinCAT / TF6100 / ACL</small></article>
                <article className={statusClass(r7e?.readinessAudit.deploymentShadowStatus)}><b>CAL</b><strong>Calibration capture</strong><span>{r7e?.readinessAudit.deploymentShadowStatus ?? "Open"}</span><small>{calibrationReady ? shortHash(r41?.calibrationPair?.pairContentHash) : "exact sample index"}</small></article>
                <article className={statusClass(validationR7E?.readinessAudit.deploymentShadowStatus)}><b>VAL</b><strong>Holdout capture</strong><span>{validationR7E?.readinessAudit.deploymentShadowStatus ?? "Open"}</span><small>{validationReady ? shortHash(r41?.validationPair?.pairContentHash) : "independent run"}</small></article>
                <article className={statusClass(r41?.analysis.realityValidationStatus)}><b>R4.1</b><strong>Reality gate</strong><span>{r41?.analysis.realityValidationStatus ?? "Open"}</span><small>single device / case scoped</small></article>
              </div>
            </section>

            <div className="field-grid">
              <section className="report-card">
                <div className="section-title compact"><span>02</span><h2>Shadow 收据</h2><em>{capture?.sourceKind ?? "no capture"}</em></div>
                <dl className="data-list compact-list">
                  <div><dt>Witness binding</dt><dd>{r7e?.witnessProfile.bindingStatus ?? "Open"}</dd></div>
                  <div><dt>Calibration frames</dt><dd>{capture?.frames.length ?? 0}</dd></div>
                  <div><dt>Validation frames</dt><dd>{validationCapture?.frames.length ?? 0}</dd></div>
                  <div><dt>Batch reads</dt><dd>{(capture?.receipt.readOperationCount ?? 0) + (validationCapture?.receipt.readOperationCount ?? 0)}</dd></div>
                  <div><dt>Dropped indices</dt><dd>{(capture?.receipt.droppedSampleIndexCount ?? 0) + (validationCapture?.receipt.droppedSampleIndexCount ?? 0)}</dd></div>
                  <div><dt>Writes</dt><dd className="status-positive">{(capture?.receipt.writeOperationCount ?? 0) + (validationCapture?.receipt.writeOperationCount ?? 0)}</dd></div>
                  <div><dt>Method calls</dt><dd className="status-positive">{(capture?.receipt.methodCallOperationCount ?? 0) + (validationCapture?.receipt.methodCallOperationCount ?? 0)}</dd></div>
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
              <div className="section-title compact"><span>04</span><h2>校准 R7-E 采集门</h2><em>{r7e?.readinessAudit.checks.filter((check) => check.status === "Passed").length ?? 0}/{r7e?.readinessAudit.checks.length ?? 0}</em></div>
              <div className="field-checks">
                {(r7e?.readinessAudit.checks ?? []).map((check) => <article key={check.checkId} className={statusClass(check.status)}><strong>{check.title}</strong><span>{check.status}</span><small>{check.reasonCode ?? check.checkId}</small></article>)}
                {!r7e?.readinessAudit.checks.length && <p>正在载入采集合同…</p>}
              </div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>05</span><h2>验证 R7-E 采集门</h2><em>{validationR7E?.readinessAudit.checks.filter((check) => check.status === "Passed").length ?? 0}/{validationR7E?.readinessAudit.checks.length ?? 0}</em></div>
              <div className="field-checks">
                {(validationR7E?.readinessAudit.checks ?? []).map((check) => <article key={check.checkId} className={statusClass(check.status)}><strong>{check.title}</strong><span>{check.status}</span><small>{check.reasonCode ?? check.checkId}</small></article>)}
                {!validationR7E?.readinessAudit.checks.length && <p>正在载入验证采集合同…</p>}
              </div>
            </section>

            <section className="report-card">
              <div className="section-title compact"><span>06</span><h2>R4.1 双运行门</h2><em>{r41?.analysis.checks.filter((check) => check.status === "Passed").length ?? 0}/8</em></div>
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
      <footer className="statusbar field-statusbar"><span><i /> {error ? "1 error" : "0 errors"}</span><span>domains: <code>{r7eManifest?.domainPackId ?? "control.domain-pack@5"}</code> + <code>{r41Manifest?.domainPackId ?? "five-axis.domain-pack@7"}</code></span><span className="statusbar-right">{shortHash(fieldReport?.contentHash ?? r7e?.readinessAudit.contentHash)} · CAL {r7e?.readinessAudit.deploymentShadowStatus.toUpperCase() ?? "OPEN"} · VAL {validationR7E?.readinessAudit.deploymentShadowStatus.toUpperCase() ?? "OPEN"} · REALITY {(fieldReport?.overallStatus ?? r41?.analysis.realityValidationStatus)?.toUpperCase() ?? "OPEN"}</span></footer>
    </>
  );
}
