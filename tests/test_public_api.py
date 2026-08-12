from __future__ import annotations

import axiom


def test_builtin_domain_packs_runtime_bindings_and_adapter_are_publicly_registered():
    domain_pack_ids = {pack.domain_pack_id for pack in axiom.list_domain_packs()}
    adapter_ids = {adapter.adapter_id for adapter in axiom.list_artifact_adapters()}

    assert domain_pack_ids >= {
        "ordered-point.domain-pack@1",
        "five-axis.domain-pack@1",
        "five-axis.domain-pack@2",
        "five-axis.domain-pack@3",
        "five-axis.domain-pack@4",
        "intelligence.domain-pack@2",
    }
    assert axiom.get_domain_runtime_binding("ordered-point.domain-pack@1")
    assert axiom.get_domain_runtime_binding("five-axis.domain-pack@1")
    assert axiom.get_domain_runtime_binding("five-axis.domain-pack@2")
    assert axiom.get_domain_runtime_binding("five-axis.domain-pack@3")
    assert axiom.get_domain_runtime_binding("five-axis.domain-pack@4")
    assert axiom.get_domain_runtime_binding("intelligence.domain-pack@2")
    assert "five-axis.sampled-cartesian-to-ordered-point@1" in adapter_ids
    assert axiom.FIVE_AXIS_F1_DOMAIN_PACK.domain_pack_id == "five-axis.domain-pack@2"
    assert hasattr(axiom, "F1ExamplePayload")
    assert hasattr(axiom, "build_f1_manifest")
    assert hasattr(axiom, "f1_example_run_spec")
    assert axiom.FIVE_AXIS_F3_DOMAIN_PACK.domain_pack_id == "five-axis.domain-pack@4"
    assert hasattr(axiom, "F3ExamplePayload")
    assert hasattr(axiom, "build_f3_manifest")
    assert hasattr(axiom, "validate_f3_example_run_spec")
    assert axiom.R5B_DOMAIN_PACK.domain_pack_id == "intelligence.domain-pack@2"
    assert hasattr(axiom, "R5BManifest")
    assert hasattr(axiom, "build_r5b_manifest")
    assert hasattr(axiom, "r5b_example_run_spec")


def test_five_axis_f0_public_example_runs_without_math_or_device_claims():
    bundle = axiom.evaluate_run(axiom.f0_example_run_spec())

    assert bundle.report.case_outcome.value == "Passed"
    assert [claim.claim_definition_id for claim in bundle.claims] == [
        "axiom.core.case-outcome-claim@1"
    ]
    assert bundle.report.metric_result("five-axis.contract.readiness@1").value is True
    assert not any(
        token in claim.predicate.lower()
        for claim in bundle.claims
        for token in ("geometry", "collision", "kinematic", "interval", "device")
    )
