# TitanicMCP architecture diagram

Companion to [`architecture-diagram.html`](architecture-diagram.html), an interactive
diagram of the service as it exists today. Open the HTML file directly in a browser; there
is no build step. All logic and styles are inline. The optional Google Fonts load when
online and fall back to system fonts offline.

The authoritative design rationale is in [`architecture.md`](architecture.md). This page
summarizes what the diagram shows, how the three deployment profiles differ, and what each
flow demonstrates.

## Using the diagram

- **Deployment profile** — switch between `local`, `container`, and `remote`. Node
  technology, ports, and the first payload of some flows change with the profile.
- **Flow tabs** — choose a scenario: query data, discover schema, safe errors, or startup
  and health.
- **Playback** — use the arrow buttons, `Space` to play/pause, or the left/right arrow
  keys. Click any node to jump to the first step where it participates.
- **Payload panel** — each step shows the concrete wire payload, SQL, result, or log record
  on the right.
- **Layout** — drag a node to reposition it, or press `R` to reset. `T` toggles the theme,
  `F` expands the canvas, and `O` cycles profiles. The shortcuts can be disabled with the
  `shortcuts` link for keyboard and screen-reader users.

## Components

The diagram uses eight tiles. Supporting modules (`models.py`, `errors.py`, and
`logging_config.py`) are folded into the tile that owns their behavior.

| Tile | Responsibility | Primary code |
|---|---|---|
| **Entrypoint** | Parse and validate configuration, configure logging, prove the database is readable, build the app, bind the port. A bad profile exits before the port opens. | `server.py` (`load_config`, `validate_config`, `main`) |
| **MCP client** | Sends JSON-RPC `tools/call` requests over Streamable HTTP. Never sends SQL. | External client |
| **Health probe** | Calls `GET /healthz`; used by the container healthcheck. No MCP session and no bearer token. | `compose.yaml`, `server.py` (`_healthz`) |
| **FastMCP HTTP app** | Streamable HTTP at `/mcp`, strict input validation, Host/Origin protection, and optional bearer authentication. | `server.py` (`create_app`, `http_app`) |
| **Tool boundary** | `ToolCallMiddleware`, the `_safe_tool` adapter, and the three thin tools. Classifies failures, returns safe messages, and emits the canonical log record. | `server.py` (`ToolCallMiddleware`, `_safe_tool`, `_register_tools`) |
| **Query core** | Static catalog, semantic validation, SQL compilation, pagination envelope. Owns all query semantics. | `queries.py` |
| **Titanic SQLite** | Read-only access with `mode=ro` and `PRAGMA query_only`; a fresh connection per operation. No write API. | `database.py` |
| **stderr JSON logs** | One canonical `event="tool_call"` record per call, metadata only. Diagnostic events are separate records. | `logging_config.py`, `server.py` |

The catalog has nine entries: the `passengers` view (recommended) plus eight raw tables
(`Observation`, `Sex`, `Embarked`, `Class`, `Who`, `Deck`, `EmbarkTown`, `Alive`).

## Deployment profiles

| Profile | Bind | Client endpoint | Auth | Required allowlist | HTTP sessions |
|---|---|---|---|---|---|
| `local` | `127.0.0.1:8000` | `http://127.0.0.1:8000/mcp` | None by default; a token is honored if set | Optional | Stateless |
| `container` | `0.0.0.0:8000` inside the container, published as `127.0.0.1:8000` | `http://127.0.0.1:8000/mcp` | None by default; a token is honored if set | `MCP_ALLOWED_HOSTS` | Stateful |
| `remote` | `0.0.0.0:8000` behind a TLS-terminating proxy | `https://mcp.example.com/mcp` | `MCP_AUTH_TOKEN` required (16+ characters) | `MCP_ALLOWED_HOSTS` | Stateful |

Profile rules enforced at startup:

- `local` rejects a non-loopback bind.
- `container` rejects an empty `MCP_ALLOWED_HOSTS`.
- `remote` rejects a missing token or allowlist, and a token shorter than 16 characters.
- An unknown profile, invalid port, log level, or log format is rejected.

`container` permits an omitted token **only** because the shipped Compose file publishes
the port on loopback. Publishing it on `0.0.0.0` requires the `remote` profile. TLS is
terminated by an external reverse proxy; the diagram does not draw a proxy tile.

`/healthz` is independent of MCP initialization and authentication. The Host/Origin guard
still wraps the app, so probes must send an allowed `Host` header.

## Flows

### 1. Query data (`query_data`) — 8 steps

The happy path, from JSON-RPC to a bounded result:

1. **Client → HTTP app.** `POST /mcp` with a `tools/call` request for `query_data`.
2. **HTTP app → tool boundary.** FastMCP decodes the request and validates the tool
   signature: strict strings and integers, `extra="forbid"`, `limit` 1–500, `offset`
   0–100000.
3. **Boundary → query core.** `validate_query()` checks catalog membership, column
   existence, operator/type compatibility, predicate count, and value types.
   `compile_query()` then builds static SQL. Identifiers come from the catalog; every value
   becomes a `?` parameter.
4. **Core → SQLite.** `fetch_all()` opens a fresh read-only connection and executes the
   statement with bound parameters. It fetches `limit + 1` rows.
