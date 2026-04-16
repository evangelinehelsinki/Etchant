"""Tests for the generative LDO regulator."""

from __future__ import annotations

from unittest.mock import patch

from etchant.circuits.generative_ldo import GenerativeLDORegulator
from etchant.core.models import CircuitSpec


class TestValidateSpec:
    def test_valid_5v_to_3v3(self) -> None:
        gen = GenerativeLDORegulator()
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=5.0, output_voltage=3.3, output_current=0.5,
            description="test",
        )
        assert gen.validate_spec(spec) == ()

    def test_rejects_step_up(self) -> None:
        gen = GenerativeLDORegulator()
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=3.0, output_voltage=5.0, output_current=1.0,
            description="test",
        )
        assert len(gen.validate_spec(spec)) > 0

    def test_warns_high_vin(self) -> None:
        gen = GenerativeLDORegulator()
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=24.0, output_voltage=3.3, output_current=0.5,
            description="test",
        )
        assert len(gen.validate_spec(spec)) > 0


class TestGenerate:
    @patch("etchant.circuits.generative_ldo.GenerativeLDORegulator._query_webench")
    def test_5v_to_3v3_fixed(self, mock_wb: object) -> None:
        mock_wb.return_value = None  # type: ignore[union-attr]
        gen = GenerativeLDORegulator()
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=5.0, output_voltage=3.3, output_current=0.5,
            description="test",
        )
        result = gen.generate(spec)
        # IC, Cin, Cout + J1 (VIN input), J2 (VOUT output)
        assert len(result.components) == 5
        assert any("AMS1117-3.3" in c.value for c in result.components)

    @patch("etchant.circuits.generative_ldo.GenerativeLDORegulator._query_webench")
    def test_5v_to_2v8_adjustable(self, mock_wb: object) -> None:
        """Non-standard voltage needs adjustable LDO with feedback."""
        mock_wb.return_value = None  # type: ignore[union-attr]
        gen = GenerativeLDORegulator()
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=5.0, output_voltage=2.8, output_current=0.5,
            description="test",
        )
        result = gen.generate(spec)
        assert any("AMS1117-ADJ" in c.value for c in result.components)
        refs = {c.reference for c in result.components}
        assert "R1" in refs  # Feedback divider
        assert "R2" in refs

    @patch("etchant.circuits.generative_ldo.GenerativeLDORegulator._query_webench")
    def test_arbitrary_voltages(self, mock_wb: object) -> None:
        mock_wb.return_value = None  # type: ignore[union-attr]
        gen = GenerativeLDORegulator()
        specs = [
            (5.0, 1.8, 0.5),
            (5.0, 2.5, 1.0),
            (12.0, 5.0, 0.3),
            (3.6, 1.2, 0.2),
        ]
        for vin, vout, iout in specs:
            spec = CircuitSpec(
                name="test", topology="ldo_regulator",
                input_voltage=vin, output_voltage=vout, output_current=iout,
                description="test",
            )
            result = gen.generate(spec)
            assert len(result.components) >= 3, f"Failed for {vin}V->{vout}V"

    @patch("etchant.circuits.generative_ldo.GenerativeLDORegulator._query_webench")
    def test_thermal_warning(self, mock_wb: object) -> None:
        mock_wb.return_value = None  # type: ignore[union-attr]
        gen = GenerativeLDORegulator()
        spec = CircuitSpec(
            name="test", topology="ldo_regulator",
            input_voltage=12.0, output_voltage=5.0, output_current=0.3,
            description="test",
        )
        result = gen.generate(spec)
        assert any("WARNING" in n for n in result.design_notes)
