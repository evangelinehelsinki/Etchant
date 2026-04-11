"""Generic constraint-driven component placer.

Places components using actual footprint dimensions and the design's
PlacementConstraint objects. No per-topology hardcoding — works for
any circuit by following the constraint graph.

Strategy:
1. Place the primary IC (or largest component) in the center
2. Place constrained components at their preferred distances from
   their target, outside the target's bounding box
3. Place remaining components in empty space
4. Connectors go to board edges

All positions account for actual footprint dimensions to prevent
courtyard overlaps.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from etchant.core.models import ComponentCategory, DesignResult
from etchant.kicad.footprint_query import FootprintInfo, get_footprint_dimensions

logger = logging.getLogger(__name__)

_PAGE_X = 100.0
_PAGE_Y = 100.0
_EDGE_CLEARANCE = 2.0  # mm from board edge to component


@dataclass
class PlacedComponent:
    x: float
    y: float
    rotation: float
    width: float
    height: float


def constraint_place(
    design: DesignResult,
) -> tuple[dict[str, tuple[float, float, float]], float, float]:
    """Place all components using constraints and real footprint dimensions.

    Returns (positions_dict, board_width, board_height).
    positions_dict maps ref -> (x_mm, y_mm, rotation_deg) in page coords.
    """
    placed: dict[str, PlacedComponent] = {}

    # Get footprint dimensions for all components
    fp_dims: dict[str, FootprintInfo] = {}
    for comp in design.components:
        fp_dims[comp.reference] = get_footprint_dimensions(comp.footprint)

    # Step 1: Find and place the primary IC (largest one) at center
    primary_ic = _find_primary_ic(design, fp_dims)
    if primary_ic:
        dims = fp_dims[primary_ic]
        placed[primary_ic] = PlacedComponent(0, 0, 0, dims.width_mm, dims.height_mm)

    # Step 2: Place secondary ICs (e.g., LDO on an MCU board)
    for comp in design.components:
        if comp.category == ComponentCategory.IC and comp.reference not in placed:
            # Place secondary ICs adjacent to the primary, preferring left side
            # (power section typically left of main IC)
            if primary_ic and primary_ic in placed:
                _place_adjacent(
                    comp.reference, primary_ic, 15.0,
                    placed, fp_dims,
                )
            else:
                dims = fp_dims[comp.reference]
                placed[comp.reference] = PlacedComponent(
                    -15, 0, 0, dims.width_mm, dims.height_mm,
                )

    # Step 3: Place constrained components relative to their targets
    # Sort by distance constraint (tightest first for best placement)
    sorted_constraints = sorted(
        design.placement_constraints,
        key=lambda pc: pc.max_distance_mm,
    )
    for pc in sorted_constraints:
        ref = pc.component_ref
        if ref in placed or ref not in fp_dims:
            continue

        target = pc.target_ref
        if target and target in placed:
            _place_adjacent(
                ref, target, pc.max_distance_mm,
                placed, fp_dims,
            )

    # Step 4: Place connectors at board edges
    for comp in design.components:
        if comp.category == ComponentCategory.CONNECTOR and comp.reference not in placed:
            _place_at_edge(comp.reference, placed, fp_dims, design)

    # Step 5: Place remaining components near their most-connected neighbor
    # (Ott: minimize loop area by placing connected components close)
    net_neighbors = _build_net_neighbors(design)
    for comp in design.components:
        if comp.reference not in placed:
            _place_near_neighbor(
                comp.reference, placed, fp_dims, net_neighbors,
            )

    # Step 5: Calculate board size and convert to page coordinates
    return _to_page_coords(placed)


def _find_primary_ic(
    design: DesignResult, fp_dims: dict[str, FootprintInfo],
) -> str | None:
    """Find the primary IC (largest footprint area among ICs)."""
    best_ref = None
    best_area = 0
    for comp in design.components:
        if comp.category == ComponentCategory.IC:
            dims = fp_dims[comp.reference]
            area = dims.width_mm * dims.height_mm
            if area > best_area:
                best_area = area
                best_ref = comp.reference
    return best_ref


def _place_adjacent(
    ref: str,
    target_ref: str,
    max_distance_mm: float,
    placed: dict[str, PlacedComponent],
    fp_dims: dict[str, FootprintInfo],
) -> None:
    """Place a component adjacent to its target, outside the target's bbox."""
    target = placed[target_ref]
    dims = fp_dims[ref]

    # Try positions around the target: right, above, below, left
    # Distance from target edge to component edge
    gap = min(max_distance_mm * 0.3, 3.0)  # Prefer close placement

    candidates = [
        # Right of target
        (
            target.x + target.width / 2 + dims.width_mm / 2 + gap,
            target.y,
            0,
        ),
        # Above target
        (
            target.x,
            target.y - target.height / 2 - dims.height_mm / 2 - gap,
            90,
        ),
        # Below target
        (
            target.x,
            target.y + target.height / 2 + dims.height_mm / 2 + gap,
            90,
        ),
        # Left of target
        (
            target.x - target.width / 2 - dims.width_mm / 2 - gap,
            target.y,
            0,
        ),
    ]

    # Pick the first position that doesn't overlap existing components
    for cx, cy, rot in candidates:
        w = dims.height_mm if rot == 90 else dims.width_mm
        h = dims.width_mm if rot == 90 else dims.height_mm
        if not _overlaps_any(cx, cy, w, h, placed):
            placed[ref] = PlacedComponent(cx, cy, rot, w, h)
            return

    # Fallback: place to the right with more distance
    cx = target.x + target.width / 2 + dims.width_mm / 2 + max_distance_mm * 0.5
    cy = target.y
    placed[ref] = PlacedComponent(cx, cy, 0, dims.width_mm, dims.height_mm)


