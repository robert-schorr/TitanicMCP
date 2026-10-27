from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from titanic_mcp.database import Database


def test_connection_uses_read_only_uri(database: Database) -> None:
    assert database.uri.startswith("file:")
    assert database.uri.endswith("?mode=ro")


def test_fetch_all_returns_ordered_mappings(database: Database) -> None:
    rows = database.fetch_all(
        'SELECT rowid AS passenger_id, survived FROM "Observation" ORDER BY rowid LIMIT 1'
    )

    assert rows == [{"passenger_id": 1, "survived": 0}]
    assert list(rows[0]) == ["passenger_id", "survived"]


def test_fetch_one_returns_a_mapping_or_none(database: Database) -> None:
    row = database.fetch_one(
        'SELECT rowid AS passenger_id, survived FROM "Observation" WHERE rowid = ?',
        (1,),
    )

    assert row == {"passenger_id": 1, "survived": 0}
    assert (
        database.fetch_one(
            'SELECT rowid FROM "Observation" WHERE rowid = ?',
            (99_999,),
        )
        is None
    )


def test_count_uses_static_source_queries(database: Database) -> None:
    assert database.count('SELECT * FROM "Observation"') == 891
    assert database.count('SELECT * FROM "Sex"') == 2


def test_connection_sets_query_only_and_row_factory(database: Database) -> None:
    with database.connect() as connection:
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1


def test_writes_are_rejected(database: Database) -> None:
    with (
        pytest.raises(sqlite3.OperationalError, match="readonly"),
        database.connect() as connection,
    ):
        connection.execute('DELETE FROM "Observation"')


def test_missing_database_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    database = Database(path)

    with pytest.raises(sqlite3.OperationalError):
        database.count('SELECT * FROM "Observation"')

    assert not path.exists()
