import type {
  FieldEvidenceAssessmentReport,
  FieldEvidenceAssessmentRequest,
  R41AssessmentRequest,
  R41ExamplePayload,
  R41Manifest,
  R7EAssessmentRequest,
  R7EExamplePayload,
  R7EManifest,
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

export function loadR7EManifest(): Promise<R7EManifest> {
  return requestJson<R7EManifest>("/api/v1/control/r7e/manifest");
}

export function loadR7EExample(): Promise<R7EExamplePayload> {
  return requestJson<R7EExamplePayload>("/api/v1/examples/control-r7e");
}

export function assessR7E(request: R7EAssessmentRequest): Promise<R7EExamplePayload> {
  return requestJson<R7EExamplePayload>("/api/v1/control/r7e/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export function loadR41Manifest(): Promise<R41Manifest> {
  return requestJson<R41Manifest>("/api/v1/physical/r41/manifest");
}

export function loadR41Example(): Promise<R41ExamplePayload> {
  return requestJson<R41ExamplePayload>("/api/v1/examples/physical-r41");
}

export function assessR41(request: R41AssessmentRequest): Promise<R41ExamplePayload> {
  return requestJson<R41ExamplePayload>("/api/v1/physical/r41/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export function assessFieldEvidence(
  request: FieldEvidenceAssessmentRequest,
): Promise<FieldEvidenceAssessmentReport> {
  return requestJson<FieldEvidenceAssessmentReport>("/api/v1/field-evidence/assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}
