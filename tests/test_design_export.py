"""Tests for design export formats."""

from __future__ import annotations

import json
from pathlib import Path

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.core.models import CircuitSpec
from etchant.kicad.design_export import DesignExporter


class TestDesignExporter:
    def _make_design(self, lm2596_spec: CircuitSpec):  # type: ignore[no-untyped-def]
        return LM2596BuckConverter().generate(lm2596_spec)

    def test_export_json(self, tmp_path: Path, lm2596_spec: CircuitSpec) -> None:
        design = self._make_design(lm2596_spec)
        exporter = DesignExporter(tmp_path)
        path = exporter.export_json(design)

        assert path.exists()
        assert path.suffix == ".json"

        with open(path) as f:
            data = json.load(f)

        assert data["spec"]["topology"] == "buck_converter"
        assert len(data["components"]) == 6
        assert len(data["nets"]) == 5

    def test_export_json_roundtrip(self, tmp_path: Path, lm2596_spec: CircuitSpec) -> None:
        design = self._make_design(lm2596_spec)
        exporter = DesignExporter(tmp_path)
        path = exporter.export_json(design)

        with open(path) as f:
            data = json.load(f)

        # Verify all component refs are present
        refs = {c["reference"] for c in data["components"]}
        assert refs == {"U1", "C1", "C2", "L1", "D1", "R1"}

        # Verify net connections are serialized
        net_by_name = {n["name"]: n for n in data["nets"]}
        assert "VIN" in net_by_name
        assert len(net_by_name["GND"]["connections"]) == 5

    def test_export_bom_csv(self, tmp_path: Path, lm2596_spec: CircuitSpec) -> None:
        design = self._make_design(lm2596_spec)
        exporter = DesignExporter(tmp_path)
        path = exporter.export_bom_csv(design)

        assert path.exists()
        assert path.suffix == ".csv"

        content = path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 7  # header + 6 components
        assert "Reference" in lines[0]
        assert "JLCPCB" in lines[0]

    def test_export_creates_output_dir(self, tmp_path: Path, lm2596_spec: CircuitSpec) -> None:
        design = self._make_design(lm2596_spec)
        nested = tmp_path / "deep" / "nested" / "dir"
        exporter = DesignExporter(nested)
        path = exporter.export_json(design)
        assert path.exists()
