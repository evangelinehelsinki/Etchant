"""Generative LDO regulator using WEBENCH + EE calculations.

Supports arbitrary voltage/current specs by querying WEBENCH for
the best LDO IC and calculating passives from EE formulas.
Falls back to AMS1117 series when offline.
"""

from __future__ import annotations

import logging

from etchant.core.component_selector import lookup_jlcpcb_part
from etchant.core.ee_calculations import calculate_ldo_passives
from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
    PlacementConstraint,
)

logger = logging.getLogger(__name__)

# AMS1117 fixed variants for offline fallback
_AMS1117_FIXED_VOLTAGES = {1.2, 1.5, 1.8, 2.5, 3.3, 5.0}


class GenerativeLDORegulator:
    """LDO regulator generator using WEBENCH + EE calculations."""

    @property
    def topology(self) -> str:
        return "ldo_regulator"

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.output_voltage >= spec.input_voltage:
            errors.append(
                f"Output voltage ({spec.output_voltage}V) must be less than "
                f"input ({spec.input_voltage}V) for an LDO"
            )
        if spec.output_voltage <= 0:
            errors.append(f"Output voltage must be positive, got {spec.output_voltage}V")
        if spec.output_current <= 0:
            errors.append(f"Output current must be positive, got {spec.output_current}A")
        if spec.output_current > 5:
            errors.append(
                f"Output current {spec.output_current}A exceeds typical LDO range. "
                f"Consider a switching regulator."
            )
        if spec.input_voltage > 20:
            errors.append(
                f"Input voltage {spec.input_voltage}V is high for an LDO. "
                f"Consider a switching regulator to avoid excessive heat."
            )
        return tuple(errors)

    def generate(self, spec: CircuitSpec) -> DesignResult:
        errors = self.validate_spec(spec)
        if errors:
            raise ValueError(f"Invalid spec: {'; '.join(errors)}")

        ic_info = self._select_ic(spec)
        passives = calculate_ldo_passives(
            vin=spec.input_voltage,
            vout=spec.output_voltage,
            iout=spec.output_current,
        )
        return self._build_design(spec, ic_info, passives)

    def _select_ic(self, spec: CircuitSpec) -> dict[str, object]:
        """Select the best LDO IC."""
        # Try WEBENCH
        ic = self._query_webench(spec)
        if ic:
            return ic
        # Fallback to AMS1117 series
        return self._ams1117_fallback(spec)

    def _query_webench(self, spec: CircuitSpec) -> dict[str, object] | None:
        try:
            from etchant.data.webench_client import query_webench

            solutions = query_webench(
                vin=spec.input_voltage,
                vout=spec.output_voltage,
                iout=spec.output_current,
                max_results=5,
            )
            # Filter for LDO topology
            for s in solutions:
                if "ldo" in s.topology.lower() or "linear" in s.topology.lower():
                    logger.info("WEBENCH LDO: %s ($%.2f)", s.base_pn, s.price_usd)
                    return {
                        "part_number": s.part_number,
                        "base_pn": s.base_pn,
                        "price_usd": s.price_usd,
                        "source": "webench_live",
                        "package": "SOT-223",
                    }
        except Exception:
            logger.debug("WEBENCH unavailable for LDO query")
        return None

    def _ams1117_fallback(self, spec: CircuitSpec) -> dict[str, object]:
        """Fall back to AMS1117 series."""
        if spec.output_voltage in _AMS1117_FIXED_VOLTAGES:
            pn = f"AMS1117-{spec.output_voltage}"
            logger.info("Using fixed AMS1117: %s", pn)
            return {
                "part_number": pn,
                "base_pn": pn,
                "source": "ams1117_fixed",
                "package": "SOT-223",
            }

        logger.info("Using AMS1117-ADJ for %.1fV output", spec.output_voltage)
        return {
            "part_number": "AMS1117-ADJ",
            "base_pn": "AMS1117-ADJ",
            "source": "ams1117_adjustable",
            "package": "SOT-223",
            "vref": 1.25,
        }

    def _build_design(
        self,
        spec: CircuitSpec,
        ic_info: dict[str, object],
        passives: object,
    ) -> DesignResult:
        base_pn = str(ic_info["base_pn"])
        source = str(ic_info.get("source", "unknown"))
        ic_jlcpcb = lookup_jlcpcb_part(base_pn)

        components: list[ComponentSpec] = [
            ComponentSpec(
                reference="U1",
                category=ComponentCategory.IC,
                value=base_pn,
                footprint=f"Package_TO_SOT_SMD:{ic_info.get('package', 'SOT-223')}-3_TabPin2",
                kicad_library="Regulator_Linear",
                kicad_symbol=base_pn,
                description=f"LDO voltage regulator ({source})",
                properties={"source": source},
                jlcpcb_part_number=ic_jlcpcb.part_number if ic_jlcpcb else None,
            ),
            ComponentSpec(
                reference="C1",
                category=ComponentCategory.CAPACITOR,
                value=f"{passives.input_cap_uf:.0f}uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="Input decoupling capacitor",
                properties={"type": "ceramic", "dielectric": "X5R"},
            ),
            ComponentSpec(
                reference="C2",
                category=ComponentCategory.CAPACITOR,
                value=f"{passives.output_cap_uf:.0f}uF",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                kicad_library="Device",
                kicad_symbol="C",
                description="Output capacitor (critical for stability)",
                properties={"type": "ceramic", "dielectric": "X5R"},
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
        ]

        nets: list[NetSpec] = [
            NetSpec(name="VIN", connections=(("J1", "1"), ("C1", "1"), ("U1", "VI"))),
            NetSpec(name="GND", connections=(("J1", "2"), ("C1", "2"), ("U1", "GND"), ("C2", "2"), ("J2", "2"))),
            NetSpec(name="VOUT", connections=(("U1", "VO"), ("C2", "1"), ("J2", "1"))),
        ]

        # Add feedback resistors for adjustable LDOs
        vref = ic_info.get("vref")
        if vref is not None:
            from etchant.core.ee_calculations import _nearest_standard_resistor

            rfbb = 1.0  # 1k bottom resistor for AMS1117-ADJ
            rfbt = _nearest_standard_resistor(rfbb * (spec.output_voltage / float(vref) - 1))

            components.extend([
                ComponentSpec(
                    reference="R1",
                    category=ComponentCategory.RESISTOR,
                    value=f"{rfbt}k",
                    footprint="Resistor_SMD:R_0805_2012Metric",
                    kicad_library="Device",
                    kicad_symbol="R",
                    description="Feedback top resistor (sets Vout)",
                ),
                ComponentSpec(
                    reference="R2",
                    category=ComponentCategory.RESISTOR,
                    value=f"{rfbb}k",
                    footprint="Resistor_SMD:R_0805_2012Metric",
                    kicad_library="Device",
                    kicad_symbol="R",
                    description="Feedback bottom resistor",
                ),
            ])
            nets.append(
                NetSpec(name="ADJ", connections=(("U1", "ADJ"), ("R1", "2"), ("R2", "1")))
            )
            # R1 top connects to VOUT (keep J2 connection too)
            nets[2] = NetSpec(
                name="VOUT", connections=(("U1", "VO"), ("C2", "1"), ("J2", "1"), ("R1", "1"))
            )
            # R2 bottom connects to GND (keep J1/J2 connections too)
            nets[1] = NetSpec(
                name="GND",
                connections=(("J1", "2"), ("C1", "2"), ("U1", "GND"), ("C2", "2"), ("J2", "2"), ("R2", "2")),
            )

        constraints = (
            PlacementConstraint(
                component_ref="C1", target_ref="U1", max_distance_mm=10.0,
                reason="Input cap close to input pin for stability",
            ),
            PlacementConstraint(
                component_ref="C2", target_ref="U1", max_distance_mm=10.0,
                reason="Output cap critical for LDO stability",
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

        notes = [
            f"Generative LDO: {spec.input_voltage}V -> {spec.output_voltage}V "
            f"@ {spec.output_current}A",
            f"IC: {base_pn} (selected via {source})",
            f"Power dissipation: {passives.power_dissipation_w:.2f}W, "
            f"efficiency: {passives.efficiency:.0%}",
            "All SMD components for JLCPCB assembly",
        ]
        if passives.power_dissipation_w > 1.0:
            notes.append(
                f"WARNING: {passives.power_dissipation_w:.1f}W dissipation — "
                f"ensure adequate copper pour or heatsink"
            )

        return DesignResult(
            spec=spec,
            components=tuple(components),
            nets=tuple(nets),
            placement_constraints=constraints,
            design_notes=tuple(notes),
        )
