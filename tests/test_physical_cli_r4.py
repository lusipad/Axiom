from __future__ import annotations

import json

from axiom.cli import main
from axiom.physical.scenarios import validate_r4_example_run_spec


def test_r4_run_spec_uses_the_same_status_semantics_through_cli(tmp_path, capsys) -> None:
    request_path = tmp_path / "physical-r4-run.json"
    request_path.write_text(
        validate_r4_example_run_spec().model_dump_json(by_alias=True, exclude_none=True, indent=2),
        encoding="utf-8",
    )

    assert main(["run", str(request_path)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["run"]["domainPackId"] == "five-axis.domain-pack@6"
    assert payload["run"]["caseOutcome"] == "Passed"
    reality_claim = next(
        claim
        for claim in payload["claims"]
        if claim["claimDefinitionId"] == "five-axis.physical-model-reality-validated-claim@1"
    )
    assert reality_claim["status"] == "Inconclusive"
