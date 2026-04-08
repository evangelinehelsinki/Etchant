"""Loader for TI WEBENCH reference design data.

Reads WEBENCH exports (solutions.json + component JSONs) and converts
them into DesignResult-compatible formats for:
- Training data for the agent (spec in -> components out)
- Golden references for new circuit topologies
- RAG context for the LLM layer
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WebenchDesign:
    """A single WEBENCH reference design."""

    device: str
    topology: str
    vin_min: float
    vin_max: float
    vout: float
    iout: float
    efficiency: float
    bom_cost: float
    bom_count: int
    frequency_hz: float
    temperature_c: float
    components: tuple[WebenchComponent, ...]


@dataclass(frozen=True)
class WebenchComponent:
    """A component from a WEBENCH design."""

    ref: str
    value: str
    quantity: int
    esr: str | None = None
    dcr: str | None = None


def load_webench_directory(base_dir: Path) -> list[WebenchDesign]:
    """Load all WEBENCH designs from a directory.

    Expects structure: base_dir/{spec}/*.json
    """
    designs: list[WebenchDesign] = []

    if not base_dir.exists():
        return designs

    for spec_dir in sorted(base_dir.iterdir()):
        if not spec_dir.is_dir():
            continue

        for comp_file in sorted(spec_dir.glob("*_components.json")):
            design = load_component_json(comp_file)
            if design is not None:
                designs.append(design)

    return designs


def load_component_json(path: Path) -> WebenchDesign | None:
    """Load a single WEBENCH component JSON file."""
    with open(path) as f:
        data = json.load(f)

    spec = data.get("spec", {})
    components_raw = data.get("components", [])

    components = tuple(
        WebenchComponent(
            ref=c.get("ref", ""),
            value=c.get("value", ""),
            quantity=c.get("qty", 1),
            esr=c.get("esr"),
            dcr=c.get("dcr"),
        )
        for c in components_raw
    )

    return WebenchDesign(
        device=data.get("device", ""),
        topology=data.get("topology", ""),
        vin_min=spec.get("vin_min", 0),
        vin_max=spec.get("vin_max", 0),
        vout=spec.get("vout", 0),
        iout=spec.get("iout", 0),
        efficiency=data.get("efficiency", 0),
        bom_cost=data.get("bom_cost", 0),
        bom_count=data.get("bom_count", 0),
        frequency_hz=data.get("frequency_hz", 0),
        temperature_c=data.get("temperature_c", 0),
        components=components,
    )


def summarize_designs(designs: list[WebenchDesign]) -> str:
    """Produce a human-readable summary of loaded designs."""
    if not designs:
        return "No WEBENCH designs loaded"

    lines = [f"WEBENCH designs: {len(designs)}"]

    # Group by spec
    specs: dict[str, list[WebenchDesign]] = {}
    for d in designs:
        key = f"{d.vin_min}V->{d.vout}V@{d.iout}A"
        specs.setdefault(key, []).append(d)

    for spec_key, spec_designs in sorted(specs.items()):
        lines.append(f"\n  {spec_key} ({len(spec_designs)} designs):")
        for d in spec_designs:
            lines.append(
                f"    {d.device}: {d.efficiency:.0%} efficient, "
                f"${d.bom_cost:.2f} BOM, {d.bom_count} parts, "
                f"{d.temperature_c:.0f}C"
            )

    return "\n".join(lines)
