"""Tests for the AMS1117 LDO regulator generator with golden reference comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from etchant.circuits.ldo_regulator import AMS1117LDORegulator
from etchant.core.models import CircuitSpec


@pytest.fixture
def generator() -> AMS1117LDORegulator:
    return AMS1117LDORegulator()


@pytest.fixture
def ldo_spec() -> CircuitSpec:
    return CircuitSpec(
        name="ams1117_ldo_5v_3v3",
        topology="ldo_regulator",
        input_voltage=5.0,
        output_voltage=3.3,
        output_current=1.0,
        description="AMS1117 5V to 3.3V 1A LDO regulator",
    )


@pytest.fixture
def golden_data(golden_dir: Path) -> dict[str, object]:
    golden_path = golden_dir / "ams1117_ldo_5v_3v3_1a.json"
    with open(golden_path) as f:
        return json.load(f)


class TestValidateSpec:
    def test_valid_spec(self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec) -> None:
        errors = generator.validate_spec(ldo_spec)
        assert errors == ()

    def test_rejects_wrong_output_voltage(self, generator: AMS1117LDORegulator) -> None:
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=5.0, output_voltage=5.0, output_current=1.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) == 1
        assert "3.3V" in errors[0]

    def test_rejects_input_too_low(self, generator: AMS1117LDORegulator) -> None:
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=3.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert any("4.5V" in e for e in errors)

    def test_rejects_input_too_high(self, generator: AMS1117LDORegulator) -> None:
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=20.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert any("15" in e for e in errors)

    def test_rejects_overcurrent(self, generator: AMS1117LDORegulator) -> None:
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=5.0, output_voltage=3.3, output_current=2.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert any("1.0A" in e for e in errors)

    def test_thermal_warning_high_dissipation(self, generator: AMS1117LDORegulator) -> None:
        """12V input with 1A output = (12-3.3)*1 = 8.7W — thermal warning in notes."""
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=12.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        # Should NOT be a validation error
        errors = generator.validate_spec(spec)
        assert not any("dissipation" in e.lower() for e in errors)
        # But should appear as a warning in design notes
        result = generator.generate(spec)
        assert any("dissipation" in note.lower() for note in result.design_notes)

    def test_rejects_zero_current(self, generator: AMS1117LDORegulator) -> None:
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=5.0, output_voltage=3.3, output_current=0.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert any("positive" in e for e in errors)


class TestGenerate:
    def test_raises_on_invalid_spec(self, generator: AMS1117LDORegulator) -> None:
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=3.0, output_voltage=5.0, output_current=1.0,
            description="test",
        )
        with pytest.raises(ValueError, match="Invalid spec"):
            generator.generate(spec)

    def test_returns_design_result(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec
    ) -> None:
        result = generator.generate(ldo_spec)
        assert result.spec == ldo_spec

    def test_topology(self, generator: AMS1117LDORegulator) -> None:
        assert generator.topology == "ldo_regulator"

    def test_all_smd_components(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec
    ) -> None:
        """LDO design should be all SMD — no THT components."""
        result = generator.generate(ldo_spec)
        for comp in result.components:
            assert "_THT:" not in comp.footprint, (
                f"{comp.reference} uses THT footprint: {comp.footprint}"
            )


class TestGoldenReference:
    def test_component_count(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(ldo_spec)
        assert len(result.components) == golden_data["expected"]["component_count"]

    def test_component_values(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(ldo_spec)
        expected_components = golden_data["expected"]["components"]
        result_by_ref = {c.reference: c for c in result.components}

        for ref, expected in expected_components.items():
            assert ref in result_by_ref, f"Missing component {ref}"
            actual = result_by_ref[ref]
            assert actual.value == expected["value"]
            assert actual.category.name == expected["category"]

    def test_net_names(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(ldo_spec)
        expected_nets = set(golden_data["expected"]["net_names"])
        actual_nets = {n.name for n in result.nets}
        assert actual_nets == expected_nets

    def test_net_connections(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(ldo_spec)
        expected_connections = golden_data["expected"]["net_connections"]
        result_by_name = {n.name: n for n in result.nets}

        for net_name, expected_conns in expected_connections.items():
            assert net_name in result_by_name
            actual = result_by_name[net_name]
            actual_conns = [list(c) for c in actual.connections]
            assert actual_conns == expected_conns

    def test_placement_constraints_count(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(ldo_spec)
        assert len(result.placement_constraints) == golden_data["expected"][
            "placement_constraints_count"
        ]

    def test_design_notes_present(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(ldo_spec)
        assert len(result.design_notes) >= golden_data["expected"]["design_notes_min_count"]

    def test_power_dissipation_in_notes(
        self, generator: AMS1117LDORegulator, ldo_spec: CircuitSpec,
    ) -> None:
        result = generator.generate(ldo_spec)
        assert any("dissipation" in note.lower() for note in result.design_notes)
