from __future__ import annotations

from fastmcp import Client

EXPECTED_TOOLS = ["list_tables", "describe_table", "query_data"]


async def test_exactly_three_tools_are_advertised(mcp_client: Client) -> None:
    tools = await mcp_client.list_tools()

    assert sorted(tool.name for tool in tools) == sorted(EXPECTED_TOOLS)
    assert all(tool.description for tool in tools)


async def test_query_schema_advertises_expected_fields(mcp_client: Client) -> None:
    tools = await mcp_client.list_tools()
    query_tool = next(tool for tool in tools if tool.name == "query_data")
    schema = query_tool.input_schema

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["table"]
    assert set(schema["properties"]) == {
        "table",
        "columns",
        "filter",
        "order_by",
        "limit",
        "offset",
    }
    assert schema["properties"]["table"]["type"] == "string"
    assert schema["properties"]["limit"]["type"] == "integer"
    assert schema["properties"]["limit"]["minimum"] == 1
    assert schema["properties"]["limit"]["maximum"] == 500
    assert schema["properties"]["offset"]["minimum"] == 0
    assert "required" not in schema["properties"]["filter"]


async def test_list_tables_schema_takes_no_arguments(mcp_client: Client) -> None:
    tools = await mcp_client.list_tools()
    list_tool = next(tool for tool in tools if tool.name == "list_tables")

    assert list_tool.input_schema["properties"] == {}
    assert "required" not in list_tool.input_schema


async def test_query_description_recommends_passengers(mcp_client: Client) -> None:
    tools = await mcp_client.list_tools()
    query_tool = next(tool for tool in tools if tool.name == "query_data")

    assert query_tool.description is not None
    assert "passengers" in query_tool.description
    assert "recommended" in query_tool.description
