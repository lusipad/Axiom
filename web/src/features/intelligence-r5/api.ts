import type { R5ExamplePayload, R5Manifest, R5ScenarioSummary } from "./types";

async function requestJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadR5Manifest(): Promise<R5Manifest> {
  return requestJson<R5Manifest>("/api/v1/intelligence/r5/manifest");
}

export function loadR5Scenarios(): Promise<R5ScenarioSummary[]> {
  return requestJson<R5ScenarioSummary[]>("/api/v1/intelligence/r5/scenarios");
}

export function loadR5Example(scenarioId: string): Promise<R5ExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<R5ExamplePayload>(`/api/v1/examples/intelligence-r5?${query}`);
}
