from __future__ import annotations

from fastapi.testclient import TestClient

import axiom.web as web_module
from axiom.web import create_app


class _PhysicalR4Service:
    def load_r4_manifest(self) -> dict[str, object]:
        return {
            "manifestId": "physical.r4-manifest@1",
            "schemaId": "physical.r4-manifest@1",
            "schemaVersion": 1,
            "stage": "R4",
            "domainPackId": "five-axis.domain-pack@6",
            "platform": "windows",
            "safetyBanner": "MODEL VALIDATION / NOT DEVICE SAFE",
            "validationBanner": "SYNTHETIC SIL / REALITY VALIDATION OPEN",
            "model": {
                "equations": ["x[k+1] = Ad x[k] + Bd u[k]", "y[k] = Cd x[k] + Dd u[k]"],
                "stateIds": ["x_pos", "x_vel"],
                "inputIds": ["u_cmd"],
                "outputIds": ["y_axis"],
                "discretization": "exact-zoh",
                "supportedDevices": ["sim-5x-windows"],
                "operatingConditions": ["warm spindle", "fixture torque nominal"],
                "unmodeledFactors": ["backlash drift"],
            },
        }

    def list_r4_scenarios(self) -> list[dict[str, object]]:
        return [
            {
                "scenarioId": "in-domain-synthetic-sil",
                "title": "In-Domain Synthetic SIL",
                "description": "Synthetic SIL calibration split with held-out validation and open reality follow-up.",
                "axisIds": ["X", "B", "C"],
            }
        ]

    def r4_example_payload(self, scenario_id: str) -> dict[str, object]:
        if scenario_id != "in-domain-synthetic-sil":
            raise KeyError(f"unknown scenario: {scenario_id}")
        return {
            "manifest": self.load_r4_manifest(),
            "scenario": self.list_r4_scenarios()[0],
            "model": self.load_r4_manifest()["model"],
            "calibration": {
                "datasetId": "cal-set@1",
                "traceId": "trace-cal",
                "scenarioRole": "calibration",
                "sourceId": "axiom.windows-file-telemetry-source@1",
                "capturedAt": "2026-08-11T09:30:00Z",
                "contentHash": "a" * 64,
            },
            "validation": {
                "datasetId": "val-set@1",
                "traceId": "trace-val",
                "scenarioRole": "validation",
                "sourceId": "axiom.windows-file-telemetry-source@1",
                "capturedAt": "2026-08-11T10:00:00Z",
                "contentHash": "b" * 64,
                "leakageGuards": [
                    {
                        "checkId": "split-by-run",
                        "status": "pass",
                        "message": "Calibration and validation runs are disjoint.",
                    },
                ],
            },
            "analysis": {
                "traceArtifactType": "five-axis.physical-response-trace",
                "axes": [
                    {
                        "axisId": "X",
                        "family": "linear-mm",
                        "unit": "mm",
                        "excitationStatus": "excited",
                        "series": {
                            "command": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 10.0}],
                            "simulation": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 9.9}],
                            "observation": [{"time": 0.0, "value": 0.1}, {"time": 1.0, "value": 10.1}],
                        },
                        "metrics": [
                            {
                                "metricId": "x.max-residual",
                                "label": "X max residual",
                                "group": "linear-mm",
                                "value": 0.2,
                                "unit": "mm",
                            }
                        ],
                        "residualDecomposition": [
                            {
                                "componentId": "x.fit",
                                "label": "fit error",
                                "value": 0.1,
                                "unit": "mm",
                                "source": "simulation-observation",
                            }
                        ],
                    },
                    {
                        "axisId": "B",
                        "family": "rotary-rad",
                        "unit": "rad",
                        "excitationStatus": "insufficient",
                        "series": {
                            "command": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.02}],
                            "simulation": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.02}],
                            "observation": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.01}],
                        },
                        "metrics": [],
                        "residualDecomposition": [],
                    },
                    {
                        "axisId": "C",
                        "family": "rotary-rad",
                        "unit": "rad",
                        "excitationStatus": "insufficient",
                        "series": {
                            "command": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.03}],
                            "simulation": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.03}],
                            "observation": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.01}],
                        },
                        "metrics": [],
                        "residualDecomposition": [],
                    },
                ],
                "metrics": [
                    {
                        "metricId": "linear.max",
                        "label": "Linear max abs residual",
                        "group": "linear-mm",
                        "value": 0.2,
                        "unit": "mm",
                    },
                    {
                        "metricId": "rotary.max",
                        "label": "Rotary max abs residual",
                        "group": "rotary-rad",
                        "value": 0.01,
                        "unit": "rad",
                    },
                ],
                "claims": [
                    {
                        "claimId": "r4.validation-window",
                        "title": "Held-out validation stays bounded",
                        "status": "Supported",
                        "statement": "Residual remains within validation threshold.",
                        "evidenceIds": ["fit-report"],
                    },
                    {
                        "claimId": "r4.rotary-coverage",
                        "title": "Rotary validation coverage remains open",
                        "status": "Inconclusive",
                        "statement": "B/C axis excitation is insufficient for a closed validation claim.",
                        "evidenceIds": ["coverage-note"],
                    },
                ],
                "evidence": [
                    {
                        "evidenceId": "fit-report",
                        "kind": "fit",
                        "title": "Validation fit report",
                        "summary": "Exact-ZOH replay stays within threshold.",
                        "contentHash": "c" * 64,
                    },
                    {
                        "evidenceId": "coverage-note",
                        "kind": "validation",
                        "title": "Rotary coverage note",
                        "summary": "Reality validation remains open for B/C axes.",
                        "contentHash": "d" * 64,
                    },
                ],
            },
            "runSpec": None,
        }


