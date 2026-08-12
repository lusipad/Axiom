import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ControlR7BWorkbench } from "./ControlR7BWorkbench";
import type {
  R7BEvidenceSet,
  R7BExamplePayload,
  R7BManifest,
  R7BScenarioSummary,
} from "./types";

const manifest: R7BManifest = {
  manifestId: "control.r7b-manifest@1",
  domainPackId: "control.domain-pack@2",
  evaluatorVersion: "control-deployment-shadow-readiness-evaluator@1",
  runnerId: "control-deployment-shadow-import@1",
  supportedPlatforms: ["Windows"],
  defaultScenarioId: "deployment-shadow-readiness-open",
  scenarioIds: ["deployment-shadow-readiness-open", "contract-fixture-blocked"],
  permissionCeiling: "Shadow",
  deviceWriteAllowed: false,
  contractReadinessStatus: "Passed",
  vendorAdapterStatus: "Open",
  deploymentShadowStatus: "Open",
  controlledTrialStatus: "Open",
  closedLoopStatus: "Open",
};

const scenarios: R7BScenarioSummary[] = [
  { scenarioId: "deployment-shadow-readiness-open", title: "Readiness open", description: "No external evidence", expectedOutcome: "Inconclusive", expectedReadinessOutcome: "Open", countsTowardReality: false },
  { scenarioId: "contract-fixture-blocked", title: "Contract fixture blocked", description: "Fixture is not real", expectedOutcome: "Inconclusive", expectedReadinessOutcome: "Blocked", countsTowardReality: false },
];

const evidenceSet: R7BEvidenceSet = {
  schemaId: "axiom.control.deployment-shadow-evidence-set@1",
  evidenceSetId: "contract@1",
  contentHash: "a".repeat(64),
  controllerProfile: { vendor: "ContractFixture", controllerFamily: "unselected", controllerModel: "unselected", softwareVersion: "unselected", machineId: "fixture", interfaceType: "controller-export", targetStatus: "Unselected" },
  authority: { principalId: "fixture", enforcementPoint: "controller", grantedOperations: ["read", "subscribe"], deniedOperations: ["parameter-write", "cycle-start"], verificationStatus: "Unverified" },
  capture: { sourceKind: "contract-fixture", declaredReal: false, frames: [{ sequence: 0, samples: [{ channelId: "axis.X.actual" }] }, { sequence: 1, samples: [{ channelId: "axis.X.actual" }] }] },
  adapterReceipt: { adapterId: "unselected@1", platform: "Windows", protocol: "controller-export", accessMode: "read-subscribe-only", status: "Succeeded", readOperationCount: 2, writeOperationCount: 0, receivedSampleCount: 2, droppedSampleCount: 0 },
  clockSignalBinding: { clockMethod: "contract-fixture", coverageFraction: 1, maximumObservedGapMs: 10, requiredMaximumGapMs: 20, signalMappings: [{ sourceChannelId: "axis.X.actual", canonicalSignalId: "machine.axis.X.position.actual" }] },
  provenance: { dataOwnerId: "fixture", capturedOutsideRepository: false, evaluationAuthorized: true },
};

function payload(readinessOutcome: "Open" | "Blocked", evidence: R7BEvidenceSet | null): R7BExamplePayload {
  return {
    manifest,
    scenario: scenarios[readinessOutcome === "Open" ? 0 : 1]!,
    readinessAudit: {
      auditId: "readiness@1",
      contentHash: "b".repeat(64),
      readinessOutcome,
      permissionCeiling: "Shadow",
      deviceWriteAllowed: false,
      contractReadinessStatus: "Passed",
      vendorAdapterStatus: "Open",
      deploymentShadowStatus: "Open",
      controlledTrialStatus: "Open",
      closedLoopStatus: "Open",
      standardsComplianceStatus: "NotAssessed",
      realityEvidenceLevel: "None",
      checks: [
        { checkId: "r7b.contract", title: "R7-B typed contract", status: "Passed", details: {} },
        { checkId: "r7b.external-evidence", title: "External real evidence", status: readinessOutcome === "Blocked" ? "Blocked" : "Open", reasonCode: readinessOutcome === "Blocked" ? "NonRealEvidenceSource" : "DeploymentShadowEvidenceMissing", details: {} },
        { checkId: "r7b.vendor-adapter", title: "Versioned vendor adapter", status: "Open", reasonCode: "VendorAdapterUnselected", details: {} },
        { checkId: "r7b.authority", title: "Controller-enforced read-only authority", status: "Open", reasonCode: "AuthorityEvidenceMissing", details: {} },
        { checkId: "r7b.capture-integrity", title: "Capture and receipt integrity", status: evidence ? "Passed" : "Open", details: {} },
        { checkId: "r7b.clock-signal-coverage", title: "Clock and signal coverage", status: "Open", reasonCode: "ClockSignalBindingMissing", details: {} },
        { checkId: "r7b.reality-gate", title: "Case-scoped deployment shadow reality gate", status: "Open", reasonCode: "RealDeploymentValidationOpen", details: {} },
      ],
    },
    evidenceSet: evidence,
    runSpec: {},
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.restoreAllMocks());

describe("ControlR7BWorkbench", () => {
  it("保持只读就绪性、厂商未选择和现实门开放边界", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? scenarios : payload("Open", null);
      return Promise.resolve(jsonResponse(data));
    });
    render(<ControlR7BWorkbench catalog={{ subjects: [], artifactAdapters: [], domainPacks: [{ domainPackId: "control.domain-pack@2", comparisonPolicyIds: [], runnerIds: [manifest.runnerId], runtimeBound: true }] }} />);

    expect(await screen.findByText("先证明“只能以最小权限只读采集”，再谈真实部署")).toBeInTheDocument();
    expect(screen.getByText("READINESS ONLY · NO DEVICE WRITE")).toBeInTheDocument();
    expect(screen.getByText("READINESS ONLY · NO DEVICE WRITE · REALITY OPEN", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /启动|复位|写入|下发|急停|连接机床/i })).not.toBeInTheDocument();
  });

  it("导入证据只调用就绪性评估并阻止合同夹具升级为现实证据", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.endsWith("/assess") && init?.method === "POST") return Promise.resolve(jsonResponse(payload("Blocked", evidenceSet)));
      return Promise.resolve(jsonResponse(payload("Open", null)));
    });
    render(<ControlR7BWorkbench catalog={null} />);
    await screen.findByText("七项就绪检查");

    const file = new File([JSON.stringify({ evidenceSet })], "deployment-evidence.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("导入外部证据 JSON"), { target: { files: [file] } });

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/control/r7b/assess") && init?.method === "POST")).toBe(true));
    expect(await screen.findByText("NonRealEvidenceSource")).toBeInTheDocument();
    expect(screen.getAllByText("Blocked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);
  });

  it("向用户展示损坏证据文件而不发送评估请求", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? scenarios : payload("Open", null);
      return Promise.resolve(jsonResponse(data));
    });
    render(<ControlR7BWorkbench catalog={null} />);
    await screen.findByText("七项就绪检查");

    const file = new File(["{bad"], "broken.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("导入外部证据 JSON"), { target: { files: [file] } });

    expect(await screen.findByRole("alert")).toHaveTextContent("证据导入失败");
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/control/r7b/assess"))).toBe(false);
  });
});
