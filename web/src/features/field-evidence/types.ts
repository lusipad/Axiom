export type GateStatus = "Passed" | "Open" | "Refuted" | "Blocked";

export interface BeckhoffWitnessDeploymentRequest {
  schemaId: "axiom.control.beckhoff-shadow-witness-deployment-request@1";
  schemaVersion: 1;
  assessmentId: string;
  caseId: string;
  profileId: string;
  maximumTimestampUncertaintyMs: number;
  vendorProfile?: Record<string, unknown> | null;
  runtimeEvidence?: Record<string, unknown> | null;
  command?: Record<string, unknown> | null;
  nodes?: Array<{
    canonicalSignalId: string;
    namespaceUri: string;
    identifier: string;
  }>;
}

export interface BeckhoffWitnessDeploymentReport {
  schemaId: "axiom.control.beckhoff-shadow-witness-deployment-report@1";
  schemaVersion: 1;
  assessmentId: string;
  caseId: string;
  requestContentHash: string;
  template: {
    templateId: string;
    fileName: "FB_AxiomShadowWitness.TcPOU";
    sourceSha256: string;
    symbolCount: 7;
    snapshotPolicy: "sample-index-published-last";
    templateValidationStatus: "ContractChecked";
    twinCatCompileStatus: "NotAssessed";
    contentHash: string;
  };
  checks: ReadinessCheck[];
  profileBindingStatus: "Open" | "Bound" | "Blocked";
  runtimePreconditionStatus: "Open" | "Passed" | "Blocked";
  capturePreparationStatus: "Open" | "Passed" | "Blocked";
  witnessProfile?: Record<string, unknown> | null;
  assessmentRequest?: R7EAssessmentRequest | null;
  captureAuthorizationStatus: "Open";
  deploymentShadowStatus: "Open";
  realityValidationStatus: "Open";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
  contentHash: string;
}

export interface R7EManifest {
  manifestId: "control.r7e-manifest@1";
  domainPackId: "control.domain-pack@5";
  runnerId: string;
  targetVendor: "Beckhoff Automation";
  targetControllerFamily: "TwinCAT 3";
  minimumTwinCatBuild: 4026;
  targetInterface: "TF6100 OPC UA Server";
  supportedPlatforms: ["Windows"];
  capturePolicy: "sample-index-triggered-batch-read";
  intervalPolicy: "exact-sample-index-no-interpolation";
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  methodCallAllowed: false;
  deploymentShadowStatus: "Open";
  realityValidationStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
}

export interface ReadinessCheck {
  checkId: string;
  title: string;
  status: "Passed" | "Open" | "Blocked";
  reasonCode?: string | null;
}

export interface R7EExamplePayload {
  manifest: R7EManifest;
  scenario: { scenarioId: string; title: string; description: string };
  vendorProfile: Record<string, unknown>;
  runtimeEvidence: Record<string, unknown> | null;
  witnessProfile: {
    profileId: string;
    bindingStatus: "Open" | "Bound";
    contentHash: string;
    nodes: Array<{ canonicalSignalId: string; axisId?: string | null; unit: string }>;
  };
  controllerProfile: Record<string, unknown> | null;
  authority: Record<string, unknown> | null;
  captureAuthorization: Record<string, unknown> | null;
  command: Record<string, unknown> | null;
  shadowEvidence: {
    evidenceId: string;
    sourceKind: "controller-live-read" | "contract-fixture";
    declaredReal: boolean;
    contentHash: string;
    frames: Array<{ sequence: number; notifiedSampleIndex: number; readSampleIndex: number }>;
    receipt: {
      readOperationCount: number;
      writeOperationCount: 0;
      methodCallOperationCount: 0;
      acceptedFrameCount: number;
      droppedSampleIndexCount: number;
    };
  } | null;
  readinessAudit: {
    auditId: string;
    contentHash: string;
    checks: ReadinessCheck[];
    readinessOutcome: "Open" | "Passed" | "Blocked";
    deploymentShadowStatus: "Open" | "Passed" | "Blocked";
    realityValidationStatus: "Open";
    countsTowardDeploymentShadow: boolean;
    countsTowardReality: false;
    deviceSafetyStatus: "NotAssessed";
    processSafetyStatus: "NotAssessed";
  };
  runSpec?: Record<string, unknown>;
}

export interface R41Manifest {
  manifestId: "physical.r4.1-manifest@1";
  stage: "R4.1";
  domainPackId: "five-axis.domain-pack@7";
  runnerId: string;
  supportedPlatforms: ["Windows"];
  requiredIndependentRuns: 2;
  calibrationRole: "calibration";
  validationRole: "validation";
  interpolationAllowed: false;
  realityValidationStatus: "Open";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
}

export interface R41Check {
  checkId: string;
  title: string;
  status: GateStatus;
  reasonCode?: string | null;
}

export interface R41ExamplePayload {
  manifest: R41Manifest;
  scenario: { scenarioId: string; title: string; description: string };
  calibrationPair: { pairId: string; pairContentHash: string } | null;
  validationPair: { pairId: string; pairContentHash: string } | null;
  analysis: {
    analysisId: string;
    contentHash: string;
    checks: R41Check[];
    axes: Array<{ axisId: string; unitFamily: string; unit: string }>;
    linearImprovementRatio?: number | null;
    rotaryImprovementRatio?: number | null;
    alignmentCoverage: number;
    fitStatus: GateStatus;
    realityValidationStatus: GateStatus;
    countsTowardReality: boolean;
    controlledTrialStatus: "Open";
    closedLoopStatus: "Open";
    deviceSafetyStatus: "NotAssessed";
    processSafetyStatus: "NotAssessed";
  };
}

export interface R7EAssessmentRequest {
  caseId?: string | null;
  vendorProfile?: Record<string, unknown> | null;
  runtimeEvidence?: Record<string, unknown> | null;
  witnessProfile?: Record<string, unknown> | null;
  controllerProfile?: Record<string, unknown> | null;
  authority?: Record<string, unknown> | null;
  captureAuthorization?: Record<string, unknown> | null;
  command?: Record<string, unknown> | null;
  shadowEvidence?: Record<string, unknown> | null;
}

export interface R41AssessmentRequest {
  calibrationPair?: Record<string, unknown> | null;
  validationPair?: Record<string, unknown> | null;
  fitImprovementMinimum?: number;
  excitationSpanMinimum?: number;
  decompositionTolerance?: number;
}

export interface FieldEvidenceAssessmentRequest {
  schemaId: "axiom.field-evidence-assessment-request@1";
  schemaVersion: 1;
  assessmentId: string;
  calibrationPairId: string;
  validationPairId: string;
  calibration: R7EAssessmentRequest;
  validation: R7EAssessmentRequest;
  fitImprovementMinimum?: number;
  excitationSpanMinimum?: number;
  decompositionTolerance?: number;
}

export interface FieldEvidenceAssessmentReport {
  schemaId: "axiom.field-evidence-assessment-report@1";
  schemaVersion: 1;
  assessmentId: string;
  caseId: string;
  calibrationPairId: string;
  validationPairId: string;
  calibrationAssessment: R7EExamplePayload;
  validationAssessment: R7EExamplePayload;
  calibrationPair: R41ExamplePayload["calibrationPair"];
  validationPair: R41ExamplePayload["validationPair"];
  realityAssessment: R41ExamplePayload;
  overallStatus: GateStatus;
  countsTowardReality: boolean;
  validationScope: "single-device-case-scoped";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
  contentHash: string;
}
