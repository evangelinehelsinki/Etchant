"""Adapter for JLCPCB parts databases.

Supports two database formats:
1. Our extracted power_parts.db (60 MB, 237K parts, fast)
2. The full jlcparts cache.sqlite3 (12 GB, 7M parts, slow without mmap)

Auto-detects the schema on first connection.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from etchant.core.component_selector import JLCPCBPartInfo, PartClassification


class JLCPartsAdapter:
    """Read-only adapter for JLCPCB parts databases."""

    def __init__(self, db_path: Path) -> None:
        if not db_path.exists():
            raise FileNotFoundError(f"JLCPCB database not found: {db_path}")
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._schema: str | None = None  # "extracted" or "jlcparts"

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._detect_schema()
        return self._conn

    def _detect_schema(self) -> None:
        """Detect whether this is our extracted DB or the jlcparts cache."""
        conn = self._conn
        if conn is None:
            return
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}

        if "parts" in table_names:
            self._schema = "extracted"
        elif "components" in table_names:
            self._schema = "jlcparts"
        else:
            raise ValueError(f"Unknown database schema: tables = {table_names}")

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
        """Search parts by manufacturer part number."""
        conn = self._get_conn()

        if self._schema == "extracted":
            return self._search_extracted(conn, query, basic_only, min_stock, limit)
        return self._search_jlcparts(conn, query, basic_only, min_stock, limit)

    def _search_extracted(
        self,
        conn: sqlite3.Connection,
        query: str,
        basic_only: bool,
        min_stock: int,
        limit: int,
    ) -> list[JLCPCBPartInfo]:
        sql = "SELECT * FROM parts WHERE mfr_part LIKE ?"
        params: list[Any] = [f"{query}%"]

        if basic_only:
            sql += " AND classification = 'basic'"
        if min_stock > 0:
            sql += " AND stock >= ?"
            params.append(min_stock)

        sql += " ORDER BY classification ASC, stock DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [
            JLCPCBPartInfo(
                part_number=r["lcsc_part"],
                classification=(
                    PartClassification.BASIC
                    if r["classification"] == "basic"
                    else PartClassification.EXTENDED
                ),
                description=r["description"] or "",
                stock=r["stock"] or 0,
            )
            for r in rows
        ]

    def _search_jlcparts(
        self,
        conn: sqlite3.Connection,
        query: str,
        basic_only: bool,
        min_stock: int,
        limit: int,
    ) -> list[JLCPCBPartInfo]:
        sql = "SELECT lcsc, mfr, description, basic, stock FROM components WHERE mfr LIKE ?"
        params: list[Any] = [f"{query}%"]

        if basic_only:
            sql += " AND basic = 1"
        if min_stock > 0:
            sql += " AND stock >= ?"
            params.append(min_stock)

        sql += " ORDER BY basic DESC, stock DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [
            JLCPCBPartInfo(
                part_number=f"C{r['lcsc']}",
                classification=(
                    PartClassification.BASIC if r["basic"] == 1
                    else PartClassification.EXTENDED
                ),
                description=r["description"] or "",
                stock=r["stock"] or 0,
            )
            for r in rows
        ]

    def get_by_lcsc_string(self, lcsc_str: str) -> JLCPCBPartInfo | None:
        """Look up by LCSC string (e.g., "C17414")."""
        conn = self._get_conn()

        if self._schema == "extracted":
            row = conn.execute(
                "SELECT * FROM parts WHERE lcsc_part = ?", (lcsc_str,)
            ).fetchone()
            if row is None:
                return None
            return JLCPCBPartInfo(
                part_number=row["lcsc_part"],
                classification=(
                    PartClassification.BASIC
                    if row["classification"] == "basic"
                    else PartClassification.EXTENDED
                ),
                description=row["description"] or "",
                stock=row["stock"] or 0,
            )

        # jlcparts schema
        if lcsc_str.startswith("C") and lcsc_str[1:].isdigit():
            lcsc_num = int(lcsc_str[1:])
            row = conn.execute(
                "SELECT lcsc, mfr, description, basic, stock "
                "FROM components WHERE lcsc = ?",
                (lcsc_num,),
            ).fetchone()
            if row is None:
                return None
            return JLCPCBPartInfo(
                part_number=f"C{row['lcsc']}",
                classification=(
                    PartClassification.BASIC if row["basic"] == 1
                    else PartClassification.EXTENDED
                ),
                description=row["description"] or "",
                stock=row["stock"] or 0,
            )
        return None

    def count_total(self) -> int:
        conn = self._get_conn()
        table = "parts" if self._schema == "extracted" else "components"
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
