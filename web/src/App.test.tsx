import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { F1ExamplePayload, F1MathStageManifest, F1RunBundle, F1ScenarioSummary } from "./features/five-axis-f1/types";
import type { Catalog, ExperimentReport, ExperimentSpec, RunBundle } from "./types";

const pointExample: ExperimentSpec = {
  experimentId: "cnc-contour-true-ab@1",
  sharedInput: {
    artifactType: "ordered-point-sequence",
    schemaVersion: 1,
    points: [[0, 0], [10, 0], [20, 0]],
    semantics: { unit: "mm", coordinateFrame: "G54-workpiece", closed: false },
  },
  parameterSet: {
    parameterSetId: "finish-pass-offset@1",
    parameterSchemaId: "ordered-point.offset-error-parameters@1",
    schemaVersion: 1,
    values: { errorVector: [0, 0.08], compensationGain: 0.75 },
    units: { errorVector: "mm", compensationGain: "ratio" },
  },
  arms: [
    { armId: "baseline", subjectId: "ordered-point.offset-baseline", subjectVersion: "1" },
    { armId: "candidate", subjectId: "ordered-point.offset-compensated", subjectVersion: "1" },
  ],
  evaluation: {
    case: {
      caseId: "contour@1",
      requiredMetrics: [
        "paired.euclidean.rms",
        { metricId: "paired.euclidean.max", threshold: { operator: "<=", value: 0.03, unit: "mm" } },
      ],
    },
  },
};

const catalog: Catalog = {
  subjects: [
    { subjectId: "ordered-point.offset-baseline", subjectVersion: "1", displayName: "Offset baseline", description: "", runnerId: "python-call@1", parameterSchemaId: "offset@1" },
    { subjectId: "ordered-point.offset-compensated", subjectVersion: "1", displayName: "Offset compensated", description: "", runnerId: "python-call@1", parameterSchemaId: "offset@1" },
  ],
  domainPacks: [
    { domainPackId: "ordered-point.domain-pack@1", comparisonPolicyIds: [], runnerIds: [], runtimeBound: true },
    { domainPackId: "five-axis.domain-pack@2", comparisonPolicyIds: [], runnerIds: ["artifact-import@1"], runtimeBound: true },
    { domainPackId: "machine-observation.domain-pack@1", comparisonPolicyIds: [], runnerIds: ["machine-trace-import@1"], runtimeBound: true },
    { domainPackId: "five-axis.domain-pack@6", comparisonPolicyIds: [], runnerIds: ["windows-file-import@1"], runtimeBound: true },
    { domainPackId: "intelligence.domain-pack@2", comparisonPolicyIds: [], runnerIds: ["intelligence-real-holdout-validation@1"], runtimeBound: true },
  ],
  artifactAdapters: [],
};

function pointRunBundle(subjectId: string, value: number, passed: boolean): RunBundle {
  return {
    observation: {
      artifact: { ...pointExample.sharedInput, points: pointExample.sharedInput.points.map(([x]) => [x, value]) },
      artifactHash: `artifact-${subjectId}`,
      source: "ExecutedSubject",
    },
    report: {
      executionStatus: "Succeeded",
      caseOutcome: passed ? "Passed" : "Failed",
      metricResults: [{ metricId: "paired.euclidean.max", status: "Computed", value, unit: "mm", thresholdPassed: passed }],
    },
    run: {
      runId: `run-${subjectId}`,
      subjectId,
      domainPackId: "ordered-point.domain-pack@1",
      runnerId: "python-call@1",
      runSpecHash: `spec-${subjectId}`,
      reportContentHash: `report-${subjectId}`,
      caseOutcome: passed ? "Passed" : "Failed",
      executionStatus: "Succeeded",
      contentHash: `content-${subjectId}`,
    },
    claims: [{
      claimDefinitionId: `claim-${subjectId}`,
      status: passed ? "Accepted" : "Rejected",
      predicate: "paired.euclidean.max <= 0.03 mm",
      metricId: "paired.euclidean.max",
      evidence: { level: "Exact", method: "index-paired" },
    }],
    bundleHash: `bundle-${subjectId}`,
  };
}

