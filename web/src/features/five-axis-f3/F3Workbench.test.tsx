import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Catalog } from "../../types";
import { F3Workbench } from "./F3Workbench";
import type {
  F3ExamplePayload,
  F3MathStageManifest,
  F3RunBundle,
  F3ScenarioSummary,
  M5DiscreteCommand,
  M5SampledTrajectory,
} from "./types";

const hashA = "a".repeat(64);
const hashB = "b".repeat(64);
const hashC = "c".repeat(64);
const hashD = "d".repeat(64);
const CONTINUOUS_CLAIM_ID = "five-axis.continuously-feasible-claim@1";
const INTERVAL_CLAIM_ID = "five-axis.interval-certified-claim@1";
const RECONSTRUCTION_POSITION_METRIC_ID = "five-axis.reconstruction-position-error.max@1";
const RECONSTRUCTION_ORIENTATION_METRIC_ID = "five-axis.reconstruction-orientation-error.max@1";

const catalog: Catalog = {
  subjects: [],
  domainPacks: [{
    domainPackId: "five-axis.domain-pack@4",
    comparisonPolicyIds: [],
    runnerIds: ["artifact-import@1"],
    runtimeBound: true,
  }],
  artifactAdapters: [],
};

const scenarios: F3ScenarioSummary[] = [
  {
    scenarioId: "smoothstep-certified",
    title: "Smoothstep Certified",
    description: "C3 smoothstep trajectory with full interval certification.",
    expectedClaimStatusById: {
      "five-axis.continuously-feasible-claim@1": "Supported",
      "five-axis.interval-certified-claim@1": "Supported",
    },
  },
  {
    scenarioId: "zoh-moving-unsupported",
    title: "Moving ZOH Unsupported",
    description: "Moving ZOH cannot certify interior interval derivatives.",
    expectedClaimStatusById: {
      "five-axis.continuously-feasible-claim@1": "Supported",
      "five-axis.interval-certified-claim@1": "Inconclusive",
    },
  },
];

const manifest: F3MathStageManifest = {
  manifestId: "five-axis.f3-math-stage-manifest@1",
  schemaId: "five-axis.f3-math-stage-manifest@1",
  schemaVersion: 1,
  stage: "F3",
  artifactDescriptors: [
    { stage: "M0", artifactType: "five-axis.normalized-program", schemaId: "five-axis.normalized-program@1" },
    { stage: "M1", artifactType: "five-axis.m1-reference-path", schemaId: "five-axis.m1-reference-path@1" },
    { stage: "M2", artifactType: "five-axis.m2-candidate-task-geometry", schemaId: "five-axis.m2-candidate-task-geometry@1" },
    { stage: "M3", artifactType: "five-axis.m3-candidate-axis-path", schemaId: "five-axis.m3-candidate-axis-path@1" },
    { stage: "M4", artifactType: "five-axis.m4-continuous-trajectory", schemaId: "five-axis.m4-continuous-trajectory@1" },
    { stage: "M5", artifactType: "five-axis.m5-sampled-trajectory", schemaId: "five-axis.m5-sampled-trajectory@1" },
  ],
  motionConstraintProfileSchemaId: "five-axis.motion-constraint-profile@1",
  motionConstraintProfileId: "five-axis.motion-constraint-profile.nominal@1",
  motionConstraintProfileContentId: hashA,
  capabilityIds: ["five-axis.time-law.bound@1", "five-axis.reconstruction.policy-bound@1"],
  fixtureContentIds: [hashB, hashD, hashA],
  policyIds: ["five-axis.reconstruction.reference-m4@1", "five-axis.reconstruction.foh@1"],
  numericEnvironment: { python: "3.14", pydantic: "2.13" },
  expectedMetrics: [
    { metricId: "five-axis.continuously-feasible-claim@1", expectedStatus: "Supported" },
    { metricId: "five-axis.interval-certified-claim@1", expectedStatus: "Supported" },
  ],
  expectedClaims: [
    { claimId: "five-axis.continuously-feasible-claim@1", claimClass: "M4", expectedStatus: "Supported", evidenceLevel: "Certified" },
    { claimId: "five-axis.interval-certified-claim@1", claimClass: "M5", expectedStatus: "Supported", evidenceLevel: "Certified" },
  ],
  expectedEvidence: [{ evidenceId: "f3.lineage", evidenceKind: "lineage", required: true }],
  tolerances: [{ toleranceId: "sigma", target: "sigma", tolerance: { absolute: 0.000001, relative: 0, unit: "dimensionless" } }],
  decisions: [{ decisionId: "f3.accept", status: "accepted", rationale: "M4/M5 evidence only." }],
};

