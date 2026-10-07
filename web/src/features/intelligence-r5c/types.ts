export interface ConditionalEffectDomain {
  domainId: string;
  feedOverrideMinimum: number;
  feedOverrideMaximum: number;
  samplePeriodMinimum: number;
  samplePeriodMaximum: number;
  feedOverrideUnit: "ratio";
  samplePeriodUnit: "s";
}

export interface R5CManifest {
  manifestId: string;
  schemaId: string;
  schemaVersion: 1;
  stage: "R5-C";
  domainPackId: "intelligence.domain-pack@3";
  platform: "windows";
  defaultScenarioId: "canonical-head-table-conditional-effect";
  parameterDomain: ConditionalEffectDomain;
  outputTargets: ["cycleTimeSeconds", "linearFollowingErrorMaxMm"];
  acceptanceThresholds: {
    maximumCycleTimeNormalizedRmse: number;
    maximumLinearErrorNormalizedRmse: number;
    minimumConformalCoverage: number;
    requiredOodAbstentionRate: number;
    maximumTargetParityGap: number;
  };
  syntheticConditionalEffectContractStatus: "Passed";
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  safetyBanner: string;
}

export interface R5CScenarioSummary {
  scenarioId: "canonical-head-table-conditional-effect";
  title: string;
  description: string;
  expectedOutcome: "Passed";
  expectedExecutionStatus: "Succeeded";
  realWorldGeneralizationStatus: "Open";
}

export interface ConditionalEffectSample {
  sampleId: string;
  feedOverride: number;
  samplePeriod: number;
  declaredSplitId: "train" | "validation" | "test";
  cycleTimeSeconds: number;
  linearFollowingErrorMaxMm: number;
  commandSampleCount: number;
  m4ContentHash: string;
  m5ContentHash: string;
  physicalResponseContentHash: string;
  sourceKind: "synthetic-sil";
  sourceScenarioId: "canonical-head-table-solver";
}

export interface ConditionalEffectModelBundle {
  artifactType: "axiom.intelligence.conditional-effect-model-bundle";
  schemaVersion: 1 | 2;
  bundleId: string;
  contentHash: string;
  parentModelBundleHash?: string;
  acquisitionReceiptHash?: string;
  targetInterpreterId: string;
  inputContractId: string;
  outputContractId: string;
  domain: ConditionalEffectDomain;
  featureOrder: string[];
  heads: Array<{
    targetId: "cycleTimeSeconds" | "linearFollowingErrorMaxMm";
    unit: "s" | "mm";
    weights: number[];
    conformalRadius: number;
  }>;
  resourceBudget: { targetRuntime: "pure-python"; featureCount: 6; outputCount: 2 };
  syntheticConditionalEffectContractStatus: "Passed" | "Failed";
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  safetyBanner: string;
}

export interface ConditionalEffectPrediction {
  schemaId: string;
  modelBundleHash: string;
  feedOverride: number;
  samplePeriod: number;
  status: "Predicted" | "Abstained";
  predictions: Array<{
    targetId: "cycleTimeSeconds" | "linearFollowingErrorMaxMm";
    unit: "s" | "mm";
    value: number;
    lower: number;
    upper: number;
  }>;
  reasonCode?: "OutsideDeclaredDomain";
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  contentHash: string;
}

export interface R5CExamplePayload {
  manifest: R5CManifest;
  scenario: R5CScenarioSummary;
  dataset: {
    datasetId: string;
    contentHash: string;
    sourceKind: "synthetic-sil";
    knownBiases: string[];
    coverageGaps: string[];
    samples: ConditionalEffectSample[];
  };
  splitManifest: {
    manifestId: string;
    contentHash: string;
    partitions: Array<{
      splitId: "train" | "validation" | "test";
      sampleIds: string[];
    }>;
  };
  modelBundle: ConditionalEffectModelBundle;
  trainingReceipt: { receiptId: string; contentHash: string };
  parityReceipt: { receiptId: string; contentHash: string; maxAbsGap: number; status: "Passed" | "Failed" };
  evaluation: {
    syntheticConditionalEffectContractStatus: "Passed" | "Failed";
    realWorldGeneralizationStatus: "Open";
    headResults: Array<{
      targetId: "cycleTimeSeconds" | "linearFollowingErrorMaxMm";
      unit: "s" | "mm";
      baselineRmse: number;
      modelRmse: number;
      normalizedRmse: number;
      improvementRatio: number;
      conformalCoverage: number;
    }>;
    oodAbstentionRate: number;
    targetParityMaxAbsGap: number;
    claims: Array<{
      claimId: string;
      title: string;
      status: "Supported" | "Refuted" | "Inconclusive";
      statement: string;
      reasonCode?: string;
    }>;
    evidence: Array<{
      evidenceId: string;
      title: string;
      contentHash?: string;
      summary: string;
    }>;
  };
  predictionExample: ConditionalEffectPrediction;
  runSpec: unknown;
}

