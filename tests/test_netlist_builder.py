"""Tests for the SKiDL netlist builder.

These tests require SKiDL and KiCad libraries to be installed.
They are skipped automatically when running outside the distrobox environment.
"""

from __future__ import annotations

import pytest

from etchant.kicad.netlist_builder import check_skidl_available

requires_skidl = pytest.mark.skipif(
    not check_skidl_available(),
    reason="SKiDL not available (run inside distrobox)",
)


@requires_skidl
class TestNetlistBuilder:
    def test_placeholder(self) -> None:
        """Placeholder — real tests run inside distrobox with KiCad libraries."""
        assert check_skidl_available()
