"""Pre-route critical power nets before autorouting.

Lays down wide traces for power nets (VIN, VOUT, SW) at the correct
width from design_rules.yaml before exporting to Freerouting.
Freerouting respects pre-existing traces and routes around them.

This ensures power traces meet current-carrying requirements and
the autorouter only handles signal traces and remaining connections.
"""

from __future__ import annotations

import logging
from pathlib import Path

from etchant.core.ee_calculations import trace_width_for_current
from etchant.core.models import DesignResult

logger = logging.getLogger(__name__)

# Nets that carry significant current and need wide traces
_POWER_NET_NAMES = {"VIN", "VOUT", "SW", "SW_NODE"}

try:
    import pcbnew

    HAS_PCBNEW = True
except ImportError:
    HAS_PCBNEW = False


def pre_route_power_nets(
    pcb_path: Path,
    design: DesignResult,
    signal_width_mm: float = 0.25,
) -> int:
    """Add pre-routed traces for power nets on an existing board.

    Routes power nets with appropriate widths based on output current.
    Signal nets are left for the autorouter.

    Returns the number of traces added.
    """
    if not HAS_PCBNEW:
        logger.warning("pcbnew not available, skipping pre-routing")
        return 0

    board = pcbnew.LoadBoard(str(pcb_path))

    # Calculate power trace width from design spec
    power_width_mm = max(
        0.5,  # Minimum 0.5mm for any power trace
        trace_width_for_current(design.spec.output_current),
    )
    logger.info(
        "Pre-routing power nets at %.2fmm (%.1fA), signals at %.2fmm",
        power_width_mm, design.spec.output_current, signal_width_mm,
    )

    # Collect pad positions by net
    net_pads: dict[str, list[tuple[int, int]]] = {}
    net_codes: dict[str, int] = {}

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_name = pad.GetNetname()
            if not net_name:
                continue
            if net_name not in net_pads:
                net_pads[net_name] = []
                net_codes[net_name] = pad.GetNet().GetNetCode()
            pos = pad.GetPosition()
            net_pads[net_name].append((pos.x, pos.y))

    traces_added = 0

    for net_name, pads in net_pads.items():
        if len(pads) < 2:
            continue

        # Skip GND — handled by ground plane pour
        if net_name in ("GND", "PGND", "AGND"):
            continue

        is_power = net_name in _POWER_NET_NAMES
        width_mm = power_width_mm if is_power else signal_width_mm
        width_nm = pcbnew.FromMM(width_mm)
        net_code = net_codes[net_name]

        # Route pads in chain with L-shaped traces
        for i in range(len(pads) - 1):
            sx, sy = pads[i]
            ex, ey = pads[i + 1]

            # Midpoint for L-route
            mx, my = ex, sy

            # Horizontal segment
            if sx != mx:
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I(sx, sy))
                track.SetEnd(pcbnew.VECTOR2I(mx, my))
                track.SetWidth(width_nm)
                track.SetLayer(pcbnew.F_Cu)
                track.SetNetCode(net_code)
                board.Add(track)
                traces_added += 1

            # Vertical segment
            if my != ey:
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I(mx, my))
                track.SetEnd(pcbnew.VECTOR2I(ex, ey))
                track.SetWidth(width_nm)
                track.SetLayer(pcbnew.F_Cu)
                track.SetNetCode(net_code)
                board.Add(track)
                traces_added += 1

        logger.info(
            "Pre-routed %s: %d pads, width=%.2fmm%s",
            net_name, len(pads), width_mm,
            " (POWER)" if is_power else "",
        )

    board.Save(str(pcb_path))
    logger.info("Pre-routed %d traces on %s", traces_added, pcb_path)
    return traces_added
