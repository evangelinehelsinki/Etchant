"""Component placement engine using KiCad's pcbnew API.

Creates a .kicad_pcb board directly from a DesignResult, placing
footprints according to placement constraints. No netlist import
needed — footprints are loaded directly from KiCad libraries.

NOTE: pcbnew is only available inside the KiCad distrobox environment.
Uses system Python (not venv) since pcbnew is a system package.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from etchant.core.models import ComponentCategory, DesignResult

logger = logging.getLogger(__name__)

_BOARD_MARGIN = 3.0
# KiCad convention: boards are placed near center of A4 sheet
_PAGE_OFFSET_X = 100.0
_PAGE_OFFSET_Y = 100.0

try:
    import pcbnew

    HAS_PCBNEW = True
except ImportError:
    HAS_PCBNEW = False


def check_pcbnew_available() -> bool:
    return HAS_PCBNEW


class ComponentPlacer:
    """Places components on a PCB using KiCad's pcbnew API."""

    def create_board(
        self,
        design: DesignResult,
        output_path: Path,
        board_width_mm: float | None = None,
        board_height_mm: float | None = None,
    ) -> Path:
        """Create a .kicad_pcb with placed footprints.

        Loads footprints from KiCad libraries and places them according
        to the design's placement constraints.
        """
        if not HAS_PCBNEW:
            raise RuntimeError(
                "pcbnew not available. Run inside distrobox with system Python."
            )

        board = pcbnew.BOARD()

        # Auto-size board based on component count and type
        n = len(design.components)
        tht_count = sum(1 for c in design.components if "_THT:" in c.footprint)
        spacing = 5.0 + tht_count * 3.0  # More THT = more spacing needed
        if board_width_mm is None:
            board_width_mm = max(25.0, 15.0 + n * spacing)
        if board_height_mm is None:
            board_height_mm = max(20.0, 12.0 + n * (spacing * 0.8))

        # Load and place footprints
        positions = self._calculate_positions(design, board_width_mm, board_height_mm)

        for comp in design.components:
            fp = self._load_footprint(board, comp.footprint)
            if fp is None:
                logger.warning(
                    "Could not load footprint for %s: %s",
                    comp.reference, comp.footprint,
                )
                continue

            fp.SetReference(comp.reference)
            fp.SetValue(comp.value)

            if comp.reference in positions:
                x_mm, y_mm, rotation = positions[comp.reference]
                fp.SetPosition(
                    pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))
                )
                fp.SetOrientationDegrees(rotation)

            board.Add(fp)
            logger.info("Placed %s (%s) at %.1f, %.1f", comp.reference, comp.value,
                        positions.get(comp.reference, (0, 0, 0))[0],
                        positions.get(comp.reference, (0, 0, 0))[1])

        # Assign nets to pads based on design connectivity
        self._assign_nets(board, design)

        # Add board outline
        self._add_board_outline(board, board_width_mm, board_height_mm)

        # Add ground plane (copper pour on GND net)
        self._add_ground_plane(board, board_width_mm, board_height_mm)

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        board.Save(str(output_path))
        logger.info("Board saved: %s", output_path)
        return output_path

    def _assign_nets(self, board: object, design: DesignResult) -> None:
        """Assign net names to footprint pads based on design connectivity."""
        from etchant.kicad.pin_mapping import get_pad_number, get_pin_name

        # Build a map: (component_ref, pin_name) -> net_name
        pin_nets: dict[tuple[str, str], str] = {}
        for net_spec in design.nets:
            for ref, pin in net_spec.connections:
                pin_nets[(ref, pin)] = net_spec.name

        # Create net info items
        net_names = {n.name for n in design.nets}
        net_items: dict[str, object] = {}
        for net_name in net_names:
            ni = pcbnew.NETINFO_ITEM(board, net_name)
            board.Add(ni)
            net_items[net_name] = ni

        # Build component lookup
        comp_by_ref = {c.reference: c for c in design.components}

        # Assign nets to pads
        assigned = 0
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            comp = comp_by_ref.get(ref)
            if comp is None:
                continue

            for pad in fp.Pads():
                pad_num = str(pad.GetNumber())

                # Try direct pad number match (works for passives: "1", "2")
                key = (ref, pad_num)
                if key in pin_nets:
                    ni = net_items.get(pin_nets[key])
                    if ni:
                        pad.SetNet(ni)
                        assigned += 1
                        continue

                # Passive pin name -> pad number mapping
                _PASSIVE_PIN_MAP = {
                    "A": "1", "K": "2",  # Diodes
                }
                mapped = False
                for pin_alias, target_pad in _PASSIVE_PIN_MAP.items():
                    if pad_num == target_pad and (ref, pin_alias) in pin_nets:
                        ni = net_items.get(pin_nets[(ref, pin_alias)])
                        if ni:
                            pad.SetNet(ni)
                            assigned += 1
                            mapped = True
                            break
                if mapped:
                    continue

                # For ICs: find which pin name maps to this pad number
                if comp.category.name == "IC":
                    for (r, pin_name), net_name in pin_nets.items():
                        if r != ref:
                            continue
                        # Map generic pin -> KiCad pin -> pad number
                        kicad_pin = get_pin_name(comp.kicad_symbol, pin_name)
                        expected_pad = get_pad_number(comp.footprint, kicad_pin)
                        if expected_pad == pad_num:
                            ni = net_items.get(net_name)
                            if ni:
                                pad.SetNet(ni)
                                assigned += 1
                                break

        logger.info("Assigned %d pad-net connections", assigned)

    def _load_footprint(self, board: object, footprint_str: str) -> object | None:
        """Load a footprint from KiCad libraries."""
        # footprint_str format: "Library:Footprint" e.g. "Resistor_SMD:R_0805_2012Metric"
        parts = footprint_str.split(":")
        if len(parts) != 2:
            return None

        lib_name, fp_name = parts

        try:
            fp = pcbnew.FootprintLoad(
                f"/usr/share/kicad/footprints/{lib_name}.pretty",
                fp_name,
            )
            if fp is not None:
                return fp
        except Exception:
            pass

        # Fallback: create a minimal placeholder footprint
        logger.debug("Creating placeholder for %s", footprint_str)
        fp = pcbnew.FOOTPRINT(board)
        return fp

    def _calculate_positions(
        self,
        design: DesignResult,
        board_w: float,
        board_h: float,
    ) -> dict[str, tuple[float, float, float]]:
        """Calculate component positions. Returns {ref: (x_mm, y_mm, rotation_deg)}."""
        positions: dict[str, tuple[float, float, float]] = {}

        center_x = _PAGE_OFFSET_X + board_w / 2
        center_y = _PAGE_OFFSET_Y + board_h / 2

        # Find the IC
        ic_ref = None
        for comp in design.components:
            if comp.category == ComponentCategory.IC:
                ic_ref = comp.reference
                break

        if ic_ref is None and design.components:
            ic_ref = design.components[0].reference

        # Place IC in center
        if ic_ref:
            positions[ic_ref] = (center_x, center_y, 0)

        # Place passives around the IC
        passive_refs = [c.reference for c in design.components if c.reference != ic_ref]
        if not passive_refs:
            return positions

        angle_step = 360.0 / len(passive_refs)
        current_angle = -90.0  # Start above IC

        for comp in design.components:
            if comp.reference in positions:
                continue

            is_tht = "_THT:" in comp.footprint
            base_distance = 15.0 if is_tht else 8.0
            distance = base_distance
            for pc in design.placement_constraints:
                if pc.component_ref == comp.reference:
                    distance = max(base_distance, min(pc.max_distance_mm, 18.0))
                    break

            rad = math.radians(current_angle)
            x = center_x + distance * math.cos(rad)
            y = center_y + distance * math.sin(rad)

            x_min = _PAGE_OFFSET_X + _BOARD_MARGIN
            x_max = _PAGE_OFFSET_X + board_w - _BOARD_MARGIN
            y_min = _PAGE_OFFSET_Y + _BOARD_MARGIN
            y_max = _PAGE_OFFSET_Y + board_h - _BOARD_MARGIN
            x = max(x_min, min(x_max, x))
            y = max(y_min, min(y_max, y))

            rotation = 0.0
            if comp.category in (ComponentCategory.CAPACITOR, ComponentCategory.RESISTOR):
                rotation = 90.0 if abs(math.cos(rad)) < 0.5 else 0.0

            positions[comp.reference] = (round(x, 2), round(y, 2), rotation)
            current_angle += angle_step

        return positions

    def _add_ground_plane(
        self, board: object, width_mm: float, height_mm: float
    ) -> None:
        """Add a copper pour zone on the GND net covering the entire board."""
        # Find or create GND net
        gnd_net = board.GetNetInfo().GetNetItem("GND")
        if gnd_net is None:
            gnd_net = pcbnew.NETINFO_ITEM(board, "GND")
            board.Add(gnd_net)

        zone = pcbnew.ZONE(board)
        zone.SetLayer(pcbnew.B_Cu)  # Ground plane on back copper
        zone.SetNetCode(gnd_net.GetNetCode())
        zone.SetZoneName("GND")

        # Zone corners with margin
        m = _BOARD_MARGIN * 0.5
        corners = [
            (_PAGE_OFFSET_X - m, _PAGE_OFFSET_Y - m),
            (_PAGE_OFFSET_X + width_mm + m, _PAGE_OFFSET_Y - m),
            (_PAGE_OFFSET_X + width_mm + m, _PAGE_OFFSET_Y + height_mm + m),
            (_PAGE_OFFSET_X - m, _PAGE_OFFSET_Y + height_mm + m),
        ]

        outline = zone.Outline()
        outline.NewOutline()
        for x, y in corners:
            outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))

        # Zone settings
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        zone.SetMinThickness(pcbnew.FromMM(0.2))

        board.Add(zone)

        # Note: zone fill is deferred — KiCad fills automatically when opened
        logger.info("Added GND ground plane zone on B.Cu (unfilled, fill on open)")

    def _add_board_outline(
        self, board: object, width_mm: float, height_mm: float
    ) -> None:
        """Add rectangular board edge cuts, centered on component placement area."""
        ox = _PAGE_OFFSET_X - _BOARD_MARGIN
        oy = _PAGE_OFFSET_Y - _BOARD_MARGIN
        w = width_mm + 2 * _BOARD_MARGIN
        h = height_mm + 2 * _BOARD_MARGIN
        corners = [
            (ox, oy), (ox + w, oy),
            (ox + w, oy + h), (ox, oy + h),
        ]
        for i in range(4):
            sx, sy = corners[i]
            ex, ey = corners[(i + 1) % 4]
            line = pcbnew.PCB_SHAPE(board)
            line.SetLayer(pcbnew.Edge_Cuts)
            line.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(sx), pcbnew.FromMM(sy)))
            line.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(ex), pcbnew.FromMM(ey)))
            line.SetWidth(pcbnew.FromMM(0.1))
            board.Add(line)