function f3Example(scenarioId: string): F3ExamplePayload {
  const isDiscreteCommand = scenarioId === "zoh-moving-unsupported";
  const axisPath = {
    axisPathId: `axis-path.${scenarioId}`,
    sourceCandidateGeometryContentId: hashB,
    machineProfileContentId: hashC,
    machineProfile: {} as never,
    ikSolutions: [],
    branchGraph: { graphId: "graph.1", rootBranchIds: [], branches: [], transitions: [] },
    jointSegments: [],
    nodeEvents: [
      { nodeId: `${scenarioId}.start`, sigma: 0, eventType: "start" },
      { nodeId: `${scenarioId}.dwell`, sigma: 0.5, eventType: "dwell", leftSegmentId: "seg.1", rightSegmentId: "seg.2" },
      { nodeId: `${scenarioId}.end`, sigma: 1, eventType: "end" },
    ],
    kinematicsCertificate: {
      certificateId: "cert.1",
      evidenceLevel: "Certified",
      continuousMethod: "five-axis.f3.continuous-replay@1",
      selectedBranchId: "branch.1",
      intervalCount: 2,
      positionResidualUpperBound: 0,
      orientationResidualUpperBound: 0,
      axisLimitNormalizedMarginLowerBound: 0.2,
      minimumSingularValueLowerBound: 0.3,
      policyIds: ["five-axis.reconstruction.reference-m4@1"],
    },
  } as never;
  const motionConstraintProfile = {
    artifactType: "five-axis.motion-constraint-profile",
    schemaId: "five-axis.motion-constraint-profile@1",
    schemaVersion: 1,
    profileId: "five-axis.motion-constraint-profile.nominal@1",
    machineProfileId: "five-axis.machine-profile.nominal@1",
    machineProfileContentId: hashC,
    axisConstraints: [
      { axisId: "X", unit: "mm", maximumVelocity: 1, maximumAcceleration: 2, maximumJerk: 3 },
      { axisId: "Y", unit: "mm", maximumVelocity: 1, maximumAcceleration: 2, maximumJerk: 3 },
      { axisId: "Z", unit: "mm", maximumVelocity: 1, maximumAcceleration: 2, maximumJerk: 3 },
      { axisId: "A", unit: "rad", maximumVelocity: 1, maximumAcceleration: 2, maximumJerk: 3 },
      { axisId: "C", unit: "rad", maximumVelocity: 1, maximumAcceleration: 2, maximumJerk: 3 },
    ],
    startBoundary: { sigmaVelocity: 0, sigmaAcceleration: 0 },
    endBoundary: { sigmaVelocity: 0, sigmaAcceleration: 0 },
    nodeConstraints: [
      { nodeId: `${scenarioId}.dwell`, sigma: 0.5, boundaryMode: "dwell", dwellSeconds: 0.3, rationale: "explicit dwell" },
    ],
    policyIds: ["five-axis.time-law.bound@1", "five-axis.reconstruction.policy-bound@1"],
    provenance: [{ sourceStage: "M3", sourceId: "axis-path.1", sourceContentId: hashB, method: "synthesis" }],
  } as never;
  const continuousTrajectory = {
    artifactType: "five-axis.m4-continuous-trajectory",
    schemaId: "five-axis.m4-continuous-trajectory@1",
    schemaVersion: 1,
    trajectoryId: `trajectory.${scenarioId}`,
    sourceAxisPath: axisPath,
    sourceAxisPathContentId: hashB,
    motionConstraintProfile,
    motionConstraintProfileContentId: hashA,
    solverId: "five-axis.f3.solver@1",
    timingMode: "smoothstep7-feasible",
    spans: [
      {
        spanId: `${scenarioId}.move.1`,
        spanKind: "move",
        segmentIds: ["seg.1"],
        startTimeSeconds: 0,
        endTimeSeconds: 1,
        sigmaStart: 0,
        sigmaEnd: 0.5,
        timeLaw: {
          lawKind: "smoothstep7",
          durationSeconds: 1,
          accelerationDurationSeconds: 0.2,
          cruiseDurationSeconds: 0.6,
          decelerationDurationSeconds: 0.2,
          sigmaVelocityLimit: 0.9,
          sigmaAccelerationLimit: 1.7,
          sigmaJerkLimit: 2.6,
          peakSigmaVelocity: 0.8,
          peakSigmaAcceleration: 1.4,
          peakSigmaJerk: 2.2,
        },
      },
      {
        spanId: `${scenarioId}.dwell.1`,
        spanKind: "dwell",
        segmentIds: [],
        startTimeSeconds: 1,
        endTimeSeconds: 1.3,
        sigmaStart: 0.5,
        sigmaEnd: 0.5,
        timeLaw: {
          lawKind: "dwell",
          durationSeconds: 0.3,
          peakSigmaVelocity: 0,
          peakSigmaAcceleration: 0,
          peakSigmaJerk: 0,
        },
      },
    ],
    verification: {
      verificationId: "verify.1",
      solverId: "five-axis.f3.solver@1",
      evidenceLevel: "Certified",
      claimId: "five-axis.continuously-feasible-claim@1",
      overallStatus: "Supported",
      totalDurationSeconds: 1.3,
      optimality: { classification: "FeasibleOnly", proofGapSeconds: 0, rationale: "synthetic" },
      nodeContracts: [
        { nodeId: `${scenarioId}.start`, sigma: 0, eventType: "start", boundaryMode: "allow-continuous", source: "regularity" },
        { nodeId: `${scenarioId}.dwell`, sigma: 0.5, eventType: "dwell", boundaryMode: "dwell", dwellSeconds: 0.3, source: "profile" },
      ],
      axisConstraintUsage: [
        { axisId: "X", unit: "mm", maximumVelocity: 0.8, velocityLimit: 1, maximumAcceleration: 1.2, accelerationLimit: 2, maximumJerk: 2.2, jerkLimit: 3 },
        { axisId: "Y", unit: "mm", maximumVelocity: 0.7, velocityLimit: 1, maximumAcceleration: 1.1, accelerationLimit: 2, maximumJerk: 2.1, jerkLimit: 3 },
        { axisId: "Z", unit: "mm", maximumVelocity: 0.6, velocityLimit: 1, maximumAcceleration: 1.0, accelerationLimit: 2, maximumJerk: 2.0, jerkLimit: 3 },
        { axisId: "A", unit: "rad", maximumVelocity: 0.5, velocityLimit: 1, maximumAcceleration: 0.9, accelerationLimit: 2, maximumJerk: 1.9, jerkLimit: 3 },
        { axisId: "C", unit: "rad", maximumVelocity: 0.4, velocityLimit: 1, maximumAcceleration: 0.8, accelerationLimit: 2, maximumJerk: 1.8, jerkLimit: 3 },
      ],
      errorLedger: [],
    },
    provenance: [{ sourceStage: "M4", sourceId: `trajectory.${scenarioId}`, sourceContentId: hashB, method: "time-law" }],
  } as never;
  const sampledTrajectory = {
    artifactType: "five-axis.m5-sampled-trajectory",
    schemaId: "five-axis.m5-sampled-trajectory@1",
    contentId: hashA,
    schemaVersion: 1,
    sampledTrajectoryId: `sampled.${scenarioId}`,
    sourceM4: continuousTrajectory,
    sourceM4Id: `trajectory.${scenarioId}`,
    sourceM4ContentId: hashD,
    samplePeriod: 0.25,
    duration: 1.3,
    remainderDuration: 0.05,
    terminalSampleIncluded: true,
    finalHold: true,
    reconstructionPolicy: { policyId: "five-axis.reconstruction.reference-m4@1" },
    limits: {
      positionUnits: ["mm", "mm", "mm", "rad", "rad"],
      velocityLimits: [1, 1, 1, 1, 1],
      accelerationLimits: [2, 2, 2, 2, 2],
      jerkLimits: [3, 3, 3, 3, 3],
    },
    samples: [
      {
        sampleId: `${scenarioId}.s0`,
        sampleIndex: 0,
        t: 0,
        cycle: 0,
        sigma: 0,
        q: [0, 0, 0, 0, 0],
        qdot: [0, 0, 0, 0, 0],
        qddot: [0, 0, 0, 0, 0],
        qjerk: [0, 0, 0, 0, 0],
        taskPose: { position: [0, 0, 0], toolAxis: [0, 0, 1] },
        provenance: [{ sourceStage: "M4", sourceId: "trajectory.1", sourceContentId: hashB, method: "fixed-period-sampling" }],
      },
      {
        sampleId: `${scenarioId}.s1`,
        sampleIndex: 1,
        t: 0.25,
        cycle: 1,
        sigma: 0.2,
        q: [1, 0, 0, 0, 0],
        qdot: [0.2, 0, 0, 0, 0],
        qddot: [0.1, 0, 0, 0, 0],
        qjerk: [0.05, 0, 0, 0, 0],
        taskPose: { position: [1, 0, 0], toolAxis: [0, 0, 1] },
        provenance: [{ sourceStage: "M4", sourceId: "trajectory.1", sourceContentId: hashB, method: "fixed-period-sampling" }],
      },
      {
        sampleId: `${scenarioId}.s2`,
        sampleIndex: 2,
        t: 0.5,
        cycle: 2,
        sigma: 0.5,
        q: [2, 0, 0, 0, 0],
        qdot: [0.3, 0, 0, 0, 0],
        qddot: [0.1, 0, 0, 0, 0],
        qjerk: [0.04, 0, 0, 0, 0],
        taskPose: { position: [2, 0, 0], toolAxis: [0, 0, 1] },
        provenance: [{ sourceStage: "M4", sourceId: "trajectory.1", sourceContentId: hashB, method: "fixed-period-sampling" }],
      },
    ],
    intervals: [
      {
        intervalId: `${scenarioId}.i0`,
        intervalIndex: 0,
        startSampleIndex: 0,
        endSampleIndex: 1,
        tStart: 0,
        tEnd: 0.25,
        intervalSemantics: "[t_k,t_k+1)",
        certificateCoefficients: [
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
        ],
      },
      {
        intervalId: `${scenarioId}.i1`,
        intervalIndex: 1,
        startSampleIndex: 1,
        endSampleIndex: 2,
        tStart: 0.25,
        tEnd: 0.5,
        intervalSemantics: "[t_k,t_k+1)",
        certificateCoefficients: [
          [1, 1, 1, 1, 1],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0],
        ],
      },
    ],
    provenance: [{ sourceStage: "M4", sourceId: `trajectory.${scenarioId}`, sourceContentId: hashD, method: "fixed-period-sampling" }],
  } as unknown as M5SampledTrajectory;
  const discreteCommand = {
    artifactType: "five-axis.m5-discrete-command",
    schemaId: "five-axis.m5-discrete-command@1",
    contentId: hashC,
    schemaVersion: 1,
    discreteCommandId: `command.${scenarioId}`,
    sourceM4: continuousTrajectory,
    sourceM4Id: `trajectory.${scenarioId}`,
    sourceM4ContentId: hashD,
    samplePeriod: 0.25,
    duration: 1.3,
    remainderDuration: 0.05,
    terminalSampleIncluded: true,
    finalHold: true,
    reconstructionPolicy: { policyId: "five-axis.reconstruction.zoh@1" },
    limits: {
      positionUnits: ["mm", "mm", "mm", "rad", "rad"],
      velocityLimits: [1, 1, 1, 1, 1],
      accelerationLimits: [2, 2, 2, 2, 2],
      jerkLimits: [3, 3, 3, 3, 3],
    },
    samples: sampledTrajectory.samples,
    intervals: sampledTrajectory.intervals,
    provenance: [{ sourceStage: "M4", sourceId: `trajectory.${scenarioId}`, sourceContentId: hashD, method: "fixed-period-sampling" }],
  } as unknown as M5DiscreteCommand;
  const scenarioManifest: F3MathStageManifest = isDiscreteCommand
    ? {
        ...manifest,
        artifactDescriptors: manifest.artifactDescriptors.map((descriptor) => descriptor.stage === "M5"
          ? { stage: "M5", artifactType: "five-axis.m5-discrete-command", schemaId: "five-axis.m5-discrete-command@1" }
          : descriptor),
        fixtureContentIds: [hashB, hashD, hashC],
        policyIds: ["five-axis.reconstruction.zoh@1"],
      }
    : manifest;
  return {
    manifest: scenarioManifest,
    scenario: scenarios.find((item) => item.scenarioId === scenarioId) ?? scenarios[0]!,
    source: { sourceText: "M4/M5 synthetic reference" },
    artifacts: isDiscreteCommand
      ? { axisPath, motionConstraintProfile, continuousTrajectory, discreteCommand }
      : { axisPath, motionConstraintProfile, continuousTrajectory, sampledTrajectory },
    runSpec: {
      subjectId: `five-axis.f3.${scenarioId}@1`,
      domainPackId: "five-axis.domain-pack@4",
      runnerId: "artifact-import@1",
      evaluatorVersion: "five-axis-f3-evaluator@1",
      request: { scenarioId },
    },
  };
}

