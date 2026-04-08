"""Component placement via KiCad's pcbnew API.

NOTE: pcbnew is only available inside the KiCad distrobox environment.
This module will raise ImportError if pcbnew is not available.

Week 1: stub implementation. Actual pcbnew integration comes once
the distrobox environment is verified working.
"""

from __future__ import annotations

from pathlib import Path

from etchant.core.models import DesignResult


class ComponentPlacer:
    """Places components on a PCB using KiCad's pcbnew API."""

    def place_components(
        self,
        pcb_path: Path,
        design: DesignResult,
    ) -> Path:
        """Place components according to design constraints. Returns path to .kicad_pcb."""
        raise NotImplementedError(
            "pcbnew placement requires KiCad environment. See setup-distrobox.sh"
        )
