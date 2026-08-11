import type { Catalog, ExperimentReport, ExperimentSpec, MathStageManifest, RunBundle, RunSpec } from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = body?.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export function loadCatalog(): Promise<Catalog> {
  return requestJson<Catalog>("/api/v1/catalog");
}

export function loadContourExample(): Promise<ExperimentSpec> {
  return requestJson<ExperimentSpec>("/api/v1/examples/contour-ab");
}

export function executeExperiment(spec: ExperimentSpec): Promise<ExperimentReport> {
  return requestJson<ExperimentReport>("/api/v1/experiments/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
}

export function loadFiveAxisManifest(): Promise<MathStageManifest> {
  return requestJson<MathStageManifest>("/api/v1/five-axis/f0/manifest");
}

export function loadFiveAxisExample(): Promise<RunSpec> {
  return requestJson<RunSpec>("/api/v1/examples/five-axis-f0");
}

export function executeRun(spec: RunSpec): Promise<RunBundle> {
  return requestJson<RunBundle>("/api/v1/runs/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
}
