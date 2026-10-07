import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntelligenceR5CWorkbench } from "./IntelligenceR5CWorkbench";
import type { ConditionalEffectPrediction, R5CExamplePayload, R5CManifest, R5CScenarioSummary, R5DManifest, R5EManifest, R5ESyntheticCampaignReport, R5FCandidateImpactReport, R5FManifest, R5GManifest, R5GModelPromotionReadinessDossier, R5HManifest, SimulationExperimentPlan } from "./types";

const manifest: R5CManifest = {
  manifestId: "axiom.intelligence.r5c-manifest@1",
  schemaId: "axiom.intelligence.r5c-manifest@1",
  schemaVersion: 1,
  stage: "R5-C",
  domainPackId: "intelligence.domain-pack@3",
  platform: "windows",
  defaultScenarioId: "canonical-head-table-conditional-effect",
  parameterDomain: {
    domainId: "axiom.intelligence.r5c-parameter-domain@1",
    feedOverrideMinimum: 0.65,
    feedOverrideMaximum: 1,
    samplePeriodMinimum: 0.04,
    samplePeriodMaximum: 0.08,
    feedOverrideUnit: "ratio",
    samplePeriodUnit: "s",
  },
  outputTargets: ["cycleTimeSeconds", "linearFollowingErrorMaxMm"],
  acceptanceThresholds: {
    maximumCycleTimeNormalizedRmse: 0.02,
    maximumLinearErrorNormalizedRmse: 0.05,
    minimumConformalCoverage: 0.8,
    requiredOodAbstentionRate: 1,
    maximumTargetParityGap: 1e-12,
  },
  syntheticConditionalEffectContractStatus: "Passed",
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  deviceWriteAllowed: false,
  safetyBanner: "SYNTHETIC CONDITIONAL EFFECT / NOT REALITY VALIDATED / NOT DEVICE SAFE",
};

const scenario: R5CScenarioSummary = {
  scenarioId: "canonical-head-table-conditional-effect",
  title: "Canonical conditional effect",
  description: "A deterministic 5x5 R4 SIL study.",
  expectedOutcome: "Passed",
  expectedExecutionStatus: "Succeeded",
  realWorldGeneralizationStatus: "Open",
};

const r5dManifest: R5DManifest = {
  manifestId: "axiom.intelligence.r5d-manifest@1",
  schemaId: "axiom.intelligence.r5d-manifest@1",
  schemaVersion: 1,
  stage: "R5-D",
  platform: "windows",
  plannerId: "axiom.intelligence.greedy-g-optimal-linear-design@1",
  candidatePoolId: "axiom.optimization.r6v2-grid@1",
  candidatePoolSize: 135,
  defaultAvailableCandidateCount: 110,
  defaultBatchSize: 5,
  maximumBatchSize: 10,
  designFeatureCount: 6,
  designPartition: "train",
  selectionObjective: "maximum-design-leverage",
  globalOptimalityStatus: "NotClaimed",
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  automaticExecutionAllowed: false,
  deviceWriteAllowed: false,
  safetyBanner: "SYNTHETIC EXPERIMENT PLAN / NOT EXECUTED / NOT REALITY VALIDATED / NOT DEVICE SAFE",
};

const r5eManifest: R5EManifest = {
  manifestId: "axiom.intelligence.r5e-manifest@1",
  schemaId: "axiom.intelligence.r5e-manifest@1",
  schemaVersion: 1,
  stage: "R5-E",
  platform: "windows",
  runnerId: "axiom.physical.canonical-f3-f4-r4-replay@1",
  approvalPolicyId: "axiom.intelligence.r5e-explicit-offline-approval@1",
  fixedBatchSize: 5,
  baseSampleCount: 25,
  acquiredSampleCount: 5,
  candidateSampleCount: 30,
  validationAndTestFrozen: true,
  automaticModelPromotionAllowed: false,
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  automaticExecutionAllowed: false,
  deviceWriteAllowed: false,
  safetyBanner: "SYNTHETIC SIL CAMPAIGN / NOT REALITY VALIDATED / NOT DEVICE SAFE / PROMOTION NOT PERFORMED",
};

