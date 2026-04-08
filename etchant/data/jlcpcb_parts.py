"""JLCPCB parts database interface.

Provides a unified interface for querying JLCPCB component data.
Week 1: SQLite-backed local database populated from CSV exports.
Week 2+: Live API queries via mixelpixx MCP server.

The database schema mirrors JLCPCB's parts catalog:
- Part number (e.g., C17414)
- MFR part number (e.g., 0805W8F1002T5E)
- Package (e.g., 0805)
- Description
- Classification (basic/extended)
- Stock count
- Category (resistors, capacitors, ICs, etc.)
"""

from __future__ import annotations

import contextlib
import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from etchant.core.component_selector import JLCPCBPartInfo, PartClassification


@dataclass(frozen=True)
class JLCPCBPart:
    """Full JLCPCB part record from the database."""

    lcsc_part: str
    mfr_part: str
    package: str
    description: str
    classification: PartClassification
    stock: int
    category: str
    subcategory: str
    price_usd: float | None = None

    def to_part_info(self) -> JLCPCBPartInfo:
        """Convert to the simpler JLCPCBPartInfo used by the component selector."""
        return JLCPCBPartInfo(
            part_number=self.lcsc_part,
            classification=self.classification,
            description=self.description,
            stock=self.stock,
        )


class JLCPCBPartsDB:
    """Local SQLite database of JLCPCB parts.

    Initialize with a path to the database file. If the file doesn't exist,
    call import_csv() to populate it from a JLCPCB CSV export.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def create_tables(self) -> None:
        """Create the parts table if it doesn't exist."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parts (
                lcsc_part TEXT PRIMARY KEY,
                mfr_part TEXT,
                package TEXT,
                description TEXT,
                classification TEXT,
                stock INTEGER,
                category TEXT,
                subcategory TEXT,
                price_usd REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mfr_part ON parts(mfr_part)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_category ON parts(category)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_classification ON parts(classification)
        """)
        conn.commit()

    def import_csv(self, csv_path: Path) -> int:
        """Import parts from a JLCPCB CSV export. Returns count of imported parts."""
        self.create_tables()
        conn = self._get_conn()

        count = 0
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                classification = row.get("Library Type", "").strip().lower()
                if classification == "basic":
                    cls = "basic"
                elif classification == "extended":
                    cls = "extended"
                else:
                    cls = "unknown"

                stock_str = row.get("Stock", "0").strip()
                stock = int(stock_str) if stock_str.isdigit() else 0

                price_str = row.get("Price", "").strip()
                price = None
                if price_str:
                    with contextlib.suppress(ValueError):
                        price = float(price_str.replace("$", "").strip())

                conn.execute(
                    """INSERT OR REPLACE INTO parts
                    (lcsc_part, mfr_part, package, description, classification,
                     stock, category, subcategory, price_usd)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row.get("LCSC Part #", "").strip(),
                        row.get("MFR.Part #", "").strip(),
                        row.get("Package", "").strip(),
                        row.get("Description", "").strip(),
                        cls,
                        stock,
                        row.get("First Category", "").strip(),
                        row.get("Second Category", "").strip(),
                        price,
                    ),
                )
                count += 1

        conn.commit()
        return count

    def search_by_value(
        self,
        value: str,
        category: str | None = None,
        basic_only: bool = False,
        min_stock: int = 0,
    ) -> list[JLCPCBPart]:
        """Search for parts matching a value string."""
        conn = self._get_conn()

        query = "SELECT * FROM parts WHERE (mfr_part LIKE ? OR description LIKE ?)"
        params: list[str | int] = [f"%{value}%", f"%{value}%"]

        if category:
            query += " AND category LIKE ?"
            params.append(f"%{category}%")

        if basic_only:
            query += " AND classification = 'basic'"

        if min_stock > 0:
            query += " AND stock >= ?"
            params.append(min_stock)

        query += " ORDER BY classification ASC, stock DESC LIMIT 20"

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_part(row) for row in rows]

    def get_by_lcsc(self, lcsc_part: str) -> JLCPCBPart | None:
        """Look up a part by its LCSC part number (e.g., C17414)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM parts WHERE lcsc_part = ?", (lcsc_part,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_part(row)

    def count_parts(self) -> int:
        """Return total number of parts in the database."""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM parts").fetchone()
        return row[0] if row else 0

    def count_basic_parts(self) -> int:
        """Return number of basic (no setup fee) parts."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM parts WHERE classification = 'basic'"
        ).fetchone()
        return row[0] if row else 0

    def _row_to_part(self, row: sqlite3.Row) -> JLCPCBPart:
        cls_str = row["classification"]
        if cls_str == "basic":
            cls = PartClassification.BASIC
        elif cls_str == "extended":
            cls = PartClassification.EXTENDED
        else:
            cls = PartClassification.UNKNOWN

        return JLCPCBPart(
            lcsc_part=row["lcsc_part"],
            mfr_part=row["mfr_part"],
            package=row["package"],
            description=row["description"],
            classification=cls,
            stock=row["stock"],
            category=row["category"],
            subcategory=row["subcategory"],
            price_usd=row["price_usd"],
        )
