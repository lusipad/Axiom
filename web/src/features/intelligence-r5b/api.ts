import { executeRun } from "../../api";
import type { RunBundle } from "../../types";
import type {
  R5BExamplePayload,
  R5BManifest,
  R5BRunSpec,
  R5BScenarioSummary,
  RealHoldoutIntakeReport,
  RealHoldoutIntakeRequest,
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

export function loadR5BManifest(): Promise<R5BManifest> {
  return requestJson<R5BManifest>("/api/v1/intelligence/r5b/manifest");
}

export function loadR5BScenarios(): Promise<R5BScenarioSummary[]> {
  return requestJson<R5BScenarioSummary[]>("/api/v1/intelligence/r5b/scenarios");
}

export function loadR5BExample(scenarioId: string): Promise<R5BExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<R5BExamplePayload>(`/api/v1/examples/intelligence-r5b?${query}`);
}

export function executeR5BRunSpec(runSpec: R5BRunSpec): Promise<RunBundle> {
  return executeRun(runSpec);
}

export async function assessRealHoldoutIntake(
  request: RealHoldoutIntakeRequest,
): Promise<RealHoldoutIntakeReport> {
  const response = await fetch("/api/v1/intelligence/r5b/intake/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<RealHoldoutIntakeReport>;
}
