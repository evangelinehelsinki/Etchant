"""Constraint-driven component placement for power supply circuits.

Places components following the power flow path using constraints from
the DesignResult's PlacementConstraint objects and footprint dimensions.
No more magic numbers — spacing is computed from actual data.

Topology flow patterns:
  Buck:  Cin -> IC -> L -> Cout  (minimize hot loop area)
  LDO:   Cin -> IC -> Cout       (tight vertical)
  Boost: Cin -> L -> IC -> D -> Cout
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from etchant.core.models import ComponentCategory, DesignResult

logger = logging.getLogger(__name__)

_PAGE_X = 100.0
_PAGE_Y = 100.0

# Estimated footprint widths (mm) by pattern — used when pcbnew isn't available
_FOOTPRINT_SIZES: dict[str, tuple[float, float]] = {
    "SOT-223": (6.5, 7.0),
    "SOT-563": (1.8, 1.6),
    "SOT-23": (3.0, 3.0),
    "0805": (2.0, 1.3),
    "0603": (1.6, 0.8),
    "0402": (1.0, 0.5),
    "R_0805": (2.0, 1.3),
    "C_0805": (2.0, 1.3),
    "SMA": (5.0, 2.6),
    "D_SMA": (5.0, 2.6),
    "IHLP-2525": (7.0, 7.0),
    "TO-263": (10.0, 15.0),
    "DO-201": (5.0, 18.0),
}

# Minimum clearance between component edges (mm)
_MIN_CLEARANCE = 1.0


@dataclass
class Position:
    x: float
    y: float
    rotation: float = 0.0


def calculate_power_placement(
    design: DesignResult,
) -> tuple[dict[str, Position], float, float]:
    """Calculate constraint-driven component positions.

    Uses PlacementConstraint preferred distances and footprint sizes
    to compute spacing. Falls back to sensible defaults.
    """
    topology = design.spec.topology

    if "buck" in topology:
        return _place_buck(design)
    if "ldo" in topology:
        return _place_ldo(design)
    if "boost" in topology:
        return _place_boost(design)
    return _place_grid(design)


def _place_buck(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Place buck converter: Cin -> IC -> L -> Cout, feedback below."""
    positions: dict[str, Position] = {}

    ic = _find_by_category(design, ComponentCategory.IC)
    caps = _find_all_by_category(design, ComponentCategory.CAPACITOR)
    inductors = _find_all_by_category(design, ComponentCategory.INDUCTOR)
    resistors = _find_all_by_category(design, ComponentCategory.RESISTOR)
    diodes = _find_all_by_category(design, ComponentCategory.DIODE)

    c_in = caps[0] if caps else None
    c_out = caps[1] if len(caps) > 1 else None
    inductor = inductors[0] if inductors else None

    # Get spacing from constraints and footprint sizes
    ic_size = _get_footprint_size(design, ic)
    cap_size = _get_footprint_size(design, c_in)
    ind_size = _get_footprint_size(design, inductor)

    # Spacing: half of each component + clearance
    cin_to_ic = (cap_size[0] / 2 + ic_size[0] / 2 + _MIN_CLEARANCE)
    ic_to_ind = (ic_size[0] / 2 + ind_size[0] / 2 + _MIN_CLEARANCE)
    ind_to_cout = (ind_size[0] / 2 + cap_size[0] / 2 + _MIN_CLEARANCE)

    # Override with constraint preferred distances if available
    cin_to_ic = _get_constraint_distance(design, c_in, cin_to_ic)
    ic_to_ind = _get_constraint_distance(design, inductor, ic_to_ind)

    # Place left to right: Cin -> IC -> L -> Cout
    cx = _PAGE_X + cin_to_ic + 3  # IC position
    cy = _PAGE_Y + max(ic_size[1], ind_size[1]) / 2 + 5

    if ic:
        positions[ic] = Position(cx, cy)
    if c_in:
        positions[c_in] = Position(cx - cin_to_ic, cy - 1, 90)
    if inductor:
        positions[inductor] = Position(cx + ic_to_ind, cy)
    if c_out:
        lx = cx + ic_to_ind if inductor else cx + 6
        positions[c_out] = Position(lx + ind_to_cout, cy - 1, 90)

    # Feedback resistors: below IC, near FB pin (4.5mm spacing for 0805 courtyards)
    res_size = _get_footprint_size(design, resistors[0] if resistors else None)
    fb_y = cy + ic_size[1] / 2 + res_size[1] / 2 + 2.0
    res_spacing = max(4.5, res_size[0] + 1.5)
    for i, ref in enumerate(resistors):
        positions[ref] = Position(cx - 1 + i * res_spacing, fb_y)

    # Diodes: below and right of IC
    for i, ref in enumerate(diodes):
        positions[ref] = Position(cx + 2, fb_y + i * 4)

    return _finalize(positions)


