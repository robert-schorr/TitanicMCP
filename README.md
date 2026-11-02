# Titanic MCP

A read-only MCP server for the Titanic passenger manifest. It exposes the query
core through three typed tools and serves MCP over Streamable HTTP with safe
local defaults, an operational health endpoint, and explicit local, container,
and remote profiles. See [`docs/architecture.md`](docs/architecture.md) for
design rationale and the full contracts.

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
server exits with a clear error if it is missing, unreadable, or does not contain
the Titanic catalog.

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
| `container` | `0.0.0.0:8000` | Optional | Stateless | Strict; `MCP_ALLOWED_HOSTS` required |
| `remote` | `0.0.0.0:8000` | Required | Stateless | Strict; token and `MCP_ALLOWED_HOSTS` required |

All profiles are stateless, so no session affinity is required and the service can
run behind a round-robin load balancer. Server-initiated session features are not
available.

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

## Container deployment

The container image packages the same HTTP service. It runs as a non-root user,
needs no writable root filesystem, and reads the database from a read-only bind
mount. Docker with Compose v2.24.4 or newer is required, and `data/titanic.db`
must exist on the host.

> **Container exposure warning:** the default Compose file publishes port 8000
> only on `127.0.0.1`. Do not change that mapping to expose the service. Use the
> remote overlay with a strong `MCP_AUTH_TOKEN`, an explicit
> `MCP_ALLOWED_HOSTS` value, and TLS termination at a reverse proxy before
> allowing external access. The image itself does not enforce the loopback
> binding; that protection comes from the Compose port mapping.

### Build and run

```powershell
docker compose build
docker compose up -d
```

The default profile publishes `127.0.0.1:8000` only, so no token is required.
Inspect the resolved profile, mounts, ports, and security settings with
`docker compose config`.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
docker compose ps
docker inspect --format '{{.State.Health.Status}}' (docker compose ps -q titanic-mcp)
```

`GET /healthz` returns 200 without MCP initialization or authentication.
`docker compose ps` reports `(healthy)` once the service is accepting requests.
The image runs as UID/GID 10001 (`titanic`); `docker compose exec titanic-mcp id`
confirms the runtime identity.

To test the image with Docker running:

```powershell
uv run python scripts/container_smoke_test.py
```

The script builds `titanic-mcp:container-test` and starts it twice: once with the
default `container` profile and once with the `remote` profile and a bearer
token. Each run waits for `/healthz`, calls `list_tables`, and verifies the
process runs as UID 10001. The remote run also verifies that unauthenticated MCP
requests are rejected and that the token never reaches the logs. It is
intentionally separate from `uv run pytest`.

### Remote overlay

The remote overlay publishes port 8000 on all interfaces and requires a token
and an explicit host allowlist. Compose interpolation fails before the
container starts if either value is missing.

```powershell
$env:MCP_AUTH_TOKEN = "<long-random-token>"
$env:MCP_ALLOWED_HOSTS = "mcp.example.com:8000"
$env:MCP_ALLOWED_ORIGINS = "https://app.example.com"  # optional
docker compose -f compose.yaml -f compose.remote.yaml up -d
```

The overlay sets `MCP_PROFILE=remote` and inherits the security settings,
restart policy, and healthcheck from `compose.yaml`. MCP clients must send
`Authorization: Bearer <long-random-token>`; requests without a valid token
receive HTTP 401. Use the public host value in `MCP_ALLOWED_HOSTS`; when TLS
terminates at a reverse proxy, include the Host header that the proxy forwards
(without a port for the default HTTPS port). Set `MCP_ALLOWED_ORIGINS` only when
a browser client calls the service cross-origin.

To stop the overlay:

```powershell
docker compose -f compose.yaml -f compose.remote.yaml down
```

### Troubleshooting

```powershell
docker compose config
docker compose logs --tail=50 titanic-mcp
docker compose down
```

- `MCP_AUTH_TOKEN is required` or `MCP_ALLOWED_HOSTS is required`: export both
  variables before starting the remote overlay.
- HTTP 401 from `/mcp`: send the bearer token configured in
  `MCP_AUTH_TOKEN`. `/healthz` remains unauthenticated.
- HTTP 421 or 403: add the client's Host or Origin value to
  `MCP_ALLOWED_HOSTS` or `MCP_ALLOWED_ORIGINS`.
- The server exits because the database is missing: ensure `data/titanic.db`
  exists; the container mounts it read-only and never copies it into the image.
  When running an installed package outside the repo, set `TITANIC_MCP_DB_PATH`.
- Port 8000 is already in use: stop the local `uv run titanic-mcp` process or
  the other container using the port, then retry.
- Source changes are not visible: rebuild with
  `docker compose up -d --build`.

## Authentication and host protection

When `MCP_AUTH_TOKEN` is set, MCP requests must include
`Authorization: Bearer <token>`; missing or invalid tokens receive HTTP 401 and
never reach tool execution. `/healthz` bypasses authentication. Host/origin
protection rejects a disallowed Host with HTTP 421 and a disallowed Origin with
HTTP 403, but it is not CORS: browser clients that need cross-origin access still
require CORS configuration at the client or proxy layer.

Authentication uses FastMCP's static token verifier. It is suitable for a
private, read-only service; it is not OAuth, does not provide user accounts, and
stores the configured token in memory. The token is read from the environment
and never logged, returned to clients, or embedded in source. See
[`docs/architecture.md`](docs/architecture.md#9-security-model) for the full
security model.

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

Example response (trimmed after the second column):

```json
{
  "name": "passengers",
  "kind": "view",
  "description": "Logical view of the Titanic manifest with decoded labels and one row per observation; recommended as the starting point for analysis.",
  "row_count": 891,
  "default_order_by": "passenger_id",
  "columns": [
    {
      "name": "passenger_id",
      "type": "integer",
      "nullable": false,
      "description": "Observation row identifier (Observation.rowid)."
    },
    {
      "name": "survived",
      "type": "integer",
      "nullable": false,
      "description": "Survival indicator (0 = died, 1 = survived)."
    }
  ]
}
```

The passenger description contains 16 columns and uses `passenger_id` as the
default order. `type` is one of `integer`, `number`, `text`, or `boolean`.

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
| `offset` | Optional integer from `0` to `100000`; default `0`. |

Use exact JSON types: `"10"` is not a valid `limit`. Boolean columns accept the
JSON booleans `true`/`false` and the integers `0`/`1`.

## Safe error contract

Validation and tool failures return a tool error rather than leaking framework
details:

| Situation | Client message |
|---|---|
| Pydantic argument validation | `Invalid arguments: <sorted field paths>` |
| Query-core validation | `Invalid arguments: <sorted field paths>` |
| Anything unexpected | `Internal error.` |

Field paths use dotted names and bracket indices:

```text
Invalid arguments: filter[0].op, limit
```

Client responses never contain Pydantic messages, SQL text, parameter values,
or tracebacks. See
[`docs/architecture.md`](docs/architecture.md#6-error-contract) for the mapping
to log statuses and error types.

## Structured logging

The server writes one canonical JSON `event="tool_call"` record per call to
stderr. Records contain metadata only: tool name, request and correlation IDs,
duration, status, error type, table, filter count, and field paths. They never
contain filter values, raw arguments, SQL, parameters, or tokens. Uvicorn's own
startup and access logs remain plain text.

The full record shape, `status` and `error_type` values, and redaction rules are
in
[`docs/architecture.md`](docs/architecture.md#7-logging-contract).

## Development quality gates

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

## Next steps

Deferred work and hardening options are tracked in
[`docs/next-steps.md`](docs/next-steps.md).
