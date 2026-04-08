"""Design export to JSON and CSV formats.

Produces machine-readable and human-readable exports of a DesignResult
without requiring KiCad or SKiDL. Useful for validation, review, and
as input to the LLM agent layer.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from etchant.core.bom import BOMGenerator
from etchant.core.models import DesignResult


class DesignExporter:
    """Exports designs to various formats."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def export_json(self, design: DesignResult) -> Path:
        """Export the full design as a JSON file."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        data = {
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

        path = self._output_dir / f"{design.spec.name}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def export_bom_csv(self, design: DesignResult) -> Path:
        """Export a BOM as a JLCPCB-compatible CSV."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        bom_gen = BOMGenerator()
        bom = bom_gen.generate(design)

        path = self._output_dir / f"{design.spec.name}_bom.csv"

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Reference",
            "Value",
            "Footprint",
            "Description",
            "Quantity",
            "JLCPCB Part #",
            "Classification",
        ])

        for entry in bom:
            writer.writerow([
                entry.reference,
                entry.value,
                entry.footprint,
                entry.description,
                entry.quantity,
                entry.jlcpcb_part_number or "",
                entry.classification.value if entry.classification else "",
            ])

        with open(path, "w", newline="") as f:
            f.write(output.getvalue())

        return path
