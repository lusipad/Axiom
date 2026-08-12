import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ControlR7DWorkbench } from "./ControlR7DWorkbench";
import type {
  BeckhoffRuntimeEvidence,
  BeckhoffTwinCatProfile,
  R7DExamplePayload,
  R7DManifest,
  R7DScenarioSummary,
} from "./types";

const manifest: R7DManifest = {
  manifestId: "control.r7d-manifest@1",
  domainPackId: "control.domain-pack@4",
  evaluatorVersion: "control-beckhoff-vendor-readiness-evaluator@1",
  runnerId: "control-beckhoff-evidence-import@1",
  vendorProfileId: "axiom.control.beckhoff-twincat-default-profile@1",
  verifierId: "axiom.control.beckhoff-twincat-read-verifier@1",
  verifierVersion: "0.2.0",
  targetVendor: "Beckhoff Automation",
  targetControllerFamily: "TwinCAT 3",
  minimumTwinCatBuild: 4026,
  targetInterface: "TF6100 OPC UA Server",
  supportedPlatforms: ["Windows"],
  defaultScenarioId: "beckhoff-twincat-runtime-open",
  scenarioIds: ["beckhoff-twincat-runtime-open"],
  permissionCeiling: "Shadow",
  deviceWriteAllowed: false,
  vendorProfileStatus: "Passed",
  vendorRuntimeStatus: "Open",
  deploymentShadowStatus: "Open",
  realityValidationStatus: "Open",
  deviceSafetyStatus: "NotAssessed",
  processSafetyStatus: "NotAssessed",
};

const scenario: R7DScenarioSummary = {
  scenarioId: "beckhoff-twincat-runtime-open",
  title: "Beckhoff TwinCAT runtime evidence (open)",
  description: "Deployment identity and runtime evidence remain open.",
  expectedOutcome: "Inconclusive",
  expectedReadinessOutcome: "Open",
  countsTowardReality: false,
};

const profile: BeckhoffTwinCatProfile = {
  schemaId: "axiom.control.beckhoff-twincat-profile@1",
  profileId: manifest.vendorProfileId,
  contentHash: "a".repeat(64),
  vendorName: "Beckhoff Automation",
  controllerFamily: "TwinCAT 3",
  minimumTwinCatBuild: 4026,
  opcUaServerProduct: "TF6100 OPC UA Server",
  requiredLicenseId: "TF6100",
  requiredPackages: ["TwinCAT.Standard.XAR", "TF6100.OpcUaServer.XAR"],
  defaultEndpointUrl: "opc.tcp://localhost:4840",
  messageSecurityMode: "SignAndEncrypt",
  accessMode: "read-subscribe-only",
  bindingStatus: "Open",
  permissionCeiling: "Shadow",
  deviceWriteAllowed: false,
  channels: ["X", "Y", "Z", "B", "C"].map((axis) => ({
    axisId: axis as "X" | "Y" | "Z" | "B" | "C",
    canonicalSignalId: `machine.axis.${axis}.position`,
    unit: (["X", "Y", "Z"].includes(axis) ? "mm" : "rad") as "mm" | "rad",
  })),
};

const runtimeEvidence: BeckhoffRuntimeEvidence = {
  schemaId: "axiom.control.beckhoff-runtime-evidence@1",
  evidenceId: "axiom.control.beckhoff.preflight@1",
  contentHash: "b".repeat(64),
  profileContentHash: profile.contentHash,
  verifierId: manifest.verifierId,
  verifierVersion: manifest.verifierVersion,
  platform: "Windows",
  sourceKind: "vendor-runtime",
  capturedAt: "2026-08-13T00:00:00+00:00",
  installation: {
    status: "Open",
    reasonCode: "TwinCatPackageManagerMissing",
    tcpkgAvailable: false,
    packages: [],
  },
  license: { licenseId: "TF6100", state: "Unknown" },
  writeRejection: { status: "NotRun", operationCount: 0 },
  countsTowardReality: false,
  realityValidationStatus: "Open",
  deviceSafetyStatus: "NotAssessed",
  processSafetyStatus: "NotAssessed",
};

