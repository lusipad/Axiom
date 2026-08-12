import { executeRun } from "../../api";
import type {
  MachineR3ExamplePayload,
  MachineR3Manifest,
  MachineR3RunBundle,
  MachineR3ScenarioSummary,
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

export function loadMachineR3Manifest(): Promise<MachineR3Manifest> {
  return requestJson<MachineR3Manifest>("/api/v1/machine/r3/manifest");
}

export function loadMachineR3Scenarios(): Promise<MachineR3ScenarioSummary[]> {
  return requestJson<MachineR3ScenarioSummary[]>("/api/v1/machine/r3/scenarios");
}

export function loadMachineR3Example(scenarioId: string): Promise<MachineR3ExamplePayload> {
  const query = new URLSearchParams({ scenarioId });
  return requestJson<MachineR3ExamplePayload>(`/api/v1/examples/machine-r3?${query}`);
}

export async function executeMachineR3Example(example: MachineR3ExamplePayload): Promise<MachineR3RunBundle> {
  if (!example.runSpec) {
    throw new Error("当前场景不提供 Machine R3 runSpec。");
  }
  return executeRun(example.runSpec) as Promise<MachineR3RunBundle>;
}
