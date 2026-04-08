"""Tests for the component selector."""

from __future__ import annotations

from pathlib import Path

from etchant.core.component_selector import (
    JLCPCBPartInfo,
    PartClassification,
    find_trace_width,
    lookup_jlcpcb_part,
)


class TestPartClassification:
    def test_basic_part(self) -> None:
        info = JLCPCBPartInfo(
            part_number="C296751",
            classification=PartClassification.BASIC,
            description="680uF 25V electrolytic capacitor",
            stock=50000,
        )
        assert info.classification == PartClassification.BASIC
        assert info.setup_fee_usd == 0.0

    def test_extended_part(self) -> None:
        info = JLCPCBPartInfo(
            part_number="C2837",
            classification=PartClassification.EXTENDED,
            description="LM2596S-5",
            stock=1000,
        )
        assert info.classification == PartClassification.EXTENDED
        assert info.setup_fee_usd == 3.0

    def test_unknown_part(self) -> None:
        info = JLCPCBPartInfo(
            part_number="C999999",
            classification=PartClassification.UNKNOWN,
            description="Unknown part",
            stock=0,
        )
        assert info.setup_fee_usd == 3.0


class TestLookupJLCPCBPart:
    def test_known_lm2596(self, constraints_dir: Path) -> None:
        info = lookup_jlcpcb_part("LM2596S-5", constraints_dir)
        assert info is not None
        assert info.part_number is not None

    def test_unknown_part_returns_none(self, constraints_dir: Path) -> None:
        info = lookup_jlcpcb_part("NONEXISTENT_PART_XYZ", constraints_dir)
        assert info is None


class TestTraceWidth:
    def test_2a_trace_width(self, constraints_dir: Path) -> None:
        result = find_trace_width(2.0, constraints_dir)
        assert result is not None
        assert result["min_width_mm"] == 0.5
        assert result["recommended_mm"] == 0.75

    def test_1a_trace_width(self, constraints_dir: Path) -> None:
        result = find_trace_width(1.0, constraints_dir)
        assert result is not None
        assert result["min_width_mm"] == 0.254

    def test_above_max_returns_highest(self, constraints_dir: Path) -> None:
        result = find_trace_width(10.0, constraints_dir)
        assert result is not None
        assert result["current_a"] == 5.0