const pointReport: ExperimentReport = {
  experimentSpec: pointExample,
  experimentSpecHash: "exp-hash-123456789",
  sharedInputHash: "input-hash-123456789",
  parameterSetHash: "parameters-hash-123456789",
  executionStatus: "Succeeded",
  caseOutcome: "Failed",
  armResults: [
    {
      armId: "baseline",
      subjectId: "ordered-point.offset-baseline",
      subjectVersion: "1",
      executionStatus: "Succeeded",
      caseOutcome: "Failed",
      outputArtifactHash: "artifact-baseline",
      runBundle: pointRunBundle("ordered-point.offset-baseline", 0.08, false),
    },
    {
      armId: "candidate",
      subjectId: "ordered-point.offset-compensated",
      subjectVersion: "1",
      executionStatus: "Succeeded",
      caseOutcome: "Passed",
      outputArtifactHash: "artifact-candidate",
      runBundle: pointRunBundle("ordered-point.offset-compensated", 0.02, true),
    },
  ],
  comparison: {
    comparisonId: "cmp",
    policyId: "ordered-point.experiment-comparison.strict@1",
    compatibility: { compatible: true, issues: [] },
    metricComparisons: [{ metricId: "paired.euclidean.max", left: 0.08, right: 0.02, unit: "mm", comparable: true, delta: -0.06, preferredSubjectId: "ordered-point.offset-compensated" }],
    contentHash: "cmp-hash",
  },
  failures: [],
  contentHash: "bundle-hash-123456789",
};

const f1Manifest: F1MathStageManifest = {
  manifestId: "five-axis.f1-math-stage-manifest@1",
  schemaId: "five-axis.f1-math-stage-manifest@1",
  schemaVersion: 1,
  stage: "F1",
  artifactDescriptors: [
    { stage: "M0", artifactType: "five-axis.normalized-program", schemaId: "five-axis.normalized-program@1" },
    { stage: "M1", artifactType: "five-axis.m1-reference-path", schemaId: "five-axis.m1-reference-path@1" },
    { stage: "M2", artifactType: "five-axis.m2-candidate-task-geometry", schemaId: "five-axis.m2-candidate-task-geometry@1" },
  ],
  capabilityIds: ["five-axis.continuous-error.bound@1", "five-axis.task-geometry.collision.checked@1"],
  fixtureContentIds: ["fixture-content-1234567890"],
  policyIds: ["five-axis.correspondence.provenance-progress@1"],
  numericEnvironment: { python: "3.14", pydantic: "2.13" },
  expectedMetrics: [
    { metricId: "five-axis.geometry.valid@1", expectedStatus: "Computed", expectedValue: true },
    { metricId: "five-axis.task-geometry.collision-free@1", expectedStatus: "Computed", expectedValue: true },
  ],
  expectedClaims: [
    { claimId: "five-axis.geometry-valid-claim@1", claimClass: "M2", expectedStatus: "Supported", evidenceLevel: "Exact" },
    { claimId: "five-axis.task-geometry-collision-free-claim@1", claimClass: "M2", expectedStatus: "Supported", evidenceLevel: "Certified" },
  ],
  expectedEvidence: [{ evidenceId: "lineage", evidenceKind: "lineage", required: true }],
  tolerances: [
    { toleranceId: "tol.position", target: "position", tolerance: { absolute: 0.001, relative: 0, unit: "MM" } },
  ],
  decisions: [{ decisionId: "f1.acceptance", status: "accepted", rationale: "M0–M2 math-only acceptance." }],
};

const f1Summaries: F1ScenarioSummary[] = [
  {
    scenarioId: "nominal-certified",
    title: "Nominal Certified",
    description: "Identity candidate with allowed cutter-stock removal and no forbidden contact.",
    expectedClaimStatusById: {
      "five-axis.geometry-valid-claim@1": "Supported",
      "five-axis.task-geometry-collision-free-claim@1": "Supported",
    },
  },
  {
    scenarioId: "fixture-collision",
    title: "Fixture Collision",
    description: "Holder contact refutes the task-geometry collision-free claim.",
    expectedClaimStatusById: {
      "five-axis.geometry-valid-claim@1": "Supported",
      "five-axis.task-geometry-collision-free-claim@1": "Refuted",
    },
  },
];