export interface ConditionalEffectPredictionRequest {
  modelBundle: ConditionalEffectModelBundle;
  feedOverride: number;
  samplePeriod: number;
}

export interface R5DManifest {
  manifestId: "axiom.intelligence.r5d-manifest@1";
  schemaId: "axiom.intelligence.r5d-manifest@1";
  schemaVersion: 1;
  stage: "R5-D";
  platform: "windows";
  plannerId: "axiom.intelligence.greedy-g-optimal-linear-design@1";
  candidatePoolId: "axiom.optimization.r6v2-grid@1";
  candidatePoolSize: 135;
  defaultAvailableCandidateCount: 110;
  defaultBatchSize: 5;
  maximumBatchSize: 10;
  designFeatureCount: 6;
  designPartition: "train";
  selectionObjective: "maximum-design-leverage";
  globalOptimalityStatus: "NotClaimed";
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  automaticExecutionAllowed: false;
  deviceWriteAllowed: false;
  safetyBanner: string;
}

export interface R5DExperimentPlanRequest {
  schemaId: "axiom.intelligence.simulation-experiment-plan-request@1";
  modelBundle: ConditionalEffectModelBundle;
  dataset: R5CExamplePayload["dataset"];
  splitManifest: R5CExamplePayload["splitManifest"];
  batchSize: number;
}

export interface SimulationExperimentPlan {
  schemaId: "axiom.intelligence.simulation-experiment-plan@1";
  planId: string;
  plannerId: string;
  candidatePoolId: string;
  modelBundleHash: string;
  datasetContentHash: string;
  splitManifestContentHash: string;
  status: "Planned" | "Blocked";
  reasonCodes: string[];
  candidatePoolSize: 135;
  availableCandidateCount: number;
  designSampleCount: number;
  excludedObservedPointCount: number;
  requestedBatchSize: number;
  proposals: Array<{
    rank: number;
    experimentId: string;
    feedOverride: number;
    samplePeriod: number;
    feedOverrideUnit: "ratio";
    samplePeriodUnit: "s";
    designLeverage: number;
    predictedOutcomes: ConditionalEffectPrediction["predictions"];
    estimatedCommandSampleCount: number;
    plannedRunnerId: string;
    sourceKind: "synthetic-sil";
    labelStatus: "NotAcquired";
    automaticExecutionAllowed: false;
    deviceWriteAllowed: false;
  }>;
  maximumCandidateLeverageBefore?: number;
  maximumCandidateLeverageAfter?: number;
  relativeMaximumLeverageReduction?: number;
  uncertaintyScope: "linear-design-epistemic-proxy";
  globalOptimalityStatus: "NotClaimed";
  experimentExecutionStatus: "NotExecuted";
  modelUpdateStatus: "NotPerformed";
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  automaticExecutionAllowed: false;
  deviceWriteAllowed: false;
  knownLimitations: string[];
  safetyBanner: string;
  contentHash: string;
}

export interface R5EManifest {
  manifestId: "axiom.intelligence.r5e-manifest@1";
  schemaId: "axiom.intelligence.r5e-manifest@1";
  schemaVersion: 1;
  stage: "R5-E";
  platform: "windows";
  runnerId: "axiom.physical.canonical-f3-f4-r4-replay@1";
  approvalPolicyId: string;
  fixedBatchSize: 5;
  baseSampleCount: 25;
  acquiredSampleCount: 5;
  candidateSampleCount: 30;
  validationAndTestFrozen: true;
  automaticModelPromotionAllowed: false;
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  automaticExecutionAllowed: false;
  deviceWriteAllowed: false;
  safetyBanner: string;
}

