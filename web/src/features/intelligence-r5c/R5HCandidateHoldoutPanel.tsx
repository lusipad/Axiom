import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";

import type { FieldEvidenceAssessmentReport } from "../field-evidence/types";
import {
  assessR5HCandidateRealHoldout,
  registerR5HCandidateHoldoutStudy,
  stringifyJsonPreservingNegativeZero,
} from "./api";
import type {
  R5HCandidateHoldoutAssessment,
  R5HCandidateHoldoutCaseSpec,
  R5HCandidateHoldoutStudyRegistrationReport,
  R5GModelPromotionReadinessDossier,
  R5HManifest,
} from "./types";

const DEFAULT_CASES: R5HCandidateHoldoutCaseSpec[] = [
  {
    caseId: "field.r5h.candidate-case-a@1",
    assessmentId: "field.r5h.candidate-assessment-a@1",
    role: "in-domain",
    deviceId: "machine-a",
    conditionId: "cold-start",
    feedOverride: 0.65,
    samplePeriod: 0.04,
  },
  {
    caseId: "field.r5h.candidate-case-b@1",
    assessmentId: "field.r5h.candidate-assessment-b@1",
    role: "in-domain",
    deviceId: "machine-b",
    conditionId: "warm-steady",
    feedOverride: 0.825,
    samplePeriod: 0.08,
  },
  {
    caseId: "field.r5h.candidate-case-ood@1",
    assessmentId: "field.r5h.candidate-assessment-ood@1",
    role: "ood-probe",
    deviceId: "machine-c",
    conditionId: "unseen-load",
    feedOverride: 1,
    samplePeriod: 0.06,
  },
];

function statusClass(status?: string): string {
  if (status === "Passed" || status === "CaseScopedPassed") return "status-positive";
  if (status === "Blocked" || status === "Refuted") return "status-negative";
  return "status-neutral";
}

function shortHash(value?: string): string {
  return value ? `${value.slice(0, 9)}…${value.slice(-7)}` : "—";
}

