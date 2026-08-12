import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Catalog } from "../../types";
import { IntelligenceR5Workbench } from "./IntelligenceR5Workbench";
import type { R5ExamplePayload, R5Manifest, R5ScenarioSummary } from "./types";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

const manifest: R5Manifest = {
  manifestId: "axiom.intelligence.r5-manifest@1",
  schemaId: "axiom.intelligence.r5-manifest@1",
  schemaVersion: 1,
  stage: "R5-A",
  domainPackId: "intelligence.domain-pack@1",
  platform: "windows",
  defaultScenarioId: "synthetic-residual-contract",
  safetyBanner: "SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE",
  learningBanner: "SYNTHETIC LEARNING CONTRACT / REAL-WORLD GENERALIZATION OPEN",
  syntheticLearningContractStatus: "Passed",
  realWorldGeneralizationStatus: "Open",
};

const scenario: R5ScenarioSummary = {
  scenarioId: "synthetic-residual-contract",
  title: "Synthetic residual contract",
  description: "Independent topology split for the X residual candidate.",
  expectedOutcome: "Passed",
  expectedExecutionStatus: "Succeeded",
};

const counterexampleScenario: R5ScenarioSummary = {
  scenarioId: "group-leak",
  title: "Group leak",
  description: "Validation illegally reuses the train trajectory family.",
  expectedOutcome: "Invalid",
  expectedExecutionStatus: "Skipped",
};

const example: R5ExamplePayload = {
  manifest,
  scenario,
  dataset: {
    datasetId: "r5.synthetic-sil@1",
    artifactType: "axiom.intelligence.dataset-snapshot",
    contentHash: "a".repeat(64),
    axisIds: ["X", "Y", "Z", "B", "C"],
    samples: Array.from({ length: 30 }, (_, index) => ({ sampleId: `sample-${index}` })),
    governance: {
      governanceId: "axiom.intelligence.synthetic-governance@1",
      sourceKind: "synthetic-sil",
      syntheticLearningContractStatus: "Passed",
      realWorldGeneralizationStatus: "Open",
      safetyBanner: "SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE",
      licenseId: "axiom-project-internal-synthetic@1",
      allowedUses: ["contract-validation"],
      sensitivity: "synthetic",
      retentionPolicyId: "axiom.synthetic-fixture-retention@1",
      redistributionAllowed: false,
    },
  },
  splitManifest: {
    manifestId: "r5.topology-split@1",
    contentHash: "b".repeat(64),
    partitions: [
      { splitId: "train", sampleIds: ["sample-0"], connectedGroupIds: ["train"], startTime: "2026-08-01T00:00:00Z", endTime: "2026-08-01T01:00:00Z" },
      { splitId: "validation", sampleIds: ["sample-10"], connectedGroupIds: ["validation"], startTime: "2026-08-02T00:00:00Z", endTime: "2026-08-02T01:00:00Z" },
      { splitId: "test", sampleIds: ["sample-20"], connectedGroupIds: ["test"], startTime: "2026-08-03T00:00:00Z", endTime: "2026-08-03T01:00:00Z" },
    ],
  },
  modelBundle: {
    bundleId: "r5.x-residual-ridge@1",
    artifactType: "axiom.intelligence.model-bundle",
    contentHash: "c".repeat(64),
    targetInterpreterId: "axiom.intelligence.target-interpreter.python@1",
    inputContractId: "axiom.intelligence.x-residual-input@1",
    preprocessorId: "axiom.intelligence.polynomial-feature-map@1",
    outputContractId: "axiom.intelligence.residual-with-abstention@1",
    xAxisHead: {
      axisId: "X",
      featureOrder: ["bias", "t", "t2", "t3", "t4", "command_minus_simulation"],
      conformalRadius: 0.04,
      featureEnvelope: { marginFraction: 0.25 },
    },
    axisDispositions: [],
    resourceBudget: { targetRuntime: "pure-python", featureCount: 6, deterministicNumericType: "float64", weightDecimalPlaces: 15 },
  },
  evaluation: {
    syntheticLearningContractStatus: "Passed",
    realWorldGeneralizationStatus: "Open",
    axisResults: [
      { axisId: "X", status: "Validated", baselineRmse: 0.1, modelRmse: 0.0789, improvementRatio: 0.2109 },
      { axisId: "Y", status: "NoValidatedImprovement", reasonCode: "IndependentTestDidNotImprove" },
      { axisId: "Z", status: "NoValidatedImprovement", reasonCode: "IndependentTestDidNotImprove" },
      { axisId: "B", status: "InsufficientExcitation", reasonCode: "InsufficientAxisExcitation" },
      { axisId: "C", status: "InsufficientExcitation", reasonCode: "InsufficientAxisExcitation" },
    ],
    oodDetectionRate: 1,
    conformalCoverage: 5 / 6,
    targetParityMaxAbsGap: 1.7e-18,
    baselineTestRmse: 0.1,
    modelTestRmse: 0.0789,
    claims: [
      { claimId: "intelligence.synthetic-learning-contract-claim@1", title: "Synthetic learning contract", status: "Supported", statement: "The Windows synthetic contract passed.", evidenceLevel: "Validated" },
      { claimId: "intelligence.real-world-generalization-claim@1", title: "Real-world generalization", status: "Inconclusive", statement: "No real paired holdout is present.", reasonCode: "RealPairedHoldoutMissing" },
    ],
    evidence: [
      { evidenceId: "independent-test", title: "Independent topology test", summary: "The test split was not used for training or conformal calibration.", contentHash: "d".repeat(64) },
    ],
  },
};

