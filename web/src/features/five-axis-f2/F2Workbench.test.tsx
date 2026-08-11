import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Catalog } from "../../types";
import { F2Workbench } from "./F2Workbench";
import type { F2ExamplePayload, F2RunBundle, F2ScenarioSummary } from "./types";

const summaries: F2ScenarioSummary[] = [
  {
    scenarioId: "canonical-table-table",
    title: "双转台 AC：连续提升",
    description: "闭式 IK 与完整 Q_free 区间证书。",
    topology: "dual-table",
    expectedClaimStatusById: {
      "five-axis.kinematically-feasible-claim@1": "Supported",
      "five-axis.configuration-collision-free-claim@1": "Supported",
    },
  },
  {
    scenarioId: "configuration-interior-collision",
    title: "区间内部机构碰撞",
    description: "端点分离、区间内部相交。",
    topology: "dual-table",
    expectedClaimStatusById: {
      "five-axis.kinematically-feasible-claim@1": "Supported",
      "five-axis.configuration-collision-free-claim@1": "Refuted",
    },
  },
];

const catalog: Catalog = {
  subjects: [],
  domainPacks: [{
    domainPackId: "five-axis.domain-pack@3",
    comparisonPolicyIds: [],
    runnerIds: ["artifact-import@1"],
    runtimeBound: true,
  }],
  artifactAdapters: [],
};

