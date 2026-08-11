import type { RunBundle, RunSpec } from "../../types";

export type Vector3 = [number, number, number];

export interface F1ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedClaimStatusById: Record<string, string>;
}

export interface F1ArtifactDescriptor {
  stage: "M0" | "M1" | "M2";
  artifactType: string;
  schemaId: string;
}

export interface F1MathStageManifest {
  manifestId: string;
  schemaId: string;
  schemaVersion: number;
  stage: "F1";
  artifactDescriptors: F1ArtifactDescriptor[];
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

export interface CoordinateContext {
  unit: string;
  coordinateFrame: string;
}

export interface NormalizedEvent {
  eventId: string;
  eventType: string;
  lineage: {
    statementId: string;
    statementIndex: number;
    line: number;
    column: number;
    sourceText: string;
    sourcePath?: string;
  };
  position?: Vector3;
  toolAxis?: Vector3;
  toolAxisSource?: string;
  sourceToolAxis?: Vector3;
  toolAxisSourceStatementId?: string;
  feedRate?: number;
  duration?: number;
}

export interface NormalizedProgram {
  artifactType: "five-axis.normalized-program";
  schemaVersion: number;
  programId: string;
  sourceSyntaxId: string;
  coordinateContext: CoordinateContext;
  events: NormalizedEvent[];
}

export interface PathProgressMapping {
  mappingId: string;
  sourceSegmentId: string;
  sourceLocalStart: number;
  sourceLocalEnd: number;
  sigmaStart: number;
  sigmaEnd: number;
  degenerateKind: string;
}

export interface PathProgress {
  progressId: string;
  schemaVersion: number;
  progressParameter: "sigma";
  unit: "dimensionless";
  mappings: PathProgressMapping[];
}

export interface PositionSegment {
  segmentId: string;
  segmentType: "line" | "arc" | "helix" | "bezier" | "bspline";
  sigmaStart: number;
  sigmaEnd: number;
  startPoint?: Vector3;
  endPoint?: Vector3;
  center?: Vector3;
  controlPoints?: Vector3[];
}

export interface OrientationSegment {
  segmentId: string;
  segmentType: "constant" | "s2-slerp";
  sigmaStart: number;
  sigmaEnd: number;
  axis?: Vector3;
  startAxis?: Vector3;
  endAxis?: Vector3;
}

export interface NodeEvent {
  nodeId: string;
  sigma: number;
  eventType: string;
  leftSegmentId?: string;
  rightSegmentId?: string;
}

export interface RegularityCertificate {
  certificateId: string;
  requestedClass: string;
  segmentEvidence: Array<{ segmentId: string; certifiedClass: string }>;
  nodeEvidence: Array<{ nodeId: string; certifiedClass: string; eventRule: string }>;
}

export interface M1ReferencePath {
  artifactType: "five-axis.m1-reference-path";
  schemaVersion: number;
  referencePathId: string;
  coordinateContext: CoordinateContext;
  pathProgress: PathProgress;
  positionSemantics: "continuous" | "static";
  staticPosition?: Vector3;
  positionSegments: PositionSegment[];
  orientationSegments: OrientationSegment[];
  nodeEvents: NodeEvent[];
  regularityCertificate?: RegularityCertificate;
}

export interface CorrespondenceCertificate {
  certificateId: string;
  sourceGeometryId: string;
  targetReferencePathId: string;
  policy: {
    strategyId: string;
    allowedSourceInterval: [number, number];
    allowedTargetInterval: [number, number];
    [key: string]: unknown;
  };
  canonicalNodes: Array<{
    pathRole: "source" | "target";
    nodeId: string;
    sigma: number;
    segmentId?: string;
  }>;
  allowedSourceIntervals: Array<{
    sourceSegmentId: string;
    allowedTargetIntervals: Array<[number, number]>;
  }>;
  selectedNodeMapping: Array<{ sourceNodeId: string; targetNodeId: string }>;
  intervals: Array<{
    intervalId: string;
    sourceSigmaStart: number;
    sourceSigmaEnd: number;
    targetSigmaStart: number;
    targetSigmaEnd: number;
    sourceSegmentId?: string;
    targetSegmentId?: string;
  }>;
  primaryObjectiveLower: number;
  primaryObjectiveUpper: number;
  objectiveDomain: "continuous" | "canonical-grid";
  tieBreakObjective: string;
  solverVersion: string;
  evidenceLevel: "machine-replayable" | "certificate-summary";
}

export interface ToleranceBinding {
  toleranceId: string;
  target: "position" | "orientation" | "sigma" | "collision-clearance";
  tolerance: { absolute: number; relative: number; unit: string };
}

export interface AxisAlignedBoundingBox {
  minCorner: Vector3;
  maxCorner: Vector3;
}

export interface CollisionContext {
  contextId: string;
  toolComponents: Array<{
    componentId: string;
    componentKind: "cutter" | "shaft" | "holder";
    shapeType: "sphere" | "capsule";
    radius: number;
    axisStartOffset: number;
    axisEndOffset: number;
  }>;
  stockFixtures: Array<{
    stockFixtureId: string;
    category: "stock" | "fixture";
    aabb: AxisAlignedBoundingBox;
  }>;
  allowedRemoval: Array<{
    removalId: string;
    toolComponentId: string;
    stockFixtureId: string;
    region?: AxisAlignedBoundingBox;
  }>;
  contactPolicy: {
    policyId: string;
    defaultPolicy: string;
    rules: Array<{
      ruleId: string;
      leftCategory: string;
      rightCategory: string;
      contactPolicy: "allowed" | "forbidden";
    }>;
  };
}

export interface ProcessStateTimeline {
  timelineId: string;
  stockUpdatePolicy: { policyId: string };
  failureStateSemantics: { policyId: string; failedStateMeaning: string };
  intervals: Array<{
    intervalId: string;
    sigmaStart: number;
    sigmaEnd: number;
    motionMode: string;
    spindleState: string;
    toolComponentId?: string;
    coolantOn: boolean;
    inputStockState: { stateId: string; contentId: string };
    outputStockState?: { stateId: string; contentId: string };
  }>;
}

export interface M2CandidateTaskGeometry {
  artifactType: "five-axis.m2-candidate-task-geometry";
  schemaVersion: number;
  candidateGeometryId: string;
  sourceReferencePathId: string;
  sourceReferencePathContentId?: string;
  coordinateContext: CoordinateContext;
  pathProgress: PathProgress;
  positionSemantics: "continuous" | "static";
  staticPosition?: Vector3;
  positionSegments: PositionSegment[];
  orientationSegments: OrientationSegment[];
  nodeEvents: NodeEvent[];
  regularityCertificate?: RegularityCertificate;
  tolerances: ToleranceBinding[];
  correspondence: CorrespondenceCertificate;
  collisionContext?: CollisionContext;
  processStateTimeline?: ProcessStateTimeline;
}

export interface F1ExamplePayload {
  manifest: F1MathStageManifest;
  scenario: F1ScenarioSummary;
  source: {
    sourceText: string;
    normalizedProgram: NormalizedProgram;
    referencePath: M1ReferencePath;
  };
  artifacts: {
    candidateGeometry: M2CandidateTaskGeometry;
    stockStateGeometries: Record<string, unknown>;
  };
  runSpec: RunSpec;
}

export interface F1RunBundle extends RunBundle {
  report: RunBundle["report"] & {
    metricResults: Array<RunBundle["report"]["metricResults"][number] & {
      details?: Record<string, unknown>;
    }>;
  };
}
