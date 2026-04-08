"""Tests for the component placement engine."""

from __future__ import annotations

from etchant.circuits.ldo_regulator import AMS1117LDORegulator
from etchant.core.models import CircuitSpec
from etchant.kicad.placement import ComponentPlacer, check_pcbnew_available


class TestComponentPlacer:
    def test_check_availability_returns_bool(self) -> None:
        assert isinstance(check_pcbnew_available(), bool)

    def test_calculate_positions(self) -> None:
        """Test position calculation (works without pcbnew)."""
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=5.0, output_voltage=3.3, output_current=0.5,
            description="test",
        )
        design = AMS1117LDORegulator().generate(spec)
        placer = ComponentPlacer()
        positions = placer._calculate_positions(design, 30.0, 25.0)

        # IC should be in center
        assert "U1" in positions
        u1_x, u1_y, _ = positions["U1"]
        assert 14 < u1_x < 16  # ~center of 30mm
        assert 11 < u1_y < 14  # ~center of 25mm

        # All components should have positions
        for comp in design.components:
            assert comp.reference in positions
