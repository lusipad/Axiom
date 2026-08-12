from __future__ import annotations

from axiom import evaluate_run
from axiom.machine.scenarios import (
    list_machine_r3_scenarios,
    machine_r3_example_run_spec,
)
from axiom.run import validate_run_bundle_integrity


def test_machine_r3_reference_scenarios_replay_deterministically() -> None:
    for scenario in list_machine_r3_scenarios():
        first = evaluate_run(machine_r3_example_run_spec(scenario["scenarioId"]))
        second = evaluate_run(machine_r3_example_run_spec(scenario["scenarioId"]))
        assert validate_run_bundle_integrity(first) == []
        assert first.bundle_hash == second.bundle_hash
