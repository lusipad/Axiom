export type Point = number[];

export interface OrderedPointSequence {
  artifactType: "ordered-point-sequence";
  schemaVersion: number;
  points: Point[];
  semantics?: {
    unit?: string;
    coordinateFrame?: string;
    closed?: boolean;
    [key: string]: unknown;
  };
}

export interface SubjectDefinition {
  subjectId: string;
  subjectVersion: string;
  displayName: string;
  description: string;
  runnerId: string;
  parameterSchemaId: string;
}

export interface CatalogDomainPack {
  domainPackId: string;
  comparisonPolicyIds: string[];
  runnerIds: string[];
  runtimeBound: boolean;
}

export interface ArtifactAdapterDescriptor {
  adapterId: string;
  sourceArtifactType: string;
  targetArtifactType: string;
}

export interface Catalog {
  subjects: SubjectDefinition[];
  domainPacks: CatalogDomainPack[];
  artifactAdapters: ArtifactAdapterDescriptor[];
}

export interface MetricRequirement {
  metricId: string;
  threshold?: {
    operator: string;
    value: number;
    unit?: string;
  };
}

export interface ExperimentSpec {
  experimentId: string;
  sharedInput: OrderedPointSequence;
  parameterSet: {
    parameterSetId: string;
    parameterSchemaId: string;
    schemaVersion: number;
    values: Record<string, unknown>;
    units: Record<string, string>;
  };
  arms: Array<{
    armId: string;
    subjectId: string;
    subjectVersion: string;
    runnerId?: string;
  }>;
  evaluation: {
    case: {
      caseId: string;
      requiredMetrics: Array<string | MetricRequirement>;
      scoreProfile?: unknown;
    };
    referenceBinding?: unknown;
  };
  domainPackId?: string;
  evaluatorVersion?: string;
  comparisonPolicyId?: string;
}

export interface EvidenceDescriptor {
  level: string;
  method: string;
}

export interface MetricResult {
  metricId: string;
  metricDefinitionId?: string;
  status: string;
  value?: unknown;
  unit?: string;
  thresholdPassed?: boolean;
  reasonCode?: string;
  requires?: string[];
  evidence?: EvidenceDescriptor;
  details?: Record<string, unknown>;
}

export interface Claim {
  claimDefinitionId: string;
  status: string;
  predicate: string;
  metricId?: string;
  evidence?: EvidenceDescriptor;
}

export interface DomainFailure {
  code: string;
  message: string;
  path?: string;
  severity?: string;
}

export interface CapabilityResolution {
  capabilityId: string;
  source: string;
}

export interface CoordinateSpec {
  coordinateSystem: string;
  axes: string[];
  unit: string;
  coordinateFrame: string;
}

export interface StageEnvelope {
  envelopeId: string;
  stage: string;
  envelopeType: string;
  schemaId: string;
  contentId: string;
  coordinateSpec?: CoordinateSpec | null;
  capabilityIds: string[];
}

export interface MathStageManifest {
  manifestId: string;
  schemaVersion: number;
  stage: string;
  capabilityIds: string[];
  fixtureContentIds: string[];
  policyVersions: Record<string, string>;
  numericEnvironment: Record<string, string>;
  expectedStatus: string;
  expectedClaim: Record<string, unknown> | null;
  tolerances: Array<{
    metricId: string;
    unit: string;
    value: number;
  }>;
  envelopes: StageEnvelope[];
}

export interface FiveAxisSample {
  sampleIndex: number;
  position: number[];
}

export interface FiveAxisPathProgress {
  progressKind: string;
  unit: string;
  values: number[];
}

export interface FiveAxisNodeEvent {
  nodeIndex: number;
  eventType: string;
  regularityClass: string;
  progressValue: number;
}

export interface FiveAxisRegularity {
  continuityClass: string;
  nodeEvents: FiveAxisNodeEvent[];
}

export interface FiveAxisSampledCartesianView {
  artifactType: "five-axis.sampled-cartesian-position-view";
  schemaVersion: number;
  derivedViewKind: string;
  sourceArtifactType: string;
  sourceCoordinateMode: string;
  coordinateSpec: CoordinateSpec;
  samples: FiveAxisSample[];
  pathProgress?: FiveAxisPathProgress;
  regularity?: FiveAxisRegularity;
  envelopes: StageEnvelope[];
  capabilityIds: string[];
}

export interface RunSpec {
  subjectId: string;
  domainPackId: string;
  runnerId: string;
  evaluatorVersion?: string;
  request: Record<string, unknown>;
}

export interface RunBundle {
  run: {
    runId: string;
    subjectId: string;
    domainPackId: string;
    runnerId: string;
    runSpecHash: string;
    reportContentHash: string;
    executionStatus: string;
    caseOutcome: string;
    evaluatorVersion?: string;
    contentHash: string;
    numericEnvironment?: Record<string, unknown>;
    provenance?: Record<string, unknown>;
  };
  observation?: {
    observationId?: string;
    subjectId?: string;
    artifact: OrderedPointSequence | FiveAxisSampledCartesianView | Record<string, unknown>;
    artifactHash: string;
    observationHash?: string;
    source: string;
  };
  report: {
    executionStatus: string;
    caseOutcome: string;
    metricResults: MetricResult[];
    capabilities?: CapabilityResolution[];
    domainFailures?: DomainFailure[];
    provenance?: Record<string, unknown>;
    score?: {
      status: string;
      value?: number;
    };
    contentHash?: string;
    evaluatorVersion?: string;
  };
  claims: Claim[];
  bundleHash: string;
}

export interface ExperimentArmResult {
  armId: string;
  subjectId: string;
  subjectVersion: string;
  executionStatus: string;
  caseOutcome: string;
  outputArtifactHash?: string;
  runBundle?: RunBundle;
  failure?: {
    code: string;
    message: string;
  };
}

export interface MetricComparison {
  metricId: string;
  left?: number;
  right?: number;
  unit?: string;
  comparable: boolean;
  delta?: number;
  preferredSubjectId?: string;
}

export interface ExperimentReport {
  experimentSpec: ExperimentSpec;
  experimentSpecHash: string;
  sharedInputHash: string;
  parameterSetHash: string;
  executionStatus: string;
  caseOutcome: string;
  armResults: ExperimentArmResult[];
  comparison?: {
    comparisonId: string;
    policyId: string;
    compatibility: {
      compatible: boolean;
      issues: Array<{ code: string; message: string }>;
    };
    metricComparisons: MetricComparison[];
    contentHash: string;
  };
  failures: Array<{ code: string; message: string }>;
  contentHash: string;
}
