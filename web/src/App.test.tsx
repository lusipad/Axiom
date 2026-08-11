import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { Catalog, ExperimentReport, ExperimentSpec, MathStageManifest, RunBundle, RunSpec } from "./types";

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
    { domainPackId: "five-axis.domain-pack@1", comparisonPolicyIds: [], runnerIds: ["artifact-import@1"], runtimeBound: true },
  ],
  artifactAdapters: [
    {
      adapterId: "five-axis.sampled-cartesian-to-ordered-point@1",
      sourceArtifactType: "five-axis.sampled-cartesian-position-view",
      targetArtifactType: "ordered-point-sequence",
    },
  ],
};

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
      runBundle: {
        observation: {
          artifact: { ...pointExample.sharedInput, points: [[0, 0.08], [10, 0.08], [20, 0.08]] },
          artifactHash: "artifact-baseline",
          source: "ExecutedSubject",
        },
        report: {
          executionStatus: "Succeeded",
          caseOutcome: "Failed",
          metricResults: [{ metricId: "paired.euclidean.max", status: "Computed", value: 0.08, unit: "mm", thresholdPassed: false }],
        },
        run: {
          runId: "run-baseline",
          subjectId: "ordered-point.offset-baseline",
          domainPackId: "ordered-point.domain-pack@1",
          runnerId: "python-call@1",
          runSpecHash: "spec-baseline",
          reportContentHash: "report-baseline",
          caseOutcome: "Failed",
          executionStatus: "Succeeded",
          contentHash: "content-baseline",
        },
        claims: [{ claimId: "claim-baseline", status: "Rejected", predicate: "paired.euclidean.max <= 0.03 mm", metricId: "paired.euclidean.max", evidence: { level: "Exact", method: "index-paired" } }],
        bundleHash: "bundle-baseline",
      },
    },
    {
      armId: "candidate",
      subjectId: "ordered-point.offset-compensated",
      subjectVersion: "1",
      executionStatus: "Succeeded",
      caseOutcome: "Passed",
      outputArtifactHash: "artifact-candidate",
      runBundle: {
        observation: {
          artifact: { ...pointExample.sharedInput, points: [[0, 0.02], [10, 0.02], [20, 0.02]] },
          artifactHash: "artifact-candidate",
          source: "ExecutedSubject",
        },
        report: {
          executionStatus: "Succeeded",
          caseOutcome: "Passed",
          metricResults: [{ metricId: "paired.euclidean.max", status: "Computed", value: 0.02, unit: "mm", thresholdPassed: true }],
        },
        run: {
          runId: "run-candidate",
          subjectId: "ordered-point.offset-compensated",
          domainPackId: "ordered-point.domain-pack@1",
          runnerId: "python-call@1",
          runSpecHash: "spec-candidate",
          reportContentHash: "report-candidate",
          caseOutcome: "Passed",
          executionStatus: "Succeeded",
          contentHash: "content-candidate",
        },
        claims: [{ claimId: "claim-candidate", status: "Accepted", predicate: "paired.euclidean.max <= 0.03 mm", metricId: "paired.euclidean.max", evidence: { level: "Exact", method: "index-paired" } }],
        bundleHash: "bundle-candidate",
      },
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

const fiveAxisManifest: MathStageManifest = {
  manifestId: "five-axis.math-stage-manifest@1",
  schemaVersion: 1,
  stage: "F0",
  capabilityIds: [
    "five-axis.contract.manifest@1",
    "five-axis.contract.envelope.m0@1",
    "five-axis.contract.envelope.m1@1",
  ],
  fixtureContentIds: ["fixture-hash-1234567890"],
  policyVersions: {
    collisionContext: "five-axis.collision-context.required@1",
    reconstructionPolicy: "five-axis.reconstruction.none@1",
  },
  numericEnvironment: { python: "3.x", platform: "portable", float: "64-bit" },
  expectedStatus: "Inconclusive",
  expectedClaim: null,
  tolerances: [{ metricId: "five-axis.contract.sample-spacing@1", unit: "mm", value: 0 }],
  envelopes: [
    {
      envelopeId: "five-axis.m0-artifact@1",
      stage: "M0",
      envelopeType: "artifact",
      schemaId: "five-axis.envelope@1",
      contentId: "m0-content-hash-1234567890",
      coordinateSpec: { coordinateSystem: "cartesian", axes: ["X", "Y", "Z"], unit: "mm", coordinateFrame: "machine.work-envelope@1" },
      capabilityIds: ["five-axis.contract.envelope.m0@1"],
    },
    {
      envelopeId: "five-axis.m1-certificate@1",
      stage: "M1",
      envelopeType: "certificate",
      schemaId: "five-axis.envelope@1",
      contentId: "m1-content-hash-1234567890",
      capabilityIds: ["five-axis.contract.envelope.m1@1"],
    },
  ],
};

const fiveAxisExample: RunSpec = {
  subjectId: "five-axis-fixture@1",
  domainPackId: "five-axis.domain-pack@1",
  runnerId: "artifact-import@1",
  evaluatorVersion: "five-axis-f0-evaluator@1",
  request: {
    artifact: {
      artifactType: "five-axis.sampled-cartesian-position-view",
      schemaVersion: 1,
      derivedViewKind: "sampled-cartesian-derived-view@1",
      sourceArtifactType: "five-axis.toolpath-envelope@1",
      sourceCoordinateMode: "cartesian-xyz",
      coordinateSpec: { coordinateSystem: "cartesian", axes: ["X", "Y", "Z"], unit: "mm", coordinateFrame: "machine.work-envelope@1" },
      samples: [{ sampleIndex: 0, position: [0, 1, 2] }, { sampleIndex: 1, position: [0.5, 1.5, 2.5] }],
      pathProgress: { progressKind: "arc-length", unit: "mm", values: [0, 0.75] },
      regularity: { continuityClass: "C1", nodeEvents: [{ nodeIndex: 1, eventType: "corner", regularityClass: "C0", progressValue: 0.75 }] },
      envelopes: fiveAxisManifest.envelopes,
      capabilityIds: ["five-axis.contract.manifest@1", "five-axis.adapter.ordered-point-export@1"],
    },
    case: { caseId: "five-axis.f0-contract@1", requiredMetrics: ["five-axis.contract.readiness@1"] },
    manifest: fiveAxisManifest,
    collisionContext: null,
    reconstructionPolicy: null,
  },
};

const fiveAxisRun: RunBundle = {
  run: {
    runId: "run-five-axis",
    subjectId: "five-axis-fixture@1",
    domainPackId: "five-axis.domain-pack@1",
    runnerId: "artifact-import@1",
    runSpecHash: "run-spec-five-axis",
    reportContentHash: "report-five-axis",
    executionStatus: "Succeeded",
    caseOutcome: "Inconclusive",
    evaluatorVersion: "five-axis-f0-evaluator@1",
    contentHash: "run-content-five-axis",
  },
  observation: {
    artifact: fiveAxisExample.request.artifact as NonNullable<RunBundle["observation"]>["artifact"],
    artifactHash: "artifact-five-axis",
    source: "ImportedArtifact",
  },
  report: {
    executionStatus: "Succeeded",
    caseOutcome: "Inconclusive",
    metricResults: [
      {
        metricId: "five-axis.contract.readiness@1",
        metricDefinitionId: "five-axis.contract.readiness@1",
        status: "InsufficientContext",
        reasonCode: "MissingContractContext",
        requires: ["five-axis.contract.manifest@1", "five-axis.derived.sampled-cartesian-view@1"],
      },
    ],
    capabilities: [{ capabilityId: "five-axis.contract.manifest@1", source: "Evaluator" }],
    domainFailures: [{ code: "MissingCollisionContext", message: "F0 contract evaluation requires an explicit CollisionContext.", path: "collisionContext", severity: "error" }],
  },
  claims: [
    {
      claimId: "claim-five-axis",
      status: "Supported",
      predicate: "case.outcome == Inconclusive",
      evidence: { level: "Observed", method: "axiom.case-outcome.aggregate@1" },
    },
  ],
  bundleHash: "bundle-five-axis",
};

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
      if (url.endsWith("/five-axis/f0/manifest")) return Promise.resolve(jsonResponse(fiveAxisManifest));
      if (url.endsWith("/five-axis-f0")) return Promise.resolve(jsonResponse(fiveAxisExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.endsWith("/runs/evaluate")) return Promise.resolve(jsonResponse(fiveAxisRun));
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /共享输入与两个 Subject 输出/ })).toBeInTheDocument();
    expect(screen.getByText("Strict compatible")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("补偿增益"), { target: { value: "0.5" } });
    fireEvent.click(screen.getByRole("button", { name: "运行实验" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    const lastCall = fetchMock.mock.calls.at(-1);
    const submitted = JSON.parse(String(lastCall?.[1]?.body)) as ExperimentSpec;
    expect(submitted.parameterSet.values.compensationGain).toBe(0.5);
  });

  it("展示初始化 API 失败，而不伪造证据", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/five-axis/f0/manifest")) return Promise.resolve(jsonResponse(fiveAxisManifest));
      if (url.endsWith("/five-axis-f0")) return Promise.resolve(jsonResponse(fiveAxisExample));
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
      if (url.endsWith("/five-axis/f0/manifest") || url.endsWith("/five-axis-f0")) {
        return Promise.resolve(jsonResponse({ detail: "F0 unavailable" }, 503));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<App />);

    expect(await screen.findByText("证据包已封存")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Five-Axis/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
  });

  it("切换到 Five-Axis Lab 并展示真实 F0 返回", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(pointExample));
      if (url.endsWith("/five-axis/f0/manifest")) return Promise.resolve(jsonResponse(fiveAxisManifest));
      if (url.endsWith("/five-axis-f0")) return Promise.resolve(jsonResponse(fiveAxisExample));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(pointReport));
      if (url.endsWith("/runs/evaluate")) return Promise.resolve(jsonResponse(fiveAxisRun));
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<App />);

    await screen.findByText("证据包已封存");
    fireEvent.click(screen.getByRole("button", { name: /Five-Axis/i }));

    expect(await screen.findByText("Five-Axis 机器契约")).toBeInTheDocument();
    expect(screen.getByText("Sample Fixture")).toBeInTheDocument();
    expect(screen.getByText("当前页面只验证机器契约、派生视图和适配器暴露，不发布几何、运动学、碰撞、设备可执行声明。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "验证 F0 契约" }));

    expect(await screen.findByText("MissingCollisionContext")).toBeInTheDocument();
    expect(screen.getByText("case.outcome == Inconclusive")).toBeInTheDocument();
    expect(screen.getByText("five-axis.contract.readiness@1")).toBeInTheDocument();
  });
});
