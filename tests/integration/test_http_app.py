from __future__ import annotations

import json
import logging
from typing import Any

import httpx2
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from titanic_mcp import queries
from titanic_mcp.database import Database
from titanic_mcp.server import ServerConfig, http_app

TOKEN = "test-token-4f8c2b1e"
SSE_HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}
INITIALIZE_PARAMS = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "titanic-tests", "version": "0.1.0"},
}


def _request(
    request_id: int, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


def _client_factory(app: Any) -> Any:
    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
        **kwargs: Any,
    ) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            headers=headers,
            timeout=timeout,
            auth=auth,
            **kwargs,
        )

    return factory


def _http_client(app: Any) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://127.0.0.1:8000",
    )


def _payload(response: httpx2.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("text/event-stream"):
        data = [
            line.removeprefix("data: ")
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert data, response.text
        return json.loads(data[-1])
    return response.json()


def _remote_config() -> ServerConfig:
    return ServerConfig(
        profile="remote",
        host="0.0.0.0",
        auth_token=TOKEN,
        allowed_hosts=("127.0.0.1:8000",),
        allowed_origins=("https://app.example",),
    )


def _container_config() -> ServerConfig:
    return ServerConfig(
        profile="container",
        host="0.0.0.0",
        allowed_hosts=("127.0.0.1:8000",),
        allowed_origins=("https://app.example",),
    )


async def test_http_client_lists_tools_and_calls_catalog(database: Database) -> None:
    app = http_app(database)
    transport = StreamableHttpTransport(
        url="http://127.0.0.1:8000/mcp",
        httpx_client_factory=_client_factory(app),
    )

    async with app.lifespan(app), Client(transport, timeout=30) as client:
        tools = await client.list_tools()
        result = await client.call_tool("list_tables", {})

    assert [tool.name for tool in tools] == [
        "list_tables",
        "describe_table",
        "query_data",
    ]
    assert len(result.data) == 9
    assert result.data[0]["name"] == "passengers"


async def test_stateless_requests_need_no_session_id(database: Database) -> None:
    app = http_app(database)

    async with app.lifespan(app), _http_client(app) as client:
        initialize = await client.post(
            "/mcp",
            headers=SSE_HEADERS,
            json=_request(1, "initialize", INITIALIZE_PARAMS),
        )
        assert initialize.status_code == 200
        assert "mcp-session-id" not in initialize.headers
        initialized = _payload(initialize)
        assert initialized["result"]["serverInfo"]["name"] == "titanic-mcp"

        notification = await client.post(
            "/mcp",
            headers=SSE_HEADERS,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        assert notification.status_code == 202

        listed = await client.post(
            "/mcp",
            headers=SSE_HEADERS,
            json=_request(2, "tools/list"),
        )
        assert listed.status_code == 200
        assert "mcp-session-id" not in listed.headers
        tools = _payload(listed)["result"]["tools"]
        assert [tool["name"] for tool in tools] == [
            "list_tables",
            "describe_table",
            "query_data",
        ]

        called = await client.post(
            "/mcp",
            headers=SSE_HEADERS,
            json=_request(
                3,
                "tools/call",
                {"name": "list_tables", "arguments": {}},
            ),
        )
        assert called.status_code == 200
        assert "mcp-session-id" not in called.headers
        text = _payload(called)["result"]["content"][0]["text"]
        assert next(entry["name"] for entry in json.loads(text)) == "passengers"


async def test_healthz_returns_ok_without_mcp_initialization(
    database: Database,
) -> None:
    app = http_app(database)

    async with app.lifespan(app), _http_client(app) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert _payload(response) == {"status": "ok"}


async def test_healthz_bypasses_authentication_and_protection(
    database: Database,
) -> None:
    app = http_app(database, _remote_config())

    async with app.lifespan(app), _http_client(app) as client:
        without_auth = await client.get("/healthz")
        with_allowed_origin = await client.get(
            "/healthz",
            headers={"origin": "https://app.example"},
        )

    assert without_auth.status_code == 200
    assert without_auth.json() == {"status": "ok"}
    assert with_allowed_origin.status_code == 200


async def test_allowed_host_and_origin_proceed_to_mcp(database: Database) -> None:
    app = http_app(database, _container_config())

    async with app.lifespan(app), _http_client(app) as client:
        response = await client.post(
            "/mcp",
            headers={**SSE_HEADERS, "origin": "https://app.example"},
            json=_request(1, "initialize", INITIALIZE_PARAMS),
        )

    assert response.status_code == 200
    assert _payload(response)["result"]["serverInfo"]["name"] == "titanic-mcp"


async def test_disallowed_host_is_rejected_before_mcp(database: Database) -> None:
    app = http_app(database, _container_config())

    async with app.lifespan(app), _http_client(app) as client:
        response = await client.post(
            "/mcp",
            headers={**SSE_HEADERS, "host": "evil.example"},
            json=_request(1, "initialize", INITIALIZE_PARAMS),
        )

    assert response.status_code == 421
    assert response.text == "Misdirected Request"
    assert "mcp-session-id" not in response.headers


async def test_local_profile_rejects_untrusted_host(database: Database) -> None:
    app = http_app(database)

    async with app.lifespan(app), _http_client(app) as client:
        response = await client.post(
            "/mcp",
            headers={**SSE_HEADERS, "host": "evil.example"},
            json=_request(1, "initialize", INITIALIZE_PARAMS),
        )

    assert response.status_code == 421
    assert response.text == "Misdirected Request"


async def test_disallowed_origin_is_rejected_before_mcp(
    database: Database,
) -> None:
    app = http_app(database, _container_config())

    async with app.lifespan(app), _http_client(app) as client:
        response = await client.post(
            "/mcp",
            headers={**SSE_HEADERS, "origin": "https://evil.example"},
            json=_request(1, "initialize", INITIALIZE_PARAMS),
        )

    assert response.status_code == 403
    assert response.text == "Forbidden Origin"


async def test_valid_bearer_token_reaches_mcp(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_list_tables = queries.list_tables
    calls: list[None] = []

    def record_call(tool_database: Database) -> Any:
        calls.append(None)
        return real_list_tables(tool_database)

    monkeypatch.setattr(queries, "list_tables", record_call)
    app = http_app(database, _remote_config())
    transport = StreamableHttpTransport(
        url="http://127.0.0.1:8000/mcp",
        headers={"authorization": f"Bearer {TOKEN}"},
        httpx_client_factory=_client_factory(app),
    )

    async with app.lifespan(app), Client(transport, timeout=30) as client:
        result = await client.call_tool("list_tables", {})

    assert len(result.data) == 9
    assert calls == [None]


@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token"])
async def test_missing_or_invalid_token_is_rejected_without_executing_a_tool(
    authorization: str | None,
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[None] = []

    def record_call(_database: Database) -> None:
        calls.append(None)  # pragma: no cover - tripwire: tool must never execute

    monkeypatch.setattr(queries, "list_tables", record_call)
    app = http_app(database, _remote_config())
    headers = dict(SSE_HEADERS)
    if authorization is not None:
        headers["authorization"] = authorization

    async with app.lifespan(app), _http_client(app) as client:
        response = await client.post(
            "/mcp",
            headers=headers,
            json=_request(
                1,
                "tools/call",
                {"name": "list_tables", "arguments": {}},
            ),
        )

    assert response.status_code == 401
    assert calls == []


async def test_token_is_never_logged_or_returned(
    database: Database,
    tool_log_records: list[logging.LogRecord],
) -> None:
    app = http_app(database, _remote_config())
    transport = StreamableHttpTransport(
        url="http://127.0.0.1:8000/mcp",
        headers={"authorization": f"Bearer {TOKEN}"},
        httpx_client_factory=_client_factory(app),
    )

    async with app.lifespan(app):
        async with _http_client(app) as client:
            rejected = await client.post(
                "/mcp",
                headers={
                    **SSE_HEADERS,
                    "authorization": "Bearer not-the-real-token",
                },
                json=_request(
                    1,
                    "tools/call",
                    {"name": "list_tables", "arguments": {}},
                ),
            )

        async with Client(transport, timeout=30) as client:
            result = await client.call_tool("list_tables", {})

    assert rejected.status_code == 401
    assert TOKEN not in rejected.text
    assert TOKEN not in repr(result.content)
    assert all(TOKEN not in repr(record.__dict__) for record in tool_log_records)


async def test_tool_schemas_are_unchanged_over_http(database: Database) -> None:
    app = http_app(database)
    transport = StreamableHttpTransport(
        url="http://127.0.0.1:8000/mcp",
        httpx_client_factory=_client_factory(app),
    )

    async with app.lifespan(app), Client(transport, timeout=30) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    assert set(tools) == {"list_tables", "describe_table", "query_data"}
    query_schema = tools["query_data"].input_schema
    assert query_schema["required"] == ["table"]
    assert set(query_schema["properties"]) == {
        "table",
        "columns",
        "filter",
        "order_by",
        "limit",
        "offset",
    }
    assert query_schema["additionalProperties"] is False


async def test_safe_error_contract_is_unchanged_over_http(
    database: Database,
    tool_log_records: list[Any],
) -> None:
    app = http_app(database)
    transport = StreamableHttpTransport(
        url="http://127.0.0.1:8000/mcp",
        httpx_client_factory=_client_factory(app),
    )

    async with app.lifespan(app), Client(transport, timeout=30) as client:
        result = await client.call_tool(
            "query_data",
            {"table": "sqlite_master"},
            raise_on_error=False,
        )

    assert result.is_error is True
    assert result.content[0].text == "Invalid arguments: table"
    canonical = [
        record
        for record in tool_log_records
        if getattr(record, "event", None) == "tool_call"
    ]
    assert len(canonical) == 1
    assert canonical[0].status == "invalid_arguments"
    assert canonical[0].error_type == "domain_validation"