export interface R5ECampaignApprovalCommand {
  planRequest: R5DExperimentPlanRequest;
  plan: SimulationExperimentPlan;
  accountablePartyId: string;
  syntheticOnlyAcknowledged: true;
}

export interface R5ESyntheticCampaignRequest {
  schemaId: string;
  planRequest: R5DExperimentPlanRequest;
  plan: SimulationExperimentPlan;
  approval: {
    approvalId: string;
    planContentHash: string;
    approvedExperimentIds: string[];
    accountablePartyId: string;
    humanApprovalPresent: true;
    automaticExecutionAllowed: false;
    deviceWriteAllowed: false;
    contentHash: string;
  };
  executionMode: "local-windows-synthetic-sil";
  contentHash: string;
}

export interface R5ESyntheticCampaignReport {
  reportId: string;
  campaignExecutionStatus: "Succeeded";
  acquisitionReceipt: {
    receiptId: string;
    contentHash: string;
    resultCount: 5;
    results: Array<{
      rank: number;
      experimentId: string;
      feedOverride: number;
      samplePeriod: number;
      cycleTimeSeconds: number;
      linearFollowingErrorMaxMm: number;
      commandSampleCount: number;
      executionStatus: "Succeeded";
      deviceWriteAllowed: false;
    }>;
  };
  dataset: R5CExamplePayload["dataset"] & {
    schemaVersion: 2;
    baseDatasetContentHash: string;
    acquisitionReceiptHash: string;
  };
  splitManifest: R5CExamplePayload["splitManifest"] & {
    schemaVersion: 2;
    baseSplitManifestHash: string;
    acquisitionReceiptHash: string;
  };
  modelBundle: ConditionalEffectModelBundle & {
    schemaVersion: 2;
    parentModelBundleHash: string;
    acquisitionReceiptHash: string;
  };
  trainingReceipt: {
    receiptId: string;
    contentHash: string;
    trainSampleCount: 20;
  };
  parityReceipt: {
    receiptId: string;
    contentHash: string;
    sampleCount: 30;
    status: "Passed" | "Failed";
  };
  candidateAssessment: {
    candidateGateStatus: "Passed" | "Failed";
    eligibleForManualPromotion: boolean;
    modelPromotionStatus: "NotPerformed";
    generalImprovementGuarantee: "NotClaimed";
    contentHash: string;
    metricDeltas: Array<{
      targetId: "cycleTimeSeconds" | "linearFollowingErrorMaxMm";
      unit: "s" | "mm";
      baselineModelRmse: number;
      candidateModelRmse: number;
      absoluteChange: number;
      relativeImprovement: number;
      status: "Improved" | "Unchanged" | "Regressed";
    }>;
  };
  nextPlan: SimulationExperimentPlan;
  modelPromotionStatus: "NotPerformed";
  realWorldGeneralizationStatus: "Open";
  automaticExecutionAllowed: false;
  deviceWriteAllowed: false;
  safetyBanner: string;
  contentHash: string;
}

export interface R5FManifest {
  manifestId: "axiom.intelligence.r5f-manifest@1";
  schemaId: "axiom.intelligence.r5f-manifest@1";
  schemaVersion: 1;
  stage: "R5-F";
  platform: "windows";
  scenarioIds: [
    "canonical-goal-conditioned-speed",
    "canonical-goal-conditioned-quality",
    "canonical-goal-conditioned-compact-command",
  ];
  screeningCandidateCount: 135;
  exactValidationBudget: 27;
  candidateUseStatus: "EvaluatedOnly";
  automaticModelPromotionAllowed: false;
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  safetyBanner: string;
}

