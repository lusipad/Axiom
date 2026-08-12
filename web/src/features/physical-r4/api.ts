import type {
  PhysicalR4ExamplePayload,
  PhysicalR4Manifest,
  PhysicalR4ScenarioSummary,
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

export function loadPhysicalR4Manifest(): Promise<PhysicalR4Manifest> {
  return requestJson<PhysicalR4Manifest>("/api/v1/physical/r4/manifest");
}

export function loadPhysicalR4Scenarios(): Promise<PhysicalR4ScenarioSummary[]> {
  return requestJson<PhysicalR4ScenarioSummary[]>("/api/v1/physical/r4/scenarios");
}

export function loadPhysicalR4Example(scenarioId: string): Promise<PhysicalR4ExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<PhysicalR4ExamplePayload>(`/api/v1/examples/physical-r4?${query}`);
}
