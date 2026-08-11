import { executeRun } from "../../api";
import type { F3ExamplePayload, F3MathStageManifest, F3RunBundle, F3ScenarioSummary } from "./types";

async function requestJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadF3Manifest(): Promise<F3MathStageManifest> {
  return requestJson<F3MathStageManifest>("/api/v1/five-axis/f3/manifest");
}

export function loadF3Scenarios(): Promise<F3ScenarioSummary[]> {
  return requestJson<F3ScenarioSummary[]>("/api/v1/five-axis/f3/scenarios");
}

export function loadF3Example(scenarioId: string): Promise<F3ExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<F3ExamplePayload>(`/api/v1/examples/five-axis-f3?${query}`);
}

export async function executeF3Example(example: F3ExamplePayload): Promise<F3RunBundle> {
  return executeRun(example.runSpec) as Promise<F3RunBundle>;
}