export interface R5FCandidateImpactReport {
  reportId: string;
  scenarioImpacts: Array<{
    scenarioId:
      | "canonical-goal-conditioned-speed"
      | "canonical-goal-conditioned-quality"
      | "canonical-goal-conditioned-compact-command";
    primaryObjectiveId:
      | "cycleTimeSeconds"
      | "linearFollowingErrorMaxMm"
      | "commandSampleCount";
    primaryObjectiveUnit: "s" | "mm" | "count";
    baselineRecommendation: {
      schemaVersion: 2;
      screeningReceipt: { selectedCount: number; selectedCandidateIds: string[] };
      bestObservedCandidateIds: string[];
      contentHash: string;
    };
    candidateRecommendation: {
      schemaVersion: 3;
      screeningReceipt: { selectedCount: number; selectedCandidateIds: string[] };
      bestObservedCandidateIds: string[];
      contentHash: string;
    };
    selectedCandidateOverlapCount: number;
    baselineOnlySelectedCandidateIds: string[];
    candidateOnlySelectedCandidateIds: string[];
    screeningOrderChanged: boolean;
    baselineBestValue: number | null;
    candidateBestValue: number | null;
    comparisonTolerance: number;
    primaryObjectiveStatus: "NoRegression" | "Regressed" | "Inconclusive";
    sharedPredictionErrorDeltas: Array<{
      targetId: "cycleTimeSeconds" | "linearFollowingErrorMaxMm";
      unit: "s" | "mm";
      sharedCandidateCount: number;
      baselineMeanAbsoluteError: number;
      candidateMeanAbsoluteError: number;
      absoluteChange: number;
      status: "Improved" | "Unchanged" | "Regressed";
    }>;
    contentHash: string;
  }>;
  impactGateStatus: "Passed" | "Failed";
  candidateUseStatus: "EvaluatedOnly";
  modelPromotionStatus: "NotPerformed";
  generalImprovementGuarantee: "NotClaimed";
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  automaticAcceptanceAllowed: false;
  deviceWriteAllowed: false;
  safetyBanner: string;
  contentHash: string;
}

export interface R5GManifest {
  manifestId: "axiom.intelligence.r5g-manifest@1";
  schemaId: "axiom.intelligence.r5g-manifest@1";
  schemaVersion: 1;
  stage: "R5-G";
  platform: "windows";
  reviewScope: "synthetic-offline-review";
  reviewReadinessStatus: "ReadyForIndependentReview";
  reviewDecisionStatus: "AwaitingIndependentHumanDecision";
  automaticModelPromotionAllowed: false;
  modelRegistryWriteAllowed: false;
  defaultModelChangeAllowed: false;
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  safetyBanner: string;
}

export interface R5GModelPromotionReadinessDossier {
  schemaId: "axiom.intelligence.model-promotion-readiness-dossier@1";
  dossierId: string;
  request: {
    preparedBy: string;
    reviewScope: "synthetic-offline-review";
    contentHash: string;
  };
  sourceCampaignReportHash: string;
  sourceImpactReportHash: string;
  replayedImpactReportHash: string;
  baselineModelBundleHash: string;
  candidateModelBundleHash: string;
  candidateContextHash: string;
  readinessChecks: Array<{
    checkId: string;
    status: "Passed" | "Blocked";
    evidenceHash: string;
    reasonCode: string;
  }>;
  remainingGates: Array<{
    gateId: string;
    status: "Open";
    reasonCode: string;
  }>;
  reviewReadinessStatus: "ReadyForIndependentReview" | "Blocked";
  reviewDecisionStatus: "AwaitingIndependentHumanDecision";
  candidateUseStatus: "EvaluatedOnly";
  modelPromotionStatus: "NotPerformed";
  realWorldGeneralizationStatus: "Open";
  permissionLevel: "Offline";
  defaultModelChanged: false;
  modelRegistryWritePerformed: false;
  activationPerformed: false;
  automaticDeploymentAllowed: false;
  deviceWriteAllowed: false;
  safetyBanner: string;
  contentHash: string;
}

export interface R5HManifest {
  manifestId: "axiom.intelligence.r5h-manifest@1";
  schemaId: "axiom.intelligence.r5h-manifest@1";
  schemaVersion: 1;
  stage: "R5-H";
  platform: "windows";
  reviewScope: "candidate-case-scoped-real-holdout";
  sourceDossierSchemaId: "axiom.intelligence.model-promotion-readiness-dossier@1";
  requiredEvidenceSchemaId: "axiom.field-evidence-assessment-report@1";
  bundledRealEvidencePresent: false;
  realWorldGeneralizationStatus: "Open";
  modelRegistryWriteAllowed: false;
  activationAllowed: false;
  automaticDeploymentAllowed: false;
  deviceWriteAllowed: false;
  checkIds: string[];
  targetIds: Array<"cycleTimeSeconds" | "linearFollowingErrorMaxMm">;
  safetyBanner: string;
}

