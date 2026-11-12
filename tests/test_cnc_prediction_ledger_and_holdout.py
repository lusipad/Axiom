from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axiom.benchmark import CncAlgorithmExport, CncBenchmarkCase
from axiom.benchmark_standard import standard_case
from axiom.cli import main as cli_main
from axiom.cnc_governance import (
    CNC_R4_CALIBRATION_CLAIM_ID,
    CNC_R4_CALIBRATION_METRIC_ID,
    CNC_R5_EPISTEMIC_CLAIM_ID,
    CNC_R5_EPISTEMIC_METRIC_ID,
    assess_cnc_greybox_governance,
)
from axiom.greybox_model import simulate_realistic_cnc_controller
from axiom.machine.models import MachineTelemetryTrace
from axiom.machine.runtime import machine_trace_content_hash
from axiom.parameter_recommender import (
    ParameterRecommendationRequest,
    build_cnc_parameter_closed_loop_demo,
    recommend_parameters,
)
from axiom.prediction_ledger import (
    append_prediction_verification_entry,
    build_prediction_verification_ledger,
    record_prediction_verification,
    render_prediction_ledger_table,
    verify_prediction_ledger_integrity,
)
from axiom.web import create_app


def _make_sealed_r3_trace_from_export(
    case: CncBenchmarkCase,
    export: CncAlgorithmExport,
    *,
    trace_id: str,
    receipt_id: str,
    actual_y_bias_mm: float = 0.0,
) -> MachineTelemetryTrace:
    t0 = datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc)
    dt = case.sample_period_seconds
    frames = []
    for k, s in enumerate(export.samples):
        assert s.actual_position_mm is not None
        ts = (t0 + timedelta(seconds=round(k * dt, 6))).isoformat().replace("+00:00", "Z")
        frames.append(
            {
                "sequenceId": k,
                "deviceTimestamp": ts,
                "samples": [
                    {"channelId": "cmd_x", "value": float(s.position_mm[0]), "quality": "good"},
                    {"channelId": "cmd_y", "value": float(s.position_mm[1]), "quality": "good"},
                    {"channelId": "cmd_z", "value": float(s.position_mm[2]), "quality": "good"},
                    {"channelId": "act_x", "value": float(s.actual_position_mm[0]), "quality": "good"},
                    {
                        "channelId": "act_y",
                        "value": float(s.actual_position_mm[1]) + actual_y_bias_mm,
                        "quality": "good",
                    },
                    {"channelId": "act_z", "value": float(s.actual_position_mm[2]), "quality": "good"},
                ],
            }
        )
    raw = {
        "schemaVersion": 1,
        "artifactType": "machine.telemetry-trace",
        "traceId": trace_id,
        "sourceKind": "controller-export",
        "deviceIdentity": {
            "deviceId": "vmc-850-shopfloor-01",
            "controllerFamily": "TwinCAT-3",
            "machineModel": "VMC-850",
        },
        "captureReceipt": {
            "receiptId": receipt_id,
            "sourceId": "axiom.windows-file-telemetry-source@1",
            "operation": "file-import",
            "transport": "windows-file-json",
            "capturedAt": "2026-11-12T10:05:00Z",
            "traceContentHash": "0" * 64,
        },
        "frames": frames,
    }
    unsigned = MachineTelemetryTrace.model_validate(raw)
    raw["captureReceipt"]["traceContentHash"] = machine_trace_content_hash(unsigned)
    return MachineTelemetryTrace.model_validate(raw)


