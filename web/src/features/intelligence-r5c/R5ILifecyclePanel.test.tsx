import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { R5ILifecyclePanel } from "./R5ILifecyclePanel";
import type {
  ConditionalEffectPrediction,
  R5IManifest,
  R5IMonitoringWindowReport,
  R5IPromotionPreflightReport,
  R5IRegistryStatus,
} from "./types";

const safetyBanner = "LOCAL MODEL LIFECYCLE ONLY / EXPLICIT AUTHORIZED TRANSACTION / NO AUTOMATIC PROMOTION / NO DEVICE DEPLOYMENT / NOT DEVICE SAFE";

const manifest: R5IManifest = {
  manifestId: "axiom.intelligence.r5i-manifest@1",
  schemaId: "axiom.intelligence.r5i-manifest@1",
  schemaVersion: 1,
  stage: "R5-I",
  platform: "windows",
  lifecycleScope: "local-conditional-effect-model",
  registryKind: "sqlite-local",
  sourceDossierSchemaId: "axiom.intelligence.model-promotion-readiness-dossier@1",
  sourceHoldoutSchemaId: "axiom.intelligence.candidate-real-holdout-assessment@1",
  promotionDecisionSchemaId: "axiom.intelligence.promotion-decision@1",
  checkIds: Array.from({ length: 7 }, (_, index) => `r5i.check-${index}@1`),
  webStateMutationAllowed: false,
  localCliTransactionRequired: true,
  automaticModelPromotionAllowed: false,
  automaticRollbackAllowed: false,
  automaticDeploymentAllowed: false,
  deviceWriteAllowed: false,
  safetyBanner,
};

const registry: R5IRegistryStatus = {
  schemaId: "axiom.intelligence.model-registry-status@1",
  registryIdentity: "1".repeat(64),
  registryInitialized: true,
  currentModelBundleHash: "2".repeat(64),
  rollbackBaselineModelBundleHash: "3".repeat(64),
  generation: 1,
  latestEvent: {
    eventId: "axiom.intelligence.r5i.activation@1",
    eventKind: "Promotion",
    sourceModelBundleHash: "3".repeat(64),
    targetModelBundleHash: "2".repeat(64),
    rollbackBaselineModelBundleHash: "3".repeat(64),
    generation: 1,
    readbackModelBundleHash: "2".repeat(64),
    readbackGeneration: 1,
    transactionStatus: "Applied",
    deviceWritePerformed: false,
    contentHash: "4".repeat(64),
  },
  modelRegistryWritePerformed: true,
  activationPerformed: true,
  automaticDeploymentAllowed: false,
  deviceWriteAllowed: false,
  permissionLevel: "Offline",
  safetyBanner,
  contentHash: "5".repeat(64),
};

const monitoring: R5IMonitoringWindowReport = {
  schemaId: "axiom.intelligence.model-monitoring-window-report@1",
  registryIdentity: registry.registryIdentity,
  modelBundleHash: registry.currentModelBundleHash ?? "",
  generation: 1,
  targetResults: [
    { targetId: "cycleTimeSeconds", unit: "s", labeledSampleCount: 1, rmse: 0, intervalCoverage: 1, status: "Passed", reasonCode: "TargetPerformanceWithinEnvelope" },
    { targetId: "linearFollowingErrorMaxMm", unit: "mm", labeledSampleCount: 1, rmse: 0, intervalCoverage: 1, status: "Passed", reasonCode: "TargetPerformanceWithinEnvelope" },
  ],
  checks: [],
  monitoringStatus: "Healthy",
  rollbackRequired: false,
  automaticRollbackAllowed: false,
  automaticDeploymentAllowed: false,
  deviceWriteAllowed: false,
  permissionLevel: "Offline",
  safetyBanner,
  contentHash: "6".repeat(64),
};

