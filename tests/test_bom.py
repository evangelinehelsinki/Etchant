"""Tests for BOM generation and cost estimation."""

from __future__ import annotations

import pytest

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.core.bom import BOMEntry, BOMGenerator, CostBreakdown
from etchant.core.component_selector import PartClassification
from etchant.core.models import CircuitSpec


@pytest.fixture
def bom_generator() -> BOMGenerator:
    return BOMGenerator()


@pytest.fixture
def buck_design(lm2596_spec: CircuitSpec):  # type: ignore[type-arg]
    return LM2596BuckConverter().generate(lm2596_spec)


class TestBOMEntry:
    def test_frozen(self) -> None:
        entry = BOMEntry(
            reference="U1",
            value="LM2596S-5",
            footprint="Package_TO_SOT_SMD:TO-263-5_TabPin3",
            description="Buck regulator",
            quantity=1,
            jlcpcb_part_number="C2837",
            classification=PartClassification.EXTENDED,
            unit_price_usd=None,
        )
        with pytest.raises(AttributeError):
            entry.reference = "U2"  # type: ignore[misc]


class TestBOMGenerator:
    def test_generates_bom_from_design(self, bom_generator: BOMGenerator, buck_design) -> None:  # type: ignore[type-arg]
        bom = bom_generator.generate(buck_design)
        assert len(bom) == 6
        refs = {e.reference for e in bom}
        assert refs == {"U1", "C1", "C2", "L1", "D1", "R1"}

    def test_bom_entries_have_jlcpcb_info(self, bom_generator: BOMGenerator, buck_design) -> None:  # type: ignore[type-arg]
        bom = bom_generator.generate(buck_design)
        for entry in bom:
            assert entry.jlcpcb_part_number is not None or entry.classification is not None

    def test_bom_quantities_are_one(self, bom_generator: BOMGenerator, buck_design) -> None:  # type: ignore[type-arg]
        bom = bom_generator.generate(buck_design)
        for entry in bom:
            assert entry.quantity == 1


class TestCostBreakdown:
    def test_cost_breakdown_from_design(self, bom_generator: BOMGenerator, buck_design) -> None:  # type: ignore[type-arg]
        bom = bom_generator.generate(buck_design)
        cost = CostBreakdown.from_bom(bom)
        assert cost.basic_parts_count >= 0
        assert cost.extended_parts_count >= 0
        assert cost.total_setup_fee_usd >= 0
        assert cost.basic_parts_count + cost.extended_parts_count + cost.unknown_parts_count == 6

    def test_basic_parts_have_no_setup_fee(self) -> None:
        bom = (
            BOMEntry(
                reference="R1",
                value="10k",
                footprint="test",
                description="test",
                quantity=1,
                jlcpcb_part_number="C17414",
                classification=PartClassification.BASIC,
                unit_price_usd=None,
            ),
        )
        cost = CostBreakdown.from_bom(bom)
        assert cost.basic_parts_count == 1
        assert cost.extended_parts_count == 0
        assert cost.total_setup_fee_usd == 0.0

    def test_extended_parts_add_setup_fees(self) -> None:
        bom = (
            BOMEntry(
                reference="U1",
                value="LM2596S-5",
                footprint="test",
                description="test",
                quantity=1,
                jlcpcb_part_number="C2837",
                classification=PartClassification.EXTENDED,
                unit_price_usd=None,
            ),
            BOMEntry(
                reference="C1",
                value="680uF",
                footprint="test",
                description="test",
                quantity=1,
                jlcpcb_part_number="C296751",
                classification=PartClassification.EXTENDED,
                unit_price_usd=None,
            ),
        )
        cost = CostBreakdown.from_bom(bom)
        assert cost.extended_parts_count == 2
        assert cost.total_setup_fee_usd == 6.0

    def test_summary_string(self, bom_generator: BOMGenerator, buck_design) -> None:  # type: ignore[type-arg]
        bom = bom_generator.generate(buck_design)
        cost = CostBreakdown.from_bom(bom)
        summary = cost.summary()
        assert "basic" in summary.lower()
        assert "extended" in summary.lower()
