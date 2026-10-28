# Titanic MCP

A read-only MCP server for the Titanic passenger manifest. It exposes the query
core through three typed tools and serves MCP over Streamable HTTP with safe
local defaults, an operational health endpoint, and explicit local, container,
and remote profiles.

## Setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/). Container
deployment additionally requires Docker with Compose v2.24.4 or newer; see
[Container deployment](#container-deployment).

```powershell
uv sync
uv run pytest
```

Run `uv run pytest --cov=titanic_mcp` to include coverage.

The server reads `data/titanic.db` in read-only mode. No tool writes to the
database, and every query is bounded. The database is opened at startup; the
server exits with a clear error if it is missing or unreadable.

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

The default database path is relative to an editable checkout. When the package
is installed non-editable, set `TITANIC_MCP_DB_PATH` explicitly.

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

## Container deployment

The container image packages the same HTTP service. It runs as a non-root user,
needs no writable root filesystem, and reads the database from a read-only bind
mount. Docker with Compose v2.24.4 or newer is required, and `data/titanic.db`
must exist on the host.

> **Container exposure warning:** the default Compose file publishes port 8000
> only on `127.0.0.1`. Do not change that mapping to expose the service. Use the
> remote overlay with a strong `MCP_AUTH_TOKEN`, an explicit
> `MCP_ALLOWED_HOSTS` value, and TLS termination at a reverse proxy before
> allowing external access.

### Build the image

```powershell
docker compose build
```

The multi-stage build uses the Debian Trixie slim variant for the uv builder
and the `python:3.13-slim-trixie` runtime. It installs from `uv.lock` with
`--frozen --no-default-groups --no-editable` and copies only the prepared virtual
environment into the runtime stage. The runtime image contains no compiler
toolchain, uv cache, project tests or test dependencies, database file, or
secrets.

### Run the default profile

```powershell
docker compose up -d
```

The default profile sets `MCP_PROFILE=container` and
`MCP_ALLOWED_HOSTS=localhost:8000,127.0.0.1:8000`, binds `0.0.0.0` inside the
container, and publishes `127.0.0.1:8000` only. It also uses a read-only root
filesystem, a read-only database mount, `no-new-privileges`, a 64 MB
`noexec,nosuid` tmpfs at `/tmp`, and resource limits of 1 CPU, 512 MB memory,
and 64 PIDs.

Point the MCP client at `http://127.0.0.1:8000/mcp` using the client
configuration shown above. No token is required for the default profile
because the published port is not externally reachable.

### Container healthcheck

The container healthcheck calls `GET /healthz` with the Python standard
library. It starts after 5 seconds, runs every 5 seconds, and marks the
container unhealthy after five failed 3-second probes.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
docker compose ps
docker inspect --format '{{.State.Health.Status}}' (docker compose ps -q titanic-mcp)
```

`GET /healthz` returns 200 without MCP initialization or authentication.
`docker compose ps` reports `(healthy)` once the service is accepting requests.

### Test the container deployment

With Docker running:

```powershell
uv run python scripts/test_container.py
```

The script builds `titanic-mcp:container-test`, starts it with the Compose
security settings, waits for `/healthz`, calls `list_tables`, and verifies the
process runs as UID 10001. It is intentionally separate from `uv run pytest`.

### Run the remote overlay

The remote overlay publishes port 8000 on all interfaces and requires a token
and an explicit host allowlist. Compose interpolation fails before the
container starts if either value is missing.

```powershell
$env:MCP_AUTH_TOKEN = "<long-random-token>"
$env:MCP_ALLOWED_HOSTS = "mcp.example.com:8000"
$env:MCP_ALLOWED_ORIGINS = "https://app.example.com"  # optional
docker compose -f compose.yaml -f compose.remote.yaml up -d
```

The overlay sets `MCP_PROFILE=remote`, replaces the loopback mapping with
`8000:8000`, and inherits the read-only filesystem, tmpfs, read-only database
mount, `no-new-privileges`, resource limits, restart policy, and healthcheck
from `compose.yaml`.

MCP clients must send `Authorization: Bearer <long-random-token>`. Requests
without a valid token receive HTTP 401. Use the public host value in
`MCP_ALLOWED_HOSTS`; when TLS terminates at a reverse proxy, include the Host
header that the proxy forwards (without a port for the default HTTPS port).
Set `MCP_ALLOWED_ORIGINS` only when a browser client calls the service
cross-origin.

To stop the overlay:

```powershell
docker compose -f compose.yaml -f compose.remote.yaml down
```

### Troubleshooting

```powershell
docker compose config
docker compose logs --tail=50 titanic-mcp
docker compose exec titanic-mcp id
docker compose down
```

- `MCP_AUTH_TOKEN is required` or `MCP_ALLOWED_HOSTS is required`: export both
  variables before starting the remote overlay.
- HTTP 401 from `/mcp`: send the bearer token configured in
  `MCP_AUTH_TOKEN`. `/healthz` remains unauthenticated.
- HTTP 421 or 403: add the client's Host or Origin value to
  `MCP_ALLOWED_HOSTS` or `MCP_ALLOWED_ORIGINS`.
- The container exits with a configuration error: `MCP_PROFILE=remote` requires
  both `MCP_AUTH_TOKEN` and `MCP_ALLOWED_HOSTS`.
- The server exits because the database is missing: ensure `data/titanic.db`
  exists; the container mounts it read-only and never copies it into the image.
  When running an installed package outside the repo, set `TITANIC_MCP_DB_PATH`.
- Port 8000 is already in use: stop the local `uv run titanic-mcp` process or
  the other container using the port, then retry.
- Source changes are not visible: rebuild with
  `docker compose up -d --build`.
- Inspect the resolved profile, mounts, ports, and healthcheck with
  `docker compose config`.

The image runs as UID/GID 10001 (`titanic`).
`docker compose exec titanic-mcp id` confirms the runtime identity.

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
