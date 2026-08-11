import { executeRun } from "../../api";
import type { F2ExamplePayload, F2RunBundle, F2ScenarioSummary } from "./types";

async function requestJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadF2Scenarios(): Promise<F2ScenarioSummary[]> {
  return requestJson<F2ScenarioSummary[]>("/api/v1/five-axis/f2/scenarios");
}

export function loadF2Example(scenarioId: string): Promise<F2ExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<F2ExamplePayload>(`/api/v1/examples/five-axis-f2?${query}`);
}

export async function executeF2Example(example: F2ExamplePayload): Promise<F2RunBundle> {
  return executeRun(example.runSpec) as Promise<F2RunBundle>;
}