function example(scenarioId: string): F2ExamplePayload {
  const collision = scenarioId === "configuration-interior-collision";
  const axes = [
    { axisId: "X", axisOrder: 0, jointType: "prismatic", installationSide: "tool", semanticRole: "linear-x", direction: [1, 0, 0], limits: { lower: -500, upper: 500, unit: "mm" }, periodic: false },
    { axisId: "Y", axisOrder: 1, jointType: "prismatic", installationSide: "tool", semanticRole: "linear-y", direction: [0, 1, 0], limits: { lower: -500, upper: 500, unit: "mm" }, periodic: false },
    { axisId: "Z", axisOrder: 2, jointType: "prismatic", installationSide: "tool", semanticRole: "linear-z", direction: [0, 0, 1], limits: { lower: -500, upper: 500, unit: "mm" }, periodic: false },
    { axisId: "A", axisOrder: 3, jointType: "revolute", installationSide: "workpiece", semanticRole: "tilt-a", direction: [1, 0, 0], limits: { lower: -2.09, upper: 2.09, unit: "rad" }, periodic: false },
    { axisId: "C", axisOrder: 4, jointType: "revolute", installationSide: "workpiece", semanticRole: "spin-c", direction: [0, 0, 1], limits: { lower: -6.28, upper: 6.28, unit: "rad" }, periodic: true },
  ] as const;
  const summary = summaries.find((item) => item.scenarioId === scenarioId) ?? summaries[0]!;
  return {
    manifest: {
      manifestId: "five-axis.f2-math-stage-manifest@1",
      schemaId: "five-axis.f2-math-stage-manifest@1",
      schemaVersion: 1,
      stage: "F2",
      artifactDescriptors: ["M0", "M1", "M2", "M3"].map((stage) => ({
        stage: stage as "M0" | "M1" | "M2" | "M3",
        artifactType: `five-axis.${stage.toLowerCase()}-artifact`,
        schemaId: `five-axis.${stage.toLowerCase()}-artifact@1`,
      })),
      machineProfileSchemaId: "five-axis.machine-profile@1",
      machineProfileId: "five-axis.machine-profile.canonical-table-table-ac@1",
      machineProfileContentId: "machine-content-1234567890",
      capabilityIds: [], fixtureContentIds: ["collision-content-1234567890"],
      policyIds: ["five-axis.closed-form-ik-policy@1"], numericEnvironment: {},
      expectedMetrics: [], expectedClaims: [], expectedEvidence: [], tolerances: [], decisions: [],
    },
    scenario: summary,
    source: {
      sourceText: "UNITS/MM\nFROM/-0.8,0,0,0.2,0.1,0.9747\nGOTO/0.8,0,0\nEND\n",
      normalizedProgram: { artifactType: "five-axis.normalized-program", schemaVersion: 1, programId: "program.1", sourceSyntaxId: "axiom-cl-subset@1", coordinateContext: { unit: "mm", coordinateFrame: "machine" }, events: [] },
      referencePath: {} as F2ExamplePayload["source"]["referencePath"],
    },
    artifacts: {
      candidateGeometry: {} as F2ExamplePayload["artifacts"]["candidateGeometry"],
      machineProfile: { artifactType: "five-axis.machine-profile", schemaVersion: 1, profileId: "five-axis.machine-profile.canonical-table-table-ac@1", profileVersion: 1, topology: "dual-table", axes: [...axes] },
      axisPath: {
        artifactType: "five-axis.m3-candidate-axis-path", schemaVersion: 1, axisPathId: "axis-path.1",
        sourceCandidateGeometryContentId: "m2-content-1234567890", machineProfileContentId: "machine-content-1234567890",
        machineProfile: { artifactType: "five-axis.machine-profile", schemaVersion: 1, profileId: "five-axis.machine-profile.canonical-table-table-ac@1", profileVersion: 1, topology: "dual-table", axes: [...axes] },
        ikSolutions: [
          { solutionId: "ik.0", sigma: 0, branchId: "ac-primary.wrap.c0", jointValues: [-0.4, -0.2, 100, 0.2, 1.1], wrapState: [{ axisId: "C", turns: 0 }], singularity: { status: "regular", minimumSingularValue: 0.18 }, withinLimits: true },
          { solutionId: "ik.1", sigma: 1, branchId: "ac-primary.wrap.c0", jointValues: [0.4, 0.2, 100.2, 0.2, 1.1], wrapState: [{ axisId: "C", turns: 0 }], singularity: { status: "regular", minimumSingularValue: 0.18 }, withinLimits: true },
        ],
        branchGraph: { graphId: "graph.1", rootBranchIds: ["ac-primary.wrap.c0"], branches: [{ branchId: "ac-primary.wrap.c0", sigmaStart: 0, sigmaEnd: 1, solutionIds: ["ik.0", "ik.1"], status: "active" }, { branchId: "ac-secondary.wrap.c0", sigmaStart: 0, sigmaEnd: 1, solutionIds: [], status: "active" }], transitions: [] },
        jointSegments: [{ segmentId: "segment.1", branchId: "ac-primary.wrap.c0", sigmaStart: 0, sigmaEnd: 1, interpolation: "linear", coefficientBasis: "local-power@1", coefficients: [[-0.4, -0.2, 100, 0.2, 1.1], [0.8, 0.4, 0.2, 0, 0]] }],
        nodeEvents: [],
        kinematicsCertificate: { certificateId: "kinematics.1", evidenceLevel: "Exact", continuousMethod: "five-axis.linear-fixed-branch-lift@1", selectedBranchId: "ac-primary.wrap.c0", intervalCount: 1, positionResidualUpperBound: 0, orientationResidualUpperBound: 0, axisLimitNormalizedMarginLowerBound: 0.33, minimumSingularValueLowerBound: 0.18, policyIds: ["five-axis.closed-form-ik-policy@1"] },
      },
      collisionModel: {
        modelId: "collision.1", contentId: "collision-content-1234567890", policyId: "five-axis.configuration-collision.explicit-pairs@1", coverageStatus: "complete", coveredPairKinds: ["machine-self", "environment"],
        entities: [{ entityId: "x-carriage", entityKind: "machine-component", anchorType: "axis", anchorAxisId: "X" }, { entityId: "column", entityKind: "machine-component", anchorType: "base" }],
        pairs: [{ pairId: "self.1", pairKind: "machine-self", leftEntityId: "x-carriage", rightEntityId: "column" }],
      },
    },
    runSpec: { subjectId: `five-axis.f2.${scenarioId}@1`, domainPackId: "five-axis.domain-pack@3", runnerId: "artifact-import@1", evaluatorVersion: "five-axis-f2-evaluator@1", request: {} },
  } as unknown as F2ExamplePayload;
}

