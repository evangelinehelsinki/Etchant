"""Circuit generator registry.

Maps topology names to generator classes. New circuit types register
themselves here so the CLI and agent layer can dispatch by name.
"""

from __future__ import annotations

from typing import Any

from etchant.circuits.buck_converter import LM2596BuckConverter
from etchant.circuits.generative_boost import GenerativeBoostConverter
from etchant.circuits.generative_buck import GenerativeBuckConverter
from etchant.circuits.generative_ldo import GenerativeLDORegulator
from etchant.circuits.ldo_regulator import AMS1117LDORegulator
from etchant.circuits.led_driver import LEDDriverCircuit
from etchant.circuits.sensor_breakout import I2CSensorBreakout

_REGISTRY: dict[str, type[Any]] = {}


def register_generator(topology: str, generator_class: type[Any]) -> None:
    """Register a circuit generator class for a topology name."""
    _REGISTRY[topology] = generator_class


def get_generator(topology: str) -> Any:
    """Instantiate and return a generator for the given topology."""
    if topology not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise KeyError(
            f"Unknown topology '{topology}'. Available: {available}"
        )
    return _REGISTRY[topology]()


def list_topologies() -> tuple[str, ...]:
    """Return all registered topology names."""
    return tuple(sorted(_REGISTRY.keys()))


# Register built-in generators
register_generator("buck_converter", GenerativeBuckConverter)
register_generator("boost_converter", GenerativeBoostConverter)
register_generator("ldo_regulator", GenerativeLDORegulator)
register_generator("led_driver", LEDDriverCircuit)
register_generator("sensor_breakout", I2CSensorBreakout)
register_generator("buck_converter_lm2596", LM2596BuckConverter)
register_generator("ldo_regulator_ams1117", AMS1117LDORegulator)