function f1Example(scenarioId = "nominal-certified"): F1ExamplePayload {
  const coordinateContext = { unit: "MM", coordinateFrame: "workpiece" };
  const pathProgress = {
    progressId: "f1.progress",
    schemaVersion: 1,
    progressParameter: "sigma" as const,
    unit: "dimensionless" as const,
    mappings: [{
      mappingId: "mapping.1",
      sourceSegmentId: "segment.1",
      sourceLocalStart: 0,
      sourceLocalEnd: 1,
      sigmaStart: 0,
      sigmaEnd: 1,
      degenerateKind: "none",
    }],
  };
  const lineage = { statementId: "statement.1", statementIndex: 0, line: 1, column: 1, sourceText: "FROM/-0.8,0,0,0,0,1" };
  const positionSegments = [{ segmentId: "segment.1", segmentType: "line" as const, sigmaStart: 0, sigmaEnd: 1, startPoint: [-0.8, 0, 0] as [number, number, number], endPoint: [0.8, 0, 0] as [number, number, number] }];
  const orientationSegments = [{ segmentId: "axis.1", segmentType: "constant" as const, sigmaStart: 0, sigmaEnd: 1, axis: [0, 0, 1] as [number, number, number] }];
  const summary = f1Summaries.find((item) => item.scenarioId === scenarioId) ?? f1Summaries[0]!;
  const scenarioManifest: F1MathStageManifest = {
    ...f1Manifest,
    fixtureContentIds: [`fixture-${scenarioId}`],
    expectedClaims: f1Manifest.expectedClaims.map((item) => ({
      ...item,
      expectedStatus: summary.expectedClaimStatusById[item.claimId] ?? item.expectedStatus,
    })),
  };
  const candidateGeometry = {
    artifactType: "five-axis.m2-candidate-task-geometry" as const,
    schemaVersion: 1,
    candidateGeometryId: `candidate.${scenarioId}`,
    sourceReferencePathId: "reference.1",
    sourceReferencePathContentId: "reference-content-1234567890",
    coordinateContext,
    pathProgress,
    positionSemantics: "continuous" as const,
    positionSegments,
    orientationSegments,
    nodeEvents: [],
    regularityCertificate: { certificateId: "regularity.1", requestedClass: "C1", segmentEvidence: [], nodeEvidence: [] },
    tolerances: f1Manifest.tolerances,
    correspondence: {
      certificateId: "correspondence.1",
      sourceGeometryId: `candidate.${scenarioId}`,
      targetReferencePathId: "reference.1",
      policy: {
        strategyId: "five-axis.correspondence.provenance-progress@1",
        allowedSourceInterval: [0, 1] as [number, number],
        allowedTargetInterval: [0, 1] as [number, number],
      },
      canonicalNodes: [],
      allowedSourceIntervals: [{ sourceSegmentId: "segment.1", allowedTargetIntervals: [[0, 1] as [number, number]] }],
      selectedNodeMapping: [],
      intervals: [{ intervalId: "corr.1", sourceSigmaStart: 0, sourceSigmaEnd: 1, targetSigmaStart: 0, targetSigmaEnd: 1, sourceSegmentId: "segment.1", targetSegmentId: "segment.1" }],
      primaryObjectiveLower: 0,
      primaryObjectiveUpper: 0,
      objectiveDomain: "continuous" as const,
      tieBreakObjective: "lowest-source-segment-id",
      solverVersion: "analytic-identity@1",
      evidenceLevel: "machine-replayable" as const,
    },
    collisionContext: {
      contextId: "collision.1",
      toolComponents: [{ componentId: "tool.cutter", componentKind: "cutter" as const, shapeType: "sphere" as const, radius: 0.1, axisStartOffset: 0, axisEndOffset: 0 }],
      stockFixtures: [
        { stockFixtureId: "stock.body", category: "stock" as const, aabb: { minCorner: [-0.4, -0.4, -0.2] as [number, number, number], maxCorner: [0.4, 0.4, 0.2] as [number, number, number] } },
        { stockFixtureId: "fixture.body", category: "fixture" as const, aabb: { minCorner: [2, 2, 0] as [number, number, number], maxCorner: [2.3, 2.3, 0.5] as [number, number, number] } },
      ],
      allowedRemoval: [],
      contactPolicy: { policyId: "five-axis.contact-policy.explicit@1", defaultPolicy: "forbidden", rules: [{ ruleId: "cutter-stock", leftCategory: "cutter", rightCategory: "stock", contactPolicy: "allowed" as const }] },
    },
    processStateTimeline: {
      timelineId: "timeline.1",
      stockUpdatePolicy: { policyId: "five-axis.stock-update.explicit-snapshot@1" },
      failureStateSemantics: { policyId: "five-axis.process-state.failure-terminal@1", failedStateMeaning: "last-input-state-persists" },
      intervals: [{ intervalId: "interval.1", sigmaStart: 0, sigmaEnd: 1, motionMode: "cut", spindleState: "cw", toolComponentId: "tool.cutter", coolantOn: false, inputStockState: { stateId: "stock.in", contentId: "stock-content-in-1234567890" }, outputStockState: { stateId: "stock.out", contentId: "stock-content-out-1234567890" } }],
    },
  };
  return {
    manifest: scenarioManifest,
    scenario: summary,
    source: {
      sourceText: "UNITS/MM\nFROM/-0.8,0,0,0,0,1\nGOTO/0.8,0,0\nEND\n",
      normalizedProgram: {
        artifactType: "five-axis.normalized-program",
        schemaVersion: 1,
        programId: "program.1",
        sourceSyntaxId: "axiom-cl-subset@1",
        coordinateContext,
        events: [
          { eventId: "event.1", eventType: "FROM", lineage, position: [-0.8, 0, 0], toolAxis: [0, 0, 1], toolAxisSource: "explicit" },
          { eventId: "event.2", eventType: "GOTO", lineage: { ...lineage, statementId: "statement.2", statementIndex: 1, line: 2, sourceText: "GOTO/0.8,0,0" }, position: [0.8, 0, 0], toolAxis: [0, 0, 1], toolAxisSource: "modal-inherited" },
        ],
      },
      referencePath: {
        artifactType: "five-axis.m1-reference-path",
        schemaVersion: 1,
        referencePathId: "reference.1",
        coordinateContext,
        pathProgress,
        positionSemantics: "continuous",
        positionSegments,
        orientationSegments,
        nodeEvents: [],
        regularityCertificate: { certificateId: "regularity.reference", requestedClass: "C1", segmentEvidence: [], nodeEvidence: [] },
      },
    },
    artifacts: { candidateGeometry, stockStateGeometries: {} },
    runSpec: {
      subjectId: `five-axis.f1.scenario.${scenarioId}@1`,
      domainPackId: "five-axis.domain-pack@2",
      runnerId: "artifact-import@1",
      evaluatorVersion: "five-axis-f1-evaluator@1",
      request: { artifact: candidateGeometry, case: { caseId: scenarioId } },
    },
  };
}

