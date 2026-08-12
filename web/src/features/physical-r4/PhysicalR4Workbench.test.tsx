import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PhysicalR4Workbench } from "./PhysicalR4Workbench";
import type { Catalog } from "../../types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const catalog: Catalog = {
  subjects: [],
  domainPacks: [
    {
      domainPackId: "five-axis.domain-pack@6",
      comparisonPolicyIds: [],
      runnerIds: ["windows-file-import@1"],
      runtimeBound: true,
    },
  ],
  artifactAdapters: [],
};

const manifest = {
  manifestId: "physical.r4-manifest@1",
  schemaId: "physical.r4-manifest@1",
  schemaVersion: 1,
  stage: "R4" as const,
  domainPackId: "five-axis.domain-pack@6",
  platform: "windows" as const,
  safetyBanner: "MODEL VALIDATION / NOT DEVICE SAFE" as const,
  validationBanner: "SYNTHETIC SIL / REALITY VALIDATION OPEN" as const,
  model: {
    equations: ["x[k+1] = Ad x[k] + Bd u[k]", "y[k] = Cd x[k] + Dd u[k]"],
    stateIds: ["x_pos", "x_vel"],
    inputIds: ["u_cmd"],
    outputIds: ["y_axis"],
    discretization: "exact-zoh" as const,
    supportedDevices: ["sim-840d", "sim-head-table"],
    operatingConditions: ["warm spindle", "nominal preload"],
    unmodeledFactors: ["thermal drift", "bearing preload variation"],
  },
};

const scenarios = [
  {
    scenarioId: "in-domain-synthetic-sil",
    title: "In-Domain Synthetic SIL",
    description: "Held-out validation split with open rotary reality validation.",
    axisIds: ["X", "B", "C"],
  },
];

const example = {
  manifest,
  scenario: scenarios[0],
  model: manifest.model,
  calibration: {
    datasetId: "cal-set@1",
    traceId: "trace-cal",
    scenarioRole: "calibration" as const,
    sourceId: "axiom.windows-file-telemetry-source@1",
    capturedAt: "2026-08-11T09:30:00Z",
    contentHash: "a".repeat(64),
  },
  validation: {
    datasetId: "val-set@1",
    traceId: "trace-val",
    scenarioRole: "validation" as const,
    sourceId: "axiom.windows-file-telemetry-source@1",
    capturedAt: "2026-08-11T10:00:00Z",
    contentHash: "b".repeat(64),
    leakageGuards: [
      { checkId: "split-by-run", status: "pass" as const, message: "Calibration and validation runs are disjoint." },
    ],
  },
  analysis: {
    traceArtifactType: "five-axis.physical-response-trace" as const,
    analysisContentHash: "c".repeat(64),
    curveMode: "canonical-analysis" as const,
    curveNotice: null,
    run: {
      caseOutcome: "Passed" as const,
      executionStatus: "Succeeded" as const,
      reportContentHash: "e".repeat(64),
      bundleHash: "f".repeat(64),
    },
    axes: [
      {
        axisId: "X",
        family: "linear-mm" as const,
        unit: "mm" as const,
        excitationStatus: "excited" as const,
        series: {
          command: [{ time: 0, value: 0 }, { time: 1, value: 10 }],
          simulation: [{ time: 0, value: 0 }, { time: 1, value: 9.8 }],
          observation: [{ time: 0, value: 0.1 }, { time: 1, value: 10.2 }],
        },
        metrics: [{ metricId: "x.max", label: "X max residual", group: "linear-mm" as const, value: 0.2, unit: "mm" }],
        residualDecomposition: [
          { componentId: "fit", label: "fit residual", value: 0.12, unit: "mm", source: "simulation-observation" as const },
        ],
      },
      {
        axisId: "B",
        family: "rotary-rad" as const,
        unit: "rad" as const,
        excitationStatus: "insufficient" as const,
        series: {
          command: [{ time: 0, value: 0 }, { time: 1, value: 0.02 }],
          simulation: [{ time: 0, value: 0 }, { time: 1, value: 0.02 }],
          observation: [{ time: 0, value: 0 }, { time: 1, value: 0.01 }],
        },
        metrics: [],
        residualDecomposition: [],
      },
      {
        axisId: "C",
        family: "rotary-rad" as const,
        unit: "rad" as const,
        excitationStatus: "insufficient" as const,
        series: {
          command: [{ time: 0, value: 0 }, { time: 1, value: 0.03 }],
          simulation: [{ time: 0, value: 0 }, { time: 1, value: 0.03 }],
          observation: [{ time: 0, value: 0 }, { time: 1, value: 0.01 }],
        },
        metrics: [],
        residualDecomposition: [],
      },
    ],
    metricResults: [
      {
        metricId: "five-axis.physical.linear.math-observation-rmse@1",
        metricDefinitionId: "five-axis.physical.linear.math-observation-rmse@1",
        label: "Linear math observation RMSE",
        group: "linear-mm" as const,
        status: "Computed" as const,
        value: 0.2,
        unit: "mm",
        thresholdPassed: null,
        reasonCode: null,
      },
      {
        metricId: "five-axis.physical.rotary.simulation-observation-rmse@1",
        metricDefinitionId: "five-axis.physical.rotary.simulation-observation-rmse@1",
        label: "Rotary simulation observation RMSE",
        group: "rotary-rad" as const,
        status: "NotApplicable" as const,
        value: null,
        unit: null,
        thresholdPassed: null,
        reasonCode: "InsufficientRotaryAxisExcitation",
      },
    ],
    claims: [
      {
        claimId: "claim:case-outcome",
        claimDefinitionId: "axiom.core.case-outcome-claim@1",
        metricId: null,
        title: "Canonical run outcome",
        status: "Supported" as const,
        statement: "case.outcome == Passed",
        reasonCode: null,
        reportContentHash: "e".repeat(64),
        evidenceLevel: "Observed" as const,
        evidenceIds: ["sealed-run-report"],
      },
      {
        claimId: "claim:fit",
        claimDefinitionId: "five-axis.physical-model-fit-within-tolerance-claim@1",
        metricId: "five-axis.physical.model-fit-within-tolerance@1",
        title: "Holdout fit within tolerance",
        status: "Supported" as const,
        statement: "five-axis physical holdout fit improves within the declared tolerance",
        reasonCode: null,
        reportContentHash: "e".repeat(64),
        evidenceLevel: "Observed" as const,
        evidenceIds: ["sealed-run-report"],
      },
      {
        claimId: "claim:reality",
        claimDefinitionId: "five-axis.physical-model-reality-validated-claim@1",
        metricId: "five-axis.physical.reality-validated@1",
        title: "Reality validation status",
        status: "Inconclusive" as const,
        statement: "five-axis physical model is validated against real device holdout evidence",
        reasonCode: "SyntheticSILIsNotRealityValidation",
        reportContentHash: "e".repeat(64),
        evidenceLevel: null,
        evidenceIds: ["sealed-run-report"],
      },
    ],
    evidence: [
      {
        evidenceId: "sealed-run-report",
        kind: "validation" as const,
        title: "Canonical evaluation report",
        summary: "Run outcome Passed; execution Succeeded; all metric and claim statuses are projected from this sealed report.",
        contentHash: "e".repeat(64),
      },
      {
        evidenceId: "physical-response-trace",
        kind: "fit" as const,
        title: "Physical response trace",
        summary: "Exact-ZOH replay of the fitted first-order candidate model on the held-out command.",
        contentHash: "c".repeat(64),
      },
      {
        evidenceId: "f4-lineage",
        kind: "validation" as const,
        title: "F4 canonical solver lineage",
        summary: "Calibration uses canonical-dual-table-solver; validation uses canonical-head-table-solver.",
        contentHash: "d".repeat(64),
      },
    ],
  },
};

