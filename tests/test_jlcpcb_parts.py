"""Tests for the JLCPCB parts database."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from etchant.core.component_selector import PartClassification
from etchant.data.jlcpcb_parts import JLCPCBPartsDB


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a sample JLCPCB CSV export for testing."""
    csv_path = tmp_path / "parts.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "LCSC Part #", "MFR.Part #", "Package", "Description",
            "Library Type", "Stock", "First Category", "Second Category", "Price",
        ])
        writer.writeheader()
        writer.writerow({
            "LCSC Part #": "C17414",
            "MFR.Part #": "0805W8F1002T5E",
            "Package": "0805",
            "Description": "10k 0805 1% Resistor",
            "Library Type": "Basic",
            "Stock": "500000",
            "First Category": "Resistors",
            "Second Category": "Chip Resistors",
            "Price": "0.001",
        })
        writer.writerow({
            "LCSC Part #": "C2837",
            "MFR.Part #": "LM2596S-5.0",
            "Package": "TO-263",
            "Description": "LM2596S-5.0 Step-Down Regulator",
            "Library Type": "Extended",
            "Stock": "5000",
            "First Category": "Power ICs",
            "Second Category": "DC-DC Converters",
            "Price": "0.85",
        })
        writer.writerow({
            "LCSC Part #": "C6186",
            "MFR.Part #": "AMS1117-3.3",
            "Package": "SOT-223",
            "Description": "AMS1117-3.3 LDO Regulator",
            "Library Type": "Basic",
            "Stock": "200000",
            "First Category": "Power ICs",
            "Second Category": "LDO Regulators",
            "Price": "0.05",
        })
    return csv_path


@pytest.fixture
def db(tmp_path: Path, sample_csv: Path) -> JLCPCBPartsDB:
    """Create and populate a test database."""
    db_path = tmp_path / "test_parts.db"
    parts_db = JLCPCBPartsDB(db_path)
    parts_db.import_csv(sample_csv)
    return parts_db


class TestImport:
    def test_import_csv(self, db: JLCPCBPartsDB) -> None:
        assert db.count_parts() == 3

    def test_basic_parts_count(self, db: JLCPCBPartsDB) -> None:
        assert db.count_basic_parts() == 2

    def test_reimport_idempotent(self, db: JLCPCBPartsDB, sample_csv: Path) -> None:
        db.import_csv(sample_csv)
        assert db.count_parts() == 3


class TestLookup:
    def test_get_by_lcsc(self, db: JLCPCBPartsDB) -> None:
        part = db.get_by_lcsc("C17414")
        assert part is not None
        assert part.mfr_part == "0805W8F1002T5E"
        assert part.classification == PartClassification.BASIC

    def test_get_nonexistent(self, db: JLCPCBPartsDB) -> None:
        part = db.get_by_lcsc("C999999")
        assert part is None


class TestSearch:
    def test_search_by_value(self, db: JLCPCBPartsDB) -> None:
        results = db.search_by_value("10k")
        assert len(results) >= 1
        assert any(p.lcsc_part == "C17414" for p in results)

    def test_search_by_mfr_part(self, db: JLCPCBPartsDB) -> None:
        results = db.search_by_value("LM2596")
        assert len(results) >= 1
        assert results[0].lcsc_part == "C2837"

    def test_search_basic_only(self, db: JLCPCBPartsDB) -> None:
        results = db.search_by_value("Regulator", basic_only=True)
        assert all(p.classification == PartClassification.BASIC for p in results)

    def test_search_by_category(self, db: JLCPCBPartsDB) -> None:
        results = db.search_by_value("", category="Power ICs")
        assert len(results) == 2

    def test_search_min_stock(self, db: JLCPCBPartsDB) -> None:
        results = db.search_by_value("", min_stock=100000)
        assert all(p.stock >= 100000 for p in results)


class TestPartConversion:
    def test_to_part_info(self, db: JLCPCBPartsDB) -> None:
        part = db.get_by_lcsc("C17414")
        assert part is not None
        info = part.to_part_info()
        assert info.part_number == "C17414"
        assert info.classification == PartClassification.BASIC
        assert info.setup_fee_usd == 0.0


class TestCleanup:
    def test_close(self, tmp_path: Path) -> None:
        db = JLCPCBPartsDB(tmp_path / "test.db")
        db.create_tables()
        db.close()
        # Should not raise
        db.close()
