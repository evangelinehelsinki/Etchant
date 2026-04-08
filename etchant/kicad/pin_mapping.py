"""Pin name mapping between generic functional names and KiCad symbol names.

Circuit generators use generic functional pin names (VIN, VOUT, SW, FB, GND).
KiCad symbols use IC-specific pin names that vary per part. This module
bridges the gap so generative designs can produce valid netlists.

The mapping is built from:
1. Static lookup table for common ICs (verified against KiCad 9 libraries)
2. Heuristic matching for unknown ICs (best-effort)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Generic functional pin names -> KiCad symbol pin names
# Format: {ic_symbol: {generic_name: kicad_name}}
_PIN_MAPS: dict[str, dict[str, str]] = {
    # Verified against KiCad 9.0.8 libraries
    "LM2596S-5": {
        "VIN": "VIN",
        "GND": "GND",
        "SW": "OUT",
        "FB": "FB",
        "ON_OFF": "~{ON}/OFF",
    },
    "LM2596S-3.3": {
        "VIN": "VIN",
        "GND": "GND",
        "SW": "OUT",
        "FB": "FB",
        "ON_OFF": "~{ON}/OFF",
    },
    "LM2596S-ADJ": {
        "VIN": "VIN",
        "GND": "GND",
        "SW": "OUT",
        "FB": "FB",
        "ON_OFF": "~{ON}/OFF",
    },
    "AMS1117-3.3": {
        "VIN": "VI",
        "VOUT": "VO",
        "GND": "GND",
    },
    "AMS1117-5.0": {
        "VIN": "VI",
        "VOUT": "VO",
        "GND": "GND",
    },
    "AMS1117-ADJ": {
        "VIN": "VI",
        "VOUT": "VO",
        "GND": "GND",
        "ADJ": "ADJ",
    },
    # TPS56x family (common modern buck converters from WEBENCH)
    "TPS563200": {
        "VIN": "VIN",
        "GND": "GND",
        "SW": "SW",
        "FB": "FB",
        "EN": "EN",
        "BST": "BST",
    },
    "TPS564257": {
        "VIN": "VIN",
        "GND": "PGND",
        "SW": "SW",
        "FB": "FB",
        "EN": "EN",
        "BST": "BST",
    },
    "TPS564255": {
        "VIN": "VIN",
        "GND": "PGND",
        "SW": "SW",
        "FB": "FB",
        "EN": "EN",
        "BST": "BST",
    },
}

# Common generic-to-KiCad name patterns for heuristic matching
_COMMON_ALIASES: dict[str, list[str]] = {
    "VIN": ["VIN", "VI", "IN", "INPUT", "VCC"],
    "VOUT": ["VOUT", "VO", "OUT", "OUTPUT"],
    "GND": ["GND", "PGND", "AGND", "VSS", "EP"],
    "SW": ["SW", "OUT", "LX", "PH", "PHASE"],
    "FB": ["FB", "VFB", "VSENSE", "ADJ"],
    "EN": ["EN", "~{ON}/OFF", "ON_OFF", "SHDN", "~{SHDN}"],
    "BST": ["BST", "BOOT", "CB"],
}


def get_pin_name(ic_symbol: str, generic_name: str) -> str:
    """Map a generic functional pin name to the KiCad symbol pin name.

    Args:
        ic_symbol: KiCad symbol name (e.g., "TPS563200")
        generic_name: Generic functional name (e.g., "VIN", "SW", "FB")

    Returns:
        The KiCad pin name to use with SKiDL.
    """
    # Check static lookup first
    if ic_symbol in _PIN_MAPS:
        mapping = _PIN_MAPS[ic_symbol]
        if generic_name in mapping:
            return mapping[generic_name]

    # Check base part number (strip suffix variants)
    for known_ic, mapping in _PIN_MAPS.items():
        is_prefix = ic_symbol.startswith(known_ic) or known_ic.startswith(ic_symbol)
        if is_prefix and generic_name in mapping:
                logger.debug(
                    "Pin %s on %s matched via prefix to %s",
                    generic_name, ic_symbol, known_ic,
                )
                return mapping[generic_name]

    # Fallback: return the generic name as-is (many ICs use standard names)
    logger.debug(
        "No pin mapping for %s on %s, using generic name",
        generic_name, ic_symbol,
    )
    return generic_name


def has_pin_mapping(ic_symbol: str) -> bool:
    """Check if we have a verified pin mapping for this IC."""
    if ic_symbol in _PIN_MAPS:
        return True
    return any(
        ic_symbol.startswith(known) or known.startswith(ic_symbol)
        for known in _PIN_MAPS
    )


def list_mapped_ics() -> list[str]:
    """Return all ICs with verified pin mappings."""
    return sorted(_PIN_MAPS.keys())
