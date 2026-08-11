from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def make_request():
    def factory(
        points: list[list[float]],
        required: list[str | dict[str, Any]],
        *,
        semantics: dict[str, Any] | None = None,
        parameter: dict[str, Any] | None = None,
        optional: list[str | dict[str, Any]] | None = None,
        reference_binding: dict[str, Any] | None = None,
        score_profile: dict[str, Any] | None = None,
        case_id: str = "test-case@1",
    ) -> dict[str, Any]:
        artifact: dict[str, Any] = {
            "artifactType": "ordered-point-sequence",
            "schemaVersion": 1,
            "points": points,
        }
        if semantics is not None:
            artifact["semantics"] = semantics
        if parameter is not None:
            artifact["parameter"] = parameter

        case: dict[str, Any] = {
            "caseId": case_id,
            "requiredMetrics": required,
            "optionalMetrics": optional or [],
        }
        if score_profile is not None:
            case["scoreProfile"] = score_profile

        request: dict[str, Any] = {"artifact": artifact, "case": case}
        if reference_binding is not None:
            request["referenceBinding"] = reference_binding
        return request

    return factory
