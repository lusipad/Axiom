import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Catalog } from "../../types";
import { F4Workbench } from "./F4Workbench";
import type {
  F4ExamplePayload,
  F4MathStageManifest,
  F4RunBundle,
  F4ScenarioSummary,
} from "./types";

const hashA = "a".repeat(64);
const hashB = "b".repeat(64);
const hashC = "c".repeat(64);

const catalog: Catalog = {
  subjects: [],
  domainPacks: [{
    domainPackId: "five-axis.domain-pack@5",
    comparisonPolicyIds: [],
    runnerIds: ["five-axis.solver-adapter@1"],
    runtimeBound: true,
  }],
  artifactAdapters: [],
};

const scenarios: F4ScenarioSummary[] = [
  {
    scenarioId: "canonical-dual-table-solver",
    title: "Dual-table Solver",
    description: "Positive dual-table solver gate.",
    topology: "dual-table",
    sutMode: "solver",
    countsTowardClosure: true,
    expectedOutcome: "Passed",
  },
  {
    scenarioId: "canonical-head-table-solver",
    title: "Head-table Solver",
    description: "Positive head-table solver gate.",
    topology: "head-table",
    sutMode: "solver",
    countsTowardClosure: true,
    expectedOutcome: "Passed",
  },
  {
    scenarioId: "canonical-dual-head-solver",
    title: "Dual-head Solver",
    description: "Positive dual-head solver gate.",
    topology: "dual-head",
    sutMode: "solver",
    countsTowardClosure: true,
    expectedOutcome: "Passed",
  },
  {
    scenarioId: "adapter-input-hash-mismatch",
    title: "Adapter Hash Mismatch",
    description: "Negative adapter hash mismatch.",
    topology: "dual-table",
    sutMode: "solver",
    countsTowardClosure: false,
    expectedOutcome: "Passed",
  },
  {
    scenarioId: "interval-interior-collision",
    title: "Interior Collision",
    description: "Negative interval interior collision.",
    topology: "dual-table",
    sutMode: "solver",
    countsTowardClosure: false,
    expectedOutcome: "Passed",
  },
];

const manifest: F4MathStageManifest = {
  manifestId: "five-axis.f4-math-stage-manifest@1",
  schemaId: "five-axis.f4-math-stage-manifest@1",
  schemaVersion: 1,
  stage: "F4",
  artifactDescriptors: [
    { stage: "M0", artifactType: "five-axis.normalized-program", schemaId: "five-axis.normalized-program@1" },
    { stage: "M1", artifactType: "five-axis.m1-reference-path", schemaId: "five-axis.m1-reference-path@1" },
    { stage: "M2", artifactType: "five-axis.m2-candidate-task-geometry", schemaId: "five-axis.m2-candidate-task-geometry@1" },
    { stage: "M3", artifactType: "five-axis.m3-candidate-axis-path", schemaId: "five-axis.m3-candidate-axis-path@1" },
    { stage: "M4", artifactType: "five-axis.m4-continuous-trajectory", schemaId: "five-axis.m4-continuous-trajectory@1" },
    { stage: "M5", artifactType: "five-axis.m5-discrete-command", schemaId: "five-axis.m5-discrete-command@1" },
  ],
  adapterTransport: "in-process",
  capabilityIds: [
    "five-axis.solver-adapter.bound@1",
    "five-axis.reference-sut.cross-validated@1",
    "five-axis.m5-collision.checked@1",
  ],
  fixtureContentIds: [hashA, hashB, hashC],
  policyIds: ["five-axis.reconstruction.polynomial@1"],
  numericEnvironment: { python: "3.14", numpy: "2.1" },
  expectedMetrics: [
    { metricId: "five-axis.adapter-contract-valid@1", expectedStatus: "Computed", expectedValue: true },
  ],
  expectedClaims: [
    { claimId: "five-axis.geometry-valid-claim@1", claimClass: "M2", expectedStatus: "Supported", evidenceLevel: "Validated" },
    { claimId: "five-axis.task-geometry-collision-free-claim@1", claimClass: "M2", expectedStatus: "Supported", evidenceLevel: "Validated" },
    { claimId: "five-axis.kinematically-feasible-claim@1", claimClass: "M3", expectedStatus: "Supported", evidenceLevel: "Validated" },
    { claimId: "five-axis.configuration-collision-free-claim@1", claimClass: "M3", expectedStatus: "Supported", evidenceLevel: "Validated" },
    { claimId: "five-axis.continuously-feasible-claim@1", claimClass: "M4", expectedStatus: "Supported", evidenceLevel: "Certified" },
    { claimId: "five-axis.interval-certified-claim@1", claimClass: "M5", expectedStatus: "Supported", evidenceLevel: "Certified" },
    { claimId: "five-axis.model-collision-free-claim@1", claimClass: "M5", expectedStatus: "Supported", evidenceLevel: "Certified" },
  ],
  expectedEvidence: [
    { evidenceId: "receipt", evidenceKind: "adapter-receipt", required: true },
    { evidenceId: "cross", evidenceKind: "cross-validation", required: true },
  ],
  tolerances: [
    { toleranceId: "gap.position", target: "position", tolerance: { absolute: 1e-12, relative: 0, unit: "axis-unit" } },
  ],
  decisions: [{ decisionId: "f4.acceptance", status: "accepted", rationale: "F4 gate manifest." }],
};

