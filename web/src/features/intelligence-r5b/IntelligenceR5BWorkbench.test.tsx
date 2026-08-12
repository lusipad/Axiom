import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Catalog, RunBundle } from "../../types";
import { IntelligenceR5BWorkbench } from "./IntelligenceR5BWorkbench";
import type { R5BExamplePayload, R5BManifest, R5BScenarioSummary } from "./types";

const catalog: Catalog = {
  subjects: [],
  artifactAdapters: [],
  domainPacks: [{ domainPackId: "intelligence.domain-pack@2", comparisonPolicyIds: [], runnerIds: [], runtimeBound: true }],
};

const manifest: R5BManifest = {
  manifestId: "axiom.intelligence.r5b-manifest@1",
  schemaId: "axiom.intelligence.r5b-manifest@1",
  schemaVersion: 1,
  stage: "R5-B",
  domainPackId: "intelligence.domain-pack@2",
  platform: "windows",
  defaultScenarioId: "real-holdout-readiness-open",
  contractReadinessStatus: "Passed",
  realWorldGeneralizationStatus: "Open",
  safetyBanner: "REAL HOLDOUT VALIDATION / NOT DEVICE SAFE",
  realityBanner: "NO BUNDLED REAL CAPTURE / CASE-SCOPED EVIDENCE REQUIRED",
  requiredEvidence: [
    "model-bundle@1",
    "dataset-snapshot@1",
    "split-manifest@1",
    "training-receipt@1",
    "target-parity-receipt@1",
    "real-paired-holdout-set@1",
  ],
  acceptanceThresholds: {
    minimumInDomainCases: 2,
    minimumTotalCases: 3,
    minimumDistinctDevices: 2,
    minimumDistinctConditions: 2,
    requiredAlignmentCoverage: 1,
    minimumImprovementRatio: 0.2,
    minimumConformalCoverage: 0.8,
    requiredOodAbstentionRate: 1,
    maximumTargetParityGap: 1e-12,
  },
};

const scenario: R5BScenarioSummary = {
  scenarioId: "real-holdout-readiness-open",
  title: "Windows real holdout readiness (open)",
  description: "The R5-A model lineage is sealed, but no bundled controller-export or device-read holdout exists.",
  expectedOutcome: "Inconclusive",
  expectedExecutionStatus: "Succeeded",
  realWorldGeneralizationStatus: "Open",
};

