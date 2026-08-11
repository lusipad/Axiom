from __future__ import annotations

import copy
import importlib
import json
import math
import re
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

from axiom import ORDERED_POINT_DOMAIN_PACK, evaluate, register_domain_pack


SUITE_DIR = Path(__file__).parents[1] / "fixtures" / "cnc_scenarios"
MANIFEST = json.loads((SUITE_DIR / "manifest.json").read_text(encoding="utf-8"))
COMPARISON_CASES = MANIFEST["comparisonCases"]


def _load_json(relative_path: str) -> Any:
    return json.loads((SUITE_DIR / relative_path).read_text(encoding="utf-8"))


def _to_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {key: _to_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_data(item) for item in value]
    if hasattr(value, "value") and value.__class__.__module__ == "enum":
        return value.value
    return value


def _get_key(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    available = ", ".join(sorted(mapping))
    raise AssertionError(f"缺少字段 {names!r}，实际字段: {available}")


def _find_key(mapping: dict[str, Any], *names: str) -> Any | None:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _resolve_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    current: Any = payload
    parts = path.split(".")
    for index, part in enumerate(parts[:-1]):
        next_part = parts[index + 1]
        if isinstance(current, list):
            current = current[int(part)]
            continue
        if part not in current:
            current[part] = [] if next_part.isdigit() else {}
        current = current[part]
    leaf = parts[-1]
    if isinstance(current, list):
        current[int(leaf)] = value
    else:
        current[leaf] = value


def _set_runtime_path(payload: Any, path: str, value: Any) -> None:
    current = payload
    parts = path.split(".")
    for part in parts[:-1]:
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            current = getattr(current, _runtime_attr_name(current, part))
    leaf = parts[-1]
    if isinstance(current, list):
        current[int(leaf)] = value
    elif isinstance(current, dict):
        current[leaf] = value
    else:
        attr_name = _runtime_attr_name(current, leaf)
        existing = getattr(current, attr_name)
        if isinstance(existing, Enum) and isinstance(value, str):
            value = existing.__class__(value)
        setattr(current, attr_name, value)


def _runtime_attr_name(instance: Any, part: str) -> str:
    if hasattr(instance, part):
        return part
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", part).lower()
    if hasattr(instance, snake):
        return snake
    return part


def _comparison_manifest(case_id: str) -> dict[str, Any]:
    for case in COMPARISON_CASES:
        if case["id"] == case_id:
            return case
    raise AssertionError(f"manifest.json 未列出 comparison case: {case_id}")


def _load_public_api() -> tuple[Any, Any, Any, Any]:
    axiom_module = importlib.import_module("axiom")
    extra_modules = []
    for module_name in ("axiom.platform", "axiom.registry", "axiom.runs"):
        try:
            extra_modules.append(importlib.import_module(module_name))
        except ModuleNotFoundError:
            continue

    def resolve(name: str, *candidates: str) -> Any:
        for module in (axiom_module, *extra_modules):
            for candidate in candidates:
                if hasattr(module, candidate):
                    return getattr(module, candidate)
        options = ", ".join(candidates)
        raise AssertionError(f"公开 API 缺少 {name}；至少需要提供以下其一: {options}")

    query_pack = resolve("DomainPack 查询入口", "get_domain_pack", "resolve_domain_pack", "load_domain_pack")
    evaluate_run = resolve("Run 评估入口", "evaluate_run", "run_evaluation")
    compare = resolve("ComparisonSpec 比较入口", "compare")
    compare_runs = resolve("RunBundle 比较入口", "compare_runs", "compare_run_reports", "compare_reports")
    return query_pack, evaluate_run, compare, compare_runs


def _resolve_known_pack(query_pack: Any) -> Any:
    known_ids = ("ordered-point.domain-pack@1",)
    for pack_id in known_ids:
        try:
            return query_pack(pack_id)
        except LookupError:
            continue
    raise AssertionError(f"无法通过公开查询入口解析已知 DomainPack，已尝试: {known_ids!r}")


def _comparison_case(case_id: str) -> dict[str, Any]:
    return _load_json(_comparison_manifest(case_id)["file"])


def _evaluate_bundle(evaluate_run: Any, subject_id: str, request: dict[str, Any]) -> dict[str, Any]:
    return evaluate_run({"subjectId": subject_id, "request": request})


def test_comparison_fixture_manifest_lists_all_files():
    listed_files = {case["file"] for case in COMPARISON_CASES}
    actual_files = {
        path.relative_to(SUITE_DIR).as_posix()
        for path in (SUITE_DIR / "comparisons").glob("*.json")
    }

    assert listed_files == actual_files
    for case in COMPARISON_CASES:
        payload = _load_json(case["file"])
        assert "id" not in payload
        assert "expectedMetrics" not in payload


def test_domain_pack_registry_exposes_ordered_point_pack_and_rejects_unknown_ids():
    query_pack, _, _, _ = _load_public_api()

    pack = _to_data(_resolve_known_pack(query_pack))
    assert _get_key(pack, "id", "packId", "domainPackId", "name") == "ordered-point.domain-pack@1"

    metric_definitions = _get_key(pack, "metricDefinitions", "metrics", "supportedMetrics")
    metric_ids = {
        item if isinstance(item, str) else _get_key(item, "id", "metricId", "metricDefinitionId")
        for item in metric_definitions
    }
    assert "path.length.open" in metric_ids
    assert "paired.euclidean.max" in metric_ids
    assert pack["artifactSchemaVersions"] == [1]
    assert "ordered-point.reference.bound@1" in pack["capabilityIds"]
    assert "axiom.core.metric-threshold-claim@1" in pack["claimDefinitionIds"]
    assert pack["comparisonPolicyIds"] == [
        "ordered-point.run-comparison.strict@1",
        "ordered-point.experiment-comparison.strict@1",
    ]

    with pytest.raises(LookupError, match="vendor\\.pack\\.unknown@1"):
        query_pack("vendor.pack.unknown@1")


def test_domain_pack_registration_is_idempotent_but_rejects_conflicting_redefinition():
    assert register_domain_pack(ORDERED_POINT_DOMAIN_PACK) is ORDERED_POINT_DOMAIN_PACK

    conflicting = ORDERED_POINT_DOMAIN_PACK.model_copy(update={"runner_id": "vendor.other-runner@1"})
    with pytest.raises(ValueError, match="ordered-point\\.domain-pack@1"):
        register_domain_pack(conflicting)


def test_registered_domain_pack_without_an_evaluator_binding_is_not_executed():
    _, evaluate_run, _, _ = _load_public_api()
    descriptor_only_pack = ORDERED_POINT_DOMAIN_PACK.model_copy(
        update={"domain_pack_id": "vendor.descriptor-only@1"}
    )
    register_domain_pack(descriptor_only_pack)
    request = _load_json("requests/cnc-contour-observation-pass.json")

    bundle = _to_data(
        evaluate_run(
            {
                "subjectId": "subject-a",
                "domainPackId": descriptor_only_pack.domain_pack_id,
                "request": request,
            }
        )
    )

    assert bundle["run"]["executionStatus"] == "Skipped"
    assert bundle["report"]["caseOutcome"] == "Unsupported"
    assert bundle["report"]["domainFailures"] == [
        {
            "code": "DomainPackEvaluatorUnavailable",
            "message": "The registered DomainPack has no evaluator binding in v0.2.",
            "path": "domainPackId",
            "severity": "error",
        }
    ]


def test_evaluate_run_builds_lineage_and_replays_deterministically():
    _, evaluate_run, _, _ = _load_public_api()
    request = _load_json("requests/cnc-contour-observation-pass.json")
    run_spec = {
        "subjectId": "subject-a",
        "request": request,
    }
    expected_report = evaluate(request).model_dump(mode="json", by_alias=True, exclude_none=True)

    first = _to_data(evaluate_run(run_spec))
    second = _to_data(evaluate_run(run_spec))
    explicit_defaults = _to_data(
        evaluate_run(
            {
                **run_spec,
                "domainPackId": "ordered-point.domain-pack@1",
                "runnerId": "artifact-import@1",
                "evaluatorVersion": "ordered-point-evaluator@1",
            }
        )
    )

    assert first == second
    assert first == explicit_defaults

    run_spec_data = _get_key(first, "runSpec", "run_spec")
    observation = _get_key(first, "observation", "rawObservation")
    report = _get_key(first, "report", "evaluationReport")
    claims = _get_key(first, "claims", "claimSet")

    assert _resolve_path(run_spec_data, "request.case.caseId") == request["case"]["caseId"]
    assert _resolve_path(observation, "artifact.artifactType") == request["artifact"]["artifactType"]
    assert report == expected_report
    assert isinstance(claims, list) and claims
    threshold_claim = next(claim for claim in claims if claim.get("metricId") == "paired.euclidean.max")
    assert threshold_claim["claimDefinitionId"] == "axiom.core.metric-threshold-claim@1"
    assert threshold_claim["status"] == "Supported"
    assert threshold_claim["details"] == {
        "metricId": "paired.euclidean.max",
        "operator": "<=",
        "thresholdValue": 0.03,
        "thresholdUnit": "mm",
        "metricValue": 0.025,
        "resultUnit": "mm",
    }
    assert threshold_claim["evidence"]["level"] == "Observed"
    assert len(first["run"]["runSpecHash"]) == 64
    assert len(observation["observationHash"]) == 64
    assert len(first["bundleHash"]) == 64


def test_equivalent_case_defaults_compare_cleanly_without_erasing_input_identity():
    _, evaluate_run, compare, _ = _load_public_api()
    minimal_request = {
        "artifact": {
            "artifactType": "ordered-point-sequence",
            "schemaVersion": 1,
            "points": [[0, 0], [3, 4]],
        },
        "case": {
            "caseId": "canonical-defaults@1",
            "requiredMetrics": ["path.length.open"],
        },
    }
    explicit_request = copy.deepcopy(minimal_request)
    explicit_request["case"].update(
        {
            "requiredMetrics": [{"metricId": "path.length.open", "threshold": None}],
            "optionalMetrics": [],
            "scoreProfile": None,
            "executionOutcomePolicy": "axiom.core.execution-outcome.default@1",
        }
    )

    minimal_bundle = _to_data(
        evaluate_run({"subjectId": "same-subject", "request": minimal_request})
    )
    explicit_bundle = _to_data(
        evaluate_run({"subjectId": "same-subject", "request": explicit_request})
    )

    assert (
        minimal_bundle["report"]["provenance"]["requestHash"]
        != explicit_bundle["report"]["provenance"]["requestHash"]
    )
    assert (
        minimal_bundle["report"]["provenance"]["caseHash"]
        == explicit_bundle["report"]["provenance"]["caseHash"]
    )

    comparison = _to_data(
        compare(
            {
                "left": {"subjectId": "algorithm-a", "request": minimal_request},
                "right": {"subjectId": "algorithm-b", "request": explicit_request},
            }
        )
    )
    assert comparison["compatibility"]["compatible"] is True
    assert comparison["compatibility"]["issues"] == []


def test_evaluate_run_keeps_an_observation_when_the_domain_pack_is_unknown():
    _, evaluate_run, _, _ = _load_public_api()
    request = _load_json("requests/cnc-contour-observation-pass.json")

    bundle = _to_data(
        evaluate_run(
            {
                "subjectId": "subject-a",
                "domainPackId": "vendor.unknown-pack@1",
                "request": request,
            }
        )
    )

    assert bundle["run"]["executionStatus"] == "Skipped"
    assert bundle["report"]["caseOutcome"] == "Unsupported"
    assert bundle["report"]["domainFailures"][0]["code"] == "UnknownDomainPack"
    assert bundle["observation"]["artifactHash"]


def test_compare_reports_left_right_delta_and_direction_per_metric():
    _, _, compare, _ = _load_public_api()
    comparison = _comparison_case("cnc-contour-ab-pass-vs-fail@1")
    expected = _comparison_manifest("cnc-contour-ab-pass-vs-fail@1")["expectedMetrics"]
    result = _to_data(compare(comparison))
    replay = _to_data(compare(comparison))

    assert result == replay

    compatibility = _get_key(result, "compatibility")
    assert _get_key(compatibility, "compatible", "isCompatible") is True
    metric_entries = _get_key(result, "metrics", "metricComparisons")
    metric_map = {
        item["metricId"]: item
        for item in metric_entries
    }

    for metric_id, metric_expected in expected.items():
        actual = metric_map[metric_id]
        left_value = _get_key(actual, "left", "leftValue")
        right_value = _get_key(actual, "right", "rightValue")
        assert math.isclose(left_value, metric_expected["left"], rel_tol=0.0, abs_tol=1e-12)
        assert math.isclose(right_value, metric_expected["right"], rel_tol=0.0, abs_tol=1e-12)
        assert math.isclose(actual["delta"], metric_expected["delta"], rel_tol=0.0, abs_tol=1e-12)
        assert actual["direction"] == metric_expected["direction"]
        assert actual["preferredSubjectId"] == "algorithm-a"


def test_compare_runs_records_environment_differences_without_marking_incompatible():
    _, evaluate_run, _, compare_runs = _load_public_api()
    comparison = _comparison_case("cnc-contour-ab-pass-vs-fail@1")
    left_bundle = _evaluate_bundle(evaluate_run, comparison["left"]["subjectId"], comparison["left"]["request"])
    right_bundle = _evaluate_bundle(evaluate_run, comparison["right"]["subjectId"], comparison["right"]["request"])
    _set_runtime_path(right_bundle, "run.numeric_environment.python", "3.12.10")
    _set_runtime_path(right_bundle, "report.evaluator_version", "ordered-point-evaluator@2")

    result = _to_data(compare_runs(left_bundle, right_bundle))

    compatibility = _get_key(result, "compatibility")
    assert _get_key(compatibility, "compatible", "isCompatible") is True
    differences = _get_key(result, "differences", "recordedDifferences", "contextDifferences")
    fields = {_get_key(item, "field", "path") for item in differences}
    assert "run.numericEnvironment.python" in fields
    assert "report.evaluatorVersion" in fields


@pytest.mark.parametrize(
    "case",
    _comparison_manifest("cnc-run-compatibility-matrix@1")["cases"],
    ids=lambda case: case["id"],
)
def test_compare_runs_reports_structured_reasons_for_incompatibilities(case):
    _, evaluate_run, _, compare_runs = _load_public_api()
    baseline = _comparison_case("cnc-run-compatibility-matrix@1")
    manifest_case = _comparison_manifest("cnc-run-compatibility-matrix@1")
    left_bundle = _evaluate_bundle(evaluate_run, baseline["left"]["subjectId"], baseline["left"]["request"])
    right_bundle = _evaluate_bundle(evaluate_run, baseline["right"]["subjectId"], baseline["right"]["request"])

    for mutation in manifest_case.get("commonMutations", []):
        _set_runtime_path(left_bundle, mutation["path"], mutation["value"])
        _set_runtime_path(right_bundle, mutation["path"], mutation["value"])
    for mutation in case.get("leftMutations", []):
        _set_runtime_path(left_bundle, mutation["path"], mutation["value"])
    for mutation in case.get("rightMutations", []):
        _set_runtime_path(right_bundle, mutation["path"], mutation["value"])

    result = _to_data(compare_runs(left_bundle, right_bundle))

    compatibility = _get_key(result, "compatibility")
    assert _get_key(compatibility, "compatible", "isCompatible") is False
    assert result["metricComparisons"] == []
    reasons = _get_key(compatibility, "issues", "reasons", "incompatibilities")

    for expected in case["expectedReasons"]:
        assert any(
            reason.get("code") == expected["code"] and _get_key(reason, "path", "field") == expected["path"]
            for reason in reasons
        ), f"未找到结构化原因 {expected!r}，实际: {reasons!r}"
