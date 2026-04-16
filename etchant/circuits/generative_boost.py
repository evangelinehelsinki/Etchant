"""Generative boost converter using WEBENCH + EE calculations.

Step-up topology: output voltage higher than input. Used for:
- Battery-powered devices (3.7V Li-Ion -> 5V USB)
- LED drivers
- Higher voltage rails from low-voltage sources

Circuit structure differs from buck:
- Inductor on INPUT side (between Vin and switch node)
- Diode from switch node to output (or sync MOSFET)
- Output cap on the high-voltage side
"""

from __future__ import annotations

import logging
import math

from etchant.core.component_selector import lookup_jlcpcb_part
from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
    PlacementConstraint,
)

logger = logging.getLogger(__name__)


class GenerativeBoostConverter:
    """Boost (step-up) converter generator."""

    @property
    def topology(self) -> str:
        return "boost_converter"

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.output_voltage <= spec.input_voltage:
            errors.append(
                f"Output voltage ({spec.output_voltage}V) must be greater than "
                f"input ({spec.input_voltage}V) for a boost converter"
            )
        if spec.input_voltage <= 0:
            errors.append(f"Input voltage must be positive, got {spec.input_voltage}V")
        if spec.output_voltage > 60:
            errors.append(f"Output voltage {spec.output_voltage}V exceeds 60V limit")
        if spec.output_current <= 0:
            errors.append(f"Output current must be positive, got {spec.output_current}A")
        if spec.output_current > 5:
            errors.append(f"Output current {spec.output_current}A exceeds 5A boost limit")
        return tuple(errors)

    def generate(self, spec: CircuitSpec) -> DesignResult:
        errors = self.validate_spec(spec)
        if errors:
            raise ValueError(f"Invalid spec: {'; '.join(errors)}")

        ic_info = self._select_ic(spec)
        passives = self._calculate_passives(spec, ic_info)
        return self._build_design(spec, ic_info, passives)

    def _select_ic(self, spec: CircuitSpec) -> dict[str, object]:
        """Select boost converter IC via WEBENCH or fallback."""
        try:
            from etchant.data.webench_client import query_webench

            solutions = query_webench(
                vin=spec.input_voltage,
                vout=spec.output_voltage,
                iout=spec.output_current,
                max_results=5,
            )
            for s in solutions:
                if "boost" in s.topology.lower():
                    logger.info("WEBENCH boost: %s ($%.2f)", s.base_pn, s.price_usd)
                    return {
                        "base_pn": s.base_pn,
                        "part_number": s.part_number,
                        "price_usd": s.price_usd,
                        "source": "webench_live",
                        "fsw_hz": 500_000,
                        "vref": 0.8,
                    }
        except Exception:
            logger.debug("WEBENCH unavailable for boost query")

        # Generic fallback
        base_pn = "TPS61230A" if spec.output_current <= 2 else "TPS55340"
        logger.info("Using generic boost IC: %s", base_pn)
        return {
            "base_pn": base_pn,
            "part_number": base_pn,
            "source": "generic_fallback",
            "fsw_hz": 500_000,
            "vref": 0.8,
        }

    def _calculate_passives(
        self, spec: CircuitSpec, ic_info: dict[str, object]
    ) -> dict[str, float]:
        """Calculate boost converter passive values."""
        vin = spec.input_voltage
        vout = spec.output_voltage
        iout = spec.output_current
        fsw = float(ic_info.get("fsw_hz", 500_000))

        # Duty cycle: D = 1 - Vin/Vout
        duty = 1 - vin / vout

        # Input current (higher than output in a boost)
        iin = iout * vout / (vin * 0.9)  # Assume 90% efficiency

        # Inductor: L = Vin * D / (fsw * delta_IL)
        ripple_ratio = 0.3
        delta_il = ripple_ratio * iin
        inductor_h = vin * duty / (fsw * delta_il)
        inductor_uh = inductor_h * 1e6
        inductor_uh = self._nearest_inductor(inductor_uh)

        # Output cap: sized for ripple and hold-up
        # Cout = Iout * D / (fsw * Vripple)
        vripple = 0.030  # 30mV target
        cout_f = iout * duty / (fsw * vripple)
        cout_uf = max(cout_f * 1e6, 22.0)
        cout_uf = self._nearest_cap(cout_uf)

        # Input cap
        cin_uf = max(10.0, cout_uf / 2)
        cin_uf = self._nearest_cap(cin_uf)

        # Feedback resistors
        vref = float(ic_info.get("vref", 0.8))
        rfbb = 10.0  # kOhm
        rfbt = rfbb * (vout / vref - 1)
        rfbt = self._nearest_resistor(rfbt)

        return {
            "inductor_uh": inductor_uh,
            "cout_uf": cout_uf,
            "cin_uf": cin_uf,
            "rfbt_kohm": rfbt,
            "rfbb_kohm": rfbb,
            "duty": duty,
            "iin": iin,
        }

    def _build_design(
        self,
        spec: CircuitSpec,
        ic_info: dict[str, object],
        passives: dict[str, float],
    ) -> DesignResult:
        base_pn = str(ic_info["base_pn"])
        source = str(ic_info.get("source", "unknown"))
        ic_jlcpcb = lookup_jlcpcb_part(base_pn)

        components = (
            ComponentSpec(
                reference="U1",
                category=ComponentCategory.IC,
                value=base_pn,
                footprint="Package_TO_SOT_SMD:SOT-23-6",
                kicad_library="Regulator_Switching",
                kicad_symbol=base_pn,
                description=f"Boost converter IC ({source})",
                properties={"source": source},
                jlcpcb_part_number=ic_jlcpcb.part_number if ic_jlcpcb else None,
            ),
            ComponentSpec(
                reference="L1",
                category=ComponentCategory.INDUCTOR,
                value=f"{passives['inductor_uh']}uH",
                footprint="Inductor_SMD:L_Vishay_IHLP-2525",
                kicad_library="Device",
                kicad_symbol="L",
                description="Boost inductor (input side)",
            ),
            ComponentSpec(
                reference="C1",
                category=ComponentCategory.CAPACITOR,
                value=f"{passives['cin_uf']:.0f}uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="Input decoupling capacitor",
            ),
            ComponentSpec(
                reference="C2",
                category=ComponentCategory.CAPACITOR,
                value=f"{passives['cout_uf']:.0f}uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="Output filter capacitor",
                properties={
                    "voltage_rating": f"{int(spec.output_voltage * 1.5)}V",
                },
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
                reference="R1",
                category=ComponentCategory.RESISTOR,
                value=f"{passives['rfbt_kohm']}k",
                footprint="Resistor_SMD:R_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description="Feedback top resistor (sets Vout)",
            ),
            ComponentSpec(
                reference="R2",
                category=ComponentCategory.RESISTOR,
                value=f"{passives['rfbb_kohm']}k",
                footprint="Resistor_SMD:R_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="R",
                description="Feedback bottom resistor",
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
                description="Output header: VOUT (boosted), GND",
            ),
        )

        nets = (
            NetSpec(name="VIN", connections=(
                ("J1", "1"), ("C1", "1"), ("L1", "1"),
            )),
            NetSpec(name="SW", connections=(
                ("L1", "2"), ("U1", "SW"), ("D1", "A"),
            )),
            NetSpec(name="VOUT", connections=(
                ("D1", "K"), ("C2", "1"), ("R1", "1"), ("J2", "1"),
            )),
            NetSpec(name="GND", connections=(
                ("J1", "2"), ("C1", "2"), ("U1", "GND"), ("C2", "2"), ("R2", "2"), ("J2", "2"),
            )),
            NetSpec(name="FB", connections=(
                ("U1", "FB"), ("R1", "2"), ("R2", "1"),
            )),
        )

        constraints = (
            PlacementConstraint(
                component_ref="L1", target_ref="U1", max_distance_mm=10.0,
                reason="Inductor close to SW pin for loop area",
            ),
            PlacementConstraint(
                component_ref="D1", target_ref="U1", max_distance_mm=10.0,
                reason="Diode close to SW node",
            ),
            PlacementConstraint(
                component_ref="C2", target_ref=None, max_distance_mm=15.0,
                reason="Output cap close to load",
            ),
            PlacementConstraint(
                component_ref="J1", target_ref=None, max_distance_mm=30.0,
                reason="Input connector at board edge (VIN/GND)",
            ),
            PlacementConstraint(
                component_ref="J2", target_ref=None, max_distance_mm=30.0,
                reason="Output connector at opposite board edge (VOUT/GND)",
            ),
        )

        notes = (
            f"Generative boost: {spec.input_voltage}V -> {spec.output_voltage}V "
            f"@ {spec.output_current}A",
            f"IC: {base_pn} (selected via {source})",
            f"Duty cycle: {passives['duty']:.1%}, "
            f"input current: {passives['iin']:.2f}A",
            f"L={passives['inductor_uh']}uH, Cout={passives['cout_uf']:.0f}uF, "
            f"Rfbt={passives['rfbt_kohm']}k/Rfbb={passives['rfbb_kohm']}k",
            "All SMD components for JLCPCB assembly",
        )

        return DesignResult(
            spec=spec,
            components=components,
            nets=nets,
            placement_constraints=constraints,
            design_notes=notes,
        )

    @staticmethod
    def _nearest_inductor(value_uh: float) -> float:
        standards = [
            0.1, 0.15, 0.22, 0.33, 0.47, 0.68,
            1.0, 1.5, 2.2, 3.3, 4.7, 6.8,
            10, 15, 22, 33, 47, 68, 100,
        ]
        return min(standards, key=lambda s: abs(s - value_uh))

    @staticmethod
    def _nearest_cap(value_uf: float) -> float:
        standards = [0.1, 0.22, 0.47, 1.0, 2.2, 4.7, 10, 22, 47, 100, 220, 470]
        return min(standards, key=lambda s: abs(s - value_uf))

    @staticmethod
    def _nearest_resistor(value_kohm: float) -> float:
        e24 = [
            1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
            3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
        ]
        if value_kohm <= 0:
            return 1.0
        decade = 10 ** math.floor(math.log10(value_kohm))
        normalized = value_kohm / decade
        nearest = min(e24, key=lambda v: abs(v - normalized))
        return round(nearest * decade, 3)
