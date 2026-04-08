"""Electrical engineering calculations for power supply design.

Implements the fundamental formulas for sizing passive components
in switching and linear regulators. These are the physics — they work
for any IC, not just the ones we've hardcoded.

References:
- TI SLVA477: Understanding Buck Power Stages
- TI SNVA057: Inductor and Capacitor Selection
- IPC-2221: Trace Width Calculations
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BuckPassives:
    """Calculated passive component values for a buck converter."""

    inductor_uh: float
    output_cap_uf: float
    input_cap_uf: float
    feedback_top_kohm: float | None  # None for fixed-output ICs
    feedback_bottom_kohm: float | None
    duty_cycle: float
    ripple_current_a: float


@dataclass(frozen=True)
class LDOPassives:
    """Calculated passive component values for an LDO regulator."""

    input_cap_uf: float
    output_cap_uf: float
    power_dissipation_w: float
    efficiency: float


def calculate_buck_passives(
    vin: float,
    vout: float,
    iout: float,
    fsw_hz: float = 500_000,
    ripple_ratio: float = 0.3,
    vout_ripple_mv: float = 30.0,
    vref: float | None = None,
    rfbb_kohm: float = 10.0,
) -> BuckPassives:
    """Calculate passive component values for a buck converter.

    Args:
        vin: Input voltage (V)
        vout: Output voltage (V)
        iout: Output current (A)
        fsw_hz: Switching frequency (Hz), default 500kHz
        ripple_ratio: Inductor ripple as fraction of Iout (0.2-0.4 typical)
        vout_ripple_mv: Target output voltage ripple (mV)
        vref: Reference voltage for feedback divider (None = fixed output IC)
        rfbb_kohm: Bottom feedback resistor value (kOhm)
    """
    # Duty cycle
    duty = vout / vin

    # Inductor ripple current
    delta_il = ripple_ratio * iout

    # Inductor value: L = (Vin - Vout) * D / (fsw * delta_IL)
    inductor_h = (vin - vout) * duty / (fsw_hz * delta_il)
    inductor_uh = inductor_h * 1e6

    # Round to nearest standard value
    inductor_uh = _nearest_standard_inductor(inductor_uh)

    # Output capacitor: sized for ripple voltage
    # Cout = delta_IL / (8 * fsw * Vripple)
    if vout_ripple_mv > 0:
        cout_f = delta_il / (8 * fsw_hz * (vout_ripple_mv / 1000))
        cout_uf = cout_f * 1e6
    else:
        cout_uf = 22.0  # Default

    # Minimum 22uF for transient response (ripple formula alone gives too low)
    cout_uf = max(cout_uf, 22.0)
    cout_uf = _nearest_standard_cap(cout_uf)

    # Input capacitor: sized for RMS ripple current
    # Cin should handle Irms = Iout * sqrt(D * (1-D))
    # Rule of thumb: Cin >= Cout, minimum 10uF
    cin_uf = max(cout_uf, 10.0)
    cin_uf = _nearest_standard_cap(cin_uf)

    # Feedback resistor divider (for adjustable output ICs)
    rfbt_kohm = None
    rfbb_result = None
    if vref is not None and vref > 0:
        # Vout = Vref * (1 + Rtop/Rbot)
        # Rtop = Rbot * (Vout/Vref - 1)
        rfbt_kohm = rfbb_kohm * (vout / vref - 1)
        rfbt_kohm = _nearest_standard_resistor(rfbt_kohm)
        rfbb_result = rfbb_kohm

    return BuckPassives(
        inductor_uh=inductor_uh,
        output_cap_uf=cout_uf,
        input_cap_uf=cin_uf,
        feedback_top_kohm=rfbt_kohm,
        feedback_bottom_kohm=rfbb_result,
        duty_cycle=duty,
        ripple_current_a=delta_il,
    )


def calculate_ldo_passives(
    vin: float,
    vout: float,
    iout: float,
) -> LDOPassives:
    """Calculate passive values and thermal parameters for an LDO.

    LDOs are simple — just input and output caps. The key calculation
    is power dissipation to ensure thermal safety.
    """
    power_dissipation = (vin - vout) * iout
    efficiency = vout / vin if vin > 0 else 0

    # Input cap: 1-10uF ceramic, higher for noisy input
    input_cap = 10.0

    # Output cap: 10-22uF, critical for LDO stability
    # Higher current needs more capacitance
    if iout <= 0.5:
        output_cap = 10.0
    elif iout <= 1.0:
        output_cap = 22.0
    else:
        output_cap = 47.0

    return LDOPassives(
        input_cap_uf=input_cap,
        output_cap_uf=output_cap,
        power_dissipation_w=power_dissipation,
        efficiency=efficiency,
    )


def trace_width_for_current(
    current_a: float,
    copper_oz: float = 1.0,
    temp_rise_c: float = 10.0,
    layer: str = "external",
) -> float:
    """Calculate minimum trace width in mm for a given current.

    Uses IPC-2221 formula:
    Area (mils^2) = (I / (k * dT^b))^(1/c)
    where k=0.048, b=0.44, c=0.725 for external layers
    """
    k = 0.024 if layer == "internal" else 0.048

    b = 0.44
    c = 0.725

    # Cross-section area in mils^2
    area_mils2 = (current_a / (k * temp_rise_c**b)) ** (1 / c)

    # Convert to width: area = width * thickness
    # 1 oz copper = 1.378 mils thick
    thickness_mils = copper_oz * 1.378
    width_mils = area_mils2 / thickness_mils

    # Convert mils to mm
    width_mm = width_mils * 0.0254

    return round(width_mm, 3)


def _nearest_standard_inductor(value_uh: float) -> float:
    """Round to nearest standard inductor value (E6 series)."""
    standards = [
        0.1, 0.15, 0.22, 0.33, 0.47, 0.68,
        1.0, 1.5, 2.2, 3.3, 4.7, 6.8,
        10, 15, 22, 33, 47, 68,
        100, 150, 220, 330, 470, 680,
    ]
    return min(standards, key=lambda s: abs(s - value_uh))


def _nearest_standard_cap(value_uf: float) -> float:
    """Round to nearest standard capacitor value."""
    standards = [
        0.1, 0.22, 0.47, 1.0, 2.2, 4.7,
        10, 22, 47, 100, 220, 470, 1000,
    ]
    return min(standards, key=lambda s: abs(s - value_uf))


def _nearest_standard_resistor(value_kohm: float) -> float:
    """Round to nearest E24 standard resistor value (kOhm)."""
    e24 = [
        1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
    ]
    # Find the right decade
    if value_kohm <= 0:
        return 1.0

    decade = 10 ** math.floor(math.log10(value_kohm))
    normalized = value_kohm / decade

    nearest = min(e24, key=lambda v: abs(v - normalized))
    return round(nearest * decade, 3)
