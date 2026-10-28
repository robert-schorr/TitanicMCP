from __future__ import annotations

from typing import cast

from titanic_mcp.database import Database
from titanic_mcp.models import QueryDataInput
from titanic_mcp.queries import describe_table, query_data

EXPECTED_FIRST_ROW = {
    "passenger_id": 1,
    "survived": 0,
    "pclass": 3,
    "sex": "male",
    "age": 22.0,
    "sibsp": 1,
    "parch": 0,
    "fare": 7.25,
    "embarked": "S",
    "class": "Third",
    "who": "man",
    "adult_male": 1,
    "deck": None,
    "embark_town": "Southampton",
    "alive": "no",
    "alone": 0,
}


def test_passenger_row_count(database: Database) -> None:
    description = describe_table(database, "passengers")

    assert description.row_count == 891


def test_integer_filter_accepts_sqlite_boundaries(database: Database) -> None:
    for value in (-(2**63), 2**63 - 1):
        response = query_data(
            database,
            QueryDataInput(
                table="passengers",
                filter=[{"column": "passenger_id", "op": "eq", "value": value}],
                limit=1,
            ),
        )

        assert response.row_count == 0


def test_documented_first_row(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(table="passengers", limit=1),
    )

    assert response.rows == [EXPECTED_FIRST_ROW]
    assert type(response.rows[0]["survived"]) is int
    assert type(response.rows[0]["pclass"]) is int
    assert type(response.rows[0]["adult_male"]) is int
    assert type(response.rows[0]["alone"]) is int


def test_deck_null_and_non_null_counts(database: Database) -> None:
    first_page = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id"],
            filter=[{"column": "deck", "op": "is_null"}],
            limit=500,
        ),
    )
    second_page = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id"],
            filter=[{"column": "deck", "op": "is_null"}],
            limit=500,
            offset=500,
        ),
    )
    non_null = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id"],
            filter=[{"column": "deck", "op": "not_null"}],
            limit=500,
        ),
    )

    assert first_page.row_count + second_page.row_count == 688
    assert first_page.truncated is True
    assert second_page.truncated is False
    assert non_null.row_count == 203
    assert non_null.truncated is False


def test_sentinel_categories_become_null(database: Database) -> None:
    by_embarked = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id", "embarked", "embark_town"],
            filter=[{"column": "embarked", "op": "is_null"}],
            limit=10,
        ),
    )
    by_embark_town = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id", "embarked", "embark_town"],
            filter=[{"column": "embark_town", "op": "is_null"}],
            limit=10,
        ),
    )

    expected_rows = [
        {"passenger_id": 62, "embarked": None, "embark_town": None},
        {"passenger_id": 830, "embarked": None, "embark_town": None},
    ]
    assert by_embarked.rows == expected_rows
    assert by_embark_town.rows == expected_rows


def test_passenger_ids_are_unique(database: Database) -> None:
    first_page = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id"],
            limit=500,
            offset=0,
        ),
    )
    second_page = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id"],
            limit=500,
            offset=500,
        ),
    )

    passenger_ids = [
        cast(int, row["passenger_id"]) for row in first_page.rows + second_page.rows
    ]

    assert len(passenger_ids) == 891
    assert len(set(passenger_ids)) == 891
    assert min(passenger_ids) == 1
    assert max(passenger_ids) == 891


def test_decoded_labels_use_lookup_values(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["sex", "class", "who", "alive"],
            limit=500,
        ),
    )

    assert {row["sex"] for row in response.rows} <= {"female", "male"}
    assert {row["class"] for row in response.rows} <= {"First", "Second", "Third"}
    assert {row["who"] for row in response.rows} <= {"child", "man", "woman"}
    assert {row["alive"] for row in response.rows} <= {"no", "yes"}
