from __future__ import annotations

from typing import Any

import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from titanic_mcp.database import Database
from titanic_mcp.server import http_app


def _canonical(records: list[Any]) -> list[Any]:
    return [
        record for record in records if getattr(record, "event", None) == "tool_call"
    ]


async def test_in_process_call_records_request_id_and_no_correlation(
    mcp_client: Client,
    tool_log_records: list[Any],
) -> None:
    await mcp_client.call_tool("list_tables", {})

    records = _canonical(tool_log_records)
    assert len(records) == 1
    record = records[0]
    assert record.request_id is not None
    assert record.correlation_id is None
    assert record.tool_name == "list_tables"
    assert record.status == "ok"
    assert record.error_type == "none"
    assert record.duration_ms >= 0


async def test_http_request_correlation_header_is_logged(
    database: Database,
    tool_log_records: list[Any],
) -> None:
    app = http_app(database)

    def client_factory(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
        **kwargs: Any,
    ) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            headers=headers,
            timeout=timeout,
            auth=auth,
            **kwargs,
        )

    transport = StreamableHttpTransport(
        url="http://testserver/mcp",
        headers={
            "x-request-id": "corr-123",
            "authorization": "Bearer top-secret-token",
        },
        httpx_client_factory=client_factory,
    )

    async with app.lifespan(app), Client(transport) as client:
        result = await client.call_tool("list_tables", {})

    assert len(result.data) == 9
    records = _canonical(tool_log_records)
    assert len(records) == 1
    record = records[0]
    assert record.correlation_id == "corr-123"
    assert record.request_id is not None
    assert record.status == "ok"
    serialized = repr(record.__dict__)
    assert "top-secret-token" not in serialized