const r5fManifest: R5FManifest = {
  manifestId: "axiom.intelligence.r5f-manifest@1",
  schemaId: "axiom.intelligence.r5f-manifest@1",
  schemaVersion: 1,
  stage: "R5-F",
  platform: "windows",
  scenarioIds: ["canonical-goal-conditioned-speed", "canonical-goal-conditioned-quality", "canonical-goal-conditioned-compact-command"],
  screeningCandidateCount: 135,
  exactValidationBudget: 27,
  candidateUseStatus: "EvaluatedOnly",
  automaticModelPromotionAllowed: false,
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  deviceWriteAllowed: false,
  safetyBanner: "CANDIDATE DOWNSTREAM IMPACT EVALUATION / EVALUATED ONLY / NOT REALITY VALIDATED / NOT DEVICE SAFE / PROMOTION NOT PERFORMED",
};

const r5gManifest: R5GManifest = {
  manifestId: "axiom.intelligence.r5g-manifest@1",
  schemaId: "axiom.intelligence.r5g-manifest@1",
  schemaVersion: 1,
  stage: "R5-G",
  platform: "windows",
  reviewScope: "synthetic-offline-review",
  reviewReadinessStatus: "ReadyForIndependentReview",
  reviewDecisionStatus: "AwaitingIndependentHumanDecision",
  automaticModelPromotionAllowed: false,
  modelRegistryWriteAllowed: false,
  defaultModelChangeAllowed: false,
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  deviceWriteAllowed: false,
  safetyBanner: "PROMOTION READINESS REVIEW / AWAITING INDEPENDENT HUMAN DECISION / NO MODEL ACTIVATION / NOT REALITY VALIDATED / NOT DEVICE SAFE",
};

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

const predicted: ConditionalEffectPrediction = {
  schemaId: "axiom.intelligence.conditional-effect-prediction@1",
  modelBundleHash: "d".repeat(64),
  feedOverride: 0.82,
  samplePeriod: 0.055,
  status: "Predicted",
  predictions: [
    { targetId: "cycleTimeSeconds", unit: "s", value: 0.8, lower: 0.79, upper: 0.81 },
    { targetId: "linearFollowingErrorMaxMm", unit: "mm", value: 0.5, lower: 0.45, upper: 0.55 },
  ],
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  deviceWriteAllowed: false,
  contentHash: "e".repeat(64),
};

const modelBundle: R5CExamplePayload["modelBundle"] = {
  artifactType: "axiom.intelligence.conditional-effect-model-bundle",
  schemaVersion: 1,
  bundleId: "bundle@1",
  contentHash: "d".repeat(64),
  targetInterpreterId: "python@1",
  inputContractId: "input@1",
  outputContractId: "output@1",
  domain: manifest.parameterDomain,
  featureOrder: ["bias", "u", "v", "uv", "v2", "u2"],
  heads: [
    { targetId: "cycleTimeSeconds", unit: "s", weights: [1, 0, 0, 0, 0, 0], conformalRadius: 0.01 },
    { targetId: "linearFollowingErrorMaxMm", unit: "mm", weights: [0.5, 0, 0, 0, 0, 0], conformalRadius: 0.05 },
  ],
  resourceBudget: { targetRuntime: "pure-python", featureCount: 6, outputCount: 2 },
  syntheticConditionalEffectContractStatus: "Passed",
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  deviceWriteAllowed: false,
  safetyBanner: manifest.safetyBanner,
};

