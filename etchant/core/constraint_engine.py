"""Constraint engine for validating designs against manufacturing and layout rules.

Loads structured YAML constraint files and checks DesignResult objects for violations.
The engine is generic; constraints are swappable per manufacturer or IC.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from etchant.core.models import DesignResult


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

    def load_manufacturing_rules(self) -> dict[str, Any]:
        path = self._constraints_dir / "jlcpcb_manufacturing.yaml"
        return self._load_yaml(path)

    def load_design_rules(self) -> dict[str, Any]:
        path = self._constraints_dir / "design_rules.yaml"
        return self._load_yaml(path)

    def load_layout_rules(self, ic_name: str) -> dict[str, Any]:
        filename = f"{ic_name.lower()}_layout.yaml"
        path = self._constraints_dir / filename
        return self._load_yaml(path)

    def validate_design(self, design: DesignResult) -> tuple[ConstraintViolation, ...]:
        """Validate a design against all applicable constraints."""
        violations: list[ConstraintViolation] = []
        violations.extend(self._check_component_count(design))
        violations.extend(self._check_placement_constraints(design))
        violations.extend(self._check_net_connectivity(design))
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
