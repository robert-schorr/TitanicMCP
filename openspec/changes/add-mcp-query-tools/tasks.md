# Tasks

## 1. Dependencies and server foundation

- [ ] 1.1 Update `pyproject.toml` to add `fastmcp>=4.1.4,<5`, remove the direct `mcp[cli]` dependency, and add `pytest-asyncio`, `httpx`, and async test configuration; verify `uv lock` and `uv sync` succeed and `uv run python -c "import fastmcp; print(fastmcp.__version__)"` reports 4.1.x
- [ ] 1.2 Implement `logging_config.py` with a stdlib JSON formatter, stderr handler, exception type/message/traceback serialization, and `configure_logging(level, json_output)`; verify `tests/security/test_logging.py` parses the JSON and checks required fields
- [ ] 1.3 Extend `errors.py` with `InvalidArgumentsError` and `SafeToolError` while keeping the core contract unchanged; verify unit tests cover safe messages and field paths
- [ ] 1.4 Create the FastMCP app factory with `strict_input_validation=True`, `mask_error_details=True`, server instructions, and the `titanic-mcp` entrypoint wrapper; verify the app imports and starts without opening a database
- [ ] 1.5 Ensure the package no longer exposes the hello-world entrypoint and `src/titanic_mcp/__init__.py` re-exports `main`; verify `uv run python -c "import titanic_mcp"` succeeds

## 2. MCP tools and delegation

- [ ] 2.1 Implement `list_tables` with no arguments, a description that names `passengers` as the recommended starting point, and delegation to the core catalog; verify `tests/integration/test_mcp_tools.py`
- [ ] 2.2 Implement `describe_table` with a required table name and delegation to core metadata; verify the passengers description returns 16 columns, types, nullability, and `default_order_by`
- [ ] 2.3 Implement `query_data` as a thin orchestrator: validate, compile, fetch `limit + 1`, build the response envelope, and return it unchanged; verify projection, filtering, ordering, and pagination through the in-process client
- [ ] 2.4 Verify the advertised schemas: exactly three tools, non-empty descriptions, `table` required, and optional `columns`, `filter`, `order_by`, `limit`, and `offset`; verify `tests/integration/test_mcp_schemas.py`

## 3. Safe errors and tool-call middleware

- [ ] 3.1 Implement `ToolCallMiddleware.on_call_tool` to time the call, collect `request_id` from the FastMCP context with a UUID4 fallback, and collect `correlation_id` from `x-request-id` or `x-correlation-id`; verify `tests/integration/test_correlation.py`
- [ ] 3.2 Implement Pydantic validation-error path extraction, formatting dotted paths with bracket indices, sorting and de-duplicating, and falling back to `request`; verify extra fields, type mismatches, unknown operators, and pagination bounds produce exact `Invalid arguments: ...` messages
- [ ] 3.3 Map `QueryValidationError` to safe argument errors, `SafeToolError` to its safe message, and all other exceptions to `Internal error.`; verify no Pydantic text, SQL, parameter values, or tracebacks reach clients
- [ ] 3.4 Emit exactly one canonical JSON `tool_call` record per call with tool name, request/correlation IDs, `duration_ms`, status, error type, table, filter count, and field paths; verify redaction of filter values, raw arguments, SQL, and authorization headers
- [ ] 3.5 Disable FastMCP's own logging configuration and narrowly filter its duplicate `Invalid arguments for tool` warning; verify the canonical record count remains exactly one per successful and failed call

## 4. In-process and transport-seam tests

- [ ] 4.1 Add async integration fixtures using the in-process MCP client; verify initialization, tool listing, and successful calls to all three tools
- [ ] 4.2 Add security integration tests for unexpected-exception masking, classified safe errors, root-level validation failures, and internal-detail logging; verify client responses and captured logs separately
- [ ] 4.3 Expose a minimal `http_app()` ASGI seam for header-correlation tests only; verify an HTTP request with `x-request-id` produces the same `correlation_id` in the canonical log and that tool calls still succeed
- [ ] 4.4 Verify the stdio entrypoint with an MCP client session: start `uv run titanic-mcp`, initialize, list the three tools, and call `list_tables`; confirm the session exits cleanly

## 5. Documentation and quality gates

- [ ] 5.1 Update `README.md` with tool payloads, strict JSON-type examples, the safe error format, the logging record, and stdio client setup; verify each example through the in-process client
- [ ] 5.2 Document that the stdio entrypoint is temporary for this increment and that production HTTP serving arrives in `add-mcp-http-service`
- [ ] 5.3 Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run ty check`; verify all pass
- [ ] 5.4 Confirm the change adds no HTTP profiles, `/healthz` route, authentication, host/origin configuration, or Docker artifacts

## Workflow follow-up

- Archive the change after implementation and review are complete.
- Sync the `mcp-query-tools` and `mcp-tool-safety` delta specs into the main OpenSpec specs during archive and verify the resulting capability files.
