import type { RunBundle, RunSpec } from "../../types";
import type {
  M1ReferencePath,
  M2CandidateTaskGeometry,
  NormalizedProgram,
  ToleranceBinding,
  Vector3,
} from "../five-axis-f1/types";

export interface F2ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  topology: "dual-table" | "head-table" | "dual-head";
  expectedClaimStatusById: Record<string, string>;
}

export interface F2ArtifactDescriptor {
  stage: "M0" | "M1" | "M2" | "M3";
  artifactType: string;
  schemaId: string;
}

export interface F2MathStageManifest {
  manifestId: string;
  schemaId: string;
  schemaVersion: number;
  stage: "F2";
  artifactDescriptors: F2ArtifactDescriptor[];
  machineProfileSchemaId: string;
  machineProfileId: string;
  machineProfileContentId: string;
  capabilityIds: string[];
  fixtureContentIds: string[];
  policyIds: string[];
  numericEnvironment: Record<string, string>;
  expectedMetrics: Array<{
    metricId: string;
    expectedStatus: string;
    expectedValue?: boolean | number;
    unit?: string;
  }>;
  expectedClaims: Array<{
    claimId: string;
    claimClass: string;
    expectedStatus: string;
    evidenceLevel?: string;
  }>;
  expectedEvidence: Array<{
    evidenceId: string;
    evidenceKind: string;
    required: boolean;
  }>;
  tolerances: ToleranceBinding[];
  decisions: Array<{ decisionId: string; status: string; rationale: string }>;
}

export interface MachineAxis {
  axisId: string;
  axisOrder: number;
  jointType: "prismatic" | "revolute";
  installationSide: "workpiece" | "tool";
  parentAxisId?: string;
  semanticRole: string;
  direction: Vector3;
  limits: { lower: number; upper: number; unit: "mm" | "rad" };
  periodic: boolean;
}

export interface MachineProfile {
  artifactType: "five-axis.machine-profile";
  schemaVersion: number;
  profileId: string;
  profileVersion: number;
  topology: "dual-table" | "head-table" | "dual-head";
  axes: MachineAxis[];
}

export interface IKSolution {
  solutionId: string;
  sigma: number;
  branchId: string;
  jointValues: number[];
  wrapState: Array<{ axisId: string; turns: number }>;
  singularity: {
    status: "regular" | "singular" | "near-singular";
    conditioningMetric?: number;
    minimumSingularValue?: number;
  };
  withinLimits: boolean;
}

export interface BranchNode {
  branchId: string;
  sigmaStart: number;
  sigmaEnd: number;
  solutionIds: string[];
  status: "active" | "terminated" | "merged";
}

export interface JointPolynomialSegment {
  segmentId: string;
  branchId: string;
  sigmaStart: number;
  sigmaEnd: number;
  interpolation: "linear" | "cubic-hermite";
  coefficientBasis: "local-power@1";
  coefficients: number[][];
}

export interface M3CandidateAxisPath {
  artifactType: "five-axis.m3-candidate-axis-path";
  schemaVersion: number;
  axisPathId: string;
  sourceCandidateGeometryContentId: string;
  machineProfileContentId: string;
  machineProfile: MachineProfile;
  ikSolutions: IKSolution[];
  branchGraph: {
    graphId: string;
    rootBranchIds: string[];
    branches: BranchNode[];
    transitions: Array<Record<string, unknown>>;
  };
  jointSegments: JointPolynomialSegment[];
  nodeEvents: Array<{
    nodeId: string;
    sigma: number;
    eventType: string;
    leftSegmentId?: string;
    rightSegmentId?: string;
  }>;
  kinematicsCertificate: {
    certificateId: string;
    evidenceLevel: string;
    continuousMethod: string;
    selectedBranchId: string;
    intervalCount: number;
    positionResidualUpperBound: number;
    orientationResidualUpperBound: number;
    axisLimitNormalizedMarginLowerBound: number;
    minimumSingularValueLowerBound: number;
    policyIds: string[];
  };
}

export interface ConfigurationCollisionModel {
  modelId: string;
  contentId: string;
  policyId: string;
  coverageStatus: "complete" | "partial";
  coveredPairKinds: string[];
  entities: Array<{
    entityId: string;
    entityKind: "machine-component" | "environment";
    anchorType: string;
    anchorAxisId?: string;
  }>;
  pairs: Array<{
    pairId: string;
    pairKind: "machine-self" | "environment";
    leftEntityId: string;
    rightEntityId: string;
  }>;
}

export interface CollisionEvaluation {
  queryKind: "point" | "segment" | "path";
  status: string;
  collisionFree?: boolean;
  certificateKind: string;
  reasonCode: string;
  evidenceLevel: string;
  continuousMethod: string;
  minimumClearanceLowerBound?: number;
  clearanceUnit: string;
  evaluationCount: number;
  subdivisionCount: number;
  pairResults: Array<{
    pairId: string;
    pairKind: string;
    status: string;
    reasonCode: string;
    minimumClearanceLowerBound?: number;
    witnessSigma?: number;
  }>;
}

export interface F2ExamplePayload {
  manifest: F2MathStageManifest;
  scenario: F2ScenarioSummary;
  source: {
    sourceText: string;
    normalizedProgram: NormalizedProgram;
    referencePath: M1ReferencePath;
  };
  artifacts: {
    candidateGeometry: M2CandidateTaskGeometry;
    axisPath: M3CandidateAxisPath;
    machineProfile: MachineProfile;
    collisionModel: ConfigurationCollisionModel;
  };
  runSpec: RunSpec;
}

export interface F2RunBundle extends RunBundle {
  report: RunBundle["report"] & {
    metricResults: Array<RunBundle["report"]["metricResults"][number] & {
      details?: {
        collisionEvaluation?: CollisionEvaluation;
        [key: string]: unknown;
      };
    }>;
  };
}