const samples = Array.from({ length: 25 }, (_, index) => ({
  sampleId: `sample-${index}`,
  feedOverride: 0.65 + Math.floor(index / 5) * 0.0875,
  samplePeriod: 0.04 + (index % 5) * 0.01,
  declaredSplitId: (index < 15 ? "train" : index < 20 ? "validation" : "test") as "train" | "validation" | "test",
  cycleTimeSeconds: 1,
  linearFollowingErrorMaxMm: 0.5,
  commandSampleCount: 10,
  m4ContentHash: "a".repeat(64),
  m5ContentHash: "b".repeat(64),
  physicalResponseContentHash: "c".repeat(64),
  sourceKind: "synthetic-sil" as const,
  sourceScenarioId: "canonical-head-table-solver" as const,
}));

const payload: R5CExamplePayload = {
  manifest,
  scenario,
  dataset: {
    datasetId: "dataset@1",
    contentHash: "a".repeat(64),
    sourceKind: "synthetic-sil",
    knownBiases: ["synthetic"],
    coverageGaps: ["No real-device holdout."],
    samples,
  },
  splitManifest: {
    manifestId: "split@1",
    contentHash: "b".repeat(64),
    partitions: [
      { splitId: "train", sampleIds: samples.slice(0, 15).map((item) => item.sampleId) },
      { splitId: "validation", sampleIds: samples.slice(15, 20).map((item) => item.sampleId) },
      { splitId: "test", sampleIds: samples.slice(20).map((item) => item.sampleId) },
    ],
  },
  modelBundle,
  trainingReceipt: { receiptId: "training@1", contentHash: "f".repeat(64) },
  parityReceipt: { receiptId: "parity@1", contentHash: "1".repeat(64), maxAbsGap: 1e-16, status: "Passed" },
  evaluation: {
    syntheticConditionalEffectContractStatus: "Passed",
    realWorldGeneralizationStatus: "Open",
    headResults: [
      { targetId: "cycleTimeSeconds", unit: "s", baselineRmse: 0.2, modelRmse: 1e-7, normalizedRmse: 3.4e-7, improvementRatio: 0.999999, conformalCoverage: 1 },
      { targetId: "linearFollowingErrorMaxMm", unit: "mm", baselineRmse: 0.07, modelRmse: 0.004, normalizedRmse: 0.0187, improvementRatio: 0.94, conformalCoverage: 0.8 },
    ],
    oodAbstentionRate: 1,
    targetParityMaxAbsGap: 1e-16,
    claims: [
      { claimId: "synthetic@1", title: "Synthetic conditional effect", status: "Supported", statement: "Synthetic contract passed." },
      { claimId: "reality@1", title: "Real-world generalization", status: "Inconclusive", statement: "Reality remains open.", reasonCode: "RealPairedHoldoutMissing" },
    ],
    evidence: [{ evidenceId: "dataset", title: "Dataset", contentHash: "a".repeat(64), summary: "5x5 study." }],
  },
  predictionExample: predicted,
  runSpec: {},
};

const experimentPlan: SimulationExperimentPlan = {
  schemaId: "axiom.intelligence.simulation-experiment-plan@1",
  planId: "plan@1",
  plannerId: r5dManifest.plannerId,
  candidatePoolId: r5dManifest.candidatePoolId,
  modelBundleHash: modelBundle.contentHash,
  datasetContentHash: payload.dataset.contentHash,
  splitManifestContentHash: payload.splitManifest.contentHash,
  status: "Planned",
  reasonCodes: [],
  candidatePoolSize: 135,
  availableCandidateCount: 110,
  designSampleCount: 15,
  excludedObservedPointCount: 25,
  requestedBatchSize: 5,
  proposals: ([
    [0.675, 0.04, 2.5149],
    [0.65, 0.045, 0.7746],
    [0.75, 0.08, 0.6375],
    [1, 0.055, 0.5139],
    [0.975, 0.08, 0.4289],
  ] as Array<[number, number, number]>).map(([feedOverride, samplePeriod, designLeverage], index) => ({
    rank: index + 1,
    experimentId: `experiment-${index}@1`,
    feedOverride,
    samplePeriod,
    feedOverrideUnit: "ratio" as const,
    samplePeriodUnit: "s" as const,
    designLeverage,
    predictedOutcomes: predicted.predictions,
    estimatedCommandSampleCount: 18,
    plannedRunnerId: "axiom.physical.canonical-f3-f4-r4-replay@1",
    sourceKind: "synthetic-sil" as const,
    labelStatus: "NotAcquired" as const,
    automaticExecutionAllowed: false as const,
    deviceWriteAllowed: false as const,
  })),
  maximumCandidateLeverageBefore: 2.5149,
  maximumCandidateLeverageAfter: 0.4276,
  relativeMaximumLeverageReduction: 0.83,
  uncertaintyScope: "linear-design-epistemic-proxy",
  globalOptimalityStatus: "NotClaimed",
  experimentExecutionStatus: "NotExecuted",
  modelUpdateStatus: "NotPerformed",
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  automaticExecutionAllowed: false,
  deviceWriteAllowed: false,
  knownLimitations: ["linear proxy"],
  safetyBanner: r5dManifest.safetyBanner,
  contentHash: "9".repeat(64),
};

