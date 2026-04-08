"""KiCad project writer.

Generates a minimal .kicad_pro project file and organizes output into a proper
KiCad project directory that can be opened directly in KiCad.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from etchant.core.models import DesignResult

logger = logging.getLogger(__name__)

_KICAD_PRO_TEMPLATE: dict[str, object] = {
    "meta": {
        "filename": "",
        "version": 1,
    },
    "schematic": {
        "legacy_lib_dir": "",
        "legacy_lib_list": [],
    },
    "boards": [],
    "text_variables": {},
}


class ProjectWriter:
    """Creates a KiCad project directory from a DesignResult and netlist."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def write_project(self, design: DesignResult, netlist_path: Path) -> Path:
        """Create a KiCad project directory. Returns path to .kicad_pro."""
        project_name = _sanitize_name(design.spec.name)
        project_dir = self._output_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Copy netlist into project directory
        dest_netlist = project_dir / netlist_path.name
        shutil.copy2(netlist_path, dest_netlist)

        # Write .kicad_pro
        pro_path = project_dir / f"{project_name}.kicad_pro"
        pro_data = {
            **_KICAD_PRO_TEMPLATE,
            "meta": {
                "filename": pro_path.name,
                "version": 1,
            },
        }

        with open(pro_path, "w") as f:
            json.dump(pro_data, f, indent=2)

        # Write a design summary as a text file for reference
        summary_path = project_dir / "design_notes.txt"
        with open(summary_path, "w") as f:
            f.write(f"Design: {design.spec.name}\n")
            f.write(f"Topology: {design.spec.topology}\n")
            f.write(f"Input: {design.spec.input_voltage}V\n")
            f.write(f"Output: {design.spec.output_voltage}V @ {design.spec.output_current}A\n")
            f.write(f"\nComponents ({len(design.components)}):\n")
            for comp in design.components:
                f.write(f"  {comp.reference}: {comp.value} ({comp.description})\n")
            f.write(f"\nNets ({len(design.nets)}):\n")
            for net in design.nets:
                pins = ", ".join(f"{ref}.{pin}" for ref, pin in net.connections)
                f.write(f"  {net.name}: {pins}\n")
            f.write("\nDesign Notes:\n")
            for note in design.design_notes:
                f.write(f"  - {note}\n")

        logger.info("KiCad project written: %s", pro_path)
        return pro_path


def _sanitize_name(name: str) -> str:
    """Convert a design name to a valid directory/file name."""
    sanitized = re.sub(r"[^\w\-.]", "_", name.lower())
    sanitized = sanitized.strip("_")
    if not sanitized:
        raise ValueError(f"Design name '{name}' produces empty sanitized name")
    return sanitized
