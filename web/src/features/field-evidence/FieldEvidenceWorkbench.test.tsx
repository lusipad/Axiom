import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FieldEvidenceWorkbench } from "./FieldEvidenceWorkbench";
import type {
  FieldEvidenceAssessmentReport,
  R41ExamplePayload,
  R41Manifest,
  R7EExamplePayload,
  R7EManifest,
} from "./types";

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
  runSpec: { request: { case: { caseId: "site.part-family-17@1" } } },
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

const fieldReport: FieldEvidenceAssessmentReport = {
  schemaId: "axiom.field-evidence-assessment-report@1",
  schemaVersion: 1,
  assessmentId: "axiom.field-evidence.web-assessment@1",
  caseId: "site.part-family-17@1",
  calibrationPairId: "axiom.field-evidence.calibration@1",
  validationPairId: "axiom.field-evidence.validation@1",
  calibrationAssessment: r7ePayload,
  validationAssessment: r7ePayload,
  calibrationPair: null,
  validationPair: null,
  realityAssessment: r41Payload,
  overallStatus: "Open",
  countsTowardReality: false,
  validationScope: "single-device-case-scoped",
  controlledTrialStatus: "Open",
  closedLoopStatus: "Open",
  deviceSafetyStatus: "NotAssessed",
  processSafetyStatus: "NotAssessed",
  contentHash: "d".repeat(64),
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

    expect(await screen.findByText("从两次真实只读轨迹，到一项受限的现实声明")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("READ / SUBSCRIBE ONLY · NOT DEVICE SAFE");
    expect(screen.getByRole("button", { name: "导入校准 Shadow 包" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入验证 Shadow 包" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行双证据验收" })).toBeInTheDocument();
    expect(screen.getByText("Write / Call").nextElementSibling).toHaveTextContent("0 / 0");
    expect(screen.getByText("NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|启动|下发|闭环/i })).not.toBeInTheDocument();
  });

  it("把两个同 Case 的 R7-E 结果交给现场证据评估端点", async () => {
    const blocked = {
      ...fieldReport,
      overallStatus: "Blocked" as const,
      realityAssessment: {
        ...r41Payload,
        analysis: { ...r41Payload.analysis, realityValidationStatus: "Blocked" as const, fitStatus: "Blocked" as const },
      },
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/control/r7e/manifest")) return Promise.resolve(response(r7eManifest));
      if (url.endsWith("/examples/control-r7e")) return Promise.resolve(response(r7ePayload));
      if (url.endsWith("/physical/r41/manifest")) return Promise.resolve(response(r41Manifest));
      if (url.endsWith("/examples/physical-r41")) return Promise.resolve(response(r41Payload));
      if (url.endsWith("/field-evidence/assess") && init?.method === "POST") return Promise.resolve(response(blocked));
      return Promise.resolve(new Response(null, { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<FieldEvidenceWorkbench catalog={null} />);
    await screen.findByText("从两次真实只读轨迹，到一项受限的现实声明");
    fireEvent.click(screen.getByRole("button", { name: "运行双证据验收" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    expect(screen.getAllByText("Blocked").length).toBeGreaterThan(0);
    const call = fetchMock.mock.calls.at(-1);
    expect(String(call?.[0])).toContain("/field-evidence/assess");
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.calibration.caseId).toBe("site.part-family-17@1");
    expect(body.validation.caseId).toBe("site.part-family-17@1");
    expect(body.calibrationPairId).not.toBe(body.validationPairId);
  });

  it("新的验收失败时不会继续展示上一次 Reality 结果", async () => {
    const passed = {
      ...fieldReport,
      overallStatus: "Passed" as const,
      countsTowardReality: true,
      realityAssessment: {
        ...r41Payload,
        analysis: {
          ...r41Payload.analysis,
          realityValidationStatus: "Passed" as const,
          fitStatus: "Passed" as const,
          countsTowardReality: true,
        },
      },
    };
    let assessmentCount = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/control/r7e/manifest")) return Promise.resolve(response(r7eManifest));
      if (url.endsWith("/examples/control-r7e")) return Promise.resolve(response(r7ePayload));
      if (url.endsWith("/physical/r41/manifest")) return Promise.resolve(response(r41Manifest));
      if (url.endsWith("/examples/physical-r41")) return Promise.resolve(response(r41Payload));
      if (url.endsWith("/field-evidence/assess") && init?.method === "POST") {
        assessmentCount += 1;
        if (assessmentCount === 1) return Promise.resolve(response(passed));
        return Promise.resolve(new Response(JSON.stringify({ detail: "capture rejected" }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }));
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<FieldEvidenceWorkbench catalog={null} />);
    await screen.findByText("从两次真实只读轨迹，到一项受限的现实声明");
    const runButton = screen.getByRole("button", { name: "运行双证据验收" });

    fireEvent.click(runButton);
    await waitFor(() => expect(screen.getAllByText("Passed").length).toBeGreaterThan(0));
    fireEvent.click(runButton);

    expect(await screen.findByRole("alert")).toHaveTextContent("capture rejected");
    expect(screen.queryByText("case-scoped evidence")).not.toBeInTheDocument();
    expect(screen.getByText("external evidence missing")).toBeInTheDocument();
  });

  it("重新导入 R7-E 结果时保留现场 Case 身份", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/control/r7e/manifest")) return Promise.resolve(response(r7eManifest));
      if (url.endsWith("/examples/control-r7e")) return Promise.resolve(response(r7ePayload));
      if (url.endsWith("/physical/r41/manifest")) return Promise.resolve(response(r41Manifest));
      if (url.endsWith("/examples/physical-r41")) return Promise.resolve(response(r41Payload));
      if (url.endsWith("/control/r7e/assess") && init?.method === "POST") return Promise.resolve(response(r7ePayload));
      return Promise.resolve(new Response(null, { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<FieldEvidenceWorkbench catalog={null} />);
    await screen.findByText("从两次真实只读轨迹，到一项受限的现实声明");
    const file = new File([JSON.stringify(r7ePayload)], "shadow.json", { type: "application/json" });
    fireEvent.change(screen.getByLabelText("导入校准 R7-E Shadow 证据 JSON"), { target: { files: [file] } });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    const call = fetchMock.mock.calls.at(-1);
    expect(String(call?.[0])).toContain("/control/r7e/assess");
    expect(JSON.parse(String(call?.[1]?.body)).caseId).toBe("site.part-family-17@1");
  });
});
