import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ControlR7Workbench } from "./ControlR7Workbench";
import type { R7ExamplePayload, R7Manifest, R7ScenarioSummary } from "./types";

const manifest: R7Manifest = {
  manifestId: "control.r7-manifest@1", domainPackId: "control.domain-pack@1", evaluatorVersion: "control-shadow-evaluator@1", runnerId: "control-synthetic-shadow-replay@1", supportedPlatforms: ["Windows"], permissionCeiling: "Shadow", deviceWriteAllowed: false, scenarioIds: ["synthetic-shadow-nominal", "synthetic-shadow-limit-breach"], syntheticShadowContractStatus: "Passed", deploymentShadowStatus: "Open", controlledTrialStatus: "Open", closedLoopStatus: "Open",
};
const scenarios: R7ScenarioSummary[] = [
  { scenarioId: "synthetic-shadow-nominal", title: "Synthetic nominal", description: "No breach", expectedOutcome: "Passed", expectedFinalState: "Completed" },
  { scenarioId: "synthetic-shadow-limit-breach", title: "Limit breach", description: "Stop promotion", expectedOutcome: "Passed", expectedFinalState: "RollbackVerified" },
];
const payload: R7ExamplePayload = {
  manifest, scenario: scenarios[0]!, recommendationSet: { contentHash: "a".repeat(64), permissionLevel: "Offline", realityValidationStatus: "Open" },
  runtimeSpec: { runtimeSpecId: "control.runtime@1", requestedPermission: "Shadow", deviceWriteRequested: false, candidateId: "candidate@1", recommendationSetContentHash: "a".repeat(64), envelope: { maximumLinearFollowingErrorMm: .6, maximumOodFraction: .5, maximumMonitorGapSeconds: .1, rollbackParameterSetId: "baseline@1", deviceWriteAllowed: false, contentHash: "b".repeat(64) }, trace: { sourceKind: "synthetic-shadow", samples: [{ sequence: 0, timeSeconds: 0, linearFollowingErrorMm: .1, oodFraction: 0 }, { sequence: 1, timeSeconds: .04, linearFollowingErrorMm: .2, oodFraction: 0 }] } },
  runtimeAudit: { auditId: "audit@1", contentHash: "c".repeat(64), finalState: "Completed", permissionCeiling: "Shadow", deviceWriteAllowed: false, deviceWritePerformed: false, syntheticShadowContractStatus: "Passed", deploymentShadowStatus: "Open", controlledTrialStatus: "Open", closedLoopStatus: "Open", standardsComplianceStatus: "NotAssessed", admissionDecision: { status: "Admitted", requestedPermission: "Shadow", grantedPermission: "Shadow", reasonCodes: [] }, acceptanceRecord: { recordId: "acceptance@1", disposition: "Shadow", grantedPermission: "Shadow", contentHash: "d".repeat(64), automatic: false, responsibility: { accountablePartyId: "owner", decisionPolicyId: "policy@1", approvalMode: "policy-replay", humanApprovalPresent: false, realDeviceAuthorityPresent: false } }, transitions: [{ sequence: 0, toState: "Prepared", reasonCode: "validated" }, { sequence: 1, fromState: "Prepared", toState: "Admitted", reasonCode: "admitted" }, { sequence: 2, fromState: "Admitted", toState: "Monitoring", reasonCode: "started" }, { sequence: 3, fromState: "Monitoring", toState: "Completed", reasonCode: "maintained" }], monitorFindings: [{ sampleSequence: 0, status: "WithinEnvelope", reasonCodes: [] }, { sampleSequence: 1, status: "WithinEnvelope", reasonCodes: [] }], stopReceipt: { requested: false, reasonCodes: [], effect: "NotRequired", deviceStopCommandIssued: false, deviceAcknowledged: false }, rollbackReceipt: { status: "NotRequired", baselineParameterSetId: "baseline@1", deviceWriteIssued: false, deviceReadbackVerified: false } }, runSpec: {},
};

afterEach(() => vi.restoreAllMocks());

describe("ControlR7Workbench", () => {
  it("展示 Shadow 权限、审计状态机和真实部署 Open 边界", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? scenarios : payload;
      return Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    render(<ControlR7Workbench catalog={{ subjects: [], artifactAdapters: [], domainPacks: [{ domainPackId: "control.domain-pack@1", comparisonPolicyIds: [], runnerIds: [manifest.runnerId], runtimeBound: true }] }} />);

    expect(await screen.findByText("可执行的是证据状态机，不是机床安全功能")).toBeInTheDocument();
    expect(screen.getByText("NO DEVICE AUTHORITY")).toBeInTheDocument();
    expect(screen.getByText("SHADOW ONLY · NOT A DEVICE SAFETY CLAIM", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /启动|复位|写入|下发|急停/i })).not.toBeInTheDocument();
  });

  it("通过唯一 replay 动作切换故障场景", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? scenarios : payload;
      return Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    render(<ControlR7Workbench catalog={null} />);
    await screen.findByText("状态迁移");
    fireEvent.change(screen.getByLabelText("冻结场景"), { target: { value: "synthetic-shadow-limit-breach" } });
    fireEvent.click(screen.getByRole("button", { name: /重放 Shadow 合同/ }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/control/r7/replay") && init?.method === "POST")).toBe(true));
  });
});

