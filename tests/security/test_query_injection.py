from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from titanic_mcp.database import Database
from titanic_mcp.errors import QueryValidationError
from titanic_mcp.models import QueryDataInput
from titanic_mcp.queries import compile_query, query_data

MALICIOUS_TABLES = [
    "passengers; DROP TABLE Observation; --",
    "Observation--",
    "sqlite_master",
    "passengers UNION SELECT * FROM sqlite_master",
    '"Observation"',
]

MALICIOUS_COLUMNS = [
    'passenger_id" FROM "Observation"; --',
    "passenger_id; DROP TABLE Observation",
    "sqlite_master",
    "1",
]


@pytest.mark.parametrize("table_name", MALICIOUS_TABLES)
def test_malicious_table_names_are_rejected(
    database: Database,
    table_name: str,
) -> None:
    with pytest.raises(QueryValidationError) as exc_info:
        query_data(database, QueryDataInput(table=table_name, limit=1))

    assert exc_info.value.field_paths == ("table",)


@pytest.mark.parametrize("column_name", MALICIOUS_COLUMNS)
def test_malicious_selected_columns_are_rejected(
    database: Database,
    column_name: str,
) -> None:
    with pytest.raises(QueryValidationError) as exc_info:
        query_data(
            database,
            QueryDataInput(
                table="passengers",
                columns=[column_name],
                limit=1,
            ),
        )

    assert exc_info.value.field_paths == ("columns[0]",)


@pytest.mark.parametrize("column_name", MALICIOUS_COLUMNS)
def test_malicious_filter_columns_are_rejected(
    database: Database,
    column_name: str,
) -> None:
    with pytest.raises(QueryValidationError) as exc_info:
        query_data(
            database,
            QueryDataInput(
                table="passengers",
                filter=[{"column": column_name, "op": "eq", "value": "x"}],
                limit=1,
            ),
        )

    assert exc_info.value.field_paths == ("filter[0].column",)


@pytest.mark.parametrize("column_name", MALICIOUS_COLUMNS)
def test_malicious_ordering_columns_are_rejected(
    database: Database,
    column_name: str,
) -> None:
    with pytest.raises(QueryValidationError) as exc_info:
        query_data(
            database,
            QueryDataInput(
                table="passengers",
                order_by={"column": column_name},
                limit=1,
            ),
        )

    assert exc_info.value.field_paths == ("order_by.column",)


def test_malicious_operators_are_rejected_by_the_model() -> None:
    with pytest.raises(ValidationError):
        QueryDataInput(
            table="passengers",
            filter=[
                {
                    "column": "age",
                    "op": "eq; DROP TABLE Observation; --",
                    "value": 1,
                }
            ],
        )


def test_malicious_direction_is_rejected_by_the_model() -> None:
    with pytest.raises(ValidationError):
        QueryDataInput(
            table="passengers",
            order_by={"column": "age", "direction": "asc; DROP TABLE Observation"},
        )


def test_malicious_limit_is_rejected_by_the_model() -> None:
    with pytest.raises(ValidationError):
        QueryDataInput.model_validate(
            {"table": "passengers", "limit": "1; DROP TABLE Observation"}
        )


def test_filter_values_remain_bound_parameters(database: Database) -> None:
    value = "male' OR 1=1 --"
    request = QueryDataInput(
        table="passengers",
        filter=[{"column": "sex", "op": "eq", "value": value}],
        limit=1,
    )

    compiled = compile_query(request)

    assert value not in compiled.sql
    assert compiled.params == (value, 2, 0)

    response = query_data(database, request)
    assert response.rows == []
    assert response.row_count == 0


def test_in_values_remain_bound_parameters(database: Database) -> None:
    values = ["female", "male' OR 1=1 --"]
    request = QueryDataInput(
        table="passengers",
        columns=["passenger_id"],
        filter=[{"column": "sex", "op": "in", "value": values}],
        limit=1,
    )

    compiled = compile_query(request)

    for value in values:
        assert value not in compiled.sql
    assert compiled.params[:2] == tuple(values)

    response = query_data(database, request)
    assert [row["passenger_id"] for row in response.rows] == [2]


def test_malicious_requests_do_not_change_the_database(
    database: Database,
    database_hash: Callable[[], str],
) -> None:
    before = database_hash()

    for table_name in MALICIOUS_TABLES:
        with pytest.raises(QueryValidationError):
            query_data(database, QueryDataInput(table=table_name, limit=1))

    for column_name in MALICIOUS_COLUMNS:
        with pytest.raises(QueryValidationError):
            query_data(
                database,
                QueryDataInput(
                    table="passengers",
                    columns=[column_name],
                    limit=1,
                ),
            )

    with (
        pytest.raises(sqlite3.OperationalError, match="readonly"),
        database.connect() as connection,
    ):
        connection.execute('DROP TABLE "Observation"')

    assert database_hash() == before
