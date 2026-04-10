"""Topology-aware component placement for power supply circuits.

Places components following the power flow path to minimize current
loop area and EMI. Each topology has a specific placement strategy:

Buck converter flow: Cin -> IC -> L -> Cout (tight hot loop)
  - Input cap adjacent to IC VIN pin
  - Inductor adjacent to IC SW pin
  - Output cap adjacent to inductor output
  - Feedback divider near IC FB pin
  - Minimize the Cin-IC-L-D loop area (the "hot loop")

LDO flow: Cin -> IC -> Cout
  - Input cap touching IC input pin
  - Output cap touching IC output pin
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from etchant.core.models import ComponentCategory, DesignResult

logger = logging.getLogger(__name__)

# Page offset for KiCad
_PAGE_X = 100.0
_PAGE_Y = 100.0
_BOARD_MARGIN = 3.0


@dataclass
class Position:
    x: float
    y: float
    rotation: float = 0.0


def calculate_power_placement(
    design: DesignResult,
) -> tuple[dict[str, Position], float, float]:
    """Calculate topology-aware component positions.

    Returns (positions_dict, board_width, board_height).
    """
    topology = design.spec.topology

    if "buck" in topology:
        return _place_buck(design)
    if "ldo" in topology:
        return _place_ldo(design)
    if "boost" in topology:
        return _place_boost(design)

    # Fallback: simple grid
    return _place_grid(design)


def _place_buck(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Place buck converter following power flow.

    Layout (power flows left to right):
        C1(in) -- U1(IC) -- L1 -- C2(out)
                    |
                  R1/R2 (feedback, below IC)
    """
    positions: dict[str, Position] = {}

    # Find components by function
    ic = _find_by_category(design, ComponentCategory.IC)
    caps = _find_all_by_category(design, ComponentCategory.CAPACITOR)
    inductors = _find_all_by_category(design, ComponentCategory.INDUCTOR)
    resistors = _find_all_by_category(design, ComponentCategory.RESISTOR)
    diodes = _find_all_by_category(design, ComponentCategory.DIODE)

    # Identify input cap (C1) and output cap (C2) from net connections
    c_in = caps[0] if caps else None
    c_out = caps[1] if len(caps) > 1 else None
    inductor = inductors[0] if inductors else None

    # Component spacing (mm)
    ic_to_cap = 3.5    # Caps right next to IC pins
    ic_to_inductor = 5.0
    cap_to_inductor = 3.0

    # IC in center
    cx = _PAGE_X + 15
    cy = _PAGE_Y + 12

    if ic:
        positions[ic] = Position(cx, cy)

    # Input cap: LEFT of IC (adjacent to VIN pin)
    if c_in:
        positions[c_in] = Position(cx - ic_to_cap - 2, cy - 2, 90)

    # Inductor: RIGHT of IC (adjacent to SW pin)
    if inductor:
        positions[inductor] = Position(cx + ic_to_inductor + 2, cy)

    # Output cap: RIGHT of inductor (at output)
    if c_out:
        lx = positions[inductor].x if inductor else cx + 8
        positions[c_out] = Position(lx + cap_to_inductor + 2, cy - 2, 90)

    # Feedback resistors: BELOW IC, near FB pin
    for i, ref in enumerate(resistors):
        positions[ref] = Position(cx - 2 + i * 4, cy + 5)

    # Diodes: BELOW IC, near SW node
    for i, ref in enumerate(diodes):
        positions[ref] = Position(cx + 3, cy + 5 + i * 4)

    # Calculate board size to fit all components
    all_x = [p.x - _PAGE_X for p in positions.values()]
    all_y = [p.y - _PAGE_Y for p in positions.values()]
    board_w = max(all_x) - min(all_x) + 12  # margin
    board_h = max(all_y) - min(all_y) + 12

    return positions, board_w, board_h


def _place_ldo(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Place LDO following power flow.

    Layout (tight vertical arrangement):
        C1(in)
          |
        U1(IC)
          |
        C2(out)
        R1/R2 (feedback, if adjustable)
    """
    positions: dict[str, Position] = {}

    ic = _find_by_category(design, ComponentCategory.IC)
    caps = _find_all_by_category(design, ComponentCategory.CAPACITOR)
    resistors = _find_all_by_category(design, ComponentCategory.RESISTOR)

    c_in = caps[0] if caps else None
    c_out = caps[1] if len(caps) > 1 else None

    cx = _PAGE_X + 10
    cy = _PAGE_Y + 10

    # Input cap: above IC, adjacent to input pin (with clearance)
    if c_in:
        positions[c_in] = Position(cx + 4, cy - 5, 90)

    # IC in center
    if ic:
        positions[ic] = Position(cx, cy)

    # Output cap: below IC, adjacent to output pin (with clearance)
    if c_out:
        positions[c_out] = Position(cx + 4, cy + 6, 90)

    # Feedback resistors: to the right, near adjust pin
    for i, ref in enumerate(resistors):
        positions[ref] = Position(cx + 6, cy + 1 + i * 3)

    board_w = 20.0
    board_h = 16.0

    return positions, board_w, board_h


def _place_boost(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Place boost converter following power flow.

    Layout: C1(in) -- L1 -- U1(IC) -- D1 -- C2(out)
                              |
                            R1/R2 (feedback)
    """
    positions: dict[str, Position] = {}

    ic = _find_by_category(design, ComponentCategory.IC)
    caps = _find_all_by_category(design, ComponentCategory.CAPACITOR)
    inductors = _find_all_by_category(design, ComponentCategory.INDUCTOR)
    resistors = _find_all_by_category(design, ComponentCategory.RESISTOR)
    diodes = _find_all_by_category(design, ComponentCategory.DIODE)

    cx = _PAGE_X + 18
    cy = _PAGE_Y + 12

    c_in = caps[0] if caps else None
    c_out = caps[1] if len(caps) > 1 else None
    inductor = inductors[0] if inductors else None
    diode = diodes[0] if diodes else None

    # Boost: inductor on input side
    if c_in:
        positions[c_in] = Position(cx - 12, cy - 2, 90)
    if inductor:
        positions[inductor] = Position(cx - 6, cy)
    if ic:
        positions[ic] = Position(cx, cy)
    if diode:
        positions[diode] = Position(cx + 5, cy)
    if c_out:
        positions[c_out] = Position(cx + 10, cy - 2, 90)

    for i, ref in enumerate(resistors):
        positions[ref] = Position(cx - 1 + i * 4, cy + 5)

    board_w = 32.0
    board_h = 20.0

    return positions, board_w, board_h


def _place_grid(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Fallback: simple grid placement."""
    positions: dict[str, Position] = {}
    n = len(design.components)
    cols = 3
    spacing = 6.0

    for i, comp in enumerate(design.components):
        row = i // cols
        col = i % cols
        positions[comp.reference] = Position(
            _PAGE_X + 5 + col * spacing,
            _PAGE_Y + 5 + row * spacing,
        )

    board_w = max(20.0, (cols + 1) * spacing)
    board_h = max(15.0, ((n // cols) + 2) * spacing)

    return positions, board_w, board_h


def _find_by_category(design: DesignResult, category: ComponentCategory) -> str | None:
    for comp in design.components:
        if comp.category == category:
            return comp.reference
    return None


def _find_all_by_category(
    design: DesignResult, category: ComponentCategory,
) -> list[str]:
    return [c.reference for c in design.components if c.category == category]
