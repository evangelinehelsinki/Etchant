"""Tests for design serialization and deserialization."""

from __future__ import annotations

from pathlib import Path

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.circuits.ldo_regulator import AMS1117LDORegulator
from etchant.core.models import CircuitSpec
from etchant.core.serialization import (
    design_to_dict,
    dict_to_design,
    load_design,
    save_design,
)


class TestDesignToDict:
    def test_buck_roundtrip(self, lm2596_spec: CircuitSpec) -> None:
        original = LM2596BuckConverter().generate(lm2596_spec)
        data = design_to_dict(original)
        restored = dict_to_design(data)

        assert restored.spec.name == original.spec.name
        assert restored.spec.topology == original.spec.topology
        assert len(restored.components) == len(original.components)
        assert len(restored.nets) == len(original.nets)
        assert len(restored.placement_constraints) == len(original.placement_constraints)
        assert len(restored.design_notes) == len(original.design_notes)

    def test_ldo_roundtrip(self) -> None:
        spec = CircuitSpec(
            name="ldo_test",
            topology="ldo_regulator",
            input_voltage=5.0,
            output_voltage=3.3,
            output_current=0.5,
            description="test",
        )
        original = AMS1117LDORegulator().generate(spec)
        data = design_to_dict(original)
        restored = dict_to_design(data)

        assert restored.spec == original.spec
        assert len(restored.components) == len(original.components)

    def test_component_values_preserved(self, lm2596_spec: CircuitSpec) -> None:
        original = LM2596BuckConverter().generate(lm2596_spec)
        data = design_to_dict(original)
        restored = dict_to_design(data)

        for orig, rest in zip(original.components, restored.components, strict=True):
            assert orig.reference == rest.reference
            assert orig.value == rest.value
            assert orig.category == rest.category
            assert orig.footprint == rest.footprint

    def test_net_connections_preserved(self, lm2596_spec: CircuitSpec) -> None:
        original = LM2596BuckConverter().generate(lm2596_spec)
        data = design_to_dict(original)
        restored = dict_to_design(data)

        for orig, rest in zip(original.nets, restored.nets, strict=True):
            assert orig.name == rest.name
            assert orig.connections == rest.connections

    def test_properties_preserved(self, lm2596_spec: CircuitSpec) -> None:
        original = LM2596BuckConverter().generate(lm2596_spec)
        data = design_to_dict(original)
        restored = dict_to_design(data)

        orig_u1 = next(c for c in original.components if c.reference == "U1")
        rest_u1 = next(c for c in restored.components if c.reference == "U1")
        assert dict(orig_u1.properties) == dict(rest_u1.properties)


class TestSaveLoad:
    def test_save_and_load(self, tmp_path: Path, lm2596_spec: CircuitSpec) -> None:
        original = LM2596BuckConverter().generate(lm2596_spec)
        path = tmp_path / "test_design.json"

        save_design(original, path)
        assert path.exists()

        loaded = load_design(path)
        assert loaded.spec.name == original.spec.name
        assert len(loaded.components) == len(original.components)

    def test_creates_parent_dirs(self, tmp_path: Path, lm2596_spec: CircuitSpec) -> None:
        original = LM2596BuckConverter().generate(lm2596_spec)
        path = tmp_path / "deep" / "nested" / "design.json"

        save_design(original, path)
        assert path.exists()

    def test_load_file_is_valid_json(self, tmp_path: Path, lm2596_spec: CircuitSpec) -> None:
        import json

        original = LM2596BuckConverter().generate(lm2596_spec)
        path = tmp_path / "design.json"
        save_design(original, path)

        with open(path) as f:
            data = json.load(f)
        assert "spec" in data
        assert "components" in data
        assert "nets" in data
