"""Tests for the circuit generator registry."""

from __future__ import annotations

import pytest

from etchant.circuits import get_generator, list_topologies, register_generator
from etchant.circuits.buck_converter import LM2596BuckConverter


class TestRegistry:
    def test_buck_converter_registered(self) -> None:
        gen = get_generator("buck_converter")
        assert isinstance(gen, LM2596BuckConverter)

    def test_list_topologies(self) -> None:
        topologies = list_topologies()
        assert "buck_converter" in topologies

    def test_unknown_topology_raises(self) -> None:
        with pytest.raises(KeyError, match="boost_converter"):
            get_generator("boost_converter")

    def test_register_custom_generator(self) -> None:
        class FakeGenerator:
            @property
            def topology(self) -> str:
                return "fake_topology"

            def generate(self, spec):  # type: ignore[no-untyped-def]
                pass

            def validate_spec(self, spec):  # type: ignore[no-untyped-def]
                return ()

        register_generator("fake_topology", FakeGenerator)
        gen = get_generator("fake_topology")
        assert isinstance(gen, FakeGenerator)
