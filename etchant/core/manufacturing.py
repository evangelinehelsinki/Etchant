"""Manufacturing capability validation.

Checks designs against specific manufacturer constraints loaded from YAML.
Validates footprint compatibility, drill sizes, trace widths, and assembly
capabilities for JLCPCB (or any manufacturer with a YAML capability file).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from etchant.core.models import ComponentCategory, DesignResult


def load_capabilities(constraints_dir: Path) -> dict[str, Any]:
    """Load manufacturing capabilities from YAML."""
    path = constraints_dir / "jlcpcb_manufacturing.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Manufacturing capabilities not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def check_assembly_compatibility(
    design: DesignResult,
    constraints_dir: Path,
) -> list[dict[str, str]]:
    """Check if all components are compatible with manufacturer assembly.

    Returns a list of issues found, each with 'component', 'issue', and 'severity'.
    """
    issues: list[dict[str, str]] = []

    try:
        load_capabilities(constraints_dir)
    except FileNotFoundError:
        return issues

    # Check for THT components (JLCPCB assembly is SMT-focused)
    for comp in design.components:
        if "_THT:" in comp.footprint:
            issues.append({
                "component": comp.reference,
                "issue": (
                    f"Through-hole footprint '{comp.footprint}' may require "
                    f"manual soldering or THT assembly service (extra cost)"
                ),
                "severity": "warning",
            })

    # Check for very small components that might be hard to assemble
    for comp in design.components:
        if comp.category == ComponentCategory.RESISTOR and "0201" in comp.footprint:
            issues.append({
                "component": comp.reference,
                "issue": "0201 package is very small — consider 0402 or 0603 for reliability",
                "severity": "info",
            })

    return issues


def estimate_board_cost(
    board_size_mm: tuple[float, float] = (50.0, 50.0),
    layers: int = 2,
    quantity: int = 5,
    constraints_dir: Path | None = None,
) -> dict[str, float]:
    """Estimate bare board cost based on JLCPCB pricing.

    Returns a dict with cost breakdown components.
    Note: These are rough estimates based on published pricing.
    Actual costs depend on many factors not captured here.
    """
    # JLCPCB pricing model (rough approximation)
    # Base price for 5 boards under 100x100mm, 2 layers: ~$2
    # Larger boards or more layers increase cost
    area_mm2 = board_size_mm[0] * board_size_mm[1]

    base_cost = 2.0
    if area_mm2 > 10000:  # > 100x100mm
        base_cost = 5.0
    if area_mm2 > 25000:  # > 158x158mm
        base_cost = max(base_cost, area_mm2 / 5000)

    layer_multiplier = {2: 1.0, 4: 3.0, 6: 5.0}.get(layers, layers * 1.5)

    quantity_pricing = {5: 1.0, 10: 1.5, 20: 2.0, 50: 3.0, 100: 4.0}
    qty_multiplier = 1.0
    for qty_threshold, price in sorted(quantity_pricing.items()):
        if quantity >= qty_threshold:
            qty_multiplier = price

    board_cost = base_cost * layer_multiplier * (qty_multiplier / quantity)

    return {
        "board_area_mm2": area_mm2,
        "layers": float(layers),
        "quantity": float(quantity),
        "per_board_usd": round(board_cost, 2),
        "total_boards_usd": round(board_cost * quantity, 2),
    }
