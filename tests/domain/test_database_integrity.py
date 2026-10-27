from __future__ import annotations

from collections.abc import Callable
from typing import Any

from titanic_mcp.database import Database
from titanic_mcp.models import QueryDataInput
from titanic_mcp.queries import TABLES, describe_table, list_tables, query_data

RAW_TABLES = [name for name in TABLES if name != "passengers"]


def _snapshot(database: Database) -> tuple[list[tuple[Any, ...]], dict[str, int]]:
    with database.connect() as connection:
        schema = [
            tuple(row)
            for row in connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "ORDER BY type, name"
            ).fetchall()
        ]
        counts = {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in RAW_TABLES
        }
    return schema, counts


def test_core_operations_leave_database_byte_identical(
    database: Database,
    database_hash: Callable[[], str],
) -> None:
    before_hash = database_hash()
    before_schema, before_counts = _snapshot(database)

    list_tables(database)
    for table_name in TABLES:
        describe_table(database, table_name)

    query_data(
        database,
        QueryDataInput(table="passengers", limit=5),
    )
    query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id", "sex", "age"],
            filter=[
                {"column": "age", "op": "gte", "value": 30},
                {"column": "sex", "op": "eq", "value": "female"},
            ],
            order_by={"column": "fare", "direction": "desc"},
            limit=10,
        ),
    )
    query_data(
        database,
        QueryDataInput(
            table="Observation",
            columns=["passenger_id", "survived"],
            limit=5,
        ),
    )
    query_data(database, QueryDataInput(table="Sex", limit=5))

    after_hash = database_hash()
    after_schema, after_counts = _snapshot(database)

    assert after_schema == before_schema
    assert after_counts == before_counts
    assert after_hash == before_hash
