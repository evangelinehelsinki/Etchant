"""Component selector with JLCPCB-first part matching.

Maps component values to JLCPCB parts, prioritizing basic parts (no setup fee)
over extended parts ($3 per unique part). Also provides design rule lookups
from the constraints YAML.

Week 1: Static lookup table for LM2596 reference design parts.
Week 2+: Wire up to JLCPCB parts database API via mixelpixx MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class PartClassification(Enum):
    BASIC = "basic"
    EXTENDED = "extended"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class JLCPCBPartInfo:
    """JLCPCB part metadata for cost optimization."""

    part_number: str
    classification: PartClassification
    description: str
    stock: int

    @property
    def setup_fee_usd(self) -> float:
        if self.classification == PartClassification.BASIC:
            return 0.0
        return 3.0


# Static lookup table for Week 1 — known parts for the LM2596 reference design.
# Week 2+ replaces this with live JLCPCB API queries.
_KNOWN_PARTS: dict[str, JLCPCBPartInfo] = {
    "LM2596S-5": JLCPCBPartInfo(
        part_number="C2837",
        classification=PartClassification.EXTENDED,
        description="LM2596S-5.0 TO-263 step-down regulator",
        stock=5000,
    ),
    "680uF": JLCPCBPartInfo(
        part_number="C296751",
        classification=PartClassification.EXTENDED,
        description="680uF 25V electrolytic capacitor",
        stock=10000,
    ),
    "220uF": JLCPCBPartInfo(
        part_number="C120318",
        classification=PartClassification.EXTENDED,
        description="220uF 10V electrolytic capacitor",
        stock=15000,
    ),
    "33uH": JLCPCBPartInfo(
        part_number="C339984",
        classification=PartClassification.EXTENDED,
        description="33uH power inductor",
        stock=8000,
    ),
    "1N5824": JLCPCBPartInfo(
        part_number="C35722",
        classification=PartClassification.BASIC,
        description="1N5824 Schottky diode 40V 5A DO-201AD",
        stock=50000,
    ),
    "10k": JLCPCBPartInfo(
        part_number="C17414",
        classification=PartClassification.BASIC,
        description="10k 0805 1% resistor",
        stock=500000,
    ),
}


def lookup_jlcpcb_part(
    value: str,
    constraints_dir: Path | None = None,
) -> JLCPCBPartInfo | None:
    """Look up a JLCPCB part by component value.

    Returns None if the part is not found in the static lookup table.
    Week 2+ will query the JLCPCB parts API.
    """
    return _KNOWN_PARTS.get(value)


def find_trace_width(
    current_a: float,
    constraints_dir: Path,
) -> dict[str, Any] | None:
    """Find the appropriate trace width rule for a given current.

    Reads from design_rules.yaml and returns the matching rule dict,
    or the highest rule if current exceeds all entries.
    """
    rules_path = constraints_dir / "design_rules.yaml"
    if not rules_path.exists():
        return None

    with open(rules_path) as f:
        rules = yaml.safe_load(f)

    trace_rules = rules.get("trace_width", [])
    if not trace_rules:
        return None

    for rule in trace_rules:
        if rule["current_a"] >= current_a:
            return dict(rule)

    # Current exceeds all rules — return the highest
    return dict(trace_rules[-1])