const example: R5BExamplePayload = {
  manifest,
  scenario,
  readinessChecks: [
    {
      checkId: "r5b.windows-runtime",
      title: "Windows-only runtime",
      status: "Passed",
      detail: "The validator is bound to the Windows acceptance matrix and exposes no device write path.",
    },
    {
      checkId: "r5b.real-source-governance",
      title: "Real source and governance",
      status: "Open",
      detail: "No controller-export or device-read capture with owner attestation and evaluation license is bundled.",
    },
    {
      checkId: "r5b.case-scoped-claim",
      title: "Case-scoped real-world claim",
      status: "Open",
      detail: "Only a complete external Windows holdout set can support a claim limited to its submitted cases.",
    },
  ],
  modelBundle: {
    artifactType: "axiom.intelligence.model-bundle",
    schemaId: "axiom.intelligence.model-bundle@1",
    schemaVersion: 1,
    bundleId: "axiom.intelligence.x-residual-ridge@1",
    domainPackId: "intelligence.domain-pack@1",
    evaluatorVersion: "intelligence-evaluator@1",
    targetInterpreterId: "axiom.intelligence.target-interpreter.python@1",
    inputContractId: "axiom.intelligence.x-residual-input@1",
    preprocessorId: "axiom.intelligence.polynomial-feature-map@1",
    outputContractId: "axiom.intelligence.residual-with-abstention@1",
    datasetContentHash: "a".repeat(64),
    splitManifestHash: "b".repeat(64),
    trainingReceiptHash: "c".repeat(64),
    syntheticLearningContractStatus: "Passed",
    realWorldGeneralizationStatus: "Open",
    axisDispositions: [
      { axisId: "X", status: "Validated" },
      { axisId: "Y", status: "NoValidatedImprovement" },
      { axisId: "Z", status: "NoValidatedImprovement" },
      { axisId: "B", status: "InsufficientExcitation" },
      { axisId: "C", status: "InsufficientExcitation" },
    ],
    xAxisHead: {
      axisId: "X",
      lambdaValue: 0.1,
      featureOrder: ["bias", "t", "t2", "t3", "t4", "command_minus_simulation"],
      weights: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
      conformalRadius: 0.04,
      featureEnvelope: {
        minimums: [0, 0, 0, 0, 0, -1],
        maximums: [1, 1, 1, 1, 1, 1],
        marginFraction: 0.25,
      },
    },
    resourceBudget: {
      targetRuntime: "pure-python",
      featureCount: 6,
      deterministicNumericType: "float64",
      weightDecimalPlaces: 15,
    },
    contentHash: "d".repeat(64),
  },
  dataset: {
    artifactType: "axiom.intelligence.dataset-snapshot",
    schemaId: "axiom.intelligence.dataset-snapshot@1",
    schemaVersion: 1,
    datasetId: "axiom.intelligence.synthetic-dataset@1",
    axisIds: ["X", "Y", "Z", "B", "C"],
    allowedSplitIds: ["train", "validation", "test"],
    governance: {
      governanceId: "axiom.synthetic-governance@1",
      sourceKind: "synthetic-sil",
      syntheticLearningContractStatus: "Passed",
      realWorldGeneralizationStatus: "Open",
      safetyBanner: "SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE",
      licenseId: "axiom.synthetic-license@1",
      allowedUses: ["contract-validation"],
      sensitivity: "synthetic",
      retentionPolicyId: "axiom.synthetic-retention@1",
      redistributionAllowed: false,
    },
    selectionPolicyId: "axiom.selection-policy@1",
    labelDerivationId: "axiom.label-derivation@1",
    knownBiases: ["synthetic domain gap"],
    coverageGaps: ["no bundled real holdout"],
    samples: [
      {
        sampleId: "sample-1",
        axisId: "X",
        topology: "dual-table",
        trajectoryFamily: "traj-a",
        taskId: "task-a",
        deviceBatchId: "batch-a",
        pairId: "pair-a",
        declaredSplitId: "train",
        scenarioRole: "in-domain",
        upstreamScenarioId: "r5-open",
        sourceCommandContentId: "e".repeat(64),
        sourceCommandSampleId: "command-1",
        labelDerivationId: "axiom.label-derivation@1",
        eventTime: "2026-08-01T00:00:00+00:00",
        t: 0,
        command: 0,
        simulation: 0,
        observation: 0,
      },
    ],
    contentHash: "f".repeat(64),
  },
  splitManifest: {
    artifactType: "axiom.intelligence.split-manifest",
    schemaId: "axiom.intelligence.split-manifest@1",
    schemaVersion: 1,
    manifestId: "axiom.intelligence.split-manifest@1",
    datasetContentHash: "f".repeat(64),
    partitions: [
      { splitId: "train", sampleIds: ["sample-1"], connectedGroupIds: ["traj-a|task-a|batch-a|pair-a"], startTime: "2026-08-01T00:00:00+00:00", endTime: "2026-08-01T00:00:00+00:00" },
      { splitId: "validation", sampleIds: ["sample-2"], connectedGroupIds: ["traj-b|task-b|batch-b|pair-b"], startTime: "2026-08-02T00:00:00+00:00", endTime: "2026-08-02T00:10:00+00:00" },
      { splitId: "test", sampleIds: ["sample-3"], connectedGroupIds: ["traj-c|task-c|batch-c|pair-c"], startTime: "2026-08-03T00:00:00+00:00", endTime: "2026-08-03T00:10:00+00:00" },
    ],
    contentHash: "1".repeat(64),
  },
  trainingReceipt: {
    artifactType: "axiom.intelligence.training-receipt",
    schemaId: "axiom.intelligence.training-receipt@1",
    schemaVersion: 1,
    receiptId: "axiom.intelligence.training-receipt@1",
    methodId: "axiom.intelligence.x-residual-ridge@1",
    datasetContentHash: "f".repeat(64),
    splitManifestHash: "1".repeat(64),
    lambdaValue: 0.1,
    featureOrder: ["bias", "t", "t2", "t3", "t4", "command_minus_simulation"],
    trainSampleCount: 12,
    validationSampleCount: 6,
    testSampleCount: 6,
    axisDispositions: [
      { axisId: "X", status: "Validated" },
      { axisId: "Y", status: "NoValidatedImprovement" },
      { axisId: "Z", status: "NoValidatedImprovement" },
      { axisId: "B", status: "InsufficientExcitation" },
      { axisId: "C", status: "InsufficientExcitation" },
    ],
    contentHash: "2".repeat(64),
  },
  parityReceipt: {
    artifactType: "axiom.intelligence.target-parity-receipt",
    schemaId: "axiom.intelligence.target-parity-receipt@1",
    schemaVersion: 1,
    receiptId: "axiom.intelligence.target-parity-receipt@1",
    modelBundleHash: "d".repeat(64),
    datasetContentHash: "f".repeat(64),
    maxAbsGap: 1e-12,
    sampleCount: 6,
    status: "Passed",
    contentHash: "3".repeat(64),
  },
  realHoldoutSet: null,
  runSpec: {
    subjectId: "axiom.intelligence.x-residual-model.real-holdout@1",
    domainPackId: "intelligence.domain-pack@2",
    runnerId: "intelligence-real-holdout-validation@1",
    evaluatorVersion: "intelligence-real-holdout-evaluator@1",
    request: {
      artifact: { bundleId: "axiom.intelligence.x-residual-ridge@1" },
      dataset: { datasetId: "axiom.intelligence.synthetic-dataset@1" },
      splitManifest: { manifestId: "axiom.intelligence.split-manifest@1" },
      trainingReceipt: { receiptId: "axiom.intelligence.training-receipt@1" },
      parityReceipt: { receiptId: "axiom.intelligence.target-parity-receipt@1" },
      realHoldoutSet: null,
      case: { caseId: "axiom.intelligence.real-holdout-readiness.case@1" },
    },
  },
};

