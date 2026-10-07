import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OptimizationR6Workbench } from "./OptimizationR6Workbench";
import type { GoalToShadowReport, R6V2ExamplePayload } from "./types";

const manifest = {
  manifestId: "optimization.r6v2-manifest@1",
  schemaId: "optimization.r6v2-manifest@1" as const,
  schemaVersion: 2 as const,
  domainPackId: "optimization.domain-pack@2" as const,
  evaluatorVersion: "optimization-evaluator@2",
  runnerId: "optimization-surrogate-assisted-search@2",
  supportedPlatforms: ["Windows"] as ["Windows"],
  parameterIds: ["feedOverride", "samplePeriod"] as ["feedOverride", "samplePeriod"],
  objectiveIds: ["cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"] as ["cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"],
  scenarioIds: ["canonical-goal-conditioned-speed"],
  screeningCandidateCount: 135 as const,
  exactValidationBudget: 27 as const,
  optimalityScope: "best-observed-within-exact-validation-budget" as const,
  globalOptimalityStatus: "NotClaimed" as const,
  permissionLevel: "Offline" as const,
  deviceWriteAllowed: false as const,
  realityValidationStatus: "Open" as const,
};

const scenario = {
  scenarioId: "canonical-goal-conditioned-speed",
  title: "Goal-conditioned speed search",
  description: "Minimize cycle time under two explicit epsilon constraints.",
  primaryObjectiveId: "cycleTimeSeconds" as const,
  expectedOutcome: "Passed" as const,
  permissionLevel: "Offline" as const,
  globalOptimalityStatus: "NotClaimed" as const,
};

const gates = [
  "geometry-valid", "task-geometry-collision-free", "kinematically-feasible",
  "configuration-collision-free", "continuously-feasible", "interval-certified", "model-collision-free",
].map((id) => ({ claimId: `five-axis.${id}-claim@1`, status: "Supported" as const, evidenceContentHash: "a".repeat(64), method: "exact replay" }));

const payload: R6V2ExamplePayload = {
  manifest,
  scenario,
  searchRequest: {
    schemaId: "optimization.search-request@2",
    scenarioId: scenario.scenarioId,
    intent: {
      intentId: "optimization.r6v2.speed-intent@1",
      primaryObjectiveId: "cycleTimeSeconds",
      maximumLinearFollowingErrorMm: 0.46,
      maximumCommandSampleCount: 18,
    },
    surrogateContext: {},
    screeningPolicyId: "optimization.r6v2.possible-feasible-lower-bound@1",
    feedOverrides: [0.65, 1],
    samplePeriods: [0.04, 0.08],
    exactValidationBudget: 27,
  },
  recommendationSet: {
    recommendationSetId: "axiom.optimization.r6v2.canonical-goal-conditioned-speed@1",
    contentHash: "b".repeat(64),
    searchRequest: {} as R6V2ExamplePayload["searchRequest"],
    screeningReceipt: {
      contentHash: "c".repeat(64),
      candidateCount: 135,
      possiblyFeasibleCount: 94,
      selectedCount: 27,
      exactValidationBudget: 27,
    },
    exactCandidates: [{
      candidateId: "optimization.r6v2.feed-0825.period-050ms@1",
      parameterSet: { parameterSetId: "optimization.r6v2.feed-0825.period-050ms@1", values: { feedOverride: 0.825, samplePeriod: 0.05 } },
      screeningRank: 3,
      objectives: { cycleTimeSeconds: 0.823, linearFollowingErrorMaxMm: 0.45, commandSampleCount: 18 },
      gateReceipts: gates,
      hardConstraintsSatisfied: true,
      exactConstraintsSatisfied: true,
      recommendationEligible: true,
      paretoOptimalWithinValidated: true,
      bestObserved: true,
      oodFraction: 0,
      epistemicStatus: "InDomain",
      cycleTimePredictionAbsoluteError: 0.000001,
      linearErrorPredictionAbsoluteError: 0.001,
      permissionLevel: "Offline",
      deviceWriteAllowed: false,
      promotionEligible: false,
      explanation: "Exact F3/F4/R4 replay satisfied the declared epsilon constraints.",
      contentHash: "d".repeat(64),
    }],
    exactFeasibleCandidateIds: ["optimization.r6v2.feed-0825.period-050ms@1"],
    paretoCandidateIds: ["optimization.r6v2.feed-0825.period-050ms@1"],
    bestObservedCandidateIds: ["optimization.r6v2.feed-0825.period-050ms@1"],
    validationPlan: {
      remainingGates: ["independent-real-device-holdout"],
      stopConditions: ["any exact gate becomes non-Supported"],
      rollbackParameterSetId: "optimization.r6v2.feed-1000.period-080ms@1",
    },
    optimalityScope: "best-observed-within-exact-validation-budget",
    globalOptimalityStatus: "NotClaimed",
    permissionLevel: "Offline",
    deviceWriteAllowed: false,
    automaticAcceptanceAllowed: false,
    shadowStatus: "Open",
    realityValidationStatus: "Open",
  },
  runSpec: {},
};
payload.recommendationSet.searchRequest = payload.searchRequest;

