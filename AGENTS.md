# AGENTS.md

## Commands

- Use `uv` for all Python commands. Python 3.13 is pinned in `.python-version`.
- Before finishing, run and pass all four gates:
  `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check`.
- `ty` is the type checker; do not substitute mypy or pyright.
- When Docker is available, also run `uv run python scripts/container_smoke_test.py`; it builds the image and verifies health, a real tool call, remote bearer-token auth, and the non-root runtime user.

## OpenSpec

- Work through the active change under `openspec/changes/<change>/`. Main specs in `openspec/specs/` are synced output, not scratch files.
- Keep `tasks.md` checkboxes current. Use `openspec status --change <name> --json` and `openspec instructions apply --change <name> --json` to track progress.
- After editing specs or active changes, run `openspec validate --all --strict`.
- Archive only after implementation, tests, and delta-spec sync are complete.
- Deferred work (CI, pre-commit hooks, metrics, security hardening) is tracked in `docs/next-steps.md`; do not claim it is implemented.

## Data and query core

- `data/titanic.db` is read-only. Never add writes to it.
- `queries.py` owns catalog semantics, validation, and SQL compilation. Tools in `server.py` stay thin wrappers; do not duplicate query logic in the tool layer.
- Queries are bounded and use bound parameters. Never interpolate user values into SQL.
- `main()` proves the database contains the Titanic catalog by querying `Observation`; do not weaken this to `SELECT 1`.

## MCP contract

- FastMCP is pinned to `>=4.1.4,<5`. It already brings the MCP SDK; do not add a direct `mcp[cli]` dependency.
- Expose only `list_tables`, `describe_table`, and `query_data` unless a change explicitly adds tools.
- Preserve strict JSON types, the safe client messages `Invalid arguments: <sorted paths>` and `Internal error.`, and the no-detail-leak contract.
- FastMCP masks non-`ToolError` exceptions before middleware. Keep `_safe_tool` and `_ClassifiedToolError` when adding tools; without them, domain validation errors become `Internal error.` and lose their log classification. `QueryValidationError` is the only client-safe classified exception; do not reintroduce `SafeToolError`.

## Logging and transport

- `configure_logging()` owns application logging. Do not add handlers or use `print`; application logs go to stderr.
- Emit exactly one canonical `event="tool_call"` JSON record per call. Never log raw arguments, filter values, SQL, parameters, request bodies, auth headers, or the configured bearer token. Only log a `table` value when it exists in `queries.TABLES`; unknown names log as `null`.
- The `titanic-mcp` entrypoint serves Streamable HTTP at `/mcp`. The default `local` profile binds `127.0.0.1:8000`, requires no authentication, and enables host/origin protection. All profiles are stateless (`stateless_http=True`); do not reintroduce session affinity.
- Keep configuration and profile validation in `server.py`: `local` rejects a non-loopback bind, `container` and `remote` require `MCP_ALLOWED_HOSTS`, and `remote` also requires `MCP_AUTH_TOKEN`. The `container` profile is unauthenticated by default and safe only when the published port is loopback-bound; the image does not enforce that.
- Keep `GET /healthz` independent of MCP initialization and authentication so probes work without a session or token.
- Uvicorn's own startup and access logs remain plain text; routing them through the JSON formatter is a documented TODO in `docs/next-steps.md`.

## Tests

- pytest-asyncio runs in auto mode. Use the in-process `Client(create_app(database))` fixture for tool integration tests.
- Keep the real HTTP entrypoint test in `tests/integration/test_http_entrypoint.py` working, including startup rejection of a missing, unreadable, or catalog-less database. HTTP seam tests use `httpx2.ASGITransport` plus the app lifespan.
- Profile validation lives in `tests/integration/test_profiles.py`; transport, health, host/origin, and auth coverage lives in `tests/integration/test_http_app.py`.
