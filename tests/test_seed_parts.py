"""Tests for the seed parts database."""

from __future__ import annotations

from pathlib import Path

from etchant.core.component_selector import PartClassification
from etchant.data.jlcpcb_parts import JLCPCBPartsDB
from etchant.data.seed_parts import seed_database


class TestSeedDatabase:
    def test_creates_database(self, tmp_path: Path) -> None:
        db_path = tmp_path / "seed.db"
        count = seed_database(db_path)
        assert count > 30
        assert db_path.exists()

    def test_has_basic_parts(self, tmp_path: Path) -> None:
        db_path = tmp_path / "seed.db"
        seed_database(db_path)
        db = JLCPCBPartsDB(db_path)
        assert db.count_basic_parts() > 15
        db.close()

    def test_can_find_ams1117(self, tmp_path: Path) -> None:
        db_path = tmp_path / "seed.db"
        seed_database(db_path)
        db = JLCPCBPartsDB(db_path)
        results = db.search_by_value("AMS1117-3.3")
        assert len(results) >= 1
        assert results[0].classification == PartClassification.BASIC
        db.close()

    def test_can_find_lm2596(self, tmp_path: Path) -> None:
        db_path = tmp_path / "seed.db"
        seed_database(db_path)
        db = JLCPCBPartsDB(db_path)
        results = db.search_by_value("LM2596")
        assert len(results) >= 1
        db.close()

    def test_has_resistors_and_caps(self, tmp_path: Path) -> None:
        db_path = tmp_path / "seed.db"
        seed_database(db_path)
        db = JLCPCBPartsDB(db_path)
        resistors = db.search_by_value("", category="Resistors")
        caps = db.search_by_value("", category="Capacitors")
        assert len(resistors) >= 5
        assert len(caps) >= 5
        db.close()

    def test_cleans_up_temp_csv(self, tmp_path: Path) -> None:
        db_path = tmp_path / "seed.db"
        seed_database(db_path)
        csv_path = tmp_path / "_seed_parts.csv"
        assert not csv_path.exists()
