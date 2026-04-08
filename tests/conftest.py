"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from etchant.core.models import CircuitSpec


@pytest.fixture
def lm2596_spec() -> CircuitSpec:
    return CircuitSpec(
        name="lm2596_buck_12v_5v",
        topology="buck_converter",
        input_voltage=12.0,
        output_voltage=5.0,
        output_current=2.0,
        description="LM2596 12V to 5V 2A buck converter",
    )


@pytest.fixture
def golden_dir() -> Path:
    return Path(__file__).parent / "golden"


@pytest.fixture
def constraints_dir() -> Path:
    return Path(__file__).parent.parent / "constraints"