const acquiredSamples = experimentPlan.proposals.map((proposal, index) => {
  const source = samples[index]!;
  return {
    ...source,
    sampleId: `r5e-sample-${index}`,
    feedOverride: proposal.feedOverride,
    samplePeriod: proposal.samplePeriod,
    declaredSplitId: "train" as const,
    cycleTimeSeconds: 0.7 + index * 0.05,
    linearFollowingErrorMaxMm: 0.35 + index * 0.04,
  };
});

const campaignReport: R5ESyntheticCampaignReport = {
  reportId: "campaign-report@1",
  campaignExecutionStatus: "Succeeded",
  acquisitionReceipt: {
    receiptId: "acquisition@1",
    contentHash: "2".repeat(64),
    resultCount: 5,
    results: experimentPlan.proposals.map((proposal, index) => ({
      rank: proposal.rank,
      experimentId: proposal.experimentId,
      feedOverride: proposal.feedOverride,
      samplePeriod: proposal.samplePeriod,
      cycleTimeSeconds: acquiredSamples[index]!.cycleTimeSeconds,
      linearFollowingErrorMaxMm: acquiredSamples[index]!.linearFollowingErrorMaxMm,
      commandSampleCount: 20 - index,
      executionStatus: "Succeeded" as const,
      deviceWriteAllowed: false as const,
    })),
  },
  dataset: {
    ...payload.dataset,
    datasetId: "dataset@2",
    schemaVersion: 2,
    contentHash: "3".repeat(64),
    samples: [...samples, ...acquiredSamples],
    baseDatasetContentHash: payload.dataset.contentHash,
    acquisitionReceiptHash: "2".repeat(64),
  },
  splitManifest: {
    ...payload.splitManifest,
    manifestId: "split@2",
    schemaVersion: 2,
    contentHash: "4".repeat(64),
    partitions: [
      { splitId: "train", sampleIds: [...payload.splitManifest.partitions[0]!.sampleIds, ...acquiredSamples.map((item) => item.sampleId)] },
      payload.splitManifest.partitions[1]!,
      payload.splitManifest.partitions[2]!,
    ],
    baseSplitManifestHash: payload.splitManifest.contentHash,
    acquisitionReceiptHash: "2".repeat(64),
  },
  modelBundle: {
    ...modelBundle,
    schemaVersion: 2,
    bundleId: "bundle@2",
    contentHash: "5".repeat(64),
    parentModelBundleHash: modelBundle.contentHash,
    acquisitionReceiptHash: "2".repeat(64),
  },
  trainingReceipt: { receiptId: "training@2", contentHash: "6".repeat(64), trainSampleCount: 20 },
  parityReceipt: { receiptId: "parity@2", contentHash: "7".repeat(64), sampleCount: 30, status: "Passed" },
  candidateAssessment: {
    candidateGateStatus: "Passed",
    eligibleForManualPromotion: true,
    modelPromotionStatus: "NotPerformed",
    generalImprovementGuarantee: "NotClaimed",
    contentHash: "8".repeat(64),
    metricDeltas: [
      { targetId: "cycleTimeSeconds", unit: "s", baselineModelRmse: 2e-7, candidateModelRmse: 1.1e-7, absoluteChange: -0.9e-7, relativeImprovement: 0.45, status: "Improved" },
      { targetId: "linearFollowingErrorMaxMm", unit: "mm", baselineModelRmse: 0.004, candidateModelRmse: 0.003, absoluteChange: -0.001, relativeImprovement: 0.25, status: "Improved" },
    ],
  },
  nextPlan: {
    ...experimentPlan,
    planId: "next-plan@1",
    availableCandidateCount: 105,
    designSampleCount: 20,
    excludedObservedPointCount: 30,
    contentHash: "a".repeat(64),
  },
  modelPromotionStatus: "NotPerformed",
  realWorldGeneralizationStatus: "Open",
  automaticExecutionAllowed: false,
  deviceWriteAllowed: false,
  safetyBanner: r5eManifest.safetyBanner,
  contentHash: "b".repeat(64),
};

