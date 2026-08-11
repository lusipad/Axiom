from __future__ import annotations

import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

import pytest

from axiom import ORDERED_POINT_DOMAIN_PACK, evaluate


SUITE_DIR = Path(__file__).parents[1] / "fixtures" / "r1_acceptance"
MANIFEST = json.loads((SUITE_DIR / "manifest.json").read_text(encoding="utf-8"))
CASES = MANIFEST["cases"]


def _load_case(case: dict[str, Any]) -> dict[str, Any]:
    return json.loads((SUITE_DIR / case["file"]).read_text(encoding="utf-8"))


def _assert_metric_value(actual: Any, expected_contract: dict[str, Any]) -> None:
    expected_value = expected_contract.get("value")
    tolerance = expected_contract.get("numericTolerance")
    if (
        tolerance is not None
        and expected_value is not None
        and isinstance(expected_value, Real)
        and not isinstance(expected_value, bool)
    ):
        assert isinstance(actual, Real) and not isinstance(actual, bool)
        assert math.isclose(
            actual,
            expected_value,
            rel_tol=tolerance["relative"],
            abs_tol=tolerance["absolute"],
        )
        return
    assert actual == expected_value


def _domain_metric_definitions() -> dict[str, dict[str, Any]]:
    pack = ORDERED_POINT_DOMAIN_PACK.model_dump(mode="json", by_alias=True, exclude_none=False)
    return {item["metricId"]: item for item in pack["metricDefinitions"]}


def test_r1_fixture_manifest_lists_every_contract_file():
    listed_files = {case["file"] for case in CASES}
    actual_files = {
        path.relative_to(SUITE_DIR).as_posix()
        for path in SUITE_DIR.glob("*.json")
        if path.name != "manifest.json"
    }

    assert listed_files == actual_files
    assert len({case["id"] for case in CASES}) == len(CASES)
    for case in CASES:
        payload = _load_case(case)
        assert payload["fixtureId"] == case["id"]
        assert payload["request"]["case"]["caseId"] == case["id"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_r1_fixture_replays_with_frozen_public_contract(case: dict[str, Any]) -> None:
    payload = _load_case(case)
    request = payload["request"]
    expected = payload["expected"]

    first = evaluate(request)
    second = evaluate(request)

    assert first.model_dump(mode="json", by_alias=True, exclude_none=False) == second.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=False,
    )
    assert first.execution_status.value == expected["executionStatus"]
    assert first.case_outcome.value == expected["caseOutcome"]
    assert {item.capability_id for item in first.capabilities} == set(expected["capabilityIds"])
    assert first.provenance is not None
    assert first.provenance.runner_id == expected["runnerId"]
    assert first.provenance.evaluator_version == expected["evaluatorVersion"]
    assert first.provenance.execution_outcome_policy == expected["executionOutcomePolicy"]

    for metric_id, metric_expected in expected["metricResults"].items():
        metric = first.metric_result(metric_id)
        assert metric.metric_definition_id == metric_expected["metricDefinitionId"]
        assert metric.status.value == metric_expected["status"]
        _assert_metric_value(metric.value, metric_expected)
        if "unit" in metric_expected:
            assert metric.unit == metric_expected["unit"]
        if "reasonCode" in metric_expected:
            assert metric.reason_code == metric_expected["reasonCode"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_r1_fixture_metric_definition_contracts_match_domain_pack(case: dict[str, Any]) -> None:
    payload = _load_case(case)
    actual_definitions = _domain_metric_definitions()
    errors: list[str] = []

    for metric_id, expected_contract in payload.get("metricDefinitionContracts", {}).items():
        actual = actual_definitions.get(metric_id)
        if actual is None:
            errors.append(
                f"{payload['fixtureId']} / {metric_id}: DomainPack is missing this MetricDefinition; "
                f"expected fields {sorted(expected_contract)}"
            )
            continue
        for field, expected_value in expected_contract.items():
            if field not in actual:
                errors.append(
                    f"{payload['fixtureId']} / {metric_id}: DomainPack MetricDefinition is missing "
                    f"field `{field}`; expected {expected_value!r}"
                )
                continue
            if actual[field] != expected_value:
                errors.append(
                    f"{payload['fixtureId']} / {metric_id}: field `{field}` is {actual[field]!r}; "
                    f"expected {expected_value!r}"
                )

    assert not errors, "\n".join(errors)
