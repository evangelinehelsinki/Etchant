"""SKiDL wrapper for generating KiCad netlists from DesignResult objects.

Isolates the SKiDL dependency so the rest of the codebase doesn't touch SKiDL directly.
If SKiDL's API changes or a different netlist tool is needed, only this file changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from etchant.core.models import DesignResult

logger = logging.getLogger(__name__)

try:
    import skidl

    HAS_SKIDL = True
except ImportError:
    HAS_SKIDL = False


def check_skidl_available() -> bool:
    return HAS_SKIDL


class NetlistBuilder:
    """Generates a KiCad .net file from a DesignResult using SKiDL."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def build(self, design: DesignResult) -> Path:
        """Generate a .net netlist file. Returns path to the output file."""
        if not HAS_SKIDL:
            raise RuntimeError(
                "SKiDL is not installed. Run inside the etchant distrobox environment. "
                "See setup-distrobox.sh"
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Reset SKiDL global state (critical for test isolation)
        skidl.reset()

        # Create SKiDL parts from our component specs
        skidl_parts: dict[str, skidl.Part] = {}
        for comp in design.components:
            part = skidl.Part(
                comp.kicad_library,
                comp.kicad_symbol,
                value=comp.value,
                footprint=comp.footprint,
                ref=comp.reference,
            )
            skidl_parts[comp.reference] = part

        # Create nets and wire connections
        for net_spec in design.nets:
            net = skidl.Net(net_spec.name)
            for ref, pin_name in net_spec.connections:
                part = skidl_parts[ref]
                net += part[pin_name]

        # Generate the netlist file
        netlist_name = f"{design.spec.name}.net"
        netlist_path = self._output_dir / netlist_name

        logger.info("Generating netlist: %s", netlist_path)
        skidl.generate_netlist(file_=str(netlist_path))

        if not netlist_path.exists():
            raise RuntimeError(f"SKiDL failed to generate netlist at {netlist_path}")

        logger.info("Netlist generated: %s (%d bytes)", netlist_path, netlist_path.stat().st_size)
        return netlist_path
