"""Generative buck converter using WEBENCH + EE calculations.

Instead of hardcoding one IC, this generator:
1. Queries WEBENCH API for the best IC for the given spec
2. Calculates passive values from EE formulas
3. Looks up all parts in the JLCPCB database
4. Falls back to offline mode using cached WEBENCH data

This is the bridge from "hardcoded LM2596" to "arbitrary voltage support."
"""

from __future__ import annotations

import logging
from pathlib import Path

from etchant.core.component_selector import lookup_jlcpcb_part
from etchant.core.ee_calculations import calculate_buck_passives
from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
    PlacementConstraint,
)

logger = logging.getLogger(__name__)

_IC_DEFAULTS = {
    "kicad_library": "Regulator_Switching",
    "footprint": "Package_TO_SOT_SMD:SOT-23-6",
}


class GenerativeBuckConverter:
    """Buck converter generator using live WEBENCH data + EE calculations."""

    def __init__(self, webench_data_dir: Path | None = None) -> None:
        self._webench_dir = webench_data_dir

    @property
    def topology(self) -> str:
        return "buck_converter"

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.output_voltage >= spec.input_voltage:
            errors.append(
                f"Output voltage ({spec.output_voltage}V) must be less than "
                f"input ({spec.input_voltage}V) for a buck converter"
            )
        if spec.input_voltage > 60:
            errors.append(f"Input voltage {spec.input_voltage}V exceeds 60V limit")
        if spec.output_current <= 0:
            errors.append(f"Output current must be positive, got {spec.output_current}A")
        if spec.output_current > 10:
            errors.append(f"Output current {spec.output_current}A exceeds 10A limit")
        if spec.output_voltage <= 0:
            errors.append(f"Output voltage must be positive, got {spec.output_voltage}V")
        return tuple(errors)

    def generate(self, spec: CircuitSpec) -> DesignResult:
        errors = self.validate_spec(spec)
        if errors:
            raise ValueError(f"Invalid spec: {'; '.join(errors)}")

        # Step 1: Find the best IC
        ic_info = self._select_ic(spec)

        # Step 2: Calculate passive values
        passives = calculate_buck_passives(
            vin=spec.input_voltage,
            vout=spec.output_voltage,
            iout=spec.output_current,
            fsw_hz=ic_info.get("frequency_hz", 500_000),
            vref=ic_info.get("vref"),
        )

        # Step 3: Build the design
        return self._build_design(spec, ic_info, passives)

    def _select_ic(self, spec: CircuitSpec) -> dict[str, object]:
        """Select the best IC for this spec."""
        # Try live WEBENCH first
        ic = self._query_webench_live(spec)
        if ic:
            return ic

        # Fall back to cached WEBENCH data
        ic = self._query_webench_cached(spec)
        if ic:
            return ic

        # Final fallback: generic recommendation
        return self._generic_ic(spec)

    def _query_webench_live(self, spec: CircuitSpec) -> dict[str, object] | None:
        """Query WEBENCH API for IC recommendation."""
        try:
            from etchant.data.webench_client import query_webench

            solutions = query_webench(
                vin=spec.input_voltage,
                vout=spec.output_voltage,
                iout=spec.output_current,
                max_results=1,
            )
            if solutions:
                s = solutions[0]
                logger.info("WEBENCH recommends: %s ($%.2f)", s.base_pn, s.price_usd)
                return {
                    "part_number": s.part_number,
                    "base_pn": s.base_pn,
                    "price_usd": s.price_usd,
                    "vin_max": s.vin_max,
                    "source": "webench_live",
                    "frequency_hz": 500_000,
                    "vref": 0.8,
                }
        except Exception:
            logger.debug("WEBENCH API unavailable, falling back to cached data")
        return None

    def _query_webench_cached(self, spec: CircuitSpec) -> dict[str, object] | None:
        """Look up cached WEBENCH designs for a close match."""
        if self._webench_dir is None or not self._webench_dir.exists():
            return None

        try:
            from etchant.data.webench_loader import load_webench_directory

            designs = load_webench_directory(self._webench_dir)
            best = None
            best_distance = float("inf")

            for d in designs:
                if d.topology.lower() != "buck":
                    continue
                distance = (
                    abs(d.vin_min - spec.input_voltage)
                    + abs(d.vout - spec.output_voltage) * 2
                    + abs(d.iout - spec.output_current) * 3
                )
                if distance < best_distance:
                    best = d
                    best_distance = distance

            if best and best_distance < 10:
                logger.info("Cached WEBENCH match: %s (distance=%.1f)", best.device, best_distance)
                return {
                    "part_number": best.device,
                    "base_pn": best.device,
                    "price_usd": best.bom_cost,
                    "source": "webench_cached",
                    "frequency_hz": best.frequency_hz,
                    "vref": 0.8,
                }
        except Exception:
            logger.debug("Cached WEBENCH lookup failed")
        return None

    def _generic_ic(self, spec: CircuitSpec) -> dict[str, object]:
        """Generic fallback when WEBENCH is unavailable."""
        if spec.input_voltage <= 17 and spec.output_current <= 4:
            base_pn = "TPS563200"
        elif spec.input_voltage <= 36 and spec.output_current <= 3:
            base_pn = "TPS54302"
        else:
            base_pn = "LM2596S-ADJ"

        logger.info("Using generic IC: %s (no WEBENCH data)", base_pn)
        return {
            "part_number": base_pn,
            "base_pn": base_pn,
            "price_usd": 0.50,
            "source": "generic_fallback",
            "frequency_hz": 500_000,
            "vref": 0.8,
        }

    def _build_design(
        self,
        spec: CircuitSpec,
        ic_info: dict[str, object],
        passives: object,
    ) -> DesignResult:
        base_pn = str(ic_info["base_pn"])
        source = str(ic_info.get("source", "unknown"))

        # Look up JLCPCB availability
        ic_jlcpcb = lookup_jlcpcb_part(base_pn)

        components = (
            ComponentSpec(
                reference="U1",
                category=ComponentCategory.IC,
                value=base_pn,
                footprint=_IC_DEFAULTS["footprint"],
                kicad_library=_IC_DEFAULTS["kicad_library"],
                kicad_symbol=base_pn,
                description=f"Buck converter IC ({source})",
                properties={
                    "source": source,
                    "price_usd": str(ic_info.get("price_usd", "")),
                },
                jlcpcb_part_number=(
                    ic_jlcpcb.part_number if ic_jlcpcb else None
                ),
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
                description="Output filter capacitor",
                properties={"type": "ceramic", "dielectric": "X5R"},
            ),
            ComponentSpec(
                reference="L1",
                category=ComponentCategory.INDUCTOR,
                value=f"{passives.inductor_uh}uH",
                footprint="Inductor_SMD:L_Vishay_IHLP-2525",
                kicad_library="Device",
                kicad_symbol="L",
                description=f"Power inductor {passives.inductor_uh}uH",
                properties={
                    "saturation_current": f"{spec.output_current * 1.3:.1f}A",
                },
            ),
        )

        # Add feedback resistors if adjustable output
        if passives.feedback_top_kohm is not None:
            components = components + (
                ComponentSpec(
                    reference="R1",
                    category=ComponentCategory.RESISTOR,
                    value=f"{passives.feedback_top_kohm}k",
                    footprint="Resistor_SMD:R_0805_2012Metric",
                    kicad_library="Device",
                    kicad_symbol="R",
                    description="Feedback top resistor (sets Vout)",
                ),
                ComponentSpec(
                    reference="R2",
                    category=ComponentCategory.RESISTOR,
                    value=f"{passives.feedback_bottom_kohm}k",
                    footprint="Resistor_SMD:R_0805_2012Metric",
                    kicad_library="Device",
                    kicad_symbol="R",
                    description="Feedback bottom resistor",
                ),
            )

        # Generic buck converter nets (pin names are functional, not IC-specific)
        nets = [
            NetSpec(name="VIN", connections=(("C1", "1"), ("U1", "VIN"))),
            NetSpec(name="GND", connections=(("C1", "2"), ("U1", "GND"), ("C2", "2"))),
            NetSpec(name="SW", connections=(("U1", "SW"), ("L1", "1"))),
            NetSpec(name="VOUT", connections=(("L1", "2"), ("C2", "1"))),
        ]

        if passives.feedback_top_kohm is not None:
            nets.append(
                NetSpec(name="FB", connections=(("U1", "FB"), ("R1", "1")))
            )
            nets.append(
                NetSpec(name="FB_DIV", connections=(("R1", "2"), ("R2", "1")))
            )
            # R2 bottom to VOUT for top-side sensing
            nets[3] = NetSpec(
                name="VOUT",
                connections=(("L1", "2"), ("C2", "1"), ("R1", "1")),
            )
            nets.append(
                NetSpec(name="FB_GND", connections=(("R2", "2"), ("U1", "GND")))
            )

        constraints = (
            PlacementConstraint(
                component_ref="C1",
                target_ref="U1",
                max_distance_mm=10.0,
                reason="Input cap close to IC for loop area minimization",
            ),
            PlacementConstraint(
                component_ref="C2",
                target_ref=None,
                max_distance_mm=15.0,
                reason="Output cap close to load",
            ),
            PlacementConstraint(
                component_ref="L1",
                target_ref="U1",
                max_distance_mm=10.0,
                reason="Inductor close to SW pin",
            ),
        )

        notes = [
            f"Generative buck: {spec.input_voltage}V -> {spec.output_voltage}V "
            f"@ {spec.output_current}A",
            f"IC: {base_pn} (selected via {source})",
            f"Calculated: L={passives.inductor_uh}uH, "
            f"Cout={passives.output_cap_uf}uF, Cin={passives.input_cap_uf}uF",
            f"Duty cycle: {passives.duty_cycle:.1%}, "
            f"ripple current: {passives.ripple_current_a:.2f}A",
            "All SMD components for JLCPCB assembly compatibility",
        ]

        if passives.feedback_top_kohm is not None:
            notes.append(
                f"Feedback: R1={passives.feedback_top_kohm}k / "
                f"R2={passives.feedback_bottom_kohm}k "
                f"(Vref=0.8V -> {spec.output_voltage}V)"
            )

        return DesignResult(
            spec=spec,
            components=components,
            nets=tuple(nets),
            placement_constraints=constraints,
            design_notes=tuple(notes),
        )