def _client() -> TestClient:
    return TestClient(create_app(serve_frontend=False))


def test_physical_r4_endpoints_expose_manifest_scenarios_and_example(monkeypatch) -> None:
    monkeypatch.setattr(web_module, "_load_physical_r4_api", lambda: _PhysicalR4Service())
    client = _client()

    manifest = client.get("/api/v1/physical/r4/manifest")
    scenarios = client.get("/api/v1/physical/r4/scenarios")
    example = client.get(
        "/api/v1/examples/physical-r4",
        params={"scenarioId": "in-domain-synthetic-sil"},
    )

    assert manifest.status_code == 200
    assert manifest.json()["safetyBanner"] == "MODEL VALIDATION / NOT DEVICE SAFE"
    assert manifest.json()["model"]["discretization"] == "exact-zoh"

    assert scenarios.status_code == 200
    assert scenarios.json()[0]["scenarioId"] == "in-domain-synthetic-sil"

    assert example.status_code == 200
    payload = example.json()
    assert payload["calibration"]["scenarioRole"] == "calibration"
    assert payload["validation"]["scenarioRole"] == "validation"
    assert payload["analysis"]["traceArtifactType"] == "five-axis.physical-response-trace"
    assert payload["analysis"]["axes"][0]["series"]["command"][1]["value"] == 10.0
    assert payload["analysis"]["claims"][1]["status"] == "Inconclusive"


def test_physical_r4_unknown_scenario_returns_not_found(monkeypatch) -> None:
    monkeypatch.setattr(web_module, "_load_physical_r4_api", lambda: _PhysicalR4Service())
    client = _client()

    assert client.get("/api/v1/examples/physical-r4", params={"scenarioId": "missing"}).status_code == 404


def test_physical_r4_real_service_exposes_evaluable_windows_contract() -> None:
    client = _client()

    manifest = client.get("/api/v1/physical/r4/manifest")
    scenarios = client.get("/api/v1/physical/r4/scenarios")
    example = client.get("/api/v1/examples/physical-r4")

    assert manifest.status_code == 200
    assert manifest.json()["platform"] == "windows"
    assert manifest.json()["domainPackId"] == "five-axis.domain-pack@6"
    assert scenarios.status_code == 200
    assert len(scenarios.json()) == 6
    assert example.status_code == 200
    assert example.json()["runSpec"]["domainPackId"] == "five-axis.domain-pack@6"
    example_reality_claim = next(
        claim
        for claim in example.json()["analysis"]["claims"]
        if claim["claimDefinitionId"]
        == "five-axis.physical-model-reality-validated-claim@1"
    )
    assert example_reality_claim["status"] == "Inconclusive"

    evaluated = client.post("/api/v1/runs/evaluate", json=example.json()["runSpec"])
    assert evaluated.status_code == 200
    assert evaluated.json()["run"]["caseOutcome"] == "Passed"
    reality_claim = next(
        claim
        for claim in evaluated.json()["claims"]
        if claim["claimDefinitionId"] == "five-axis.physical-model-reality-validated-claim@1"
    )
    assert reality_claim["status"] == "Inconclusive"
