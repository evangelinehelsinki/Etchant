"""Tests for design comparison."""

from __future__ import annotations

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.core.comparison import ComparisonResult, compare_designs
from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
)


class TestIdenticalDesigns:
    def test_same_design_matches(self, lm2596_spec: CircuitSpec) -> None:
        design = LM2596BuckConverter().generate(lm2596_spec)
        result = compare_designs(design, design)
        assert result.matches
        assert result.total_diffs == 0

    def test_summary_for_match(self, lm2596_spec: CircuitSpec) -> None:
        design = LM2596BuckConverter().generate(lm2596_spec)
        result = compare_designs(design, design)
        assert result.summary() == "Designs match"


class TestComponentDiffs:
    def test_missing_component(self) -> None:
        spec = CircuitSpec(
            name="test", topology="test",
            input_voltage=5.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        expected = DesignResult(
            spec=spec,
            components=(
                ComponentSpec(
                    reference="U1", category=ComponentCategory.IC,
                    value="LM2596", footprint="test", kicad_library="test",
                    kicad_symbol="test", description="test",
                ),
                ComponentSpec(
                    reference="C1", category=ComponentCategory.CAPACITOR,
                    value="100uF", footprint="test", kicad_library="test",
                    kicad_symbol="test", description="test",
                ),
            ),
            nets=(), placement_constraints=(), design_notes=(),
        )
        actual = DesignResult(
            spec=spec,
            components=(
                ComponentSpec(
                    reference="U1", category=ComponentCategory.IC,
                    value="LM2596", footprint="test", kicad_library="test",
                    kicad_symbol="test", description="test",
                ),
            ),
            nets=(), placement_constraints=(), design_notes=(),
        )
        result = compare_designs(actual, expected)
        assert not result.matches
        assert any("Missing component C1" in d for d in result.component_diffs)

    def test_wrong_value(self) -> None:
        spec = CircuitSpec(
            name="test", topology="test",
            input_voltage=5.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        base_comp = ComponentSpec(
            reference="C1", category=ComponentCategory.CAPACITOR,
            value="100uF", footprint="test", kicad_library="test",
            kicad_symbol="test", description="test",
        )
        wrong_comp = ComponentSpec(
            reference="C1", category=ComponentCategory.CAPACITOR,
            value="220uF", footprint="test", kicad_library="test",
            kicad_symbol="test", description="test",
        )
        expected = DesignResult(
            spec=spec, components=(base_comp,),
            nets=(), placement_constraints=(), design_notes=(),
        )
        actual = DesignResult(
            spec=spec, components=(wrong_comp,),
            nets=(), placement_constraints=(), design_notes=(),
        )
        result = compare_designs(actual, expected)
        assert not result.matches
        assert any("220uF" in d and "100uF" in d for d in result.component_diffs)


class TestNetDiffs:
    def test_missing_net(self) -> None:
        spec = CircuitSpec(
            name="test", topology="test",
            input_voltage=5.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        expected = DesignResult(
            spec=spec, components=(),
            nets=(NetSpec(name="VIN", connections=(("U1", "1"),)),),
            placement_constraints=(), design_notes=(),
        )
        actual = DesignResult(
            spec=spec, components=(), nets=(),
            placement_constraints=(), design_notes=(),
        )
        result = compare_designs(actual, expected)
        assert any("Missing net VIN" in d for d in result.net_diffs)

    def test_missing_connection(self) -> None:
        spec = CircuitSpec(
            name="test", topology="test",
            input_voltage=5.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        expected = DesignResult(
            spec=spec, components=(),
            nets=(NetSpec(name="VIN", connections=(("U1", "1"), ("C1", "1"))),),
            placement_constraints=(), design_notes=(),
        )
        actual = DesignResult(
            spec=spec, components=(),
            nets=(NetSpec(name="VIN", connections=(("U1", "1"),)),),
            placement_constraints=(), design_notes=(),
        )
        result = compare_designs(actual, expected)
        assert any("missing connection C1.1" in d for d in result.net_diffs)


class TestComparisonResult:
    def test_total_diffs(self) -> None:
        result = ComparisonResult(
            matches=False,
            component_diffs=("a", "b"),
            net_diffs=("c",),
            constraint_diffs=(),
            note_diffs=("d",),
        )
        assert result.total_diffs == 4

    def test_summary_includes_all_types(self) -> None:
        result = ComparisonResult(
            matches=False,
            component_diffs=("comp issue",),
            net_diffs=("net issue",),
            constraint_diffs=(),
            note_diffs=(),
        )
        summary = result.summary()
        assert "[component]" in summary
        assert "[net]" in summary