function downloadJson(filename: string, value: unknown): void {
  const url = URL.createObjectURL(new Blob([stringifyJsonPreservingNegativeZero(value)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function R5HCandidateHoldoutPanel({
  manifest,
  readinessDossier,
}: {
  manifest: R5HManifest | null;
  readinessDossier: R5GModelPromotionReadinessDossier | null;
}) {
  const [studyId, setStudyId] = useState("axiom.intelligence.r5h.candidate-holdout-study@1");
  const [createdAt, setCreatedAt] = useState("");
  const [registeredAt, setRegisteredAt] = useState("");
  const [authorityId, setAuthorityId] = useState("");
  const [recordId, setRecordId] = useState("");
  const [cases, setCases] = useState<R5HCandidateHoldoutCaseSpec[]>(DEFAULT_CASES);
  const [registration, setRegistration] = useState<R5HCandidateHoldoutStudyRegistrationReport | null>(null);
  const [evidenceReports, setEvidenceReports] = useState<FieldEvidenceAssessmentReport[]>([]);
  const [assessment, setAssessment] = useState<R5HCandidateHoldoutAssessment | null>(null);
  const [registering, setRegistering] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRegistration(null);
    setEvidenceReports([]);
    setAssessment(null);
    setError(null);
  }, [readinessDossier?.contentHash]);

  const updateCase = (index: number, patch: Partial<R5HCandidateHoldoutCaseSpec>) => {
    setCases((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
    setRegistration(null);
    setEvidenceReports([]);
    setAssessment(null);
  };

  const registerStudy = async () => {
    if (!readinessDossier) return;
    setRegistering(true);
    setError(null);
    setAssessment(null);
    try {
      setRegistration(await registerR5HCandidateHoldoutStudy(readinessDossier, {
        studyId: studyId.trim(),
        createdAt: createdAt.trim(),
        registeredAt: registeredAt.trim(),
        registrationAuthorityId: authorityId.trim(),
        registrationRecordId: recordId.trim(),
        cases,
      }));
      setEvidenceReports([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R5-H 预注册失败。");
    } finally {
      setRegistering(false);
    }
  };

  const loadEvidence = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    setAssessment(null);
    setError(null);
    try {
      const parsed = (await Promise.all(files.map(async (file) => JSON.parse(await file.text()) as unknown))).flatMap((value) => Array.isArray(value) ? value : [value]);
      if (parsed.some((value) => typeof value !== "object" || value === null || (value as { schemaId?: string }).schemaId !== "axiom.field-evidence-assessment-report@1")) {
        throw new Error("每个文件都必须是 R4.1 FieldEvidenceAssessmentReport JSON。");
      }
      setEvidenceReports(parsed as FieldEvidenceAssessmentReport[]);
    } catch (reason) {
      setEvidenceReports([]);
      setError(reason instanceof Error ? reason.message : "R5-H 证据文件读取失败。");
    }
  };

  const assess = async () => {
    if (!readinessDossier || !registration) return;
    setAssessing(true);
    setError(null);
    try {
      setAssessment(await assessR5HCandidateRealHoldout(readinessDossier, registration, evidenceReports));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "R5-H 留出评估失败。");
    } finally {
      setAssessing(false);
    }
  };

  const formReady = Boolean(
    readinessDossier
    && studyId.trim()
    && createdAt.trim()
    && registeredAt.trim()
    && authorityId.trim()
    && recordId.trim()
    && cases.every((item) => item.caseId.trim() && item.assessmentId.trim() && item.deviceId.trim() && item.conditionId.trim() && Number.isFinite(item.feedOverride) && Number.isFinite(item.samplePeriod)),
  );

  return (
    <section className="report-card intelligence-r5h-holdout" aria-label="R5-H 候选真实留出验证">
      <div className="intelligence-r5d-heading">
        <div><span className="eyebrow">PRE-REGISTER → R4.1 FIELD EVIDENCE → CASE-SCOPED VERDICT</span><h2>R5-H 候选真实留出验证</h2><p>先冻结案例与完整 M5 指令，再导入现场采集形成的 R4.1 报告。周期头只使用精确规划器；线性误差头才计入现实证据。</p></div>
        <div className="intelligence-r5d-status"><strong className={statusClass(assessment?.overallStatus)}>{assessment?.overallStatus ?? (registration ? "Registered" : readinessDossier ? "Ready to register" : "Awaiting dossier")}</strong><span>{assessment?.realWorldGeneralizationStatus ?? "reality Open"}</span></div>
      </div>

      <div className="notice-card intelligence-r5h-boundary" role="note"><strong>{manifest?.safetyBanner ?? "CANDIDATE REAL HOLDOUT / CASE-SCOPED ONLY / NO MODEL ACTIVATION / NOT DEVICE SAFE"}</strong><p>外部登记时间与责任方属于所有者声明，Axiom 不做密码学验证；本页面不包含模型注册、激活、默认切换或设备写入动作。</p></div>
      {error && <div className="intelligence-r5h-error" role="alert">{error}</div>}

      {!readinessDossier ? (
        <div className="intelligence-r5d-empty"><strong>等待 R5-G 审查包</strong><p>只有确定性重放通过且已准备独立审查的候选，才能建立候选专属留出研究。</p></div>
      ) : !registration ? (
        <div className="intelligence-r5h-registration">
          <div className="intelligence-r5h-fields">
            <label><span>studyId</span><input aria-label="R5-H studyId" value={studyId} onChange={(event) => setStudyId(event.target.value)} /></label>
            <label><span>createdAt · ISO 8601 with offset</span><input aria-label="R5-H createdAt" placeholder="2026-08-14T08:00:00+08:00" value={createdAt} onChange={(event) => setCreatedAt(event.target.value)} /></label>
            <label><span>registeredAt · external record time</span><input aria-label="R5-H registeredAt" placeholder="2026-08-14T08:30:00+08:00" value={registeredAt} onChange={(event) => setRegisteredAt(event.target.value)} /></label>
            <label><span>registrationAuthorityId</span><input aria-label="R5-H registrationAuthorityId" value={authorityId} onChange={(event) => setAuthorityId(event.target.value)} /></label>
            <label><span>registrationRecordId</span><input aria-label="R5-H registrationRecordId" value={recordId} onChange={(event) => setRecordId(event.target.value)} /></label>
          </div>
          <div className="intelligence-r5c-table-wrap"><table className="intelligence-r5c-table intelligence-r5h-cases"><thead><tr><th>Role</th><th>Case / assessment</th><th>Device / condition</th><th>Feed</th><th>Δt</th></tr></thead><tbody>{cases.map((item, index) => <tr key={`${item.role}-${index}`}><td data-label="Role"><select aria-label={`R5-H case ${index + 1} role`} value={item.role} onChange={(event) => updateCase(index, { role: event.target.value as R5HCandidateHoldoutCaseSpec["role"] })}><option value="in-domain">in-domain</option><option value="ood-probe">ood-probe</option></select></td><td data-label="Case / assessment"><input aria-label={`R5-H case ${index + 1} caseId`} value={item.caseId} onChange={(event) => updateCase(index, { caseId: event.target.value })} /><input aria-label={`R5-H case ${index + 1} assessmentId`} value={item.assessmentId} onChange={(event) => updateCase(index, { assessmentId: event.target.value })} /></td><td data-label="Device / condition"><input aria-label={`R5-H case ${index + 1} deviceId`} value={item.deviceId} onChange={(event) => updateCase(index, { deviceId: event.target.value })} /><input aria-label={`R5-H case ${index + 1} conditionId`} value={item.conditionId} onChange={(event) => updateCase(index, { conditionId: event.target.value })} /></td><td data-label="Feed"><input aria-label={`R5-H case ${index + 1} feedOverride`} type="number" min="0.65" max="1" step="0.001" value={item.feedOverride} onChange={(event) => updateCase(index, { feedOverride: Number(event.target.value) })} /></td><td data-label="Δt · s"><input aria-label={`R5-H case ${index + 1} samplePeriod`} type="number" min="0.04" max="0.08" step="0.001" value={item.samplePeriod} onChange={(event) => updateCase(index, { samplePeriod: Number(event.target.value) })} /></td></tr>)}</tbody></table></div>
          <button className="button button-primary intelligence-r5h-action" type="button" onClick={() => void registerStudy()} disabled={!formReady || registering}>{registering ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◇</span>}{registering ? "精确规划并冻结中…" : "预注册并生成完整 M5 计划"}</button>
        </div>
      ) : (
        <div className="intelligence-r5h-study">
          <div className="intelligence-r5h-summary">
            <article><span>Registration</span><strong className="status-positive">{registration.registrationStatus}</strong><small>{registration.registration.registrationMethod}</small></article>
            <article><span>Cases</span><strong>{registration.manifest.cases.length}</strong><small>2 in-domain · 1 OOD probe minimum</small></article>
            <article><span>Evidence</span><strong>{evidenceReports.length} / {registration.manifest.cases.length}</strong><small>R4.1 reports in frozen order</small></article>
            <article><span>Mutation</span><strong>None</strong><small>registry · activation · device</small></article>
          </div>
          <div className="intelligence-r5h-study-actions">
            <button className="button" type="button" onClick={() => downloadJson(`${registration.registration.studyId}.registration.json`, registration)}>下载预注册包（含完整 M5）</button>
            <button className="button" type="button" onClick={() => { setRegistration(null); setEvidenceReports([]); setAssessment(null); }}>重新填写研究</button>
            <label className="button intelligence-r5h-upload"><input aria-label="导入 R5-H 现场证据" type="file" accept="application/json,.json" multiple onChange={(event) => void loadEvidence(event)} />导入 R4.1 现场证据</label>
            <button className="button button-primary" type="button" onClick={() => void assess()} disabled={assessing}>{assessing ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">◆</span>}{assessing ? "重放与评估中…" : `评估当前证据（${evidenceReports.length}/${registration.manifest.cases.length}）`}</button>
          </div>
          <div className="intelligence-r5h-identities"><span>manifest <code title={registration.manifest.contentHash}>{shortHash(registration.manifest.contentHash)}</code></span><span>registration <code title={registration.registration.contentHash}>{shortHash(registration.registration.contentHash)}</code></span><span>candidate <code title={registration.manifest.candidateModelBundleHash}>{shortHash(registration.manifest.candidateModelBundleHash)}</code></span></div>
          {evidenceReports.length > 0 && <ul className="intelligence-r5h-evidence-list">{evidenceReports.map((report) => <li key={report.assessmentId}><code>{report.assessmentId}</code><span className={statusClass(report.overallStatus)}>{report.overallStatus}</span><small>{shortHash(report.contentHash)}</small></li>)}</ul>}
        </div>
      )}

      {assessment && <div className="intelligence-r5h-result" aria-label="R5-H 留出评估结果">
        <div className="intelligence-r5h-summary"><article><span>Overall</span><strong className={statusClass(assessment.overallStatus)}>{assessment.overallStatus}</strong></article><article><span>Reality</span><strong className={statusClass(assessment.realWorldGeneralizationStatus)}>{assessment.realWorldGeneralizationStatus}</strong></article><article><span>Decision</span><strong>Pending human</strong><small>{assessment.reviewDecisionStatus}</small></article><article><span>Activation</span><strong>Not performed</strong><small>device write false</small></article></div>
        {assessment.targetResults.length > 0 && <div className="intelligence-r5c-table-wrap"><table className="intelligence-r5c-table"><thead><tr><th>Target</th><th>Evidence</th><th>Baseline RMSE</th><th>Candidate RMSE</th><th>Coverage</th><th>Status</th></tr></thead><tbody>{assessment.targetResults.map((target) => <tr key={target.targetId}><td>{target.targetId}</td><td>{target.evidenceSource}{target.countsTowardReality ? " · reality" : " · exact only"}</td><td>{target.baselineRmse.toPrecision(6)} {target.unit}</td><td>{target.candidateRmse.toPrecision(6)} {target.unit}</td><td>{(target.candidateIntervalCoverage * 100).toFixed(1)}%</td><td className={statusClass(target.status)}>{target.status}</td></tr>)}</tbody></table></div>}
        <div className="intelligence-r5h-checks">{assessment.checks.map((check) => <article key={check.checkId}><div><strong>{check.title}</strong><em className={statusClass(check.status)}>{check.status}</em></div><code>{check.checkId}</code><small>{check.reasonCode ?? "—"}</small></article>)}</div>
        <footer className="intelligence-r5e-boundary intelligence-r5h-result-boundary"><strong>{assessment.safetyBanner}</strong><span>Promotion: {assessment.modelPromotionStatus}</span><span>Default changed: false · registry write: false · activation: false</span></footer>
      </div>}
    </section>
  );
}
