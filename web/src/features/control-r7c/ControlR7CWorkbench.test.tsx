import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ControlR7CWorkbench } from "./ControlR7CWorkbench";
import type {
  OpcUaTransportEvidence,
  R7CExamplePayload,
  R7CManifest,
  R7CScenarioSummary,
} from "./types";

const manifest: R7CManifest = {
  manifestId: "control.r7c-manifest@1",
  domainPackId: "control.domain-pack@3",
  evaluatorVersion: "control-opcua-transport-readiness-evaluator@1",
  runnerId: "control-opcua-transport-import@1",
  adapterId: "axiom.control.opcua-shadow-read-adapter@1",
  adapterVersion: "0.1.0",
  protocolStack: "OPCFoundation.NetStandard.Opc.Ua.Client@1.5.378.156",
  supportedPlatforms: ["Windows"],
  defaultScenarioId: "opcua-transport-evidence-open",
  scenarioIds: ["opcua-transport-evidence-open"],
  permissionCeiling: "Shadow",
  deviceWriteAllowed: false,
  adapterContractStatus: "Passed",
  networkConformanceStatus: "Passed",
  vendorAdapterStatus: "Open",
  realityValidationStatus: "Open",
};

const scenarios: R7CScenarioSummary[] = [{
  scenarioId: "opcua-transport-evidence-open",
  title: "Windows OPC UA transport evidence (open)",
  description: "No capture evidence has been imported.",
  expectedOutcome: "Inconclusive",
  expectedReadinessOutcome: "Open",
  countsTowardReality: false,
}];

const evidence: OpcUaTransportEvidence = {
  schemaId: "axiom.control.opcua-transport-evidence@1",
  evidenceId: "transport@1",
  contentHash: "a".repeat(64),
  adapterId: manifest.adapterId,
  adapterVersion: manifest.adapterVersion,
  platform: "Windows",
  protocol: "opc-ua",
  accessMode: "read-subscribe-only",
  declaredReal: false,
  countsTowardReality: false,
  endpoint: {
    endpointUrl: "opc.tcp://localhost:4840/axiom-opcua-shadow",
    serverApplicationUri: "urn:localhost:axiom:server",
    serverCertificateSha256: "b".repeat(64),
    clientApplicationUri: "urn:localhost:axiom:client",
    clientCertificateSha256: "c".repeat(64),
    securityPolicyUri: "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256",
    messageSecurityMode: "SignAndEncrypt",
    identityType: "username",
    principalId: "shadow-reader",
    anonymous: false,
  },
  subscription: {
    requestedPublishingIntervalMs: 50,
    revisedPublishingIntervalMs: 50,
    requestedSamplingIntervalMs: 20,
    queueSize: 32,
    monitoredItemCount: 5,
  },
  channels: ["X", "Y", "Z", "B", "C"].map((axis) => ({
    channelId: `axis.${axis}.position`,
    canonicalSignalId: `machine.axis.${axis}.position`,
    axisId: axis as "X" | "Y" | "Z" | "B" | "C",
    unit: (["X", "Y", "Z"].includes(axis) ? "mm" : "rad") as "mm" | "rad",
  })),
  frames: [
    { sequence: 0, protocolSequenceNumber: 1 },
    { sequence: 1, protocolSequenceNumber: 2 },
  ],
  receipt: {
    status: "Succeeded",
    readOperationCount: 0,
    subscribeOperationCount: 1,
    writeOperationCount: 0,
    methodCallOperationCount: 0,
    receivedFrameCount: 2,
    receivedSampleCount: 10,
    droppedNotificationCount: 0,
    transcriptContentHash: "d".repeat(64),
  },
  virtualTransportStatus: "Passed",
  vendorAdapterStatus: "Open",
  realityValidationStatus: "Open",
  deviceSafetyStatus: "NotAssessed",
  processSafetyStatus: "NotAssessed",
};