function runBundle(scenarioId: string): F2RunBundle {
  const collisionFree = scenarioId !== "configuration-interior-collision";
  const collisionEvaluation = {
    queryKind: "path" as const, status: collisionFree ? "safe" : "collision", collisionFree,
    certificateKind: collisionFree ? "proof" : "counterexample", reasonCode: collisionFree ? "ConfigurationCollisionCertified" : "ConfigurationCollisionDetected",
    evidenceLevel: collisionFree ? "Certified" : "Observed", continuousMethod: "five-axis.configuration-collision.path-aggregate@1",
    minimumClearanceLowerBound: collisionFree ? 99.5 : 0, clearanceUnit: "mm", evaluationCount: 9, subdivisionCount: 3,
    pairResults: [{ pairId: "self.1", pairKind: "machine-self", status: collisionFree ? "safe" : "collision", reasonCode: collisionFree ? "ContinuousClearanceCertified" : "CollisionWitnessFound", minimumClearanceLowerBound: collisionFree ? 99.5 : 0, witnessSigma: collisionFree ? undefined : 0.5 }],
  };
  return {
    run: { runId: "run.1", subjectId: `five-axis.f2.${scenarioId}@1`, domainPackId: "five-axis.domain-pack@3", runnerId: "artifact-import@1", runSpecHash: "spec-hash", reportContentHash: "report-hash", executionStatus: "Succeeded", caseOutcome: "Passed", evaluatorVersion: "five-axis-f2-evaluator@1", contentHash: "run-hash" },
    report: {
      executionStatus: "Succeeded", caseOutcome: "Passed",
      metricResults: [
        { metricId: "five-axis.kinematically-feasible@1", status: "Computed", value: true, evidence: { level: "Exact", method: "five-axis.f2.linear-fixed-branch-lift-closure@1" } },
        { metricId: "five-axis.configuration-collision-free@1", status: "Computed", value: collisionFree, evidence: { level: collisionFree ? "Certified" : "Observed", method: "five-axis.f2.configuration-collision-closure@1" }, details: { collisionEvaluation } },
        { metricId: "five-axis.position-residual.max@1", status: "Computed", value: 0, unit: "mm", evidence: { level: "Exact", method: "fk-replay" } },
        { metricId: "five-axis.orientation-residual.max@1", status: "Computed", value: 0, unit: "rad", evidence: { level: "Exact", method: "fk-replay" } },
        { metricId: "five-axis.axis-limit-margin.min@1", status: "Computed", value: 0.33, unit: "dimensionless", evidence: { level: "Exact", method: "limit-replay" } },
        { metricId: "five-axis.singularity.minimum-singular-value@1", status: "Computed", value: 0.18, unit: "dimensionless", evidence: { level: "Exact", method: "jacobian-replay" } },
      ],
    },
    claims: [
      { claimId: "claim.kinematics", status: "Supported", predicate: "five-axis.KinematicallyFeasible is true", metricId: "five-axis.kinematically-feasible@1", evidence: { level: "Exact", method: "kinematics-closure" } },
      { claimId: "claim.collision", status: collisionFree ? "Supported" : "Refuted", predicate: `five-axis.ConfigurationCollisionFree is ${collisionFree}`, metricId: "five-axis.configuration-collision-free@1", evidence: { level: collisionFree ? "Certified" : "Observed", method: "collision-closure" } },
    ],
    bundleHash: `bundle-${scenarioId}`,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("Five-Axis F2 workbench", () => {
  it("展示连续轴路径、数学安全边界和独立复算声明", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/five-axis/f2/scenarios")) return Promise.resolve(jsonResponse(summaries));
      if (url.includes("/examples/five-axis-f2")) return Promise.resolve(jsonResponse(example("canonical-table-table")));
      if (url.endsWith("/runs/evaluate")) return Promise.resolve(jsonResponse(runBundle("canonical-table-table")));
      return Promise.resolve(jsonResponse({}, 404));
    }));

    render(<F2Workbench catalog={catalog} />);

    expect(await screen.findByText("五轴运动学实验室")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /五轴坐标随路径进度变化/ })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("不是 DeviceSafe");
    expect(screen.getByText("Runtime binding").parentElement).toHaveTextContent("Bound");
    expect(screen.getAllByText("Supported").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: "M3 sealed · 2" })).toBeInTheDocument();
  });

  it("切换到区间内部碰撞场景并展示反例 witness", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/five-axis/f2/scenarios")) return Promise.resolve(jsonResponse(summaries));
      if (url.includes("/examples/five-axis-f2")) {
        const id = new URL(url, "http://test").searchParams.get("scenarioId") ?? "canonical-table-table";
        return Promise.resolve(jsonResponse(example(id)));
      }
      if (url.endsWith("/runs/evaluate")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { subjectId?: string };
        const id = body.subjectId?.includes("interior-collision") ? "configuration-interior-collision" : "canonical-table-table";
        return Promise.resolve(jsonResponse(runBundle(id)));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<F2Workbench catalog={catalog} />);
    await screen.findByText("五轴运动学实验室");
    fireEvent.change(screen.getByLabelText("场景"), { target: { value: "configuration-interior-collision" } });

    await waitFor(() => expect(screen.getAllByText("Refuted").length).toBeGreaterThanOrEqual(1));
    expect(screen.getByText("case: Passed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Q_free 碰撞" }));
    expect(await screen.findByText("0.500000")).toBeInTheDocument();
    expect(screen.getAllByText("collision").length).toBeGreaterThanOrEqual(1);
  });
});
