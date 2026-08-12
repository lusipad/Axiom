export type R7CCheckStatus = "Passed" | "Open" | "Blocked";

export interface R7CManifest {
  manifestId: "control.r7c-manifest@1";
  domainPackId: "control.domain-pack@3";
  evaluatorVersion: string;
  runnerId: string;
  adapterId: string;
  adapterVersion: string;
  protocolStack: string;
  supportedPlatforms: ["Windows"];
  defaultScenarioId: string;
  scenarioIds: string[];
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  adapterContractStatus: "Passed";
  networkConformanceStatus: "Passed";
  vendorAdapterStatus: "Open";
  realityValidationStatus: "Open";
}

export interface R7CScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedOutcome: "Inconclusive";
  expectedReadinessOutcome: "Open";
  countsTowardReality: false;
}

export interface R7CReadinessCheck {
  checkId: string;
  title: string;
  status: R7CCheckStatus;
  reasonCode?: string | null;
  details: Record<string, unknown>;
}

export interface R7CReadinessAudit {
  auditId: string;
  contentHash: string;
  checks: R7CReadinessCheck[];
  readinessOutcome: "Open" | "Blocked";
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  adapterContractStatus: "Passed";
  virtualTransportStatus: "Open" | "Passed";
  vendorAdapterStatus: "Open";
  deploymentShadowStatus: "Open";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
  standardsComplianceStatus: "NotAssessed";
  realityEvidenceLevel: "None";
}

export interface OpcUaTransportEvidence {
  schemaId: "axiom.control.opcua-transport-evidence@1";
  evidenceId: string;
  contentHash: string;
  adapterId: string;
  adapterVersion: string;
  platform: "Windows";
  protocol: "opc-ua";
  accessMode: "read-subscribe-only";
  declaredReal: false;
  countsTowardReality: false;
  endpoint: {
    endpointUrl: string;
    serverApplicationUri: string;
    serverCertificateSha256: string;
    clientApplicationUri: string;
    clientCertificateSha256: string;
    securityPolicyUri: string;
    messageSecurityMode: "SignAndEncrypt";
    identityType: "username";
    principalId: string;
    anonymous: false;
  };
  subscription: {
    requestedPublishingIntervalMs: number;
    revisedPublishingIntervalMs: number;
    requestedSamplingIntervalMs: number;
    queueSize: number;
    monitoredItemCount: 5;
  };
  channels: Array<{
    channelId: string;
    canonicalSignalId: string;
    axisId: "X" | "Y" | "Z" | "B" | "C";
    unit: "mm" | "rad";
  }>;
  frames: Array<{ sequence: number; protocolSequenceNumber: number }>;
  receipt: {
    status: "Succeeded";
    readOperationCount: 0;
    subscribeOperationCount: 1;
    writeOperationCount: 0;
    methodCallOperationCount: 0;
    receivedFrameCount: number;
    receivedSampleCount: number;
    droppedNotificationCount: number;
    transcriptContentHash: string;
  };
  virtualTransportStatus: "Passed";
  vendorAdapterStatus: "Open";
  realityValidationStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
}

export interface R7CExamplePayload {
  manifest: R7CManifest;
  scenario: R7CScenarioSummary;
  readinessAudit: R7CReadinessAudit;
  transportEvidence: OpcUaTransportEvidence | null;
  runSpec: unknown;
}
