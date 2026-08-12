import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OptimizationR6Workbench } from "./OptimizationR6Workbench";
import type { R6ExamplePayload } from "./types";

const manifest = {
  manifestId: "optimization.r6-manifest@1",
  domainPackId: "optimization.domain-pack@1" as const,
  evaluatorVersion: "optimization-evaluator@1",
  runnerId: "optimization-offline-search@1",
  supportedPlatforms: ["Windows"] as ["Windows"],
  permissionLevel: "Offline" as const,
  deviceWriteAllowed: false as const,
  parameterIds: ["feedOverride", "samplePeriod"] as ["feedOverride", "samplePeriod"],
  objectiveIds: ["cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"] as ["cycleTimeSeconds", "linearFollowingErrorMaxMm", "commandSampleCount"],
  scenarioIds: ["canonical-head-table-offline-pareto"],
  realityValidationStatus: "Open" as const,
};

const scenario = {
  scenarioId: "canonical-head-table-offline-pareto",
  title: "Canonical head-table offline Pareto search",
  description: "Six evidence-backed offline candidates.",
  expectedOutcome: "Passed" as const,
  permissionLevel: "Offline" as const,
};

const gates = [
  "geometry-valid", "task-geometry-collision-free", "kinematically-feasible",
  "configuration-collision-free", "continuously-feasible", "interval-certified", "model-collision-free",
].map((id) => ({ claimId: `five-axis.${id}-claim@1`, status: "Supported" as const, evidenceContentHash: "a".repeat(64), method: "replay" }));

const payload: R6ExamplePayload = {
  manifest,
  scenario,
  searchRequest: {
    schemaId: "optimization.search-request@1",
    scenarioId: "canonical-head-table-offline-pareto",
    goal: { goalId: "optimization.r6.balanced-goal@1", objectiveIds: manifest.objectiveIds },
    grid: { feedOverrides: [0.7, 0.85, 1], samplePeriods: [0.04, 0.08] },
  },
  recommendationSet: {
    recommendationSetId: "axiom.optimization.r6.canonical-head-table@1",
    contentHash: "b".repeat(64),
    candidates: [{
      candidateId: "optimization.r6.feed-100.period-080ms@1",
      parameterSet: { parameterSetId: "optimization.r6.feed-100.period-080ms@1", values: { feedOverride: 1, samplePeriod: 0.08 } },
      objectives: { cycleTimeSeconds: 0.679, linearFollowingErrorMaxMm: 0.574, commandSampleCount: 10 },
      gateReceipts: gates,
      physicalApplicabilityPassed: true,
      hardConstraintsSatisfied: true,
      goalFeasible: true,
      paretoOptimal: true,
      oodFraction: 0.4,
      epistemicStatus: "PartiallyOutOfDomain",
      permissionLevel: "Offline",
      deviceWriteAllowed: false,
      promotionEligible: false,
      explanation: "Fastest candidate, but the model remains partially out of domain.",
      candidateContentHash: "c".repeat(64),
    }],
    paretoCandidateIds: ["optimization.r6.feed-100.period-080ms@1"],
    permissionLevel: "Offline",
    deviceWriteAllowed: false,
    automaticAcceptanceAllowed: false,
    shadowStatus: "Open",
    realityValidationStatus: "Open",
    physicalApplicabilityEvidence: {
      contentHash: "d".repeat(64), status: "Passed", oracleId: "oracle@1",
      endpointEvaluations: [
        { samplePeriodSeconds: 0.04, sampleCount: 18, improvementRatio: 0.92, requiredImprovementRatio: 0.35, passed: true },
        { samplePeriodSeconds: 0.08, sampleCount: 10, improvementRatio: 0.98, requiredImprovementRatio: 0.35, passed: true },
      ],
    },
    validationPlan: {
      planId: "optimization.r6.offline-validation-plan@1", permissionLevel: "Offline",
      remainingGates: ["real holdout"], stopConditions: ["math gate failure"],
      rollbackParameterSetId: "optimization.r6.feed-100.period-080ms@1", deviceWriteAllowed: false,
    },
  },
  runSpec: {},
};

afterEach(() => vi.restoreAllMocks());

describe("OptimizationR6Workbench", () => {
  it("展示 Pareto、七硬门与 Offline 权限边界", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? [scenario] : payload;
      return Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));
    });

    render(<OptimizationR6Workbench catalog={{ subjects: [], artifactAdapters: [], domainPacks: [{ domainPackId: "optimization.domain-pack@1", comparisonPolicyIds: [], runnerIds: ["optimization-offline-search@1"], runtimeBound: true }] }} />);

    expect(await screen.findByText("快、准、少采样，不压成一个总分")).toBeInTheDocument();
    expect(screen.getByText("7 / 7")).toBeInTheDocument();
    expect(screen.getByText("OFFLINE · NO WRITE")).toBeInTheDocument();
    expect(screen.queryByText(/DeviceSafe/)).not.toBeInTheDocument();
  });

  it("把用户目标约束提交到 R6 搜索端点", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? [scenario] : payload;
      return Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    render(<OptimizationR6Workbench catalog={null} />);
    await screen.findByText("候选矩阵");

    fireEvent.change(screen.getByLabelText("最大周期"), { target: { value: "0.7" } });
    fireEvent.click(screen.getByRole("button", { name: /搜索 Pareto 候选/ }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/optimization/r6/search") && init?.method === "POST")).toBe(true));
  });

  it("在发送请求前拒绝非整数的最大样本数", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const data = url.endsWith("/manifest") ? manifest : url.endsWith("/scenarios") ? [scenario] : payload;
      return Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    render(<OptimizationR6Workbench catalog={null} />);
    await screen.findByText("候选矩阵");

    fireEvent.change(screen.getByLabelText("最大样本数"), { target: { value: "10.5" } });
    fireEvent.click(screen.getByRole("button", { name: /搜索 Pareto 候选/ }));

    expect(await screen.findByText("最大样本数必须是正整数。")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/optimization/r6/search"))).toBe(false);
  });
});
