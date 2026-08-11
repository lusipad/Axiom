import type { RunBundle, RunSpec } from "../../types";
import type { M3CandidateAxisPath } from "../five-axis-f2/types";

export interface F3ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedClaimStatusById: Record<string, string>;
}

export interface F3ArtifactDescriptor {
  stage: "M0" | "M1" | "M2" | "M3" | "M4" | "M5";
  artifactType: string;
  schemaId: string;
}

export type F3ClaimClass = "M0" | "M1" | "M2" | "M3" | "M4" | "M5" | "DeviceSafe";
export type F3ClaimStatus = "Supported" | "Refuted" | "Inconclusive" | "Unsupported" | "Insufficient";
export type F3EvidenceKind =
  | "lineage"
  | "regularity"
  | "correspondence"
  | "ik-branch"
  | "wrap"
  | "kinematics"
  | "configuration-collision"
  | "singularity"
  | "time-law"
  | "node-contract"
  | "reconstruction"
  | "error-ledger";

export interface F3ExpectedMetric {
  metricId: string;
  expectedStatus: string;
  expectedValue?: boolean | number;
  unit?: string;
}

export interface F3ExpectedClaim {
  claimId: string;
  claimClass: F3ClaimClass;
  expectedStatus: F3ClaimStatus;
  evidenceLevel?: string;
}

export interface F3ExpectedEvidence {
  evidenceId: string;
  evidenceKind: F3EvidenceKind;
  required: boolean;
}

export interface F3ToleranceBinding {
  toleranceId: string;
  target: "position" | "orientation" | "sigma" | "collision-clearance" | "time" | "velocity" | "acceleration" | "jerk" | "quantization";
  tolerance: {
    absolute: number;
    relative: number;
    unit: string;
  };
}

export interface F3MathStageManifest {
  manifestId: "five-axis.f3-math-stage-manifest@1";
  schemaId: "five-axis.f3-math-stage-manifest@1";
  schemaVersion: 1;
  stage: "F3";
  artifactDescriptors: F3ArtifactDescriptor[];
  motionConstraintProfileSchemaId: "five-axis.motion-constraint-profile@1";
  motionConstraintProfileId: string;
  motionConstraintProfileContentId: string;
  capabilityIds: string[];
  fixtureContentIds: string[];
  policyIds: string[];
  numericEnvironment: Record<string, string>;
  expectedMetrics: F3ExpectedMetric[];
  expectedClaims: F3ExpectedClaim[];
  expectedEvidence: F3ExpectedEvidence[];
  tolerances: F3ToleranceBinding[];
  decisions: Array<{ decisionId: string; status: string; rationale: string }>;
}

export interface BoundaryState {
  sigmaVelocity: number;
  sigmaAcceleration: number;
}

export interface AxisMotionConstraint {
  axisId: string;
  unit: "mm" | "rad";
  maximumVelocity: number;
  maximumAcceleration: number;
  maximumJerk?: number | null;
}

export interface NodeMotionConstraint {
  nodeId: string;
  sigma: number;
  boundaryMode: "allow-continuous" | "mandatory-stop" | "dwell";
  dwellSeconds?: number | null;
  rationale?: string | null;
}

export interface MotionConstraintProfile {
  artifactType: "five-axis.motion-constraint-profile";
  schemaId: "five-axis.motion-constraint-profile@1";
  schemaVersion: 1;
  profileId: string;
  machineProfileId: string;
  machineProfileContentId: string;
  axisConstraints: AxisMotionConstraint[];
  startBoundary: BoundaryState;
  endBoundary: BoundaryState;
  maximumPathVelocity?: number | null;
  pathVelocityUnit?: string | null;
  feedSource?: string | null;
  nodeConstraints: NodeMotionConstraint[];
  policyIds: string[];
  provenance: ProvenanceRef[];
}

export interface ProvenanceRef {
  sourceStage: "M0" | "M1" | "M2" | "M3" | "M4" | "M5";
  sourceId: string;
  sourceContentId?: string;
  method?: string | null;
}