def test_synthetic_and_duplicate_ledgers_cannot_promote_r4_r5_claims() -> None:
    demo = build_cnc_parameter_closed_loop_demo(
        offline_count=16, controller_count=10, seed=42, multi_case_calibration=True
    )
    sur = demo.surrogate
    cand = demo.recommendation_report.presets[0]

    # 1. Three synthetic simulator exports -> SyntheticHoldoutNotAccepted
    synth_entries = []
    for idx, cname in enumerate(("corner90", "circle", "s-curve"), 1):
        c = standard_case(cname)
        exp_syn = simulate_realistic_cnc_controller(
            c,
            cand.full_parameters,
            source_kind="controller-trace",
            registry=sur.registry,
        )
        entry = record_prediction_verification(
            c,
            sur,
            exp_syn,
            applied_parameters=cand.full_parameters,
            entry_id=f"syn.{idx:03d}",
        )
        assert entry.evidence_origin == "synthetic-simulation"
        synth_entries.append(entry)

    synth_ledger = build_prediction_verification_ledger(synth_entries, surrogate=sur)
    gov_syn = assess_cnc_greybox_governance(demo, verification_ledger=synth_ledger)
    claims_syn = {c.claim_definition_id: c.status.value for c in gov_syn.run_bundle.claims}
    reasons_syn = {r.metric_id: r.reason_code for r in gov_syn.run_bundle.report.metric_results}
    assert claims_syn[CNC_R4_CALIBRATION_CLAIM_ID] == "Inconclusive"
    assert claims_syn[CNC_R5_EPISTEMIC_CLAIM_ID] == "Inconclusive"
    assert reasons_syn[CNC_R4_CALIBRATION_METRIC_ID] == "SyntheticHoldoutNotAccepted"
    assert reasons_syn[CNC_R5_EPISTEMIC_METRIC_ID] == "SyntheticHoldoutNotAccepted"
    assert gov_syn.run_bundle.report.case_outcome.value == "Inconclusive"

    # 2. External controller trace without R3 capture receipt -> UnattestedHoldoutReceiptRequired
    ext_exp = exp_syn.model_copy(
        update={"algorithm_id": "beckhoff.twincat.scope-csv", "algorithm_version": "nc-3.1.4024"}
    )
    ext_entry = record_prediction_verification(
        standard_case("s-curve"),
        sur,
        ext_exp,
        applied_parameters=cand.full_parameters,
        entry_id="ext.001",
    )
    assert ext_entry.evidence_origin == "external-controller-trace"
    ext_ledger = build_prediction_verification_ledger((ext_entry,) * 3, surrogate=sur)
    gov_ext = assess_cnc_greybox_governance(demo, verification_ledger=ext_ledger)
    reasons_ext = {r.metric_id: r.reason_code for r in gov_ext.run_bundle.report.metric_results}
    assert reasons_ext[CNC_R4_CALIBRATION_METRIC_ID] == "UnattestedHoldoutReceiptRequired"

    # 3. Duplicate R3 trace submitted 3 times -> distinctRealR3TraceCount == 1 -> InsufficientHoldoutSamples
    c90 = standard_case("corner90")
    ref_exp = simulate_realistic_cnc_controller(
        c90, cand.full_parameters, source_kind="controller-trace", registry=sur.registry
    )
    r3_single = _make_sealed_r3_trace_from_export(
        c90, ref_exp, trace_id="r3.dup.01", receipt_id="rcpt.dup.01"
    )
    dup_entries = [
        record_prediction_verification(
            c90,
            sur,
            r3_single,
            recommendation_report=demo.recommendation_report,
            entry_id=f"dup.{k}",
        )
        for k in range(1, 4)
    ]
    dup_ledger = build_prediction_verification_ledger(dup_entries, surrogate=sur)
    assert dup_ledger.summary.real_r3_entry_count == 3
    assert dup_ledger.summary.distinct_real_r3_trace_count == 1
    gov_dup = assess_cnc_greybox_governance(demo, verification_ledger=dup_ledger)
    reasons_dup = {r.metric_id: r.reason_code for r in gov_dup.run_bundle.report.metric_results}
    assert reasons_dup[CNC_R4_CALIBRATION_METRIC_ID] == "InsufficientHoldoutSamples"


