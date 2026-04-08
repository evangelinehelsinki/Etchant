"""Bill of Materials generation and JLCPCB cost estimation.

Transforms a DesignResult into a BOM with JLCPCB part numbers and cost breakdown.
The cost model accounts for basic vs extended part classification since extended
parts add $3 per unique part to JLCPCB assembly orders.
"""

from __future__ import annotations

from dataclasses import dataclass

from etchant.core.component_selector import (
    PartClassification,
    lookup_jlcpcb_part,
)
from etchant.core.models import DesignResult


@dataclass(frozen=True)
class BOMEntry:
    """A single line item in a Bill of Materials."""

    reference: str
    value: str
    footprint: str
    description: str
    quantity: int
    jlcpcb_part_number: str | None
    classification: PartClassification | None
    unit_price_usd: float | None


@dataclass(frozen=True)
class CostBreakdown:
    """JLCPCB assembly cost breakdown."""

    basic_parts_count: int
    extended_parts_count: int
    unknown_parts_count: int
    total_setup_fee_usd: float

    @classmethod
    def from_bom(cls, bom: tuple[BOMEntry, ...]) -> CostBreakdown:
        basic = 0
        extended = 0
        unknown = 0
        setup_fee = 0.0

        for entry in bom:
            if entry.classification == PartClassification.BASIC:
                basic += 1
            elif entry.classification == PartClassification.EXTENDED:
                extended += 1
                setup_fee += 3.0
            else:
                unknown += 1
                setup_fee += 3.0  # Assume extended pricing for unknown parts

        return cls(
            basic_parts_count=basic,
            extended_parts_count=extended,
            unknown_parts_count=unknown,
            total_setup_fee_usd=setup_fee,
        )

    def summary(self) -> str:
        total = self.basic_parts_count + self.extended_parts_count + self.unknown_parts_count
        lines = [
            f"BOM: {total} unique parts",
            f"  Basic: {self.basic_parts_count} (no setup fee)",
            f"  Extended: {self.extended_parts_count} ($3 each = ${self.extended_parts_count * 3})",
        ]
        if self.unknown_parts_count > 0:
            lines.append(
                f"  Unknown: {self.unknown_parts_count} (assumed extended pricing)"
            )
        lines.append(f"  Total setup fee: ${self.total_setup_fee_usd:.2f}")
        return "\n".join(lines)


class BOMGenerator:
    """Generates a BOM from a DesignResult with JLCPCB part matching."""

    def generate(self, design: DesignResult) -> tuple[BOMEntry, ...]:
        entries: list[BOMEntry] = []

        for comp in design.components:
            part_info = lookup_jlcpcb_part(comp.value)
            entries.append(
                BOMEntry(
                    reference=comp.reference,
                    value=comp.value,
                    footprint=comp.footprint,
                    description=comp.description,
                    quantity=1,
                    jlcpcb_part_number=part_info.part_number if part_info else None,
                    classification=(
                        part_info.classification if part_info else PartClassification.UNKNOWN
                    ),
                    unit_price_usd=None,
                )
            )

        return tuple(entries)
