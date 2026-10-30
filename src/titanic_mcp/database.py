from __future__ import annotations

import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class Database:
    """Read-only SQLite access for the Titanic database.

    A fresh connection is opened for each operation. The URI forces SQLite into
    read-only mode and ``PRAGMA query_only`` provides defense in depth.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.uri = f"{self.path.as_uri()}?mode=ro"

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection]:
        """Open a short-lived read-only connection."""

        connection = sqlite3.connect(self.uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            yield connection
        finally:
            connection.close()

    def fetch_all(
        self, sql: str, params: Sequence[object] = ()
    ) -> list[dict[str, Any]]:
        """Execute a read query and return rows as ordered mappings."""

        with self.connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def fetch_one(
        self, sql: str, params: Sequence[object] = ()
    ) -> dict[str, Any] | None:
        """Execute a read query and return the first row, if any."""

        with self.connect() as connection:
            row = connection.execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def count(self, source_sql: str) -> int:
        """Count the rows produced by a static catalog source query."""

        with self.connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) FROM ({source_sql}) AS source"  # nosec B608 — wraps static catalog SQL; user values are bound params
            ).fetchone()
        # ``SELECT COUNT(*)`` always returns exactly one row.
        assert row is not None
        return int(row[0])
