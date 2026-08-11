import { executeRun } from "../../api";
import type {
  F4ExamplePayload,
  F4MathStageManifest,
  F4RunBundle,
  F4ScenarioSummary,
} from "./types";

async function requestJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadF4Manifest(): Promise<F4MathStageManifest> {
  return requestJson<F4MathStageManifest>("/api/v1/five-axis/f4/manifest");
}

export function loadF4Scenarios(): Promise<F4ScenarioSummary[]> {
  return requestJson<F4ScenarioSummary[]>("/api/v1/five-axis/f4/scenarios");
}

export function loadF4Example(scenarioId: string): Promise<F4ExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<F4ExamplePayload>(`/api/v1/examples/five-axis-f4?${query}`);
}

export async function executeF4Example(example: F4ExamplePayload): Promise<F4RunBundle> {
  if (!example.runSpec) {
    throw new Error("当前场景不提供 F4 门禁 runSpec。");
  }
  return executeRun(example.runSpec) as Promise<F4RunBundle>;
}
