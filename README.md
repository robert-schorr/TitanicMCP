# Titanic MCP

A read-only MCP server for the Titanic passenger manifest. It exposes the query
core through three typed tools and runs over stdio for this increment.

> **Transport note:** the default `titanic-mcp` entrypoint uses **stdio** for
> this change. Production Streamable HTTP serving, health checks, profiles,
> authentication, and host/origin controls arrive in `add-mcp-http-service`.

## Setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
uv run pytest
```

The server reads `data/titanic.db` in read-only mode. No tool writes to the
database, and every query is bounded.

## Run the server

```powershell
uv run titanic-mcp
```

The process speaks MCP over stdin/stdout. Logs are written to stderr so they do
not corrupt the protocol stream.

### MCP client configuration

Use the absolute path to this repository. For example, in an MCP client that
accepts a JSON server map:

```json
{
  "mcpServers": {
    "titanic": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\Users\\Robert\\Documents\\Python Projects\\TitanicMCP",
        "titanic-mcp"
      ]
    }
  }
}
```

Start the client, initialize the session, list tools, and call any tool. The
server exposes exactly `list_tables`, `describe_table`, and `query_data`.

## Tools

### `list_tables`

Takes no arguments. Returns the nine catalog entries with row counts. The
`passengers` logical view is the recommended starting point for analysis.

```json
[
  {
    "name": "passengers",
    "kind": "view",
    "description": "Logical view of the Titanic manifest with decoded labels and one row per observation; recommended as the starting point for analysis.",
    "row_count": 891,
    "recommended": true
  }
]
```

The eight raw tables follow: `Observation`, `Sex`, `Embarked`, `Class`, `Who`,
`Deck`, `EmbarkTown`, and `Alive`.

### `describe_table`

Requires the `table` name. Returns the table metadata, including the ordered
columns, their types, nullability, and `default_order_by`.

```json
{
  "table": "passengers"
}
```

The passenger description contains 16 columns and uses `passenger_id` as the
default order.

### `query_data`

Runs a bounded, read-only query. Only JSON-native types are accepted; the server
does not coerce strings into numbers or booleans.

```json
{
  "table": "passengers",
  "columns": ["sex", "age"],
  "filter": [
    { "column": "age", "op": "gte", "value": 30 },
    { "column": "sex", "op": "eq", "value": "female" }
  ],
  "order_by": { "column": "age", "direction": "desc" },
  "limit": 3,
  "offset": 0
}
```

Response envelope:

```json
{
  "table": "passengers",
  "columns": ["sex", "age"],
  "rows": [
    { "sex": "female", "age": 63.0 },
    { "sex": "female", "age": 63.0 },
    { "sex": "female", "age": 62.0 }
  ],
  "row_count": 3,
  "limit": 3,
  "offset": 0,
  "truncated": true,
  "next_offset": 3
}
```

Query rules:

| Field | Rules |
|---|---|
| `table` | Required. One catalog name. |
| `columns` | Optional non-empty list of unique column names. Omit for all columns in catalog order. |
| `filter` | Optional list of up to 20 AND-combined predicates. |
| `filter[].op` | `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `is_null`, or `not_null`. Text columns exclude range operators. |
| `filter[].value` | Must match the column type. `is_null` and `not_null` take no value; `in` takes 1–100 values. |
| `order_by` | Optional single column and `asc`/`desc`. A stable ID tiebreaker is added automatically. |
| `limit` | Optional integer from 1 to 500; default `100`. |
| `offset` | Optional integer greater than or equal to `0`; default `0`. |

Use exact JSON types: `"10"` is not a valid `limit`, and `1` is not a valid
boolean filter value.

## Safe error contract

Validation and tool failures return a tool error rather than leaking framework
details:

| Situation | Client message |
|---|---|
| Pydantic argument validation | `Invalid arguments: <sorted field paths>` |
| Query-core validation | `Invalid arguments: <sorted field paths>` |
| Explicitly safe tool error | The safe message |
| Anything unexpected | `Internal error.` |

Field paths use dotted names and bracket indices:

```text
Invalid arguments: filter[0].op, limit
```

Client responses never contain Pydantic messages, SQL text, parameter values,
or tracebacks.

## Structured logging

The server writes one canonical JSON `tool_call` record per call to stderr:

```json
{
  "timestamp": "2026-10-27T19:01:48.564346Z",
  "level": "INFO",
  "logger": "titanic_mcp.server",
  "message": "tool_call",
  "event": "tool_call",
  "tool_name": "query_data",
  "request_id": "3",
  "correlation_id": null,
  "duration_ms": 6.933,
  "status": "invalid_arguments",
  "error_type": "validation_error",
  "table": "passengers",
  "filter_count": 0,
  "field_paths": ["limit"]
}
```

`status` is one of `ok`, `invalid_arguments`, `safe_error`, or
`internal_error`. `error_type` is one of `none`, `validation_error`,
`domain_validation`, `safe_tool_error`, or `unexpected_exception`.

Internal diagnostics (validation error types/locations and unexpected exception
tracebacks) are logged separately. The canonical record never contains filter
values, raw arguments, authorization headers, SQL, or parameter values.

## Development quality gates

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```
