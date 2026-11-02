"""Build and smoke-test the container deployment.

Requires a running Docker daemon. Builds the image, then starts it with the same
read-only filesystem, database mount, and security settings as ``compose.yaml``.
Checks the default ``container`` profile, then the ``remote`` profile with
bearer-token authentication: waits for ``/healthz``, rejects unauthenticated MCP
requests, calls ``list_tables`` through the published port, checks that the
token never reaches the logs, and checks that the runtime user is not root.

    uv run python scripts/container_smoke_test.py

This is a manual verification script, not part of the pytest suite.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "titanic.db"
IMAGE = "titanic-mcp:container-test"
NAMES = ("list_tables", "describe_table", "query_data")


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))
    return ok


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def start_container(
    name: str, port: int, profile: str, extra_env: tuple[str, ...] = ()
) -> bool:
    allowed_hosts = f"localhost:8000,127.0.0.1:8000,localhost:{port},127.0.0.1:{port}"
    environment = [
        f"MCP_PROFILE={profile}",
        "TITANIC_MCP_DB_PATH=/app/data/titanic.db",
        f"MCP_ALLOWED_HOSTS={allowed_hosts}",
        *extra_env,
    ]
    args = [
        "run",
        "--detach",
        "--name",
        name,
        "--publish",
        f"127.0.0.1:{port}:8000",
    ]
    for entry in environment:
        args += ["--env", entry]
    args += [
        "--mount",
        f"type=bind,source={DB_PATH},target=/app/data/titanic.db,readonly",
        "--read-only",
        "--tmpfs",
        "/tmp:noexec,nosuid,size=64m",
        "--security-opt",
        "no-new-privileges:true",
        IMAGE,
    ]

    started = docker(*args)
    if started.returncode != 0:
        print(started.stderr.strip(), file=sys.stderr)
        return False
    return True


def wait_for_health(port: int, container: str, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/healthz", timeout=2
            ) as response:
                if response.status == 200 and json.load(response) == {"status": "ok"}:
                    return True
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = exc

        running = docker("inspect", "--format", "{{.State.Running}}", container)
        if running.returncode != 0 or running.stdout.strip() != "true":
            print(f"Container {container} exited before becoming healthy.")
            print_logs(container)
            return False
        time.sleep(0.5)

    print(f"Health check timed out: {last_error!r}")
    print_logs(container)
    return False


def print_logs(container: str) -> None:
    logs = docker("logs", "--tail", "50", container)
    output = (logs.stdout + logs.stderr).strip()
    if output:
        print("--- container logs ---")
        print(output)


def unauthenticated_status(url: str) -> int | None:
    request = urllib.request.Request(
        url,
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "container-smoke-test", "version": "0.1.0"},
                },
            }
        ).encode(),
        headers={
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return None


async def call_list_tables(url: str, token: str | None = None) -> tuple[list[str], int]:
    headers = {"authorization": f"Bearer {token}"} if token else None
    transport = StreamableHttpTransport(url=url, headers=headers)
    async with Client(transport, timeout=30) as client:
        tools = [tool.name for tool in await client.list_tools()]
        result = await client.call_tool("list_tables", {})
    return tools, len(result.data)


def check_container(
    profile: str, container: str, port: int, token: str | None = None
) -> int:
    failures = 0
    url = f"http://127.0.0.1:{port}/mcp"

    if not check(f"{profile}: container is healthy", wait_for_health(port, container)):
        return 1

    if token is not None and not check(
        f"{profile}: unauthenticated request rejected",
        unauthenticated_status(url) == 401,
    ):
        failures += 1

    try:
        tools, row_count = asyncio.run(call_list_tables(url, token))
    except Exception as exc:  # noqa: BLE001 - report any client failure
        print_logs(container)
        failures += 1
        check(f"{profile}: list_tables call", False, repr(exc))
    else:
        if not check(f"{profile}: tool names", tools == list(NAMES), str(tools)):
            failures += 1
        if not check(f"{profile}: list_tables returns 9 rows", row_count == 9):
            failures += 1

    if token is not None:
        logs = docker("logs", container)
        if not check(
            f"{profile}: token not logged",
            token not in logs.stdout + logs.stderr,
        ):
            failures += 1

    uid = docker("exec", container, "python", "-c", "import os; print(os.getuid())")
    if uid.returncode != 0:
        failures += 1
        check(f"{profile}: runtime UID", False, uid.stderr.strip())
    elif not check(f"{profile}: runtime UID is 10001", uid.stdout.strip() == "10001"):
        failures += 1

    return failures


def run_profile(profile: str, token: str | None = None) -> int:
    container = f"titanic-mcp-{profile}-{uuid.uuid4().hex[:8]}"
    port = free_port()
    extra_env = (f"MCP_AUTH_TOKEN={token}",) if token else ()
    try:
        if not start_container(container, port, profile, extra_env):
            return 1
        print(f"Started {profile} container {container} on port {port}")
        return check_container(profile, container, port, token)
    finally:
        docker("rm", "--force", container)


def main() -> int:
    if shutil.which("docker") is None:
        print("Docker CLI not found on PATH.", file=sys.stderr)
        return 1
    if docker("info").returncode != 0:
        print("Docker daemon is not available.", file=sys.stderr)
        return 1
    if not DB_PATH.is_file():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        return 1

    print(f"Building {IMAGE} ...")
    build = subprocess.run(
        ["docker", "build", "--tag", IMAGE, "."],
        cwd=REPO_ROOT,
        check=False,
    )
    if build.returncode != 0:
        print("Image build failed.", file=sys.stderr)
        return 1

    failures = run_profile("container") + run_profile("remote", uuid.uuid4().hex)

    if failures:
        print(f"\n{failures} container check(s) failed.")
        return 1

    print("\nContainer deployment test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