afterEach(() => vi.unstubAllGlobals());

describe("PhysicalR4Workbench", () => {
  it("渲染 banner、模型合同、分组指标、曲线与证据", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/physical/r4/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/physical/r4/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.includes("/examples/physical-r4")) return Promise.resolve(jsonResponse(example));
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<PhysicalR4Workbench catalog={catalog} />);

    expect(await screen.findByText("MODEL VALIDATION / NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByText("SYNTHETIC SIL / REALITY VALIDATION OPEN")).toBeInTheDocument();
    expect(screen.getAllByText("exact-zoh").length).toBeGreaterThan(0);
    expect(screen.getByText("linear-mm 分组指标")).toBeInTheDocument();
    expect(screen.getByText("rotary-rad 分组指标")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "选定轴的 command / simulation / observation 曲线" })).toBeInTheDocument();
    expect(screen.getByText("Residual Decomposition")).toBeInTheDocument();
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Succeeded").length).toBeGreaterThan(0);
    expect(screen.getByText("Holdout fit within tolerance")).toBeInTheDocument();
    expect(screen.getByText("SyntheticSILIsNotRealityValidation")).toBeInTheDocument();
    expect(screen.getByText("Canonical evaluation report")).toBeInTheDocument();
    expect(screen.getByText("NotApplicable · InsufficientRotaryAxisExcitation")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|控制|应用/i })).not.toBeInTheDocument();
  });

  it("旧 payload 缺少 run 字段时不崩溃", async () => {
    const legacyExample = {
      ...example,
      analysis: {
        ...example.analysis,
        run: undefined,
      },
    };

    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/physical/r4/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/physical/r4/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.includes("/examples/physical-r4")) return Promise.resolve(jsonResponse(legacyExample));
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<PhysicalR4Workbench catalog={catalog} />);

    expect(await screen.findByText("MODEL VALIDATION / NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    expect(screen.getByText("Canonical evaluation report")).toBeInTheDocument();
  });
});
