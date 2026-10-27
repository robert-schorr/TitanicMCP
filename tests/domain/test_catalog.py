from __future__ import annotations

import pytest

from titanic_mcp.database import Database
from titanic_mcp.errors import QueryValidationError
from titanic_mcp.models import ColumnType, FilterOperator, TableKind
from titanic_mcp.queries import (
    NUMERIC_OPERATORS,
    TABLES,
    TEXT_OPERATORS,
    describe_table,
    get_table_spec,
    list_tables,
)

EXPECTED_TABLES = [
    "passengers",
    "Observation",
    "Sex",
    "Embarked",
    "Class",
    "Who",
    "Deck",
    "EmbarkTown",
    "Alive",
]

EXPECTED_COUNTS = [891, 891, 2, 4, 3, 3, 8, 4, 2]

PASSENGER_COLUMNS = [
    "passenger_id",
    "survived",
    "pclass",
    "sex",
    "age",
    "sibsp",
    "parch",
    "fare",
    "embarked",
    "class",
    "who",
    "adult_male",
    "deck",
    "embark_town",
    "alive",
    "alone",
]

RAW_COLUMNS = {
    "Observation": [
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
    ],
    "Sex": ["sex_id", "sex"],
    "Embarked": ["embarked_id", "embarked"],
    "Class": ["class_id", "class"],
    "Who": ["who_id", "who"],
    "Deck": ["deck_id", "deck"],
    "EmbarkTown": ["embark_town_id", "embark_town"],
    "Alive": ["alive_id", "alive"],
}


def test_catalog_has_nine_entries_in_order() -> None:
    assert list(TABLES) == EXPECTED_TABLES
    assert len(TABLES) == 9


def test_catalog_entries_have_complete_metadata() -> None:
    for name, spec in TABLES.items():
        assert spec.name == name
        assert spec.description
        assert spec.source_sql
        assert spec.source_sql.strip().upper().startswith("SELECT")
        column_names = [column.name for column in spec.columns]
        assert len(column_names) == len(set(column_names))
        assert spec.default_order_by in column_names
        assert spec.tiebreaker in column_names
        assert all(column.description for column in spec.columns)
        assert all(column.allowed_operators for column in spec.columns)

    assert TABLES["passengers"].kind is TableKind.view
    assert TABLES["passengers"].recommended is True
    assert all(
        spec.kind is TableKind.table and spec.recommended is False
        for name, spec in TABLES.items()
        if name != "passengers"
    )


def test_passenger_columns_types_and_nullability() -> None:
    spec = TABLES["passengers"]

    assert [column.name for column in spec.columns] == PASSENGER_COLUMNS
    assert spec.default_order_by == "passenger_id"

    types = {column.name: column.type for column in spec.columns}
    assert types == {
        "passenger_id": ColumnType.integer,
        "survived": ColumnType.integer,
        "pclass": ColumnType.integer,
        "sex": ColumnType.text,
        "age": ColumnType.number,
        "sibsp": ColumnType.integer,
        "parch": ColumnType.integer,
        "fare": ColumnType.number,
        "embarked": ColumnType.text,
        "class": ColumnType.text,
        "who": ColumnType.text,
        "adult_male": ColumnType.boolean,
        "deck": ColumnType.text,
        "embark_town": ColumnType.text,
        "alive": ColumnType.text,
        "alone": ColumnType.boolean,
    }

    nullable = {column.name: column.nullable for column in spec.columns}
    assert nullable == {
        "passenger_id": False,
        "survived": False,
        "pclass": False,
        "sex": False,
        "age": True,
        "sibsp": False,
        "parch": False,
        "fare": False,
        "embarked": True,
        "class": False,
        "who": False,
        "adult_male": False,
        "deck": True,
        "embark_town": True,
        "alive": False,
        "alone": False,
    }


def test_raw_tables_have_expected_columns() -> None:
    for name, expected_columns in RAW_COLUMNS.items():
        spec = TABLES[name]

        assert [column.name for column in spec.columns] == expected_columns
        assert spec.kind is TableKind.table
        assert spec.recommended is False
        assert spec.default_order_by == expected_columns[0]
        assert spec.tiebreaker == expected_columns[0]


def test_operator_allowlists_follow_column_types() -> None:
    for spec in TABLES.values():
        for column in spec.columns:
            if column.type is ColumnType.text:
                assert column.allowed_operators == TEXT_OPERATORS
            else:
                assert column.allowed_operators == NUMERIC_OPERATORS

    assert FilterOperator.gt not in TEXT_OPERATORS
    assert FilterOperator.gt in NUMERIC_OPERATORS


def test_get_table_spec_returns_the_registry_entry() -> None:
    assert get_table_spec("passengers") is TABLES["passengers"]


def test_get_table_spec_rejects_unknown_tables() -> None:
    with pytest.raises(QueryValidationError) as exc_info:
        get_table_spec("sqlite_master")

    assert exc_info.value.field_paths == ("table",)
    assert "sqlite_master" in exc_info.value.detail


def test_list_tables_returns_nine_entries_with_counts(database: Database) -> None:
    summaries = list_tables(database)

    assert [summary.name for summary in summaries] == EXPECTED_TABLES
    assert [summary.row_count for summary in summaries] == EXPECTED_COUNTS
    assert [summary.recommended for summary in summaries] == [
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    ]
    assert [summary.kind for summary in summaries] == [TableKind.view] + [
        TableKind.table
    ] * 8
    assert all(summary.description for summary in summaries)


def test_describe_passengers_metadata(database: Database) -> None:
    description = describe_table(database, "passengers")

    assert description.name == "passengers"
    assert description.kind is TableKind.view
    assert description.row_count == 891
    assert description.default_order_by == "passenger_id"
    assert [column.name for column in description.columns] == PASSENGER_COLUMNS
    assert all(column.description for column in description.columns)
    assert {column.name for column in description.columns if column.nullable} == {
        "age",
        "embarked",
        "deck",
        "embark_town",
    }


def test_describe_sex_metadata(database: Database) -> None:
    description = describe_table(database, "Sex")

    assert description.name == "Sex"
    assert description.kind is TableKind.table
    assert description.row_count == 2
    assert description.default_order_by == "sex_id"
    assert [column.name for column in description.columns] == ["sex_id", "sex"]


def test_describe_table_rejects_unknown_tables(database: Database) -> None:
    with pytest.raises(QueryValidationError) as exc_info:
        describe_table(database, "not_a_table")

    assert exc_info.value.field_paths == ("table",)
    assert "not_a_table" in exc_info.value.detail
