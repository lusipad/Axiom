import type { OptimizationSearchRequest, R6ExamplePayload, R6Manifest, R6ScenarioSummary } from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadR6Manifest(): Promise<R6Manifest> {
  return requestJson<R6Manifest>("/api/v1/optimization/r6/manifest");
}

export function loadR6Scenarios(): Promise<R6ScenarioSummary[]> {
  return requestJson<R6ScenarioSummary[]>("/api/v1/optimization/r6/scenarios");
}

export function loadR6Example(): Promise<R6ExamplePayload> {
  return requestJson<R6ExamplePayload>("/api/v1/examples/optimization-r6");
}

export function runR6Search(request: OptimizationSearchRequest): Promise<R6ExamplePayload> {
  return requestJson<R6ExamplePayload>("/api/v1/optimization/r6/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}
