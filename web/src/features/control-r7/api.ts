import type { R7ExamplePayload, R7Manifest, R7ScenarioSummary } from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadR7Manifest(): Promise<R7Manifest> {
  return requestJson<R7Manifest>("/api/v1/control/r7/manifest");
}

export function loadR7Scenarios(): Promise<R7ScenarioSummary[]> {
  return requestJson<R7ScenarioSummary[]>("/api/v1/control/r7/scenarios");
}

export function loadR7Example(scenarioId = "synthetic-shadow-nominal"): Promise<R7ExamplePayload> {
  return requestJson<R7ExamplePayload>(`/api/v1/examples/control-r7?scenarioId=${encodeURIComponent(scenarioId)}`);
}

export function replayR7Scenario(scenarioId: string): Promise<R7ExamplePayload> {
  return requestJson<R7ExamplePayload>("/api/v1/control/r7/replay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenarioId }),
  });
}