function f3RunBundle(scenarioId: string): F3RunBundle {
  const isDiscreteCommand = scenarioId === "zoh-moving-unsupported";
  return {
    run: {
      runId: `run-${scenarioId}`,
      subjectId: `five-axis.f3.${scenarioId}@1`,
      domainPackId: "five-axis.domain-pack@4",
      runnerId: "artifact-import@1",
      runSpecHash: `spec-${scenarioId}`,
      reportContentHash: `report-${scenarioId}`,
      executionStatus: "Succeeded",
      caseOutcome: isDiscreteCommand ? "Unsupported" : "Passed",
      evaluatorVersion: "five-axis-f3-evaluator@1",
      contentHash: `bundle-${scenarioId}`,
    },
    report: {
      executionStatus: "Succeeded",
      caseOutcome: isDiscreteCommand ? "Unsupported" : "Passed",
      metricResults: [
        {
          metricId: RECONSTRUCTION_POSITION_METRIC_ID,
          status: "Computed",
          value: isDiscreteCommand ? 0.2 : 0.01,
          unit: "mm",
          details: {
            entries: [
              { quantity: "position", source: "five-axis.reconstruction.reference-m4@1", bound: isDiscreteCommand ? 0.2 : 0.01, method: "midpoint-replay", unit: "mm" },
            ],
          },
        },
        {
          metricId: RECONSTRUCTION_ORIENTATION_METRIC_ID,
          status: "Computed",
          value: isDiscreteCommand ? 0.08 : 0.005,
          unit: "rad",
          details: {
            entries: [
              { quantity: "orientation", source: "five-axis.reconstruction.reference-m4@1", bound: isDiscreteCommand ? 0.08 : 0.005, method: "midpoint-replay", unit: "rad" },
            ],
          },
        },
      ],
    },
    claims: [
      {
        claimDefinitionId: CONTINUOUS_CLAIM_ID,
        metricId: CONTINUOUS_CLAIM_ID,
        status: "Supported",
        predicate: "five-axis.ContinuouslyFeasible is true",
        evidence: { level: "Certified", method: "time-law-closure" },
      },
      {
        claimDefinitionId: INTERVAL_CLAIM_ID,
        metricId: INTERVAL_CLAIM_ID,
        status: isDiscreteCommand ? "Inconclusive" : "Supported",
        predicate: isDiscreteCommand ? "five-axis.IntervalCertified is inconclusive under moving ZOH" : "five-axis.IntervalCertified is true",
        evidence: isDiscreteCommand ? undefined : { level: "Certified", method: "reconstruction-policy-closure" },
      },
    ],
    bundleHash: `bundle-${scenarioId}`,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("Five-Axis F3 workbench", () => {
  it("展示 M4/M5 证书、轴上限和采样重建记录", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/five-axis/f3/manifest")) return Promise.resolve(jsonResponse(manifest));
      if (url.endsWith("/five-axis/f3/scenarios")) return Promise.resolve(jsonResponse(scenarios));
      if (url.includes("/examples/five-axis-f3")) {
        const scenarioId = new URL(url, "http://test").searchParams.get("scenarioId") ?? "smoothstep-certified";
        return Promise.resolve(jsonResponse(f3Example(scenarioId)));
      }
      if (url.endsWith("/runs/evaluate")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { request?: { scenarioId?: string }; subjectId?: string };
        const scenarioId = body.request?.scenarioId ?? (body.subjectId?.includes("zoh-moving-unsupported") ? "zoh-moving-unsupported" : "smoothstep-certified");
        return Promise.resolve(jsonResponse(f3RunBundle(scenarioId)));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<F3Workbench catalog={catalog} />);

    expect(await screen.findByText("时域与采样实验室")).toBeInTheDocument();
    expect(screen.getAllByText("MATH ONLY / NOT DEVICE SAFE")).toHaveLength(2);
    expect(screen.getByText("ContinuouslyFeasible")).toBeInTheDocument();
    expect(screen.getByText("IntervalCertified")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /sigma\(t\) 与时间分段/ })).toBeInTheDocument();
    expect(screen.getByText("误差账本")).toBeInTheDocument();
    expect(screen.getByText("sampled trajectory")).toBeInTheDocument();
    expect(screen.getAllByTitle(hashD).length).toBeGreaterThan(0);
    // Regression: ISSUE-002 — the UI read claimId instead of the API claimDefinitionId.
    // Found by /qa on 2026-08-12.
    // Report: .gstack/qa-reports/qa-report-localhost-2026-08-12.md
    const verdictCard = screen.getByText("CLAIM VERDICT").closest(".verdict-card");
    expect(verdictCard).not.toBeNull();
    expect(within(verdictCard as HTMLElement).getByText("Supported")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("场景"), { target: { value: "zoh-moving-unsupported" } });
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes("scenarioId=zoh-moving-unsupported"))).toBe(true));
    await waitFor(() => expect(screen.getAllByText("Inconclusive")).not.toHaveLength(0));
    expect(screen.getByText("discrete command")).toBeInTheDocument();
    expect(screen.getAllByText("five-axis.reconstruction.zoh@1").length).toBeGreaterThan(0);
    expect(screen.queryByText("暂无采样记录")).not.toBeInTheDocument();
    expect(screen.queryByText("暂无区间证书")).not.toBeInTheDocument();
    expect(screen.getAllByTitle(hashC).length).toBeGreaterThan(0);
  });
});
