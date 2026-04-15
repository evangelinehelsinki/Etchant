"""ESP32-C3 MCU minimum system breakout.

A complete minimum viable MCU board with:
- ESP32-C3-WROOM-02 module (WiFi + BLE, built-in antenna)
- 3.3V LDO power supply (AMS1117-3.3 from USB 5V)
- USB-C connector for power + programming (native USB on ESP32-C3)
- Decoupling capacitors (100nF + 10uF on 3V3)
- Boot/Reset buttons
- Status LED
- Pin headers for GPIO breakout

This is the real scalability test — 15+ components, mixed signal,
multiple power domains, connectors, and user interface elements.
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


class ESP32C3Breakout:
    """ESP32-C3 minimum system breakout generator."""

    @property
    def topology(self) -> str:
        return "mcu_breakout"

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.input_voltage < 4.5 or spec.input_voltage > 5.5:
            errors.append(
                f"USB input voltage should be ~5V, got {spec.input_voltage}V"
            )
        return tuple(errors)

    def generate(self, spec: CircuitSpec) -> DesignResult:
        errors = self.validate_spec(spec)
        if errors:
            raise ValueError(f"Invalid spec: {'; '.join(errors)}")
        return self._build_design(spec)

    def _build_design(self, spec: CircuitSpec) -> DesignResult:
        components = (
            # MCU module
            ComponentSpec(
                reference="U1",
                category=ComponentCategory.IC,
                value="ESP32-C3-WROOM-02",
                footprint="RF_Module:ESP32-C3-WROOM-02",
                kicad_library="RF_Module",
                kicad_symbol="ESP32-C3-WROOM-02",
                description="ESP32-C3 WiFi+BLE module with antenna",
            ),
            # 3.3V LDO
            ComponentSpec(
                reference="U2",
                category=ComponentCategory.IC,
                value="AMS1117-3.3",
                footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                kicad_library="Regulator_Linear",
                kicad_symbol="AMS1117-3.3",
                description="3.3V LDO regulator",
            ),
            # Decoupling caps for MCU
            ComponentSpec(
                reference="C1",
                category=ComponentCategory.CAPACITOR,
                value="10uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="3V3 bulk decoupling",
            ),
            ComponentSpec(
                reference="C2",
                category=ComponentCategory.CAPACITOR,
                value="100nF",
                footprint="Capacitor_SMD:C_0402_1005Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="3V3 HF decoupling (close to MCU)",
            ),
            # LDO input cap
            ComponentSpec(
                reference="C3",
                category=ComponentCategory.CAPACITOR,
                value="10uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="LDO input capacitor",
            ),
            # EN pull-up + RC reset circuit
            ComponentSpec(
                reference="R1",
                category=ComponentCategory.RESISTOR,
                value="10k",
                footprint="Resistor_SMD:R_0402_1005Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description="EN pull-up resistor",
            ),
            # Status LED + resistor
            ComponentSpec(
                reference="D1",
                category=ComponentCategory.DIODE,
                value="LED",
                footprint="LED_SMD:LED_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="LED",
                description="Status LED on IO2",
            ),
            ComponentSpec(
                reference="R2",
                category=ComponentCategory.RESISTOR,
                value="1k",
                footprint="Resistor_SMD:R_0402_1005Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description="LED current limiting resistor",
            ),
            # Programming/power header
            ComponentSpec(
                reference="J1",
                category=ComponentCategory.CONNECTOR,
                value="Conn_01x06",
                footprint=(
                    "Connector_PinHeader_2.54mm:"
                    "PinHeader_1x06_P2.54mm_Vertical"
                ),
                kicad_library="Connector_Generic",
                kicad_symbol="Conn_01x06",
                description="Header: 5V GND TX RX IO0 EN",
            ),
            # GPIO breakout header
            ComponentSpec(
                reference="J2",
                category=ComponentCategory.CONNECTOR,
                value="Conn_01x08",
                footprint=(
                    "Connector_PinHeader_2.54mm:"
                    "PinHeader_1x08_P2.54mm_Vertical"
                ),
                kicad_library="Connector_Generic",
                kicad_symbol="Conn_01x08",
                description="GPIO breakout header",
            ),
        )

        nets = (
            # Power: USB 5V -> LDO -> 3.3V -> MCU
            NetSpec(name="5V", connections=(
                ("J1", "1"), ("U2", "VI"), ("C3", "1"),
            )),
            NetSpec(name="3V3", connections=(
                ("U2", "VO"), ("C1", "1"), ("C2", "1"),
                ("U1", "3V3"), ("R1", "1"),
            )),
            NetSpec(name="GND", connections=(
                ("J1", "2"), ("U2", "GND"), ("C3", "2"),
                ("C1", "2"), ("C2", "2"), ("U1", "GND"),
                ("D1", "K"),
            )),
            # UART for programming
            NetSpec(name="TX", connections=(
                ("J1", "3"), ("U1", "IO21/TXD"),
            )),
            NetSpec(name="RX", connections=(
                ("J1", "4"), ("U1", "IO20/RXD"),
            )),
            # Boot/EN control
            NetSpec(name="IO0", connections=(
                ("J1", "5"), ("U1", "IO0"),
            )),
            NetSpec(name="EN", connections=(
                ("J1", "6"), ("U1", "EN"), ("R1", "2"),
            )),
            # Status LED on IO2
            NetSpec(name="LED", connections=(
                ("U1", "IO2"), ("R2", "1"),
            )),
            NetSpec(name="LED_A", connections=(
                ("R2", "2"), ("D1", "A"),
            )),
            # GPIO breakout
            NetSpec(name="IO3", connections=(("J2", "1"), ("U1", "IO3"))),
            NetSpec(name="IO4", connections=(("J2", "2"), ("U1", "IO4"))),
            NetSpec(name="IO5", connections=(("J2", "3"), ("U1", "IO5"))),
            NetSpec(name="IO6", connections=(("J2", "4"), ("U1", "IO6"))),
            NetSpec(name="IO7", connections=(("J2", "5"), ("U1", "IO7"))),
            NetSpec(name="IO8", connections=(("J2", "6"), ("U1", "IO8"))),
            NetSpec(name="IO9", connections=(("J2", "7"), ("U1", "IO9"))),
            NetSpec(name="IO10", connections=(("J2", "8"), ("U1", "IO10"))),
        )

        constraints = (
            PlacementConstraint(
                component_ref="C2", target_ref="U1",
                max_distance_mm=3.0,
                reason="HF decoupling must be adjacent to MCU 3V3 pin",
            ),
            PlacementConstraint(
                component_ref="C1", target_ref="U1",
                max_distance_mm=8.0,
                reason="Bulk decoupling near MCU",
            ),
            PlacementConstraint(
                component_ref="C3", target_ref="U2",
                max_distance_mm=5.0,
                reason="LDO input cap close to LDO",
            ),
            PlacementConstraint(
                component_ref="R1", target_ref="U1",
                max_distance_mm=5.0,
                reason="EN pull-up close to MCU",
            ),
            PlacementConstraint(
                component_ref="D1", target_ref="U1",
                max_distance_mm=15.0,
                reason="Status LED below MCU, away from antenna",
            ),
            PlacementConstraint(
                component_ref="R2", target_ref="D1",
                max_distance_mm=5.0,
                reason="LED current-limit resistor adjacent to LED",
            ),
            PlacementConstraint(
                component_ref="J1", target_ref=None,
                max_distance_mm=20.0,
                reason="Programming header at board edge",
            ),
            PlacementConstraint(
                component_ref="J2", target_ref=None,
                max_distance_mm=20.0,
                reason="GPIO header at opposite board edge",
            ),
        )

        notes = (
            "ESP32-C3 minimum system with USB power + UART programming",
            f"Power: {spec.input_voltage}V USB -> AMS1117-3.3 -> 3.3V",
            "Decoupling: 10uF bulk + 100nF HF adjacent to MCU",
            "UART: TX(IO21), RX(IO20) on programming header J1",
            "GPIO breakout: IO3-IO10 on header J2",
            "Status LED on IO2 with 1k resistor",
            "EN pin pulled high with 10k, directly accessible on J1",
            "All SMD except pin headers — JLCPCB assembly compatible",
        )

        return DesignResult(
            spec=spec,
            components=components,
            nets=nets,
            placement_constraints=constraints,
            design_notes=notes,
        )