function payload(transportEvidence: OpcUaTransportEvidence | null): R7CExamplePayload {
  const transportStatus = transportEvidence ? "Passed" : "Open";
  return {
    manifest,
    scenario: scenarios[0]!,
    readinessAudit: {
      auditId: "control.r7c.opcua-transport-readiness-audit@1",
      contentHash: "e".repeat(64),
      readinessOutcome: "Open",
      permissionCeiling: "Shadow",
      deviceWriteAllowed: false,
      adapterContractStatus: "Passed",
      virtualTransportStatus: transportStatus,
      vendorAdapterStatus: "Open",
      deploymentShadowStatus: "Open",
      controlledTrialStatus: "Open",
      closedLoopStatus: "Open",
      standardsComplianceStatus: "NotAssessed",
      realityEvidenceLevel: "None",
      checks: [
        { checkId: "r7c.contract", title: "R7-C typed adapter contract", status: "Passed", details: {} },
        { checkId: "r7c.transport-evidence", title: "Virtual OPC UA transport evidence", status: transportStatus, reasonCode: transportEvidence ? undefined : "OpcUaTransportEvidenceMissing", details: {} },
        { checkId: "r7c.secure-channel", title: "Pinned encrypted channel", status: transportStatus, details: {} },
        { checkId: "r7c.subscription-integrity", title: "Five-axis subscription integrity", status: transportStatus, details: {} },
        { checkId: "r7c.zero-write", title: "Zero write and method-call operations", status: transportStatus, details: {} },
        { checkId: "r7c.vendor-adapter", title: "Versioned vendor adapter", status: "Open", reasonCode: "VendorAdapterUnselected", details: {} },
        { checkId: "r7c.reality-gate", title: "Real deployment validation", status: "Open", reasonCode: "RealDeploymentValidationOpen", details: {} },
      ],
    },
    transportEvidence,
    runSpec: {},
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => vi.restoreAllMocks());

describe("ControlR7CWorkbench", () => {
  it("显示虚拟传输、零写与现实门开放边界", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest")
        ? manifest
        : url.endsWith("/scenarios")
          ? scenarios
          : payload(null);
      return Promise.resolve(jsonResponse(data));
    });
    render(<ControlR7CWorkbench catalog={{ subjects: [], artifactAdapters: [], domainPacks: [{ domainPackId: "control.domain-pack@3", comparisonPolicyIds: [], runnerIds: [manifest.runnerId], runtimeBound: true }] }} />);

    expect(await screen.findByText("先证明安全地读到，再选择真实控制器")).toBeInTheDocument();
    expect(screen.getByText("VIRTUAL OPC UA ONLY · NO DEVICE WRITE")).toBeInTheDocument();
    expect(screen.getByText(/VIRTUAL ONLY · ZERO WRITE · REALITY OPEN/)).toBeInTheDocument();
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /启动|复位|写入|下发|急停|连接机床/i })).not.toBeInTheDocument();
  });

  it("导入 .NET 证据只关闭虚拟传输检查", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.endsWith("/assess") && init?.method === "POST") return Promise.resolve(jsonResponse(payload(evidence)));
      return Promise.resolve(jsonResponse(payload(null)));
    });
    render(<ControlR7CWorkbench catalog={null} />);
    await screen.findByText("七项门禁");

    const file = new File([JSON.stringify(evidence)], "transport-evidence.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("导入 OPC UA 传输证据 JSON"), { target: { files: [file] } });

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/control/r7c/assess") && init?.method === "POST")).toBe(true));
    expect(await screen.findByText("Basic256Sha256")).toBeInTheDocument();
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);
    expect(screen.getByText("NotAssessed")).toBeInTheDocument();
  });

  it("损坏文件停在浏览器侧", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? scenarios : payload(null);
      return Promise.resolve(jsonResponse(data));
    });
    render(<ControlR7CWorkbench catalog={null} />);
    await screen.findByText("七项门禁");

    fireEvent.change(screen.getByLabelText("导入 OPC UA 传输证据 JSON"), {
      target: { files: [new File(["{bad"], "broken.json", { type: "application/json" })] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("证据导入失败");
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/control/r7c/assess"))).toBe(false);
  });
});