const preflight: R5IPromotionPreflightReport = {
  schemaId: "axiom.intelligence.promotion-preflight-report@1",
  requestContentHash: "7".repeat(64),
  candidateModelBundleHash: "2".repeat(64),
  rollbackBaselineModelBundleHash: "3".repeat(64),
  checks: manifest.checkIds.map((checkId) => ({ checkId, status: "Passed", evidenceHash: "8".repeat(64), reasonCode: "Passed" })),
  overallStatus: "Passed",
  promotionTransactionStatus: "Eligible",
  reviewDecisionStatus: "Approved",
  authorizationVerified: true,
  registryTransactionAllowed: true,
  realWorldGeneralizationStatus: "CaseScopedPassed",
  modelPromotionStatus: "NotPerformed",
  modelRegistryWritePerformed: false,
  activationPerformed: false,
  defaultModelChanged: false,
  automaticModelPromotionAllowed: false,
  automaticDeploymentAllowed: false,
  deviceWriteAllowed: false,
  permissionLevel: "Offline",
  safetyBanner,
  contentHash: "9".repeat(64),
};

const prediction: ConditionalEffectPrediction = {
  schemaId: "axiom.intelligence.conditional-effect-prediction@1",
  modelBundleHash: "2".repeat(64),
  feedOverride: 0.825,
  samplePeriod: 0.08,
  status: "Predicted",
  predictions: [
    { targetId: "cycleTimeSeconds", unit: "s", value: 1.25, lower: 1.2, upper: 1.3 },
    { targetId: "linearFollowingErrorMaxMm", unit: "mm", value: 0.012, lower: 0.01, upper: 0.014 },
  ],
  realWorldGeneralizationStatus: "Open",
  permissionLevel: "Offline",
  deviceWriteAllowed: false,
  contentHash: "a".repeat(64),
};

function response(value: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
}

afterEach(() => vi.restoreAllMocks());

it("只读展示本机 Registry，并允许预检和默认模型推理但不暴露生命周期写操作", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.endsWith("/r5i/manifest")) return response(manifest);
    if (url.endsWith("/r5i/registry/status")) return response(registry);
    if (url.includes("/r5i/monitoring/windows")) return response([monitoring]);
    if (url.endsWith("/r5i/promotion/preflight")) return response(preflight);
    if (url.endsWith("/r5i/predict")) return response(prediction);
    throw new Error(`unexpected request: ${url}`);
  });
  render(<R5ILifecyclePanel />);

  await screen.findByText("Generation 1");
  expect(screen.getByText(safetyBanner)).toBeInTheDocument();
  expect(screen.getByText("Healthy")).toBeInTheDocument();
  expect(screen.getByText("网页没有 promote / activate / rollback API")).toBeInTheDocument();

  const request = {
    schemaId: "axiom.intelligence.promotion-preflight-request@1",
    schemaVersion: 1,
  };
  const file = new File([JSON.stringify(request)], "promotion.json", { type: "application/json" });
  Object.defineProperty(file, "text", {
    value: () => Promise.resolve(JSON.stringify(request)),
  });
  fireEvent.change(screen.getByLabelText("导入 R5-I 提升预检请求"), {
    target: { files: [file] },
  });
  await screen.findByText("promotion.json");
  fireEvent.click(screen.getByRole("button", { name: "只读预检" }));

  const preflightResult = await screen.findByLabelText("R5-I 提升预检结果");
  expect(preflightResult).toHaveTextContent("Eligible");
  expect(preflightResult).toHaveTextContent("registry write false");

  fireEvent.click(screen.getByRole("button", { name: "使用当前默认模型" }));
  await screen.findByText("1.250000 s");
  expect(screen.getByText("0.01200000 mm")).toBeInTheDocument();

  expect(screen.queryByRole("button", { name: /promote|activate|rollback|晋升|激活|回滚/i })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) => /\/r5i\/(promote|activate|rollback)/.test(String(input)))).toBe(false);
  const preflightCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/r5i/promotion/preflight"));
  expect(JSON.parse(String(preflightCall?.[1]?.body))).toEqual({ request });
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
});
