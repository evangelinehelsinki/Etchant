"""Tests for the component selector."""

from __future__ import annotations

from pathlib import Path

from etchant.core.component_selector import (
    JLCPCBPartInfo,
    PartClassification,
    find_trace_width,
    lookup_jlcpcb_part,
    set_parts_db,
)


class TestPartClassification:
    def test_basic_part(self) -> None:
        info = JLCPCBPartInfo(
            part_number="C296751",
            classification=PartClassification.BASIC,
            description="680uF 25V electrolytic capacitor",
            stock=50000,
        )
        assert info.classification == PartClassification.BASIC
        assert info.setup_fee_usd == 0.0

    def test_extended_part(self) -> None:
        info = JLCPCBPartInfo(
            part_number="C2837",
            classification=PartClassification.EXTENDED,
            description="LM2596S-5",
            stock=1000,
        )
        assert info.classification == PartClassification.EXTENDED
        assert info.setup_fee_usd == 3.0

    def test_unknown_part(self) -> None:
        info = JLCPCBPartInfo(
            part_number="C999999",
            classification=PartClassification.UNKNOWN,
            description="Unknown part",
            stock=0,
        )
        assert info.setup_fee_usd == 3.0


class TestLookupJLCPCBPart:
    def test_known_lm2596(self, constraints_dir: Path) -> None:
        info = lookup_jlcpcb_part("LM2596S-5", constraints_dir)
        assert info is not None
        assert info.part_number is not None

    def test_unknown_part_returns_none(self, constraints_dir: Path) -> None:
        info = lookup_jlcpcb_part("NONEXISTENT_PART_XYZ", constraints_dir)
        assert info is None


class TestDBIntegration:
    def test_lookup_uses_db_when_set(self, tmp_path: Path) -> None:
        """When a DB is set, lookup_jlcpcb_part queries it first."""
        import csv

        from etchant.data.jlcpcb_parts import JLCPCBPartsDB

        # Create a CSV with a part not in the static table
        csv_path = tmp_path / "parts.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "LCSC Part #", "MFR.Part #", "Package", "Description",
                "Library Type", "Stock", "First Category", "Second Category", "Price",
            ])
            writer.writeheader()
            writer.writerow({
                "LCSC Part #": "C99999",
                "MFR.Part #": "CUSTOM_PART_XYZ",
                "Package": "0603",
                "Description": "Custom test part",
                "Library Type": "Basic",
                "Stock": "10000",
                "First Category": "Test",
                "Second Category": "Test",
                "Price": "0.01",
            })

        db = JLCPCBPartsDB(tmp_path / "test.db")
        db.import_csv(csv_path)

        try:
            set_parts_db(db)
            result = lookup_jlcpcb_part("CUSTOM_PART_XYZ")
            assert result is not None
            assert result.part_number == "C99999"
        finally:
            set_parts_db(None)
            db.close()

    def test_falls_back_to_static_when_db_misses(self, tmp_path: Path) -> None:
        from etchant.data.jlcpcb_parts import JLCPCBPartsDB

        db = JLCPCBPartsDB(tmp_path / "empty.db")
        db.create_tables()

        try:
            set_parts_db(db)
            result = lookup_jlcpcb_part("10k")
            assert result is not None
            assert result.part_number == "C17414"  # From static table
        finally:
            set_parts_db(None)
            db.close()


class TestTraceWidth:
    def test_2a_trace_width(self, constraints_dir: Path) -> None:
        result = find_trace_width(2.0, constraints_dir)
        assert result is not None
        assert result["min_width_mm"] == 0.5
        assert result["recommended_mm"] == 0.75

    def test_1a_trace_width(self, constraints_dir: Path) -> None:
        result = find_trace_width(1.0, constraints_dir)
        assert result is not None
        assert result["min_width_mm"] == 0.254

    def test_above_max_returns_highest(self, constraints_dir: Path) -> None:
        result = find_trace_width(10.0, constraints_dir)
        assert result is not None
        assert result["current_a"] == 5.0
