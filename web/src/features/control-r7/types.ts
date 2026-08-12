export type RuntimeState = "Prepared" | "Admitted" | "Blocked" | "Monitoring" | "StopRequested" | "Stopped" | "RollbackVerified" | "Completed";

export interface R7Manifest {
  manifestId: "control.r7-manifest@1";
  domainPackId: "control.domain-pack@1";
  evaluatorVersion: string;
  runnerId: string;
  supportedPlatforms: ["Windows"];
  permissionCeiling: "Shadow";
  deviceWriteAllowed: false;
  scenarioIds: string[];
  syntheticShadowContractStatus: "Passed";
  deploymentShadowStatus: "Open";
  controlledTrialStatus: "Open";
  closedLoopStatus: "Open";
}

export interface R7ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedOutcome: "Passed";
  expectedFinalState: RuntimeState;
}

export interface R7ExamplePayload {
  manifest: R7Manifest;
  scenario: R7ScenarioSummary;
  recommendationSet: {
    contentHash: string;
    permissionLevel: "Offline";
    realityValidationStatus: "Open";
  };
  runtimeSpec: {
    runtimeSpecId: string;
    requestedPermission: string;
    deviceWriteRequested: boolean;
    candidateId: string;
    recommendationSetContentHash: string;
    envelope: {
      maximumLinearFollowingErrorMm: number;
      maximumOodFraction: number;
      maximumMonitorGapSeconds: number;
      rollbackParameterSetId: string;
      deviceWriteAllowed: false;
      contentHash: string;
    };
    trace: {
      sourceKind: "synthetic-shadow";
      samples: Array<{
        sequence: number;
        timeSeconds: number;
        linearFollowingErrorMm: number;
        oodFraction: number;
      }>;
    };
  };
  runtimeAudit: {
    auditId: string;
    contentHash: string;
    finalState: RuntimeState;
    permissionCeiling: "Shadow";
    deviceWriteAllowed: false;
    deviceWritePerformed: false;
    syntheticShadowContractStatus: "Passed";
    deploymentShadowStatus: "Open";
    controlledTrialStatus: "Open";
    closedLoopStatus: "Open";
    standardsComplianceStatus: "NotAssessed";
    admissionDecision: {
      status: "Admitted" | "Blocked";
      requestedPermission: string;
      grantedPermission: string;
      reasonCodes: string[];
    };
    acceptanceRecord: {
      recordId: string;
      disposition: "Shadow" | "Blocked";
      grantedPermission: string;
      contentHash: string;
      automatic: false;
      responsibility: {
        accountablePartyId: string;
        decisionPolicyId: string;
        approvalMode: "policy-replay";
        humanApprovalPresent: false;
        realDeviceAuthorityPresent: false;
      };
    };
    transitions: Array<{
      sequence: number;
      fromState?: RuntimeState;
      toState: RuntimeState;
      reasonCode: string;
    }>;
    monitorFindings: Array<{
      sampleSequence: number;
      status: "WithinEnvelope" | "Breach";
      reasonCodes: string[];
    }>;
    stopReceipt: {
      requested: boolean;
      reasonCodes: string[];
      effect: "NotRequired" | "PromotionSuppressed";
      deviceStopCommandIssued: false;
      deviceAcknowledged: false;
    };
    rollbackReceipt: {
      status: "NotRequired" | "BaselineRetained";
      baselineParameterSetId: string;
      deviceWriteIssued: false;
      deviceReadbackVerified: false;
    };
  };
  runSpec: unknown;
}

