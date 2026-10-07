export interface R6Manifest {
  manifestId: string;
  domainPackId: "optimization.domain-pack@1";
  evaluatorVersion: string;
  runnerId: string;
  supportedPlatforms: ["Windows"];
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  parameterIds: ["feedOverride", "samplePeriod"];
  objectiveIds: ["cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"];
  scenarioIds: string[];
  realityValidationStatus: "Open";
}

export interface R6ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedOutcome: "Passed";
  permissionLevel: "Offline";
}

export interface OptimizationSearchRequest {
  schemaId: "optimization.search-request@1";
  scenarioId: "canonical-head-table-offline-pareto";
  goal: {
    goalId: string;
    objectiveIds: ["cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"];
    maximumCycleTimeSeconds?: number;
    maximumLinearFollowingErrorMm?: number;
    maximumCommandSampleCount?: number;
  };
  grid: {
    feedOverrides: number[];
    samplePeriods: number[];
  };
}

export interface GateReceipt {
  claimId: string;
  status: "Supported" | "Refuted" | "Inconclusive";
  evidenceContentHash: string;
  method: string;
  reasonCode?: string;
}

export interface RecommendationCandidate {
  candidateId: string;
  parameterSet: {
    parameterSetId: string;
    values: { feedOverride: number; samplePeriod: number };
  };
  objectives: {
    cycleTimeSeconds: number;
    linearFollowingErrorMaxMm: number;
    commandSampleCount: number;
  };
  gateReceipts: GateReceipt[];
  physicalApplicabilityPassed: boolean;
  hardConstraintsSatisfied: boolean;
  goalFeasible: boolean;
  paretoOptimal: boolean;
  oodFraction: number;
  epistemicStatus: "InDomain" | "PartiallyOutOfDomain" | "Unavailable";
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  promotionEligible: false;
  explanation: string;
  candidateContentHash: string;
}

export interface RecommendationSet {
  recommendationSetId: string;
  contentHash: string;
  candidates: RecommendationCandidate[];
  paretoCandidateIds: string[];
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  automaticAcceptanceAllowed: false;
  shadowStatus: "Open";
  realityValidationStatus: "Open";
  physicalApplicabilityEvidence: {
    contentHash: string;
    status: "Passed";
    oracleId: string;
    endpointEvaluations: Array<{
      samplePeriodSeconds: number;
      sampleCount: number;
      improvementRatio: number;
      requiredImprovementRatio: number;
      passed: boolean;
    }>;
  };
  validationPlan: {
    planId: string;
    permissionLevel: "Offline";
    remainingGates: string[];
    stopConditions: string[];
    rollbackParameterSetId: string;
    deviceWriteAllowed: false;
  };
}

export interface R6ExamplePayload {
  manifest: R6Manifest;
  scenario: R6ScenarioSummary;
  searchRequest: OptimizationSearchRequest;
  recommendationSet: RecommendationSet;
  runSpec: unknown;
}

export type R6V2PrimaryObjective =
  | "cycleTimeSeconds"
  | "linearFollowingErrorMaxMm"
  | "commandSampleCount";

export interface R6V2Manifest {
  manifestId: string;
  schemaId: "optimization.r6v2-manifest@1";
  schemaVersion: 2;
  domainPackId: "optimization.domain-pack@2";
  evaluatorVersion: string;
  runnerId: string;
  supportedPlatforms: ["Windows"];
  parameterIds: ["feedOverride", "samplePeriod"];
  objectiveIds: ["cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"];
  scenarioIds: string[];
  screeningCandidateCount: 135;
  exactValidationBudget: 27;
  optimalityScope: "best-observed-within-exact-validation-budget";
  globalOptimalityStatus: "NotClaimed";
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  realityValidationStatus: "Open";
}

export interface R6V2ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  primaryObjectiveId: R6V2PrimaryObjective;
  expectedOutcome: "Passed";
  permissionLevel: "Offline";
  globalOptimalityStatus: "NotClaimed";
}

export type R6V2Intent =
  | {
    intentId: string;
    primaryObjectiveId: "cycleTimeSeconds";
    maximumLinearFollowingErrorMm: number;
    maximumCommandSampleCount: number;
  }
  | {
    intentId: string;
    primaryObjectiveId: "linearFollowingErrorMaxMm";
    maximumCycleTimeSeconds: number;
    maximumCommandSampleCount: number;
  }
  | {
    intentId: string;
    primaryObjectiveId: "commandSampleCount";
    maximumCycleTimeSeconds: number;
    maximumLinearFollowingErrorMm: number;
  };

