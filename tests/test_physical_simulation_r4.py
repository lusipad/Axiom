from __future__ import annotations

import math

from axiom.physical.simulation import exact_zoh_response, fit_first_order_axis


def test_exact_zoh_uses_previous_interval_command() -> None:
    response = exact_zoh_response(
        (0.0, 1.0, 1.0),
        (0.0, 0.1, 0.2),
        time_constant_seconds=0.1,
        bias=0.0,
    )
    assert response[0] == 0.0
    assert response[1] == 0.0
    assert math.isclose(response[2], 1.0 - math.exp(-1.0), abs_tol=1e-12)


def test_grid_fit_recovers_deterministic_first_order_parameters() -> None:
    times = tuple(index * 0.08 for index in range(10))
    command = (0.0, 0.3, 0.7, 1.0, 1.2, 1.3, 1.35, 1.38, 1.4, 1.4)
    observation = exact_zoh_response(command, times, time_constant_seconds=0.12, bias=0.025)
    fitted = fit_first_order_axis(
        axis_id="X",
        axis_index=0,
        unit_family="linear-mm",
        unit="mm",
        command=command,
        observation=observation,
        times=times,
        excitation_span_minimum=0.01,
    )
    assert fitted.status == "identified"
    assert fitted.time_constant_seconds == 0.12
    assert math.isclose(fitted.bias or 0.0, 0.025, abs_tol=1e-12)
    assert fitted.rmse is not None and fitted.rmse < 1e-12


def test_grid_fit_refuses_unexcited_rotary_axis() -> None:
    fitted = fit_first_order_axis(
        axis_id="B",
        axis_index=3,
        unit_family="rotary-rad",
        unit="rad",
        command=(0.0, 0.0, 0.0),
        observation=(0.0, 0.0, 0.0),
        times=(0.0, 0.08, 0.16),
        excitation_span_minimum=0.01,
    )
    assert fitted.status == "insufficient-excitation"
    assert fitted.time_constant_seconds is None
    assert fitted.bias is None
    assert fitted.deterministic_work_units == 0
