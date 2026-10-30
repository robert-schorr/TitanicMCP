"""Smoke-test the Titanic MCP server.

In-process by default; pass --http to test a running Streamable HTTP server.

    uv run python scripts/smoke_test.py
    uv run titanic-mcp
    uv run python scripts/smoke_test.py --http
    uv run python scripts/smoke_test.py --http http://127.0.0.1:8000/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp_types import TextContent

from titanic_mcp.server import create_app

DEFAULT_HTTP_URL = "http://127.0.0.1:8000/mcp"


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
        "--http",
        nargs="?",
        const=DEFAULT_HTTP_URL,
        metavar="URL",
        help=(f"test a running Streamable HTTP server (default: {DEFAULT_HTTP_URL})"),
    )
    args = parser.parse_args()

    if args.http:
        print(f"Connecting to {args.http}")
        async with Client(
            StreamableHttpTransport(url=args.http),
            timeout=90,
        ) as client:
            await run(client)
    else:
        async with Client(create_app()) as client:
            await run(client)

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
