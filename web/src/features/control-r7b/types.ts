export type R7BCheckStatus = "Passed" | "Open" | "Blocked";

export interface R7BManifest {
  manifestId: "control.r7b-manifest@1";
  domainPackId: "control.domain-pack@2";
  evaluatorVersion: string;
  runnerId: string;
  supportedPlatforms: ["Windows"];
  defaultScenarioId: string;
  scenarioIds: string[];
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  contractReadinessStatus: "Passed";
  vendorAdapterStatus: "Open";
  deploymentShadowStatus: "Open";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
}

export interface R7BScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedOutcome: "Inconclusive";
  expectedReadinessOutcome: "Open" | "Blocked";
  countsTowardReality: false;
}

export interface R7BReadinessCheck {
  checkId: string;
  title: string;
  status: R7BCheckStatus;
  reasonCode?: string | null;
  details: Record<string, unknown>;
}

export interface R7BReadinessAudit {
  auditId: string;
  contentHash: string;
  checks: R7BReadinessCheck[];
  readinessOutcome: "Open" | "Blocked";
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  contractReadinessStatus: "Passed";
  vendorAdapterStatus: "Open";
  deploymentShadowStatus: "Open";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
  standardsComplianceStatus: "NotAssessed";
  realityEvidenceLevel: "None";
}

export interface R7BEvidenceSet {
  schemaId: "axiom.control.deployment-shadow-evidence-set@1";
  evidenceSetId: string;
  contentHash: string;
  controllerProfile: {
    vendor: string;
    controllerFamily: string;
    controllerModel: string;
    softwareVersion: string;
    machineId: string;
    interfaceType: string;
    targetStatus: "Unselected" | "Selected";
  };
  authority: {
    principalId: string;
    enforcementPoint: "controller";
    grantedOperations: Array<"read" | "subscribe">;
    deniedOperations: string[];
    verificationStatus: "Verified" | "Unverified";
  };
  capture: {
    sourceKind: "contract-fixture" | "controller-live-read" | "controller-export";
    declaredReal: boolean;
    frames: Array<{ sequence: number; samples: Array<{ channelId: string }> }>;
  };
  adapterReceipt: {
    adapterId: string;
    platform: "Windows";
    protocol: string;
    accessMode: "read-subscribe-only";
    status: "Succeeded" | "Failed" | "Unsupported";
    readOperationCount: number;
    writeOperationCount: 0;
    receivedSampleCount: number;
    droppedSampleCount: number;
  };
  clockSignalBinding: {
    clockMethod: string;
    coverageFraction: number;
    maximumObservedGapMs: number;
    requiredMaximumGapMs: number;
    signalMappings: Array<{ sourceChannelId: string; canonicalSignalId: string }>;
  };
  provenance: {
    dataOwnerId: string;
    capturedOutsideRepository: boolean;
    evaluationAuthorized: boolean;
  };
}

export interface R7BExamplePayload {
  manifest: R7BManifest;
  scenario: R7BScenarioSummary;
  readinessAudit: R7BReadinessAudit;
  evidenceSet: R7BEvidenceSet | null;
  runSpec: unknown;
}
