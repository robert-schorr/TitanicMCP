from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from mcp_types import TextContent

from titanic_mcp import queries
from titanic_mcp.errors import InvalidArgumentsError, SafeToolError
from titanic_mcp.server import ToolCallMiddleware, _safe_tool


def _canonical(records: list[Any]) -> list[Any]:
    return [
        record for record in records if getattr(record, "event", None) == "tool_call"
    ]


def _error_text(result: Any) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


async def test_unexpected_exception_is_masked(
    mcp_client: Client,
    tool_log_records: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(_database: Any) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(queries, "list_tables", explode)

    result = await mcp_client.call_tool("list_tables", {}, raise_on_error=False)

    assert result.is_error is True
    assert _error_text(result) == "Internal error."
    assert "database unavailable" not in _error_text(result)

    records = _canonical(tool_log_records)
    assert len(records) == 1
    assert records[0].status == "internal_error"
    assert records[0].error_type == "unexpected_exception"

    internal = [
        record
        for record in tool_log_records
        if getattr(record, "event", None) == "tool_call_unhandled_error"
    ]
    assert len(internal) == 1
    assert internal[0].exc_info is not None
    assert internal[0].exception_type == "RuntimeError"


async def test_classified_safe_error_passes_through(
    mcp_client: Client,
    tool_log_records: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_database: Any, _table: str) -> None:
        raise SafeToolError("The catalog is temporarily unavailable.")

    monkeypatch.setattr(queries, "describe_table", fail)

    result = await mcp_client.call_tool(
        "describe_table", {"table": "passengers"}, raise_on_error=False
    )

    assert result.is_error is True
    assert _error_text(result) == "The catalog is temporarily unavailable."
    records = _canonical(tool_log_records)
    assert len(records) == 1
    assert records[0].status == "safe_error"
    assert records[0].error_type == "safe_tool_error"


async def test_domain_validation_maps_to_safe_arguments(
    mcp_client: Client,
    tool_log_records: list[Any],
) -> None:
    result = await mcp_client.call_tool(
        "query_data", {"table": "sqlite_master"}, raise_on_error=False
    )

    assert result.is_error is True
    assert _error_text(result) == "Invalid arguments: table"
    records = _canonical(tool_log_records)
    assert records[0].status == "invalid_arguments"
    assert records[0].error_type == "domain_validation"
    assert records[0].field_paths == ["table"]


async def test_root_level_validation_falls_back_to_request(
    tool_log_records: list[Any],
) -> None:
    app = FastMCP(
        name="root-validation-test",
        strict_input_validation=True,
        mask_error_details=True,
        middleware=[ToolCallMiddleware()],
    )

    @app.tool
    @_safe_tool
    def root_failure() -> str:
        raise InvalidArgumentsError([], "unlocatable failure")

    async with Client(app) as client:
        result = await client.call_tool("root_failure", {}, raise_on_error=False)

    assert result.is_error is True
    assert _error_text(result) == "Invalid arguments: request"
    records = _canonical(tool_log_records)
    assert records[0].field_paths == ["request"]


async def test_validation_internal_detail_is_logged_but_not_returned(
    mcp_client: Client,
    tool_log_records: list[Any],
) -> None:
    result = await mcp_client.call_tool(
        "query_data",
        {"table": "passengers", "limit": "not-an-integer"},
        raise_on_error=False,
    )

    assert _error_text(result) == "Invalid arguments: limit"
    internal = [
        record
        for record in tool_log_records
        if getattr(record, "event", None) == "tool_call_internal_error"
    ]
    assert len(internal) == 1
    assert internal[0].error_types == ["int_type"]
    assert internal[0].field_paths == ["limit"]
    assert "not-an-integer" not in _error_text(result)


async def test_unexpected_field_is_rejected_with_field_path(
    mcp_client: Client,
    tool_log_records: list[Any],
) -> None:
    result = await mcp_client.call_tool(
        "query_data",
        {"table": "passengers", "foo": 1},
        raise_on_error=False,
    )

    assert result.is_error is True
    assert _error_text(result) == "Invalid arguments: foo"
    records = _canonical(tool_log_records)
    assert len(records) == 1
    assert records[0].status == "invalid_arguments"
    assert records[0].error_type == "validation_error"
    assert records[0].field_paths == ["foo"]


@pytest.mark.parametrize(
    ("arguments", "field_path"),
    [
        ({"table": "passengers", "limit": 0}, "limit"),
        ({"table": "passengers", "limit": 501}, "limit"),
        ({"table": "passengers", "offset": -1}, "offset"),
    ],
)
async def test_pagination_bounds_are_rejected_with_field_path(
    mcp_client: Client,
    tool_log_records: list[Any],
    arguments: dict[str, Any],
    field_path: str,
) -> None:
    result = await mcp_client.call_tool("query_data", arguments, raise_on_error=False)

    assert result.is_error is True
    assert _error_text(result) == f"Invalid arguments: {field_path}"
    records = _canonical(tool_log_records)
    assert len(records) == 1
    assert records[0].status == "invalid_arguments"
    assert records[0].error_type == "validation_error"
    assert records[0].field_paths == [field_path]


async def test_oversized_filter_is_rejected_at_the_tool_boundary(
    mcp_client: Client,
    tool_log_records: list[Any],
) -> None:
    arguments = {
        "table": "passengers",
        "filter": [
            {"column": "age", "op": "gte", "value": index} for index in range(21)
        ],
    }

    result = await mcp_client.call_tool("query_data", arguments, raise_on_error=False)

    assert result.is_error is True
    assert _error_text(result) == "Invalid arguments: filter"
    records = _canonical(tool_log_records)
    assert len(records) == 1
    assert records[0].status == "invalid_arguments"
    assert records[0].error_type == "validation_error"
    assert records[0].field_paths == ["filter"]


async def test_canonical_log_excludes_filter_values_and_raw_arguments(
    mcp_client: Client,
    tool_log_records: list[Any],
) -> None:
    await mcp_client.call_tool(
        "query_data",
        {
            "table": "passengers",
            "filter": [{"column": "sex", "op": "eq", "value": "TopSecret"}],
        },
    )

    records = _canonical(tool_log_records)
    assert len(records) == 1
    serialized = json.dumps(records[0].__dict__, default=str)
    assert "TopSecret" not in serialized
    assert "sex" not in serialized
    assert records[0].table == "passengers"
    assert records[0].filter_count == 1
