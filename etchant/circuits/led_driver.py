"""Constant-current LED driver circuit generator.

A simple constant-current LED driver using a dedicated driver IC
or a transistor-based current source. Different from power supplies:
- Output is constant current, not constant voltage
- Load is an LED (forward voltage drop)
- Sense resistor sets the current
- PWM dimming support

Week 1: Simple resistor-limited LED circuit and AP3019 boost LED driver.
"""

from __future__ import annotations

from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
    PlacementConstraint,
)


class LEDDriverCircuit:
    """LED driver circuit generator."""

    @property
    def topology(self) -> str:
        return "led_driver"

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.input_voltage <= 0:
            errors.append(f"Input voltage must be positive, got {spec.input_voltage}V")
        if spec.output_current <= 0:
            errors.append(
                f"LED current must be positive, got {spec.output_current}A"
            )
        if spec.output_current > 1.0:
            errors.append(
                f"LED current {spec.output_current}A exceeds 1A limit"
            )
        if spec.output_voltage <= 0:
            errors.append(
                f"LED forward voltage must be positive, got {spec.output_voltage}V"
            )
        return tuple(errors)

    def generate(self, spec: CircuitSpec) -> DesignResult:
        errors = self.validate_spec(spec)
        if errors:
            raise ValueError(f"Invalid spec: {'; '.join(errors)}")

        # Choose topology based on Vin vs Vf
        if spec.input_voltage > spec.output_voltage + 1.0:
            return self._build_resistor_limited(spec)
        return self._build_boost_driver(spec)

    def _build_resistor_limited(self, spec: CircuitSpec) -> DesignResult:
        """Simple resistor-limited LED circuit (Vin > Vf)."""
        # R = (Vin - Vf) / Iled
        v_drop = spec.input_voltage - spec.output_voltage
        r_value = v_drop / spec.output_current
        # Round to nearest E24
        from etchant.core.ee_calculations import _nearest_standard_resistor

        r_kohm = _nearest_standard_resistor(r_value / 1000)
        r_display = (
            f"{r_kohm}k" if r_kohm >= 1
            else f"{int(r_kohm * 1000)}"
        )

        power_w = v_drop * spec.output_current

        components = (
            ComponentSpec(
                reference="R1",
                category=ComponentCategory.RESISTOR,
                value=r_display,
                footprint="Resistor_SMD:R_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description=f"Current limiting resistor ({power_w:.2f}W)",
                properties={"power_rating": "0.125W"},
            ),
            ComponentSpec(
                reference="D1",
                category=ComponentCategory.DIODE,
                value="LED",
                footprint="LED_SMD:LED_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="LED",
                description=f"LED ({spec.output_voltage}V forward)",
            ),
            ComponentSpec(
                reference="J1",
                category=ComponentCategory.CONNECTOR,
                value="Conn_01x02",
                footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
                kicad_library="Connector_Generic",
                kicad_symbol="Conn_01x02",
                description="Power input connector",
            ),
        )

        nets = (
            NetSpec(name="VIN", connections=(("J1", "1"), ("R1", "1"))),
            NetSpec(name="LED_A", connections=(("R1", "2"), ("D1", "A"))),
            NetSpec(name="GND", connections=(("D1", "K"), ("J1", "2"))),
        )

        constraints = (
            PlacementConstraint(
                component_ref="R1", target_ref="D1",
                max_distance_mm=8.0,
                reason="Resistor close to LED for short current path",
            ),
        )

        notes = (
            f"Resistor-limited LED: {spec.input_voltage}V input, "
            f"{spec.output_current * 1000:.0f}mA",
            f"R1 = ({spec.input_voltage}V - {spec.output_voltage}V) / "
            f"{spec.output_current}A = {r_value:.0f}Ohm -> {r_display}",
            f"Power dissipation in R1: {power_w:.2f}W",
        )

        return DesignResult(
            spec=spec, components=components, nets=nets,
            placement_constraints=constraints, design_notes=notes,
        )

    def _build_boost_driver(self, spec: CircuitSpec) -> DesignResult:
        """Boost LED driver for Vf >= Vin (e.g., white LEDs from 3.3V)."""
        # Sense resistor: R = 0.1V / Iled (typical 100mV sense)
        r_sense = 0.1 / spec.output_current

        r_display = f"{int(r_sense * 1000)}m" if r_sense < 1 else f"{r_sense:.1f}"

        components = (
            ComponentSpec(
                reference="U1",
                category=ComponentCategory.IC,
                value="AP3019",
                footprint="Package_TO_SOT_SMD:SOT-23-5",
                kicad_library="Driver_LED",
                kicad_symbol="AP3019",
                description="Boost LED driver IC",
            ),
            ComponentSpec(
                reference="L1",
                category=ComponentCategory.INDUCTOR,
                value="10uH",
                footprint="Inductor_SMD:L_Vishay_IHLP-2525",
                kicad_library="Device",
                kicad_symbol="L",
                description="Boost inductor",
            ),
            ComponentSpec(
                reference="D1",
                category=ComponentCategory.DIODE,
                value="SS34",
                footprint="Diode_SMD:D_SMA",
                kicad_library="Diode",
                kicad_symbol="SS34",
                description="Boost Schottky diode",
            ),
            ComponentSpec(
                reference="C1",
                category=ComponentCategory.CAPACITOR,
                value="10uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="Input capacitor",
            ),
            ComponentSpec(
                reference="R1",
                category=ComponentCategory.RESISTOR,
                value=r_display,
                footprint="Resistor_SMD:R_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description="LED current sense resistor",
            ),
            ComponentSpec(
                reference="LED1",
                category=ComponentCategory.DIODE,
                value="LED",
                footprint="LED_SMD:LED_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="LED",
                description=f"LED ({spec.output_voltage}V forward)",
            ),
        )

        nets = (
            NetSpec(name="VIN", connections=(
                ("C1", "1"), ("U1", "VIN"), ("L1", "1"),
            )),
            NetSpec(name="SW", connections=(("L1", "2"), ("U1", "SW"), ("D1", "A"))),
            NetSpec(name="VLED", connections=(("D1", "K"), ("LED1", "A"))),
            NetSpec(name="LED_SENSE", connections=(
                ("LED1", "K"), ("R1", "1"), ("U1", "FB"),
            )),
            NetSpec(name="GND", connections=(
                ("R1", "2"), ("C1", "2"), ("U1", "GND"),
            )),
        )

        constraints = (
            PlacementConstraint(
                component_ref="C1", target_ref="U1",
                max_distance_mm=8.0,
                reason="Input cap close to driver IC",
            ),
            PlacementConstraint(
                component_ref="L1", target_ref="U1",
                max_distance_mm=8.0,
                reason="Inductor close to SW pin",
            ),
            PlacementConstraint(
                component_ref="R1", target_ref="U1",
                max_distance_mm=10.0,
                reason="Sense resistor near FB pin",
            ),
        )

        notes = (
            f"Boost LED driver: {spec.input_voltage}V -> "
            f"{spec.output_voltage}V LED @ {spec.output_current * 1000:.0f}mA",
            "IC: AP3019 boost LED driver",
            f"Sense resistor: {r_display}Ohm "
            f"(100mV / {spec.output_current}A)",
            "All SMD components for JLCPCB assembly",
        )

        return DesignResult(
            spec=spec, components=components, nets=nets,
            placement_constraints=constraints, design_notes=notes,
        )
