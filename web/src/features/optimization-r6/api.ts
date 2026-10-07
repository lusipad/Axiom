import type {
  OptimizationSearchRequest,
  GoalToShadowReport,
  R6ExamplePayload,
  R6Manifest,
  R6ScenarioSummary,
  R6V2ExamplePayload,
  R6V2Manifest,
  R6V2ScenarioSummary,
  R6V2SearchRequest,
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

export function loadR6V2Manifest(): Promise<R6V2Manifest> {
  return requestJson<R6V2Manifest>("/api/v1/optimization/r6v2/manifest");
}

export function loadR6V2Scenarios(): Promise<R6V2ScenarioSummary[]> {
  return requestJson<R6V2ScenarioSummary[]>("/api/v1/optimization/r6v2/scenarios");
}

export function loadR6V2Example(scenarioId: string): Promise<R6V2ExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<R6V2ExamplePayload>(`/api/v1/examples/optimization-r6v2?${query}`);
}

export function runR6V2Search(request: R6V2SearchRequest): Promise<R6V2ExamplePayload> {
  return requestJson<R6V2ExamplePayload>("/api/v1/optimization/r6v2/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export function rehearseGoalToShadow(
  searchRequest: R6V2SearchRequest,
  candidateId: string,
): Promise<GoalToShadowReport> {
  return requestJson<GoalToShadowReport>("/api/v1/control/goal-to-shadow/rehearse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ searchRequest, candidateId }),
  });
}
