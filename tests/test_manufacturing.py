"""Tests for manufacturing capability validation."""

from __future__ import annotations

from pathlib import Path

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.core.manufacturing import (
    check_assembly_compatibility,
    estimate_board_cost,
    load_capabilities,
)
from etchant.core.models import CircuitSpec


class TestLoadCapabilities:
    def test_loads_jlcpcb(self, constraints_dir: Path) -> None:
        caps = load_capabilities(constraints_dir)
        assert caps["manufacturer"] == "JLCPCB"
        assert "capabilities" in caps


class TestAssemblyCompatibility:
    def test_tht_components_flagged(self, constraints_dir: Path, lm2596_spec: CircuitSpec) -> None:
        design = LM2596BuckConverter().generate(lm2596_spec)
        issues = check_assembly_compatibility(design, constraints_dir)
        # LM2596 design has THT caps, inductor, and diode
        tht_issues = [i for i in issues if "Through-hole" in i["issue"]]
        assert len(tht_issues) > 0

    def test_issues_have_required_fields(
        self, constraints_dir: Path, lm2596_spec: CircuitSpec
    ) -> None:
        design = LM2596BuckConverter().generate(lm2596_spec)
        issues = check_assembly_compatibility(design, constraints_dir)
        for issue in issues:
            assert "component" in issue
            assert "issue" in issue
            assert "severity" in issue


class TestBoardCostEstimate:
    def test_small_2layer_board(self) -> None:
        cost = estimate_board_cost(board_size_mm=(50, 50), layers=2, quantity=5)
        assert cost["per_board_usd"] > 0
        assert cost["total_boards_usd"] > 0
        assert cost["board_area_mm2"] == 2500

    def test_larger_board_costs_more(self) -> None:
        small = estimate_board_cost(board_size_mm=(50, 50), layers=2, quantity=5)
        large = estimate_board_cost(board_size_mm=(150, 150), layers=2, quantity=5)
        assert large["per_board_usd"] > small["per_board_usd"]

    def test_more_layers_costs_more(self) -> None:
        two = estimate_board_cost(board_size_mm=(50, 50), layers=2, quantity=5)
        four = estimate_board_cost(board_size_mm=(50, 50), layers=4, quantity=5)
        assert four["per_board_usd"] > two["per_board_usd"]
