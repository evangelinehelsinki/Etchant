"""Simple point-to-point trace router for power supply boards.

For simple boards (3-7 components), routes traces directly between
connected pads using straight lines with one bend (L-route).
Not a general autorouter — just enough for power supply circuits.

Uses pcbnew's PCB_TRACK API to create traces.
"""

from __future__ import annotations

import logging
from pathlib import Path

from etchant.core.ee_calculations import trace_width_for_current
from etchant.core.models import DesignResult

logger = logging.getLogger(__name__)

# Net names that carry power (use wider traces)
_POWER_NETS = {"VIN", "VOUT", "SW", "SW_NODE"}

try:
    import pcbnew

    HAS_PCBNEW = True
except ImportError:
    HAS_PCBNEW = False


class SimpleRouter:
    """Routes traces between pads on a placed PCB board."""

    def route_board(
        self,
        pcb_path: Path,
        design: DesignResult,
        default_width_mm: float = 0.25,
    ) -> Path:
        """Add traces to an existing .kicad_pcb file.

        Routes each net by connecting pads in sequence with L-shaped traces.
        Power nets get wider traces based on output current.
        """
        if not HAS_PCBNEW:
            raise RuntimeError("pcbnew not available")

        board = pcbnew.LoadBoard(str(pcb_path))

        # Calculate power trace width
        power_width_mm = max(
            default_width_mm,
            trace_width_for_current(design.spec.output_current),
        )
        logger.info(
            "Trace widths: signal=%.2fmm, power=%.2fmm",
            default_width_mm, power_width_mm,
        )

        # Build a map of net name -> pad positions
        net_pads = self._collect_net_pads(board)

        # Route each net
        traces_added = 0
        for net_name, pads in net_pads.items():
            if len(pads) < 2:
                continue

            is_power = net_name in _POWER_NETS
            width = power_width_mm if is_power else default_width_mm
            width_nm = pcbnew.FromMM(width)

            # Get the net code
            net_info = board.GetNetInfo().GetNetItem(net_name)
            if net_info is None:
                continue
            net_code = net_info.GetNetCode()

            # Connect pads in chain (pad0->pad1->pad2->...)
            for i in range(len(pads) - 1):
                start = pads[i]
                end = pads[i + 1]

                # Create L-shaped route (horizontal then vertical)
                mid = pcbnew.VECTOR2I(end.x, start.y)

                # First segment: horizontal
                track1 = pcbnew.PCB_TRACK(board)
                track1.SetStart(start)
                track1.SetEnd(mid)
                track1.SetWidth(width_nm)
                track1.SetLayer(pcbnew.F_Cu)
                track1.SetNetCode(net_code)
                board.Add(track1)

                # Second segment: vertical
                track2 = pcbnew.PCB_TRACK(board)
                track2.SetStart(mid)
                track2.SetEnd(end)
                track2.SetWidth(width_nm)
                track2.SetLayer(pcbnew.F_Cu)
                track2.SetNetCode(net_code)
                board.Add(track2)

                traces_added += 2

            logger.info(
                "Routed %s: %d pads, width=%.2fmm%s",
                net_name, len(pads), width,
                " (power)" if is_power else "",
            )

        board.Save(str(pcb_path))
        logger.info("Saved board with %d traces: %s", traces_added, pcb_path)
        return pcb_path

    def _collect_net_pads(
        self, board: object
    ) -> dict[str, list[object]]:
        """Collect pad positions grouped by net name."""
        net_pads: dict[str, list[object]] = {}

        for fp in board.GetFootprints():
            for pad in fp.Pads():
                net_name = pad.GetNetname()
                if not net_name:
                    continue
                if net_name not in net_pads:
                    net_pads[net_name] = []
                net_pads[net_name].append(pad.GetPosition())

        return net_pads
