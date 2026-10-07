from __future__ import annotations

import json
import math
import hashlib
import hmac
import platform
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .models import canonical_hash
from .r5c_interpreter import predict_conditional_effect
from .r5c_models import (
    ConditionalEffectModelBundle,
    ConditionalEffectModelBundleV2,
    ConditionalEffectPrediction,
    ConditionalEffectPredictionRequest,
)
from .r5i_models import (
    R5I_MONITORING_CHECK_IDS,
    R5I_SAFETY_BANNER,
    R5IActivationReceipt,
    R5IMonitoringCheck,
    R5IMonitoringSample,
    R5IMonitoringSampleResult,
    R5IMonitoringTargetResult,
    R5IMonitoringWindowReport,
    R5IMonitoringWindowRequest,
    R5IPromotionPreflightRequest,
    R5IRegistryStatus,
    R5IRollbackReceipt,
    R5IRollbackRequest,
)
from .r5i_promotion import preflight_r5i_model_promotion

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_SCHEMA_VERSION = 1
_SLOT = "conditional-effect-default"


def _seal(model_type: type[_ModelT], payload: dict[str, Any]) -> _ModelT:
    draft = {**payload, "contentHash": "0" * 64}
    provisional = model_type.model_construct(**draft)
    draft["contentHash"] = canonical_hash(
        provisional,
        exclude={"content_hash"},
    )
    return model_type.model_validate(draft)


def _registry_path(path: str | Path) -> Path:
    raw = str(path)
    if raw == ":memory:" or raw.startswith("file:"):
        raise ValueError("R5-I registry requires an explicit persistent file path")
    if raw.startswith("\\\\"):
        raise ValueError("R5-I registry does not support Windows network shares")
    resolved = Path(path).resolve(strict=False)
    if not resolved.parent.is_dir():
        raise ValueError("R5-I registry parent directory must already exist")
    return resolved


def _registry_identity(path: Path) -> str:
    return canonical_hash({"registryPath": str(path).casefold()})


