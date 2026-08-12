import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FieldEvidenceWorkbench } from "./FieldEvidenceWorkbench";
import type { R41ExamplePayload, R41Manifest, R7EExamplePayload, R7EManifest } from "./types";

const r7eManifest: R7EManifest = {
  manifestId: "control.r7e-manifest@1",
  domainPackId: "control.domain-pack@5",
  runnerId: "control-beckhoff-shadow-evidence-import@1",
  targetVendor: "Beckhoff Automation",
  targetControllerFamily: "TwinCAT 3",
  minimumTwinCatBuild: 4026,
  targetInterface: "TF6100 OPC UA Server",
  supportedPlatforms: ["Windows"],
  capturePolicy: "sample-index-triggered-batch-read",
  intervalPolicy: "exact-sample-index-no-interpolation",
  permissionCeiling: "Shadow",
  deviceWriteAllowed: false,
  methodCallAllowed: false,
  deploymentShadowStatus: "Open",
  realityValidationStatus: "Open",
  deviceSafetyStatus: "NotAssessed",
  processSafetyStatus: "NotAssessed",
};

const r7ePayload: R7EExamplePayload = {
  manifest: r7eManifest,
  scenario: { scenarioId: "beckhoff-shadow-witness-open", title: "Shadow evidence open", description: "No live capture is bundled." },
  vendorProfile: {},
  runtimeEvidence: null,
  witnessProfile: { profileId: "witness.open@1", bindingStatus: "Open", contentHash: "a".repeat(64), nodes: [] },
  controllerProfile: null,
  authority: null,
  captureAuthorization: null,
  command: null,
  shadowEvidence: null,
  readinessAudit: {
    auditId: "control.r7e.beckhoff-shadow-run-readiness-audit@1",
    contentHash: "b".repeat(64),
    checks: [
      { checkId: "r7e.contract", title: "Windows Beckhoff witness contract", status: "Passed" },
      { checkId: "r7e.capture", title: "External controller capture", status: "Open", reasonCode: "ShadowEvidenceMissing" },
    ],
    readinessOutcome: "Open",
    deploymentShadowStatus: "Open",
    realityValidationStatus: "Open",
    countsTowardDeploymentShadow: false,
    countsTowardReality: false,
    deviceSafetyStatus: "NotAssessed",
    processSafetyStatus: "NotAssessed",
  },
};

const r41Manifest: R41Manifest = {
  manifestId: "physical.r4.1-manifest@1",
  stage: "R4.1",
  domainPackId: "five-axis.domain-pack@7",
  runnerId: "five-axis-physical-reality-import@1",
  supportedPlatforms: ["Windows"],
  requiredIndependentRuns: 2,
  calibrationRole: "calibration",
  validationRole: "validation",
  interpolationAllowed: false,
  realityValidationStatus: "Open",
  controlledTrialStatus: "Open",
  closedLoopStatus: "Open",
  deviceSafetyStatus: "NotAssessed",
  processSafetyStatus: "NotAssessed",
};

const r41Checks = [
  "contract", "independent-evidence", "r7e-deployment-gates", "calibration",
  "alignment", "holdout-fit", "residual-decomposition", "reality-gate",
].map((id) => ({ checkId: `r41.${id}`, title: id, status: id === "contract" ? "Passed" as const : "Open" as const }));

const r41Payload: R41ExamplePayload = {
  manifest: r41Manifest,
  scenario: { scenarioId: "physical-reality-evidence-open", title: "Reality evidence open", description: "Two real runs are required." },
  calibrationPair: null,
  validationPair: null,
  analysis: {
    analysisId: "five-axis.r4.1.reality-analysis@1",
    contentHash: "c".repeat(64),
    checks: r41Checks,
    axes: [],
    alignmentCoverage: 0,
    fitStatus: "Open",
    realityValidationStatus: "Open",
    countsTowardReality: false,
    controlledTrialStatus: "Open",
    closedLoopStatus: "Open",
    deviceSafetyStatus: "NotAssessed",
    processSafetyStatus: "NotAssessed",
  },
};

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("FieldEvidenceWorkbench", () => {
  it("展示 R7-E 到 R4.1 的开放证据链且没有执行动作", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/control/r7e/manifest")) return Promise.resolve(response(r7eManifest));
      if (url.endsWith("/examples/control-r7e")) return Promise.resolve(response(r7ePayload));
      if (url.endsWith("/physical/r41/manifest")) return Promise.resolve(response(r41Manifest));
      if (url.endsWith("/examples/physical-r41")) return Promise.resolve(response(r41Payload));
      return Promise.resolve(new Response(null, { status: 404 }));
    }));

    render(<FieldEvidenceWorkbench catalog={{ subjects: [], artifactAdapters: [], domainPacks: [
      { domainPackId: "control.domain-pack@5", comparisonPolicyIds: [], runnerIds: [], runtimeBound: true },
      { domainPackId: "five-axis.domain-pack@7", comparisonPolicyIds: [], runnerIds: [], runtimeBound: true },
    ] }} />);

    expect(await screen.findByText("从一条真实只读轨迹，到一项受限的现实声明")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("READ / SUBSCRIBE ONLY · NOT DEVICE SAFE");
    expect(screen.getAllByText("Missing")).toHaveLength(2);
    expect(screen.getByText("Write / Call").nextElementSibling).toHaveTextContent("0 / 0");
    expect(screen.getByText("NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|启动|下发|闭环/i })).not.toBeInTheDocument();
  });

  it("导入双运行包后只调用 R4.1 评估端点", async () => {
    const blocked = {
      ...r41Payload,
      analysis: { ...r41Payload.analysis, realityValidationStatus: "Blocked" as const, fitStatus: "Blocked" as const },
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/control/r7e/manifest")) return Promise.resolve(response(r7eManifest));
      if (url.endsWith("/examples/control-r7e")) return Promise.resolve(response(r7ePayload));
      if (url.endsWith("/physical/r41/manifest")) return Promise.resolve(response(r41Manifest));
      if (url.endsWith("/examples/physical-r41")) return Promise.resolve(response(r41Payload));
      if (url.endsWith("/physical/r41/assess") && init?.method === "POST") return Promise.resolve(response(blocked));
      return Promise.resolve(new Response(null, { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<FieldEvidenceWorkbench catalog={null} />);
    await screen.findByText("从一条真实只读轨迹，到一项受限的现实声明");
    const file = new File([JSON.stringify({ calibrationPair: { pairId: "cal@1" }, validationPair: { pairId: "val@1" } })], "reality.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("导入 R4.1 双运行证据 JSON"), { target: { files: [file] } });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    expect(screen.getAllByText("Blocked").length).toBeGreaterThan(0);
    const call = fetchMock.mock.calls.at(-1);
    expect(String(call?.[0])).toContain("/physical/r41/assess");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ calibrationPair: { pairId: "cal@1" }, validationPair: { pairId: "val@1" } });
  });
});
