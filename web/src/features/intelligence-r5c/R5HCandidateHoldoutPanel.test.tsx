import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { stringifyJsonPreservingNegativeZero } from "./api";
import { R5HCandidateHoldoutPanel } from "./R5HCandidateHoldoutPanel";
import type {
  R5HCandidateHoldoutAssessment,
  R5HCandidateHoldoutCasePlan,
  R5HCandidateHoldoutStudyRegistrationReport,
  R5GModelPromotionReadinessDossier,
  R5HManifest,
} from "./types";

const r5hManifest: R5HManifest = {
  manifestId: "axiom.intelligence.r5h-manifest@1",
  schemaId: "axiom.intelligence.r5h-manifest@1",
  schemaVersion: 1,
  stage: "R5-H",
  platform: "windows",
  reviewScope: "candidate-case-scoped-real-holdout",
  sourceDossierSchemaId: "axiom.intelligence.model-promotion-readiness-dossier@1",
  requiredEvidenceSchemaId: "axiom.field-evidence-assessment-report@1",
  bundledRealEvidencePresent: false,
  realWorldGeneralizationStatus: "Open",
  modelRegistryWriteAllowed: false,
  activationAllowed: false,
  automaticDeploymentAllowed: false,
  deviceWriteAllowed: false,
  checkIds: Array.from({ length: 8 }, (_, index) => `r5h.check-${index}@1`),
  targetIds: ["cycleTimeSeconds", "linearFollowingErrorMaxMm"],
  safetyBanner: "CANDIDATE REAL HOLDOUT / CASE-SCOPED ONLY / AWAITING INDEPENDENT HUMAN DECISION / NO MODEL ACTIVATION / NOT DEVICE SAFE",
};

const readinessDossier: R5GModelPromotionReadinessDossier = {
  schemaId: "axiom.intelligence.model-promotion-readiness-dossier@1",
  dossierId: "candidate-promotion-readiness@1",
  request: { preparedBy: "reviewer", reviewScope: "synthetic-offline-review", contentHash: "1".repeat(64) },
  sourceCampaignReportHash: "2".repeat(64),
  sourceImpactReportHash: "3".repeat(64),
  replayedImpactReportHash: "3".repeat(64),
  baselineModelBundleHash: "4".repeat(64),
  candidateModelBundleHash: "5".repeat(64),
  candidateContextHash: "6".repeat(64),
  readinessChecks: [],
  remainingGates: [],
  reviewReadinessStatus: "ReadyForIndependentReview",
  reviewDecisionStatus: "AwaitingIndependentHumanDecision",
  candidateUseStatus: "EvaluatedOnly",
  modelPromotionStatus: "NotPerformed",
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  defaultModelChanged: false,
  modelRegistryWritePerformed: false,
  activationPerformed: false,
  automaticDeploymentAllowed: false,
  deviceWriteAllowed: false,
  safetyBanner: r5hManifest.safetyBanner,
  contentHash: "a".repeat(64),
};

function casePlan(index: number, role: "in-domain" | "ood-probe"): R5HCandidateHoldoutCasePlan {
  return {
    caseId: `field.r5h.candidate-case-${index}@1`,
    assessmentId: `field.r5h.candidate-assessment-${index}@1`,
    role,
    deviceId: `machine-${index}`,
    conditionId: `condition-${index}`,
    feedOverride: index === 1 ? 0.65 : index === 2 ? 0.825 : 1,
    samplePeriod: index === 1 ? 0.04 : index === 2 ? 0.08 : 0.06,
    exactOperatingPoint: {
      plannedM4ContentHash: String(index).repeat(64),
      plannedM5ContentHash: String(index + 3).repeat(64),
      exactCycleTimeSeconds: 1,
      commandSampleCount: 2,
      numericEnvironment: { python: "3.12" },
    },
    plannedCommand: {
      contentId: String(index + 3).repeat(64),
      sourceM4ContentId: String(index).repeat(64),
      samplePeriod: index === 1 ? 0.04 : index === 2 ? 0.08 : 0.06,
      duration: 1,
      samples: [{ position: [-0, 0, 0] }],
    },
    contentHash: String(index + 6).repeat(64),
  };
}

