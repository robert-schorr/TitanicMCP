from __future__ import annotations

import pytest

from titanic_mcp.database import Database
from titanic_mcp.models import ColumnType
from titanic_mcp.queries import TABLES, ColumnSpec, TableSpec

SQLITE_TYPE_TO_COLUMN_TYPE = {
    "BIGINT": ColumnType.integer,
    "FLOAT": ColumnType.number,
    "BOOLEAN": ColumnType.boolean,
    "TEXT": ColumnType.text,
}

RAW_TABLE_NAMES = [name for name in TABLES if name != "passengers"]


def _catalog_columns_for_pragma(spec: TableSpec) -> list[ColumnSpec]:
    return [
        column
        for column in spec.columns
        if not (spec.name == "Observation" and column.name == "passenger_id")
    ]


@pytest.mark.parametrize("table_name", RAW_TABLE_NAMES)
def test_catalog_matches_pragma_schema(database: Database, table_name: str) -> None:
    spec = TABLES[table_name]
    pragma_columns = database.fetch_all(f'PRAGMA table_info("{table_name}")')
    catalog_columns = _catalog_columns_for_pragma(spec)

    assert [column.name for column in catalog_columns] == [
        row["name"] for row in pragma_columns
    ]

    for column, pragma_column in zip(catalog_columns, pragma_columns, strict=True):
        assert column.type is SQLITE_TYPE_TO_COLUMN_TYPE[pragma_column["type"]]
        assert column.nullable is (pragma_column["notnull"] == 0)


def test_observation_synthetic_passenger_id(database: Database) -> None:
    spec = TABLES["Observation"]
    pragma_names = {
        row["name"] for row in database.fetch_all('PRAGMA table_info("Observation")')
    }

    passenger_id = spec.columns[0]
    assert passenger_id.name == "passenger_id"
    assert passenger_id.type is ColumnType.integer
    assert passenger_id.nullable is False
    assert passenger_id.name not in pragma_names


@pytest.mark.parametrize("table_name", list(TABLES))
def test_every_source_sql_matches_catalog_columns(
    database: Database,
    table_name: str,
) -> None:
    spec = TABLES[table_name]

    assert "?" not in spec.source_sql

    with database.connect() as connection:
        cursor = connection.execute(
            f"SELECT * FROM ({spec.source_sql}) AS source LIMIT 0"
        )
        source_columns = [description[0] for description in cursor.description or ()]

    assert source_columns == [column.name for column in spec.columns]


def test_passengers_nullability_matches_data(database: Database) -> None:
    spec = TABLES["passengers"]
    nullable_names = [column.name for column in spec.columns if column.nullable]
    non_nullable_names = [column.name for column in spec.columns if not column.nullable]

    null_predicate = " OR ".join(f'"{name}" IS NULL' for name in non_nullable_names)
    row = database.fetch_one(
        f"SELECT COUNT(*) AS count FROM ({spec.source_sql}) AS source "
        f"WHERE {null_predicate}"
    )
    assert row == {"count": 0}

    for name in nullable_names:
        row = database.fetch_one(
            f"SELECT COUNT(*) AS count FROM ({spec.source_sql}) AS source "
            f'WHERE "{name}" IS NULL'
        )
        assert row is not None
        assert row["count"] > 0
