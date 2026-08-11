import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type { Catalog, ExperimentReport, ExperimentSpec } from "./types";

const example: ExperimentSpec = {
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
  domainPacks: [{ domainPackId: "ordered-point.domain-pack@1", comparisonPolicyIds: [], runnerIds: [] }],
};

const report: ExperimentReport = {
  experimentSpec: example,
  experimentSpecHash: "exp-hash-123456789",
  sharedInputHash: "input-hash-123456789",
  parameterSetHash: "parameters-hash-123456789",
  executionStatus: "Succeeded",
  caseOutcome: "Failed",
  armResults: [
    {
      armId: "baseline", subjectId: "ordered-point.offset-baseline", subjectVersion: "1", executionStatus: "Succeeded", caseOutcome: "Failed", outputArtifactHash: "a",
      runBundle: {
        observation: { artifact: { ...example.sharedInput, points: [[0, 0.08], [10, 0.08], [20, 0.08]] }, artifactHash: "a", source: "ExecutedSubject" },
        report: { metricResults: [{ metricId: "paired.euclidean.max", status: "Computed", value: 0.08, unit: "mm", thresholdPassed: false }] },
        run: { runId: "a", runnerId: "python-call@1", caseOutcome: "Failed", executionStatus: "Succeeded", contentHash: "a" },
        claims: [{ claimId: "a", status: "Rejected", predicate: "paired.euclidean.max <= 0.03 mm", metricId: "paired.euclidean.max", evidence: { level: "Exact", method: "index-paired" } }],
        bundleHash: "a",
      },
    },
    {
      armId: "candidate", subjectId: "ordered-point.offset-compensated", subjectVersion: "1", executionStatus: "Succeeded", caseOutcome: "Passed", outputArtifactHash: "b",
      runBundle: {
        observation: { artifact: { ...example.sharedInput, points: [[0, 0.02], [10, 0.02], [20, 0.02]] }, artifactHash: "b", source: "ExecutedSubject" },
        report: { metricResults: [{ metricId: "paired.euclidean.max", status: "Computed", value: 0.02, unit: "mm", thresholdPassed: true }] },
        run: { runId: "b", runnerId: "python-call@1", caseOutcome: "Passed", executionStatus: "Succeeded", contentHash: "b" },
        claims: [{ claimId: "b", status: "Accepted", predicate: "paired.euclidean.max <= 0.03 mm", metricId: "paired.euclidean.max", evidence: { level: "Exact", method: "index-paired" } }],
        bundleHash: "b",
      },
    },
  ],
  comparison: {
    comparisonId: "cmp", policyId: "ordered-point.experiment-comparison.strict@1",
    compatibility: { compatible: true, issues: [] },
    metricComparisons: [{ metricId: "paired.euclidean.max", left: 0.08, right: 0.02, unit: "mm", comparable: true, delta: -0.06, preferredSubjectId: "ordered-point.offset-compensated" }],
    contentHash: "cmp-hash",
  },
  failures: [],
  contentHash: "bundle-hash-123456789",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("Axiom workbench", () => {
  it("loads the real catalog/example, runs both arms, and reruns edited parameters", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (url.endsWith("/contour-ab")) return Promise.resolve(jsonResponse(example));
      if (url.endsWith("/experiments/run")) return Promise.resolve(jsonResponse(report));
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

  it("shows a useful API failure without fabricating evidence", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (String(input).endsWith("/contour-ab")) return Promise.resolve(jsonResponse(example));
      return Promise.resolve(jsonResponse({ detail: "runner unavailable" }, 503));
    }));

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("API 503");
    expect(screen.queryByText("证据包已封存")).not.toBeInTheDocument();
  });

  it("renders a half-failed experiment without reading a missing run bundle", async () => {
    const failed = structuredClone(report);
    failed.executionStatus = "ExecutionFailed";
    failed.caseOutcome = "Inconclusive";
    failed.comparison = undefined;
    failed.armResults[1] = {
      armId: "candidate",
      subjectId: "vendor.missing-subject",
      subjectVersion: "1",
      executionStatus: "ExecutionFailed",
      caseOutcome: "Inconclusive",
      failure: { code: "UnknownSubject", message: "No local Subject is registered." },
    };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (String(input).endsWith("/contour-ab")) return Promise.resolve(jsonResponse(example));
      return Promise.resolve(jsonResponse(failed));
    }));

    render(<App />);

    expect(await screen.findByText("No local Subject is registered.")).toBeInTheDocument();
    expect(screen.getAllByText("ExecutionFailed").length).toBeGreaterThan(0);
    expect(screen.getByText("等待比较")).toBeInTheDocument();
  });

  it("blocks metric preference when strict comparison is incompatible", async () => {
    const incompatible = structuredClone(report);
    incompatible.caseOutcome = "Inconclusive";
    incompatible.comparison!.compatibility = {
      compatible: false,
      issues: [{ code: "ParameterSetMismatch", message: "Parameter identity differs." }],
    };
    incompatible.comparison!.metricComparisons = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/catalog")) return Promise.resolve(jsonResponse(catalog));
      if (String(input).endsWith("/contour-ab")) return Promise.resolve(jsonResponse(example));
      return Promise.resolve(jsonResponse(incompatible));
    }));

    render(<App />);

    expect(await screen.findByText("Incompatible")).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });
});
