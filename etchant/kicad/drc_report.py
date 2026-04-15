"""Parse kicad-cli drc report output into structured violation counts.

KiCad's DRC report is plain text with a `[category]:` prefix on each
violation, followed by a rule line, then one or more location lines.
This module parses that format without calling kicad-cli — callers
generate the report separately and hand it in.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_VIOLATION_LINE = re.compile(r"^\[(?P<category>[a-z_]+)\]:")
_COUNT_LINE = re.compile(r"Found (?P<n>\d+) (?P<kind>DRC violations|unconnected pads|Footprint errors)")


@dataclass(frozen=True)
class DRCReport:
    """Structured DRC report.

    violations_by_category is a frozen mapping of category name (e.g.
    "courtyards_overlap", "clearance") to integer count.
    """

    violations_by_category: dict[str, int] = field(default_factory=dict)
    total_violations: int = 0
    unconnected_pads: int = 0
    footprint_errors: int = 0

    @property
    def errors_only(self) -> int:
        """Count of violations that kicad treats as errors (not warnings).

        Uses the default rule_severities from etchant's jlcpcb template.
        """
        error_categories = {
            "clearance", "courtyards_overlap", "drill_out_of_range",
            "hole_clearance", "shorting_items", "solder_mask_bridge",
            "starved_thermal", "unconnected_items", "items_not_allowed",
            "copper_edge_clearance", "annular_width", "track_width",
            "text_on_edge_cuts", "creepage", "invalid_outline",
            "item_on_disabled_layer", "malformed_courtyard",
            "microvia_drill_out_of_range", "through_hole_pad_without_hole",
            "too_many_vias", "track_angle", "track_segment_length",
            "tracks_crossing", "unresolved_variable", "zones_intersect",
            "length_out_of_range", "skew_out_of_range",
            "diff_pair_gap_out_of_range", "diff_pair_uncoupled_length_too_long",
            "footprint",
        }
        return sum(
            n for cat, n in self.violations_by_category.items()
            if cat in error_categories
        )

    @property
    def warnings_only(self) -> int:
        """Count of violations that kicad treats as warnings."""
        return self.total_violations - self.errors_only


def parse_drc_report(report_path: Path) -> DRCReport:
    """Parse a kicad-cli drc report file into a DRCReport."""
    if not report_path.exists():
        raise FileNotFoundError(f"DRC report not found: {report_path}")

    text = report_path.read_text()
    return parse_drc_text(text)


def parse_drc_text(text: str) -> DRCReport:
    """Parse DRC report text content."""
    categories: Counter[str] = Counter()
    total = 0
    unconnected = 0
    footprint_errs = 0

    for line in text.splitlines():
        vm = _VIOLATION_LINE.match(line.strip())
        if vm:
            categories[vm.group("category")] += 1
            continue

        cm = _COUNT_LINE.search(line)
        if cm:
            n = int(cm.group("n"))
            kind = cm.group("kind")
            if kind == "DRC violations":
                total = n
            elif kind == "unconnected pads":
                unconnected = n
            elif kind == "Footprint errors":
                footprint_errs = n

    return DRCReport(
        violations_by_category=dict(categories),
        total_violations=total,
        unconnected_pads=unconnected,
        footprint_errors=footprint_errs,
    )
