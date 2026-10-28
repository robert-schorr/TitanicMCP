from __future__ import annotations

import asyncio
import os
import shutil
import socket
import sys
import time
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport

import titanic_mcp.server as server_module
from titanic_mcp.server import main

ENVIRONMENT_VARIABLES = (
    "TITANIC_MCP_DB_PATH",
    "TITANIC_MCP_HOST",
    "TITANIC_MCP_PORT",
    "MCP_PROFILE",
    "MCP_AUTH_TOKEN",
    "MCP_ALLOWED_HOSTS",
    "MCP_ALLOWED_ORIGINS",
    "TITANIC_MCP_LOG_LEVEL",
    "TITANIC_MCP_LOG_FORMAT",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _capture_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_run(self: FastMCP, transport: Any = None, **kwargs: Any) -> None:
        captured["transport"] = transport
        captured["kwargs"] = kwargs
        captured["auth"] = self.auth

    monkeypatch.setattr(FastMCP, "run", fake_run)
    monkeypatch.setattr(
        server_module,
        "configure_logging",
        lambda **kwargs: captured.setdefault("logging", kwargs),
    )
    return captured


def _clear_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def _subprocess_environment(**overrides: str) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in ENVIRONMENT_VARIABLES
    }
    environment.update(overrides)
    return environment


def test_subprocess_environment_drops_server_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "inherited-token")
    monkeypatch.setenv("TITANIC_MCP_DB_PATH", "inherited.db")

    environment = _subprocess_environment(MCP_PROFILE="local")

    assert "MCP_AUTH_TOKEN" not in environment
    assert "TITANIC_MCP_DB_PATH" not in environment
    assert environment["MCP_PROFILE"] == "local"