export interface R5HCandidateHoldoutCaseSpec {
  caseId: string;
  assessmentId: string;
  role: "in-domain" | "ood-probe";
  deviceId: string;
  conditionId: string;
  feedOverride: number;
  samplePeriod: number;
}

export interface R5HCandidateHoldoutCasePlan extends R5HCandidateHoldoutCaseSpec {
  exactOperatingPoint: {
    plannedM4ContentHash: string;
    plannedM5ContentHash: string;
    exactCycleTimeSeconds: number;
    commandSampleCount: number;
    numericEnvironment: Record<string, string>;
  };
  plannedCommand: {
    contentId: string;
    sourceM4ContentId: string;
    samplePeriod: number;
    duration: number;
    samples: unknown[];
  };
  contentHash: string;
}

export interface R5HCandidateHoldoutStudyRegistrationReport {
  schemaId: "axiom.intelligence.candidate-holdout-study-registration-report@1";
  schemaVersion: 1;
  requestContentHash: string;
  manifest: {
    artifactType: "axiom.intelligence.candidate-holdout-study-manifest";
    schemaId: "axiom.intelligence.candidate-holdout-study-manifest@1";
    schemaVersion: 1;
    studyId: string;
    readinessDossierContentHash: string;
    baselineModelBundleHash: string;
    candidateModelBundleHash: string;
    createdAt: string;
    maximumCandidateRmseRegressionRatio: 0;
    minimumCandidateIntervalCoverage: 1;
    minimumInDomainCases: 2;
    minimumDevices: 2;
    minimumConditions: 2;
    oodProbeRequired: true;
    cases: R5HCandidateHoldoutCasePlan[];
    platform: "windows";
    contentHash: string;
  };
  registration: {
    artifactType: "axiom.intelligence.candidate-holdout-study-registration";
    schemaId: "axiom.intelligence.candidate-holdout-study-registration@1";
    schemaVersion: 1;
    studyId: string;
    manifestContentHash: string;
    registeredAt: string;
    registrationAuthorityId: string;
    registrationRecordId: string;
    registrationMethod: "external-owner-attestation";
    trustBoundary: string;
    contentHash: string;
  };
  registrationStatus: "Passed";
  realWorldGeneralizationStatus: "Open";
  modelPromotionStatus: "NotPerformed";
  modelRegistryWritePerformed: false;
  activationPerformed: false;
  deviceWriteAllowed: false;
  safetyBanner: string;
  contentHash: string;
}

export interface R5HCandidateHoldoutAssessment {
  artifactType: "axiom.intelligence.candidate-real-holdout-assessment";
  schemaId: "axiom.intelligence.candidate-real-holdout-assessment@1";
  schemaVersion: 1;
  assessmentId: string;
  checks: Array<{
    checkId: string;
    title: string;
    status: "Passed" | "Open" | "Refuted" | "Blocked";
    reasonCode: string | null;
    details: Record<string, unknown>;
  }>;
  caseResults: unknown[];
  targetResults: Array<{
    targetId: "cycleTimeSeconds" | "linearFollowingErrorMaxMm";
    unit: "s" | "mm";
    evidenceSource: "exact-planner" | "controller-live-read";
    countsTowardReality: boolean;
    inDomainCaseCount: number;
    baselineRmse: number;
    candidateRmse: number;
    candidateRmseRegressionRatio: number;
    candidateIntervalCoverage: number;
    status: "Passed" | "Refuted";
  }>;
  overallStatus: "Passed" | "Open" | "Refuted" | "Blocked";
  realWorldGeneralizationStatus: "CaseScopedPassed" | "Open" | "Refuted" | "Blocked";
  reviewDecisionStatus: "AwaitingIndependentHumanDecision";
  candidateUseStatus: "EvaluatedOnly";
  modelPromotionStatus: "NotPerformed";
  defaultModelChanged: false;
  modelRegistryWritePerformed: false;
  activationPerformed: false;
  automaticDeploymentAllowed: false;
  deviceWriteAllowed: false;
  permissionLevel: "Offline";
  safetyBanner: string;
  contentHash: string;
}

