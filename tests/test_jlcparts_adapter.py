"""Tests for the jlcparts database adapter.

Tests against the real 7M-part database if available, otherwise skips.
Note: First run creates indexes on the 12 GB database (takes ~60s).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etchant.core.component_selector import PartClassification

_JLCPARTS_DB = Path("/home/evangeline/Projects/etchant-data/data/jlcparts/cache.sqlite3")
_has_db = _JLCPARTS_DB.exists()

requires_jlcparts = pytest.mark.skipif(
    not _has_db,
    reason="jlcparts database not available",
)


@requires_jlcparts
class TestJLCPartsAdapter:
    @pytest.fixture
    def adapter(self):  # type: ignore[no-untyped-def]
        from etchant.data.jlcparts_adapter import JLCPartsAdapter

        db = JLCPartsAdapter(_JLCPARTS_DB)
        yield db
        db.close()

    def test_search_resistor(self, adapter) -> None:  # type: ignore[no-untyped-def]
        results = adapter.search("10kOhm 0805", min_stock=1000, limit=5)
        assert len(results) > 0

    def test_search_ams1117(self, adapter) -> None:  # type: ignore[no-untyped-def]
        results = adapter.search("AMS1117-3.3", limit=5)
        assert len(results) > 0
        # AMS1117-3.3 should be a basic part
        assert any(r.classification == PartClassification.BASIC for r in results)

    def test_search_lm2596(self, adapter) -> None:  # type: ignore[no-untyped-def]
        results = adapter.search("LM2596", limit=5)
        assert len(results) > 0

    def test_search_basic_only(self, adapter) -> None:  # type: ignore[no-untyped-def]
        results = adapter.search("capacitor", basic_only=True, limit=5)
        assert all(r.classification == PartClassification.BASIC for r in results)

    def test_get_by_lcsc_number(self, adapter) -> None:  # type: ignore[no-untyped-def]
        result = adapter.get_by_lcsc_number(1002)
        assert result is not None
        assert result.part_number == "C1002"

    def test_get_by_lcsc_string(self, adapter) -> None:  # type: ignore[no-untyped-def]
        result = adapter.get_by_lcsc_string("C1002")
        assert result is not None

    def test_nonexistent_part(self, adapter) -> None:  # type: ignore[no-untyped-def]
        result = adapter.get_by_lcsc_number(999999999)
        assert result is None

    def test_part_has_stock(self, adapter) -> None:  # type: ignore[no-untyped-def]
        results = adapter.search("AMS1117", min_stock=100, limit=3)
        assert all(r.stock >= 100 for r in results)
