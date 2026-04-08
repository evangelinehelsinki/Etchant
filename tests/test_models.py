"""Tests for core data models."""

from __future__ import annotations

import pytest

from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
    PlacementConstraint,
)


class TestCircuitSpec:
    def test_construction(self) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=2.0,
            description="test spec",
        )
        assert spec.name == "test"
        assert spec.topology == "buck_converter"
        assert spec.input_voltage == 12.0

    def test_frozen(self) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=2.0,
            description="test spec",
        )
        with pytest.raises(AttributeError):
            spec.name = "modified"  # type: ignore[misc]


class TestComponentSpec:
    def test_construction(self) -> None:
        comp = ComponentSpec(
            reference="U1",
            category=ComponentCategory.IC,
            value="LM2596S-5",
            footprint="Package_TO_SOT_SMD:TO-263-5_TabPin3",
            kicad_library="Regulator_Switching",
            kicad_symbol="LM2596S-5",
            description="Buck regulator",
        )
        assert comp.reference == "U1"
        assert comp.category == ComponentCategory.IC
        assert comp.jlcpcb_part_number is None

    def test_with_jlcpcb_part(self) -> None:
        comp = ComponentSpec(
            reference="C1",
            category=ComponentCategory.CAPACITOR,
            value="680uF",
            footprint="Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
            kicad_library="Device",
            kicad_symbol="C_Polarized",
            description="Input cap",
            jlcpcb_part_number="C296751",
        )
        assert comp.jlcpcb_part_number == "C296751"

    def test_frozen(self) -> None:
        comp = ComponentSpec(
            reference="U1",
            category=ComponentCategory.IC,
            value="LM2596S-5",
            footprint="test",
            kicad_library="test",
            kicad_symbol="test",
            description="test",
        )
        with pytest.raises(AttributeError):
            comp.reference = "U2"  # type: ignore[misc]

    def test_properties_immutable(self) -> None:
        comp = ComponentSpec(
            reference="U1",
            category=ComponentCategory.IC,
            value="LM2596S-5",
            footprint="test",
            kicad_library="test",
            kicad_symbol="test",
            description="test",
            properties={"key": "value"},
        )
        with pytest.raises(TypeError):
            comp.properties["new_key"] = "oops"  # type: ignore[index]


class TestNetSpec:
    def test_construction(self) -> None:
        net = NetSpec(
            name="VIN",
            connections=(("C1", "1"), ("U1", "IN")),
        )
        assert net.name == "VIN"
        assert len(net.connections) == 2

    def test_connections_are_tuples(self) -> None:
        net = NetSpec(
            name="GND",
            connections=(("U1", "GND"), ("C1", "2")),
        )
        assert isinstance(net.connections, tuple)
        assert isinstance(net.connections[0], tuple)


class TestDesignResult:
    def test_construction(self) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=2.0,
            description="test",
        )
        result = DesignResult(
            spec=spec,
            components=(),
            nets=(),
            placement_constraints=(),
            design_notes=("note1",),
        )
        assert result.spec == spec
        assert len(result.components) == 0
        assert result.design_notes == ("note1",)

    def test_collections_are_tuples(self) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=2.0,
            description="test",
        )
        result = DesignResult(
            spec=spec,
            components=(),
            nets=(),
            placement_constraints=(),
            design_notes=(),
        )
        assert isinstance(result.components, tuple)
        assert isinstance(result.nets, tuple)
        assert isinstance(result.placement_constraints, tuple)
        assert isinstance(result.design_notes, tuple)


class TestPlacementConstraint:
    def test_with_target(self) -> None:
        pc = PlacementConstraint(
            component_ref="C1",
            target_ref="U1",
            max_distance_mm=50.0,
            reason="Close to IC",
        )
        assert pc.target_ref == "U1"

    def test_without_target(self) -> None:
        pc = PlacementConstraint(
            component_ref="C2",
            target_ref=None,
            max_distance_mm=30.0,
            reason="Close to load",
        )
        assert pc.target_ref is None
