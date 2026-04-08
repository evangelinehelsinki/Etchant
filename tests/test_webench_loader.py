"""Tests for the WEBENCH data loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from etchant.data.webench_loader import (
    load_component_json,
    load_webench_directory,
    summarize_designs,
)

_WEBENCH_DIR = Path("/home/evangeline/Projects/etchant-data/data/webench")
_has_webench = _WEBENCH_DIR.exists()

requires_webench = pytest.mark.skipif(
    not _has_webench,
    reason="WEBENCH data not available",
)


@requires_webench
class TestLoadWebench:
    def test_loads_designs(self) -> None:
        designs = load_webench_directory(_WEBENCH_DIR)
        assert len(designs) > 50  # Should have ~100 designs

    def test_design_has_components(self) -> None:
        designs = load_webench_directory(_WEBENCH_DIR)
        for d in designs[:5]:
            assert len(d.components) > 0
            assert d.device != ""
            assert d.vout > 0

    def test_12v_to_5v_designs_exist(self) -> None:
        designs = load_webench_directory(_WEBENCH_DIR)
        buck_5v = [d for d in designs if d.vout == 5.0 and d.vin_min == 12.0]
        assert len(buck_5v) > 0

    def test_efficiency_in_range(self) -> None:
        designs = load_webench_directory(_WEBENCH_DIR)
        for d in designs:
            if d.efficiency > 0:
                assert 0.5 < d.efficiency < 1.0

    def test_summarize(self) -> None:
        designs = load_webench_directory(_WEBENCH_DIR)
        summary = summarize_designs(designs)
        assert "WEBENCH designs:" in summary
        assert "efficient" in summary


class TestLoadComponentJson:
    def test_load_single_file(self, tmp_path: Path) -> None:
        import json

        data = {
            "spec": {"vin_min": 12, "vin_max": 12, "vout": 5, "iout": 2.0},
            "device": "TestIC",
            "topology": "Buck",
            "efficiency": 0.92,
            "bom_cost": 1.50,
            "bom_count": 5,
            "frequency_hz": 500000,
            "temperature_c": 45.0,
            "components": [
                {"ref": "L1", "value": "10uH", "qty": 1, "dcr": "20mOhm"},
                {"ref": "Cout", "value": "22uF", "qty": 2, "esr": "3mOhm"},
            ],
        }
        path = tmp_path / "TestIC_components.json"
        with open(path, "w") as f:
            json.dump(data, f)

        design = load_component_json(path)
        assert design is not None
        assert design.device == "TestIC"
        assert design.efficiency == 0.92
        assert len(design.components) == 2
        assert design.components[0].dcr == "20mOhm"


class TestSummarize:
    def test_empty(self) -> None:
        assert "No WEBENCH" in summarize_designs([])
