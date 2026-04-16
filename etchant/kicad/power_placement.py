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
    if "led" in topology:
        return _place_led_driver(design)
    if "sensor" in topology:
        return _place_sensor_breakout(design)
    if "mcu" in topology:
        return _place_mcu_breakout(design)
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

    # Feedback resistors: below the tallest component in the row (IC or
    # inductor — whichever sticks further down) so resistor courtyards
    # don't overlap the inductor's courtyard.
    res_size = _get_footprint_size(design, resistors[0] if resistors else None)
    row_half_height = max(ic_size[1], ind_size[1]) / 2
    fb_y = cy + row_half_height + res_size[1] / 2 + _MIN_CLEARANCE + 1.0
    res_spacing = max(4.5, res_size[0] + 1.5)
    for i, ref in enumerate(resistors):
        positions[ref] = Position(cx - 1 + i * res_spacing, fb_y)

    # Diodes: below and right of IC
    for i, ref in enumerate(diodes):
        positions[ref] = Position(cx + 2, fb_y + i * 4)

    _add_power_connectors(positions, design)
    return _finalize(positions, design)


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

    _add_power_connectors(positions, design)
    return _finalize(positions, design)


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

    _add_power_connectors(positions, design)
    return _finalize(positions, design)


def _place_led_driver(design: DesignResult) -> tuple[dict[str, Position], float, float]:
    """Place LED driver in a straight line following current flow."""
    positions: dict[str, Position] = {}

    ic = _find_by_category(design, ComponentCategory.IC)
    connectors = _find_all_by_category(design, ComponentCategory.CONNECTOR)
    resistors = _find_all_by_category(design, ComponentCategory.RESISTOR)
    diodes = _find_all_by_category(design, ComponentCategory.DIODE)
    inductors = _find_all_by_category(design, ComponentCategory.INDUCTOR)
    caps = _find_all_by_category(design, ComponentCategory.CAPACITOR)

    cx = _PAGE_X + 5
    cy = _PAGE_Y + 5
    step = 5.0

    if ic:
        # Boost LED driver: Cin -> IC -> L -> D -> LED, R below
        x = cx
        for ref in connectors:
            positions[ref] = Position(x, cy)
            x += step
        if caps:
            positions[caps[0]] = Position(x, cy, 90)
            x += step
        positions[ic] = Position(x, cy)
        x += step
        for ref in inductors:
            positions[ref] = Position(x, cy)
            x += step
        for ref in diodes:
            positions[ref] = Position(x, cy)
            x += step
        # Sense resistor below IC
        for i, ref in enumerate(resistors):
            if ref not in positions:
                positions[ref] = Position(
                    positions[ic].x + i * 4.5, cy + 4,
                )
    else:
        # Simple resistor-limited: J1 -> R1 -> D1 straight line
        x = cx
        for ref in connectors:
            positions[ref] = Position(x, cy)
            x += step
        for ref in resistors:
            positions[ref] = Position(x, cy)
            x += step
        for ref in diodes:
            positions[ref] = Position(x, cy)
            x += step

    # Any remaining caps
    for ref in caps:
        if ref not in positions:
            positions[ref] = Position(cx + step, cy - 3, 90)

    return _finalize(positions, design)


def _place_sensor_breakout(
    design: DesignResult,
) -> tuple[dict[str, Position], float, float]:
    """Place I2C sensor breakout: header on left, sensor center, caps/pullups right."""
    positions: dict[str, Position] = {}

    ic = _find_by_category(design, ComponentCategory.IC)
    connectors = _find_all_by_category(design, ComponentCategory.CONNECTOR)
    caps = _find_all_by_category(design, ComponentCategory.CAPACITOR)
    resistors = _find_all_by_category(design, ComponentCategory.RESISTOR)

    ic_size = _get_footprint_size(design, ic)

    cx = _PAGE_X + 12
    cy = _PAGE_Y + 8

    # Header on left edge
    for ref in connectors:
        positions[ref] = Position(cx - 6, cy)

    # Sensor IC in center
    if ic:
        positions[ic] = Position(cx, cy)

    # Decoupling cap adjacent to IC
    if caps:
        positions[caps[0]] = Position(cx, cy - ic_size[1] / 2 - 2, 90)

    # I2C pull-ups to the right of IC, close to SCL/SDA pins
    for i, ref in enumerate(resistors):
        positions[ref] = Position(
            cx + ic_size[0] / 2 + 3,
            cy - 2 + i * 4,
        )

    return _finalize(positions, design)


def _place_mcu_breakout(
    design: DesignResult,
) -> tuple[dict[str, Position], float, float]:
    """Place MCU breakout: headers on edges, MCU center, power section nearby.

    Layout:
      J1(prog header)  |  U2(LDO) C3  |  U1(MCU)  |  J2(GPIO header)
                        |  C1 C2       |  R1 D1 R2 |
    """
    positions: dict[str, Position] = {}

    # Categorize components by reference
    comp_map = {c.reference: c for c in design.components}

    cx = _PAGE_X + 25  # MCU center
    cy = _PAGE_Y + 15

    # MCU in center
    if "U1" in comp_map:
        positions["U1"] = Position(cx, cy)

    # Programming header J1 on left edge
    if "J1" in comp_map:
        positions["J1"] = Position(cx - 18, cy)

    # GPIO header J2 on right edge
    if "J2" in comp_map:
        positions["J2"] = Position(cx + 18, cy)

    # LDO U2 between J1 and MCU
    if "U2" in comp_map:
        positions["U2"] = Position(cx - 10, cy - 4)

    # LDO input cap C3 near LDO
    if "C3" in comp_map:
        positions["C3"] = Position(cx - 13, cy - 4, 90)

    # Bulk decoupling C1 near MCU
    if "C1" in comp_map:
        positions["C1"] = Position(cx - 5, cy - 5, 90)

    # HF decoupling C2 adjacent to MCU
    if "C2" in comp_map:
        positions["C2"] = Position(cx - 3, cy - 4, 90)

    # EN pull-up R1 near MCU
    if "R1" in comp_map:
        positions["R1"] = Position(cx + 5, cy - 5)

    # LED D1 and resistor R2 below MCU
    if "D1" in comp_map:
        positions["D1"] = Position(cx + 3, cy + 7)
    if "R2" in comp_map:
        positions["R2"] = Position(cx, cy + 7)

    return _finalize(positions, design)


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


