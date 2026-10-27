# AGENTS.md

## Commands

- Use `uv` for all Python commands. Python 3.13 is pinned in `.python-version`.
- Before finishing, run and pass all four gates:
  `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check`.
- `ty` is the type checker; do not substitute mypy or pyright.

## OpenSpec

- Work through the active change under `openspec/changes/<change>/`. Main specs in `openspec/specs/` are synced output, not scratch files.
- Keep `tasks.md` checkboxes current. Use `openspec status --change <name> --json` and `openspec instructions apply --change <name> --json` to track progress.
- Archive only after implementation, tests, and delta-spec sync are complete.

## Data and query core

- `data/titanic.db` is read-only. Never add writes to it.
- `queries.py` owns catalog semantics, validation, and SQL compilation. Tools in `server.py` stay thin wrappers; do not duplicate query logic in the tool layer.
- Queries are bounded and use bound parameters. Never interpolate user values into SQL.

## MCP contract

- FastMCP is pinned to `>=4.1.4,<5`. It already brings the MCP SDK; do not add a direct `mcp[cli]` dependency.
- Expose only `list_tables`, `describe_table`, and `query_data` unless a change explicitly adds tools.
- Preserve strict JSON types, the safe client messages `Invalid arguments: <sorted paths>` and `Internal error.`, and the no-detail-leak contract.
- FastMCP masks non-`ToolError` exceptions before middleware. Keep `_safe_tool` and `_ClassifiedToolError` when adding tools; without them, domain/safe errors become `Internal error.` and lose their log classification.

## Logging and transport

- `configure_logging()` owns application logging. Do not add handlers or use `print`; application logs go to stderr.
- Emit exactly one canonical `event="tool_call"` JSON record per call. Never log raw arguments, filter values, SQL, parameters, request bodies, auth headers, or the configured bearer token.
- The `titanic-mcp` entrypoint serves Streamable HTTP at `/mcp`. The default `local` profile binds `127.0.0.1:8000`, is stateless, requires no authentication, and enables host/origin protection.
- Keep configuration and profile validation in `server.py`: `local` rejects a non-loopback bind, `container` and `remote` require `MCP_ALLOWED_HOSTS`, and `remote` also requires `MCP_AUTH_TOKEN`.
- Keep `GET /healthz` independent of MCP initialization and authentication so probes work without a session or token.

## Tests

- pytest-asyncio runs in auto mode. Use the in-process `Client(create_app(database))` fixture for tool integration tests.
- Keep the real HTTP entrypoint test in `tests/integration/test_http_entrypoint.py` working. HTTP seam tests use `httpx2.ASGITransport` plus the app lifespan.
- Profile validation lives in `tests/integration/test_profiles.py`; transport, health, host/origin, and auth coverage lives in `tests/integration/test_http_app.py`.
