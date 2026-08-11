import type { RunBundle, RunSpec } from "../../types";
import type {
  M1ReferencePath,
  M2CandidateTaskGeometry,
  NormalizedProgram,
} from "../five-axis-f1/types";
import type {
  ConfigurationCollisionModel,
  M3CandidateAxisPath,
} from "../five-axis-f2/types";
import type {
  M4ContinuousTrajectory,
  M5DiscreteCommand,
  MotionConstraintProfile,
} from "../five-axis-f3/types";

export interface F4ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  topology: "dual-table" | "head-table" | "dual-head";
  sutMode: "solver" | "replay";
  countsTowardClosure: boolean;
  expectedOutcome: "Passed" | "Failed";
}

export interface F4ArtifactDescriptor {
  stage: "M0" | "M1" | "M2" | "M3" | "M4" | "M5";
  artifactType: string;
  schemaId: string;
}

export interface F4ExpectedMetric {
  metricId: string;
  expectedStatus: string;
  expectedValue?: boolean | number;
  unit?: string;
}

export interface F4ExpectedClaim {
  claimId: string;
  claimClass: "M0" | "M1" | "M2" | "M3" | "M4" | "M5";
  expectedStatus: "Supported";
  evidenceLevel?: string;
}

export interface F4ExpectedEvidence {
  evidenceId: string;
  evidenceKind:
    | "adapter-descriptor"
    | "adapter-invocation"
    | "adapter-receipt"
    | "cross-validation"
    | "reconstruction-collision"
    | "stage-acceptance";
  required: boolean;
}

export interface F4ToleranceBinding {
  toleranceId: string;
  target:
    | "position"
    | "orientation"
    | "sigma"
    | "collision-clearance"
    | "time"
    | "velocity"
    | "acceleration"
    | "jerk"
    | "quantization";
  tolerance: {
    absolute: number;
    relative: number;
    unit: string;
  };
}

export interface F4MathStageManifest {
  manifestId: "five-axis.f4-math-stage-manifest@1";
  schemaId: "five-axis.f4-math-stage-manifest@1";
  schemaVersion: 1;
  stage: "F4";
  artifactDescriptors: F4ArtifactDescriptor[];
  adapterTransport: "in-process";
  capabilityIds: string[];
  fixtureContentIds: string[];
  policyIds: string[];
  numericEnvironment: Record<string, string>;
  expectedMetrics: F4ExpectedMetric[];
  expectedClaims: F4ExpectedClaim[];
  expectedEvidence: F4ExpectedEvidence[];
  tolerances: F4ToleranceBinding[];
  decisions: Array<{ decisionId: string; status: string; rationale: string }>;
}

export interface AdapterDescriptor {
  adapterId: string;
  version: string;
  role: "reference" | "sut";
  subjectId: string;
  subjectVersion: string;
  inputType: "five-axis.m4-continuous-trajectory";
  outputType: "five-axis.m5-discrete-command";
  transport: "in-process";
}

export interface AdapterInvocation {
  invocationId: string;
  descriptor: AdapterDescriptor;
  inputM4Id: string;
  inputM4ContentHash: string;
  policyId: string;
  samplePeriod: number;
  finalHold: boolean;
}

export interface AdapterReceipt {
  invocation: AdapterInvocation;
  descriptor: AdapterDescriptor;
  status: "Succeeded" | "Failed" | "Unsupported";
  inputContentHash: string;
  outputContentHash?: string;
  deterministicWorkUnits: number;
  failureCode?: string;
  failureMessage?: string;
  numericEnvironment: Record<string, string>;
}

export interface CrossValidationResult {
  referenceContentHash: string;
  sutContentHash: string;
  status: "Supported" | "Refuted" | "Inconclusive";
  maxPositionGap: number;
  maxVelocityGap: number;
  maxAccelerationGap: number;
  maxJerkGap: number;
  tolerances: F4ToleranceBinding[];
  evidenceLevel: "Exact" | "Validated" | "Certified";
  method: string;
}

export interface M5CollisionIntervalResult {
  intervalId: string;
  tStart: number;
  tEnd: number;
  status: "safe" | "collision" | "unsupported" | "unresolved";
  witnessTime?: number | null;
  minimumClearanceLowerBound?: number | null;
  reasonCode?: string | null;
}

export interface M5CollisionVerification {
  contributesToClaimId: "five-axis.model-collision-free-claim@1";
  commandId: string;
  commandContentHash: string;
  sourceM3Id: string;
  sourceM3ContentHash: string;
  collisionModelId: string;
  collisionModelContentHash: string;
  reconstructionPolicyId: string;
  status: "safe" | "collision" | "unsupported" | "unresolved";
  coverageStatus: "complete" | "partial";
  supportsModelCollisionAggregation: boolean;
  evidenceLevel: "Certified" | "Validated" | "Observed";
  method: string;
  intervalEvaluations: M5CollisionIntervalResult[];
}

export interface F4ScenarioResult {
  scenarioId: string;
  topology: "dual-table" | "head-table" | "dual-head";
  sutMode: "solver" | "replay";
  countsTowardClosure: boolean;
  outcome: "Passed" | "Failed";
  referenceReceiptStatus: "Succeeded" | "Failed" | "Unsupported";
  sutReceiptStatus: "Succeeded" | "Failed" | "Unsupported";
  crossValidationStatus: "Supported" | "Refuted" | "Inconclusive";
  collisionStatus: "safe" | "collision" | "unsupported" | "unresolved";
}

export interface TopologyCoverage {
  topology: "dual-table" | "head-table" | "dual-head";
  covered: boolean;
}

export interface CounterexampleCoverage {
  counterexampleId: string;
  covered: boolean;
}

export interface GateClaimStatus {
  claimId: string;
  status: "Supported" | "Refuted" | "Inconclusive" | "Unsupported" | "Insufficient";
  evidenceLevel?: string;
}

export interface F4StageAcceptanceReport {
  reportId: string;
  stage: "F4";
  scenarioResults: F4ScenarioResult[];
  topologyCoverage: TopologyCoverage[];
  counterexampleCoverage: CounterexampleCoverage[];
  gateClaimStatuses: GateClaimStatus[];
  status: "Passed" | "Failed";
  contentHash: string;
}

export interface F4ExamplePayload {
  manifest: F4MathStageManifest;
  scenario: F4ScenarioSummary;
  source: {
    sourceText: string;
    normalizedProgram: NormalizedProgram;
    referencePath: M1ReferencePath;
  };
  artifacts: {
    candidateGeometry: M2CandidateTaskGeometry;
    stockStateGeometries: Record<string, Record<string, unknown>>;
    axisPath: M3CandidateAxisPath;
    motionConstraintProfile: MotionConstraintProfile;
    continuousTrajectory: M4ContinuousTrajectory;
    collisionModel: ConfigurationCollisionModel;
    referenceInvocation: AdapterInvocation;
    sutInvocation: AdapterInvocation;
    referenceCommand?: M5DiscreteCommand | null;
    sutCommand?: M5DiscreteCommand | null;
  };
  evidence: {
    referenceReceipt: AdapterReceipt;
    sutReceipt: AdapterReceipt;
    crossValidation?: CrossValidationResult | null;
    collisionVerification?: M5CollisionVerification | null;
    scenarioResult: F4ScenarioResult;
  };
  acceptanceReport: F4StageAcceptanceReport;
  runSpec?: RunSpec | null;
}

export interface F4RunBundle extends RunBundle {}