function f4Example(scenarioId: string): F4ExamplePayload {
  const counterexample = scenarioId === "adapter-input-hash-mismatch" || scenarioId === "interval-interior-collision";
  const collisionStatus = scenarioId === "interval-interior-collision" ? "collision" : counterexample ? "unsupported" : "safe";
  const exampleScenario = scenarios.find((item) => item.scenarioId === scenarioId) ?? scenarios[0]!;
  return {
    manifest,
    scenario: exampleScenario,
    source: {
      sourceText: "F4 synthetic source",
      normalizedProgram: { artifactType: "five-axis.normalized-program", schemaVersion: 1, programId: "program.1", sourceSyntaxId: "axiom-cl@1", coordinateContext: { unit: "MM", coordinateFrame: "workpiece" }, events: [] } as never,
      referencePath: { artifactType: "five-axis.m1-reference-path", schemaVersion: 1, referencePathId: "reference.1", coordinateContext: { unit: "MM", coordinateFrame: "workpiece" }, pathProgress: { progressId: "progress.1", schemaVersion: 1, progressParameter: "sigma", unit: "dimensionless", mappings: [] }, positionSemantics: "continuous", positionSegments: [], orientationSegments: [], nodeEvents: [] } as never,
    },
    artifacts: {
      candidateGeometry: { artifactType: "five-axis.m2-candidate-task-geometry", schemaVersion: 1, candidateGeometryId: "candidate.1", sourceReferencePathId: "reference.1", coordinateContext: { unit: "MM", coordinateFrame: "workpiece" }, pathProgress: { progressId: "progress.1", schemaVersion: 1, progressParameter: "sigma", unit: "dimensionless", mappings: [] }, positionSemantics: "continuous", positionSegments: [], orientationSegments: [], nodeEvents: [], tolerances: [], correspondence: {} } as never,
      stockStateGeometries: { "stock.in": { "stock.body": [] } },
      axisPath: { axisPathId: "axis-path.1", machineProfile: { profileId: "machine.1", topology: exampleScenario.topology }, nodeEvents: [] } as never,
      motionConstraintProfile: { artifactType: "five-axis.motion-constraint-profile", schemaId: "five-axis.motion-constraint-profile@1", schemaVersion: 1, profileId: "profile.1", machineProfileId: "machine.1", machineProfileContentId: hashA, axisConstraints: [], startBoundary: { sigmaVelocity: 0, sigmaAcceleration: 0 }, endBoundary: { sigmaVelocity: 0, sigmaAcceleration: 0 }, nodeConstraints: [], policyIds: [], provenance: [] } as never,
      continuousTrajectory: { artifactType: "five-axis.m4-continuous-trajectory", schemaId: "five-axis.m4-continuous-trajectory@1", schemaVersion: 1, trajectoryId: "trajectory.1", sourceAxisPath: {}, sourceAxisPathContentId: hashA, motionConstraintProfile: {}, motionConstraintProfileContentId: hashB, solverId: "solver.1", timingMode: "smoothstep7-feasible", spans: [], verification: { totalDurationSeconds: 1.0 }, provenance: [] } as never,
      collisionModel: { modelId: "collision.1", contentId: hashC, policyId: "collision.policy@1", coverageStatus: "complete", coveredPairKinds: [], entities: [], pairs: [] },
      referenceInvocation: {
        invocationId: `${scenarioId}.reference.invoke`,
        descriptor: { adapterId: "five-axis.f4.reference-adapter", version: "1.0.0", role: "reference", subjectId: "five-axis.reference-solver", subjectVersion: "1.0.0", inputType: "five-axis.m4-continuous-trajectory", outputType: "five-axis.m5-discrete-command", transport: "in-process" },
        inputM4Id: "trajectory.1",
        inputM4ContentHash: hashA,
        policyId: "five-axis.reconstruction.polynomial@1",
        samplePeriod: scenarioId === "interval-interior-collision" ? 0.25 : 0.08,
        finalHold: false,
      },
      sutInvocation: {
        invocationId: `${scenarioId}.sut.invoke`,
        descriptor: { adapterId: "five-axis.f4.sut-adapter", version: "1.0.0", role: "sut", subjectId: "five-axis.sut-solver", subjectVersion: "1.0.0", inputType: "five-axis.m4-continuous-trajectory", outputType: "five-axis.m5-discrete-command", transport: "in-process" },
        inputM4Id: "trajectory.1",
        inputM4ContentHash: counterexample && scenarioId === "adapter-input-hash-mismatch" ? hashB : hashA,
        policyId: "five-axis.reconstruction.polynomial@1",
        samplePeriod: scenarioId === "interval-interior-collision" ? 0.25 : 0.08,
        finalHold: false,
      },
      referenceCommand: counterexample && scenarioId === "adapter-input-hash-mismatch" ? null : { artifactType: "five-axis.m5-discrete-command", schemaId: "five-axis.m5-discrete-command@1", schemaVersion: 1, discreteCommandId: "reference.command", contentId: hashB } as never,
      sutCommand: counterexample && scenarioId === "adapter-input-hash-mismatch" ? null : { artifactType: "five-axis.m5-discrete-command", schemaId: "five-axis.m5-discrete-command@1", schemaVersion: 1, discreteCommandId: "sut.command", contentId: hashC } as never,
    },
    evidence: {
      referenceReceipt: {
        invocation: {} as never,
        descriptor: { adapterId: "five-axis.f4.reference-adapter", version: "1.0.0", role: "reference", subjectId: "five-axis.reference-solver", subjectVersion: "1.0.0", inputType: "five-axis.m4-continuous-trajectory", outputType: "five-axis.m5-discrete-command", transport: "in-process" },
        status: "Succeeded",
        inputContentHash: hashA,
        outputContentHash: counterexample && scenarioId === "adapter-input-hash-mismatch" ? undefined : hashB,
        deterministicWorkUnits: 12,
        numericEnvironment: { python: "3.14", numpy: "2.1" },
      },
      sutReceipt: {
        invocation: {} as never,
        descriptor: { adapterId: "five-axis.f4.sut-adapter", version: "1.0.0", role: "sut", subjectId: "five-axis.sut-solver", subjectVersion: "1.0.0", inputType: "five-axis.m4-continuous-trajectory", outputType: "five-axis.m5-discrete-command", transport: "in-process" },
        status: counterexample && scenarioId === "adapter-input-hash-mismatch" ? "Failed" : "Succeeded",
        inputContentHash: hashA,
        outputContentHash: counterexample && scenarioId === "adapter-input-hash-mismatch" ? undefined : hashC,
        deterministicWorkUnits: 12,
        failureCode: counterexample && scenarioId === "adapter-input-hash-mismatch" ? "InputContentHashMismatch" : undefined,
        failureMessage: counterexample && scenarioId === "adapter-input-hash-mismatch" ? "hash mismatch" : undefined,
        numericEnvironment: { python: "3.14", numpy: "2.1" },
      },
      crossValidation: counterexample && scenarioId === "adapter-input-hash-mismatch" ? null : {
        referenceContentHash: hashB,
        sutContentHash: hashC,
        status: "Supported",
        maxPositionGap: 0,
        maxVelocityGap: 0,
        maxAccelerationGap: 0,
        maxJerkGap: 0,
        tolerances: [],
        evidenceLevel: "Validated",
        method: "five-axis.f4.adapter-cross-validation.polynomial@1",
      },
      collisionVerification: counterexample && scenarioId === "adapter-input-hash-mismatch" ? null : {
        contributesToClaimId: "five-axis.model-collision-free-claim@1",
        commandId: "sut.command",
        commandContentHash: hashC,
        sourceM3Id: "axis-path.1",
        sourceM3ContentHash: hashA,
        collisionModelId: "collision.1",
        collisionModelContentHash: hashC,
        reconstructionPolicyId: "five-axis.reconstruction.polynomial@1",
        status: collisionStatus,
        coverageStatus: "complete",
        supportsModelCollisionAggregation: collisionStatus === "safe",
        evidenceLevel: collisionStatus === "collision" ? "Observed" : "Certified",
        method: "five-axis.f4.m5-polynomial-collision-envelope@1",
        intervalEvaluations: [
          { intervalId: "interval.0", tStart: 0, tEnd: 0.25, status: "safe", minimumClearanceLowerBound: 0.1 },
          { intervalId: "interval.1", tStart: 0.25, tEnd: 0.5, status: collisionStatus, witnessTime: collisionStatus === "collision" ? 0.375 : undefined, minimumClearanceLowerBound: collisionStatus === "collision" ? undefined : 0.1 },
        ],
      },
      scenarioResult: {
        scenarioId,
        topology: exampleScenario.topology,
        sutMode: "solver",
        countsTowardClosure: exampleScenario.countsTowardClosure,
        outcome: "Passed",
        referenceReceiptStatus: "Succeeded",
        sutReceiptStatus: counterexample && scenarioId === "adapter-input-hash-mismatch" ? "Failed" : "Succeeded",
        crossValidationStatus: counterexample && scenarioId === "adapter-input-hash-mismatch" ? "Inconclusive" : "Supported",
        collisionStatus,
      },
    },
    acceptanceReport: {
      reportId: "five-axis.f4.acceptance-report.v1",
      stage: "F4",
      scenarioResults: [],
      topologyCoverage: [
        { topology: "dual-table", covered: true },
        { topology: "head-table", covered: true },
        { topology: "dual-head", covered: true },
      ],
      counterexampleCoverage: [
        { counterexampleId: "counterexample.adapter-input-hash-mismatch", covered: true },
        { counterexampleId: "counterexample.interval-interior-collision", covered: true },
      ],
      gateClaimStatuses: [
        { claimId: "five-axis.geometry-valid-claim@1", status: "Supported", evidenceLevel: "Validated" },
        { claimId: "five-axis.task-geometry-collision-free-claim@1", status: "Supported", evidenceLevel: "Validated" },
        { claimId: "five-axis.kinematically-feasible-claim@1", status: "Supported", evidenceLevel: "Validated" },
        { claimId: "five-axis.configuration-collision-free-claim@1", status: "Supported", evidenceLevel: "Validated" },
        { claimId: "five-axis.continuously-feasible-claim@1", status: "Supported", evidenceLevel: "Certified" },
        { claimId: "five-axis.interval-certified-claim@1", status: "Supported", evidenceLevel: "Certified" },
        { claimId: "five-axis.model-collision-free-claim@1", status: "Supported", evidenceLevel: "Certified" },
      ],
      status: "Passed",
      contentHash: hashA,
    },
    runSpec: counterexample ? null : {
      subjectId: `five-axis.f4.scenario.${scenarioId}@1`,
      domainPackId: "five-axis.domain-pack@5",
      runnerId: "five-axis.solver-adapter@1",
      evaluatorVersion: "five-axis-f4-evaluator@1",
      request: { scenarioId },
    },
  };
}

