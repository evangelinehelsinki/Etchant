"""Design serialization and deserialization.

Converts DesignResult objects to/from JSON-serializable dicts. Used for:
- Saving designs to disk for later review
- Loading golden reference designs for comparison
- Passing designs between agent sessions
- Storing designs in a database for RAG
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from etchant.core.models import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignResult,
    NetSpec,
    PlacementConstraint,
)


def design_to_dict(design: DesignResult) -> dict[str, Any]:
    """Serialize a DesignResult to a JSON-compatible dict."""
    return {
        "spec": {
            "name": design.spec.name,
            "topology": design.spec.topology,
            "input_voltage": design.spec.input_voltage,
            "output_voltage": design.spec.output_voltage,
            "output_current": design.spec.output_current,
            "description": design.spec.description,
        },
        "components": [
            {
                "reference": c.reference,
                "category": c.category.name,
                "value": c.value,
                "footprint": c.footprint,
                "kicad_library": c.kicad_library,
                "kicad_symbol": c.kicad_symbol,
                "description": c.description,
                "properties": dict(c.properties),
                "jlcpcb_part_number": c.jlcpcb_part_number,
            }
            for c in design.components
        ],
        "nets": [
            {
                "name": n.name,
                "connections": [list(conn) for conn in n.connections],
            }
            for n in design.nets
        ],
        "placement_constraints": [
            {
                "component_ref": pc.component_ref,
                "target_ref": pc.target_ref,
                "max_distance_mm": pc.max_distance_mm,
                "reason": pc.reason,
            }
            for pc in design.placement_constraints
        ],
        "design_notes": list(design.design_notes),
    }


def dict_to_design(data: dict[str, Any]) -> DesignResult:
    """Deserialize a dict back into a DesignResult."""
    spec_data = data["spec"]
    spec = CircuitSpec(
        name=spec_data["name"],
        topology=spec_data["topology"],
        input_voltage=spec_data["input_voltage"],
        output_voltage=spec_data["output_voltage"],
        output_current=spec_data["output_current"],
        description=spec_data["description"],
    )

    components = tuple(
        ComponentSpec(
            reference=c["reference"],
            category=ComponentCategory[c["category"]],
            value=c["value"],
            footprint=c["footprint"],
            kicad_library=c["kicad_library"],
            kicad_symbol=c["kicad_symbol"],
            description=c["description"],
            properties=c.get("properties", {}),
            jlcpcb_part_number=c.get("jlcpcb_part_number"),
        )
        for c in data["components"]
    )

    nets = tuple(
        NetSpec(
            name=n["name"],
            connections=tuple(tuple(conn) for conn in n["connections"]),
        )
        for n in data["nets"]
    )

    constraints = tuple(
        PlacementConstraint(
            component_ref=pc["component_ref"],
            target_ref=pc.get("target_ref"),
            max_distance_mm=pc["max_distance_mm"],
            reason=pc["reason"],
        )
        for pc in data["placement_constraints"]
    )

    notes = tuple(data.get("design_notes", ()))

    return DesignResult(
        spec=spec,
        components=components,
        nets=nets,
        placement_constraints=constraints,
        design_notes=notes,
    )


def save_design(design: DesignResult, path: Path) -> None:
    """Save a design to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(design_to_dict(design), f, indent=2)


def load_design(path: Path) -> DesignResult:
    """Load a design from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    return dict_to_design(data)