const shadowReport: GoalToShadowReport = {
  status: "Passed",
  reasonCodes: [],
  selectedCandidateId: "optimization.r6v2.feed-0825.period-050ms@1",
  sourceSearchRequestHash: "e".repeat(64),
  recommendationProjection: { selectionClass: "BestObserved", contentHash: "f".repeat(64) },
  physicalShadowProjection: {
    candidateContentHash: "d".repeat(64),
    candidateM4ContentHash: "1".repeat(64),
    sourceCommandM4ContentId: "2".repeat(64),
    sourceM5ContentHash: "3".repeat(64),
    sourcePhysicalResponseContentHash: "4".repeat(64),
    sampleCount: 18,
    alignment: "exact-sample-index-time-and-command",
    interpolationApplied: false,
    linearAxisIds: ["X", "Y", "Z"],
    linearAxisUnit: "mm",
    excludedRotaryAxisIds: ["B", "C"],
    candidateOodFraction: 0.22,
    maximumLinearFollowingErrorMm: 0.44976,
    sourceKind: "synthetic-sil",
    shadowTrace: { contentHash: "5".repeat(64), samples: [] },
    contentHash: "6".repeat(64),
  },
  runtimeAudit: {
    admissionDecision: { status: "Admitted", reasonCodes: [] },
    finalState: "Completed",
    monitorFindings: [],
    stopReceipt: { requested: false, effect: "NotRequired", reasonCodes: [] },
    rollbackReceipt: { status: "NotRequired" },
    deviceWritePerformed: false,
    deploymentShadowStatus: "Open",
    controlledTrialStatus: "Open",
    closedLoopStatus: "Open",
    contentHash: "7".repeat(64),
  },
  syntheticSilStatus: "Passed",
  deploymentShadowStatus: "Open",
  realityValidationStatus: "Open",
  controlledTrialStatus: "Open",
  closedLoopStatus: "Open",
  deviceSafetyStatus: "NotAssessed",
  processSafetyStatus: "NotAssessed",
  deviceWriteAllowed: false,
  automaticAcceptanceAllowed: false,
  contentHash: "8".repeat(64),
};

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? [scenario] : url.endsWith("/goal-to-shadow/rehearse") ? shadowReport : payload;
    return Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));
  });
}

afterEach(() => vi.restoreAllMocks());

describe("OptimizationR6Workbench", () => {
  it("默认展示目标驱动、证据漏斗与 Offline 权限边界", async () => {
    mockApi();
    render(<OptimizationR6Workbench catalog={{ subjects: [], artifactAdapters: [], domainPacks: [{ domainPackId: "optimization.domain-pack@2", comparisonPolicyIds: [], runnerIds: ["optimization-surrogate-assisted-search@2"], runtimeBound: true }] }} />);

    expect(await screen.findByText("先用小模型缩小搜索，再用数学与物理模型裁决")).toBeInTheDocument();
    expect(screen.getByText("135")).toBeInTheDocument();
    expect(screen.getByText("7 / 7")).toBeInTheDocument();
    expect(screen.getByText("OFFLINE · NO WRITE")).toBeInTheDocument();
    expect(screen.getByText("v1 · Pareto")).toBeInTheDocument();
    expect(screen.queryByText(/DeviceSafe/)).not.toBeInTheDocument();
  });

  it("把一个主目标和两个约束提交到 R6 v2 搜索端点", async () => {
    const fetchMock = mockApi();
    render(<OptimizationR6Workbench catalog={null} />);
    await screen.findByText("精确验证候选");

    fireEvent.change(screen.getByLabelText("最大线性误差"), { target: { value: "0.455" } });
    fireEvent.click(screen.getByRole("button", { name: /运行目标搜索/ }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/optimization/r6v2/search") && init?.method === "POST")).toBe(true));
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/optimization/r6v2/search"));
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.intent).toMatchObject({ primaryObjectiveId: "cycleTimeSeconds", maximumLinearFollowingErrorMm: 0.455, maximumCommandSampleCount: 18 });
    expect(body.intent).not.toHaveProperty("weights");
  });

  it("在发送请求前拒绝非整数的最大指令样本数", async () => {
    const fetchMock = mockApi();
    render(<OptimizationR6Workbench catalog={null} />);
    await screen.findByText("精确验证候选");

    fireEvent.change(screen.getByLabelText("最大指令样本数"), { target: { value: "10.5" } });
    fireEvent.click(screen.getByRole("button", { name: /运行目标搜索/ }));

    expect(await screen.findByText("最大指令样本数必须是正整数。")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/optimization/r6v2/search"))).toBe(false);
  });

  it("把用户选择的 exact candidate 与搜索请求一起送入真实 R4 Shadow 预演", async () => {
    const fetchMock = mockApi();
    render(<OptimizationR6Workbench catalog={null} />);
    await screen.findByText("Synthetic Shadow 预演");

    fireEvent.click(screen.getByRole("button", { name: /进入 Synthetic Shadow/ }));

    await screen.findByText("Completed");
    expect(screen.getByText("exact identity chain verified")).toBeInTheDocument();
    expect(screen.getByText("exact samples")).toBeInTheDocument();
    expect(screen.getByText("NOT DEVICE SAFE · NO WRITE · NO AUTO ACCEPT")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/control/goal-to-shadow/rehearse"));
    expect(call?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      candidateId: "optimization.r6v2.feed-0825.period-050ms@1",
      searchRequest: { scenarioId: "canonical-goal-conditioned-speed" },
    });
  });
});
