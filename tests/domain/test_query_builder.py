from __future__ import annotations

import pytest

from titanic_mcp.errors import QueryValidationError
from titanic_mcp.models import (
    FilterOperator,
    FilterPredicate,
    FilterValue,
    OrderBy,
    QueryDataInput,
)
from titanic_mcp.queries import TABLES, compile_query, validate_query


def _expect_invalid(request: QueryDataInput, field_path: str) -> None:
    with pytest.raises(QueryValidationError) as exc_info:
        validate_query(request)

    assert exc_info.value.field_paths == (field_path,)


def test_valid_request_returns_table_spec() -> None:
    request = QueryDataInput(
        table="passengers",
        columns=["sex", "age"],
        filter=[{"column": "age", "op": "gte", "value": 30}],
        order_by={"column": "fare", "direction": "desc"},
        limit=10,
        offset=5,
    )

    assert validate_query(request) is TABLES["passengers"]


def test_unknown_table_is_rejected() -> None:
    _expect_invalid(QueryDataInput(table="unknown"), "table")


def test_unknown_selected_column_is_rejected() -> None:
    _expect_invalid(
        QueryDataInput(table="passengers", columns=["sex", "nope"]),
        "columns[1]",
    )


def test_unknown_filter_column_is_rejected() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "nope", "op": "eq", "value": "x"}],
        ),
        "filter[0].column",
    )


def test_unknown_order_column_is_rejected() -> None:
    _expect_invalid(
        QueryDataInput(table="passengers", order_by={"column": "nope"}),
        "order_by.column",
    )


def test_text_range_operator_is_rejected() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "sex", "op": "gt", "value": "male"}],
        ),
        "filter[0].op",
    )


def test_numeric_range_operator_is_accepted() -> None:
    request = QueryDataInput(
        table="passengers",
        filter=[{"column": "age", "op": "gte", "value": 30}],
    )

    validate_query(request)


def test_text_membership_and_null_filters_are_accepted() -> None:
    request = QueryDataInput(
        table="passengers",
        filter=[
            {"column": "sex", "op": "in", "value": ["male", "female"]},
            {"column": "deck", "op": "is_null"},
            {"column": "embarked", "op": "not_null"},
        ],
    )

    validate_query(request)


@pytest.mark.parametrize("operator", list(FilterOperator))
def test_numeric_columns_accept_every_operator(operator: FilterOperator) -> None:
    if operator is FilterOperator.in_:
        value: FilterValue = [30]
    elif operator in {FilterOperator.is_null, FilterOperator.not_null}:
        value = None
    else:
        value = 30

    request = QueryDataInput(
        table="passengers",
        filter=[FilterPredicate(column="age", op=operator, value=value)],
    )

    validate_query(request)


@pytest.mark.parametrize(
    "operator",
    [
        FilterOperator.eq,
        FilterOperator.ne,
        FilterOperator.in_,
        FilterOperator.is_null,
        FilterOperator.not_null,
    ],
)
def test_text_columns_accept_only_the_text_allowlist(
    operator: FilterOperator,
) -> None:
    value = ["male"] if operator is FilterOperator.in_ else "male"
    if operator in {FilterOperator.is_null, FilterOperator.not_null}:
        value = None

    request = QueryDataInput(
        table="passengers",
        filter=[FilterPredicate(column="sex", op=operator, value=value)],
    )

    validate_query(request)


def test_type_mismatch_is_rejected() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "pclass", "op": "eq", "value": "First"}],
        ),
        "filter[0].value",
    )


def test_integer_columns_reject_floats_and_booleans() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "pclass", "op": "eq", "value": 1.0}],
        ),
        "filter[0].value",
    )
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "pclass", "op": "eq", "value": True}],
        ),
        "filter[0].value",
    )


def test_number_columns_accept_integers_and_floats() -> None:
    for value in (30, 30.5):
        validate_query(
            QueryDataInput(
                table="passengers",
                filter=[{"column": "age", "op": "gte", "value": value}],
            )
        )


def test_boolean_columns_accept_booleans_and_zero_one() -> None:
    for value in (True, False, 0, 1):
        validate_query(
            QueryDataInput(
                table="passengers",
                filter=[{"column": "adult_male", "op": "eq", "value": value}],
            )
        )

    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "adult_male", "op": "eq", "value": 2}],
        ),
        "filter[0].value",
    )


def test_null_operators_reject_values() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "deck", "op": "is_null", "value": "A"}],
        ),
        "filter[0].value",
    )
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "deck", "op": "not_null", "value": ["A"]}],
        ),
        "filter[0].value",
    )


def test_eq_null_is_rejected() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "deck", "op": "eq", "value": None}],
        ),
        "filter[0].value",
    )


def test_scalar_operators_reject_lists() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "age", "op": "eq", "value": [30]}],
        ),
        "filter[0].value",
    )


def test_in_requires_a_list() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "sex", "op": "in", "value": "male"}],
        ),
        "filter[0].value",
    )


