import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Catalog, RunBundle } from "../../types";
import { MachineR3Workbench } from "./MachineR3Workbench";
import type { MachineR3ExamplePayload, MachineR3Manifest, MachineR3ScenarioSummary } from "./types";

const catalog: Catalog = {
  subjects: [],
  domainPacks: [
    { domainPackId: "machine-observation.domain-pack@1", comparisonPolicyIds: [], runnerIds: ["machine-trace-import@1"], runtimeBound: true },
  ],
  artifactAdapters: [],
};

const manifest: MachineR3Manifest = {
  manifestId: "machine.r3-manifest@1",
  schemaId: "machine.r3-manifest@1",
  schemaVersion: 1,
  stage: "R3",
  readOnly: true,
  safetyBanner: "READ ONLY / NOT DEVICE SAFE",
  suiteId: "machine-r3-fixtures@1",
  artifactDescriptors: [
    { artifactType: "machine.telemetry-trace", schemaVersion: 1, role: "run-input" },
  ],
  capabilityIds: [
    "machine-observation.trace.raw@1",
    "machine-observation.capture.read-only@1",
  ],
  claimDefinitionIds: [
    "machine-observation.raw-integrity-claim@1",
    "machine-observation.read-only-capture-claim@1",
  ],
  forbiddenClaims: ["DeviceSafe", "ProcessSafe", "safe-to-run"],
  cases: [{
    id: "read-only-paired-pass",
    title: "只读配对基线导入",
    description: "冻结 F4 基线、命令身份和七项上游 claim 的只读历史导入。",
    expectedExecutionStatus: "Succeeded",
    expectedCaseOutcome: "Passed",
  }],
};

const scenarios: MachineR3ScenarioSummary[] = [
  {
    scenarioId: "read-only-paired-pass",
    title: "只读配对基线导入",
    description: "冻结 F4 基线、命令身份和七项上游 claim 的只读历史导入。",
    expectedExecutionStatus: "Succeeded",
    expectedCaseOutcome: "Passed",
  },
  {
    scenarioId: "read-only-unpaired-pass",
    title: "只读未配对历史导入",
    description: "未绑定数学基线，但保留原始观测与设备上下文。",
    expectedExecutionStatus: "Succeeded",
    expectedCaseOutcome: "Passed",
  },
  {
    scenarioId: "out-of-order-gap",
    title: "帧序列断裂",
    description: "traceContentHash 正确，但 sequenceId 存在缺口，不允许插值。",
    expectedExecutionStatus: "Succeeded",
    expectedCaseOutcome: "Failed",
  },
  {
    scenarioId: "forbidden-write-operation",
    title: "非法写操作回放",
    description: "captureReceipt 标记为写设备行为，必须在 request 校验阶段拒绝。",
    expectedExecutionStatus: "Skipped",
    expectedCaseOutcome: "Invalid",
  },
];

