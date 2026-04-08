"""Base protocol for circuit generators.

Every circuit topology (buck, boost, LDO, etc.) implements this protocol.
The protocol uses structural subtyping — generators just need to match the shape,
no inheritance required.
"""

from __future__ import annotations

from typing import Protocol

from etchant.core.models import CircuitSpec, DesignResult


class CircuitGenerator(Protocol):
    """Protocol for circuit generators."""

    @property
    def topology(self) -> str: ...

    def generate(self, spec: CircuitSpec) -> DesignResult: ...

    def validate_spec(self, spec: CircuitSpec) -> tuple[str, ...]: ...
