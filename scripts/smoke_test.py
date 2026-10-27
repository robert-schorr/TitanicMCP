"""Smoke-test the Titanic MCP server.

In-process by default; add --stdio to test the real `titanic-mcp` entrypoint.

    uv run python scripts/smoke_test.py
    uv run python scripts/smoke_test.py --stdio
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from mcp_types import TextContent

from titanic_mcp.server import create_app


def show(label: str, data: Any) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(data, indent=2, default=str)[:800])


async def run(client: Client) -> None:
    tools = await client.list_tools()
    print(f"Tools: {[tool.name for tool in tools]}")

    show("list_tables", (await client.call_tool("list_tables", {})).data)

    show(
        "describe_table(passengers)",
        (await client.call_tool("describe_table", {"table": "passengers"})).data,
    )

    show(
        "query_data (3 rows)",
        (
            await client.call_tool(
                "query_data",
                {
                    "table": "passengers",
                    "columns": ["sex", "age"],
                    "filter": [{"column": "sex", "op": "eq", "value": "female"}],
                    "order_by": {"column": "age", "direction": "desc"},
                    "limit": 3,
                },
            )
        ).data,
    )

    for label, args in (
        ("unknown table", {"table": "sqlite_master"}),
        ("bad limit", {"table": "passengers", "limit": 501}),
        ("unexpected field", {"table": "passengers", "foo": 1}),
    ):
        result = await client.call_tool("query_data", args, raise_on_error=False)
        block = result.content[0]
        assert isinstance(block, TextContent)
        print(f"\n=== error check: {label} ===")
        print(block.text)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="test the titanic-mcp entrypoint over stdio",
    )
    args = parser.parse_args()

    if args.stdio:
        transport = StdioTransport(command="uv", args=["run", "titanic-mcp"], cwd=".")
        async with Client(transport, timeout=90) as client:
            await run(client)
    else:
        async with Client(create_app()) as client:
            await run(client)

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
