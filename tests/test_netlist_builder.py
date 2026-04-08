"""Tests for the SKiDL netlist builder.

Unit tests use mocks to verify the builder's logic without requiring
KiCad libraries. Integration tests (marked requires_skidl) need distrobox.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
)
from etchant.kicad.netlist_builder import NetlistBuilder, check_skidl_available


@pytest.fixture
def simple_design() -> DesignResult:
    spec = CircuitSpec(
        name="test_circuit",
        topology="test",
        input_voltage=5.0,
        output_voltage=3.3,
        output_current=1.0,
        description="test",
    )
    return DesignResult(
        spec=spec,
        components=(
            ComponentSpec(
                reference="R1",
                category=ComponentCategory.RESISTOR,
                value="10k",
                footprint="Resistor_SMD:R_0805",
                kicad_library="Device",
                kicad_symbol="R",
                description="test resistor",
            ),
        ),
        nets=(
            NetSpec(name="VIN", connections=(("R1", "1"),)),
        ),
        placement_constraints=(),
        design_notes=(),
    )


class TestCheckAvailability:
    def test_returns_bool(self) -> None:
        result = check_skidl_available()
        assert isinstance(result, bool)


class TestNetlistBuilderWithMocks:
    @patch("etchant.kicad.netlist_builder.HAS_SKIDL", False)
    @patch("etchant.kicad.netlist_builder._KICAD_LIBS_AVAILABLE", False)
    def test_raises_when_skidl_unavailable(
        self, tmp_path: Path, simple_design: DesignResult
    ) -> None:
        builder = NetlistBuilder(tmp_path)
        with pytest.raises(RuntimeError, match="SKiDL is not installed"):
            builder.build(simple_design)

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested"
        builder = NetlistBuilder(nested)
        assert not nested.exists()
        # The directory creation happens in build(), but we can't call it
        # without SKiDL. Just verify the path is stored.
        assert builder._output_dir == nested


class TestNetlistBuilderIntegration:
    """Integration tests that require SKiDL + KiCad libraries (distrobox)."""

    @pytest.mark.skipif(
        not check_skidl_available(),
        reason="SKiDL + KiCad libraries not available (run inside distrobox)",
    )
    def test_generates_netlist_file(
        self, tmp_path: Path, simple_design: DesignResult
    ) -> None:
        builder = NetlistBuilder(tmp_path)
        netlist_path = builder.build(simple_design)
        assert netlist_path.exists()
        assert netlist_path.suffix == ".net"
        assert netlist_path.stat().st_size > 0
