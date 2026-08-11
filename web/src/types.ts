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

export interface Catalog {
  subjects: SubjectDefinition[];
  domainPacks: Array<{
    domainPackId: string;
    comparisonPolicyIds: string[];
    runnerIds: string[];
  }>;
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

export interface MetricResult {
  metricId: string;
  status: string;
  value?: number;
  unit?: string;
  thresholdPassed?: boolean;
  evidence?: {
    level: string;
    method: string;
  };
}

export interface Claim {
  claimId: string;
  status: string;
  predicate: string;
  metricId?: string;
  evidence?: {
    level: string;
    method: string;
  };
}

export interface RunBundle {
  observation?: {
    artifact: OrderedPointSequence;
    artifactHash: string;
    source: string;
  };
  report: {
    metricResults: MetricResult[];
    score?: {
      status: string;
      value?: number;
    };
    provenance?: Record<string, string>;
  };
  run: {
    runId: string;
    runnerId: string;
    caseOutcome: string;
    executionStatus: string;
    contentHash: string;
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
