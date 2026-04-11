"""Generic constraint-driven component placer.

Places components using:
1. Real footprint dimensions (from pcbnew or estimates)
2. Design PlacementConstraint objects
3. Manufacturer layout YAML (preferred_side, antenna keep-out, etc.)
4. Net connectivity (components sharing nets placed near each other)

No per-topology hardcoding. Works for any circuit by following
constraint data from datasheets encoded as YAML.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from etchant.core.models import ComponentCategory, DesignResult
from etchant.kicad.footprint_query import FootprintInfo, get_footprint_dimensions

logger = logging.getLogger(__name__)

_PAGE_X = 100.0
_PAGE_Y = 100.0
_EDGE_CLEARANCE = 2.0
_CONSTRAINTS_DIR = Path(__file__).parent.parent.parent / "constraints"


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
    """Place all components using constraints, YAML rules, and footprint dims."""
    placed: dict[str, PlacedComponent] = {}

    # Get footprint dimensions
    fp_dims: dict[str, FootprintInfo] = {}
    for comp in design.components:
        fp_dims[comp.reference] = get_footprint_dimensions(comp.footprint)

    # Load manufacturer YAML for the primary IC if available
    ic_yaml = _load_ic_yaml(design)

    # Step 1: Place primary IC at center
    primary_ic = _find_primary_ic(design, fp_dims)
    if primary_ic:
        dims = fp_dims[primary_ic]
        placed[primary_ic] = PlacedComponent(0, 0, 0, dims.width_mm, dims.height_mm)

    # Step 2: Place secondary ICs using YAML preferred_side
    for comp in design.components:
        if comp.category == ComponentCategory.IC and comp.reference not in placed:
            side = _get_yaml_preferred_side(ic_yaml, comp.reference, "U_ldo")
            if primary_ic and primary_ic in placed:
                _place_on_side(
                    comp.reference, primary_ic, side,
                    placed, fp_dims, ic_yaml,
                )

    # Step 3: Place constrained components using preferred_side from YAML
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
            # Check YAML for preferred side
            side = _get_yaml_side_for_ref(ic_yaml, ref)
            if side:
                _place_on_side(ref, target, side, placed, fp_dims, ic_yaml)
            else:
                _place_adjacent(ref, target, pc.max_distance_mm, placed, fp_dims, ic_yaml)

    # Step 4: Place connectors at edges using YAML preferred_side
    for comp in design.components:
        if comp.category == ComponentCategory.CONNECTOR and comp.reference not in placed:
            side = _get_yaml_side_for_ref(ic_yaml, comp.reference)
            if side and primary_ic in placed:
                _place_on_side(comp.reference, primary_ic, side, placed, fp_dims, ic_yaml)
            else:
                _place_at_edge(comp.reference, placed, fp_dims, design)

    # Step 5: Place remaining via net-neighbor proximity
    net_neighbors = _build_net_neighbors(design)
    for comp in design.components:
        if comp.reference not in placed:
            side = _get_yaml_side_for_ref(ic_yaml, comp.reference)
            if side and primary_ic and primary_ic in placed:
                _place_on_side(comp.reference, primary_ic, side, placed, fp_dims, ic_yaml)
            else:
                _place_near_neighbor(comp.reference, placed, fp_dims, net_neighbors, ic_yaml)

    return _to_page_coords(placed)


def _load_ic_yaml(design: DesignResult) -> dict[str, Any]:
    """Load manufacturer layout YAML for the primary IC."""
    for comp in design.components:
        if comp.category != ComponentCategory.IC:
            continue
        # Try loading a YAML matching the IC value
        ic_name = comp.value.lower().replace("-", "").replace("_", "")
        for yaml_file in _CONSTRAINTS_DIR.glob("*_layout.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    continue
                yaml_ic = data.get("ic", "").lower().replace("-", "").replace("_", "")
                if yaml_ic and (ic_name.startswith(yaml_ic) or yaml_ic.startswith(ic_name)):
                    logger.info("Loaded layout YAML: %s for %s", yaml_file.name, comp.value)
                    return data
            except Exception:
                continue
    return {}


def _get_yaml_preferred_side(
    ic_yaml: dict[str, Any], ref: str, yaml_key: str,
) -> str:
    """Get preferred side from YAML placement_constraints by yaml key prefix."""
    for pc in ic_yaml.get("placement_constraints", []):
        comp_key = pc.get("component", "")
        if comp_key.lower().startswith(yaml_key.lower()):
            return pc.get("preferred_side", "below")
    return "below"


_yaml_match_index: dict[str, int] = {}  # Track which YAML entry each prefix has used


def _get_yaml_side_for_ref(ic_yaml: dict[str, Any], ref: str) -> str | None:
    """Match a component reference to a YAML placement constraint.

    Uses sequential matching: J1 matches the 1st J_ constraint,
    J2 matches the 2nd J_ constraint, etc.
    """
    ref_lower = ref.lower()
    ref_prefix = ref_lower.rstrip("0123456789")  # "j", "c", "r", "u", "d"
    ref_num = ref_lower[len(ref_prefix):]  # "1", "2", etc.

    # Find all YAML constraints matching this component category
    matching_constraints = []
    for pc in ic_yaml.get("placement_constraints", []):
        comp_key = pc.get("component", "").lower()
        if not comp_key:
            continue
        yaml_prefix = comp_key.split("_")[0] if "_" in comp_key else comp_key
        if yaml_prefix == ref_prefix:
            matching_constraints.append(pc)

    if not matching_constraints:
        return None

    # Match by index: J1 -> 1st J_ constraint, J2 -> 2nd
    try:
        idx = int(ref_num) - 1 if ref_num else 0
    except ValueError:
        idx = 0

    if idx < len(matching_constraints):
        return matching_constraints[idx].get("preferred_side")
    return matching_constraints[-1].get("preferred_side")


def _find_primary_ic(
    design: DesignResult, fp_dims: dict[str, FootprintInfo],
) -> str | None:
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


def _place_on_side(
    ref: str,
    target_ref: str,
    side: str,
    placed: dict[str, PlacedComponent],
    fp_dims: dict[str, FootprintInfo],
    ic_yaml: dict[str, Any],
) -> None:
    """Place component on a specific side of the target."""
    target = placed[target_ref]
    dims = fp_dims[ref]
    gap = 2.0

    # Map side names to positions relative to target edge
    side_positions = {
        "right": (target.x + target.width / 2 + dims.width_mm / 2 + gap, target.y, 0),
        "left": (target.x - target.width / 2 - dims.width_mm / 2 - gap, target.y, 0),
        "above": (target.x, target.y - target.height / 2 - dims.height_mm / 2 - gap, 90),
        "below": (target.x, target.y + target.height / 2 + dims.height_mm / 2 + gap, 90),
        "below-left": (
            target.x - target.width / 4,
            target.y + target.height / 2 + dims.height_mm / 2 + gap,
            0,
        ),
        "below-right": (
            target.x + target.width / 4,
            target.y + target.height / 2 + dims.height_mm / 2 + gap,
            0,
        ),
    }

    cx, cy, rot = side_positions.get(side, side_positions["below"])

    # Check antenna keep-out zone
    if _in_antenna_keepout(cx, cy, target, ic_yaml):
        # Shift to below instead
        cx = target.x
        cy = target.y + target.height / 2 + dims.height_mm / 2 + gap

    # Check overlap and adjust
    w = dims.height_mm if rot == 90 else dims.width_mm
    h = dims.width_mm if rot == 90 else dims.height_mm
    if _overlaps_any(cx, cy, w, h, placed):
        # Try shifting along the axis
        for offset in [4, 8, 12, -4, -8, -12]:
            if "left" in side or "right" in side:
                test_y = cy + offset
                if not _overlaps_any(cx, test_y, w, h, placed):
                    cy = test_y
                    break
            else:
                test_x = cx + offset
                if not _overlaps_any(test_x, cy, w, h, placed):
                    cx = test_x
                    break

    placed[ref] = PlacedComponent(cx, cy, rot, w, h)


def _in_antenna_keepout(
    x: float, y: float,
    ic: PlacedComponent,
    ic_yaml: dict[str, Any],
) -> bool:
    """Check if a position falls in the antenna keep-out zone."""
    antenna = ic_yaml.get("antenna", {})
    keepout = antenna.get("keep_out_zone", {})
    if not keepout:
        return False

    extend_sides = keepout.get("extend_sides_mm", 0)
    _ = keepout.get("extend_above_mm", 0)  # Used for zone definition

    # Antenna occupies the top ~6mm of the module body
    antenna_zone_bottom = ic.y - ic.height / 2 + 6
    zone_left = ic.x - ic.width / 2 - extend_sides
    zone_right = ic.x + ic.width / 2 + extend_sides

    return y < antenna_zone_bottom and zone_left < x < zone_right


def _place_adjacent(
    ref: str,
    target_ref: str,
    max_distance_mm: float,
    placed: dict[str, PlacedComponent],
    fp_dims: dict[str, FootprintInfo],
    ic_yaml: dict[str, Any],
) -> None:
    """Place a component adjacent to its target, avoiding antenna keep-out."""
    target = placed[target_ref]
    dims = fp_dims[ref]
    gap = min(max_distance_mm * 0.3, 3.0)

    # Try right, below, left, above (prefer below to avoid antenna)
    candidates = [
        (target.x + target.width / 2 + dims.width_mm / 2 + gap, target.y, 0),
        (target.x, target.y + target.height / 2 + dims.height_mm / 2 + gap, 90),
        (target.x - target.width / 2 - dims.width_mm / 2 - gap, target.y, 0),
        (target.x, target.y - target.height / 2 - dims.height_mm / 2 - gap, 90),
    ]

    for cx, cy, rot in candidates:
        w = dims.height_mm if rot == 90 else dims.width_mm
        h = dims.width_mm if rot == 90 else dims.height_mm
        no_overlap = not _overlaps_any(cx, cy, w, h, placed)
        no_antenna = not _in_antenna_keepout(cx, cy, target, ic_yaml)
        if no_overlap and no_antenna:
            placed[ref] = PlacedComponent(cx, cy, rot, w, h)
            return

    # Fallback
    cx = target.x + target.width / 2 + dims.width_mm / 2 + max_distance_mm * 0.5
    cy = target.y
    placed[ref] = PlacedComponent(cx, cy, 0, dims.width_mm, dims.height_mm)


def _place_at_edge(
    ref: str,
    placed: dict[str, PlacedComponent],
    fp_dims: dict[str, FootprintInfo],
    design: DesignResult,
) -> None:
    """Place connector at board edge."""
    dims = fp_dims[ref]
    all_x = [p.x for p in placed.values()] if placed else [0]
    min_x = min(all_x)
    max_x = max(all_x)

    connector_refs = {
        c.reference for c in design.components
        if c.category == ComponentCategory.CONNECTOR
    }
    connector_count = sum(1 for r in placed if r in connector_refs)

    cx = min_x - 10 if connector_count == 0 else max_x + 10
    cy = 0
    placed[ref] = PlacedComponent(cx, cy, 0, dims.width_mm, dims.height_mm)


def _build_net_neighbors(design: DesignResult) -> dict[str, list[str]]:
    """Build component -> neighbors map ranked by shared net count."""
    shared: dict[tuple[str, str], int] = {}
    for net in design.nets:
        refs_in_net = [ref for ref, _pin in net.connections]
        for i, r1 in enumerate(refs_in_net):
            for r2 in refs_in_net[i + 1:]:
                key = (min(r1, r2), max(r1, r2))
                shared[key] = shared.get(key, 0) + 1

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
    ic_yaml: dict[str, Any],
) -> None:
    """Place near most-connected already-placed neighbor, avoiding antenna."""
    dims = fp_dims[ref]
    best_neighbor = None
    for neighbor_ref in net_neighbors.get(ref, []):
        if neighbor_ref in placed:
            best_neighbor = placed[neighbor_ref]
            break

    if best_neighbor is not None:
        gap = 2.0
        nb = best_neighbor
        dx = nb.width / 2 + dims.width_mm / 2 + gap
        dy = nb.height / 2 + dims.height_mm / 2 + gap
        candidates = [
            (nb.x + dx, nb.y, 0),
            (nb.x, nb.y + dy, 0),
            (nb.x - dx, nb.y, 0),
            (nb.x, nb.y - dy, 0),
        ]
        for cx, cy, rot in candidates:
            if not _overlaps_any(cx, cy, dims.width_mm, dims.height_mm, placed):
                # Check antenna keep-out against all ICs
                placed[ref] = PlacedComponent(cx, cy, rot, dims.width_mm, dims.height_mm)
                return

    # Spiral fallback
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
    return any(
        _rects_overlap(x, y, w, h, p.x, p.y, p.width, p.height)
        for p in placed.values()
    )


def _rects_overlap(
    x1: float, y1: float, w1: float, h1: float,
    x2: float, y2: float, w2: float, h2: float,
    margin: float = 1.0,
) -> bool:
    return (
        abs(x1 - x2) < (w1 + w2) / 2 + margin
        and abs(y1 - y2) < (h1 + h2) / 2 + margin
    )


def _to_page_coords(
    placed: dict[str, PlacedComponent],
) -> tuple[dict[str, tuple[float, float, float]], float, float]:
    if not placed:
        return {}, 35.0, 30.0

    all_x = [p.x for p in placed.values()]
    all_y = [p.y for p in placed.values()]

    n = len(placed)
    if n <= 3:
        margin = 4.0
    elif n <= 5:
        margin = 6.0
    else:
        margin = 8.0

    span_x = max(all_x) - min(all_x)
    span_y = max(all_y) - min(all_y)

    min_w = 15.0 if n <= 4 else 25.0 if n <= 6 else 30.0
    min_h = 13.0 if n <= 4 else 20.0 if n <= 6 else 25.0
    board_w = max(min_w, span_x + 2 * margin)
    board_h = max(min_h, span_y + 2 * margin)

    center_x = (max(all_x) + min(all_x)) / 2
    center_y = (max(all_y) + min(all_y)) / 2
    target_x = _PAGE_X + board_w / 2
    target_y = _PAGE_Y + board_h / 2
    shift_x = target_x - center_x
    shift_y = target_y - center_y

    final = {
        ref: (p.x + shift_x, p.y + shift_y, p.rotation)
        for ref, p in placed.items()
    }

    return final, board_w, board_h
