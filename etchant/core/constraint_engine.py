"""Constraint engine for validating designs against manufacturing and layout rules.

Loads structured YAML constraint files and checks DesignResult objects for violations.
The engine is generic; constraints are swappable per manufacturer or IC.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from etchant.core.models import DesignResult

logger = logging.getLogger(__name__)


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ConstraintViolation:
    """A single constraint violation found during validation."""

    rule: str
    severity: Severity
    message: str
    component_ref: str | None = None


class ConstraintEngine:
    """Loads YAML constraints and validates designs against them."""

    def __init__(self, constraints_dir: Path) -> None:
        self._constraints_dir = constraints_dir
        self._design_rules: dict[str, Any] | None = None

    def load_manufacturing_rules(self) -> dict[str, Any]:
        path = self._constraints_dir / "jlcpcb_manufacturing.yaml"
        return self._load_yaml(path)

    def load_design_rules(self) -> dict[str, Any]:
        if self._design_rules is None:
            path = self._constraints_dir / "design_rules.yaml"
            self._design_rules = self._load_yaml(path)
        return self._design_rules

    def load_layout_rules(self, ic_name: str) -> dict[str, Any]:
        filename = f"{ic_name.lower()}_layout.yaml"
        path = self._constraints_dir / filename
        return self._load_yaml(path)

    def validate_design(self, design: DesignResult) -> tuple[ConstraintViolation, ...]:
        """Validate a design against structural and YAML-backed rules."""
        violations: list[ConstraintViolation] = []
        violations.extend(self._check_component_count(design))
        violations.extend(self._check_placement_constraints(design))
        violations.extend(self._check_net_connectivity(design))
        violations.extend(self._check_single_pin_nets(design))
        violations.extend(self._check_trace_width_requirements(design))
        violations.extend(self._check_duplicate_references(design))
        violations.extend(self._check_power_nets_exist(design))
        return tuple(violations)

    def _check_component_count(self, design: DesignResult) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        if len(design.components) == 0:
            violations.append(
                ConstraintViolation(
                    rule="min_components",
                    severity=Severity.ERROR,
                    message="Design has no components",
                )
            )
        return violations

    def _check_placement_constraints(self, design: DesignResult) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        component_refs = {c.reference for c in design.components}

        for constraint in design.placement_constraints:
            if constraint.component_ref not in component_refs:
                violations.append(
                    ConstraintViolation(
                        rule="placement_component_exists",
                        severity=Severity.ERROR,
                        message=(
                            f"Placement constraint references non-existent "
                            f"component '{constraint.component_ref}'"
                        ),
                        component_ref=constraint.component_ref,
                    )
                )
            if constraint.target_ref is not None and constraint.target_ref not in component_refs:
                violations.append(
                    ConstraintViolation(
                        rule="placement_target_exists",
                        severity=Severity.ERROR,
                        message=(
                            f"Placement constraint target '{constraint.target_ref}' "
                            f"does not exist in design"
                        ),
                        component_ref=constraint.component_ref,
                    )
                )
        return violations

    def _check_net_connectivity(self, design: DesignResult) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        component_refs = {c.reference for c in design.components}

        for net in design.nets:
            for ref, _pin in net.connections:
                if ref not in component_refs:
                    violations.append(
                        ConstraintViolation(
                            rule="net_component_exists",
                            severity=Severity.ERROR,
                            message=(
                                f"Net '{net.name}' references non-existent "
                                f"component '{ref}'"
                            ),
                            component_ref=ref,
                        )
                    )
        return violations

    def _check_single_pin_nets(self, design: DesignResult) -> list[ConstraintViolation]:
        """Flag nets with only one connection (likely unconnected pins)."""
        violations: list[ConstraintViolation] = []
        for net in design.nets:
            if len(net.connections) < 2:
                violations.append(
                    ConstraintViolation(
                        rule="single_pin_net",
                        severity=Severity.WARNING,
                        message=(
                            f"Net '{net.name}' has only {len(net.connections)} connection(s) "
                            f"— likely a dangling pin"
                        ),
                    )
                )
        return violations

    def _check_trace_width_requirements(
        self, design: DesignResult
    ) -> list[ConstraintViolation]:
        """Check trace width requirements based on output current and design_rules.yaml."""
        violations: list[ConstraintViolation] = []

        try:
            rules = self.load_design_rules()
        except FileNotFoundError:
            logger.debug("design_rules.yaml not found, skipping trace width check")
            return violations

        trace_rules = rules.get("trace_width", [])
        if not trace_rules:
            return violations

        current = design.spec.output_current
        matching_rule = None
        for rule in trace_rules:
            if rule["current_a"] >= current:
                matching_rule = rule
                break

        if matching_rule is None:
            # Current exceeds all rules — use the highest
            matching_rule = trace_rules[-1]
            violations.append(
                ConstraintViolation(
                    rule="trace_width_recommendation",
                    severity=Severity.WARNING,
                    message=(
                        f"Output current {current}A exceeds highest trace width rule "
                        f"({matching_rule['current_a']}A). "
                        f"Minimum trace width: {matching_rule['min_width_mm']}mm, "
                        f"recommended: {matching_rule['recommended_mm']}mm. "
                        f"Verify trace width is adequate for {current}A."
                    ),
                )
            )
        else:
            violations.append(
                ConstraintViolation(
                    rule="trace_width_recommendation",
                    severity=Severity.INFO,
                    message=(
                        f"For {current}A: minimum trace width {matching_rule['min_width_mm']}mm, "
                        f"recommended {matching_rule['recommended_mm']}mm "
                        f"(1oz copper, {rules.get('temperature_rise_c', 10)}C rise)"
                    ),
                )
            )

        return violations

    def _check_power_nets_exist(self, design: DesignResult) -> list[ConstraintViolation]:
        """Verify that essential power nets (VIN, VOUT/output, GND) exist."""
        violations: list[ConstraintViolation] = []
        net_names = {n.name for n in design.nets}

        has_ground = any(
            name in net_names for name in ("GND", "VSS", "GROUND", "AGND", "DGND")
        )
        if not has_ground and len(design.components) > 0:
            violations.append(
                ConstraintViolation(
                    rule="ground_net_missing",
                    severity=Severity.WARNING,
                    message=(
                        "No ground net (GND/VSS) found — "
                        "most circuits require a ground reference"
                    ),
                )
            )

        return violations

    def _check_duplicate_references(self, design: DesignResult) -> list[ConstraintViolation]:
        """Flag duplicate component references."""
        violations: list[ConstraintViolation] = []
        seen: set[str] = set()
        for comp in design.components:
            if comp.reference in seen:
                violations.append(
                    ConstraintViolation(
                        rule="duplicate_reference",
                        severity=Severity.ERROR,
                        message=f"Duplicate component reference '{comp.reference}'",
                        component_ref=comp.reference,
                    )
                )
            seen.add(comp.reference)
        return violations

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._constraints_dir.resolve()):
            raise ValueError(f"Path escapes constraints directory: {path}")
        if not resolved.exists():
            raise FileNotFoundError(f"Constraint file not found: {path}")
        with open(resolved) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected YAML dict, got {type(data).__name__} in {path}")
        return data
