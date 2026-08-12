import type {
  R7DAssessmentRequest,
  R7DExamplePayload,
  R7DManifest,
  R7DScenarioSummary,
} from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadR7DManifest(): Promise<R7DManifest> {
  return requestJson<R7DManifest>("/api/v1/control/r7d/manifest");
}

export function loadR7DScenarios(): Promise<R7DScenarioSummary[]> {
  return requestJson<R7DScenarioSummary[]>("/api/v1/control/r7d/scenarios");
}

export function loadR7DExample(
  scenarioId = "beckhoff-twincat-runtime-open",
): Promise<R7DExamplePayload> {
  return requestJson<R7DExamplePayload>(
    `/api/v1/examples/control-r7d?scenarioId=${encodeURIComponent(scenarioId)}`,
  );
}

export function assessR7DEvidence(request: R7DAssessmentRequest): Promise<R7DExamplePayload> {
  return requestJson<R7DExamplePayload>("/api/v1/control/r7d/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}
