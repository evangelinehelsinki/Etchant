"""Core data models for the Etchant design pipeline.

All types are frozen dataclasses with tuple collections to enforce immutability.
These are the data contracts between circuit generators, the constraint engine,
and the KiCad export layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from types import MappingProxyType


class ComponentCategory(Enum):
    IC = auto()
    CAPACITOR = auto()
    INDUCTOR = auto()
    DIODE = auto()
    RESISTOR = auto()
    CONNECTOR = auto()


@dataclass(frozen=True)
class ComponentSpec:
    """A single component in a circuit design."""

    reference: str
    category: ComponentCategory
    value: str
    footprint: str
    kicad_library: str
    kicad_symbol: str
    description: str
    properties: Mapping[str, str] = field(default_factory=dict)
    jlcpcb_part_number: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", MappingProxyType(dict(self.properties)))


@dataclass(frozen=True)
class NetSpec:
    """A named net connecting component pins."""

    name: str
    connections: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PlacementConstraint:
    """Physical placement constraint between components."""

    component_ref: str
    target_ref: str | None
    max_distance_mm: float
    reason: str


@dataclass(frozen=True)
class CircuitSpec:
    """Input specification for a circuit design."""

    name: str
    topology: str
    input_voltage: float
    output_voltage: float
    output_current: float
    description: str


@dataclass(frozen=True)
class DesignResult:
    """Complete output of a circuit generator."""

    spec: CircuitSpec
    components: tuple[ComponentSpec, ...]
    nets: tuple[NetSpec, ...]
    placement_constraints: tuple[PlacementConstraint, ...]
    design_notes: tuple[str, ...]