def _connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro",
            uri=True,
            timeout=5.0,
        )
    else:
        connection = sqlite3.connect(path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if not read_only:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
    return connection


def _initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS registry_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT;
        CREATE TABLE IF NOT EXISTS model_artifact (
            content_hash TEXT PRIMARY KEY,
            schema_id TEXT NOT NULL,
            canonical_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT;
        CREATE TABLE IF NOT EXISTS lifecycle_authorization (
            authorization_id TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK(kind IN ('Promotion', 'Rollback')),
            canonical_json TEXT NOT NULL
        ) STRICT;
        CREATE TABLE IF NOT EXISTS registry_entry (
            model_hash TEXT PRIMARY KEY REFERENCES model_artifact(content_hash),
            baseline_hash TEXT NOT NULL REFERENCES model_artifact(content_hash),
            authorization_hash TEXT NOT NULL REFERENCES lifecycle_authorization(content_hash),
            registered_at TEXT NOT NULL
        ) STRICT;
        CREATE TABLE IF NOT EXISTS activation_state (
            slot TEXT PRIMARY KEY CHECK(slot = 'conditional-effect-default'),
            model_hash TEXT NOT NULL REFERENCES model_artifact(content_hash),
            baseline_hash TEXT NOT NULL REFERENCES model_artifact(content_hash),
            generation INTEGER NOT NULL CHECK(generation >= 1)
        ) STRICT;
        CREATE TABLE IF NOT EXISTS activation_event (
            event_id TEXT PRIMARY KEY,
            authorization_hash TEXT NOT NULL UNIQUE REFERENCES lifecycle_authorization(content_hash),
            generation INTEGER NOT NULL UNIQUE CHECK(generation >= 1),
            receipt_hash TEXT NOT NULL UNIQUE,
            receipt_json TEXT NOT NULL
        ) STRICT;
        CREATE TABLE IF NOT EXISTS monitoring_window (
            window_id TEXT PRIMARY KEY,
            request_hash TEXT NOT NULL UNIQUE,
            model_hash TEXT NOT NULL,
            generation INTEGER NOT NULL CHECK(generation >= 1),
            status TEXT NOT NULL CHECK(status IN ('Healthy', 'Open', 'RollbackRequired')),
            report_hash TEXT NOT NULL UNIQUE,
            report_json TEXT NOT NULL
        ) STRICT;
        """
    )
    current = connection.execute(
        "SELECT value FROM registry_metadata WHERE key = 'schema_version'"
    ).fetchone()
    if current is None:
        connection.execute(
            "INSERT INTO registry_metadata(key, value) VALUES('schema_version', ?)",
            (str(_SCHEMA_VERSION),),
        )
        connection.commit()
    elif current["value"] != str(_SCHEMA_VERSION):
        raise ValueError("unsupported R5-I registry schema version")


def _canonical_json(model: BaseModel) -> str:
    return json.dumps(
        model.model_dump(mode="json", by_alias=True, exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _model_bundles(request: R5IPromotionPreflightRequest) -> tuple[Any, Any]:
    dossier = request.readiness_dossier
    scenario = dossier.request.impact_report.scenario_impacts[0]
    baseline = (
        scenario.baseline_recommendation.search_request.surrogate_context.model_bundle
    )
    candidate = (
        scenario.candidate_recommendation.search_request.surrogate_context.model_bundle
    )
    if baseline.content_hash != dossier.baseline_model_bundle_hash:
        raise ValueError("R5-I rollback baseline artifact mismatch")
    if candidate.content_hash != dossier.candidate_model_bundle_hash:
        raise ValueError("R5-I candidate artifact mismatch")
    return baseline, candidate


def _insert_model(
    connection: sqlite3.Connection,
    model: BaseModel,
    *,
    created_at: str,
) -> None:
    content_hash = getattr(model, "content_hash")
    canonical_json = _canonical_json(model)
    existing = connection.execute(
        "SELECT schema_id, canonical_json FROM model_artifact WHERE content_hash = ?",
        (content_hash,),
    ).fetchone()
    if existing is not None:
        if (
            existing["schema_id"] != getattr(model, "schema_id")
            or existing["canonical_json"] != canonical_json
        ):
            raise ValueError("model artifact content identity conflict")
        return
    connection.execute(
        "INSERT INTO model_artifact(content_hash, schema_id, canonical_json, created_at) "
        "VALUES(?, ?, ?, ?)",
        (content_hash, getattr(model, "schema_id"), canonical_json, created_at),
    )


def _transaction_checkpoint() -> None:
    """Test seam for proving rollback before commit; production performs no action."""


def _latest_receipt(
    connection: sqlite3.Connection,
) -> R5IActivationReceipt | R5IRollbackReceipt | None:
    row = connection.execute(
        "SELECT receipt_json FROM activation_event ORDER BY generation DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["receipt_json"])
    if payload.get("schemaId") == "axiom.intelligence.model-rollback-receipt@1":
        return R5IRollbackReceipt.model_validate(payload)
    return R5IActivationReceipt.model_validate(payload)


def _status(connection: sqlite3.Connection, path: Path) -> R5IRegistryStatus:
    state = connection.execute(
        "SELECT model_hash, baseline_hash, generation FROM activation_state "
        "WHERE slot = ?",
        (_SLOT,),
    ).fetchone()
    latest = _latest_receipt(connection)
    active = state is not None
    return _seal(
        R5IRegistryStatus,
        {
            "schemaId": "axiom.intelligence.model-registry-status@1",
            "schemaVersion": 1,
            "registryIdentity": _registry_identity(path),
            "registryInitialized": True,
            "currentModelBundleHash": state["model_hash"] if active else None,
            "rollbackBaselineModelBundleHash": (
                state["baseline_hash"] if active else None
            ),
            "generation": state["generation"] if active else 0,
            "latestEvent": latest,
            "modelRegistryWritePerformed": active,
            "activationPerformed": active,
            "automaticDeploymentAllowed": False,
            "deviceWriteAllowed": False,
            "permissionLevel": "Offline",
            "safetyBanner": R5I_SAFETY_BANNER,
        },
    )


def read_r5i_registry_status(path: str | Path) -> R5IRegistryStatus:
    resolved = _registry_path(path)
    if not resolved.exists():
        return _seal(
            R5IRegistryStatus,
            {
                "schemaId": "axiom.intelligence.model-registry-status@1",
                "schemaVersion": 1,
                "registryIdentity": _registry_identity(resolved),
                "registryInitialized": False,
                "currentModelBundleHash": None,
                "rollbackBaselineModelBundleHash": None,
                "generation": 0,
                "latestEvent": None,
                "modelRegistryWritePerformed": False,
                "activationPerformed": False,
                "automaticDeploymentAllowed": False,
                "deviceWriteAllowed": False,
                "permissionLevel": "Offline",
                "safetyBanner": R5I_SAFETY_BANNER,
            },
        )
    with _connect(resolved, read_only=True) as connection:
        metadata = connection.execute(
            "SELECT value FROM registry_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if metadata is None or metadata["value"] != str(_SCHEMA_VERSION):
            raise ValueError("unsupported or malformed R5-I registry")
        return _status(connection, resolved)


def apply_r5i_promotion_transaction(
    path: str | Path,
    request: R5IPromotionPreflightRequest,
    *,
    authority_keys: Mapping[str, bytes],
    event_id: str,
    activated_at: str,
    expected_generation: int,
    current_platform: str | None = None,
) -> R5IActivationReceipt:
    preflight = preflight_r5i_model_promotion(
        request,
        authority_keys=authority_keys,
        current_platform=current_platform,
    )
    if not preflight.registry_transaction_allowed:
        raise ValueError("R5-I promotion preflight is not eligible for registry write")
    if expected_generation < 0:
        raise ValueError("expected generation must be non-negative")
    activation_time = datetime.fromisoformat(activated_at)
    if activation_time.tzinfo is None:
        raise ValueError("activatedAt must include an explicit UTC offset")
    decision_time = datetime.fromisoformat(request.promotion_decision.decided_at)
    if activation_time < decision_time:
        raise ValueError("activation must not precede the promotion decision")

    resolved = _registry_path(path)
    baseline, candidate = _model_bundles(request)
    decision = request.promotion_decision

    with _connect(resolved) as connection:
        _initialize(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing_decision = connection.execute(
                "SELECT content_hash FROM lifecycle_authorization "
                "WHERE authorization_id = ?",
                (decision.decision_id,),
            ).fetchone()
            if existing_decision is not None:
                if existing_decision["content_hash"] != decision.content_hash:
                    raise ValueError("promotion decision identity conflict")
                row = connection.execute(
                    "SELECT receipt_json FROM activation_event "
                    "WHERE authorization_hash = ?",
                    (decision.content_hash,),
                ).fetchone()
                if row is None:
                    raise ValueError("promotion decision exists without activation event")
                connection.rollback()
                return R5IActivationReceipt.model_validate_json(row["receipt_json"])

            state = connection.execute(
                "SELECT model_hash, baseline_hash, generation FROM activation_state "
                "WHERE slot = ?",
                (_SLOT,),
            ).fetchone()
            actual_generation = state["generation"] if state is not None else 0
            if actual_generation != expected_generation:
                raise ValueError(
                    "registry generation conflict: "
                    f"expected {expected_generation}, actual {actual_generation}"
                )
            if state is not None:
                raise ValueError("R5-I candidate promotion requires inactive baseline state")

            _insert_model(connection, baseline, created_at=activated_at)
            _insert_model(connection, candidate, created_at=activated_at)
            connection.execute(
                "INSERT INTO lifecycle_authorization(authorization_id, content_hash, "
                "kind, canonical_json) VALUES(?, ?, 'Promotion', ?)",
                (decision.decision_id, decision.content_hash, _canonical_json(decision)),
            )
            connection.execute(
                "INSERT INTO registry_entry(model_hash, baseline_hash, authorization_hash, "
                "registered_at) VALUES(?, ?, ?, ?)",
                (
                    candidate.content_hash,
                    baseline.content_hash,
                    decision.content_hash,
                    activated_at,
                ),
            )
            generation = actual_generation + 1
            connection.execute(
                "INSERT INTO activation_state(slot, model_hash, baseline_hash, generation) "
                "VALUES(?, ?, ?, ?)",
                (_SLOT, candidate.content_hash, baseline.content_hash, generation),
            )
            receipt = _seal(
                R5IActivationReceipt,
                {
                    "schemaId": "axiom.intelligence.model-activation-receipt@1",
                    "schemaVersion": 1,
                    "eventId": event_id,
                    "eventKind": "Promotion",
                    "preflightReportContentHash": preflight.content_hash,
                    "promotionDecisionContentHash": decision.content_hash,
                    "sourceModelBundleHash": baseline.content_hash,
                    "targetModelBundleHash": candidate.content_hash,
                    "rollbackBaselineModelBundleHash": baseline.content_hash,
                    "activatedAt": activated_at,
                    "generation": generation,
                    "readbackModelBundleHash": candidate.content_hash,
                    "readbackGeneration": generation,
                    "transactionStatus": "Applied",
                    "modelPromotionStatus": "Performed",
                    "modelRegistryWritePerformed": True,
                    "activationPerformed": True,
                    "defaultModelChanged": True,
                    "automaticDeploymentAllowed": False,
                    "deviceWritePerformed": False,
                    "deviceWriteAllowed": False,
                    "permissionLevel": "Offline",
                    "safetyBanner": R5I_SAFETY_BANNER,
                },
            )
            connection.execute(
                "INSERT INTO activation_event(event_id, authorization_hash, generation, "
                "receipt_hash, receipt_json) VALUES(?, ?, ?, ?, ?)",
                (
                    receipt.event_id,
                    decision.content_hash,
                    generation,
                    receipt.content_hash,
                    _canonical_json(receipt),
                ),
            )
            _transaction_checkpoint()
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        status = _status(connection, resolved)
        if (
            status.current_model_bundle_hash != candidate.content_hash
            or status.generation != receipt.generation
            or status.latest_event != receipt
        ):
            raise ValueError("R5-I registry readback mismatch after commit")
        return receipt


def _load_model_bundle(
    connection: sqlite3.Connection,
    model_hash: str,
) -> ConditionalEffectModelBundle | ConditionalEffectModelBundleV2:
    row = connection.execute(
        "SELECT schema_id, canonical_json FROM model_artifact WHERE content_hash = ?",
        (model_hash,),
    ).fetchone()
    if row is None:
        raise ValueError("active model artifact is missing from R5-I registry")
    model_type = (
        ConditionalEffectModelBundleV2
        if row["schema_id"]
        == "axiom.intelligence.conditional-effect-model-bundle@2"
        else ConditionalEffectModelBundle
        if row["schema_id"]
        == "axiom.intelligence.conditional-effect-model-bundle@1"
        else None
    )
    if model_type is None:
        raise ValueError("unsupported active R5-I model schema")
    bundle = model_type.model_validate_json(row["canonical_json"])
    if bundle.content_hash != model_hash:
        raise ValueError("active model artifact content hash mismatch")
    return bundle


def predict_r5i_active_model(
    path: str | Path,
    *,
    feed_override: float,
    sample_period: float,
) -> ConditionalEffectPrediction:
    resolved = _registry_path(path)
    status = read_r5i_registry_status(resolved)
    if status.current_model_bundle_hash is None:
        raise ValueError("R5-I registry has no active local model")
    with _connect(resolved, read_only=True) as connection:
        bundle = _load_model_bundle(connection, status.current_model_bundle_hash)
    return predict_conditional_effect(
        ConditionalEffectPredictionRequest(
            modelBundle=bundle,
            feedOverride=feed_override,
            samplePeriod=sample_period,
        )
    )


def build_r5i_monitoring_request(
    *,
    registry_status: R5IRegistryStatus,
    window_id: str,
    opened_at: str,
    closed_at: str,
    samples: tuple[R5IMonitoringSample, ...],
    maximum_cycle_rmse_seconds: float,
    maximum_linear_rmse_mm: float,
    maximum_ood_fraction: float = 0.0,
    minimum_interval_coverage: float = 1.0,
) -> R5IMonitoringWindowRequest:
    if registry_status.current_model_bundle_hash is None or registry_status.generation < 1:
        raise ValueError("R5-I monitoring requires an active registry model")
    return _seal(
        R5IMonitoringWindowRequest,
        {
            "schemaId": "axiom.intelligence.model-monitoring-window-request@1",
            "schemaVersion": 1,
            "windowId": window_id,
            "registryIdentity": registry_status.registry_identity,
            "modelBundleHash": registry_status.current_model_bundle_hash,
            "generation": registry_status.generation,
            "openedAt": opened_at,
            "closedAt": closed_at,
            "samples": samples,
            "maximumOodFraction": maximum_ood_fraction,
            "minimumIntervalCoverage": minimum_interval_coverage,
            "maximumCycleRmseSeconds": maximum_cycle_rmse_seconds,
            "maximumLinearRmseMm": maximum_linear_rmse_mm,
            "monitoringScope": "local-model-behavior",
        },
    )


def _monitoring_check(
    check_id: str,
    *,
    status: str,
    reason_code: str,
    evidence: Any,
) -> R5IMonitoringCheck:
    return R5IMonitoringCheck(
        checkId=check_id,
        status=status,
        reasonCode=reason_code,
        evidenceHash=canonical_hash(
            {
                "checkId": check_id,
                "status": status,
                "reasonCode": reason_code,
                "evidence": evidence,
            }
        ),
    )


def _target_monitoring_results(
    request: R5IMonitoringWindowRequest,
    sample_results: tuple[R5IMonitoringSampleResult, ...],
) -> tuple[R5IMonitoringTargetResult, R5IMonitoringTargetResult]:
    configured = (
        ("cycleTimeSeconds", "s", request.maximum_cycle_rmse_seconds),
        (
            "linearFollowingErrorMaxMm",
            "mm",
            request.maximum_linear_rmse_mm,
        ),
    )
    results: list[R5IMonitoringTargetResult] = []
    for target_id, unit, maximum_rmse in configured:
        targets = tuple(
            target
            for sample in sample_results
            for target in sample.targets
            if target.target_id == target_id and target.actual is not None
        )
        if len(targets) != len(request.samples):
            results.append(
                R5IMonitoringTargetResult(
                    targetId=target_id,
                    unit=unit,
                    labeledSampleCount=len(targets),
                    rmse=None,
                    intervalCoverage=None,
                    status="Open",
                    reasonCode="CompleteLabeledWindowRequired",
                )
            )
            continue
        rmse = math.sqrt(
            math.fsum(target.absolute_error**2 for target in targets) / len(targets)
        )
        coverage = math.fsum(
            1.0 if target.interval_covered else 0.0 for target in targets
        ) / len(targets)
        passed = (
            rmse <= maximum_rmse
            and coverage >= request.minimum_interval_coverage
        )
        results.append(
            R5IMonitoringTargetResult(
                targetId=target_id,
                unit=unit,
                labeledSampleCount=len(targets),
                rmse=rmse,
                intervalCoverage=coverage,
                status="Passed" if passed else "Refuted",
                reasonCode=(
                    "TargetPerformanceWithinEnvelope"
                    if passed
                    else "TargetPerformanceOutsideEnvelope"
                ),
            )
        )
    return results[0], results[1]


def _build_monitoring_report(
    path: Path,
    request: R5IMonitoringWindowRequest,
) -> R5IMonitoringWindowReport:
    registry_status = read_r5i_registry_status(path)
    binding_ok = (
        registry_status.registry_identity == request.registry_identity
        and registry_status.current_model_bundle_hash == request.model_bundle_hash
        and registry_status.generation == request.generation
    )
    binding_check = _monitoring_check(
        R5I_MONITORING_CHECK_IDS[0],
        status="Passed" if binding_ok else "Open",
        reason_code=(
            "RegistryGenerationBound" if binding_ok else "RegistryGenerationDrift"
        ),
        evidence={
            "requestedRegistryIdentity": request.registry_identity,
            "actualRegistryIdentity": registry_status.registry_identity,
            "requestedModelBundleHash": request.model_bundle_hash,
            "actualModelBundleHash": registry_status.current_model_bundle_hash,
            "requestedGeneration": request.generation,
            "actualGeneration": registry_status.generation,
        },
    )

    bundle = None
    bundle_ok = False
    if binding_ok:
        try:
            with _connect(path, read_only=True) as connection:
                bundle = _load_model_bundle(connection, request.model_bundle_hash)
            bundle_ok = bundle.content_hash == request.model_bundle_hash
        except (sqlite3.Error, TypeError, ValueError):
            bundle_ok = False
    bundle_check = _monitoring_check(
        R5I_MONITORING_CHECK_IDS[1],
        status="Passed" if bundle_ok else "Open",
        reason_code=(
            "ActiveBundleIntegrityPassed"
            if bundle_ok
            else "ActiveBundleUnavailableOrInvalid"
        ),
        evidence={
            "modelBundleHash": request.model_bundle_hash,
            "bundleLoaded": bundle_ok,
        },
    )

    sample_results: list[R5IMonitoringSampleResult] = []
    inference_failed = False
    ood_count = 0
    if bundle_ok and bundle is not None:
        for sample in request.samples:
            try:
                prediction = predict_conditional_effect(
                    ConditionalEffectPredictionRequest(
                        modelBundle=bundle,
                        feedOverride=sample.feed_override,
                        samplePeriod=sample.sample_period,
                    )
                )
                if prediction.status == "Abstained":
                    ood_count += 1
                    sample_results.append(
                        R5IMonitoringSampleResult(
                            sampleId=sample.sample_id,
                            feedOverride=sample.feed_override,
                            samplePeriod=sample.sample_period,
                            predictionStatus="Abstained",
                            reasonCode=prediction.reason_code,
                            targets=(),
                            evidenceContentHash=sample.evidence_content_hash,
                        )
                    )
                    continue
                actuals = {
                    "cycleTimeSeconds": sample.actual_cycle_time_seconds,
                    "linearFollowingErrorMaxMm": (
                        sample.actual_linear_following_error_max_mm
                    ),
                }
                targets = []
                for predicted in prediction.predictions:
                    actual = actuals[predicted.target_id]
                    targets.append(
                        {
                            "targetId": predicted.target_id,
                            "unit": predicted.unit,
                            "predicted": predicted.value,
                            "intervalLower": predicted.lower,
                            "intervalUpper": predicted.upper,
                            "actual": actual,
                            "absoluteError": (
                                abs(predicted.value - actual)
                                if actual is not None
                                else None
                            ),
                            "intervalCovered": (
                                predicted.lower <= actual <= predicted.upper
                                if actual is not None
                                else None
                            ),
                        }
                    )
                sample_results.append(
                    R5IMonitoringSampleResult(
                        sampleId=sample.sample_id,
                        feedOverride=sample.feed_override,
                        samplePeriod=sample.sample_period,
                        predictionStatus="Predicted",
                        reasonCode=None,
                        targets=targets,
                        evidenceContentHash=sample.evidence_content_hash,
                    )
                )
            except (ArithmeticError, TypeError, ValueError) as exc:
                inference_failed = True
                sample_results.append(
                    R5IMonitoringSampleResult(
                        sampleId=sample.sample_id,
                        feedOverride=sample.feed_override,
                        samplePeriod=sample.sample_period,
                        predictionStatus="Failed",
                        reasonCode=type(exc).__name__,
                        targets=(),
                        evidenceContentHash=sample.evidence_content_hash,
                    )
                )
    sample_result_tuple = tuple(sample_results)
    inference_complete = bundle_ok and not inference_failed and (
        len(sample_result_tuple) == len(request.samples)
    )
    inference_check = _monitoring_check(
        R5I_MONITORING_CHECK_IDS[2],
        status=(
            "Passed"
            if inference_complete
            else "Refuted"
            if bundle_ok and inference_failed
            else "Open"
        ),
        reason_code=(
            "InferenceComplete"
            if inference_complete
            else "InferenceFailure"
            if bundle_ok and inference_failed
            else "InferenceNotRun"
        ),
        evidence={
            "sampleCount": len(request.samples),
            "resultCount": len(sample_result_tuple),
            "failed": inference_failed,
        },
    )
    ood_fraction = ood_count / len(request.samples) if bundle_ok else None
    ood_passed = ood_fraction is not None and (
        ood_fraction <= request.maximum_ood_fraction
    )
    ood_check = _monitoring_check(
        R5I_MONITORING_CHECK_IDS[3],
        status=(
            "Passed"
            if ood_passed
            else "Refuted"
            if ood_fraction is not None
            else "Open"
        ),
        reason_code=(
            "OodFractionWithinEnvelope"
            if ood_passed
            else "OodFractionOutsideEnvelope"
            if ood_fraction is not None
            else "OodFractionUnavailable"
        ),
        evidence={
            "oodFraction": ood_fraction,
            "maximumOodFraction": request.maximum_ood_fraction,
        },
    )
    target_results = _target_monitoring_results(request, sample_result_tuple)
    target_statuses = tuple(item.status for item in target_results)
    target_check_status = (
        "Refuted"
        if "Refuted" in target_statuses
        else "Open"
        if "Open" in target_statuses
        else "Passed"
    )
    target_check = _monitoring_check(
        R5I_MONITORING_CHECK_IDS[4],
        status=target_check_status,
        reason_code={
            "Passed": "BothTargetsWithinEnvelope",
            "Open": "CompleteLabeledWindowRequired",
            "Refuted": "TargetPerformanceOutsideEnvelope",
        }[target_check_status],
        evidence={
            "targets": [
                item.model_dump(mode="json", by_alias=True) for item in target_results
            ]
        },
    )
    checks = (
        binding_check,
        bundle_check,
        inference_check,
        ood_check,
        target_check,
    )
    monitoring_status = (
        "RollbackRequired"
        if any(check.status == "Refuted" for check in checks)
        else "Open"
        if any(check.status == "Open" for check in checks)
        else "Healthy"
    )
    return _seal(
        R5IMonitoringWindowReport,
        {
            "schemaId": "axiom.intelligence.model-monitoring-window-report@1",
            "schemaVersion": 1,
            "request": request,
            "registryIdentity": request.registry_identity,
            "modelBundleHash": request.model_bundle_hash,
            "generation": request.generation,
            "sampleResults": sample_result_tuple,
            "targetResults": target_results,
            "checks": checks,
            "monitoringStatus": monitoring_status,
            "rollbackRequired": monitoring_status == "RollbackRequired",
            "automaticRollbackAllowed": False,
            "automaticDeploymentAllowed": False,
            "deviceWriteAllowed": False,
            "permissionLevel": "Offline",
            "safetyBanner": R5I_SAFETY_BANNER,
        },
    )


def assess_r5i_monitoring_window(
    path: str | Path,
    request: R5IMonitoringWindowRequest,
) -> R5IMonitoringWindowReport:
    resolved = _registry_path(path)
    request = R5IMonitoringWindowRequest.model_validate(
        request.model_dump(mode="json", by_alias=True)
    )
    report = _build_monitoring_report(resolved, request)
    with _connect(resolved) as connection:
        _initialize(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                "SELECT request_hash, report_json FROM monitoring_window "
                "WHERE window_id = ?",
                (request.window_id,),
            ).fetchone()
            if existing is not None:
                if existing["request_hash"] != request.content_hash:
                    raise ValueError("monitoring window identity conflict")
                replayed = R5IMonitoringWindowReport.model_validate_json(
                    existing["report_json"]
                )
                if replayed != report:
                    raise ValueError("monitoring window replay mismatch")
                connection.rollback()
                return replayed
            state = connection.execute(
                "SELECT model_hash, generation FROM activation_state WHERE slot = ?",
                (_SLOT,),
            ).fetchone()
            if state is None or (
                state["model_hash"] != request.model_bundle_hash
                or state["generation"] != request.generation
            ):
                raise ValueError("registry generation changed during monitoring")
            connection.execute(
                "INSERT INTO monitoring_window(window_id, request_hash, model_hash, "
                "generation, status, report_hash, report_json) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    request.window_id,
                    request.content_hash,
                    request.model_bundle_hash,
                    request.generation,
                    report.monitoring_status,
                    report.content_hash,
                    _canonical_json(report),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return report


def list_r5i_monitoring_windows(
    path: str | Path,
    *,
    limit: int = 20,
) -> tuple[R5IMonitoringWindowReport, ...]:
    if not 1 <= limit <= 100:
        raise ValueError("monitoring window limit must be between 1 and 100")
    resolved = _registry_path(path)
    if not resolved.exists():
        return ()
    with _connect(resolved, read_only=True) as connection:
        metadata = connection.execute(
            "SELECT value FROM registry_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if metadata is None or metadata["value"] != str(_SCHEMA_VERSION):
            raise ValueError("unsupported or malformed R5-I registry")
        rows = connection.execute(
            "SELECT report_json FROM monitoring_window "
            "ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return tuple(
        R5IMonitoringWindowReport.model_validate_json(row["report_json"])
        for row in rows
    )


def build_r5i_rollback_request(
    registry_status: R5IRegistryStatus,
    monitoring_report: R5IMonitoringWindowReport,
    *,
    request_id: str,
    requested_by: str,
    requested_at: str,
    reason: str,
    authority_key_id: str,
    authority_key: bytes,
) -> R5IRollbackRequest:
    if monitoring_report.monitoring_status != "RollbackRequired":
        raise ValueError("R5-I rollback requires a RollbackRequired monitoring report")
    if (
        registry_status.current_model_bundle_hash is None
        or registry_status.rollback_baseline_model_bundle_hash is None
        or registry_status.registry_identity != monitoring_report.registry_identity
        or registry_status.current_model_bundle_hash
        != monitoring_report.model_bundle_hash
        or registry_status.generation != monitoring_report.generation
    ):
        raise ValueError("R5-I rollback trigger does not match current registry state")
    if not isinstance(authority_key, bytes) or len(authority_key) < 16:
        raise ValueError("authority key must contain at least 16 bytes")
    requested_time = datetime.fromisoformat(requested_at)
    if requested_time.tzinfo is None:
        raise ValueError("requestedAt must include an explicit UTC offset")
    if requested_time < datetime.fromisoformat(monitoring_report.request.closed_at):
        raise ValueError("rollback request must follow the monitoring window")
    body = {
        "schemaId": "axiom.intelligence.model-rollback-request@1",
        "schemaVersion": 1,
        "requestId": request_id,
        "registryIdentity": registry_status.registry_identity,
        "monitoringReportContentHash": monitoring_report.content_hash,
        "expectedCurrentModelBundleHash": (
            registry_status.current_model_bundle_hash
        ),
        "rollbackBaselineModelBundleHash": (
            registry_status.rollback_baseline_model_bundle_hash
        ),
        "expectedGeneration": registry_status.generation,
        "requestedBy": requested_by,
        "requestedAt": requested_at,
        "reason": reason,
        "authorityKeyId": authority_key_id,
    }
    signed_body_hash = canonical_hash(body)
    proof = hmac.new(
        authority_key,
        signed_body_hash.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return _seal(
        R5IRollbackRequest,
        {
            **body,
            "signedBodyHash": signed_body_hash,
            "authorizationProof": proof,
        },
    )


def apply_r5i_rollback_transaction(
    path: str | Path,
    request: R5IRollbackRequest,
    *,
    authority_keys: Mapping[str, bytes],
    event_id: str,
    current_platform: str | None = None,
) -> R5IRollbackReceipt:
    runtime_platform = current_platform or platform.system()
    if runtime_platform.lower() != "windows":
        raise ValueError("R5-I rollback only supports Windows")
    request = R5IRollbackRequest.model_validate(
        request.model_dump(mode="json", by_alias=True)
    )
    authority_key = authority_keys.get(request.authority_key_id)
    if not isinstance(authority_key, bytes) or len(authority_key) < 16:
        raise ValueError("R5-I rollback authority key is unavailable")
    expected_proof = hmac.new(
        authority_key,
        request.signed_body_hash.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(request.authorization_proof, expected_proof):
        raise ValueError("R5-I rollback authorization proof mismatch")
    resolved = _registry_path(path)
    if request.registry_identity != _registry_identity(resolved):
        raise ValueError("R5-I rollback registry identity mismatch")

    with _connect(resolved) as connection:
        _initialize(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                "SELECT content_hash FROM lifecycle_authorization "
                "WHERE authorization_id = ?",
                (request.request_id,),
            ).fetchone()
            if existing is not None:
                if existing["content_hash"] != request.content_hash:
                    raise ValueError("rollback request identity conflict")
                row = connection.execute(
                    "SELECT receipt_json FROM activation_event "
                    "WHERE authorization_hash = ?",
                    (request.content_hash,),
                ).fetchone()
                if row is None:
                    raise ValueError("rollback request exists without rollback event")
                connection.rollback()
                return R5IRollbackReceipt.model_validate_json(row["receipt_json"])

            trigger = connection.execute(
                "SELECT report_json FROM monitoring_window WHERE report_hash = ?",
                (request.monitoring_report_content_hash,),
            ).fetchone()
            if trigger is None:
                raise ValueError("rollback monitoring trigger is not registered")
            monitoring_report = R5IMonitoringWindowReport.model_validate_json(
                trigger["report_json"]
            )
            if monitoring_report.monitoring_status != "RollbackRequired":
                raise ValueError("rollback trigger must be RollbackRequired")
            state = connection.execute(
                "SELECT model_hash, baseline_hash, generation FROM activation_state "
                "WHERE slot = ?",
                (_SLOT,),
            ).fetchone()
            if state is None:
                raise ValueError("R5-I registry has no active model to roll back")
            if (
                state["model_hash"]
                != request.expected_current_model_bundle_hash
                or state["baseline_hash"]
                != request.rollback_baseline_model_bundle_hash
                or state["generation"] != request.expected_generation
                or monitoring_report.model_bundle_hash != state["model_hash"]
                or monitoring_report.generation != state["generation"]
            ):
                raise ValueError("R5-I rollback registry generation conflict")
            _load_model_bundle(connection, state["baseline_hash"])

            generation = state["generation"] + 1
            connection.execute(
                "INSERT INTO lifecycle_authorization(authorization_id, content_hash, "
                "kind, canonical_json) VALUES(?, ?, 'Rollback', ?)",
                (request.request_id, request.content_hash, _canonical_json(request)),
            )
            connection.execute(
                "UPDATE activation_state SET model_hash = ?, generation = ? "
                "WHERE slot = ?",
                (state["baseline_hash"], generation, _SLOT),
            )
            receipt = _seal(
                R5IRollbackReceipt,
                {
                    "schemaId": "axiom.intelligence.model-rollback-receipt@1",
                    "schemaVersion": 1,
                    "eventId": event_id,
                    "eventKind": "Rollback",
                    "rollbackRequestContentHash": request.content_hash,
                    "monitoringReportContentHash": monitoring_report.content_hash,
                    "sourceModelBundleHash": state["model_hash"],
                    "targetModelBundleHash": state["baseline_hash"],
                    "rollbackBaselineModelBundleHash": state["baseline_hash"],
                    "requestedBy": request.requested_by,
                    "rolledBackAt": request.requested_at,
                    "generation": generation,
                    "readbackModelBundleHash": state["baseline_hash"],
                    "readbackGeneration": generation,
                    "transactionStatus": "Applied",
                    "modelPromotionStatus": "Reverted",
                    "modelRegistryWritePerformed": True,
                    "rollbackPerformed": True,
                    "defaultModelChanged": True,
                    "automaticRollbackAllowed": False,
                    "automaticDeploymentAllowed": False,
                    "deviceWritePerformed": False,
                    "deviceWriteAllowed": False,
                    "permissionLevel": "Offline",
                    "safetyBanner": R5I_SAFETY_BANNER,
                },
            )
            connection.execute(
                "INSERT INTO activation_event(event_id, authorization_hash, generation, "
                "receipt_hash, receipt_json) VALUES(?, ?, ?, ?, ?)",
                (
                    receipt.event_id,
                    request.content_hash,
                    generation,
                    receipt.content_hash,
                    _canonical_json(receipt),
                ),
            )
            _transaction_checkpoint()
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        status = _status(connection, resolved)
        if (
            status.current_model_bundle_hash != state["baseline_hash"]
            or status.generation != receipt.generation
            or status.latest_event != receipt
        ):
            raise ValueError("R5-I rollback readback mismatch after commit")
        return receipt


__all__ = [
    "apply_r5i_promotion_transaction",
    "apply_r5i_rollback_transaction",
    "assess_r5i_monitoring_window",
    "build_r5i_monitoring_request",
    "build_r5i_rollback_request",
    "list_r5i_monitoring_windows",
    "predict_r5i_active_model",
    "read_r5i_registry_status",
]
