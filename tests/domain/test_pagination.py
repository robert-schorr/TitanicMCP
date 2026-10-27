from __future__ import annotations

from typing import cast

from titanic_mcp.database import Database
from titanic_mcp.models import QueryDataInput
from titanic_mcp.queries import TABLES, build_response, compile_query, query_data

PASSENGER_COLUMNS = [column.name for column in TABLES["passengers"].columns]


def test_first_page(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(table="passengers", limit=5),
    )

    assert response.table == "passengers"
    assert response.columns == PASSENGER_COLUMNS
    assert response.row_count == 5
    assert len(response.rows) == 5
    assert response.limit == 5
    assert response.offset == 0
    assert response.truncated is True
    assert response.next_offset == 5


def test_final_page(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(table="passengers", limit=5, offset=890),
    )

    assert response.row_count == 1
    assert len(response.rows) == 1
    assert response.limit == 5
    assert response.offset == 890
    assert response.truncated is False
    assert response.next_offset is None


def test_offset_paging_is_stable(database: Database) -> None:
    first = query_data(
        database,
        QueryDataInput(table="passengers", limit=5, offset=0),
    )
    second = query_data(
        database,
        QueryDataInput(table="passengers", limit=5, offset=5),
    )

    first_ids = {row["passenger_id"] for row in first.rows}
    second_ids = {row["passenger_id"] for row in second.rows}

    assert len(first_ids) == 5
    assert len(second_ids) == 5
    assert first_ids.isdisjoint(second_ids)
    assert second.next_offset == 10


def test_offset_paging_is_stable_with_requested_order(database: Database) -> None:
    first = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id"],
            order_by={"column": "age", "direction": "asc"},
            limit=10,
            offset=0,
        ),
    )
    second = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id"],
            order_by={"column": "age", "direction": "asc"},
            limit=10,
            offset=10,
        ),
    )

    first_ids = {row["passenger_id"] for row in first.rows}
    second_ids = {row["passenger_id"] for row in second.rows}

    assert first_ids.isdisjoint(second_ids)


def test_requested_projection_order_is_preserved(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["sex", "passenger_id"],
            limit=1,
        ),
    )

    assert response.columns == ["sex", "passenger_id"]
    assert list(response.rows[0]) == ["sex", "passenger_id"]


def test_default_projection_uses_catalog_order(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(table="passengers", limit=1),
    )

    assert response.columns == PASSENGER_COLUMNS
    assert list(response.rows[0]) == PASSENGER_COLUMNS


def test_response_envelope_echoes_request_values(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(table="passengers", limit=7, offset=3),
    )

    assert response.row_count == len(response.rows)
    assert response.limit == 7
    assert response.offset == 3


def test_build_response_slices_limit_plus_one_rows() -> None:
    request = QueryDataInput(
        table="passengers",
        columns=["passenger_id"],
        limit=2,
        offset=4,
    )
    compiled = compile_query(request)
    rows = [
        {"passenger_id": 5},
        {"passenger_id": 6},
        {"passenger_id": 7},
    ]

    response = build_response(request, compiled, rows)

    assert [row["passenger_id"] for row in response.rows] == [5, 6]
    assert response.row_count == 2
    assert response.truncated is True
    assert response.next_offset == 6


def test_build_response_marks_the_final_page() -> None:
    request = QueryDataInput(
        table="passengers",
        columns=["passenger_id"],
        limit=5,
        offset=890,
    )
    compiled = compile_query(request)
    rows = [{"passenger_id": 891}]

    response = build_response(request, compiled, rows)

    assert [row["passenger_id"] for row in response.rows] == [891]
    assert response.truncated is False
    assert response.next_offset is None


def test_limit_500_pages(database: Database) -> None:
    first = query_data(
        database,
        QueryDataInput(table="passengers", limit=500, offset=0),
    )
    second = query_data(
        database,
        QueryDataInput(table="passengers", limit=500, offset=500),
    )

    assert first.row_count == 500
    assert first.truncated is True
    assert first.next_offset == 500
    assert second.row_count == 391
    assert second.truncated is False
    assert second.next_offset is None


def test_offset_beyond_the_end_returns_an_empty_page(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(table="passengers", limit=5, offset=10_000),
    )

    assert response.rows == []
    assert response.row_count == 0
    assert response.truncated is False
    assert response.next_offset is None


def test_descending_order_returns_non_increasing_fares(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id", "fare"],
            order_by={"column": "fare", "direction": "desc"},
            limit=20,
        ),
    )

    fares = [cast(float, row["fare"]) for row in response.rows]
    assert fares == sorted(fares, reverse=True)


def test_ties_are_broken_by_the_id_tiebreaker(database: Database) -> None:
    response = query_data(
        database,
        QueryDataInput(
            table="passengers",
            columns=["passenger_id", "survived"],
            order_by={"column": "survived", "direction": "desc"},
            limit=50,
        ),
    )

    rows = response.rows
    for index in range(1, len(rows)):
        previous, current = rows[index - 1], rows[index]
        if current["survived"] == previous["survived"]:
            assert cast(int, current["passenger_id"]) > cast(
                int, previous["passenger_id"]
            )
