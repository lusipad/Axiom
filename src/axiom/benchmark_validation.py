"""Declared offline experiments and synthetic evaluator counterexamples."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .benchmark import CncBenchmarkCase, _hash, benchmark_case_hash, compare_cnc_exports
from .benchmark_offline import RuckigOfflineOptions, _write_json, generate_ruckig_export, offline_cases


def _scenario(identifier: str, title: str, category: str, expected: str, purpose: str) -> dict[str, str]:
    return dict(id=identifier, title=title, category=category, expectedOutcome=expected, purpose=purpose)


VALIDATION_SCENARIOS = (
    _scenario("aa-long", "长位移 A/A", "offline-sut", "WithinTolerance", "固定输入重复生成，验证巡航段与确定性"),
    _scenario("aa-short", "短位移 A/A", "offline-sut", "WithinTolerance", "验证无巡航的短行程与固定周期"),
    _scenario("aa-velocity", "速度边界 A/A", "offline-sut", "WithinTolerance", "验证速度主导轨迹，生成约束使用 99% 预算"),
    _scenario("aa-negative-z", "Z 轴负向 A/A", "offline-sut", "WithinTolerance", "验证负向移动与非零固定轴"),
    _scenario("faster-parameters", "参数对比：更快", "offline-sut", "Improved", "同版本 Ruckig，约束缩放 75% → 99%；不是算法版本提升"),
    _scenario("slower-parameters", "参数对比：更慢", "offline-sut", "Regressed", "同版本 Ruckig，约束缩放 99% → 75%"),
    _scenario("accuracy-speed-tradeoff", "精度—时间取舍", "synthetic-example", "Tradeoff", "候选更快但有平滑横向偏差，仍在约束内，不给总分"),
    _scenario("path-offset", "横向偏移", "synthetic-example", "CandidateViolatesLimits", "偏移超过路径及端点预算"),
    _scenario("unfinished", "未完成任务", "synthetic-example", "CandidateViolatesLimits", "截掉末段；单向路径距离仍小，端点不能通过"),
    _scenario("backtracking", "中途后退", "synthetic-example", "CandidateViolatesLimits", "端点正确但中途后退；用高差分预算隔离遍历检查"),
    _scenario("velocity-exceeded", "速度超限", "synthetic-example", "CandidateViolatesLimits", "压缩运动周期且两端仍完成；离散速度超限"),
    _scenario("missing-sample", "漏采样", "synthetic-example", "InputRejected", "采样索引缺口必须拒绝，不能插值修补"),
    _scenario("reordered-samples", "乱序采样", "synthetic-example", "InputRejected", "乱序必须拒绝，不能自动排序"),
    _scenario("bad-clock", "时间戳错误", "synthetic-example", "InputRejected", "时间轴不符合固定周期必须拒绝"),
    _scenario("wrong-case-hash", "案例身份错误", "synthetic-example", "InputRejected", "候选未绑定同一 Case 必须拒绝"),
    _scenario("circle-stationary", "圆弧原地不动", "synthetic-example", "Inconclusive", "闭合路径端点相同，不把短时间伪任务判为改善"),
    _scenario("circle-reversed", "圆弧反向", "synthetic-example", "Inconclusive", "距离正确不证明遍历顺序；复杂路径保守降级"),
)


def validation_experiment(identifier: str) -> dict[str, Any]:
    definition = next((item for item in VALIDATION_SCENARIOS if item["id"] == identifier), None)
    if definition is None:
        raise ValueError(f"Unknown validation scenario: {identifier}")
    name = identifier.removeprefix("aa-")
    case = offline_cases()[{"short": 1, "velocity": 2}.get(name, 0)]
    case_data = case.model_dump(mode="json", by_alias=True, exclude_none=True)
    case_data["caseId"] = f"validation.v1.{identifier}"
    if identifier == "aa-negative-z":
        case_data["referencePath"] = [[2, -3, 4], [2, -3, 3]]
    if identifier == "accuracy-speed-tradeoff":
        case_data["maximumPathDeviationMm"] = 0.01
    case = CncBenchmarkCase.model_validate(case_data)
    left_scale = 0.75 if identifier in {"faster-parameters", "accuracy-speed-tradeoff"} else 0.99
    right_scale = 0.75 if identifier == "slower-parameters" else 0.99
    baseline, left_manifest = generate_ruckig_export(case, RuckigOfflineOptions(limitScale=left_scale))
    candidate, right_manifest = generate_ruckig_export(case, RuckigOfflineOptions(limitScale=right_scale))
    request = {"case": case_data, "baseline": baseline.model_dump(mode="json", by_alias=True, exclude_none=True),
               "candidate": candidate.model_dump(mode="json", by_alias=True, exclude_none=True)}
    samples = request["candidate"]["samples"]
    if definition["category"] == "synthetic-example":
        for role in ("baseline", "candidate"):
            request[role]["sourceKind"] = "synthetic-example"
            request[role]["algorithmId"] = "validation.derived-synthetic"
        if identifier == "accuracy-speed-tradeoff":
            duration = samples[-1]["t"]
            for sample in samples:
                sample["positionMm"][1] += 0.002 * math.sin(math.pi * sample["t"] / duration) ** 2
        elif identifier == "path-offset":
            for sample in samples:
                sample["positionMm"][1] += 0.01
        elif identifier == "unfinished":
            del samples[len(samples) // 2:]
        elif identifier == "backtracking":
            samples[len(samples) // 2]["positionMm"][0] -= 0.2
            for limits in case_data["axisLimits"]:
                for field in ("maximumVelocityMmS", "maximumAccelerationMmS2", "maximumJerkMmS3"):
                    limits[field] = 1e12
        elif identifier == "velocity-exceeded":
            period = case_data["samplePeriodSeconds"] / 2
            case_data["samplePeriodSeconds"] = period
            for role in ("baseline", "candidate"):
                request[role]["samplePeriodSeconds"] = period
            count = len(request["baseline"]["samples"])
            request["baseline"]["samples"] = [dict(sampleIndex=i, t=i * period, positionMm=[100 * i / (2 * count - 2), 0, 0]) for i in range(2 * count - 1)]
            for index, sample in enumerate(samples):
                sample["t"] = index * period
        elif identifier == "missing-sample":
            del samples[len(samples) // 2]
        elif identifier == "reordered-samples":
            samples[1], samples[2] = samples[2], samples[1]
        elif identifier == "bad-clock":
            samples[2]["t"] += case.sample_period_seconds / 2
        elif identifier.startswith("circle-"):
            case_data["referencePath"] = [[1, 0, 0], [-1, 0, 0], [1, 0, 0]]
            case_data["referenceArcs"] = [dict(segmentIndex=i, centerMm=[0, 0], direction="ccw") for i in (0, 1)]
            case_data["samplePeriodSeconds"] = 0.01
            for limits in case_data["axisLimits"]:
                for field in ("maximumVelocityMmS", "maximumAccelerationMmS2", "maximumJerkMmS3"):
                    limits[field] = 1e12
            for role in ("baseline", "candidate"):
                request[role]["samplePeriodSeconds"] = 0.01
                sign = -1 if role == "candidate" and identifier == "circle-reversed" else 1
                request[role]["samples"] = [dict(sampleIndex=i, t=i * 0.01, positionMm=[math.cos(sign * 2 * math.pi * i / 400), math.sin(sign * 2 * math.pi * i / 400), 0]) for i in range(401)]
            if identifier == "circle-stationary":
                request["candidate"]["samples"] = [dict(sampleIndex=i, t=i * 0.01, positionMm=[1, 0, 0]) for i in range(4)]
    case_hash = benchmark_case_hash(case_data)
    for role in ("baseline", "candidate"):
        request[role]["caseContentHash"] = case_hash
    if identifier == "wrong-case-hash":
        request["candidate"]["caseContentHash"] = "0" * 64
    return {
        "definition": dict(definition), "request": request,
        "provenance": {"seedManifests": {"baseline": left_manifest, "candidate": right_manifest},
                       "inputExportHashes": {role: _hash(request[role]) for role in ("baseline", "candidate")},
                       "inputRequestHash": _hash(request),
                       "derivation": definition["purpose"] if definition["category"] == "synthetic-example" else "Unmodified local Ruckig output",
                       "note": "Seed manifests describe original SUT exports, not derived exports. Input hashes bind JSON values before model normalization; report hashes bind validated models. No production evidence."},
    }


def evaluate_validation_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    from .benchmark import cnc_diagnostics

    request = experiment["request"]
    try:
        report = compare_cnc_exports(request)
        replay = compare_cnc_exports(copy.deepcopy(request))
        result = {"observedOutcome": report.outcome, "report": report.model_dump(mode="json", by_alias=True, exclude_none=True),
                  "diagnostics": cnc_diagnostics(request), "deterministicReplay": report == replay}
    except ValidationError as exc:
        result = {"observedOutcome": "InputRejected", "inputErrors": exc.errors(include_url=False, include_context=False, include_input=False),
                  "deterministicReplay": None}
    generation = request["baseline"] == request["candidate"] if experiment["definition"]["id"].startswith("aa-") else None
    return {**experiment, **result, "deterministicGeneration": generation,
            "passed": result["observedOutcome"] == experiment["definition"]["expectedOutcome"] and result["deterministicReplay"] is not False and generation is not False}


def write_validation_suite(out_dir: Path) -> dict[str, Any]:
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise ValueError("Validation suite output directory must be new or empty")
    experiments = [evaluate_validation_experiment(validation_experiment(item["id"])) for item in VALIDATION_SCENARIOS]
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for experiment in experiments:
        identifier = experiment["definition"]["id"]
        _write_json(out_dir / f"{identifier}.request.json", experiment["request"])
        _write_json(out_dir / f"{identifier}.result.json", {key: value for key, value in experiment.items() if key != "request"})
        rows.append({key: experiment[key] for key in ("definition", "observedOutcome", "passed", "deterministicReplay", "deterministicGeneration")})
    summary = {"schemaId": "axiom.cnc-validation-suite@1", "purpose": "evaluator-integration-validation",
               "passed": all(item["passed"] for item in rows), "cases": rows,
               "limitations": "Offline SUT and declared synthetic experiments only; passing detects expected evaluator behavior, not algorithm superiority."}
    _write_json(out_dir / "summary.json", summary)
    return summary