function runBundle(overrides?: Partial<RunBundle>): RunBundle {
  const base: RunBundle = {
    run: {
      runId: "run.r5b",
      subjectId: "axiom.intelligence.x-residual-model.real-holdout@1",
      domainPackId: "intelligence.domain-pack@2",
      runnerId: "intelligence-real-holdout-validation@1",
      runSpecHash: "4".repeat(64),
      reportContentHash: "5".repeat(64),
      executionStatus: "Succeeded",
      caseOutcome: "Inconclusive",
      evaluatorVersion: "intelligence-real-holdout-evaluator@1",
      contentHash: "6".repeat(64),
    },
    report: {
      executionStatus: "Succeeded",
      caseOutcome: "Inconclusive",
      metricResults: [
        { metricId: "intelligence.r5b.model-integrity@1", status: "Computed", value: true },
        { metricId: "intelligence.real-world-generalization@1", status: "InsufficientContext", reasonCode: "RealPairedHoldoutMissing" },
        { metricId: "intelligence.r5b.alignment-coverage@1", status: "InsufficientContext", reasonCode: "RealPairedHoldoutMissing" },
        { metricId: "intelligence.r5b.x.observed-improvement-ratio@1", status: "InsufficientContext", reasonCode: "RealPairedHoldoutMissing", unit: "ratio" },
        { metricId: "intelligence.r5b.x.ood-abstention-rate@1", status: "InsufficientContext", reasonCode: "RealPairedHoldoutMissing", unit: "ratio" },
      ],
      provenance: {
        contextHashes: {
          dataset: "f".repeat(64),
          splitManifest: "1".repeat(64),
          trainingReceipt: "2".repeat(64),
          parityReceipt: "3".repeat(64),
        },
      },
    },
    claims: [
      {
        claimDefinitionId: "intelligence.real-world-generalization-claim@1",
        status: "Inconclusive",
        predicate: "Real-world generalization is supported only for the submitted Windows read-only holdout cases.",
      },
    ],
    bundleHash: "7".repeat(64),
  };
  return { ...base, ...overrides };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("IntelligenceR5BWorkbench", () => {
  it("展示 Open 原因、readiness 和内置场景的 Inconclusive RunBundle", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/intelligence/r5b/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/intelligence/r5b/scenarios")) return Promise.resolve(jsonResponse([scenario]));
      if (url.includes("/examples/intelligence-r5b")) return Promise.resolve(jsonResponse(example));
      if (url.endsWith("/runs/evaluate")) {
        expect(JSON.parse(String(init?.body))).toMatchObject({
          subjectId: "axiom.intelligence.x-residual-model.real-holdout@1",
          domainPackId: "intelligence.domain-pack@2",
        });
        return Promise.resolve(jsonResponse(runBundle()));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<IntelligenceR5BWorkbench catalog={catalog} />);

    expect(await screen.findByText("REAL HOLDOUT VALIDATION / NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByText("NO BUNDLED REAL CAPTURE / CASE-SCOPED EVIDENCE REQUIRED")).toBeInTheDocument();
    expect(screen.getByText("仓库未内置 controller-export / device-read holdout；真实世界泛化门保持 Open。")).toBeInTheDocument();
    expect(screen.getAllByText("Only a complete external Windows holdout set can support a claim limited to its submitted cases.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("100.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("20.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("80.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("absent").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /写设备|在线学习|自动部署/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "执行内置 Open 场景" }));

    expect(await screen.findByText("RunBundle: Inconclusive；缺少真实配对 holdout。")).toBeInTheDocument();
    expect(screen.getAllByText("Inconclusive").length).toBeGreaterThan(0);
    expect(screen.getByText("缺少真实配对 holdout，结论不可闭合。")).toBeInTheDocument();
    expect(screen.getByText("device write: blocked")).toBeInTheDocument();
  });

  it("支持导入客户端 RunSpec JSON 并走公共运行接口", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/intelligence/r5b/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/intelligence/r5b/scenarios")) return Promise.resolve(jsonResponse([scenario]));
      if (url.includes("/examples/intelligence-r5b")) return Promise.resolve(jsonResponse(example));
      if (url.endsWith("/runs/evaluate")) {
        expect(JSON.parse(String(init?.body))).toMatchObject({
          subjectId: "imported.subject@1",
          domainPackId: "intelligence.domain-pack@2",
          runnerId: "intelligence-real-holdout-validation@1",
          request: { realHoldoutSet: { artifactType: "axiom.intelligence.real-paired-holdout-set" } },
        });
        const supported = runBundle();
        supported.run.caseOutcome = "Passed";
        supported.report.caseOutcome = "Passed";
        supported.claims = [{
          claimDefinitionId: "intelligence.real-world-generalization-claim@1",
          status: "Supported",
          predicate: "Real-world generalization is supported only for the submitted Windows read-only holdout cases.",
        }];
        return Promise.resolve(jsonResponse(supported));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<IntelligenceR5BWorkbench catalog={catalog} />);
    await screen.findByText("REAL HOLDOUT VALIDATION / NOT DEVICE SAFE");

    const input = screen.getByLabelText("导入 RunSpec JSON") as HTMLInputElement;
    const file = new File(
      [JSON.stringify({
        subjectId: "imported.subject@1",
        domainPackId: "intelligence.domain-pack@2",
        runnerId: "intelligence-real-holdout-validation@1",
        evaluatorVersion: "intelligence-real-holdout-evaluator@1",
        request: {
          case: { caseId: "imported-case@1" },
          realHoldoutSet: { artifactType: "axiom.intelligence.real-paired-holdout-set" },
        },
      })],
      "r5b-runspec.json",
      { type: "application/json" },
    );

    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText(/已选择 r5b-runspec\.json/)).toBeInTheDocument();
    expect(screen.getByText("imported.subject@1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "执行导入 RunSpec" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([request]) => String(request).endsWith("/runs/evaluate"))).toBe(true);
    });
    expect(await screen.findByText("RunBundle: Passed；结论仅限已提交 holdout。")).toBeInTheDocument();
    expect(screen.getByText("证据范围仅限本次提交的 Windows holdout cases。")).toBeInTheDocument();
    expect(screen.queryByText("缺少真实配对 holdout，结论不可闭合。")).not.toBeInTheDocument();
  });

  it("明确展示导入解析错误与执行错误", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/intelligence/r5b/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/intelligence/r5b/scenarios")) return Promise.resolve(jsonResponse([scenario]));
      if (url.includes("/examples/intelligence-r5b")) return Promise.resolve(jsonResponse(example));
      if (url.endsWith("/runs/evaluate")) return Promise.resolve(jsonResponse({ detail: "boom" }, 500));
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<IntelligenceR5BWorkbench catalog={catalog} />);
    await screen.findByText("REAL HOLDOUT VALIDATION / NOT DEVICE SAFE");

    const input = screen.getByLabelText("导入 RunSpec JSON") as HTMLInputElement;
    const badFile = new File(["{bad"], "broken.json", { type: "application/json" });
    fireEvent.change(input, { target: { files: [badFile] } });
    expect(await screen.findByText("导入失败：JSON 解析失败，请提供完整 RunSpec JSON。")).toBeInTheDocument();

    const goodFile = new File(
      [JSON.stringify({
        subjectId: "imported.subject@1",
        domainPackId: "intelligence.domain-pack@2",
        runnerId: "intelligence-real-holdout-validation@1",
        request: { case: { caseId: "imported-case@1" } },
      })],
      "good.json",
      { type: "application/json" },
    );
    fireEvent.change(input, { target: { files: [goodFile] } });
    await screen.findByText("imported.subject@1");

    fireEvent.click(screen.getByRole("button", { name: "执行导入 RunSpec" }));
    expect(await screen.findByText('执行失败：API 500: "boom"')).toBeInTheDocument();
  });
});
