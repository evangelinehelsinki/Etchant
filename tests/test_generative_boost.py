"""Tests for the generative boost converter."""

from __future__ import annotations

from unittest.mock import patch

from etchant.circuits.generative_boost import GenerativeBoostConverter
from etchant.core.models import CircuitSpec


class TestValidateSpec:
    def test_valid_3v7_to_5v(self) -> None:
        gen = GenerativeBoostConverter()
        spec = CircuitSpec(
            name="test", topology="boost_converter",
            input_voltage=3.7, output_voltage=5.0, output_current=1.0,
            description="test",
        )
        assert gen.validate_spec(spec) == ()

    def test_rejects_step_down(self) -> None:
        gen = GenerativeBoostConverter()
        spec = CircuitSpec(
            name="test", topology="boost_converter",
            input_voltage=12.0, output_voltage=5.0, output_current=1.0,
            description="test",
        )
        assert len(gen.validate_spec(spec)) > 0


class TestGenerate:
    @patch("etchant.circuits.generative_boost.GenerativeBoostConverter._select_ic")
    def test_3v7_to_5v(self, mock_ic: object) -> None:
        mock_ic.return_value = {  # type: ignore[union-attr]
            "base_pn": "TPS61230A",
            "part_number": "TPS61230A",
            "source": "test",
            "fsw_hz": 500_000,
            "vref": 0.8,
        }
        gen = GenerativeBoostConverter()
        spec = CircuitSpec(
            name="test", topology="boost_converter",
            input_voltage=3.7, output_voltage=5.0, output_current=1.0,
            description="test",
        )
        result = gen.generate(spec)
        # IC, L, Cin, Cout, D, R1, R2 + J1 (VIN), J2 (VOUT)
        assert len(result.components) == 9
        assert any(c.reference == "D1" for c in result.components)  # Boost has diode
        assert any(c.reference == "L1" for c in result.components)

    @patch("etchant.circuits.generative_boost.GenerativeBoostConverter._select_ic")
    def test_5v_to_12v(self, mock_ic: object) -> None:
        mock_ic.return_value = {  # type: ignore[union-attr]
            "base_pn": "TPS55340",
            "source": "test",
            "part_number": "TPS55340",
            "fsw_hz": 500_000,
            "vref": 0.8,
        }
        gen = GenerativeBoostConverter()
        spec = CircuitSpec(
            name="test", topology="boost_converter",
            input_voltage=5.0, output_voltage=12.0, output_current=0.5,
            description="test",
        )
        result = gen.generate(spec)
        # IC, L, Cin, Cout, D, R1, R2 + J1 (VIN), J2 (VOUT)
        assert len(result.components) == 9

    @patch("etchant.circuits.generative_boost.GenerativeBoostConverter._select_ic")
    def test_all_smd(self, mock_ic: object) -> None:
        mock_ic.return_value = {  # type: ignore[union-attr]
            "base_pn": "TPS61230A",
            "source": "test",
            "part_number": "TPS61230A",
            "fsw_hz": 500_000,
            "vref": 0.8,
        }
        gen = GenerativeBoostConverter()
        spec = CircuitSpec(
            name="test", topology="boost_converter",
            input_voltage=3.7, output_voltage=5.0, output_current=1.0,
            description="test",
        )
        result = gen.generate(spec)
        for comp in result.components:
            assert "_THT:" not in comp.footprint

    @patch("etchant.circuits.generative_boost.GenerativeBoostConverter._select_ic")
    def test_has_boost_specific_nets(self, mock_ic: object) -> None:
        """Boost should have SW net connecting inductor, IC, and diode."""
        mock_ic.return_value = {  # type: ignore[union-attr]
            "base_pn": "TPS61230A",
            "source": "test",
            "part_number": "TPS61230A",
            "fsw_hz": 500_000,
            "vref": 0.8,
        }
        gen = GenerativeBoostConverter()
        spec = CircuitSpec(
            name="test", topology="boost_converter",
            input_voltage=3.7, output_voltage=5.0, output_current=1.0,
            description="test",
        )
        result = gen.generate(spec)
        net_names = {n.name for n in result.nets}
        assert "SW" in net_names
        assert "FB" in net_names
