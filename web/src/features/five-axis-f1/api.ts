import { executeRun } from "../../api";
import type { F1ExamplePayload, F1RunBundle, F1ScenarioSummary } from "./types";

async function requestJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadF1Scenarios(): Promise<F1ScenarioSummary[]> {
  return requestJson<F1ScenarioSummary[]>("/api/v1/five-axis/f1/scenarios");
}

export function loadF1Example(scenarioId: string): Promise<F1ExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<F1ExamplePayload>(`/api/v1/examples/five-axis-f1?${query}`);
}

export async function executeF1Example(example: F1ExamplePayload): Promise<F1RunBundle> {
  return executeRun(example.runSpec) as Promise<F1RunBundle>;
}
