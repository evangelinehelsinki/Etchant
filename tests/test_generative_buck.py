"""Tests for the generative buck converter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from etchant.circuits.generative_buck import GenerativeBuckConverter
from etchant.core.models import CircuitSpec


@pytest.fixture
def generator() -> GenerativeBuckConverter:
    return GenerativeBuckConverter()


@pytest.fixture
def webench_generator() -> GenerativeBuckConverter:
    webench_dir = Path("/home/evangeline/Projects/etchant-data/data/webench")
    if webench_dir.exists():
        return GenerativeBuckConverter(webench_data_dir=webench_dir)
    return GenerativeBuckConverter()


class TestValidateSpec:
    def test_valid_12v_to_5v(self, generator: GenerativeBuckConverter) -> None:
        spec = CircuitSpec(
            name="test", topology="buck_converter",
            input_voltage=12.0, output_voltage=5.0, output_current=2.0,
            description="test",
        )
        assert generator.validate_spec(spec) == ()

    def test_valid_24v_to_3v3(self, generator: GenerativeBuckConverter) -> None:
        spec = CircuitSpec(
            name="test", topology="buck_converter",
            input_voltage=24.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        assert generator.validate_spec(spec) == ()

    def test_rejects_step_up(self, generator: GenerativeBuckConverter) -> None:
        spec = CircuitSpec(
            name="test", topology="buck_converter",
            input_voltage=5.0, output_voltage=12.0, output_current=1.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) > 0

    def test_rejects_zero_current(self, generator: GenerativeBuckConverter) -> None:
        spec = CircuitSpec(
            name="test", topology="buck_converter",
            input_voltage=12.0, output_voltage=5.0, output_current=0.0,
            description="test",
        )
        errors = generator.validate_spec(spec)
        assert len(errors) > 0


class TestGenerateOffline:
    """Test generation without WEBENCH API (uses generic fallback)."""

    @patch("etchant.circuits.generative_buck.GenerativeBuckConverter._query_webench_live")
    def test_12v_to_5v_2a(
        self, mock_webench: object, generator: GenerativeBuckConverter
    ) -> None:
        mock_webench.return_value = None  # type: ignore[union-attr]
        spec = CircuitSpec(
            name="gen_buck_12v_5v",
            topology="buck_converter",
            input_voltage=12.0, output_voltage=5.0, output_current=2.0,
            description="test",
        )
        result = generator.generate(spec)
        assert len(result.components) >= 4  # IC, Cin, Cout, L (+ maybe R1, R2)
        assert any(c.reference == "U1" for c in result.components)
        assert any(c.reference == "L1" for c in result.components)

    @patch("etchant.circuits.generative_buck.GenerativeBuckConverter._query_webench_live")
    def test_24v_to_3v3_1a(
        self, mock_webench: object, generator: GenerativeBuckConverter
    ) -> None:
        mock_webench.return_value = None  # type: ignore[union-attr]
        spec = CircuitSpec(
            name="gen_buck_24v_3v3",
            topology="buck_converter",
            input_voltage=24.0, output_voltage=3.3, output_current=1.0,
            description="test",
        )
        result = generator.generate(spec)
        assert len(result.components) >= 4

    @patch("etchant.circuits.generative_buck.GenerativeBuckConverter._query_webench_live")
    def test_has_feedback_resistors(
        self, mock_webench: object, generator: GenerativeBuckConverter
    ) -> None:
        """Generative designs use adjustable ICs with feedback dividers."""
        mock_webench.return_value = None  # type: ignore[union-attr]
        spec = CircuitSpec(
            name="test", topology="buck_converter",
            input_voltage=12.0, output_voltage=3.3, output_current=2.0,
            description="test",
        )
        result = generator.generate(spec)
        refs = {c.reference for c in result.components}
        assert "R1" in refs  # Feedback top
        assert "R2" in refs  # Feedback bottom

    @patch("etchant.circuits.generative_buck.GenerativeBuckConverter._query_webench_live")
    def test_all_smd(
        self, mock_webench: object, generator: GenerativeBuckConverter
    ) -> None:
        mock_webench.return_value = None  # type: ignore[union-attr]
        spec = CircuitSpec(
            name="test", topology="buck_converter",
            input_voltage=12.0, output_voltage=5.0, output_current=2.0,
            description="test",
        )
        result = generator.generate(spec)
        for comp in result.components:
            assert "_THT:" not in comp.footprint, (
                f"{comp.reference} uses THT: {comp.footprint}"
            )

    @patch("etchant.circuits.generative_buck.GenerativeBuckConverter._query_webench_live")
    def test_design_notes_mention_source(
        self, mock_webench: object, generator: GenerativeBuckConverter
    ) -> None:
        mock_webench.return_value = None  # type: ignore[union-attr]
        spec = CircuitSpec(
            name="test", topology="buck_converter",
            input_voltage=12.0, output_voltage=5.0, output_current=2.0,
            description="test",
        )
        result = generator.generate(spec)
        assert any("generic_fallback" in n for n in result.design_notes)

    @patch("etchant.circuits.generative_buck.GenerativeBuckConverter._query_webench_live")
    def test_arbitrary_voltages_work(
        self, mock_webench: object, generator: GenerativeBuckConverter
    ) -> None:
        """The whole point — this should work for ANY step-down spec."""
        mock_webench.return_value = None  # type: ignore[union-attr]
        test_specs = [
            (48, 12, 1.0),
            (5.0, 1.8, 0.5),
            (9.0, 3.3, 3.0),
            (36, 5, 2.0),
            (15, 1.2, 4.0),
        ]
        for vin, vout, iout in test_specs:
            spec = CircuitSpec(
                name=f"test_{vin}_{vout}",
                topology="buck_converter",
                input_voltage=vin, output_voltage=vout, output_current=iout,
                description="test",
            )
            result = generator.generate(spec)
            assert len(result.components) >= 4, f"Failed for {vin}V->{vout}V@{iout}A"
