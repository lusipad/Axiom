import type {
  ConditionalEffectPrediction,
  ConditionalEffectPredictionRequest,
  R5DExperimentPlanRequest,
  R5DManifest,
  R5ECampaignApprovalCommand,
  R5EManifest,
  R5ESyntheticCampaignReport,
  R5ESyntheticCampaignRequest,
  R5FCandidateImpactReport,
  R5FManifest,
  R5GManifest,
  R5GModelPromotionReadinessDossier,
  R5HCandidateHoldoutAssessment,
  R5HCandidateHoldoutCaseSpec,
  R5HCandidateHoldoutStudyRegistrationReport,
  R5HManifest,
  R5IManifest,
  R5IMonitoringWindowReport,
  R5IPromotionPreflightReport,
  R5IRegistryStatus,
  R5CExamplePayload,
  R5CManifest,
  R5CScenarioSummary,
  SimulationExperimentPlan,
} from "./types";
import type { FieldEvidenceAssessmentReport } from "../field-evidence/types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function stringifyJsonPreservingNegativeZero(value: unknown): string {
  if (Object.is(value, -0)) return "-0.0";
  if (value === null || typeof value === "string" || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stringifyJsonPreservingNegativeZero(item)).join(",")}]`;
  }
  if (typeof value === "object") {
    const fields = Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .map(([key, item]) => `${JSON.stringify(key)}:${stringifyJsonPreservingNegativeZero(item)}`);
    return `{${fields.join(",")}}`;
  }
  throw new TypeError(`Unsupported JSON value: ${typeof value}`);
}

export function loadR5CManifest(): Promise<R5CManifest> {
  return requestJson<R5CManifest>("/api/v1/intelligence/r5c/manifest");
}

export function loadR5CScenarios(): Promise<R5CScenarioSummary[]> {
  return requestJson<R5CScenarioSummary[]>("/api/v1/intelligence/r5c/scenarios");
}

export function loadR5CExample(scenarioId: string): Promise<R5CExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<R5CExamplePayload>(`/api/v1/examples/intelligence-r5c?${query}`);
}

export function requestR5CPrediction(
  request: ConditionalEffectPredictionRequest,
): Promise<ConditionalEffectPrediction> {
  return requestJson<ConditionalEffectPrediction>("/api/v1/intelligence/r5c/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export function loadR5DManifest(): Promise<R5DManifest> {
  return requestJson<R5DManifest>("/api/v1/intelligence/r5d/manifest");
}

export function requestR5DExperimentPlan(
  request: R5DExperimentPlanRequest,
): Promise<SimulationExperimentPlan> {
  return requestJson<SimulationExperimentPlan>("/api/v1/intelligence/r5d/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export function loadR5EManifest(): Promise<R5EManifest> {
  return requestJson<R5EManifest>("/api/v1/intelligence/r5e/manifest");
}

export function approveR5ESyntheticCampaign(
  command: R5ECampaignApprovalCommand,
): Promise<R5ESyntheticCampaignRequest> {
  return requestJson<R5ESyntheticCampaignRequest>("/api/v1/intelligence/r5e/campaigns/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(command),
  });
}

export function executeR5ESyntheticCampaign(
  request: R5ESyntheticCampaignRequest,
): Promise<R5ESyntheticCampaignReport> {
  return requestJson<R5ESyntheticCampaignReport>("/api/v1/intelligence/r5e/campaigns/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export function loadR5FManifest(): Promise<R5FManifest> {
  return requestJson<R5FManifest>("/api/v1/intelligence/r5f/manifest");
}

export function assessR5FCandidateImpact(
  campaignReport: R5ESyntheticCampaignReport,
): Promise<R5FCandidateImpactReport> {
  return requestJson<R5FCandidateImpactReport>("/api/v1/intelligence/r5f/impact/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ campaignReport }),
  });
}

export function loadR5GManifest(): Promise<R5GManifest> {
  return requestJson<R5GManifest>("/api/v1/intelligence/r5g/manifest");
}

export function prepareR5GPromotionReadiness(
  impactReport: R5FCandidateImpactReport,
  preparedBy: string,
): Promise<R5GModelPromotionReadinessDossier> {
  return requestJson<R5GModelPromotionReadinessDossier>("/api/v1/intelligence/r5g/promotion/readiness", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      impactReport,
      preparedBy,
      realityGateOpenAcknowledged: true,
      deviceSafetyNotEstablishedAcknowledged: true,
      automaticDeploymentForbiddenAcknowledged: true,
    }),
  });
}

export function loadR5HManifest(): Promise<R5HManifest> {
  return requestJson<R5HManifest>("/api/v1/intelligence/r5h/manifest");
}

export function registerR5HCandidateHoldoutStudy(
  readinessDossier: R5GModelPromotionReadinessDossier,
  input: {
    studyId: string;
    createdAt: string;
    registeredAt: string;
    registrationAuthorityId: string;
    registrationRecordId: string;
    cases: R5HCandidateHoldoutCaseSpec[];
  },
): Promise<R5HCandidateHoldoutStudyRegistrationReport> {
  return requestJson<R5HCandidateHoldoutStudyRegistrationReport>("/api/v1/intelligence/r5h/studies/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ readinessDossier, ...input }),
  });
}

export function assessR5HCandidateRealHoldout(
  readinessDossier: R5GModelPromotionReadinessDossier,
  registrationReport: R5HCandidateHoldoutStudyRegistrationReport,
  evidenceReports: FieldEvidenceAssessmentReport[],
): Promise<R5HCandidateHoldoutAssessment> {
  return requestJson<R5HCandidateHoldoutAssessment>("/api/v1/intelligence/r5h/holdout/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: stringifyJsonPreservingNegativeZero({ readinessDossier, registrationReport, evidenceReports }),
  });
}

export function loadR5IManifest(): Promise<R5IManifest> {
  return requestJson<R5IManifest>("/api/v1/intelligence/r5i/manifest");
}

export function loadR5IRegistryStatus(): Promise<R5IRegistryStatus> {
  return requestJson<R5IRegistryStatus>("/api/v1/intelligence/r5i/registry/status");
}

export function loadR5IMonitoringWindows(
  limit = 20,
): Promise<R5IMonitoringWindowReport[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  return requestJson<R5IMonitoringWindowReport[]>(
    `/api/v1/intelligence/r5i/monitoring/windows?${query}`,
  );
}

export function requestR5IPromotionPreflight(
  request: Record<string, unknown>,
): Promise<R5IPromotionPreflightReport> {
  return requestJson<R5IPromotionPreflightReport>(
    "/api/v1/intelligence/r5i/promotion/preflight",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: stringifyJsonPreservingNegativeZero({ request }),
    },
  );
}

export function requestR5IActivePrediction(
  feedOverride: number,
  samplePeriod: number,
): Promise<ConditionalEffectPrediction> {
  return requestJson<ConditionalEffectPrediction>(
    "/api/v1/intelligence/r5i/predict",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedOverride, samplePeriod }),
    },
  );
}
