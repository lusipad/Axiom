import type {
  R7BEvidenceSet,
  R7BExamplePayload,
  R7BManifest,
  R7BScenarioSummary,
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

export function loadR7BManifest(): Promise<R7BManifest> {
  return requestJson<R7BManifest>("/api/v1/control/r7b/manifest");
}

export function loadR7BScenarios(): Promise<R7BScenarioSummary[]> {
  return requestJson<R7BScenarioSummary[]>("/api/v1/control/r7b/scenarios");
}

export function loadR7BExample(scenarioId = "deployment-shadow-readiness-open"): Promise<R7BExamplePayload> {
  return requestJson<R7BExamplePayload>(`/api/v1/examples/control-r7b?scenarioId=${encodeURIComponent(scenarioId)}`);
}

export function assessR7BEvidence(evidenceSet: R7BEvidenceSet | null): Promise<R7BExamplePayload> {
  return requestJson<R7BExamplePayload>("/api/v1/control/r7b/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ evidenceSet }),
  });
}