def test_real_r3_holdout_ledger_supports_valid_model_and_refutes_misspecified_bounds() -> None:
    demo = build_cnc_parameter_closed_loop_demo(
        offline_count=18, controller_count=10, seed=42, multi_case_calibration=True
    )
    sur = demo.surrogate

    # A. Three distinct R3 verification cuts consistent with calibrated plant -> R4 & R5 Supported!
    good_entries = []
    for idx, cname in enumerate(("corner90", "circle", "s-curve"), 1):
        c = standard_case(cname)
        rec_c = recommend_parameters(
            sur,
            ParameterRecommendationRequest(
                targetCase=c,
                maximumPathDeviationMm=0.055,
                maximumActualPathDeviationMm=0.065,
                seed=10 + idx,
            ),
        )
        chosen = rec_c.presets[0]
        base_exp = simulate_realistic_cnc_controller(
            c, sur.baseline_parameters, source_kind="controller-trace", registry=sur.registry
        )
        ver_exp = simulate_realistic_cnc_controller(
            c, chosen.full_parameters, source_kind="controller-trace", registry=sur.registry
        )
        r3_trace = _make_sealed_r3_trace_from_export(
            c, ver_exp, trace_id=f"r3.holdout.{idx}", receipt_id=f"rcpt.holdout.{idx}"
        )
        good_entries.append(
            record_prediction_verification(
                c,
                sur,
                r3_trace,
                recommendation_report=rec_c,
                candidate_id=chosen.candidate_id,
                baseline_trace_or_report=base_exp,
                entry_id=f"real.good.{idx:03d}",
            )
        )

    good_ledger = build_prediction_verification_ledger(good_entries, surrogate=sur)
    table = render_prediction_ledger_table(good_ledger)
    assert "预测-实测对账单" in table
    assert good_ledger.summary.distinct_real_r3_trace_count == 3
    assert (good_ledger.summary.empirical_coverage_rate or 0.0) >= 0.80

    gov_good = assess_cnc_greybox_governance(demo, verification_ledger=good_ledger)
    claims_good = {c.claim_definition_id: c.status.value for c in gov_good.run_bundle.claims}
    assert claims_good[CNC_R4_CALIBRATION_CLAIM_ID] == "Supported"
    assert claims_good[CNC_R5_EPISTEMIC_CLAIM_ID] == "Supported"
    assert gov_good.run_bundle.report.case_outcome.value == "Passed"
    # Even when R4 & R5 are Supported, R7 permission ceiling stays strictly OfflineAdvisory!
    assert gov_good.permission_ceiling == "OfflineAdvisory"
    assert gov_good.device_write_allowed is False
    assert gov_good.deployment_shadow_status == "Open"

    # B. Three distinct R3 verification cuts with severe unmodeled +0.085 mm bias -> R4 & R5 Refuted!
    bad_entries = []
    for idx, cname in enumerate(("corner90", "circle", "line"), 1):
        c = standard_case(cname)
        ver_exp = simulate_realistic_cnc_controller(
            c, sur.baseline_parameters, source_kind="controller-trace", registry=sur.registry
        )
        r3_bad = _make_sealed_r3_trace_from_export(
            c,
            ver_exp,
            trace_id=f"r3.bad.{idx}",
            receipt_id=f"rcpt.bad.{idx}",
            actual_y_bias_mm=0.085,
        )
        bad_entries.append(
            record_prediction_verification(
                c,
                sur,
                r3_bad,
                applied_parameters=sur.baseline_parameters,
                entry_id=f"real.bad.{idx:03d}",
            )
        )

    bad_ledger = build_prediction_verification_ledger(bad_entries, surrogate=sur)
    gov_bad = assess_cnc_greybox_governance(demo, verification_ledger=bad_ledger)
    claims_bad = {c.claim_definition_id: c.status.value for c in gov_bad.run_bundle.claims}
    assert claims_bad[CNC_R4_CALIBRATION_CLAIM_ID] == "Refuted"
    assert claims_bad[CNC_R5_EPISTEMIC_CLAIM_ID] == "Refuted"
    assert gov_bad.run_bundle.report.case_outcome.value == "Failed"

    # C. Tampered ledger summary hash is caught by verify_prediction_ledger_integrity and governance
    tampered_summary = bad_ledger.summary.model_copy(update={"empirical_coverage_rate": 1.0})
    tampered_ledger = bad_ledger.model_copy(update={"summary": tampered_summary})
    with pytest.raises(ValueError, match="ledgerContentHash"):
        verify_prediction_ledger_integrity(tampered_ledger)

    gov_tampered = assess_cnc_greybox_governance(demo, verification_ledger=tampered_ledger)
    reasons_t = {r.metric_id: r.reason_code for r in gov_tampered.run_bundle.report.metric_results}
    assert reasons_t[CNC_R4_CALIBRATION_METRIC_ID] == "ContentHashMismatch"
    assert reasons_t[CNC_R5_EPISTEMIC_METRIC_ID] == "ContentHashMismatch"