function examplePayload(
  scenarioId: "read-only-paired-pass" | "read-only-unpaired-pass" | "out-of-order-gap" | "forbidden-write-operation",
): MachineR3ExamplePayload {
  const paired = scenarioId === "read-only-paired-pass";
  const unpaired = scenarioId === "read-only-unpaired-pass";
  const forbidden = scenarioId === "forbidden-write-operation";
  return {
    manifest,
    scenario: scenarios.find((item) => item.scenarioId === scenarioId)!,
    artifact: {
      artifactType: "machine.telemetry-trace",
      schemaVersion: 1,
      traceId: `trace:${scenarioId}`,
      sourceKind: "synthetic-replay",
      captureReceipt: {
        receiptId: `receipt:${scenarioId}`,
        sourceId: "axiom.windows-file-telemetry-source@1",
        operation: forbidden ? "parameter-write" : "file-import",
        transport: "windows-file-json",
        capturedAt: "2026-08-11T09:30:00Z",
        traceContentHash: "24c7f3c433b76765db97f31ae2ceb38bb1d54234b5e0a2d4ad88f551724cb9f6",
      },
      deviceIdentity: {
        deviceId: "sim-840d",
        controllerFamily: "siemens-840d",
        machineModel: "vmc-5x-sim",
      },
      frames: [
        {
          sequenceId: paired ? 100 : unpaired ? 300 : forbidden ? 600 : 500,
          deviceTimestamp: paired ? "2026-08-11T09:29:58.000Z" : unpaired ? "2026-08-11T11:29:58.000Z" : "2026-08-11T12:29:58.000Z",
          samples: [
            { channelId: "pos.work", value: paired ? [0, 0, 5] : unpaired ? [12, 1.5, 5] : [30, 2, 5], unit: "mm" },
            { channelId: "feed.actual", value: paired ? 1200 : unpaired ? 800 : 500, unit: "mm/min" },
          ],
          ...(forbidden ? {} : { alarms: [] }),
        },
        {
          sequenceId: paired ? 101 : unpaired ? 301 : forbidden ? 601 : 502,
          deviceTimestamp: paired ? "2026-08-11T09:29:58.020Z" : unpaired ? "2026-08-11T11:29:58.040Z" : "2026-08-11T12:29:58.060Z",
          samples: [
            { channelId: "pos.work", value: paired ? [1.5, 0, 4.7] : unpaired ? [13.5, 1.5, 4.8] : [31.5, 2, 4.7], unit: "mm" },
            { channelId: "feed.actual", value: paired ? 1200 : unpaired ? 800 : 500, unit: "mm/min" },
          ],
          ...(forbidden ? {} : { alarms: [] }),
        },
      ],
      vendorMetadata: { programName: "DEMO_5X_R3", channel: "CHANNEL_1" },
    },
    deviceProfile: {
      profileId: "device-profile.sim-840d@1",
      deviceId: "sim-840d",
      controllerFamily: "siemens-840d",
      manufacturer: "Siemens",
      machineModel: "vmc-5x-sim",
      exportVersion: "sinumerik-export@1.4",
      allowedReadOnlyOperations: ["file-import"],
      firmwareVersion: paired ? "840D-sl-6.15" : "840D-sl-6.14",
      calibrationId: paired ? "calibration.sim-840d@1" : null,
      channels: [
        { channelId: "pos.work", kind: "position-vector", unit: "mm", coordinateFrame: "workpiece" },
        { channelId: "feed.actual", kind: "scalar", unit: "mm/min" },
      ],
    },
    clockMapping: {
      mappingId: "clock-map.sim-840d@1",
      deviceId: "sim-840d",
      mappingMethod: paired ? "synchronized-export" : "fixed-offset",
      deviceReferenceTimestamp: paired ? "2026-08-11T09:29:58.000Z" : unpaired ? "2026-08-11T11:29:58.000Z" : "2026-08-11T12:29:58.000Z",
      hostReferenceTimestamp: paired ? "2026-08-11T17:29:58.010Z" : unpaired ? "2026-08-11T19:29:58.012Z" : "2026-08-11T20:29:58.015Z",
      offsetMilliseconds: paired ? 10 : unpaired ? 12 : 15,
      driftBoundMilliseconds: 2,
    },
    coordinateAlignment: {
      alignmentId: "alignment.sim-840d@1",
      deviceId: "sim-840d",
      sourceKind: unpaired ? "synthetic-reference" : "calibration-record",
      effectiveAt: unpaired ? "2026-08-10T08:00:00Z" : "2026-08-11T08:45:00Z",
      machineCoordinateFrame: "machine",
      workCoordinateFrame: "workpiece",
      calibrationStatus: unpaired ? "estimated" : "calibrated",
      calibrationId: unpaired ? null : "calibration.sim-840d@1",
      channelIds: ["pos.work"],
    },
    lineage: {
      machineRunId: paired ? "machine-run:paired-pass" : unpaired ? "machine-run:unpaired-pass" : forbidden ? "machine-run:forbidden" : "machine-run:gap",
      pairingStatus: unpaired || forbidden ? "unpaired" : "paired",
      baselineKind: unpaired || forbidden ? null : "reference",
      baselineRunBundleHash: unpaired || forbidden ? null : "beec29557d6bf8c22363616c65a73f4394e484c9b516478898e9c4039bc44d79",
      sourceCommandContentHash: unpaired || forbidden ? null : "085ab2047f6089fb3fa681c7a83ee3aa63c9d379b55529bbbabbd0411874d218",
      upstreamClaims: unpaired || forbidden
        ? []
        : [
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
      subjectId: paired ? "machine-r3-sim@paired" : unpaired ? "machine-r3-sim@unpaired" : forbidden ? "machine-r3-sim@forbidden" : "machine-r3-sim@gap",
      domainPackId: "machine-observation.domain-pack@1",
      runnerId: "machine-trace-import@1",
      evaluatorVersion: "machine-observation-evaluator@1",
      request: {
        artifact: {
          artifactType: "machine.telemetry-trace",
          schemaVersion: 1,
          traceId: `trace:${scenarioId}`,
        },
        case: { caseId: scenarioId },
      },
    },
  };
}

function runBundle(): RunBundle {
  return {
    run: {
      runId: "run.machine-r3",
      subjectId: "machine-r3-sim@paired",
      domainPackId: "machine-observation.domain-pack@1",
      runnerId: "machine-trace-import@1",
      runSpecHash: "run-spec-hash",
      reportContentHash: "report-hash",
      executionStatus: "Succeeded",
      caseOutcome: "Passed",
      evaluatorVersion: "machine-observation-evaluator@1",
      contentHash: "content-hash",
    },
    observation: {
      artifact: { artifactType: "machine.telemetry-trace", traceId: "trace:read-only-paired-pass" },
      artifactHash: "artifact-hash",
      source: "ImportedArtifact",
    },
    report: {
      executionStatus: "Succeeded",
      caseOutcome: "Passed",
      metricResults: [
        { metricId: "machine-observation.raw-integrity@1", status: "Computed", value: true, evidence: { level: "Observed", method: "hash-verify" } },
        { metricId: "machine-observation.clock-aligned@1", status: "Computed", value: true, evidence: { level: "Observed", method: "clock-audit" } },
        { metricId: "machine-observation.coordinate-context@1", status: "Computed", value: true, evidence: { level: "Observed", method: "alignment-audit" } },
      ],
      provenance: {
        contextHashes: {
          trace: "24c7f3c433b76765db97f31ae2ceb38bb1d54234b5e0a2d4ad88f551724cb9f6",
          baseline: "beec29557d6bf8c22363616c65a73f4394e484c9b516478898e9c4039bc44d79",
        },
      },
    },
    claims: [
      { claimDefinitionId: "machine-observation.read-only-capture-claim@1", status: "Supported", predicate: "capture is read-only", evidence: { level: "Observed", method: "receipt-check" } },
    ],
    bundleHash: "bundle-hash",
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("MachineR3Workbench", () => {
  it("展示真实 R3 schema 的只读边界并可提交 runSpec 评估", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/machine/r3/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/machine/r3/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.includes("/examples/machine-r3")) {
        const scenarioId = new URL(url, "http://test").searchParams.get("scenarioId") as "read-only-paired-pass" | "read-only-unpaired-pass" | "out-of-order-gap" | "forbidden-write-operation";
        return Promise.resolve(jsonResponse(examplePayload(scenarioId)));
      }
      if (url.endsWith("/runs/evaluate")) {
        const body = JSON.parse(String(init?.body)) as MachineR3ExamplePayload["runSpec"];
        if (body?.subjectId === "machine-r3-sim@forbidden") {
          const invalid = runBundle();
          invalid.run.executionStatus = "Skipped";
          invalid.run.caseOutcome = "Invalid";
          invalid.report.executionStatus = "Skipped";
          invalid.report.caseOutcome = "Invalid";
          invalid.claims = [];
          return Promise.resolve(jsonResponse(invalid));
        }
        return Promise.resolve(jsonResponse(runBundle()));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MachineR3Workbench catalog={catalog} />);

    expect(await screen.findByText("READ ONLY / NOT DEVICE SAFE")).toBeInTheDocument();
    expect(screen.getByText("clock-synchronized")).toBeInTheDocument();
    expect(screen.getByText("coordinate-calibrated")).toBeInTheDocument();
    expect(screen.getAllByText("paired").length).toBeGreaterThan(0);
    expect(screen.getByText("siemens-840d")).toBeInTheDocument();
    expect(screen.getByText("Siemens")).toBeInTheDocument();
    expect(screen.getByText("sinumerik-export@1.4")).toBeInTheDocument();
    expect(screen.getAllByText("file-import").length).toBeGreaterThan(0);
    expect(screen.getByText("programName, channel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "导入观测并评估" }));
    expect(await screen.findByText("capture is read-only")).toBeInTheDocument();
    expect(screen.getByText("clock-verified")).toBeInTheDocument();
    expect(screen.getByText("coordinate-verified")).toBeInTheDocument();
    expect(screen.getByText("ImportedArtifact")).toBeInTheDocument();
    expect(screen.getByText("trace")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("场景"), { target: { value: "read-only-unpaired-pass" } });
    expect(await screen.findAllByText("unpaired")).toHaveLength(3);
    expect(screen.getAllByText("unpaired")[0]?.className).toContain("status-neutral");
    expect(screen.getByText("coordinate-estimated")).toBeInTheDocument();
    expect(screen.getByText("coordinate-estimated").className).toContain("status-neutral");
    expect(screen.queryByText("missing-coordinate")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("场景"), { target: { value: "out-of-order-gap" } });
    expect(await screen.findByText("sequenceId 存在断裂或乱序，禁止插值补齐。")).toBeInTheDocument();
    expect(screen.getByText("存在 1 处 sequence discontinuity / gap。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /写入|启动|下发/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("场景"), { target: { value: "forbidden-write-operation" } });
    expect(await screen.findByText("检测到非只读操作，R3 应直接阻断。")).toBeInTheDocument();
    expect(screen.getByText("parameter-write")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "导入观测并评估" }));
    expect(await screen.findByText("Invalid")).toBeInTheDocument();
    expect(screen.getAllByText("Skipped").length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input).includes("scenarioId=read-only-unpaired-pass"))).toBe(true);
      expect(fetchMock.mock.calls.some(([input]) => String(input).includes("scenarioId=out-of-order-gap"))).toBe(true);
      expect(fetchMock.mock.calls.some(([input]) => String(input).includes("scenarioId=forbidden-write-operation"))).toBe(true);
    });
  });
});
