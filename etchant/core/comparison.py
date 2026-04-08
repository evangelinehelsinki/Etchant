"""Design comparison for automated verification.

Compares two DesignResult objects and produces a structured diff.
Used for:
- Comparing generated designs against golden references
- Detecting regressions when the generator changes
- Verifying LLM-generated designs against known-good designs
"""

from __future__ import annotations

from dataclasses import dataclass

from etchant.core.models import DesignResult


@dataclass(frozen=True)
class ComparisonResult:
    """Result of comparing two designs."""

    matches: bool
    component_diffs: tuple[str, ...]
    net_diffs: tuple[str, ...]
    constraint_diffs: tuple[str, ...]
    note_diffs: tuple[str, ...]

    @property
    def total_diffs(self) -> int:
        return (
            len(self.component_diffs)
            + len(self.net_diffs)
            + len(self.constraint_diffs)
            + len(self.note_diffs)
        )

    def summary(self) -> str:
        if self.matches:
            return "Designs match"

        lines = [f"Found {self.total_diffs} difference(s):"]
        for diff in self.component_diffs:
            lines.append(f"  [component] {diff}")
        for diff in self.net_diffs:
            lines.append(f"  [net] {diff}")
        for diff in self.constraint_diffs:
            lines.append(f"  [constraint] {diff}")
        for diff in self.note_diffs:
            lines.append(f"  [note] {diff}")
        return "\n".join(lines)


def compare_designs(actual: DesignResult, expected: DesignResult) -> ComparisonResult:
    """Compare two designs and return structured differences."""
    comp_diffs = _compare_components(actual, expected)
    net_diffs = _compare_nets(actual, expected)
    constraint_diffs = _compare_constraints(actual, expected)
    note_diffs = _compare_notes(actual, expected)

    matches = not any([comp_diffs, net_diffs, constraint_diffs, note_diffs])

    return ComparisonResult(
        matches=matches,
        component_diffs=comp_diffs,
        net_diffs=net_diffs,
        constraint_diffs=constraint_diffs,
        note_diffs=note_diffs,
    )


def _compare_components(actual: DesignResult, expected: DesignResult) -> tuple[str, ...]:
    diffs: list[str] = []

    actual_refs = {c.reference: c for c in actual.components}
    expected_refs = {c.reference: c for c in expected.components}

    for ref in sorted(expected_refs.keys() - actual_refs.keys()):
        diffs.append(f"Missing component {ref} ({expected_refs[ref].value})")

    for ref in sorted(actual_refs.keys() - expected_refs.keys()):
        diffs.append(f"Extra component {ref} ({actual_refs[ref].value})")

    for ref in sorted(actual_refs.keys() & expected_refs.keys()):
        a, e = actual_refs[ref], expected_refs[ref]
        if a.value != e.value:
            diffs.append(f"{ref}: value '{a.value}' != expected '{e.value}'")
        if a.category != e.category:
            diffs.append(f"{ref}: category {a.category.name} != expected {e.category.name}")
        if a.footprint != e.footprint:
            diffs.append(f"{ref}: footprint '{a.footprint}' != expected '{e.footprint}'")

    return tuple(diffs)


def _compare_nets(actual: DesignResult, expected: DesignResult) -> tuple[str, ...]:
    diffs: list[str] = []

    actual_nets = {n.name: n for n in actual.nets}
    expected_nets = {n.name: n for n in expected.nets}

    for name in sorted(expected_nets.keys() - actual_nets.keys()):
        diffs.append(f"Missing net {name}")

    for name in sorted(actual_nets.keys() - expected_nets.keys()):
        diffs.append(f"Extra net {name}")

    for name in sorted(actual_nets.keys() & expected_nets.keys()):
        a_conns = set(actual_nets[name].connections)
        e_conns = set(expected_nets[name].connections)

        for conn in sorted(e_conns - a_conns):
            diffs.append(f"Net {name}: missing connection {conn[0]}.{conn[1]}")
        for conn in sorted(a_conns - e_conns):
            diffs.append(f"Net {name}: extra connection {conn[0]}.{conn[1]}")

    return tuple(diffs)


def _compare_constraints(actual: DesignResult, expected: DesignResult) -> tuple[str, ...]:
    diffs: list[str] = []

    if len(actual.placement_constraints) != len(expected.placement_constraints):
        diffs.append(
            f"Constraint count {len(actual.placement_constraints)} "
            f"!= expected {len(expected.placement_constraints)}"
        )

    return tuple(diffs)


def _compare_notes(actual: DesignResult, expected: DesignResult) -> tuple[str, ...]:
    diffs: list[str] = []

    if len(actual.design_notes) < len(expected.design_notes):
        diffs.append(
            f"Fewer design notes ({len(actual.design_notes)}) "
            f"than expected ({len(expected.design_notes)})"
        )

    return tuple(diffs)