5. **SQLite → core.** Ordered rows return; the extra row is the pagination signal.
6. **Core → boundary.** `build_response()` slices the fetch into the public envelope:
   `rows`, `row_count`, `truncated`, and `next_offset`.
7. **Boundary → HTTP app.** The tool returns the envelope unchanged. In `finally`, the
   middleware emits exactly one canonical `event="tool_call"` record to stderr.
8. **HTTP app → client.** The JSON-RPC result contains catalog columns and the pagination
   envelope, never SQL or internal details.

The compiled SQL projects from the catalog's static `source_sql`, orders nulls last with a
stable `passenger_id` tiebreaker, and ends with `LIMIT ? OFFSET ?`.

### 2. Discover schema (`list_tables`) — 8 steps

1. **Client → HTTP app.** `tools/call` for `list_tables` with no arguments.
2. **HTTP app → boundary.** FastMCP validates the empty argument object and dispatches the
   tool.
3. **Boundary → core.** The core walks the nine hand-written `TableSpec` entries. The
   catalog is a code contract, not runtime schema introspection.
4. **Core → SQLite.** Each entry runs one live
   `SELECT COUNT(*) FROM (<source_sql>)` query.
5. **SQLite → core.** One count per entry returns.
6. **Core → boundary.** Nine typed `TableSummary` objects carry name, kind, description,
   row count, and the `recommended` flag.
7. **Boundary → HTTP app.** The summaries are serialized and the same canonical log record
   is emitted.
8. **HTTP app → client.** The client can call `describe_table` for columns and types, then
   `query_data` for rows.

`describe_table` shares the same catalog and runs one count for the requested entry;
`list_tables` runs one count per entry.

### 3. Safe errors and logging — 7 steps

1. **Client → HTTP app.** A structurally valid call asks for the unknown column `agee`.
2. **HTTP app → boundary.** Pydantic validates shape only; catalog meaning is not its job.
3. **Boundary → core.** `validate_query()` finds no `agee` in the table's `column_map` and
   raises a field-scoped `QueryValidationError`. The SQL compiler never runs.
4. **Core → boundary.** `_safe_tool` re-raises the domain error as a `ToolError` subclass
   (`_ClassifiedToolError`). This is required because FastMCP masks non-`ToolError`
   exceptions before middleware sees them.
5. **Boundary → logs.** The middleware writes one metadata-only failure record. It
   contains the tool name, status, error type, table, filter count, and field paths — no
   values, SQL, parameters, or tracebacks.
6. **Boundary → HTTP app.** The client message is normalized to
   `Invalid arguments: columns[0]`.
7. **HTTP app → client.** The error is a tool result (`isError: true`), not a transport
   crash, so the session stays usable.

Unexpected exceptions become `Internal error.`; both paths keep implementation details
out of the client response.

### 4. Startup and health — 4 steps

1. **Entrypoint → SQLite.** `load_config()` parses the environment, `validate_config()`
   rejects contradictory profiles, and the entrypoint opens the database once with
   `SELECT 1`. A missing or unreadable file exits before serving.
2. **Entrypoint → HTTP app.** `create_app()` registers the three tools, the middleware, and
   `/healthz`; `run()` binds the configured host and port. `create_app()` itself does not
   open the database.
3. **Probe → HTTP app.** `GET /healthz` with an allowed `Host` header. No token, no MCP
   session, no database check. The inherited Compose healthcheck calls
   `http://127.0.0.1:8000/healthz`, so the remote example allowlist includes
   `127.0.0.1:8000` as well as the public host.
4. **HTTP app → probe.** `200 {"status": "ok"}`. The container healthcheck runs every five
   seconds and marks the service unhealthy after five failed three-second probes.

## Invariants the diagram encodes

- User input never becomes SQL text. Only catalog identifiers and closed-enum directions
  are interpolated; all values are bound parameters.
- Every query is bounded: `limit` 1–500, `offset` 0–100000, at most 16 projected columns,
  at most 20 predicates.
- The database is read-only by construction: `mode=ro`, `PRAGMA query_only`, fresh
  connection per operation, and no write API.
- One canonical `event="tool_call"` record per call; no raw arguments, filter values, SQL,
  parameters, request bodies, auth headers, or tokens.
- Safe client messages are limited to `Invalid arguments: <sorted paths>`, an explicit
  `SafeToolError` message, and `Internal error.`.
- `/healthz` is shallow, unauthenticated, and independent of MCP initialization.
- Profiles fail closed before the port is bound.

## Scope

The diagram describes the current implementation only:

- Three tools: `list_tables`, `describe_table`, `query_data`.
- No metrics endpoint and no CI workflow; those OpenSpec changes are not implemented.
- Remote TLS is external to the app, so there is no reverse-proxy tile.
- The interactive diagram uses the architecture-diagram skill template at
  `.opencode/skills/architecture-diagram/assets/template.html`; flow data lives in the
  `flows` object near the end of `architecture-diagram.html`.

For the reasoning behind these choices, read [`architecture.md`](architecture.md). For the
exact tool contracts and operational commands, read [`../README.md`](../README.md).
