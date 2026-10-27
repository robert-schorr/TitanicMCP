from __future__ import annotations

from fastmcp import Client

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


async def test_client_initializes_and_lists_three_tools(mcp_client: Client) -> None:
    tools = await mcp_client.list_tools()

    assert [tool.name for tool in tools] == [
        "list_tables",
        "describe_table",
        "query_data",
    ]
    assert all(tool.description for tool in tools)


async def test_list_tables_returns_the_catalog(mcp_client: Client) -> None:
    result = await mcp_client.call_tool("list_tables", {})

    assert result.is_error is False
    assert [entry["name"] for entry in result.data] == EXPECTED_TABLES
    assert [entry["row_count"] for entry in result.data] == EXPECTED_COUNTS
    assert [entry["recommended"] for entry in result.data] == [
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
    assert result.data[0]["kind"] == "view"
    assert result.data[0]["description"]


async def test_list_tables_description_recommends_passengers(
    mcp_client: Client,
) -> None:
    tools = await mcp_client.list_tools()
    description = next(tool.description for tool in tools if tool.name == "list_tables")

    assert description is not None
    assert "passengers" in description
    assert "recommended" in description


async def test_describe_passengers_returns_metadata(mcp_client: Client) -> None:
    result = await mcp_client.call_tool("describe_table", {"table": "passengers"})

    assert result.is_error is False
    assert result.data["name"] == "passengers"
    assert result.data["row_count"] == 891
    assert result.data["default_order_by"] == "passenger_id"
    assert len(result.data["columns"]) == 16
    assert [column["name"] for column in result.data["columns"]] == [
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
    nullable = {
        column["name"] for column in result.data["columns"] if column["nullable"]
    }
    assert nullable == {"age", "embarked", "deck", "embark_town"}


async def test_describe_sex_returns_lookup_metadata(mcp_client: Client) -> None:
    result = await mcp_client.call_tool("describe_table", {"table": "Sex"})

    assert result.data["default_order_by"] == "sex_id"
    assert [column["name"] for column in result.data["columns"]] == [
        "sex_id",
        "sex",
    ]


async def test_query_data_projection_filter_and_order(mcp_client: Client) -> None:
    result = await mcp_client.call_tool(
        "query_data",
        {
            "table": "passengers",
            "columns": ["sex", "age"],
            "filter": [{"column": "age", "op": "gte", "value": 30}],
            "order_by": {"column": "age", "direction": "desc"},
            "limit": 3,
        },
    )

    assert result.is_error is False
    assert result.data["table"] == "passengers"
    assert result.data["columns"] == ["sex", "age"]
    assert result.data["row_count"] == 3
    assert result.data["limit"] == 3
    assert result.data["offset"] == 0
    assert result.data["truncated"] is True
    assert result.data["next_offset"] == 3
    assert all(entry["age"] >= 30 for entry in result.data["rows"])
    assert [entry["age"] for entry in result.data["rows"]] == sorted(
        [entry["age"] for entry in result.data["rows"]],
        reverse=True,
    )


async def test_query_data_returns_the_core_envelope(mcp_client: Client) -> None:
    result = await mcp_client.call_tool(
        "query_data",
        {"table": "passengers", "columns": ["sex", "age"], "limit": 3},
    )

    assert result.data == {
        "table": "passengers",
        "columns": ["sex", "age"],
        "rows": [
            {"sex": "male", "age": 22.0},
            {"sex": "female", "age": 38.0},
            {"sex": "female", "age": 26.0},
        ],
        "row_count": 3,
        "limit": 3,
        "offset": 0,
        "truncated": True,
        "next_offset": 3,
    }


async def test_query_data_final_page(mcp_client: Client) -> None:
    result = await mcp_client.call_tool(
        "query_data", {"table": "passengers", "limit": 5, "offset": 890}
    )

    assert result.data["row_count"] == 1
    assert result.data["truncated"] is False
    assert result.data["next_offset"] is None


async def test_query_data_omitted_columns_returns_catalog_order(
    mcp_client: Client,
) -> None:
    result = await mcp_client.call_tool("query_data", {"table": "Sex", "limit": 1})

    assert result.data["columns"] == ["sex_id", "sex"]
    assert list(result.data["rows"][0]) == ["sex_id", "sex"]
