import type { RunBundle, RunSpec } from "../../types";

export interface MachineR3Manifest {
  manifestId: string;
  schemaId: string;
  schemaVersion: number;
  stage: "R3";
  readOnly: true;
  safetyBanner: string;
  suiteId: string;
  artifactDescriptors: Array<{
    artifactType: string;
    schemaVersion: number;
    role: string;
  }>;
  capabilityIds: string[];
  claimDefinitionIds: string[];
  forbiddenClaims: string[];
  cases: Array<{
    id: string;
    title: string;
    description: string;
    expectedExecutionStatus: string;
    expectedCaseOutcome: string;
  }>;
}

export interface MachineR3ScenarioSummary {
  scenarioId: string;
  title: string;
  description: string;
  expectedExecutionStatus?: string;
  expectedCaseOutcome?: string;
}

export interface MachineR3DeviceProfile {
  profileId: string;
  deviceId: string;
  controllerFamily: string;
  manufacturer: string;
  machineModel: string;
  exportVersion: string;
  allowedReadOnlyOperations: ["file-import"];
  firmwareVersion?: string | null;
  calibrationId?: string | null;
}

export interface MachineR3Alignment {
  deviceId: string;
}

export interface MachineR3ClockMapping extends MachineR3Alignment {
  mappingId: string;
  mappingMethod: "fixed-offset" | "synchronized-export" | "vendor-declared";
  deviceReferenceTimestamp: string;
  hostReferenceTimestamp: string;
  offsetMilliseconds: number;
  driftBoundMilliseconds?: number;
}

export interface MachineR3CoordinateAlignment extends MachineR3Alignment {
  alignmentId: string;
  sourceKind: "calibration-record" | "vendor-declared" | "synthetic-reference";
  effectiveAt: string;
  machineCoordinateFrame: string;
  workCoordinateFrame: string;
  calibrationStatus: "calibrated" | "estimated";
  calibrationId?: string | null;
  channelIds: string[];
}

export interface MachineR3Lineage {
  machineRunId: string;
  pairingStatus: "paired" | "unpaired";
  baselineKind?: "reference" | "benchmark" | null;
  baselineRunBundleHash?: string | null;
  sourceCommandContentHash?: string | null;
  upstreamClaims?: Array<{
    claimDefinitionId: string;
    status: string;
    reportContentHash?: string;
  }>;
}

export interface MachineR3TraceArtifact {
  artifactType: "machine.telemetry-trace";
  schemaVersion: 1;
  traceId: string;
  sourceKind: "synthetic-replay" | "controller-export" | "device-read";
  captureReceipt: {
    receiptId: string;
    sourceId: "axiom.windows-file-telemetry-source@1";
    operation: "file-import" | "parameter-write";
    transport: "windows-file-json";
    capturedAt: string;
    traceContentHash: string;
  };
  deviceIdentity: {
    deviceId: string;
    controllerFamily: string;
    machineModel: string;
  };
  frames: Array<{
    sequenceId: number;
    deviceTimestamp: string;
    samples: Array<{
      channelId: string;
      value: number | string | number[];
      unit?: string | null;
      quality?: "good" | "suspect" | "bad" | null;
    }>;
    alarms?: string[];
  }>;
  vendorMetadata: Record<string, unknown>;
}

export interface MachineR3DeviceChannel {
  channelId: string;
  kind: "position-vector" | "scalar" | "state" | "alarm";
  unit?: string;
  coordinateFrame?: string | null;
}

export interface MachineR3ExamplePayload {
  manifest: MachineR3Manifest;
  scenario: MachineR3ScenarioSummary;
  artifact: MachineR3TraceArtifact;
  deviceProfile: MachineR3DeviceProfile & {
    channels: MachineR3DeviceChannel[];
  };
  clockMapping?: MachineR3ClockMapping;
  coordinateAlignment?: MachineR3CoordinateAlignment;
  lineage: MachineR3Lineage;
  runSpec?: RunSpec;
}

export type MachineR3RunBundle = RunBundle;
