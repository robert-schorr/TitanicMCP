from __future__ import annotations

import pytest

from titanic_mcp.database import Database
from titanic_mcp.models import QueryDataInput
from titanic_mcp.queries import TABLES, query_data

RAW_TABLES = [name for name in TABLES if name != "passengers"]
LOOKUP_TABLES = ["Sex", "Embarked", "Class", "Who", "Deck", "EmbarkTown", "Alive"]


def test_observation_passenger_id_aliases_rowid(database: Database) -> None:
    spec = TABLES["Observation"]
    rowids = database.fetch_all(
        'SELECT rowid AS row_id FROM "Observation" ORDER BY rowid'
    )
    source_ids = database.fetch_all(
        f"SELECT passenger_id FROM ({spec.source_sql}) AS source ORDER BY passenger_id"
    )

    assert [row["passenger_id"] for row in source_ids] == [
        row["row_id"] for row in rowids
    ]

    response = query_data(
        database,
        QueryDataInput(
            table="Observation",
            columns=["passenger_id", "survived"],
            filter=[{"column": "passenger_id", "op": "eq", "value": 1}],
            limit=1,
        ),
    )
    assert response.rows == [{"passenger_id": 1, "survived": 0}]


@pytest.mark.parametrize("table_name", LOOKUP_TABLES)
def test_lookup_tables_expose_id_and_label_pairs(
    database: Database,
    table_name: str,
) -> None:
    spec = TABLES[table_name]
    id_column = spec.default_order_by
    expected = database.fetch_all(
        f'SELECT * FROM "{table_name}" ORDER BY "{id_column}"'
    )

    response = query_data(
        database,
        QueryDataInput(table=table_name, limit=100),
    )

    assert response.columns == [column.name for column in spec.columns]
    assert response.rows == expected


def test_sex_lookup_pairs(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(table="Sex", limit=10),
    )

    assert response.rows == [
        {"sex_id": 0, "sex": "female"},
        {"sex_id": 1, "sex": "male"},
    ]


@pytest.mark.parametrize("table_name", RAW_TABLES)
def test_all_raw_tables_are_queryable(database: Database, table_name: str) -> None:
    spec = TABLES[table_name]

    response = query_data(
        database,
        QueryDataInput(table=table_name, limit=1),
    )

    assert response.table == table_name
    assert response.columns == [column.name for column in spec.columns]
    assert response.row_count == 1
    assert list(response.rows[0]) == [column.name for column in spec.columns]


def test_observation_exposes_original_columns(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(table="Observation", limit=1),
    )

    assert response.columns == [
        "passenger_id",
        "survived",
        "pclass",
        "age",
        "sibsp",
        "parch",
        "fare",
        "adult_male",
        "alone",
        "sex_id",
        "embarked_id",
        "class_id",
        "who_id",
        "deck_id",
        "embark_town_id",
        "alive_id",
    ]
