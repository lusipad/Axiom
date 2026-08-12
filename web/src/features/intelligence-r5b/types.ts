import type { RunSpec } from "../../types";

export type R5BStageStatus = "Passed" | "Open" | "Failed" | "Inconclusive";

export interface R5BAcceptanceThresholds {
  minimumInDomainCases: number;
  minimumTotalCases: number;
  minimumDistinctDevices: number;
  minimumDistinctConditions: number;
  requiredAlignmentCoverage: number;
  minimumImprovementRatio: number;
  minimumConformalCoverage: number;
  requiredOodAbstentionRate: number;
  maximumTargetParityGap: number;
}

export interface R5BManifest {
  manifestId: string;
  schemaId: string;
  schemaVersion: number;
  stage: "R5-B";
  domainPackId: string;
  platform: "windows";
  defaultScenarioId: string;
  contractReadinessStatus: "Passed";
  realWorldGeneralizationStatus: "Open";
  safetyBanner: string;
  realityBanner: string;
  requiredEvidence: string[];
  acceptanceThresholds: R5BAcceptanceThresholds;
}

export interface R5BScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedOutcome: "Passed" | "Inconclusive" | "Invalid" | "Unsupported";
  expectedExecutionStatus: "Succeeded" | "Skipped";
  realWorldGeneralizationStatus: "Open";
}

export interface R5BReadinessCheck {
  checkId: string;
  title: string;
  status: "Passed" | "Open" | "Failed" | "Invalid";
  detail: string;
}

export interface DatasetGovernance {
  governanceId: string;
  sourceKind: "synthetic-sil";
  syntheticLearningContractStatus: R5BStageStatus;
  realWorldGeneralizationStatus: "Open";
  safetyBanner: string;
  licenseId: string;
  allowedUses: string[];
  sensitivity: "synthetic";
  retentionPolicyId: string;
  redistributionAllowed: false;
}

export interface IntelligenceSample {
  sampleId: string;
  axisId: "X" | "Y" | "Z" | "B" | "C";
  topology: "dual-table" | "head-table" | "dual-head";
  trajectoryFamily: string;
  taskId: string;
  deviceBatchId: string;
  pairId: string;
  declaredSplitId: "train" | "validation" | "test";
  scenarioRole: "in-domain" | "ood-probe";
  upstreamScenarioId: string;
  sourceCommandContentId: string;
  sourceCommandSampleId: string;
  labelDerivationId: string;
  eventTime: string;
  t: number;
  command: number;
  simulation: number;
  observation: number;
}

export interface DatasetSnapshot {
  artifactType: "axiom.intelligence.dataset-snapshot";
  schemaId: "axiom.intelligence.dataset-snapshot@1";
  schemaVersion: 1;
  datasetId: string;
  axisIds: Array<"X" | "Y" | "Z" | "B" | "C">;
  allowedSplitIds: Array<"train" | "validation" | "test">;
  governance: DatasetGovernance;
  selectionPolicyId: string;
  labelDerivationId: string;
  knownBiases: string[];
  coverageGaps: string[];
  samples: IntelligenceSample[];
  contentHash: string;
}

export interface SplitPartition {
  splitId: "train" | "validation" | "test";
  sampleIds: string[];
  connectedGroupIds: string[];
  startTime: string;
  endTime: string;
}

export interface SplitManifest {
  artifactType: "axiom.intelligence.split-manifest";
  schemaId: "axiom.intelligence.split-manifest@1";
  schemaVersion: 1;
  manifestId: string;
  datasetContentHash: string;
  partitions: SplitPartition[];
  contentHash: string;
}

export interface AxisDisposition {
  axisId: "X" | "Y" | "Z" | "B" | "C";
  status: "Validated" | "NoValidatedImprovement" | "InsufficientExcitation" | "Failed";
}

export interface ModelBundle {
  artifactType: "axiom.intelligence.model-bundle";
  schemaId: "axiom.intelligence.model-bundle@1";
  schemaVersion: 1;
  bundleId: string;
  domainPackId: string;
  evaluatorVersion: string;
  targetInterpreterId: string;
  inputContractId: string;
  preprocessorId: string;
  outputContractId: string;
  datasetContentHash: string;
  splitManifestHash: string;
  trainingReceiptHash: string;
  syntheticLearningContractStatus: "Passed" | "Failed";
  realWorldGeneralizationStatus: "Open";
  axisDispositions: AxisDisposition[];
  xAxisHead: {
    axisId: "X";
    lambdaValue: number;
    featureOrder: string[];
    weights: number[];
    conformalRadius: number;
    featureEnvelope: {
      minimums: number[];
      maximums: number[];
      marginFraction: number;
    };
  };
  resourceBudget: {
    targetRuntime: string;
    featureCount: number;
    deterministicNumericType: string;
    weightDecimalPlaces: number;
  };
  contentHash: string;
}

export interface TrainingReceipt {
  artifactType: "axiom.intelligence.training-receipt";
  schemaId: "axiom.intelligence.training-receipt@1";
  schemaVersion: 1;
  receiptId: string;
  methodId: string;
  datasetContentHash: string;
  splitManifestHash: string;
  lambdaValue: number;
  featureOrder: string[];
  trainSampleCount: number;
  validationSampleCount: number;
  testSampleCount: number;
  axisDispositions: AxisDisposition[];
  contentHash: string;
}

export interface TargetParityReceipt {
  artifactType: "axiom.intelligence.target-parity-receipt";
  schemaId: "axiom.intelligence.target-parity-receipt@1";
  schemaVersion: 1;
  receiptId: string;
  modelBundleHash: string;
  datasetContentHash: string;
  maxAbsGap: number;
  sampleCount: number;
  status: "Passed" | "Failed";
  contentHash: string;
}

export type R5BRunSpec = RunSpec & { subjectVersion?: string };

export interface R5BExamplePayload {
  manifest: R5BManifest;
  scenario: R5BScenarioSummary;
  readinessChecks: R5BReadinessCheck[];
  modelBundle: ModelBundle;
  dataset: DatasetSnapshot;
  splitManifest: SplitManifest;
  trainingReceipt: TrainingReceipt;
  parityReceipt: TargetParityReceipt;
  realHoldoutSet: Record<string, unknown> | null;
  runSpec: R5BRunSpec;
}