const selectedIds = Array.from({ length: 27 }, (_, index) => `candidate-${index}@1`);
const impactReport: R5FCandidateImpactReport = {
  reportId: "candidate-impact@1",
  scenarioImpacts: ([
    ["canonical-goal-conditioned-speed", "cycleTimeSeconds", "s", 0.82303, true],
    ["canonical-goal-conditioned-quality", "linearFollowingErrorMaxMm", "mm", 0.43597, true],
    ["canonical-goal-conditioned-compact-command", "commandSampleCount", "count", 12, false],
  ] as const).map(([scenarioId, primaryObjectiveId, primaryObjectiveUnit, best, orderChanged]) => ({
    scenarioId,
    primaryObjectiveId,
    primaryObjectiveUnit,
    baselineRecommendation: {
      schemaVersion: 2 as const,
      screeningReceipt: { selectedCount: 27, selectedCandidateIds: selectedIds },
      bestObservedCandidateIds: [selectedIds[0]!],
      contentHash: "c".repeat(64),
    },
    candidateRecommendation: {
      schemaVersion: 3 as const,
      screeningReceipt: { selectedCount: 27, selectedCandidateIds: orderChanged ? [selectedIds[1]!, selectedIds[0]!, ...selectedIds.slice(2)] : selectedIds },
      bestObservedCandidateIds: [selectedIds[0]!],
      contentHash: "d".repeat(64),
    },
    selectedCandidateOverlapCount: 27,
    baselineOnlySelectedCandidateIds: [],
    candidateOnlySelectedCandidateIds: [],
    screeningOrderChanged: orderChanged,
    baselineBestValue: best,
    candidateBestValue: best,
    comparisonTolerance: primaryObjectiveId === "commandSampleCount" ? 0 : 1e-12,
    primaryObjectiveStatus: "NoRegression" as const,
    sharedPredictionErrorDeltas: [
      { targetId: "cycleTimeSeconds" as const, unit: "s" as const, sharedCandidateCount: 27, baselineMeanAbsoluteError: 0.01, candidateMeanAbsoluteError: 0.008, absoluteChange: -0.002, status: "Improved" as const },
      { targetId: "linearFollowingErrorMaxMm" as const, unit: "mm" as const, sharedCandidateCount: 27, baselineMeanAbsoluteError: 0.02, candidateMeanAbsoluteError: 0.015, absoluteChange: -0.005, status: "Improved" as const },
    ],
    contentHash: "e".repeat(64),
  })),
  impactGateStatus: "Passed",
  candidateUseStatus: "EvaluatedOnly",
  modelPromotionStatus: "NotPerformed",
  generalImprovementGuarantee: "NotClaimed",
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  automaticAcceptanceAllowed: false,
  deviceWriteAllowed: false,
  safetyBanner: r5fManifest.safetyBanner,
  contentHash: "f".repeat(64),
};