def _place_at_edge(
    ref: str,
    placed: dict[str, PlacedComponent],
    fp_dims: dict[str, FootprintInfo],
    design: DesignResult,
) -> None:
    """Place a connector at the board edge."""
    dims = fp_dims[ref]

    # Determine which edge based on net connections
    # Connectors with power nets go left, signal nets go right
    all_x = [p.x for p in placed.values()] if placed else [0]
    min_x = min(all_x)
    max_x = max(all_x)

    # First connector goes left, second goes right
    connector_count = sum(
        1 for r, p in placed.items()
        if any(
            c.category == ComponentCategory.CONNECTOR and c.reference == r
            for c in design.components
        )
    )

    if connector_count == 0:
        # Left edge
        cx = min_x - 10
        cy = 0
    else:
        # Right edge
        cx = max_x + 10
        cy = 0

    placed[ref] = PlacedComponent(cx, cy, 0, dims.width_mm, dims.height_mm)


def _build_net_neighbors(
    design: DesignResult,
) -> dict[str, list[str]]:
    """Build a map of component -> list of components sharing nets, ranked by connection count."""
    # Count shared nets between each pair of components
    shared: dict[tuple[str, str], int] = {}
    for net in design.nets:
        refs_in_net = [ref for ref, _pin in net.connections]
        for i, r1 in enumerate(refs_in_net):
            for r2 in refs_in_net[i + 1:]:
                key = (min(r1, r2), max(r1, r2))
                shared[key] = shared.get(key, 0) + 1

    # Build neighbor list sorted by connection count (most connected first)
    neighbors: dict[str, list[str]] = {}
    all_refs = {c.reference for c in design.components}
    for ref in all_refs:
        ref_neighbors = []
        for (r1, r2), count in shared.items():
            if r1 == ref:
                ref_neighbors.append((r2, count))
            elif r2 == ref:
                ref_neighbors.append((r1, count))
        ref_neighbors.sort(key=lambda x: -x[1])
        neighbors[ref] = [r for r, _ in ref_neighbors]

    return neighbors