function f1Run(scenarioId = "nominal-certified"): F1RunBundle {
  const collisionFree = scenarioId !== "fixture-collision";
  const metrics = [
    { metricId: "five-axis.geometry.valid@1", status: "Computed", value: true, evidence: { level: "Exact", method: "five-axis.f1.geometry-tolerance-gate@1" } },
    { metricId: "five-axis.task-geometry.collision-free@1", status: "Computed", value: collisionFree, reasonCode: collisionFree ? "CollisionCertified" : "ForbiddenContact", evidence: { level: collisionFree ? "Certified" : "Observed", method: "continuous-envelope-recursive" } },
    { metricId: "five-axis.position.max-error@1", status: "Computed", value: 0, unit: "MM", evidence: { level: "Exact", method: "analytic-identity" } },
    { metricId: "five-axis.orientation.max-error@1", status: "Computed", value: 0, unit: "rad", evidence: { level: "Exact", method: "analytic-identity" } },
    { metricId: "five-axis.task-geometry.overcut-free@1", status: "Computed", value: true, evidence: { level: "Certified", method: "continuous-envelope-recursive" } },
    { metricId: "five-axis.task-geometry.minimum-clearance@1", status: "Computed", value: collisionFree ? 0.2 : 0, unit: "MM", evidence: { level: collisionFree ? "Certified" : "Observed", method: "continuous-envelope-recursive" } },
  ];
  return {
    run: {
      runId: `run-${scenarioId}`,
      subjectId: `five-axis.f1.scenario.${scenarioId}@1`,
      domainPackId: "five-axis.domain-pack@2",
      runnerId: "artifact-import@1",
      runSpecHash: `spec-${scenarioId}`,
      reportContentHash: `report-${scenarioId}`,
      executionStatus: "Succeeded",
      caseOutcome: collisionFree ? "Passed" : "Failed",
      evaluatorVersion: "five-axis-f1-evaluator@1",
      contentHash: `run-content-${scenarioId}`,
    },
    report: { executionStatus: "Succeeded", caseOutcome: collisionFree ? "Passed" : "Failed", metricResults: metrics },
    claims: [
      { claimDefinitionId: `geometry-${scenarioId}`, status: "Supported", predicate: "five-axis.GeometryValid is true", metricId: "five-axis.geometry.valid@1", evidence: { level: "Exact", method: "five-axis.f1.geometry-tolerance-gate@1" } },
      { claimDefinitionId: `collision-${scenarioId}`, status: collisionFree ? "Supported" : "Refuted", predicate: `five-axis.TaskGeometryCollisionFree is ${collisionFree}`, metricId: "five-axis.task-geometry.collision-free@1", evidence: { level: collisionFree ? "Certified" : "Observed", method: "continuous-envelope-recursive" } },
    ],
    bundleHash: `bundle-${scenarioId}`,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("Axiom workbench", () => {
  it("加载 Point Lab 并允许重新运行实验", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /共享输入与两个 Subject 输出/ })).toBeInTheDocument();
    expect(screen.getByText("Strict compatible")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("补偿增益"), { target: { value: "0.5" } });
    fireEvent.click(screen.getByRole("button", { name: "运行实验" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const lastCall = fetchMock.mock.calls.at(-1);
    const submitted = JSON.parse(String(lastCall?.[1]?.body)) as ExperimentSpec;
    expect(submitted.parameterSet.values.compensationGain).toBe(0.5);
  });

  it("展示初始化 API 失败，而不伪造证据", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      return Promise.resolve(jsonResponse({ detail: "runner unavailable" }, 503));
    }));

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
    expect(screen.queryByText("证据包已封存")).not.toBeInTheDocument();
  });

  it("Five-Axis 入口失败时仍保持 Point Lab 可用", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.includes("/five-axis/f1/")) return Promise.resolve(jsonResponse({ detail: "F1 unavailable" }, 503));
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Five-Axis.*F1/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
  });

  it("Five-Axis F4 入口失败时仍保留导航并显示 API 错误", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.includes("/five-axis/f4/")) return Promise.resolve(jsonResponse({ detail: "F4 unavailable" }, 503));
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Five-Axis.*F4/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
    expect(screen.getByRole("button", { name: /Five-Axis.*F4/i })).toBeInTheDocument();
  });

  it("Physical R4 入口失败时仍保留导航并显示 API 错误", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.includes("/physical/r4/") || url.includes("/examples/physical-r4")) {
        return Promise.resolve(jsonResponse({ detail: "R4 unavailable" }, 503));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Physical.*R4/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
    expect(screen.getByRole("button", { name: /Physical.*R4/i })).toBeInTheDocument();
  });

  it("R7-A 顶栏保持 Shadow 权限和无设备授权边界", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.includes("/control/r7/") || url.includes("/examples/control-r7")) {
        return Promise.resolve(jsonResponse({ detail: "R7 unavailable" }, 503));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Controlled.*R7-A/i }));

    expect(screen.getByText("SHADOW ONLY · NO DEVICE AUTHORITY · DEPLOYMENT OPEN")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
  });

  it("R7-B 顶栏保持就绪性、厂商未选择和禁止设备写入边界", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.includes("/control/r7b/") || url.includes("/examples/control-r7b")) {
        return Promise.resolve(jsonResponse({ detail: "R7-B unavailable" }, 503));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Deployment.*R7-B/i }));

    expect(screen.getByText("READINESS ONLY · VENDOR UNSELECTED · NO DEVICE WRITE · REALITY OPEN")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
    expect(screen.queryByRole("button", { name: /启动|复位|写入参数|下发|急停|连接机床/i })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/control/r7b/manifest"))).toBe(true);
  });

  it("R5-B 入口保持 Windows 真实 holdout 边界且不暴露设备控制", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.includes("/intelligence/r5b/") || url.includes("/examples/intelligence-r5b")) {
        return Promise.resolve(jsonResponse({ detail: "R5-B unavailable" }, 503));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Intelligence.*R5-B/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
    expect(screen.getByText("REAL HOLDOUT VALIDATION · REAL GENERALIZATION OPEN · NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Intelligence.*R5-B/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|控制设备|在线学习|自动部署/i })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/intelligence/r5b/manifest"))).toBe(true);
  });

  it("Machine R3 入口展示只读边界而不暴露写入控件", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.endsWith("/machine/r3/manifest")) {
        return Promise.resolve(jsonResponse({
          manifestId: "machine.r3-manifest@1",
          schemaId: "machine.r3-manifest@1",
          schemaVersion: 1,
          stage: "R3",
          readOnly: true,
          safetyBanner: "READ ONLY / NOT DEVICE SAFE",
          suiteId: "machine-r3-fixtures@1",
          artifactDescriptors: [{ artifactType: "machine.telemetry-trace", schemaVersion: 1, role: "run-input" }],
          capabilityIds: ["machine-observation.trace.raw@1"],
          claimDefinitionIds: ["machine-observation.read-only-capture-claim@1"],
          forbiddenClaims: ["DeviceSafe", "ProcessSafe", "safe-to-run"],
          cases: [{
            id: "read-only-paired-pass",
            title: "只读配对基线导入",
            description: "冻结 F4 基线、命令身份和七项上游 claim 的只读历史导入。",
            expectedExecutionStatus: "Succeeded",
            expectedCaseOutcome: "Passed",
          }],
        }));
      }
      if (url.endsWith("/machine/r3/scenarios")) {
        return Promise.resolve(jsonResponse([{
          scenarioId: "read-only-paired-pass",
          title: "只读配对基线导入",
          description: "冻结 F4 基线、命令身份和七项上游 claim 的只读历史导入。",
          expectedExecutionStatus: "Succeeded",
          expectedCaseOutcome: "Passed",
        }]));
      }
      if (url.includes("/examples/machine-r3")) {
        return Promise.resolve(jsonResponse({
          manifest: {
            manifestId: "machine.r3-manifest@1",
            schemaId: "machine.r3-manifest@1",
            schemaVersion: 1,
            stage: "R3",
            readOnly: true,
            safetyBanner: "READ ONLY / NOT DEVICE SAFE",
            suiteId: "machine-r3-fixtures@1",
            artifactDescriptors: [{ artifactType: "machine.telemetry-trace", schemaVersion: 1, role: "run-input" }],
            capabilityIds: ["machine-observation.trace.raw@1"],
            claimDefinitionIds: ["machine-observation.read-only-capture-claim@1"],
            forbiddenClaims: ["DeviceSafe", "ProcessSafe", "safe-to-run"],
            cases: [],
          },
          scenario: {
            scenarioId: "read-only-paired-pass",
            title: "只读配对基线导入",
            description: "冻结 F4 基线、命令身份和七项上游 claim 的只读历史导入。",
            expectedExecutionStatus: "Succeeded",
            expectedCaseOutcome: "Passed",
          },
          artifact: {
            artifactType: "machine.telemetry-trace",
            schemaVersion: 1,
            traceId: "trace:read-only-paired-pass",
            sourceKind: "synthetic-replay",
            captureReceipt: {
              receiptId: "receipt:read-only-paired-pass",
              sourceId: "axiom.windows-file-telemetry-source@1",
              operation: "file-import",
              transport: "windows-file-json",
              capturedAt: "2026-08-11T09:30:00Z",
              traceContentHash: "24c7f3c433b76765db97f31ae2ceb38bb1d54234b5e0a2d4ad88f551724cb9f6",
            },
            deviceIdentity: { deviceId: "sim-840d", controllerFamily: "siemens-840d", machineModel: "vmc-5x-sim" },
            vendorMetadata: { programName: "DEMO_5X_R3", channel: "CHANNEL_1" },
            frames: [{
              sequenceId: 100,
              deviceTimestamp: "2026-08-11T09:29:58.000Z",
              samples: [
                { channelId: "pos.work", value: [0, 0, 5], unit: "mm" },
                { channelId: "feed.actual", value: 1200, unit: "mm/min" },
              ],
              alarms: [],
            }],
          },
          deviceProfile: {
            profileId: "device-profile.sim-840d@1",
            deviceId: "sim-840d",
            controllerFamily: "siemens-840d",
            manufacturer: "Siemens",
            machineModel: "vmc-5x-sim",
            exportVersion: "sinumerik-export@1.4",
            allowedReadOnlyOperations: ["file-import"],
            firmwareVersion: "840D-sl-6.15",
            calibrationId: "calibration.sim-840d@1",
            channels: [
              { channelId: "pos.work", kind: "position-vector", unit: "mm", coordinateFrame: "workpiece" },
              { channelId: "feed.actual", kind: "scalar", unit: "mm/min" },
            ],
          },
          clockMapping: {
            mappingId: "clock-map.sim-840d@1",
            deviceId: "sim-840d",
            mappingMethod: "synchronized-export",
            deviceReferenceTimestamp: "2026-08-11T09:29:58.000Z",
            hostReferenceTimestamp: "2026-08-11T17:29:58.010Z",
            offsetMilliseconds: 10,
            driftBoundMilliseconds: 2,
          },
          coordinateAlignment: {
            alignmentId: "alignment.sim-840d@1",
            deviceId: "sim-840d",
            sourceKind: "calibration-record",
            effectiveAt: "2026-08-11T08:45:00Z",
            machineCoordinateFrame: "machine",
            workCoordinateFrame: "workpiece",
            calibrationStatus: "calibrated",
            calibrationId: "calibration.sim-840d@1",
            channelIds: ["pos.work"],
          },
          lineage: {
            machineRunId: "machine-run:paired-pass",
            pairingStatus: "paired",
            baselineKind: "reference",
            baselineRunBundleHash: "beec29557d6bf8c22363616c65a73f4394e484c9b516478898e9c4039bc44d79",
            sourceCommandContentHash: "085ab2047f6089fb3fa681c7a83ee3aa63c9d379b55529bbbabbd0411874d218",
            upstreamClaims: [
              { claimDefinitionId: "five-axis.geometry-valid-claim@1", status: "Supported" },
              { claimDefinitionId: "five-axis.task-geometry-collision-free-claim@1", status: "Supported" },
              { claimDefinitionId: "five-axis.kinematically-feasible-claim@1", status: "Supported" },
              { claimDefinitionId: "five-axis.configuration-collision-free-claim@1", status: "Supported" },
              { claimDefinitionId: "five-axis.continuously-feasible-claim@1", status: "Supported" },
              { claimDefinitionId: "five-axis.interval-certified-claim@1", status: "Supported" },
              { claimDefinitionId: "five-axis.model-collision-free-claim@1", status: "Supported" },
            ],
          },
          runSpec: {
            subjectId: "machine-r3-sim@paired",
            domainPackId: "machine-observation.domain-pack@1",
            runnerId: "machine-trace-import@1",
            evaluatorVersion: "machine-observation-evaluator@1",
            request: { artifact: { artifactType: "machine.telemetry-trace" }, case: { caseId: "read-only-paired-pass" } },
          },
        }));
      }
      if (url.endsWith("/runs/evaluate")) {
        return Promise.resolve(jsonResponse({
          run: {
            runId: "run.machine-r3",
            subjectId: "machine-r3-sim@paired",
            domainPackId: "machine-observation.domain-pack@1",
            runnerId: "machine-trace-import@1",
            runSpecHash: "spec-hash",
            reportContentHash: "report-hash",
            executionStatus: "Succeeded",
            caseOutcome: "Passed",
            evaluatorVersion: "machine-observation-evaluator@1",
            contentHash: "content-hash",
          },
          observation: { artifact: { artifactType: "machine.telemetry-trace" }, artifactHash: "artifact-hash", source: "ImportedArtifact" },
          report: {
            executionStatus: "Succeeded",
            caseOutcome: "Passed",
            metricResults: [
              { metricId: "machine-observation.clock-aligned@1", status: "Computed", value: true, evidence: { level: "Observed", method: "clock-audit" } },
              { metricId: "machine-observation.coordinate-context@1", status: "Computed", value: true, evidence: { level: "Observed", method: "alignment-audit" } },
            ],
            provenance: {
              contextHashes: {
                trace: "24c7f3c433b76765db97f31ae2ceb38bb1d54234b5e0a2d4ad88f551724cb9f6",
              },
            },
          },
          claims: [{ claimDefinitionId: "machine-observation.read-only-capture-claim@1", status: "Supported", predicate: "capture is read-only", evidence: { level: "Observed", method: "receipt-check" } }],
          bundleHash: "bundle-hash",
        }));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Machine.*R3/i }));
    expect(await screen.findByText("READ ONLY / NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByText("READ ONLY · NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入观测并评估" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|启动|下发/i })).not.toBeInTheDocument();
  });

  it("Physical R4 入口展示模型验证边界与开放现实验证状态", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.endsWith("/physical/r4/manifest")) {
        return Promise.resolve(jsonResponse({
          manifestId: "physical.r4-manifest@1",
          schemaId: "physical.r4-manifest@1",
          schemaVersion: 1,
          stage: "R4",
          domainPackId: "five-axis.domain-pack@6",
          platform: "windows",
          safetyBanner: "MODEL VALIDATION / NOT DEVICE SAFE",
          validationBanner: "SYNTHETIC SIL / REALITY VALIDATION OPEN",
          model: {
            equations: ["x[k+1] = Ad x[k] + Bd u[k]"],
            stateIds: ["x_pos"],
            inputIds: ["u_cmd"],
            outputIds: ["y_axis"],
            discretization: "exact-zoh",
            supportedDevices: ["sim-840d"],
            operatingConditions: ["warm spindle"],
            unmodeledFactors: ["thermal drift"],
          },
        }));
      }
      if (url.endsWith("/physical/r4/scenarios")) {
        return Promise.resolve(jsonResponse([{
          scenarioId: "in-domain-synthetic-sil",
          title: "In-Domain Synthetic SIL",
          description: "Held-out validation split with open rotary reality validation.",
          axisIds: ["X", "B", "C"],
        }]));
      }
      if (url.includes("/examples/physical-r4")) {
        return Promise.resolve(jsonResponse({
          manifest: {
            manifestId: "physical.r4-manifest@1",
            schemaId: "physical.r4-manifest@1",
            schemaVersion: 1,
            stage: "R4",
            domainPackId: "five-axis.domain-pack@6",
            platform: "windows",
            safetyBanner: "MODEL VALIDATION / NOT DEVICE SAFE",
            validationBanner: "SYNTHETIC SIL / REALITY VALIDATION OPEN",
            model: {
              equations: ["x[k+1] = Ad x[k] + Bd u[k]"],
              stateIds: ["x_pos"],
              inputIds: ["u_cmd"],
              outputIds: ["y_axis"],
              discretization: "exact-zoh",
              supportedDevices: ["sim-840d"],
              operatingConditions: ["warm spindle"],
              unmodeledFactors: ["thermal drift"],
            },
          },
          scenario: {
            scenarioId: "in-domain-synthetic-sil",
            title: "In-Domain Synthetic SIL",
            description: "Held-out validation split with open rotary reality validation.",
            axisIds: ["X", "B", "C"],
          },
          model: {
            equations: ["x[k+1] = Ad x[k] + Bd u[k]"],
            stateIds: ["x_pos"],
            inputIds: ["u_cmd"],
            outputIds: ["y_axis"],
            discretization: "exact-zoh",
            supportedDevices: ["sim-840d"],
            operatingConditions: ["warm spindle"],
            unmodeledFactors: ["thermal drift"],
          },
          calibration: {
            datasetId: "cal-set@1",
            traceId: "trace-cal",
            scenarioRole: "calibration",
            sourceId: "axiom.windows-file-telemetry-source@1",
            capturedAt: "2026-08-11T09:30:00Z",
            contentHash: "a".repeat(64),
          },
          validation: {
            datasetId: "val-set@1",
            traceId: "trace-val",
            scenarioRole: "validation",
            sourceId: "axiom.windows-file-telemetry-source@1",
            capturedAt: "2026-08-11T10:00:00Z",
            contentHash: "b".repeat(64),
            leakageGuards: [
              { checkId: "split-by-run", status: "pass", message: "Calibration and validation runs are disjoint." },
            ],
          },
          analysis: {
            traceArtifactType: "PhysicalResponseTrace",
            axes: [
              {
                axisId: "X",
                family: "linear-mm",
                unit: "mm",
                excitationStatus: "excited",
                series: {
                  command: [{ time: 0, value: 0 }, { time: 1, value: 10 }],
                  simulation: [{ time: 0, value: 0 }, { time: 1, value: 9.8 }],
                  observation: [{ time: 0, value: 0.1 }, { time: 1, value: 10.2 }],
                },
                metrics: [{ metricId: "x.max", label: "X max residual", group: "linear-mm", value: 0.2, unit: "mm" }],
                residualDecomposition: [{ componentId: "fit", label: "fit residual", value: 0.12, unit: "mm", source: "simulation-observation" }],
              },
              {
                axisId: "B",
                family: "rotary-rad",
                unit: "rad",
                excitationStatus: "insufficient",
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
                family: "rotary-rad",
                unit: "rad",
                excitationStatus: "insufficient",
                series: {
                  command: [{ time: 0, value: 0 }, { time: 1, value: 0.03 }],
                  simulation: [{ time: 0, value: 0 }, { time: 1, value: 0.03 }],
                  observation: [{ time: 0, value: 0 }, { time: 1, value: 0.01 }],
                },
                metrics: [],
                residualDecomposition: [],
              },
            ],
            metrics: [
              { metricId: "linear.max", label: "Linear max abs residual", group: "linear-mm", value: 0.2, unit: "mm" },
              { metricId: "rotary.max", label: "Rotary max abs residual", group: "rotary-rad", value: 0.01, unit: "rad" },
            ],
            claims: [
              {
                claimId: "r4.validation-window",
                title: "Held-out validation stays bounded",
                status: "Supported",
                statement: "Residual remains inside the validation envelope.",
                evidenceIds: ["fit-report"],
              },
              {
                claimId: "r4.rotary-coverage",
                title: "Rotary validation coverage remains open",
                status: "Inconclusive",
                statement: "B/C axis excitation is insufficient for a closed validation claim.",
                evidenceIds: ["coverage-note"],
              },
            ],
            evidence: [
              {
                evidenceId: "fit-report",
                kind: "fit",
                title: "Validation fit report",
                summary: "Exact-ZOH replay stays within threshold.",
                contentHash: "c".repeat(64),
              },
              {
                evidenceId: "coverage-note",
                kind: "validation",
                title: "Rotary coverage note",
                summary: "Reality validation remains open for B/C axes.",
                contentHash: "d".repeat(64),
              },
            ],
          },
        }));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Physical.*R4/i }));
    expect(await screen.findByText("MODEL VALIDATION / NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByText("SYNTHETIC SIL / REALITY VALIDATION OPEN")).toBeInTheDocument();
    expect(screen.getByText("MODEL VALIDATION · NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByText("PhysicalResponseTrace")).toBeInTheDocument();
    expect(screen.getAllByText("insufficient").length).toBeGreaterThan(0);
    expect(screen.getByText("Rotary validation coverage remains open")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|控制|应用/i })).not.toBeInTheDocument();
  });

  it("运行工程化 F1 场景并在碰撞场景中拒绝标准声明", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.endsWith("/five-axis/f1/manifest")) return Promise.resolve(jsonResponse(f1Manifest));
      if (url.endsWith("/five-axis/f1/scenarios")) return Promise.resolve(jsonResponse(f1Summaries));
      if (url.includes("/examples/five-axis-f1")) {
        const scenarioId = new URL(url, "http://test").searchParams.get("scenarioId") ?? "nominal-certified";
        return Promise.resolve(jsonResponse(f1Example(scenarioId)));
      }
      if (url.endsWith("/runs/evaluate")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { subjectId?: string };
        const scenarioId = body.subjectId?.includes("fixture-collision") ? "fixture-collision" : "nominal-certified";
        return Promise.resolve(jsonResponse(f1Run(scenarioId)));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByText("证据包已封存");
    fireEvent.click(screen.getByRole("button", { name: /Five-Axis.*F1/i }));

    expect(await screen.findByText("五轴数学场景")).toBeInTheDocument();
    expect(await screen.findAllByText("Supported")).toHaveLength(5);
    expect(screen.getByRole("note")).toHaveTextContent("不是 DeviceSafe");
    expect(screen.getByRole("img", { name: /参考路径、候选路径与碰撞上下文/ })).toBeInTheDocument();
    expect(screen.getAllByText("continuous").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("场景"), { target: { value: "fixture-collision" } });
    expect((await screen.findAllByText("Refuted")).length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("STANDARD CLAIM VERDICT")).toBeInTheDocument();
    expect(screen.getByTitle("fixture-fixture-collision")).toBeInTheDocument();
    expect(screen.getByText("Fixture Collision")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("scenarioId=fixture-collision"))).toBe(true);
  });
});