def _place_ldo(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Place LDO: Cin -> IC -> Cout vertical, feedback to side."""
    positions: dict[str, Position] = {}

    ic = _find_by_category(design, ComponentCategory.IC)
    caps = _find_all_by_category(design, ComponentCategory.CAPACITOR)
    resistors = _find_all_by_category(design, ComponentCategory.RESISTOR)

    c_in = caps[0] if caps else None
    c_out = caps[1] if len(caps) > 1 else None

    ic_size = _get_footprint_size(design, ic)
    cap_size = _get_footprint_size(design, c_in)

    # Vertical spacing: cap adjacent to IC pin
    cap_to_ic = (cap_size[1] / 2 + ic_size[1] / 2 + _MIN_CLEARANCE)
    cap_to_ic = _get_constraint_distance(design, c_in, cap_to_ic)

    # Cap offset: place caps adjacent to IC pins using actual dimensions
    cap_offset_x = ic_size[0] / 2 + cap_size[0] / 2 + 0.5

    cx = _PAGE_X + 10
    cy = _PAGE_Y + cap_to_ic + 5

    if c_in:
        positions[c_in] = Position(cx + cap_offset_x, cy - cap_to_ic, 90)
    if ic:
        positions[ic] = Position(cx, cy)
    if c_out:
        positions[c_out] = Position(cx + cap_offset_x, cy + cap_to_ic, 90)

    # Feedback resistors to the right
    res_size = _get_footprint_size(design, resistors[0] if resistors else None)
    for i, ref in enumerate(resistors):
        positions[ref] = Position(
            cx + ic_size[0] / 2 + res_size[0] / 2 + 2,
            cy - 1 + i * max(4.5, res_size[1] + 1.5),
        )

    return _finalize(positions)


def _place_boost(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Place boost: Cin -> L -> IC -> D -> Cout."""
    positions: dict[str, Position] = {}

    ic = _find_by_category(design, ComponentCategory.IC)
    caps = _find_all_by_category(design, ComponentCategory.CAPACITOR)
    inductors = _find_all_by_category(design, ComponentCategory.INDUCTOR)
    resistors = _find_all_by_category(design, ComponentCategory.RESISTOR)
    diodes = _find_all_by_category(design, ComponentCategory.DIODE)

    c_in = caps[0] if caps else None
    c_out = caps[1] if len(caps) > 1 else None
    inductor = inductors[0] if inductors else None
    diode = diodes[0] if diodes else None

    ic_size = _get_footprint_size(design, ic)
    spacing = 4.0  # Base spacing between components

    cx = _PAGE_X + 18
    cy = _PAGE_Y + 10

    if c_in:
        positions[c_in] = Position(cx - 3 * spacing, cy - 1, 90)
    if inductor:
        positions[inductor] = Position(cx - 1.5 * spacing, cy)
    if ic:
        positions[ic] = Position(cx, cy)
    if diode:
        positions[diode] = Position(cx + 1.5 * spacing, cy)
    if c_out:
        positions[c_out] = Position(cx + 3 * spacing, cy - 1, 90)

    fb_y = cy + ic_size[1] / 2 + 3
    for i, ref in enumerate(resistors):
        positions[ref] = Position(cx - 1 + i * 3.5, fb_y)

    return _finalize(positions)


def _place_grid(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Fallback grid placement."""
    positions: dict[str, Position] = {}
    cols = 3
    spacing = 6.0
    for i, comp in enumerate(design.components):
        positions[comp.reference] = Position(
            _PAGE_X + 5 + (i % cols) * spacing,
            _PAGE_Y + 5 + (i // cols) * spacing,
        )
    n = len(design.components)
    return positions, max(20.0, (cols + 1) * spacing), max(15.0, ((n // cols) + 2) * spacing)


def _get_footprint_size(design: DesignResult, ref: str | None) -> tuple[float, float]:
    """Estimate footprint width/height in mm from the footprint name."""
    if ref is None:
        return (3.0, 3.0)

    comp = next((c for c in design.components if c.reference == ref), None)
    if comp is None:
        return (3.0, 3.0)

    fp = comp.footprint
    for pattern, size in _FOOTPRINT_SIZES.items():
        if pattern in fp:
            return size

    return (3.0, 3.0)


def _get_constraint_distance(
    design: DesignResult, ref: str | None, default: float,
) -> float:
    """Get preferred placement distance from design constraints."""
    if ref is None:
        return default

    for pc in design.placement_constraints:
        if pc.component_ref == ref:
            # Use preferred distance, bounded by component clearance
            return max(default, pc.max_distance_mm * 0.4)

    return default


def _finalize(
    positions: dict[str, Position],
    max_footprint_extent: float = 8.0,
) -> tuple[dict[str, Position], float, float]:
    """Calculate board size accounting for footprint extents, not just centers."""
    if not positions:
        return positions, 35.0, 30.0

    all_x = [p.x for p in positions.values()]
    all_y = [p.y for p in positions.values()]

    # Margin = half largest footprint + routing space + board edge clearance
    # max_footprint_extent covers half the largest component body
    margin = max_footprint_extent + 5.0  # 5mm routing + edge clearance

    span_x = max(all_x) - min(all_x)
    span_y = max(all_y) - min(all_y)

    board_w = max(30.0, span_x + 2 * margin)
    board_h = max(25.0, span_y + 2 * margin)

    # Center components on board
    center_x = (max(all_x) + min(all_x)) / 2
    center_y = (max(all_y) + min(all_y)) / 2
    target_x = _PAGE_X + board_w / 2
    target_y = _PAGE_Y + board_h / 2
    shift_x = target_x - center_x
    shift_y = target_y - center_y

    final = {
        ref: Position(p.x + shift_x, p.y + shift_y, p.rotation)
        for ref, p in positions.items()
    }

    return final, board_w, board_h


def _find_by_category(design: DesignResult, category: ComponentCategory) -> str | None:
    for comp in design.components:
        if comp.category == category:
            return comp.reference
    return None


def _find_all_by_category(
    design: DesignResult, category: ComponentCategory,
) -> list[str]:
    return [c.reference for c in design.components if c.category == category]
