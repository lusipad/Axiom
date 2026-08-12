from __future__ import annotations

import pytest
from pydantic import ValidationError

from axiom.physical.models import PhysicalAxisParameter


def test_identified_axis_requires_tau_and_bias() -> None:
    with pytest.raises(ValidationError, match="identified axes require"):
        PhysicalAxisParameter(
            axisId="X",
            axisIndex=0,
            unitFamily="linear-mm",
            unit="mm",
            excitationStatus="identified",
        )


def test_insufficient_axis_rejects_guessed_parameters() -> None:
    with pytest.raises(ValidationError, match="insufficient axes must omit"):
        PhysicalAxisParameter(
            axisId="B",
            axisIndex=3,
            unitFamily="rotary-rad",
            unit="rad",
            excitationStatus="insufficient-excitation",
            timeConstantSeconds=0.1,
            bias=0.0,
        )


def test_axis_unit_families_are_not_interchangeable() -> None:
    with pytest.raises(ValidationError, match="unit must match"):
        PhysicalAxisParameter(
            axisId="B",
            axisIndex=3,
            unitFamily="rotary-rad",
            unit="mm",
            excitationStatus="insufficient-excitation",
        )