export interface TrajectoryErrorLedgerEntry {
  entryId: string;
  quantity: string;
  unit: string;
  source: string;
  bound: number;
  method: string;
  code: string;
  severity: "warning" | "error";
  message: string;
  relatedNodeId?: string | null;
  relatedSegmentId?: string | null;
}

export interface TrajectoryOptimality {
  classification: "ProvenOptimal" | "Bounded" | "FeasibleOnly" | "NotApplicable";
  proofGapSeconds?: number | null;
  rationale: string;
}

export interface ContinuousTrajectorySpan {
  spanId: string;
  spanKind: "move" | "dwell";
  segmentIds: string[];
  startTimeSeconds: number;
  endTimeSeconds: number;
  sigmaStart: number;
  sigmaEnd: number;
  timeLaw: {
    lawKind: "triangular" | "trapezoidal" | "smoothstep7" | "dwell";
    durationSeconds: number;
    accelerationDurationSeconds?: number | null;
    cruiseDurationSeconds?: number | null;
    decelerationDurationSeconds?: number | null;
    sigmaVelocityLimit?: number | null;
    sigmaAccelerationLimit?: number | null;
    sigmaJerkLimit?: number | null;
    peakSigmaVelocity: number;
    peakSigmaAcceleration: number;
    peakSigmaJerk: number;
  };
}

export interface ContinuousTrajectoryVerification {
  verificationId: string;
  solverId: string;
  evidenceLevel: "Certified" | "Validated" | "Observed";
  claimId: "five-axis.continuously-feasible-claim@1";
  overallStatus: "Supported" | "Unsupported" | "Refuted";
  totalDurationSeconds: number;
  optimality: TrajectoryOptimality;
  nodeContracts: Array<{
    nodeId: string;
    sigma: number;
    eventType: string;
    boundaryMode: "allow-continuous" | "mandatory-stop" | "dwell";
    dwellSeconds?: number | null;
    source: "regularity" | "event-type" | "profile";
  }>;
  axisConstraintUsage: Array<{
    axisId: string;
    unit: "mm" | "rad";
    maximumVelocity: number;
    velocityLimit: number;
    maximumAcceleration: number;
    accelerationLimit: number;
    maximumJerk?: number | null;
    jerkLimit?: number | null;
  }>;
  errorLedger: TrajectoryErrorLedgerEntry[];
}

export interface M4ContinuousTrajectory {
  artifactType: "five-axis.m4-continuous-trajectory";
  schemaId: "five-axis.m4-continuous-trajectory@1";
  schemaVersion: 1;
  trajectoryId: string;
  sourceAxisPath: M3CandidateAxisPath;
  sourceAxisPathContentId: string;
  motionConstraintProfile: MotionConstraintProfile;
  motionConstraintProfileContentId: string;
  solverId: string;
  timingMode: "second-order-optimal" | "smoothstep7-feasible";
  spans: ContinuousTrajectorySpan[];
  verification: ContinuousTrajectoryVerification;
  provenance: ProvenanceRef[];
}

export interface ReconstructionPolicy {
  policyId:
    | "five-axis.reconstruction.reference-m4@1"
    | "five-axis.reconstruction.polynomial@1"
    | "five-axis.reconstruction.foh@1"
    | "five-axis.reconstruction.zoh@1";
}

export interface M5ProvenanceRef {
  sourceStage: "M0" | "M1" | "M2" | "M3" | "M4" | "M5";
  sourceId: string;
  sourceContentId?: string;
  method?: string | null;
}

export interface M5TaskPose {
  position: [number, number, number];
  toolAxis: [number, number, number];
}

export interface M5Sample {
  sampleId: string;
  sampleIndex: number;
  t: number;
  cycle: number;
  sigma: number;
  q: [number, number, number, number, number];
  qdot: [number, number, number, number, number];
  qddot: [number, number, number, number, number];
  qjerk: [number, number, number, number, number];
  taskPose: M5TaskPose;
  provenance: M5ProvenanceRef[];
}

