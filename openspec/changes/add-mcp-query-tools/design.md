# Design

## Context

See `proposal.md` for motivation. This change consumes the tested `titanic-data-access` core and adds the MCP tool boundary. The core owns catalog and query semantics; this change owns tool schemas, framework validation, safe errors, and observability. Production HTTP deployment is deliberately deferred.

## Goals / Non-Goals

**Goals:**

- Expose exactly three MCP tools with stable names, descriptions, and schemas.
- Keep data semantics in the core; tool handlers only delegate.
- Strict validation and a non-leaky client error contract.
- One structured audit record per tool call.
- A runnable stdio MCP server and in-process integration tests.

**Non-Goals:**

- Production HTTP profiles, `/healthz`, authentication, host/origin protection, or Docker.
- New query semantics or catalog entries.
- OAuth, per-user authorization, or multi-tenant behavior.
- A custom MCP client or UI.

## Decisions

### 1. Framework and validation

Use FastMCP 4.1.x on MCP SDK v2 with:

- `strict_input_validation=True`
- `mask_error_details=True`
- `transport="stdio"` as the temporary default entrypoint

The MCP SDK v2 `MCPServer` alternative was rejected because its middleware sees a failed `CallToolResult` rather than the original field-level validation exception. FastMCP's `on_call_tool` hook exposes the framework `ValidationError`, which is needed to extract field paths and replace the Pydantic message.

### 2. Tool layer and module boundaries

New or extended modules:

```text
src/titanic_mcp/
  server.py           # FastMCP app factory, tools, middleware, main()
  logging_config.py   # stdlib JSON formatter and logger setup
  errors.py           # add InvalidArgumentsError and SafeToolError
  __init__.py         # re-export main
```

The tool handlers are thin:

```text
list_tables()       -> queries.list_tables() + database count
describe_table(t)   -> queries.describe_table(t) + database count
query_data(request) -> queries.compile_query(request) -> database.fetch_all()
                    -> slice page -> response envelope
```

No tool handler builds SQL or opens a database directly.

### 3. Error mapping

`errors.py` retains `QueryValidationError` from the core and adds:

- `InvalidArgumentsError(field_paths)`
- `SafeToolError(message)`

`ToolCallMiddleware.on_call_tool` maps:

| Condition | Client message | `status` | `error_type` |
|---|---|---|---|
| FastMCP/Pydantic validation | `Invalid arguments: <paths>` | `invalid_arguments` | `validation_error` |
| `QueryValidationError` | `Invalid arguments: <paths>` | `invalid_arguments` | `domain_validation` |
| `SafeToolError` | safe message | `safe_error` | `safe_tool_error` |
| Unexpected exception | `Internal error.` | `internal_error` | `unexpected_exception` |
| Success | tool result | `ok` | `none` |

Field paths come from Pydantic `loc` tuples, formatted as dotted paths with bracket indices (`filter[0].op`). Root-level or unlocatable errors become `request`. Paths are sorted and de-duplicated before the message is built.

The middleware logs the internal Pydantic error types/locations and exception traceback, then raises a `ToolError` with only the safe message. `mask_error_details=True` remains enabled as defense in depth.

### 4. Structured logging

Use native `logging`; do not add loguru.

`logging_config.py` provides:

- `JsonFormatter` emitting flat JSON to stderr with timestamp, level, logger, message, and structured extras.
- Exception objects with type, message, and formatted traceback.
- `configure_logging(level, json_output)`; JSON is the default, text is available for local debugging.
- A narrow filter that removes FastMCP's duplicate `Invalid arguments for tool ...` warning.

FastMCP's own logging configuration is disabled with `fastmcp.settings.log_enabled = False` before startup. The `fastmcp` logger then propagates to the application handler without replacing it or setting `propagate=False`.

The canonical record is emitted once in `finally`:

```text
event="tool_call", tool_name, request_id, correlation_id,
duration_ms, status, error_type, table, filter_count, field_paths
```

- `duration_ms` uses `time.perf_counter()` around `call_next`.
- `request_id` comes from `context.fastmcp_context.request_id`, or a UUID4 fallback.
- `correlation_id` comes from `x-request-id` or `x-correlation-id` via `get_http_headers()`.
- Logs never contain filter values, SQL text, SQL parameters, raw arguments, request bodies, or auth tokens.
- Uvicorn access logs are irrelevant in this increment; the stdio entrypoint does not emit them.

### 5. Minimal HTTP test seam

The app factory also exposes `http_app()` for transport-level tests of header correlation and tool calls. It is not the default entrypoint and has no production profile, health route, authentication, or host/origin configuration in this change. This keeps the logging contract testable without pulling HTTP deployment into the tool change.

### 6. Tests

Security tests:

- strict field/type/table/operator rejection
- exact safe argument messages and root fallback
- unexpected-exception masking
- one canonical log record per call, required fields, correlation IDs, and redaction
- FastMCP duplicate-warning suppression

Integration tests:

- in-process `Client(mcp)` lists the three tools and calls each
- input schemas include the expected fields
- query delegation returns the core envelope
- minimal HTTP client checks correlation headers and tool calls

## Risks / Trade-offs

- **FastMCP 4 is a recent major** → pin `>=4.1.4,<5` and test the middleware seam.
- **Temporary stdio default** → the next change switches the entrypoint to HTTP; the tool contract stays unchanged.
- **Strict validation rejects coercible values** → intentional; documented examples use exact JSON types.
- **Minimal HTTP seam has no production controls** → it is test-only and not the default entrypoint; production controls land in `add-mcp-http-service`.
- **One canonical log record** → FastMCP's own validation warning is filtered narrowly; other framework logs remain available.

## Migration Plan

1. Add FastMCP and test dependencies; remove the direct `mcp[cli]` dependency.
2. Add `server.py` and `logging_config.py`; extend `errors.py`.
3. Replace the hello-world entrypoint with the stdio MCP server.
4. Add security and in-process integration tests.
5. Update README tool and error/logging documentation.

Rollback is a source revert; the core modules and database remain unchanged.

## Open Questions

None.
