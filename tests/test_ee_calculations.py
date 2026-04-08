"""Tests for EE calculations.

Validates component value calculations against known WEBENCH outputs
and datasheet reference designs.
"""

from __future__ import annotations

from etchant.core.ee_calculations import (
    calculate_buck_passives,
    calculate_ldo_passives,
    trace_width_for_current,
)


class TestBuckPassives:
    def test_12v_to_5v_2a(self) -> None:
        """Compare against WEBENCH TPS563200 at 12V->5V 2A.
        WEBENCH says: L=3.3uH, Cout=22uF x2, Cin=10uF x2.
        """
        result = calculate_buck_passives(
            vin=12.0, vout=5.0, iout=2.0, fsw_hz=800_000,
        )
        # Inductor should be in the right ballpark (2-6 uH range)
        assert 1.0 <= result.inductor_uh <= 10.0
        # Duty cycle should be ~0.42
        assert 0.3 < result.duty_cycle < 0.5
        # Output cap should be reasonable
        assert result.output_cap_uf >= 10.0

    def test_12v_to_3v3_1a(self) -> None:
        result = calculate_buck_passives(
            vin=12.0, vout=3.3, iout=1.0, fsw_hz=500_000,
        )
        assert 2.0 <= result.inductor_uh <= 33.0
        assert result.duty_cycle < 0.5

    def test_24v_to_5v_2a(self) -> None:
        """Higher Vin means higher inductor value needed."""
        result = calculate_buck_passives(
            vin=24.0, vout=5.0, iout=2.0, fsw_hz=500_000,
        )
        assert result.inductor_uh > 0
        assert result.duty_cycle < 0.3  # Low duty at high step-down

    def test_feedback_divider(self) -> None:
        """Adjustable output with Vref=0.8V targeting 3.3V."""
        result = calculate_buck_passives(
            vin=12.0, vout=3.3, iout=1.0,
            vref=0.8, rfbb_kohm=10.0,
        )
        assert result.feedback_top_kohm is not None
        assert result.feedback_bottom_kohm == 10.0
        # Rtop should be ~31.25k for 3.3V with 0.8V ref
        # (3.3/0.8 - 1) * 10 = 31.25 -> nearest E24 = 30k or 33k
        assert 27.0 <= result.feedback_top_kohm <= 36.0

    def test_no_feedback_for_fixed_output(self) -> None:
        result = calculate_buck_passives(
            vin=12.0, vout=5.0, iout=2.0,
        )
        assert result.feedback_top_kohm is None
        assert result.feedback_bottom_kohm is None

    def test_ripple_current_reasonable(self) -> None:
        result = calculate_buck_passives(
            vin=12.0, vout=5.0, iout=2.0,
        )
        # Default 30% ripple ratio
        assert 0.4 <= result.ripple_current_a <= 0.8

    def test_standard_value_rounding(self) -> None:
        """Inductor should be a standard value, not arbitrary."""
        result = calculate_buck_passives(
            vin=12.0, vout=5.0, iout=2.0, fsw_hz=500_000,
        )
        standard_values = [
            0.1, 0.15, 0.22, 0.33, 0.47, 0.68,
            1.0, 1.5, 2.2, 3.3, 4.7, 6.8,
            10, 15, 22, 33, 47, 68, 100,
        ]
        assert result.inductor_uh in standard_values


class TestLDOPassives:
    def test_5v_to_3v3(self) -> None:
        result = calculate_ldo_passives(vin=5.0, vout=3.3, iout=0.5)
        assert result.power_dissipation_w > 0
        assert result.efficiency > 0.5
        assert result.input_cap_uf >= 1.0
        assert result.output_cap_uf >= 10.0

    def test_power_dissipation(self) -> None:
        result = calculate_ldo_passives(vin=12.0, vout=3.3, iout=1.0)
        expected = (12.0 - 3.3) * 1.0
        assert abs(result.power_dissipation_w - expected) < 0.01

    def test_efficiency(self) -> None:
        result = calculate_ldo_passives(vin=5.0, vout=3.3, iout=1.0)
        assert abs(result.efficiency - 3.3 / 5.0) < 0.01

    def test_higher_current_needs_more_cap(self) -> None:
        low = calculate_ldo_passives(vin=5.0, vout=3.3, iout=0.3)
        high = calculate_ldo_passives(vin=5.0, vout=3.3, iout=1.5)
        assert high.output_cap_uf >= low.output_cap_uf


class TestTraceWidth:
    def test_1a_external(self) -> None:
        width = trace_width_for_current(1.0)
        # Should be roughly 0.2-0.5mm for 1A on 1oz copper
        assert 0.1 < width < 1.0

    def test_higher_current_wider(self) -> None:
        w1 = trace_width_for_current(1.0)
        w5 = trace_width_for_current(5.0)
        assert w5 > w1

    def test_internal_wider_than_external(self) -> None:
        ext = trace_width_for_current(2.0, layer="external")
        int_ = trace_width_for_current(2.0, layer="internal")
        assert int_ > ext  # Internal has worse cooling

    def test_2oz_copper_narrower(self) -> None:
        oz1 = trace_width_for_current(3.0, copper_oz=1.0)
        oz2 = trace_width_for_current(3.0, copper_oz=2.0)
        assert oz2 < oz1  # Thicker copper needs less width
