"""Adapter for the community jlcparts SQLite database (7M+ parts).

Wraps the jlcparts cache.sqlite3 database (from yaqwsx/jlcparts) and
exposes it through our JLCPCBPartInfo interface. This is the production
data source replacing our 35-part seed database.

The jlcparts schema differs from our internal schema:
- `basic` column: 1 = basic, 0 = extended
- `lcsc` column: integer (e.g., 1002), not string (e.g., "C1002")
- `price` column: JSON array of quantity price breaks
- `extra` column: JSON with full LCSC part number
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from etchant.core.component_selector import JLCPCBPartInfo, PartClassification


class JLCPartsAdapter:
    """Read-only adapter for the jlcparts cache.sqlite3 database."""

    def __init__(self, db_path: Path) -> None:
        if not db_path.exists():
            raise FileNotFoundError(f"jlcparts database not found: {db_path}")
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._ensure_indexes()
        return self._conn

    def _ensure_indexes(self) -> None:
        """Create indexes for fast queries (idempotent, runs once)."""
        conn = self._conn
        if conn is None:
            return
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_comp_basic ON components(basic)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_comp_mfr ON components(mfr)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_comp_stock ON components(stock)"
        )
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def search(
        self,
        query: str,
        basic_only: bool = False,
        min_stock: int = 0,
        limit: int = 20,
    ) -> list[JLCPCBPartInfo]:
        """Search parts by manufacturer part number or description."""
        conn = self._get_conn()

        sql = """
            SELECT c.lcsc, c.mfr, c.description, c.basic, c.stock, c.package,
                   c.extra, cat.category, cat.subcategory
            FROM components c
            LEFT JOIN categories cat ON c.category_id = cat.id
            WHERE (c.mfr LIKE ? OR c.description LIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if basic_only:
            sql += " AND c.basic = 1"

        if min_stock > 0:
            sql += " AND c.stock >= ?"
            params.append(min_stock)

        # Prefer basic parts, then sort by stock
        sql += " ORDER BY c.basic DESC, c.stock DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_info(row) for row in rows]

    def get_by_lcsc_number(self, lcsc_number: int) -> JLCPCBPartInfo | None:
        """Look up by LCSC number (integer, e.g., 17414 for C17414)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT lcsc, mfr, description, basic, stock, package, extra "
            "FROM components WHERE lcsc = ?",
            (lcsc_number,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_info(row)

    def get_by_lcsc_string(self, lcsc_str: str) -> JLCPCBPartInfo | None:
        """Look up by LCSC string (e.g., "C17414")."""
        if lcsc_str.startswith("C") and lcsc_str[1:].isdigit():
            return self.get_by_lcsc_number(int(lcsc_str[1:]))
        return None

    def count_total(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM components").fetchone()
        return row[0] if row else 0

    def count_basic(self) -> int:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM components WHERE basic = 1"
        ).fetchone()
        return row[0] if row else 0

    def count_in_stock(self, min_stock: int = 1) -> int:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM components WHERE stock >= ?",
            (min_stock,),
        ).fetchone()
        return row[0] if row else 0

    def _row_to_info(self, row: sqlite3.Row) -> JLCPCBPartInfo:
        lcsc_num = row["lcsc"]
        part_number = f"C{lcsc_num}"

        classification = (
            PartClassification.BASIC if row["basic"] == 1
            else PartClassification.EXTENDED
        )

        return JLCPCBPartInfo(
            part_number=part_number,
            classification=classification,
            description=row["description"] or "",
            stock=row["stock"] or 0,
        )
