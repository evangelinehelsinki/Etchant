"""Tests for the component placement stub."""

from __future__ import annotations

from pathlib import Path

import pytest

from etchant.core.models import (
    CircuitSpec,
    DesignResult,
)
from etchant.kicad.placement import ComponentPlacer


class TestComponentPlacer:
    def test_raises_not_implemented(self) -> None:
        placer = ComponentPlacer()
        spec = CircuitSpec(
            name="test",
            topology="buck",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=2.0,
            description="test",
        )
        design = DesignResult(
            spec=spec,
            components=(),
            nets=(),
            placement_constraints=(),
            design_notes=(),
        )
        with pytest.raises(NotImplementedError, match="pcbnew"):
            placer.place_components(Path("/tmp/test.kicad_pcb"), design)
