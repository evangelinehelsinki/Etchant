"""Query real footprint dimensions from KiCad libraries.

Loads footprints from pcbnew and extracts actual bounding box dimensions,
pad positions, and courtyard extents. Falls back to estimates when
pcbnew isn't available.

This replaces the hardcoded _FOOTPRINT_SIZES lookup table with real data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import pcbnew

    HAS_PCBNEW = True
except ImportError:
    HAS_PCBNEW = False

# Fallback estimates when pcbnew isn't available (mm)
_FALLBACK_SIZES: dict[str, tuple[float, float]] = {
    "SOT-223": (6.5, 7.0),
    "SOT-563": (1.8, 1.6),
    "SOT-23": (3.0, 3.0),
    "0805": (2.0, 1.3),
    "0603": (1.6, 0.8),
    "0402": (1.0, 0.5),
    "SMA": (5.0, 2.6),
    "IHLP-2525": (7.0, 7.0),
    "TO-263": (10.0, 15.0),
    "ESP32-C3-WROOM": (18.0, 20.0),
    "PinHeader_1x02": (2.54, 5.08),
    "PinHeader_1x04": (2.54, 10.16),
    "PinHeader_1x06": (2.54, 15.24),
    "PinHeader_1x08": (2.54, 20.32),
    "LED_0805": (2.0, 1.3),
    "LGA-8": (2.5, 2.5),
    "Bosch_LGA": (2.5, 2.5),
}

# Cache for loaded footprint dimensions
_fp_cache: dict[str, tuple[float, float]] = {}


@dataclass(frozen=True)
class FootprintInfo:
    """Real footprint dimensions."""

    width_mm: float   # X extent
    height_mm: float  # Y extent


def get_footprint_dimensions(footprint_str: str) -> FootprintInfo:
    """Get the bounding box dimensions of a footprint.

    Tries to load from pcbnew first, falls back to estimates.
    Results are cached.
    """
    if footprint_str in _fp_cache:
        w, h = _fp_cache[footprint_str]
        return FootprintInfo(w, h)

    # Try pcbnew
    if HAS_PCBNEW:
        dims = _query_pcbnew(footprint_str)
        if dims:
            _fp_cache[footprint_str] = dims
            return FootprintInfo(*dims)

    # Fallback to estimates
    dims = _estimate_size(footprint_str)
    _fp_cache[footprint_str] = dims
    return FootprintInfo(*dims)


def _query_pcbnew(footprint_str: str) -> tuple[float, float] | None:
    """Load footprint from KiCad and measure its bounding box."""
    parts = footprint_str.split(":")
    if len(parts) != 2:
        return None

    lib_name, fp_name = parts
    lib_path = f"/usr/share/kicad/footprints/{lib_name}.pretty"

    if not Path(lib_path).exists():
        return None

    try:
        fp = pcbnew.FootprintLoad(lib_path, fp_name)
        if fp is None:
            return None

        # Get bounding box from courtyard or copper layers
        bbox = fp.GetBoundingBox(False, False)
        w = pcbnew.ToMM(bbox.GetWidth())
        h = pcbnew.ToMM(bbox.GetHeight())

        if w > 0 and h > 0:
            logger.debug("Footprint %s: %.1f x %.1f mm", footprint_str, w, h)
            return (w, h)
    except Exception:
        logger.debug("Failed to load footprint: %s", footprint_str)

    return None


def _estimate_size(footprint_str: str) -> tuple[float, float]:
    """Estimate footprint size from the name."""
    for pattern, size in _FALLBACK_SIZES.items():
        if pattern in footprint_str:
            return size
    return (3.0, 3.0)