def test_in_value_count_bounds() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "sex", "op": "in", "value": []}],
        ),
        "filter[0].value",
    )
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[
                {
                    "column": "sex",
                    "op": "in",
                    "value": ["male"] * 101,
                }
            ],
        ),
        "filter[0].value",
    )


def test_in_values_reject_null_and_mismatched_types() -> None:
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "sex", "op": "in", "value": ["male", None]}],
        ),
        "filter[0].value[1]",
    )
    _expect_invalid(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "sex", "op": "in", "value": ["male", 1]}],
        ),
        "filter[0].value[1]",
    )


def test_predicate_limit() -> None:
    predicates = [
        FilterPredicate(column="age", op=FilterOperator.gte, value=index)
        for index in range(20)
    ]
    validate_query(QueryDataInput(table="passengers", filter=predicates))

    predicates.append(FilterPredicate(column="age", op=FilterOperator.lte, value=100))
    _expect_invalid(QueryDataInput(table="passengers", filter=predicates), "filter")


def test_order_by_accepts_catalog_columns() -> None:
    validate_query(QueryDataInput(table="passengers", order_by=OrderBy(column="age")))


def test_compile_query_builds_static_sql_and_ordered_params() -> None:
    request = QueryDataInput(
        table="passengers",
        columns=["sex", "passenger_id"],
        filter=[
            {"column": "age", "op": "gte", "value": 30},
            {"column": "sex", "op": "eq", "value": "female"},
        ],
        order_by={"column": "fare", "direction": "desc"},
        limit=5,
        offset=10,
    )

    compiled = compile_query(request)

    assert compiled.columns == ["sex", "passenger_id"]
    assert compiled.fetch_limit == 6
    assert compiled.params == (30, "female", 6, 10)
    assert 'SELECT "sex", "passenger_id"' in compiled.sql
    assert "FROM (" in compiled.sql
    assert 'WHERE "age" >= ? AND "sex" = ?' in compiled.sql
    assert (
        'ORDER BY ("fare" IS NULL) ASC, "fare" DESC, "passenger_id" ASC' in compiled.sql
    )
    assert compiled.sql.endswith("LIMIT ? OFFSET ?")
    assert "female" not in compiled.sql
    assert "30" not in compiled.sql


def test_compile_query_expands_in_placeholders() -> None:
    compiled = compile_query(
        QueryDataInput(
            table="passengers",
            filter=[
                {
                    "column": "class",
                    "op": "in",
                    "value": ["First", "Second"],
                }
            ],
            limit=1,
        )
    )

    assert '"class" IN (?, ?)' in compiled.sql
    assert compiled.params == ("First", "Second", 2, 0)


def test_compile_query_handles_null_filters_without_params() -> None:
    is_null = compile_query(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "deck", "op": "is_null"}],
            limit=1,
        )
    )
    not_null = compile_query(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "deck", "op": "not_null"}],
            limit=1,
        )
    )

    assert '"deck" IS NULL' in is_null.sql
    assert is_null.params == (2, 0)
    assert '"deck" IS NOT NULL' in not_null.sql
    assert not_null.params == (2, 0)


def test_compile_query_defaults_to_catalog_order() -> None:
    compiled = compile_query(QueryDataInput(table="passengers", limit=1))

    assert compiled.columns == [
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
    assert 'ORDER BY "passenger_id" ASC' in compiled.sql


def test_compile_query_adds_null_last_and_tiebreaker() -> None:
    compiled = compile_query(
        QueryDataInput(
            table="passengers",
            order_by={"column": "age", "direction": "asc"},
            limit=1,
        )
    )

    assert 'ORDER BY ("age" IS NULL) ASC, "age" ASC, "passenger_id" ASC' in compiled.sql


def test_compile_query_omits_duplicate_tiebreaker() -> None:
    compiled = compile_query(
        QueryDataInput(
            table="passengers",
            order_by={"column": "passenger_id", "direction": "desc"},
            limit=1,
        )
    )

    assert 'ORDER BY ("passenger_id" IS NULL) ASC, "passenger_id" DESC' in compiled.sql


def test_compile_query_uses_lookup_tiebreaker() -> None:
    compiled = compile_query(
        QueryDataInput(
            table="Sex",
            order_by={"column": "sex", "direction": "desc"},
            limit=1,
        )
    )

    assert 'ORDER BY ("sex" IS NULL) ASC, "sex" DESC, "sex_id" ASC' in compiled.sql


def test_compile_query_never_embeds_filter_values() -> None:
    value = "male' OR 1=1 --"

    compiled = compile_query(
        QueryDataInput(
            table="passengers",
            filter=[{"column": "sex", "op": "eq", "value": value}],
            limit=1,
        )
    )

    assert value not in compiled.sql
    assert compiled.params == (value, 2, 0)


def test_compile_query_uses_fetch_limit_one_greater_than_limit() -> None:
    compiled = compile_query(QueryDataInput(table="passengers", limit=500))

    assert compiled.fetch_limit == 501
    assert compiled.params == (501, 0)
