export type R7DCheckStatus = "Passed" | "Open" | "Blocked";

export interface R7DManifest {
  manifestId: "control.r7d-manifest@1";
  domainPackId: "control.domain-pack@4";
  evaluatorVersion: string;
  runnerId: string;
  vendorProfileId: string;
  verifierId: string;
  verifierVersion: string;
  targetVendor: "Beckhoff Automation";
  targetControllerFamily: "TwinCAT 3";
  minimumTwinCatBuild: 4026;
  targetInterface: "TF6100 OPC UA Server";
  supportedPlatforms: ["Windows"];
  defaultScenarioId: string;
  scenarioIds: string[];
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  vendorProfileStatus: "Passed";
  vendorRuntimeStatus: "Open";
  deploymentShadowStatus: "Open";
  realityValidationStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
}

export interface R7DScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedOutcome: "Inconclusive";
  expectedReadinessOutcome: "Open";
  countsTowardReality: false;
}

export interface BeckhoffNodeBinding {
  namespaceUri: string;
  identifier: string;
  expectedDataType: "Double";
  requiredAccessLevel: 1;
  requiredUserAccessLevel: 1;
}

export interface BeckhoffTwinCatProfile {
  schemaId: "axiom.control.beckhoff-twincat-profile@1";
  profileId: string;
  contentHash: string;
  vendorName: "Beckhoff Automation";
  controllerFamily: "TwinCAT 3";
  minimumTwinCatBuild: 4026;
  opcUaServerProduct: "TF6100 OPC UA Server";
  requiredLicenseId: "TF6100";
  requiredPackages: string[];
  defaultEndpointUrl: string;
  messageSecurityMode: "SignAndEncrypt";
  accessMode: "read-subscribe-only";
  bindingStatus: "Open" | "Bound";
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  serverIdentity?: {
    endpointUrl: string;
    productName: string;
    softwareVersion: string;
    buildNumber: string;
  } | null;
  channels: Array<{
    axisId: "X" | "Y" | "Z" | "B" | "C";
    canonicalSignalId: string;
    unit: "mm" | "rad";
    nodeBinding?: BeckhoffNodeBinding | null;
  }>;
}

export interface BeckhoffRuntimeEvidence {
  schemaId: "axiom.control.beckhoff-runtime-evidence@1";
  evidenceId: string;
  contentHash: string;
  profileContentHash: string;
  verifierId: string;
  verifierVersion: string;
  platform: "Windows";
  sourceKind: "vendor-runtime" | "contract-fixture";
  capturedAt: string;
  installation: {
    status: R7DCheckStatus;
    reasonCode?: string | null;
    tcpkgAvailable: boolean;
    twinCatBuild?: number | null;
    packages: Array<{ packageId: string; version: string; installed: true }>;
    serverBinary?: { productName: string; companyName: string; fileVersion: string } | null;
  };
  license: {
    licenseId: "TF6100";
    state: "Full" | "Trial" | "Missing" | "Unknown";
    resultCode?: number | null;
  };
  serverIdentity?: {
    productName: string;
    manufacturerName: string;
    softwareVersion: string;
    buildNumber: string;
    buildDate: string;
  } | null;
  channelAccess?: Array<{
    axisId: "X" | "Y" | "Z" | "B" | "C";
    identifier: string;
    dataType: "Double";
    accessLevel: number;
    userAccessLevel: number;
  }> | null;
  writeRejection: {
    status: "NotRun" | "Rejected" | "Accepted";
    operationCount: 0 | 1;
    statusCode?: string | null;
    serverValueUnchanged?: boolean | null;
  };
  countsTowardReality: false;
  realityValidationStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
}

export interface R7DReadinessCheck {
  checkId: string;
  title: string;
  status: R7DCheckStatus;
  reasonCode?: string | null;
  details: Record<string, unknown>;
}

export interface R7DReadinessAudit {
  auditId: string;
  contentHash: string;
  checks: R7DReadinessCheck[];
  readinessOutcome: "Open" | "Blocked";
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  vendorProfileStatus: "Passed";
  vendorRuntimeStatus: R7DCheckStatus;
  deploymentShadowStatus: "Open";
  realityValidationStatus: "Open";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
  deviceSafetyStatus: "NotAssessed";
  processSafetyStatus: "NotAssessed";
}

export interface R7DExamplePayload {
  manifest: R7DManifest;
  scenario: R7DScenarioSummary;
  profile: BeckhoffTwinCatProfile;
  readinessAudit: R7DReadinessAudit;
  runtimeEvidence: BeckhoffRuntimeEvidence | null;
  transportEvidence: unknown | null;
  runSpec: unknown;
}

export interface R7DAssessmentRequest {
  profile: BeckhoffTwinCatProfile;
  runtimeEvidence: BeckhoffRuntimeEvidence | null;
  transportEvidence: unknown | null;
}
