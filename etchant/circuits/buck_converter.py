"""LM2596 buck converter circuit generator.

Reference: TI SNVS124F datasheet, typical application circuit.
Week 1: Only LM2596S-5 (fixed 5V output) is implemented.

Generates a complete DesignResult with components, nets, placement constraints,
and design notes matching the datasheet reference design.
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

_INPUT_VOLTAGE_MIN = 7.0
_INPUT_VOLTAGE_MAX = 40.0
_OUTPUT_VOLTAGE = 5.0
_MAX_CURRENT = 2.0


class LM2596BuckConverter:
    """Hardcoded LM2596-5.0 buck converter generator."""

    @property
    def topology(self) -> str:
        return "buck_converter"

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.output_voltage != _OUTPUT_VOLTAGE:
            errors.append(f"Only 5V output supported, got {spec.output_voltage}V")
        if spec.input_voltage < _INPUT_VOLTAGE_MIN or spec.input_voltage > _INPUT_VOLTAGE_MAX:
            errors.append(
                f"Input voltage must be {_INPUT_VOLTAGE_MIN}-{_INPUT_VOLTAGE_MAX}V, "
                f"got {spec.input_voltage}V"
            )
        if spec.output_current > _MAX_CURRENT:
            errors.append(f"Max output current is {_MAX_CURRENT}A, got {spec.output_current}A")
        if spec.output_current <= 0:
            errors.append(f"Output current must be positive, got {spec.output_current}A")
        return tuple(errors)

    def generate(self, spec: CircuitSpec) -> DesignResult:
        errors = self.validate_spec(spec)
        if errors:
            raise ValueError(f"Invalid spec: {'; '.join(errors)}")
        return self._build_design(spec)

    def _build_design(self, spec: CircuitSpec) -> DesignResult:
        components = self._build_components()
        nets = self._build_nets()
        constraints = self._build_placement_constraints()
        notes = self._build_design_notes(spec)

        return DesignResult(
            spec=spec,
            components=components,
            nets=nets,
            placement_constraints=constraints,
            design_notes=notes,
        )

    def _build_components(self) -> tuple[ComponentSpec, ...]:
        return (
            ComponentSpec(
                reference="U1",
                category=ComponentCategory.IC,
                value="LM2596S-5",
                footprint="Package_TO_SOT_SMD:TO-263-5_TabPin3",
                kicad_library="Regulator_Switching",
                kicad_symbol="LM2596S-5",
                description="5V 2A step-down voltage regulator, 150kHz",
                properties={
                    "input_voltage_max": "40V",
                    "output_voltage": "5V",
                    "output_current_max": "2A",
                    "switching_frequency": "150kHz",
                },
            ),
            ComponentSpec(
                reference="C1",
                category=ComponentCategory.CAPACITOR,
                value="680uF",
                footprint="Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
                kicad_library="Device",
                kicad_symbol="C_Polarized",
                description="Input bypass capacitor, low ESR electrolytic",
                properties={"voltage_rating": "25V", "type": "electrolytic", "esr": "low"},
            ),
            ComponentSpec(
                reference="C2",
                category=ComponentCategory.CAPACITOR,
                value="220uF",
                footprint="Capacitor_THT:CP_Radial_D8.0mm_P3.50mm",
                kicad_library="Device",
                kicad_symbol="C_Polarized",
                description="Output filter capacitor, low ESR electrolytic",
                properties={"voltage_rating": "10V", "type": "electrolytic", "esr": "low"},
            ),
            ComponentSpec(
                reference="L1",
                category=ComponentCategory.INDUCTOR,
                value="33uH",
                footprint="Inductor_THT:L_Radial_D12.5mm_P9.00mm",
                kicad_library="Device",
                kicad_symbol="L",
                description="Energy storage inductor, 33uH 3A saturation",
                properties={
                    "saturation_current": "3A",
                    "dcr_max_ohm": "0.1",
                },
            ),
            ComponentSpec(
                reference="D1",
                category=ComponentCategory.DIODE,
                value="1N5824",
                footprint="Diode_THT:D_DO-201AD_P15.24mm_Horizontal",
                kicad_library="Diode",
                kicad_symbol="1N5824",
                description="Schottky catch diode, 40V 3A",
                properties={
                    "type": "schottky",
                    "voltage_rating": "40V",
                    "current_rating": "3A",
                },
            ),
            ComponentSpec(
                reference="R1",
                category=ComponentCategory.RESISTOR,
                value="10k",
                footprint="Resistor_SMD:R_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description="ON/OFF pull-down to GND (always-on enable)",
                properties={"tolerance": "5%", "power_rating": "0.125W"},
            ),
        )

    def _build_nets(self) -> tuple[NetSpec, ...]:
        return (
            NetSpec(
                name="VIN",
                connections=(
                    ("C1", "1"),
                    ("U1", "IN"),
                ),
            ),
            NetSpec(
                name="GND",
                connections=(
                    ("C1", "2"),
                    ("U1", "GND"),
                    ("D1", "A"),
                    ("C2", "2"),
                    ("R1", "2"),
                ),
            ),
            NetSpec(
                name="SW_NODE",
                connections=(
                    ("U1", "OUT"),
                    ("L1", "1"),
                    ("D1", "K"),
                ),
            ),
            NetSpec(
                name="VOUT",
                connections=(
                    ("L1", "2"),
                    ("C2", "1"),
                    ("U1", "FB"),
                ),
            ),
            NetSpec(
                name="ON_OFF",
                connections=(
                    ("U1", "ON_OFF"),
                    ("R1", "1"),
                ),
            ),
        )

    def _build_placement_constraints(self) -> tuple[PlacementConstraint, ...]:
        return (
            PlacementConstraint(
                component_ref="C1",
                target_ref="U1",
                max_distance_mm=20.0,
                reason="Input capacitor must be close to IN and GND pins (TI datasheet)",
            ),
            PlacementConstraint(
                component_ref="D1",
                target_ref="U1",
                max_distance_mm=15.0,
                reason="Catch diode must minimize loop area with IC (TI datasheet)",
            ),
            PlacementConstraint(
                component_ref="C2",
                target_ref=None,
                max_distance_mm=30.0,
                reason="Output capacitor close to load connection",
            ),
            PlacementConstraint(
                component_ref="L1",
                target_ref="U1",
                max_distance_mm=25.0,
                reason="Inductor between OUT pin and output capacitor",
            ),
        )

    def _build_design_notes(self, spec: CircuitSpec) -> tuple[str, ...]:
        return (
            f"LM2596S-5 fixed 5V output buck converter, {spec.input_voltage}V input, "
            f"{spec.output_current}A max output",
            "Reference: TI SNVS124F datasheet typical application circuit",
            "Use ground plane with star grounding at IC GND pin",
            "Route FB trace away from switching node (L1, D1) to minimize noise coupling",
            f"Power traces (VIN, VOUT, SW_NODE) minimum width: 0.5mm for {spec.output_current}A",
            "ON_OFF pin: R1 (10k) pulls to GND for always-on operation",
        )