def _place_near_neighbor(
    ref: str,
    placed: dict[str, PlacedComponent],
    fp_dims: dict[str, FootprintInfo],
    net_neighbors: dict[str, list[str]],
) -> None:
    """Place a component near its most-connected already-placed neighbor."""
    dims = fp_dims[ref]

    # Find the best placed neighbor
    best_neighbor = None
    for neighbor_ref in net_neighbors.get(ref, []):
        if neighbor_ref in placed:
            best_neighbor = placed[neighbor_ref]
            break

    if best_neighbor is not None:
        # Place adjacent to the best neighbor
        gap = 2.0
        candidates = [
            (best_neighbor.x + best_neighbor.width / 2 + dims.width_mm / 2 + gap,
             best_neighbor.y, 0),
            (best_neighbor.x,
             best_neighbor.y + best_neighbor.height / 2 + dims.height_mm / 2 + gap, 0),
            (best_neighbor.x - best_neighbor.width / 2 - dims.width_mm / 2 - gap,
             best_neighbor.y, 0),
            (best_neighbor.x,
             best_neighbor.y - best_neighbor.height / 2 - dims.height_mm / 2 - gap, 0),
        ]
        for cx, cy, rot in candidates:
            if not _overlaps_any(cx, cy, dims.width_mm, dims.height_mm, placed):
                placed[ref] = PlacedComponent(cx, cy, rot, dims.width_mm, dims.height_mm)
                return

    # Fallback: spiral search from center
    for radius in range(3, 30, 3):
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            cx = radius * math.cos(rad)
            cy = radius * math.sin(rad)
            if not _overlaps_any(cx, cy, dims.width_mm, dims.height_mm, placed):
                placed[ref] = PlacedComponent(cx, cy, 0, dims.width_mm, dims.height_mm)
                return

    placed[ref] = PlacedComponent(20, 0, 0, dims.width_mm, dims.height_mm)


def _overlaps_any(
    x: float, y: float, w: float, h: float,
    placed: dict[str, PlacedComponent],
) -> bool:
    """Check if a rectangle overlaps any placed component."""
    return any(
        _rects_overlap(x, y, w, h, p.x, p.y, p.width, p.height)
        for p in placed.values()
    )


def _rects_overlap(
    x1: float, y1: float, w1: float, h1: float,
    x2: float, y2: float, w2: float, h2: float,
    margin: float = 1.0,
) -> bool:
    """Check if two center-origin rectangles overlap (with margin)."""
    return (
        abs(x1 - x2) < (w1 + w2) / 2 + margin
        and abs(y1 - y2) < (h1 + h2) / 2 + margin
    )


def _to_page_coords(
    placed: dict[str, PlacedComponent],
) -> tuple[dict[str, tuple[float, float, float]], float, float]:
    """Convert relative coords to page coords and compute board size."""
    if not placed:
        return {}, 30.0, 25.0

    # Find extents including component dimensions
    min_x = min(p.x - p.width / 2 for p in placed.values())
    max_x = max(p.x + p.width / 2 for p in placed.values())
    min_y = min(p.y - p.height / 2 for p in placed.values())
    max_y = max(p.y + p.height / 2 for p in placed.values())

    board_w = max_x - min_x + 2 * (_EDGE_CLEARANCE + 2)
    board_h = max_y - min_y + 2 * (_EDGE_CLEARANCE + 2)

    # Minimum board sizes
    board_w = max(15.0, board_w)
    board_h = max(13.0, board_h)

    # Shift so components are centered on the board
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    offset_x = _PAGE_X + board_w / 2 - center_x
    offset_y = _PAGE_Y + board_h / 2 - center_y

    positions = {
        ref: (p.x + offset_x, p.y + offset_y, p.rotation)
        for ref, p in placed.items()
    }

    return positions, board_w, board_h
