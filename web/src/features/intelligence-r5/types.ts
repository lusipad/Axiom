export type R5StageStatus = "Passed" | "Open" | "Failed" | "Inconclusive";

export interface R5Manifest {
  manifestId: string;
  schemaId: string;
  schemaVersion: number;
  stage: "R5-A";
  domainPackId: string;
  platform: "windows";
  defaultScenarioId: string;
  safetyBanner: string;
  learningBanner?: string;
  syntheticLearningContractStatus: R5StageStatus;
  realWorldGeneralizationStatus: R5StageStatus;
}

export interface R5ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedOutcome: "Passed" | "Invalid";
  expectedExecutionStatus: "Succeeded" | "Skipped";
}

export interface DatasetGovernance {
  governanceId: string;
  sourceKind: "synthetic-sil";
  syntheticLearningContractStatus: R5StageStatus;
  realWorldGeneralizationStatus: "Open";
  safetyBanner: string;
  licenseId: string;
  allowedUses: string[];
  sensitivity: "synthetic";
  retentionPolicyId: string;
  redistributionAllowed: false;
}

export interface DatasetSnapshot {
  datasetId: string;
  artifactType: "axiom.intelligence.dataset-snapshot";
  contentHash: string;
  axisIds: string[];
  samples: unknown[];
  governance: DatasetGovernance;
}

export interface SplitPartition {
  splitId: "train" | "validation" | "test";
  sampleIds: string[];
  connectedGroupIds: string[];
  startTime: string;
  endTime: string;
}

export interface TrainingSplitManifest {
  manifestId: string;
  contentHash: string;
  partitions: SplitPartition[];
}

export interface AxisEvaluation {
  axisId: "X" | "Y" | "Z" | "B" | "C";
  status: "Validated" | "NoValidatedImprovement" | "InsufficientExcitation" | "Failed";
  baselineRmse?: number | null;
  modelRmse?: number | null;
  improvementRatio?: number | null;
  reasonCode?: string | null;
}

export interface R5Claim {
  claimId: string;
  title: string;
  status: "Supported" | "Refuted" | "Inconclusive";
  statement: string;
  reasonCode?: string | null;
  evidenceLevel?: "Observed" | "Validated" | null;
}

export interface R5Evidence {
  evidenceId: string;
  title: string;
  summary: string;
  contentHash?: string | null;
}

export interface R5Evaluation {
  syntheticLearningContractStatus: R5StageStatus;
  realWorldGeneralizationStatus: R5StageStatus;
  axisResults: AxisEvaluation[];
  oodDetectionRate: number;
  conformalCoverage: number;
  targetParityMaxAbsGap: number;
  baselineTestRmse: number;
  modelTestRmse: number;
  claims: R5Claim[];
  evidence: R5Evidence[];
}

export interface ModelBundle {
  bundleId: string;
  artifactType: "axiom.intelligence.model-bundle";
  contentHash: string;
  targetInterpreterId: string;
  inputContractId: string;
  preprocessorId: string;
  outputContractId: string;
  xAxisHead: {
    axisId: "X";
    featureOrder: string[];
    conformalRadius: number;
    featureEnvelope: { marginFraction: number };
  };
  axisDispositions: Array<{ axisId: string; status: string }>;
  resourceBudget: { targetRuntime: string; featureCount: number; deterministicNumericType: string; weightDecimalPlaces: number };
}

export interface R5ExamplePayload {
  manifest: R5Manifest;
  scenario: R5ScenarioSummary;
  dataset: DatasetSnapshot;
  splitManifest: TrainingSplitManifest;
  modelBundle: ModelBundle;
  evaluation?: R5Evaluation;
  runSpec?: unknown;
}
