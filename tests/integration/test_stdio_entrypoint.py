from __future__ import annotations

from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def test_stdio_entrypoint_lists_tools_and_calls_catalog(
    project_root: Path,
) -> None:
    transport = StdioTransport(
        command="uv",
        args=["run", "titanic-mcp"],
        cwd=str(project_root),
    )

    async with Client(transport, timeout=90) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools] == [
            "list_tables",
            "describe_table",
            "query_data",
        ]

        result = await client.call_tool("list_tables", {})
        assert len(result.data) == 9
        assert result.data[0]["name"] == "passengers"
