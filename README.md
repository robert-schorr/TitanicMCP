# Titanic MCP

A read-only MCP server for the Titanic passenger manifest. It exposes the query
core through three typed tools and serves MCP over Streamable HTTP with safe
local defaults, an operational health endpoint, and explicit local, container,
and remote profiles.

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

By default the server listens on `http://127.0.0.1:8000/mcp`. The default
profile is `local`: loopback-only, unauthenticated, stateless, and protected
against untrusted Host and Origin headers. Logs are written to stderr.

### Health check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

```json
{ "status": "ok" }
```

`GET /healthz` returns 200 once the HTTP app is accepting requests. It does not
require MCP initialization or an authentication token, so it is suitable for
container and load-balancer probes.

### MCP client configuration

Point an MCP client that supports Streamable HTTP at the `/mcp` endpoint:

```json
{
  "mcpServers": {
    "titanic": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Start the server before connecting the client, then list tools and call
`list_tables`. The server exposes exactly `list_tables`, `describe_table`, and
`query_data`.

## Configuration

Configuration comes from environment variables. Blank values are treated as
unset.

| Variable | Default | Purpose |
|---|---|---|
| `TITANIC_MCP_DB_PATH` | `data/titanic.db` | Read-only SQLite file |
| `TITANIC_MCP_HOST` | `127.0.0.1` for `local`; `0.0.0.0` for `container` and `remote` | Bind host |
| `TITANIC_MCP_PORT` | `8000` | Bind port |
| `MCP_PROFILE` | `local` | `local`, `container`, or `remote` |
| `MCP_AUTH_TOKEN` | unset | Optional bearer token; required for `remote` |
| `MCP_ALLOWED_HOSTS` | unset | Comma-separated Host allowlist; required for `container` and `remote` |
| `MCP_ALLOWED_ORIGINS` | unset | Comma-separated Origin allowlist |
| `TITANIC_MCP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `TITANIC_MCP_LOG_FORMAT` | `json` | `json` or `text` |

### Profiles

| Profile | Default bind | Authentication | Sessions | Host/origin protection |
|---|---|---|---|---|
| `local` | `127.0.0.1:8000` | None | Stateless | Automatic loopback protection |
| `container` | `0.0.0.0:8000` | Optional | Stateful | Strict; `MCP_ALLOWED_HOSTS` required |
| `remote` | `0.0.0.0:8000` | Required | Stateful | Strict; token and `MCP_ALLOWED_HOSTS` required |

Startup validation fails before the app accepts requests when settings are
contradictory:

- `local` rejects a non-loopback bind host.
- `container` requires a non-empty `MCP_ALLOWED_HOSTS`.
- `remote` requires a non-empty `MCP_AUTH_TOKEN` and `MCP_ALLOWED_HOSTS`.

The error names the missing or invalid setting.

### Remote profile example

```powershell
$env:MCP_PROFILE = "remote"
$env:TITANIC_MCP_HOST = "0.0.0.0"
$env:MCP_AUTH_TOKEN = "<long-random-token>"
$env:MCP_ALLOWED_HOSTS = "mcp.example.com"
$env:MCP_ALLOWED_ORIGINS = "https://app.example.com"  # optional
uv run titanic-mcp
```

The client must then send `Authorization: Bearer <long-random-token>`. Use a
reverse proxy for TLS termination; the server itself does not provide TLS.

### Container profile example

```powershell
$env:MCP_PROFILE = "container"
$env:MCP_ALLOWED_HOSTS = "localhost:8000,127.0.0.1:8000"
uv run titanic-mcp
```

The `container` profile binds all interfaces inside the container and permits
token omission because the deployment must publish the port only on loopback.
See the exposure warning below.

## Authentication

When `MCP_AUTH_TOKEN` is set, MCP requests must include
`Authorization: Bearer <token>`. Missing or invalid tokens receive HTTP 401 and
never reach tool execution. `GET /healthz` bypasses authentication.

Authentication uses FastMCP's static token verifier. It is suitable for a
private, read-only service; it is not OAuth, does not provide user accounts, and
stores the configured token in memory. The token is read from the environment
and never logged, returned to clients, or embedded in source.

## Host and origin protection

Host/origin protection rejects requests before MCP handling:

- A Host that is not allowed receives HTTP 421.
- An Origin that is not allowed receives HTTP 403.
- `GET /healthz` remains reachable for probes.

`local` uses automatic protection for loopback-bound serving. `container` and
`remote` use strict protection and require an explicit `MCP_ALLOWED_HOSTS`.
`MCP_ALLOWED_ORIGINS` is optional; set it when a browser client must call the
server cross-origin.

Host/origin protection is not CORS. Browser JavaScript that must read
cross-origin responses still needs separate CORS configuration at the client or
proxy layer.

> **Exposure warning:** the bind address is not the same as public exposure.
> The `local` profile rejects non-loopback binds. The `container` profile binds
> `0.0.0.0` inside its network namespace, so the deployment must publish it only
> to loopback. Before exposing the service externally, use the `remote` profile
> with a strong token, an explicit host allowlist, and TLS termination at a
> reverse proxy.

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