const registrationReport: R5HCandidateHoldoutStudyRegistrationReport = {
  schemaId: "axiom.intelligence.candidate-holdout-study-registration-report@1",
  schemaVersion: 1,
  requestContentHash: "b".repeat(64),
  manifest: {
    artifactType: "axiom.intelligence.candidate-holdout-study-manifest",
    schemaId: "axiom.intelligence.candidate-holdout-study-manifest@1",
    schemaVersion: 1,
    studyId: "axiom.intelligence.r5h.candidate-holdout-study@1",
    readinessDossierContentHash: readinessDossier.contentHash,
    baselineModelBundleHash: readinessDossier.baselineModelBundleHash,
    candidateModelBundleHash: readinessDossier.candidateModelBundleHash,
    createdAt: "2026-08-14T08:00:00+08:00",
    maximumCandidateRmseRegressionRatio: 0,
    minimumCandidateIntervalCoverage: 1,
    minimumInDomainCases: 2,
    minimumDevices: 2,
    minimumConditions: 2,
    oodProbeRequired: true,
    cases: [casePlan(1, "in-domain"), casePlan(2, "in-domain"), casePlan(3, "ood-probe")],
    platform: "windows",
    contentHash: "c".repeat(64),
  },
  registration: {
    artifactType: "axiom.intelligence.candidate-holdout-study-registration",
    schemaId: "axiom.intelligence.candidate-holdout-study-registration@1",
    schemaVersion: 1,
    studyId: "axiom.intelligence.r5h.candidate-holdout-study@1",
    manifestContentHash: "c".repeat(64),
    registeredAt: "2026-08-14T08:30:00+08:00",
    registrationAuthorityId: "model-owner",
    registrationRecordId: "external-record-001",
    registrationMethod: "external-owner-attestation",
    trustBoundary: "external authority attestation; not cryptographically verified by Axiom",
    contentHash: "d".repeat(64),
  },
  registrationStatus: "Passed",
  realWorldGeneralizationStatus: "Open",
  modelPromotionStatus: "NotPerformed",
  modelRegistryWritePerformed: false,
  activationPerformed: false,
  deviceWriteAllowed: false,
  safetyBanner: r5hManifest.safetyBanner,
  contentHash: "e".repeat(64),
};

const openAssessment: R5HCandidateHoldoutAssessment = {
  artifactType: "axiom.intelligence.candidate-real-holdout-assessment",
  schemaId: "axiom.intelligence.candidate-real-holdout-assessment@1",
  schemaVersion: 1,
  assessmentId: "axiom.intelligence.r5h.candidate-holdout-assessment@1",
  checks: r5hManifest.checkIds.map((checkId, index) => ({
    checkId,
    title: `Check ${index + 1}`,
    status: index < 2 ? "Passed" : "Open",
    reasonCode: index < 2 ? "Passed" : "RealEvidenceMissing",
    details: {},
  })),
  caseResults: [],
  targetResults: [],
  overallStatus: "Open",
  realWorldGeneralizationStatus: "Open",
  reviewDecisionStatus: "AwaitingIndependentHumanDecision",
  candidateUseStatus: "EvaluatedOnly",
  modelPromotionStatus: "NotPerformed",
  defaultModelChanged: false,
  modelRegistryWritePerformed: false,
  activationPerformed: false,
  automaticDeploymentAllowed: false,
  deviceWriteAllowed: false,
  permissionLevel: "Offline",
  safetyBanner: r5hManifest.safetyBanner,
  contentHash: "f".repeat(64),
};

function response(value: unknown): Promise<Response> {
  return Promise.resolve(new Response(stringifyJsonPreservingNegativeZero(value), { status: 200, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => vi.restoreAllMocks());

it("预注册完整 M5 研究并在缺少现场证据时保持 Open", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.endsWith("/r5h/studies/register")) return response(registrationReport);
    if (url.endsWith("/r5h/holdout/assess")) return response(openAssessment);
    throw new Error(`unexpected request: ${url}`);
  });
  render(<R5HCandidateHoldoutPanel manifest={r5hManifest} readinessDossier={readinessDossier} />);

  fireEvent.change(screen.getByLabelText("R5-H createdAt"), { target: { value: "2026-08-14T08:00:00+08:00" } });
  fireEvent.change(screen.getByLabelText("R5-H registeredAt"), { target: { value: "2026-08-14T08:30:00+08:00" } });
  fireEvent.change(screen.getByLabelText("R5-H registrationAuthorityId"), { target: { value: "model-owner" } });
  fireEvent.change(screen.getByLabelText("R5-H registrationRecordId"), { target: { value: "external-record-001" } });
  const register = screen.getByRole("button", { name: "预注册并生成完整 M5 计划" });
  expect(register).toBeEnabled();
  fireEvent.click(register);

  await screen.findByText("external-owner-attestation");
  expect(screen.getByRole("button", { name: "下载预注册包（含完整 M5）" })).toBeInTheDocument();
  const assess = screen.getByRole("button", { name: "评估当前证据（0/3）" });
  fireEvent.click(assess);

  const result = await screen.findByLabelText("R5-H 留出评估结果");
  await waitFor(() => expect(result).toHaveTextContent("RealEvidenceMissing"));
  expect(result).toHaveTextContent("Open");
  expect(result).toHaveTextContent("Promotion: NotPerformed");
  expect(result).toHaveTextContent("Default changed: false · registry write: false · activation: false");
  expect(result).toHaveTextContent(r5hManifest.safetyBanner);

  const registerRequest = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/r5h/studies/register"));
  const registerBody = JSON.parse(String(registerRequest?.[1]?.body));
  expect(registerBody).toMatchObject({
    studyId: "axiom.intelligence.r5h.candidate-holdout-study@1",
    registrationAuthorityId: "model-owner",
    registrationRecordId: "external-record-001",
  });
  expect(registerBody.cases.map((item: { role: string }) => item.role)).toEqual(["in-domain", "in-domain", "ood-probe"]);
  const assessRequest = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/r5h/holdout/assess"));
  expect(String(assessRequest?.[1]?.body)).toContain("[-0.0,0,0]");
  expect(JSON.parse(String(assessRequest?.[1]?.body))).toMatchObject({ evidenceReports: [] });
  expect(screen.queryByRole("button", { name: /激活|晋升|部署|写入设备|切换默认/i })).not.toBeInTheDocument();
});