def test_main_starts_http_on_loopback_8000(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    captured = _capture_run(monkeypatch)

    main()

    assert captured["transport"] == "http"
    assert captured["kwargs"] == {
        "host": "127.0.0.1",
        "port": 8000,
        "path": "/mcp",
        "stateless_http": True,
        "host_origin_protection": "auto",
        "allowed_hosts": None,
        "allowed_origins": None,
        "show_banner": False,
    }
    assert captured["logging"] == {"level": "INFO", "json_output": True}
    assert captured["auth"] is None


def test_main_wires_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("TITANIC_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("TITANIC_MCP_PORT", "9123")
    monkeypatch.setenv("TITANIC_MCP_LOG_LEVEL", "debug")
    monkeypatch.setenv("TITANIC_MCP_LOG_FORMAT", "text")
    captured = _capture_run(monkeypatch)

    main()

    assert captured["kwargs"]["port"] == 9123
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["logging"] == {"level": "DEBUG", "json_output": False}


def test_main_uses_the_configured_database_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("TITANIC_MCP_DB_PATH", "custom/titanic.db")
    captured = _capture_run(monkeypatch)
    recorded: dict[str, Path] = {}

    def record_database(path: Path) -> object:
        recorded["path"] = path

        class FakeDatabase:
            def fetch_one(self, sql: str) -> dict[str, int]:
                return {"1": 1}

        return FakeDatabase()

    monkeypatch.setattr(server_module, "Database", record_database)

    main()

    assert recorded["path"] == Path("custom/titanic.db")
    assert captured["transport"] == "http"


def test_main_fails_before_serving_when_database_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("TITANIC_MCP_DB_PATH", str(tmp_path / "missing.db"))
    captured = _capture_run(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert "database is not readable" in str(exc_info.value)
    assert "transport" not in captured


def test_main_starts_the_remote_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("MCP_PROFILE", "remote")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "remote-token")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "mcp.example.com,localhost:8000")
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://app.example")
    captured = _capture_run(monkeypatch)

    main()

    assert captured["kwargs"] == {
        "host": "0.0.0.0",
        "port": 8000,
        "path": "/mcp",
        "stateless_http": False,
        "host_origin_protection": True,
        "allowed_hosts": ["mcp.example.com", "localhost:8000"],
        "allowed_origins": ["https://app.example"],
        "show_banner": False,
    }
    assert captured["auth"] is not None


@pytest.mark.parametrize(
    ("environ", "missing_setting"),
    [
        (
            {
                "MCP_PROFILE": "remote",
                "MCP_ALLOWED_HOSTS": "mcp.example.com",
            },
            "MCP_AUTH_TOKEN",
        ),
        (
            {
                "MCP_PROFILE": "remote",
                "MCP_AUTH_TOKEN": "never-logged-token",
            },
            "MCP_ALLOWED_HOSTS",
        ),
        (
            {
                "MCP_PROFILE": "container",
            },
            "MCP_ALLOWED_HOSTS",
        ),
    ],
)
def test_main_fails_before_serving_when_settings_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    environ: dict[str, str],
    missing_setting: str,
) -> None:
    _clear_environment(monkeypatch)
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    captured = _capture_run(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        main()

    message = str(exc_info.value)
    assert missing_setting in message
    assert "never-logged-token" not in message
    assert "transport" not in captured


async def _wait_for_health(
    port: int,
    process: asyncio.subprocess.Process,
    deadline_seconds: float = 60,
) -> None:
    deadline = time.monotonic() + deadline_seconds
    last_error: Exception | None = None
    async with httpx2.AsyncClient(timeout=1.0) as client:
        while time.monotonic() < deadline:
            if process.returncode is not None:
                raise AssertionError(
                    f"server exited before becoming healthy (code {process.returncode})"
                )
            try:
                response = await client.get(f"http://127.0.0.1:{port}/healthz")
                if response.status_code == 200 and response.json() == {"status": "ok"}:
                    return
            except (httpx2.HTTPError, ValueError) as exc:
                last_error = exc
            await asyncio.sleep(0.2)
    raise AssertionError(f"server did not become healthy: {last_error!r}")


async def _stop(process: asyncio.subprocess.Process) -> bytes:
    if process.returncode is None:
        if sys.platform == "win32":
            # `uv run` starts the server as a child process on Windows, so
            # terminate the whole tree rather than only the uv launcher.
            stopped = await asyncio.create_subprocess_exec(
                "taskkill",
                "/T",
                "/F",
                "/PID",
                str(process.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await stopped.wait()
            if stopped.returncode != 0:  # pragma: no cover - taskkill race fallback
                process.terminate()
        else:  # pragma: no cover - only POSIX resolves uv without a child tree
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:  # pragma: no cover - last resort for a stuck tree
            process.kill()
            await process.wait()
    if process.stderr is None:
        return b""
    return await process.stderr.read()


async def test_wait_for_health_raises_when_the_server_exits() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "pass",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        with pytest.raises(AssertionError, match="exited before becoming healthy"):
            await _wait_for_health(_free_port(), process)
    finally:
        await _stop(process)


async def test_wait_for_health_raises_when_the_deadline_expires() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(120)",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        with pytest.raises(AssertionError, match="did not become healthy"):
            await _wait_for_health(_free_port(), process, deadline_seconds=0.4)
    finally:
        await _stop(process)


async def test_stop_returns_empty_stderr_without_a_pipe() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "pass",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.wait()

    stderr = await _stop(process)

    assert stderr == b""
    assert process.returncode is not None


async def test_http_entrypoint_serves_mcp(project_root: Path) -> None:
    uv_path = shutil.which("uv")
    assert uv_path is not None, "uv must be on PATH for the entrypoint smoke test"
    port = _free_port()
    environment = _subprocess_environment(
        TITANIC_MCP_HOST="127.0.0.1",
        TITANIC_MCP_PORT=str(port),
        MCP_PROFILE="local",
    )
    process = await asyncio.create_subprocess_exec(
        uv_path,
        "run",
        "titanic-mcp",
        cwd=str(project_root),
        env=environment,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        await _wait_for_health(port, process)
        transport = StreamableHttpTransport(
            url=f"http://127.0.0.1:{port}/mcp",
        )
        async with Client(transport, timeout=30) as client:
            tools = await client.list_tools()
            result = await client.call_tool("list_tables", {})
    finally:
        stderr = await _stop(process)

    assert [tool.name for tool in tools] == [
        "list_tables",
        "describe_table",
        "query_data",
    ]
    assert len(result.data) == 9
    assert b"Configuration error" not in stderr


async def test_remote_entrypoint_requires_token_and_never_logs_it(
    project_root: Path,
) -> None:
    port = _free_port()
    token = "entrypoint-secret-9c1a4e"
    environment = _subprocess_environment(
        TITANIC_MCP_HOST="127.0.0.1",
        TITANIC_MCP_PORT=str(port),
        MCP_PROFILE="remote",
        MCP_AUTH_TOKEN=token,
        MCP_ALLOWED_HOSTS=f"127.0.0.1:{port}",
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "from titanic_mcp import main; main()",
        cwd=str(project_root),
        env=environment,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        await _wait_for_health(port, process)
        async with httpx2.AsyncClient(timeout=10.0) as client:
            rejected = await client.post(
                f"http://127.0.0.1:{port}/mcp",
                headers={
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "entrypoint-test", "version": "0.1.0"},
                    },
                },
            )

        transport = StreamableHttpTransport(
            url=f"http://127.0.0.1:{port}/mcp",
            headers={"authorization": f"Bearer {token}"},
        )
        async with Client(transport, timeout=30) as client:
            result = await client.call_tool("list_tables", {})
    finally:
        stderr = await _stop(process)

    assert rejected.status_code == 401
    assert len(result.data) == 9
    assert token not in stderr.decode(errors="replace")
    assert token not in rejected.text
    assert token not in repr(result.content)
