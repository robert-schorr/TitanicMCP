# Proposal

## Why

The query core is not usable by an MCP client until it is exposed through typed tools with a predictable contract. This change adds the MCP tool layer, strict validation, safe errors, and structured logs while keeping transport deployment out of scope.

## What Changes

- Replace the hello-world entrypoint with a FastMCP 4.1.x server exposing `list_tables`, `describe_table`, and `query_data`.
- Delegate tool execution to the query core so data semantics remain in one place.
- Enable strict input validation and reject unexpected fields, type mismatches, unknown tables/columns/operators, and invalid pagination.
- Add an `on_call_tool` middleware that extracts validation field paths, logs internal detail, and returns `Invalid arguments: <field paths>` or `Internal error.`
- Add native `logging` JSON output with one canonical `tool_call` record per call, including tool name, request/correlation ID, duration, status, and error type.
- Add in-process MCP integration tests and a minimal ASGI test seam for HTTP-header correlation.
- Update `README.md` with tool payloads, examples, and the safe error/logging contract.
- Provide a runnable MCP entrypoint using the default stdio transport. Production HTTP serving is added by `add-mcp-http-service`.

This change does **not** add production HTTP profiles, `/healthz`, authentication, host/origin protection, or Docker packaging.

## Capabilities

### New Capabilities

- `mcp-query-tools`: The MCP tool surface that advertises and delegates to the Titanic query core.
- `mcp-tool-safety`: Strict tool input validation, safe client errors, internal diagnostics, structured per-call logs, and log privacy.

### Modified Capabilities

None.

## Impact

- **Code:** Add `server.py` and `logging_config.py`; extend `errors.py`; update `__init__.py`; add integration and security tests.
- **Dependencies:** Add `fastmcp>=4.1.4,<5`; remove the direct `mcp[cli]` dependency; add `pytest-asyncio` and HTTP test support to the test group.
- **Runtime:** The `titanic-mcp` entrypoint runs the MCP server over stdio for this increment.
- **Data:** No schema changes or writes to `data/titanic.db`.
- **Depends on:** `add-titanic-query-core`.
- **Unblocks:** `add-mcp-http-service`.