def _add_power_connectors(
    positions: dict[str, Position], design: DesignResult,
) -> None:
    """Place input/output connectors at the left/right outer envelope.

    First connector goes to the left edge of placed parts, second to the
    right edge, subsequent ones alternate. Uses outer-edge extents
    (center ± half footprint) so a wide inductor or IC body isn't
    mistaken for being inside the envelope — the first attempt at this
    used bare centers and landed J1 inside U1's courtyard.
    """
    connectors = [
        c.reference for c in design.components
        if c.category == ComponentCategory.CONNECTOR
        and c.reference not in positions
    ]
    if not connectors or not positions:
        return

    def half_extent(ref: str, pos: Position) -> tuple[float, float]:
        w, h = _get_footprint_size(design, ref)
        if pos.rotation == 90:
            return h / 2, w / 2
        return w / 2, h / 2

    lefts, rights, tops, bottoms = [], [], [], []
    for ref, pos in positions.items():
        hw, hh = half_extent(ref, pos)
        lefts.append(pos.x - hw)
        rights.append(pos.x + hw)
        tops.append(pos.y - hh)
        bottoms.append(pos.y + hh)
    min_x, max_x = min(lefts), max(rights)
    center_y = (min(tops) + max(bottoms)) / 2

    gap = 2.0
    for i, ref in enumerate(connectors):
        w, _h = _get_footprint_size(design, ref)
        if i % 2 == 0:
            x = min_x - gap - w / 2
            positions[ref] = Position(x, center_y, 0)
            min_x = x - w / 2
        else:
            x = max_x + gap + w / 2
            positions[ref] = Position(x, center_y, 0)
            max_x = x + w / 2


def _get_footprint_size(design: DesignResult, ref: str | None) -> tuple[float, float]:
    """Return real footprint bounding-box dims (inc. courtyard) or an estimate.

    Prefers pcbnew's actual dimensions via footprint_query so placements
    include the real courtyard extents — the estimated _FOOTPRINT_SIZES
    values are only used as a fallback when pcbnew isn't available or
    can't load the library.
    """
    if ref is None:
        return (3.0, 3.0)

    comp = next((c for c in design.components if c.reference == ref), None)
    if comp is None:
        return (3.0, 3.0)

    # Real footprint dims from pcbnew include silkscreen + courtyard bleed,
    # which is what we want for spacing to avoid courtyards_overlap DRC errors.
    from etchant.kicad.footprint_query import get_footprint_dimensions
    info = get_footprint_dimensions(comp.footprint)
    if info.width_mm > 0 and info.height_mm > 0:
        return (info.width_mm, info.height_mm)

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
    design: DesignResult | None = None,
) -> tuple[dict[str, Position], float, float]:
    """Size the board from component outer edges, not centers.

    Earlier versions sized via span_between_centers + 2*margin, which
    overinflated the board because a component at min_x actually extends
    half its width further out — on top of the margin. Pin headers on
    breakout boards need to sit AT the physical edge for breadboard use,
    not 8mm inside it.
    """
    if not positions:
        return positions, 10.0, 10.0

    # Look up each component's footprint dims and project into the same
    # rotation frame as its Position (swap w/h when rot=90). Fall back to
    # a small default if design wasn't threaded in (shouldn't happen in
    # practice — all call sites pass design now).
    def half_extent(ref: str, pos: Position) -> tuple[float, float]:
        if design is None:
            return 1.5, 1.5
        w, h = _get_footprint_size(design, ref)
        if pos.rotation == 90:
            return h / 2, w / 2
        return w / 2, h / 2

    lefts, rights, tops, bottoms = [], [], [], []
    for ref, pos in positions.items():
        hw, hh = half_extent(ref, pos)
        lefts.append(pos.x - hw)
        rights.append(pos.x + hw)
        tops.append(pos.y - hh)
        bottoms.append(pos.y + hh)

    envelope_x = (min(lefts), max(rights))
    envelope_y = (min(tops), max(bottoms))
    envelope_w = envelope_x[1] - envelope_x[0]
    envelope_h = envelope_y[1] - envelope_y[0]

    # 2mm edge margin = 0.5mm JLCPCB copper-to-edge + silk + mech tolerance.
    margin = 2.0
    board_w = max(10.0, envelope_w + 2 * margin)
    board_h = max(10.0, envelope_h + 2 * margin)

    envelope_center_x = (envelope_x[0] + envelope_x[1]) / 2
    envelope_center_y = (envelope_y[0] + envelope_y[1]) / 2
    target_x = _PAGE_X + board_w / 2
    target_y = _PAGE_Y + board_h / 2
    shift_x = target_x - envelope_center_x
    shift_y = target_y - envelope_center_y

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