function f4RunBundle(scenarioId: string): F4RunBundle {
  return {
    run: {
      runId: `run-${scenarioId}`,
      subjectId: `five-axis.f4.scenario.${scenarioId}@1`,
      domainPackId: "five-axis.domain-pack@5",
      runnerId: "five-axis.solver-adapter@1",
      runSpecHash: `spec-${scenarioId}`,
      reportContentHash: `report-${scenarioId}`,
      executionStatus: "Succeeded",
      caseOutcome: "Passed",
      evaluatorVersion: "five-axis-f4-evaluator@1",
      contentHash: `content-${scenarioId}`,
    },
    report: {
      executionStatus: "Succeeded",
      caseOutcome: "Passed",
      metricResults: [],
    },
    claims: [
      "five-axis.geometry-valid-claim@1",
      "five-axis.task-geometry-collision-free-claim@1",
      "five-axis.kinematically-feasible-claim@1",
      "five-axis.configuration-collision-free-claim@1",
      "five-axis.continuously-feasible-claim@1",
      "five-axis.interval-certified-claim@1",
      "five-axis.model-collision-free-claim@1",
    ].map((claimId) => ({
      claimDefinitionId: claimId,
      status: "Supported",
      predicate: `${claimId} is true`,
      evidence: { level: "Certified", method: "f4-runtime" },
    })),
    bundleHash: `bundle-${scenarioId}`,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("Five-Axis F4 workbench", () => {
  it("展示 stage acceptance、gap、collision，并执行正向 F4 门禁", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/five-axis/f4/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/five-axis/f4/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.includes("/examples/five-axis-f4")) {
        const scenarioId = new URL(url, "http://test").searchParams.get("scenarioId") ?? "canonical-dual-table-solver";
        return Promise.resolve(jsonResponse(f4Example(scenarioId)));
      }
      if (url.endsWith("/runs/evaluate")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { request?: { scenarioId?: string } };
        return Promise.resolve(jsonResponse(f4RunBundle(body.request?.scenarioId ?? "canonical-dual-table-solver")));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<F4Workbench catalog={catalog} />);

    expect(await screen.findByText("F4 门禁工作台")).toBeInTheDocument();
    expect(screen.getByText("StageAcceptance")).toBeInTheDocument();
    expect(screen.getByText("position gap")).toBeInTheDocument();
    expect(screen.getByText("M5 Collision")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dual-table Solver" })).toBeInTheDocument();
    expect(screen.getAllByText("dual-table").length).toBeGreaterThan(0);
    expect(screen.getAllByText("counterexample.adapter-input-hash-mismatch").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "执行 F4 门禁" }));

    await waitFor(() => expect(screen.getByText("7/7")).toBeInTheDocument());
    expect(screen.getAllByText("five-axis.model-collision-free-claim@1 is true")).toHaveLength(2);
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/runs/evaluate"))).toBe(true);
    expect(screen.queryByText("0/7")).not.toBeInTheDocument();
  });

  it("反例场景禁用运行按钮并明确不计入闭环", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/five-axis/f4/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/five-axis/f4/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.includes("/examples/five-axis-f4")) {
        const scenarioId = new URL(url, "http://test").searchParams.get("scenarioId") ?? "canonical-dual-table-solver";
        return Promise.resolve(jsonResponse(f4Example(scenarioId)));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<F4Workbench catalog={catalog} />);

    expect(await screen.findByText("F4 门禁工作台")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("场景"), { target: { value: "adapter-input-hash-mismatch" } });

    expect(await screen.findByText("只验证失败行为，不计入闭环。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "执行 F4 门禁" })).toBeDisabled();
    expect(screen.getByText("Counterexample only")).toBeInTheDocument();
  });

  it("执行失败时清空旧 bundle 并展示 API 错误", async () => {
    let runCount = 0;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/five-axis/f4/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/five-axis/f4/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.includes("/examples/five-axis-f4")) return Promise.resolve(jsonResponse(f4Example("canonical-dual-table-solver")));
      if (url.endsWith("/runs/evaluate")) {
        runCount += 1;
        if (runCount === 1) return Promise.resolve(jsonResponse(f4RunBundle("canonical-dual-table-solver")));
        return Promise.resolve(jsonResponse({ detail: "runner unavailable" }, 503));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<F4Workbench catalog={catalog} />);

    expect(await screen.findByText("F4 门禁工作台")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "执行 F4 门禁" }));
    expect(await screen.findByText("7/7")).toBeInTheDocument();
    expect(screen.getAllByText("five-axis.model-collision-free-claim@1 is true")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "执行 F4 门禁" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
    expect(screen.queryAllByText("five-axis.model-collision-free-claim@1 is true")).toHaveLength(0);
  });
});
