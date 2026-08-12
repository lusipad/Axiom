import type {
  OpcUaTransportEvidence,
  R7CExamplePayload,
  R7CManifest,
  R7CScenarioSummary,
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

export function loadR7CManifest(): Promise<R7CManifest> {
  return requestJson<R7CManifest>("/api/v1/control/r7c/manifest");
}

export function loadR7CScenarios(): Promise<R7CScenarioSummary[]> {
  return requestJson<R7CScenarioSummary[]>("/api/v1/control/r7c/scenarios");
}

export function loadR7CExample(
  scenarioId = "opcua-transport-evidence-open",
): Promise<R7CExamplePayload> {
  return requestJson<R7CExamplePayload>(
    `/api/v1/examples/control-r7c?scenarioId=${encodeURIComponent(scenarioId)}`,
  );
}

export function assessR7CTransport(
  transportEvidence: OpcUaTransportEvidence | null,
): Promise<R7CExamplePayload> {
  return requestJson<R7CExamplePayload>("/api/v1/control/r7c/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transportEvidence }),
  });
}