function payload(
  evidence: BeckhoffRuntimeEvidence | null,
  vendorRuntimeStatus: "Open" | "Passed" = "Open",
): R7DExamplePayload {
  const check = (checkId: string, title: string, status: "Passed" | "Open", reasonCode?: string) => ({ checkId, title, status, reasonCode, details: {} });
  return {
    manifest,
    scenario,
    profile,
    runtimeEvidence: evidence,
    transportEvidence: null,
    runSpec: {},
    readinessAudit: {
      auditId: "control.r7d.beckhoff-vendor-readiness-audit@1",
      contentHash: "c".repeat(64),
      checks: [
        check("r7d.target", "Beckhoff TwinCAT 3 target selection", "Passed"),
        check("r7d.profile", "Versioned Beckhoff Vendor Profile contract", "Passed"),
        check("r7d.installation", "TwinCAT 3 Build 4026+ and TF6100 runtime packages", "Open", evidence?.installation.reasonCode ?? "BeckhoffRuntimeEvidenceMissing"),
        check("r7d.license", "TF6100 license state", "Open", "Tf6100LicenseEvidenceMissing"),
        check("r7d.server-identity", "Pinned TwinCAT OPC UA Server BuildInfo", "Open", "DeploymentBindingOpen"),
        check("r7d.node-mapping", "X/Y/Z/B/C node mapping and read-only access levels", "Open", "DeploymentBindingOpen"),
        check("r7d.readonly-enforcement", "Independent controller-side write rejection", "Open", "IndependentWriteProbeMissing"),
        check("r7d.transport", "R7-C secure five-axis transport receipt", "Open", "DeploymentBindingOpen"),
        check("r7d.reality-gate", "Independent case-scoped deployment Shadow validation", "Open", "RealDeploymentCaptureMissing"),
      ],
      readinessOutcome: "Open",
      permissionCeiling: "Shadow",
      deviceWriteAllowed: false,
      vendorProfileStatus: "Passed",
      vendorRuntimeStatus,
      deploymentShadowStatus: "Open",
      realityValidationStatus: "Open",
      controlledTrialStatus: "Open",
      closedLoopStatus: "Open",
      deviceSafetyStatus: "NotAssessed",
      processSafetyStatus: "NotAssessed",
    },
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => vi.restoreAllMocks());

describe("ControlR7DWorkbench", () => {
  it("显示默认 Beckhoff 目标与现实门开放边界", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      return Promise.resolve(jsonResponse(url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? [scenario] : payload(null)));
    });
    render(<ControlR7DWorkbench catalog={{ subjects: [], artifactAdapters: [], domainPacks: [{ domainPackId: manifest.domainPackId, comparisonPolicyIds: [], runnerIds: [manifest.runnerId], runtimeBound: true }] }} />);

    expect(await screen.findByText("把“支持 OPC UA”收紧为可审计的厂商事实")).toBeInTheDocument();
    expect(screen.getByText("READ / SUBSCRIBE ONLY · REALITY OPEN")).toBeInTheDocument();
    expect(screen.getByText("evaluator-bound")).toBeInTheDocument();
    expect(screen.getByText(/BECKHOFF PROFILE · VENDOR OPEN · REALITY OPEN/)).toBeInTheDocument();
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /安装|连接|写入|下发|启动|复位|急停/i })).not.toBeInTheDocument();
  });

  it("导入厂商运行时通过证据时只更新厂商门且保持现实门开放", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/scenarios")) return Promise.resolve(jsonResponse([scenario]));
      if (url.endsWith("/assess") && init?.method === "POST") {
        return Promise.resolve(jsonResponse(payload(runtimeEvidence, "Passed")));
      }
      return Promise.resolve(jsonResponse(payload(null)));
    });
    render(<ControlR7DWorkbench catalog={null} />);
    await screen.findByText("九项厂商门禁");

    const file = new File([JSON.stringify(runtimeEvidence)], "beckhoff-runtime.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("导入 Beckhoff R7-D 证据 JSON"), { target: { files: [file] } });

    expect(await screen.findByText(/BECKHOFF PROFILE · VENDOR PASSED · REALITY OPEN/)).toBeInTheDocument();
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);
  });

  it("导入 preflight 证据后仍保持现实门开放", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/scenarios")) return Promise.resolve(jsonResponse([scenario]));
      if (url.endsWith("/assess") && init?.method === "POST") return Promise.resolve(jsonResponse(payload(runtimeEvidence)));
      return Promise.resolve(jsonResponse(payload(null)));
    });
    render(<ControlR7DWorkbench catalog={null} />);
    await screen.findByText("九项厂商门禁");

    const file = new File([JSON.stringify(runtimeEvidence)], "beckhoff-preflight.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("导入 Beckhoff R7-D 证据 JSON"), { target: { files: [file] } });

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/control/r7d/assess") && init?.method === "POST")).toBe(true));
    expect((await screen.findAllByText("TwinCatPackageManagerMissing")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);
    expect(screen.getByText("NotAssessed")).toBeInTheDocument();
  });

  it("损坏文件停在浏览器侧", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      return Promise.resolve(jsonResponse(url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? [scenario] : payload(null)));
    });
    render(<ControlR7DWorkbench catalog={null} />);
    await screen.findByText("九项厂商门禁");

    fireEvent.change(screen.getByLabelText("导入 Beckhoff R7-D 证据 JSON"), {
      target: { files: [new File(["{bad"], "broken.json", { type: "application/json" })] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("证据导入失败");
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/control/r7d/assess"))).toBe(false);
  });
});