def test_cli_and_web_prediction_ledger_and_holdout_governance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = build_cnc_parameter_closed_loop_demo(
        offline_count=16, controller_count=8, seed=42, multi_case_calibration=True
    )
    sur = demo.surrogate
    cand = demo.recommendation_report.presets[0]

    model_path = tmp_path / "surrogate.json"
    rec_path = tmp_path / "recommendation.json"
    ledger_path = tmp_path / "ledger.json"
    model_path.write_text(
        sur.model_dump_json(indent=2, by_alias=True, exclude_none=True), encoding="utf-8"
    )
    rec_path.write_text(
        demo.recommendation_report.model_dump_json(indent=2, by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    # Append 3 distinct R3 verification cuts via CLI `param-ledger`
    last_case_path = tmp_path / "case_1.json"
    last_exp_path = tmp_path / "exp_1.json"
    for idx, cname in enumerate(("corner90", "circle", "line"), 1):
        c = standard_case(cname)
        ver_exp = simulate_realistic_cnc_controller(
            c, cand.full_parameters, source_kind="controller-trace", registry=sur.registry
        )
        r3 = _make_sealed_r3_trace_from_export(
            c, ver_exp, trace_id=f"cli.r3.{idx}", receipt_id=f"cli.rcpt.{idx}"
        )
        c_path = tmp_path / f"case_{idx}.json"
        r3_path = tmp_path / f"r3_{idx}.json"
        e_path = tmp_path / f"exp_{idx}.json"
        c_path.write_text(c.model_dump_json(indent=2, by_alias=True, exclude_none=True), encoding="utf-8")
        r3_path.write_text(r3.model_dump_json(indent=2, by_alias=True, exclude_none=True), encoding="utf-8")
        e_path.write_text(ver_exp.model_dump_json(indent=2, by_alias=True, exclude_none=True), encoding="utf-8")
        last_case_path, last_exp_path = c_path, e_path

        cmd = [
            "param-ledger",
            "--case",
            str(c_path),
            "--model",
            str(model_path),
            "--trace",
            str(r3_path),
            "--params",
            str(tmp_path / f"params_{idx}.json"),
            "--entry-id",
            f"cli.entry.{idx}",
            "--out",
            str(ledger_path),
        ]
        (tmp_path / f"params_{idx}.json").write_text(
            json.dumps(cand.full_parameters), encoding="utf-8"
        )
        if idx > 1:
            cmd.extend(["--ledger-in", str(ledger_path)])
        rc_led = cli_main(cmd)
        assert rc_led == 0
        capsys.readouterr()

    # Run CLI `param-governance --ledger` -> exit code 0 ("Passed"!)
    rc_gov = cli_main(
        [
            "param-governance",
            "--case",
            str(last_case_path),
            "--export",
            str(last_exp_path),
            "--model",
            str(model_path),
            "--recommendation",
            str(rec_path),
            "--ledger",
            str(ledger_path),
        ]
    )
    assert rc_gov == 0
    gov_json = json.loads(capsys.readouterr().out)
    assert gov_json["runBundle"]["report"]["caseOutcome"] == "Passed"

    # Web API `/api/v1/benchmarks/cnc/param-ledger` + `/api/v1/benchmarks/cnc/param-governance`
    client = TestClient(create_app())
    c_line = standard_case("line")
    ver_line = simulate_realistic_cnc_controller(
        c_line, cand.full_parameters, source_kind="controller-trace", registry=sur.registry
    )
    r3_web = _make_sealed_r3_trace_from_export(
        c_line, ver_line, trace_id="web.r3.01", receipt_id="web.rcpt.01"
    )
    r_led = client.post(
        "/api/v1/benchmarks/cnc/param-ledger",
        json={
            "case": c_line.model_dump(mode="json", by_alias=True, exclude_none=True),
            "surrogate": sur.model_dump(mode="json", by_alias=True, exclude_none=True),
            "verificationTrace": r3_web.model_dump(mode="json", by_alias=True, exclude_none=True),
            "appliedParameters": cand.full_parameters,
            "existingLedger": json.loads(ledger_path.read_text(encoding="utf-8")),
            "entryId": "web.entry.04",
        },
    )
    assert r_led.status_code == 200
    assert r_led.json()["summary"]["distinctRealR3TraceCount"] == 4

    r_gov = client.post(
        "/api/v1/benchmarks/cnc/param-governance",
        json={
            **demo.model_dump(mode="json", by_alias=True, exclude_none=True),
            "verificationLedger": r_led.json(),
        },
    )
    assert r_gov.status_code == 200
    assert r_gov.json()["runBundle"]["report"]["caseOutcome"] == "Passed"
