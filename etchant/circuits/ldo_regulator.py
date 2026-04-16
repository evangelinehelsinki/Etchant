"""AMS1117 LDO voltage regulator circuit generator.

Reference: AMS1117 datasheet typical application circuit.
Week 1: Only AMS1117-3.3 (fixed 3.3V output) is implemented.

Much simpler than a switching converter — just input cap, output cap,
and the regulator IC. No inductor, no diode, no switching node.
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

_INPUT_VOLTAGE_MIN = 4.5  # 3.3V + 1.2V dropout
_INPUT_VOLTAGE_MAX = 15.0
_OUTPUT_VOLTAGE = 3.3
_MAX_CURRENT = 1.0


class AMS1117LDORegulator:
    """Hardcoded AMS1117-3.3 LDO regulator generator."""

    @property
    def topology(self) -> str:
        return "ldo_regulator"

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.output_voltage != _OUTPUT_VOLTAGE:
            errors.append(f"Only 3.3V output supported, got {spec.output_voltage}V")
        if spec.input_voltage < _INPUT_VOLTAGE_MIN:
            errors.append(
                f"Input voltage must be >= {_INPUT_VOLTAGE_MIN}V "
                f"(3.3V + 1.2V dropout), got {spec.input_voltage}V"
            )
        if spec.input_voltage > _INPUT_VOLTAGE_MAX:
            errors.append(
                f"Input voltage must be <= {_INPUT_VOLTAGE_MAX}V, got {spec.input_voltage}V"
            )
        if spec.output_current > _MAX_CURRENT:
            errors.append(f"Max output current is {_MAX_CURRENT}A, got {spec.output_current}A")
        if spec.output_current <= 0:
            errors.append(f"Output current must be positive, got {spec.output_current}A")

        return tuple(errors)

    def _thermal_warnings(self, spec: CircuitSpec) -> tuple[str, ...]:
        """Check power dissipation — returns warnings, not errors."""
        warnings: list[str] = []
        if spec.input_voltage > 0 and spec.output_current > 0:
            power_dissipation = (spec.input_voltage - _OUTPUT_VOLTAGE) * spec.output_current
            if power_dissipation > 2.0:
                warnings.append(
                    f"Power dissipation {power_dissipation:.1f}W is very high for SOT-223 "
                    f"(~1.5W without heatsink). Strongly consider a switching regulator."
                )
            elif power_dissipation > 1.0:
                warnings.append(
                    f"Power dissipation {power_dissipation:.1f}W — ensure adequate copper "
                    f"pour or heatsink on SOT-223 tab pad."
                )
        return tuple(warnings)

    def generate(self, spec: CircuitSpec) -> DesignResult:
        errors = self.validate_spec(spec)
        if errors:
            raise ValueError(f"Invalid spec: {'; '.join(errors)}")
        return self._build_design(spec)

    def _build_design(self, spec: CircuitSpec) -> DesignResult:
        notes = self._build_design_notes(spec) + self._thermal_warnings(spec)
        return DesignResult(
            spec=spec,
            components=self._build_components(),
            nets=self._build_nets(),
            placement_constraints=self._build_placement_constraints(),
            design_notes=notes,
        )

    def _build_components(self) -> tuple[ComponentSpec, ...]:
        return (
            ComponentSpec(
                reference="U1",
                category=ComponentCategory.IC,
                value="AMS1117-3.3",
                footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                kicad_library="Regulator_Linear",
                kicad_symbol="AMS1117-3.3",
                description="3.3V 1A LDO voltage regulator",
                properties={
                    "output_voltage": "3.3V",
                    "output_current_max": "1A",
                    "dropout_voltage": "1.2V",
                    "package": "SOT-223",
                },
            ),
            ComponentSpec(
                reference="C1",
                category=ComponentCategory.CAPACITOR,
                value="10uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="Input decoupling capacitor, ceramic",
                properties={"voltage_rating": "16V", "type": "ceramic", "dielectric": "X5R"},
            ),
            ComponentSpec(
                reference="C2",
                category=ComponentCategory.CAPACITOR,
                value="22uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="Output capacitor, ceramic (required for stability)",
                properties={"voltage_rating": "10V", "type": "ceramic", "dielectric": "X5R"},
            ),
            ComponentSpec(
                reference="J1",
                category=ComponentCategory.CONNECTOR,
                value="Conn_01x02",
                footprint=(
                    "Connector_PinHeader_2.54mm:"
                    "PinHeader_1x02_P2.54mm_Vertical"
                ),
                kicad_library="Connector_Generic",
                kicad_symbol="Conn_01x02",
                description="Input header: VIN, GND",
            ),
            ComponentSpec(
                reference="J2",
                category=ComponentCategory.CONNECTOR,
                value="Conn_01x02",
                footprint=(
                    "Connector_PinHeader_2.54mm:"
                    "PinHeader_1x02_P2.54mm_Vertical"
                ),
                kicad_library="Connector_Generic",
                kicad_symbol="Conn_01x02",
                description="Output header: VOUT, GND",
            ),
        )

    def _build_nets(self) -> tuple[NetSpec, ...]:
        return (
            NetSpec(
                name="VIN",
                connections=(
                    ("J1", "1"),
                    ("C1", "1"),
                    ("U1", "VI"),
                ),
            ),
            NetSpec(
                name="GND",
                connections=(
                    ("J1", "2"),
                    ("C1", "2"),
                    ("U1", "GND"),
                    ("C2", "2"),
                    ("J2", "2"),
                ),
            ),
            NetSpec(
                name="VOUT",
                connections=(
                    ("U1", "VO"),
                    ("C2", "1"),
                    ("J2", "1"),
                ),
            ),
        )

    def _build_placement_constraints(self) -> tuple[PlacementConstraint, ...]:
        return (
            PlacementConstraint(
                component_ref="C1",
                target_ref="U1",
                max_distance_mm=10.0,
                reason="Input capacitor must be close to input pin for stability",
            ),
            PlacementConstraint(
                component_ref="C2",
                target_ref="U1",
                max_distance_mm=10.0,
                reason="Output capacitor critical for LDO stability — place as close as possible",
            ),
            PlacementConstraint(
                component_ref="J1",
                target_ref=None,
                max_distance_mm=30.0,
                reason="Input connector at board edge (VIN/GND)",
            ),
            PlacementConstraint(
                component_ref="J2",
                target_ref=None,
                max_distance_mm=30.0,
                reason="Output connector at opposite board edge (VOUT/GND)",
            ),
        )

    def _build_design_notes(self, spec: CircuitSpec) -> tuple[str, ...]:
        power_dissipation = (spec.input_voltage - _OUTPUT_VOLTAGE) * spec.output_current
        return (
            f"AMS1117-3.3 fixed 3.3V LDO, {spec.input_voltage}V input, "
            f"{spec.output_current}A max output",
            "Reference: AMS1117 datasheet typical application circuit",
            f"Power dissipation: {power_dissipation:.2f}W "
            f"({spec.input_voltage}V - 3.3V) * {spec.output_current}A",
            "Output capacitor is critical for stability — do not omit",
            "All SMD components — compatible with standard JLCPCB assembly",
        )
