"""Tests for the LM2596 buck converter generator with golden reference comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.core.models import CircuitSpec


@pytest.fixture
def generator() -> LM2596BuckConverter:
    return LM2596BuckConverter()


@pytest.fixture
def golden_data(golden_dir: Path) -> dict[str, object]:
    golden_path = golden_dir / "lm2596_buck_12v_5v_2a.json"
    with open(golden_path) as f:
        return json.load(f)


class TestValidateSpec:
    def test_valid_spec(self, generator: LM2596BuckConverter, lm2596_spec: CircuitSpec) -> None:
        errors = generator.validate_spec(lm2596_spec)
        assert errors == ()

    def test_rejects_wrong_output_voltage(self, generator: LM2596BuckConverter) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=12.0,
            output_voltage=3.3,
            output_current=2.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) == 1
        assert "5V" in errors[0]

    def test_rejects_input_too_low(self, generator: LM2596BuckConverter) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=3.0,
            output_voltage=5.0,
            output_current=2.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) == 1
        assert "7" in errors[0]

    def test_rejects_input_too_high(self, generator: LM2596BuckConverter) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=45.0,
            output_voltage=5.0,
            output_current=2.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) == 1
        assert "40" in errors[0]

    def test_rejects_overcurrent(self, generator: LM2596BuckConverter) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=3.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) == 1
        assert "2.0A" in errors[0]

    def test_rejects_zero_current(self, generator: LM2596BuckConverter) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=0.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) == 1
        assert "positive" in errors[0]

    def test_multiple_errors(self, generator: LM2596BuckConverter) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=3.0,
            output_voltage=3.3,
            output_current=5.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) == 3


class TestGenerate:
    def test_raises_on_invalid_spec(self, generator: LM2596BuckConverter) -> None:
        spec = CircuitSpec(
            name="test",
            topology="buck_converter",
            input_voltage=3.0,
            output_voltage=3.3,
            output_current=2.0,
            description="test",
        )
        with pytest.raises(ValueError, match="Invalid spec"):
            generator.generate(spec)

    def test_returns_design_result(
        self, generator: LM2596BuckConverter, lm2596_spec: CircuitSpec
    ) -> None:
        result = generator.generate(lm2596_spec)
        assert result.spec == lm2596_spec

    def test_topology(self, generator: LM2596BuckConverter) -> None:
        assert generator.topology == "buck_converter"


class TestGoldenReference:
    def test_component_count(
        self,
        generator: LM2596BuckConverter,
        lm2596_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(lm2596_spec)
        expected = golden_data["expected"]
        assert len(result.components) == expected["component_count"]

    def test_component_values(
        self,
        generator: LM2596BuckConverter,
        lm2596_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(lm2596_spec)
        expected_components = golden_data["expected"]["components"]
        result_by_ref = {c.reference: c for c in result.components}

        for ref, expected in expected_components.items():
            assert ref in result_by_ref, f"Missing component {ref}"
            actual = result_by_ref[ref]
            assert actual.value == expected["value"], (
                f"{ref}: expected value '{expected['value']}', got '{actual.value}'"
            )
            assert actual.category.name == expected["category"], (
                f"{ref}: expected category '{expected['category']}', got '{actual.category.name}'"
            )

    def test_net_names(
        self,
        generator: LM2596BuckConverter,
        lm2596_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(lm2596_spec)
        expected_nets = set(golden_data["expected"]["net_names"])
        actual_nets = {n.name for n in result.nets}
        assert actual_nets == expected_nets

    def test_net_count(
        self,
        generator: LM2596BuckConverter,
        lm2596_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(lm2596_spec)
        assert len(result.nets) == golden_data["expected"]["net_count"]

    def test_placement_constraints_count(
        self,
        generator: LM2596BuckConverter,
        lm2596_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(lm2596_spec)
        assert len(result.placement_constraints) == golden_data["expected"][
            "placement_constraints_count"
        ]

    def test_net_connections(
        self,
        generator: LM2596BuckConverter,
        lm2596_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(lm2596_spec)
        expected_connections = golden_data["expected"]["net_connections"]
        result_by_name = {n.name: n for n in result.nets}

        for net_name, expected_conns in expected_connections.items():
            assert net_name in result_by_name, f"Missing net {net_name}"
            actual = result_by_name[net_name]
            actual_conns = [list(c) for c in actual.connections]
            assert actual_conns == expected_conns, (
                f"Net {net_name}: expected {expected_conns}, got {actual_conns}"
            )

    def test_design_notes_present(
        self,
        generator: LM2596BuckConverter,
        lm2596_spec: CircuitSpec,
        golden_data: dict[str, object],
    ) -> None:
        result = generator.generate(lm2596_spec)
        min_count = golden_data["expected"]["design_notes_min_count"]
        assert len(result.design_notes) >= min_count
