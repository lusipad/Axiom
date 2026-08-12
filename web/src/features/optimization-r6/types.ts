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