export interface M5IntervalRecord {
  intervalId: string;
  intervalIndex: number;
  startSampleIndex: number;
  endSampleIndex: number;
  tStart: number;
  tEnd: number;
  intervalSemantics: "[t_k,t_k+1)";
  certificateCoefficients: [
    [number, number, number, number, number],
    [number, number, number, number, number],
    [number, number, number, number, number],
    [number, number, number, number, number],
    [number, number, number, number, number],
    [number, number, number, number, number],
    [number, number, number, number, number],
    [number, number, number, number, number],
  ];
}

export interface M5KinematicLimits {
  positionUnits: [string, string, string, string, string];
  velocityLimits?: [number, number, number, number, number] | null;
  accelerationLimits?: [number, number, number, number, number] | null;
  jerkLimits?: [number, number, number, number, number] | null;
}

export interface M5AxisVerification {
  axis: number;
  unit: string;
  status: "Supported" | "Refuted" | "Unsupported";
  observedPeak?: number | null;
  limit?: number | null;
  intervalId?: string | null;
  reasonCode?: string | null;
}

export interface M5QuantityVerification {
  quantity: "position" | "velocity" | "acceleration" | "jerk" | "interval-certified";
  status: "Supported" | "Refuted" | "Unsupported";
  axisResults: M5AxisVerification[];
  reasonCode?: string | null;
}

export interface M5VerificationResult {
  status: "Supported" | "Refuted" | "Unsupported";
  evidenceLevel: "Certified" | "Validated" | "Observed";
  method: string;
  policyId: ReconstructionPolicy["policyId"];
  artifactType: "five-axis.m5-sampled-trajectory" | "five-axis.m5-discrete-command";
  artifactId: string;
  sourceM4ContentId: string;
  quantities: M5QuantityVerification[];
  errorLedger: M5ErrorLedgerEntry[];
}

export interface M5ErrorLedgerEntry {
  quantity: "sigma" | "joint-position" | "joint-velocity" | "joint-acceleration" | "joint-jerk" | "position" | "orientation";
  axis?: number | null;
  unit: string;
  source: string;
  bound: number;
  method: string;
}

export interface M5ArtifactBase {
  schemaId: "five-axis.m5-sampled-trajectory@1" | "five-axis.m5-discrete-command@1";
  schemaVersion: 1;
  contentId: string;
  sourceM4: M4ContinuousTrajectory;
  sourceM4Id: string;
  sourceM4ContentId: string;
  samplePeriod: number;
  duration: number;
  remainderDuration: number;
  terminalSampleIncluded: true;
  finalHold: boolean;
  reconstructionPolicy: ReconstructionPolicy;
  limits: M5KinematicLimits;
  samples: M5Sample[];
  intervals: M5IntervalRecord[];
  provenance: M5ProvenanceRef[];
}

export interface M5SampledTrajectory extends M5ArtifactBase {
  artifactType: "five-axis.m5-sampled-trajectory";
  sampledTrajectoryId: string;
}

export interface M5DiscreteCommand extends M5ArtifactBase {
  artifactType: "five-axis.m5-discrete-command";
  discreteCommandId: string;
}

export type F3ExampleArtifacts = {
  axisPath: M3CandidateAxisPath;
  motionConstraintProfile: MotionConstraintProfile;
  continuousTrajectory: M4ContinuousTrajectory;
} & (
  | { sampledTrajectory: M5SampledTrajectory; discreteCommand?: never }
  | { sampledTrajectory?: never; discreteCommand: M5DiscreteCommand }
);

export interface F3ExamplePayload {
  manifest: F3MathStageManifest;
  scenario: F3ScenarioSummary;
  source?: {
    sourceText?: string;
  };
  artifacts: F3ExampleArtifacts;
  runSpec: RunSpec;
}

export interface F3RunBundle extends RunBundle {}