export interface R6V2SearchRequest {
  schemaId: "optimization.search-request@2";
  scenarioId: string;
  intent: R6V2Intent;
  surrogateContext: unknown;
  screeningPolicyId: string;
  feedOverrides: number[];
  samplePeriods: number[];
  exactValidationBudget: 27;
}

export interface R6V2ExactCandidate {
  candidateId: string;
  parameterSet: {
    parameterSetId: string;
    values: { feedOverride: number; samplePeriod: number };
  };
  screeningRank: number;
  objectives: {
    cycleTimeSeconds: number;
    linearFollowingErrorMaxMm: number;
    commandSampleCount: number;
  };
  gateReceipts: GateReceipt[];
  hardConstraintsSatisfied: boolean;
  exactConstraintsSatisfied: boolean;
  recommendationEligible: boolean;
  paretoOptimalWithinValidated: boolean;
  bestObserved: boolean;
  oodFraction: number;
  epistemicStatus: "InDomain" | "PartiallyOutOfDomain" | "Unavailable";
  cycleTimePredictionAbsoluteError: number;
  linearErrorPredictionAbsoluteError: number;
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  promotionEligible: false;
  explanation: string;
  contentHash: string;
}

export interface RecommendationSetV2 {
  recommendationSetId: string;
  contentHash: string;
  searchRequest: R6V2SearchRequest;
  screeningReceipt: {
    contentHash: string;
    candidateCount: 135;
    possiblyFeasibleCount: number;
    selectedCount: number;
    exactValidationBudget: 27;
  };
  exactCandidates: R6V2ExactCandidate[];
  exactFeasibleCandidateIds: string[];
  paretoCandidateIds: string[];
  bestObservedCandidateIds: string[];
  validationPlan: {
    remainingGates: string[];
    stopConditions: string[];
    rollbackParameterSetId: string;
  };
  optimalityScope: "best-observed-within-exact-validation-budget";
  globalOptimalityStatus: "NotClaimed";
  permissionLevel: "Offline";
  deviceWriteAllowed: false;
  automaticAcceptanceAllowed: false;
  shadowStatus: "Open";
  realityValidationStatus: "Open";
}

export interface R6V2ExamplePayload {
  manifest: R6V2Manifest;
  scenario: R6V2ScenarioSummary;
  searchRequest: R6V2SearchRequest;
  recommendationSet: RecommendationSetV2;
  runSpec: unknown;
}

export interface GoalToShadowReport {
  status: "Passed" | "Blocked";
  reasonCodes: string[];
  selectedCandidateId?: string;
  sourceSearchRequestHash: string;
  recommendationProjection?: {
    selectionClass: "BestObserved" | "ParetoWithinValidated" | "ExactEligible" | "ExactIneligible";
    contentHash: string;
  };
  physicalShadowProjection?: {
    candidateContentHash: string;
    candidateM4ContentHash: string;
    sourceCommandM4ContentId: string;
    sourceM5ContentHash: string;
    sourcePhysicalResponseContentHash: string;
    sampleCount: number;
    alignment: "exact-sample-index-time-and-command";
    interpolationApplied: false;
    linearAxisIds: ["X", "Y", "Z"];
    linearAxisUnit: "mm";
    excludedRotaryAxisIds: ["B", "C"];
    candidateOodFraction: number;
    maximumLinearFollowingErrorMm: number;
    sourceKind: "synthetic-sil";
    shadowTrace: {
      contentHash: string;
      samples: Array<{
        sequence: number;
        timeSeconds: number;
        linearFollowingErrorMm: number;
        oodFraction: number;
      }>;
    };
    contentHash: string;
  };
  runtimeAudit?: {
    admissionDecision: { status: "Admitted" | "Blocked"; reasonCodes: string[] };
    finalState: "Blocked" | "Completed" | "RollbackVerified";
    monitorFindings: Array<{ status: "WithinEnvelope" | "Breach"; reasonCodes: string[] }>;
    stopReceipt: { requested: boolean; effect: "NotRequired" | "PromotionSuppressed"; reasonCodes: string[] };
    rollbackReceipt: { status: "NotRequired" | "BaselineRetained" };
    deviceWritePerformed: false;
    deploymentShadowStatus: "Open";
    controlledTrialStatus: "Open";
    closedLoopStatus: "Open";
    contentHash: string;
  };
  syntheticSilStatus: "Passed" | "Blocked";
  deploymentShadowStatus: "Open";
  realityValidationStatus: "Open";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
  deviceWriteAllowed: false;
  automaticAcceptanceAllowed: false;
  contentHash: string;
}