export interface R5IManifest {
  manifestId: "axiom.intelligence.r5i-manifest@1";
  schemaId: "axiom.intelligence.r5i-manifest@1";
  schemaVersion: 1;
  stage: "R5-I";
  platform: "windows";
  lifecycleScope: "local-conditional-effect-model";
  registryKind: "sqlite-local";
  sourceDossierSchemaId: "axiom.intelligence.model-promotion-readiness-dossier@1";
  sourceHoldoutSchemaId: "axiom.intelligence.candidate-real-holdout-assessment@1";
  promotionDecisionSchemaId: "axiom.intelligence.promotion-decision@1";
  checkIds: string[];
  webStateMutationAllowed: false;
  localCliTransactionRequired: true;
  automaticModelPromotionAllowed: false;
  automaticRollbackAllowed: false;
  automaticDeploymentAllowed: false;
  deviceWriteAllowed: false;
  safetyBanner: string;
}

export interface R5IPromotionPreflightReport {
  schemaId: "axiom.intelligence.promotion-preflight-report@1";
  requestContentHash: string;
  candidateModelBundleHash: string;
  rollbackBaselineModelBundleHash: string;
  checks: Array<{
    checkId: string;
    status: "Passed" | "Blocked";
    evidenceHash: string;
    reasonCode: string;
  }>;
  overallStatus: "Passed" | "Blocked" | "Rejected";
  promotionTransactionStatus: "Eligible" | "Blocked" | "Rejected";
  reviewDecisionStatus: "Approved" | "Rejected" | "Invalid";
  authorizationVerified: boolean;
  registryTransactionAllowed: boolean;
  realWorldGeneralizationStatus: "CaseScopedPassed" | "Open" | "Refuted" | "Blocked";
  modelPromotionStatus: "NotPerformed";
  modelRegistryWritePerformed: false;
  activationPerformed: false;
  defaultModelChanged: false;
  automaticModelPromotionAllowed: false;
  automaticDeploymentAllowed: false;
  deviceWriteAllowed: false;
  permissionLevel: "Offline";
  safetyBanner: string;
  contentHash: string;
}

export interface R5IRegistryEvent {
  eventId: string;
  eventKind: "Promotion" | "Rollback";
  sourceModelBundleHash: string;
  targetModelBundleHash: string;
  rollbackBaselineModelBundleHash: string;
  generation: number;
  readbackModelBundleHash: string;
  readbackGeneration: number;
  transactionStatus: "Applied";
  deviceWritePerformed: false;
  contentHash: string;
}

export interface R5IRegistryStatus {
  schemaId: "axiom.intelligence.model-registry-status@1";
  registryIdentity: string;
  registryInitialized: boolean;
  currentModelBundleHash?: string;
  rollbackBaselineModelBundleHash?: string;
  generation: number;
  latestEvent?: R5IRegistryEvent;
  modelRegistryWritePerformed: boolean;
  activationPerformed: boolean;
  automaticDeploymentAllowed: false;
  deviceWriteAllowed: false;
  permissionLevel: "Offline";
  safetyBanner: string;
  contentHash: string;
}

export interface R5IMonitoringWindowReport {
  schemaId: "axiom.intelligence.model-monitoring-window-report@1";
  registryIdentity: string;
  modelBundleHash: string;
  generation: number;
  targetResults: Array<{
    targetId: "cycleTimeSeconds" | "linearFollowingErrorMaxMm";
    unit: "s" | "mm";
    labeledSampleCount: number;
    rmse?: number;
    intervalCoverage?: number;
    status: "Passed" | "Open" | "Refuted";
    reasonCode: string;
  }>;
  checks: Array<{
    checkId: string;
    status: "Passed" | "Open" | "Refuted";
    reasonCode: string;
    evidenceHash: string;
  }>;
  monitoringStatus: "Healthy" | "Open" | "RollbackRequired";
  rollbackRequired: boolean;
  automaticRollbackAllowed: false;
  automaticDeploymentAllowed: false;
  deviceWriteAllowed: false;
  permissionLevel: "Offline";
  safetyBanner: string;
  contentHash: string;
}
