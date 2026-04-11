"""I2C sensor breakout board generator.

Generates a simple breakout board for an I2C sensor with:
- Sensor IC with decoupling cap
- I2C pull-up resistors (SDA, SCL)
- Pin header for connection
- Optional LDO if sensor needs different voltage

This tests non-power circuit generation: signal integrity matters,
connectors are a first-class component, and the layout needs to
consider I2C routing (matched length, keep short).
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


class I2CSensorBreakout:
    """I2C sensor breakout board generator."""

    @property
    def topology(self) -> str:
        return "sensor_breakout"

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.input_voltage <= 0:
            errors.append(f"Supply voltage must be positive, got {spec.input_voltage}V")
        if spec.input_voltage > 5.5:
            errors.append(f"Supply voltage {spec.input_voltage}V too high for most sensors")
        return tuple(errors)

    def generate(self, spec: CircuitSpec) -> DesignResult:
        errors = self.validate_spec(spec)
        if errors:
            raise ValueError(f"Invalid spec: {'; '.join(errors)}")
        return self._build_breakout(spec)

    def _build_breakout(self, spec: CircuitSpec) -> DesignResult:
        """Generate a generic I2C sensor breakout."""
        # Pull-up value: 4.7k is standard for I2C at 100/400kHz
        pullup = "4.7k"

        components = (
            ComponentSpec(
                reference="U1",
                category=ComponentCategory.IC,
                value="BME280",
                footprint="Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm",
                kicad_library="Sensor_Pressure",
                kicad_symbol="BME280",
                description="Temperature/humidity/pressure sensor I2C",
                properties={
                    "interface": "I2C",
                    "vdd_range": "1.71-3.6V",
                    "address": "0x76/0x77",
                },
            ),
            ComponentSpec(
                reference="C1",
                category=ComponentCategory.CAPACITOR,
                value="100nF",
                footprint="Capacitor_SMD:C_0402_1005Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="Decoupling capacitor (close to VDD pin)",
            ),
            ComponentSpec(
                reference="R1",
                category=ComponentCategory.RESISTOR,
                value=pullup,
                footprint="Resistor_SMD:R_0402_1005Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description="I2C SCL pull-up resistor",
            ),
            ComponentSpec(
                reference="R2",
                category=ComponentCategory.RESISTOR,
                value=pullup,
                footprint="Resistor_SMD:R_0402_1005Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description="I2C SDA pull-up resistor",
            ),
            ComponentSpec(
                reference="J1",
                category=ComponentCategory.CONNECTOR,
                value="Conn_01x04",
                footprint=(
                    "Connector_PinHeader_2.54mm:"
                    "PinHeader_1x04_P2.54mm_Vertical"
                ),
                kicad_library="Connector_Generic",
                kicad_symbol="Conn_01x04",
                description="I2C header (VCC, GND, SCL, SDA)",
            ),
        )

        nets = (
            NetSpec(name="VCC", connections=(
                ("J1", "1"), ("U1", "VDD"), ("C1", "1"),
                ("R1", "1"), ("R2", "1"),
            )),
            NetSpec(name="GND", connections=(
                ("J1", "2"), ("U1", "GND"), ("C1", "2"),
            )),
            NetSpec(name="SCL", connections=(
                ("J1", "3"), ("U1", "SCL"), ("R1", "2"),
            )),
            NetSpec(name="SDA", connections=(
                ("J1", "4"), ("U1", "SDA"), ("R2", "2"),
            )),
        )

        constraints = (
            PlacementConstraint(
                component_ref="C1", target_ref="U1",
                max_distance_mm=3.0,
                reason="Decoupling cap must be adjacent to sensor VDD pin",
            ),
            PlacementConstraint(
                component_ref="R1", target_ref="U1",
                max_distance_mm=8.0,
                reason="I2C pull-up near sensor for signal integrity",
            ),
            PlacementConstraint(
                component_ref="R2", target_ref="U1",
                max_distance_mm=8.0,
                reason="I2C pull-up near sensor for signal integrity",
            ),
            PlacementConstraint(
                component_ref="J1", target_ref=None,
                max_distance_mm=15.0,
                reason="Header at board edge for easy connection",
            ),
        )

        notes = (
            f"I2C sensor breakout: BME280 at {spec.input_voltage}V",
            "I2C address: 0x76 (SDO=GND) or 0x77 (SDO=VDD)",
            f"Pull-ups: {pullup} on SCL and SDA (100kHz/400kHz)",
            "100nF decoupling cap adjacent to VDD pin",
            "Header pinout: VCC, GND, SCL, SDA",
            "Keep I2C traces short and matched length",
        )

        return DesignResult(
            spec=spec, components=components, nets=nets,
            placement_constraints=constraints, design_notes=notes,
        )