const catalog: Catalog = {
  subjects: [],
  artifactAdapters: [],
  domainPacks: [{ domainPackId: "intelligence.domain-pack@1", comparisonPolicyIds: [], runnerIds: [], runtimeBound: true }],
};

afterEach(() => vi.unstubAllGlobals());

describe("IntelligenceR5Workbench", () => {
  it("展示双状态门、按轴边界、OOD/UQ 和端侧一致性", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/intelligence/r5/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/intelligence/r5/scenarios")) return Promise.resolve(jsonResponse([scenario]));
      if (url.includes("/examples/intelligence-r5")) return Promise.resolve(jsonResponse(example));
      return Promise.resolve(new Response("not found", { status: 404 }));
    }));

    render(<IntelligenceR5Workbench catalog={catalog} />);

    expect(await screen.findByText("SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByText("SYNTHETIC LEARNING CONTRACT / REAL-WORLD GENERALIZATION OPEN")).toBeInTheDocument();
    expect(screen.getByText("21.1% RMSE improvement")).toBeInTheDocument();
    expect(screen.getAllByText("No Validated Improvement")).toHaveLength(2);
    expect(screen.getAllByText("Insufficient Excitation")).toHaveLength(2);
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    expect(screen.getByText("83.3%")).toBeInTheDocument();
    expect(screen.getByText("Real-world generalization")).toBeInTheDocument();
    expect(screen.getByText("absent")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|应用参数|在线学习/i })).not.toBeInTheDocument();
  });

  it("切换到反例时只展示预期拒绝，不继承正向模型声明", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/intelligence/r5/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/intelligence/r5/scenarios")) {
        return Promise.resolve(jsonResponse([scenario, counterexampleScenario]));
      }
      if (url.includes("scenarioId=group-leak")) {
        const counterexample: R5ExamplePayload = { ...example };
        delete counterexample.evaluation;
        return Promise.resolve(jsonResponse({ ...counterexample, scenario: counterexampleScenario }));
      }
      if (url.includes("/examples/intelligence-r5")) return Promise.resolve(jsonResponse(example));
      return Promise.resolve(new Response("not found", { status: 404 }));
    }));

    render(<IntelligenceR5Workbench catalog={catalog} />);
    await screen.findByText("21.1% RMSE improvement");

    fireEvent.change(screen.getByLabelText("验收场景"), { target: { value: "group-leak" } });

    expect(await screen.findByText("Expected outcome: Invalid")).toBeInTheDocument();
    expect(screen.getByText("No positive claim emitted")).toBeInTheDocument();
    expect(screen.queryByText("21.1% RMSE improvement")).not.toBeInTheDocument();
    expect(screen.queryByText("Synthetic learning contract")).not.toBeInTheDocument();
  });
});