const readinessDossier: R5GModelPromotionReadinessDossier = {
  schemaId: "axiom.intelligence.model-promotion-readiness-dossier@1",
  dossierId: "candidate-promotion-readiness@1",
  request: {
    preparedBy: "independent-review-preparer",
    reviewScope: "synthetic-offline-review",
    contentHash: "1".repeat(64),
  },
  sourceCampaignReportHash: "2".repeat(64),
  sourceImpactReportHash: impactReport.contentHash,
  replayedImpactReportHash: impactReport.contentHash,
  baselineModelBundleHash: "3".repeat(64),
  candidateModelBundleHash: "4".repeat(64),
  candidateContextHash: "5".repeat(64),
  readinessChecks: [
    ["r5e-candidate-gate@1", "CandidateGatePassed"],
    ["r5f-impact-gate@1", "ImpactGatePassed"],
    ["r5f-deterministic-replay@1", "ReplayIdentityMatched"],
    ["single-candidate-lineage@1", "SingleCandidateLineage"],
    ["rollback-baseline-bound@1", "RollbackBaselineBound"],
  ].map(([checkId, reasonCode], index) => ({ checkId: checkId!, status: "Passed" as const, evidenceHash: String(index + 5).repeat(64), reasonCode: reasonCode! })),
  remainingGates: [
    "real-world-holdout@1",
    "independent-human-decision@1",
    "model-registry@1",
    "activation-and-default-switch@1",
    "rollback-execution@1",
    "runtime-monitoring@1",
  ].map((gateId) => ({ gateId, status: "Open" as const, reasonCode: "NotEstablished" })),
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
  safetyBanner: r5gManifest.safetyBanner,
  contentHash: "a".repeat(64),
};

function jsonResponse(value: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => vi.restoreAllMocks());

