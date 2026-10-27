from __future__ import annotations

import pytest
from pydantic import ValidationError

from titanic_mcp.models import (
    ColumnMetadata,
    ColumnType,
    FilterOperator,
    FilterPredicate,
    OrderBy,
    OrderDirection,
    QueryDataInput,
    QueryResponse,
    TableDescription,
    TableKind,
    TableSummary,
)


def test_query_defaults() -> None:
    request = QueryDataInput(table="passengers")

    assert request.columns is None
    assert request.filter is None
    assert request.order_by is None
    assert request.limit == 100
    assert request.offset == 0


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        QueryDataInput.model_validate({"table": "passengers", "unexpected": True})

    with pytest.raises(ValidationError):
        FilterPredicate.model_validate(
            {"column": "age", "op": "gte", "value": 30, "unexpected": True}
        )

    with pytest.raises(ValidationError):
        OrderBy.model_validate({"column": "age", "unexpected": True})


def test_duplicate_columns_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        QueryDataInput(table="passengers", columns=["age", "sex", "age"])


def test_columns_preserve_requested_order() -> None:
    request = QueryDataInput(table="passengers", columns=["sex", "passenger_id"])

    assert request.columns == ["sex", "passenger_id"]


def test_columns_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        QueryDataInput(table="passengers", columns=[])


def test_limit_bounds() -> None:
    assert QueryDataInput(table="passengers", limit=1).limit == 1
    assert QueryDataInput(table="passengers", limit=500).limit == 500

    with pytest.raises(ValidationError):
        QueryDataInput(table="passengers", limit=0)
    with pytest.raises(ValidationError):
        QueryDataInput(table="passengers", limit=501)


def test_offset_must_be_non_negative() -> None:
    assert QueryDataInput(table="passengers", offset=0).offset == 0
    assert QueryDataInput(table="passengers", offset=890).offset == 890

    with pytest.raises(ValidationError):
        QueryDataInput(table="passengers", offset=-1)


def test_input_types_are_strict() -> None:
    with pytest.raises(ValidationError):
        QueryDataInput.model_validate({"table": "passengers", "limit": "10"})

    with pytest.raises(ValidationError):
        QueryDataInput.model_validate({"table": "passengers", "offset": 1.0})


def test_filter_shape() -> None:
    request = QueryDataInput(
        table="passengers",
        filter=[
            {"column": "age", "op": "gte", "value": 30},
            {"column": "class", "op": "in", "value": ["First", "Second"]},
            {"column": "deck", "op": "is_null"},
        ],
    )

    assert request.filter is not None
    assert request.filter[0].op is FilterOperator.gte
    assert request.filter[1].value == ["First", "Second"]
    assert request.filter[2].value is None


def test_unknown_operator_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FilterPredicate(column="age", op="between", value=30)  # type: ignore[arg-type]


def test_order_by_shape() -> None:
    order = OrderBy(column="fare", direction="desc")

    assert order.column == "fare"
    assert order.direction is OrderDirection.desc
    assert OrderBy(column="age").direction is OrderDirection.asc


def test_metadata_models() -> None:
    column = ColumnMetadata(
        name="age",
        type="number",
        nullable=True,
        description="Age in years.",
    )
    summary = TableSummary(
        name="passengers",
        kind="view",
        description="Passenger view.",
        row_count=891,
        recommended=True,
    )
    description = TableDescription(
        name="passengers",
        kind=TableKind.view,
        description="Passenger view.",
        row_count=891,
        default_order_by="passenger_id",
        columns=[column],
    )

    assert column.type is ColumnType.number
    assert summary.kind is TableKind.view
    assert description.columns == [column]


def test_query_response_envelope() -> None:
    response = QueryResponse(
        table="passengers",
        columns=["passenger_id", "sex"],
        rows=[{"passenger_id": 1, "sex": "male"}],
        row_count=1,
        limit=100,
        offset=0,
        truncated=False,
        next_offset=None,
    )

    assert response.row_count == len(response.rows)
    assert response.next_offset is None
