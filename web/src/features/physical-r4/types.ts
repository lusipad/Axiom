export interface PhysicalR4ModelContract {
  equations: string[];
  stateIds: string[];
  inputIds: string[];
  outputIds: string[];
  discretization: "exact-zoh";
  supportedDevices: string[];
  operatingConditions: string[];
  unmodeledFactors: string[];
}

export interface PhysicalR4Manifest {
  manifestId: string;
  schemaId: string;
  schemaVersion: number;
  stage: "R4";
  domainPackId?: string;
  platform: "windows";
  safetyBanner: "MODEL VALIDATION / NOT DEVICE SAFE";
  validationBanner: "SYNTHETIC SIL / REALITY VALIDATION OPEN";
  model: PhysicalR4ModelContract;
}

export interface PhysicalR4ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  axisIds: string[];
}

export interface PhysicalR4DatasetIdentity {
  datasetId: string;
  traceId: string;
  scenarioRole: "calibration" | "validation";
  sourceId: string;
  capturedAt: string;
  contentHash: string;
}

export interface PhysicalR4LeakageGuard {
  checkId: string;
  status: "pass" | "blocked";
  message: string;
}

export interface PhysicalR4SignalSample {
  time: number;
  value: number;
}

export type PhysicalR4MetricGroup = "linear-mm" | "rotary-rad";

export type PhysicalR4MetricStatus =
  | "Computed"
  | "NotApplicable"
  | "InsufficientContext"
  | "UnsupportedCapability"
  | "InvalidObservation"
  | "NumericalFailure";

export interface PhysicalR4AxisMetric {
  metricId: string;
  label: string;
  group: PhysicalR4MetricGroup;
  value: number | string | boolean;
  unit?: string;
  axisId?: string;
  status?: string;
}

export interface PhysicalR4MetricResult {
  metricId: string;
  metricDefinitionId: string;
  label: string;
  group: PhysicalR4MetricGroup;
  status: PhysicalR4MetricStatus;
  value: number | string | boolean | null;
  unit?: string | null;
  thresholdPassed?: boolean | null;
  reasonCode?: string | null;
}

export interface PhysicalR4ResidualComponent {
  componentId: string;
  label: string;
  value: number;
  unit: string;
  source: "command-simulation" | "simulation-observation" | "command-observation";
}

export interface PhysicalR4Axis {
  axisId: string;
  family: PhysicalR4MetricGroup;
  unit: "mm" | "rad";
  excitationStatus: "excited" | "partial" | "insufficient";
  series: {
    command: PhysicalR4SignalSample[];
    simulation: PhysicalR4SignalSample[];
    observation: PhysicalR4SignalSample[];
  };
  metrics: PhysicalR4AxisMetric[];
  residualDecomposition: PhysicalR4ResidualComponent[];
}

export type PhysicalR4ClaimStatus = "Supported" | "Refuted" | "Inconclusive";

export interface PhysicalR4Claim {
  claimId: string;
  claimDefinitionId: string;
  metricId?: string | null;
  title: string;
  status: PhysicalR4ClaimStatus;
  statement: string;
  evidenceIds: string[];
  reasonCode?: string | null;
  reportContentHash?: string | null;
  evidenceLevel?: "Exact" | "Certified" | "Validated" | "Observed" | null;
}

export interface PhysicalR4EvidenceItem {
  evidenceId: string;
  kind: "receipt" | "fit" | "residual" | "validation" | "lineage";
  title: string;
  summary: string;
  contentHash?: string | null;
}

export interface PhysicalR4RunSummary {
  caseOutcome: "Passed" | "Failed" | "Inconclusive" | "Unsupported" | "Invalid";
  executionStatus:
    | "Pending"
    | "Running"
    | "Succeeded"
    | "ExecutionFailed"
    | "Cancelled"
    | "Skipped";
  reportContentHash: string;
  bundleHash: string;
}

export interface PhysicalR4Analysis {
  traceArtifactType: "five-axis.physical-response-trace";
  analysisContentHash?: string;
  curveMode: "canonical-analysis" | "diagnostic-preview";
  curveNotice?: string | null;
  run?: PhysicalR4RunSummary;
  axes: PhysicalR4Axis[];
  metricResults: PhysicalR4MetricResult[];
  claims: PhysicalR4Claim[];
  evidence: PhysicalR4EvidenceItem[];
}

export interface PhysicalR4ExamplePayload {
  manifest: PhysicalR4Manifest;
  scenario: PhysicalR4ScenarioSummary;
  model: PhysicalR4ModelContract;
  calibration: PhysicalR4DatasetIdentity;
  validation: PhysicalR4DatasetIdentity & {
    leakageGuards: PhysicalR4LeakageGuard[];
  };
  analysis: PhysicalR4Analysis;
  runSpec?: unknown;
}