describe("IntelligenceR5CWorkbench", () => {
  it("分别展示秒与毫米输出，并保持现实验证开放", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/r5h/manifest")) return jsonResponse(r5hManifest);
      if (url.includes("/r5e/manifest")) return jsonResponse(r5eManifest);
      if (url.includes("/r5d/manifest")) return jsonResponse(r5dManifest);
      if (url.endsWith("/manifest")) return jsonResponse(manifest);
      if (url.endsWith("/scenarios")) return jsonResponse([scenario]);
      return jsonResponse(payload);
    });

    render(<IntelligenceR5CWorkbench catalog={null} />);

    expect(await screen.findByText("条件改变什么，不做万能总分")).toBeInTheDocument();
    expect(screen.getByText(manifest.safetyBanner)).toBeInTheDocument();
    expect(screen.getByLabelText("双输出预测")).toHaveTextContent("0.8 s");
    expect(screen.getByLabelText("双输出预测")).toHaveTextContent("0.5 mm");
    expect(screen.getByText("25 点参数平面")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|下发|应用参数/i })).not.toBeInTheDocument();
  });

  it("把用户参数提交到离线预测端点", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/r5h/manifest")) return jsonResponse(r5hManifest);
      if (url.includes("/r5e/manifest")) return jsonResponse(r5eManifest);
      if (url.includes("/r5d/manifest")) return jsonResponse(r5dManifest);
      if (url.endsWith("/manifest")) return jsonResponse(manifest);
      if (url.endsWith("/scenarios")) return jsonResponse([scenario]);
      if (url.endsWith("/predict")) return jsonResponse({ ...predicted, feedOverride: 0.9 });
      return jsonResponse(payload);
    });
    render(<IntelligenceR5CWorkbench catalog={null} />);
    await screen.findByText("独立测试门");

    fireEvent.change(screen.getByLabelText("feedOverride"), { target: { value: "0.9" } });
    fireEvent.click(screen.getByRole("button", { name: "离线预测" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/predict") && init?.method === "POST")).toBe(true));
  });

  it("域外参数只显示拒绝，不显示数值预测", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/r5h/manifest")) return jsonResponse(r5hManifest);
      if (url.includes("/r5e/manifest")) return jsonResponse(r5eManifest);
      if (url.includes("/r5d/manifest")) return jsonResponse(r5dManifest);
      if (url.endsWith("/manifest")) return jsonResponse(manifest);
      if (url.endsWith("/scenarios")) return jsonResponse([scenario]);
      if (url.endsWith("/predict")) return jsonResponse({
        ...predicted,
        feedOverride: 1.01,
        status: "Abstained",
        predictions: [],
        reasonCode: "OutsideDeclaredDomain",
      });
      return jsonResponse(payload);
    });
    render(<IntelligenceR5CWorkbench catalog={null} />);
    await screen.findByText("独立测试门");

    fireEvent.change(screen.getByLabelText("feedOverride"), { target: { value: "1.01" } });
    fireEvent.click(screen.getByRole("button", { name: "离线预测" }));

    expect(await screen.findByText("拒绝域外外推")).toBeInTheDocument();
    expect(screen.getAllByText("OutsideDeclaredDomain")).toHaveLength(2);
    expect(screen.queryByLabelText("双输出预测")).not.toBeInTheDocument();
  });

  it("生成下一批仿真计划，但不提供自动执行或设备写入", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/r5h/manifest")) return jsonResponse(r5hManifest);
      if (url.includes("/r5e/manifest")) return jsonResponse(r5eManifest);
      if (url.includes("/r5d/manifest")) return jsonResponse(r5dManifest);
      if (url.endsWith("/manifest")) return jsonResponse(manifest);
      if (url.endsWith("/scenarios")) return jsonResponse([scenario]);
      if (url.endsWith("/r5d/plan")) return jsonResponse(experimentPlan);
      return jsonResponse(payload);
    });
    render(<IntelligenceR5CWorkbench catalog={null} />);
    await screen.findByText("R5-D 下一批仿真实验");

    fireEvent.click(screen.getByRole("button", { name: "规划下一批仿真" }));

    expect(await screen.findByText("83.0%")).toBeInTheDocument();
    expect(screen.getByLabelText("R5-D 仿真实验计划")).toHaveTextContent("0.675");
    expect(screen.getByLabelText("R5-D 仿真实验计划")).toHaveTextContent("NotExecuted");
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/r5d/plan") && init?.method === "POST")).toBe(true);
    expect(screen.queryByRole("button", { name: /执行仿真|自动执行|写入|下发|应用参数/i })).not.toBeInTheDocument();
  });

  it("显式执行 synthetic SIL 后生成只读晋升就绪审查包", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/r5h/manifest")) return jsonResponse(r5hManifest);
      if (url.includes("/r5g/manifest")) return jsonResponse(r5gManifest);
      if (url.includes("/r5f/manifest")) return jsonResponse(r5fManifest);
      if (url.includes("/r5e/manifest")) return jsonResponse(r5eManifest);
      if (url.includes("/r5d/manifest")) return jsonResponse(r5dManifest);
      if (url.endsWith("/manifest")) return jsonResponse(manifest);
      if (url.endsWith("/scenarios")) return jsonResponse([scenario]);
      if (url.endsWith("/r5d/plan")) return jsonResponse(experimentPlan);
      if (url.endsWith("/campaigns/approve")) return jsonResponse({
        schemaId: "campaign-request@1",
        planRequest: {},
        plan: experimentPlan,
        approval: { accountablePartyId: "local-reviewer", humanApprovalPresent: true },
        executionMode: "local-windows-synthetic-sil",
        contentHash: "c".repeat(64),
      });
      if (url.endsWith("/campaigns/execute")) return jsonResponse(campaignReport);
      if (url.endsWith("/r5f/impact/assess")) return jsonResponse(impactReport);
      if (url.endsWith("/r5g/promotion/readiness")) return jsonResponse(readinessDossier);
      return jsonResponse(payload);
    });
    render(<IntelligenceR5CWorkbench catalog={null} />);
    await screen.findByText("R5-E 离线合成反馈闭环");

    const executeButton = screen.getByRole("button", { name: "批准并执行合成 SIL 批次" });
    expect(executeButton).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "规划下一批仿真" }));
    await screen.findByText("83.0%");
    fireEvent.change(screen.getByLabelText("R5-E accountable party"), { target: { value: "local-reviewer" } });
    fireEvent.click(screen.getByLabelText("确认仅执行本地 synthetic SIL"));
    expect(executeButton).toBeEnabled();
    fireEvent.click(executeButton);

    const campaign = await screen.findByLabelText("R5-E 合成实验反馈闭环");
    await waitFor(() => expect(campaign).toHaveTextContent("25 → 30"));
    expect(campaign).toHaveTextContent("15 → 20");
    expect(campaign).toHaveTextContent("45.0%");
    expect(campaign).toHaveTextContent("25.0%");
    expect(campaign).toHaveTextContent("promotion NotPerformed");
    expect(campaign).toHaveTextContent(r5eManifest.safetyBanner);
    const impactButton = screen.getByRole("button", { name: "评估候选下游影响" });
    expect(impactButton).toBeEnabled();
    fireEvent.click(impactButton);
    const impact = await screen.findByLabelText("R5-F 候选下游影响评估");
    await waitFor(() => expect(impact).toHaveTextContent("3 / 3"));
    expect(impact).toHaveTextContent("NoRegression");
    expect(impact).toHaveTextContent("EvaluatedOnly");
    expect(impact).toHaveTextContent(r5fManifest.safetyBanner);
    const readinessButton = screen.getByRole("button", { name: "生成晋升就绪审查包" });
    expect(readinessButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText("R5-G prepared by"), { target: { value: "independent-review-preparer" } });
    fireEvent.click(screen.getByLabelText("确认现实验证门仍为 Open"));
    fireEvent.click(screen.getByLabelText("确认尚未建立设备安全性"));
    fireEvent.click(screen.getByLabelText("确认禁止自动部署"));
    expect(readinessButton).toBeEnabled();
    fireEvent.click(readinessButton);
    const readiness = await screen.findByLabelText("R5-G 模型晋升就绪审查");
    await waitFor(() => expect(readiness).toHaveTextContent("ReadyForIndependentReview"));
    expect(readiness).toHaveTextContent("5 / 5");
    expect(readiness).toHaveTextContent("6 Open");
    expect(readiness).toHaveTextContent("AwaitingIndependentHumanDecision");
    expect(readiness).toHaveTextContent("promotion NotPerformed");
    expect(readiness).toHaveTextContent("Default changed: false · registry write: false · activation: false");
    expect(readiness).toHaveTextContent(r5gManifest.safetyBanner);
    const approveIndex = fetchMock.mock.calls.findIndex(([input]) => String(input).endsWith("/campaigns/approve"));
    const executeIndex = fetchMock.mock.calls.findIndex(([input]) => String(input).endsWith("/campaigns/execute"));
    expect(approveIndex).toBeGreaterThan(-1);
    expect(executeIndex).toBeGreaterThan(approveIndex);
    const impactIndex = fetchMock.mock.calls.findIndex(([input]) => String(input).endsWith("/r5f/impact/assess"));
    expect(impactIndex).toBeGreaterThan(executeIndex);
    const readinessIndex = fetchMock.mock.calls.findIndex(([input]) => String(input).endsWith("/r5g/promotion/readiness"));
    expect(readinessIndex).toBeGreaterThan(impactIndex);
    const readinessRequest = JSON.parse(String(fetchMock.mock.calls[readinessIndex]?.[1]?.body));
    expect(readinessRequest).toMatchObject({
      preparedBy: "independent-review-preparer",
      realityGateOpenAcknowledged: true,
      deviceSafetyNotEstablishedAcknowledged: true,
      automaticDeploymentForbiddenAcknowledged: true,
    });
    expect(screen.queryByText(/DeviceSafe|ProcessSafe|safe-to-run/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /采用候选|晋升模型|应用模型|激活模型|部署模型/i })).not.toBeInTheDocument();
  });
});
