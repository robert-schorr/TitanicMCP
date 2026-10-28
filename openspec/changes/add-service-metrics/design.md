# Design

## Context

`ToolCallMiddleware.on_call_tool` already times every call with `time.perf_counter()`, derives `duration_ms` in its `finally` block, and classifies the outcome as `status` and `error_type` before writing the single canonical `event="tool_call"` log record. The measurement and the classification exist; only a scrapeable sink is missing. See `proposal.md` for why this change exists, and `specs/service-metrics/spec.md` for the behavior contract.

Two facts from the installed FastMCP 4.1.4 shape the endpoint:

- The auth provider's `get_middleware()` contributes a `starlette` `AuthenticationMiddleware` with `BearerAuthBackend` to the **whole** application, plus `AuthContextMiddleware`. Only the `/mcp` route is additionally wrapped in `RequireAuthMiddleware`, which performs the rejection. A custom route therefore sees an already-populated `scope["user"]` without being enforced by it.
- `FastMCP.custom_route` is the same mechanism `GET /healthz` uses, so `/metrics` inherits the existing route ordering and the app-wide host/origin guard.

## Goals / Non-Goals

**Goals:**

- One additional dependency, no collector, no exporter pipeline.
- Metrics that describe exactly what the log record already says, so dashboards and log queries agree.
- A label set whose size is decided by the server, not by the client.
- No new configuration and no change to the tool, error, or logging contracts.

**Non-Goals:**

- HTTP-level metrics, so auth rejections, host/origin rejections, and 404s do not appear in the series.
- OpenTelemetry SDK, tracing export, exemplars, or `process_*`/`python_*` runtime metrics.
- Multi-process aggregation: each worker exposes its own series and PromQL sums across them.
- Scrape interval, alert thresholds, dashboards, or a Prometheus deployment in this repository.

## Decisions

### Prometheus-native rather than an OpenTelemetry pipeline

`prometheus-client` 0.26 has no default transitive dependencies, and `generate_latest(registry)` writes the endpoint in a few lines. The OTel route needs `opentelemetry-sdk` plus an exporter before a single number is visible, and `opentelemetry-exporter-prometheus` itself depends on `prometheus-client`, so OTel-first adds packages without removing any. FastMCP's own instrumentation is trace-only and already a no-op without an SDK, which means adopting OTel later stays possible: a collector can scrape this endpoint, or an SDK can be added for traces in a separate change.

### Record inside the existing middleware

The metrics call belongs in the same `finally` block as the log record, using the same `started`, `tool_name`, `status`, and `error_type` values. This cannot drift from the log contract, cannot miss a call that fails, and avoids a second timer.

A separate ASGI middleware would measure the HTTP request instead: it would also catch auth and host rejections, but it cannot attribute a call to a tool without parsing the JSON-RPC body, and it would measure body length instead of tool work. That is a different metric for a different question, and it is out of scope here.

### One recorder instance per application

`create_app` constructs the recorder, passes it to `ToolCallMiddleware`, and closes over it in the `/metrics` route. The recorder owns a private `CollectorRegistry`, so two applications in the same process — the normal case in tests — never share samples and never raise on duplicate registration.

The alternatives are worse: module-level `Counter`/`Histogram` objects bind to the default registry and break the moment a second app is created; a context variable would hide the dependency and demand per-request plumbing for no benefit. The cost is one constructor argument, which makes the bare `ToolCallMiddleware()` in `tests/security/test_mcp_tool_safety.py` fail to construct until it passes a recorder. That is a deliberate signature change: a middleware that silently records nowhere is harder to notice than an error at construction.

### Clamp the `tool` label

`on_call_tool` receives `context.message.name` before the tool is resolved, so the value is client-controlled. Verified against a live client: calling a 200-character tool name delivers that exact name to the middleware, and an unrecognized name is classified `status="internal_error"`, `error_type="unexpected_exception"`. Using the raw name as a label would let any client — including an unauthenticated local one — mint unbounded series and exhaust the scrape payload.

The recorder therefore maps the three exposed names to themselves and everything else to `unknown`. The unknown call is still counted, so the traffic is visible, and the series count stays at four. Dropping unknown calls would hide probing traffic; normalizing the name further (for example lowercasing) would buy nothing.

### Keep the status contract unchanged

An unknown tool keeps reporting `internal_error` in both the log and the counter. Adding an `unknown_tool` status would be more precise, but it changes a contract that `mcp-tool-safety` owns and every assertion that enumerates statuses, in exchange for a value that only matters when someone is probing. Dashboards that measure server health use `tool!="unknown"`.

### Authenticate by reading the attached user

When `MCP_AUTH_TOKEN` is set, the `/metrics` handler returns 401 unless `request.user.is_authenticated`. Verified behavior of the installed stack: a valid bearer token yields an authenticated user, a wrong or absent token yields an unauthenticated one, and a configured provider means the middleware is always installed. When no token is configured, no auth middleware exists and accessing `request.user` raises `AssertionError`, so the check is guarded by the same `config.auth_token` condition that decides whether a provider is created.

Parsing `Authorization` and comparing the token in the handler would duplicate the verifier, duplicate its comparison behavior, and create a second place where a credential is read. Reading the attached user keeps one authentication path for the whole application. The 401 response carries a `WWW-Authenticate: Bearer` header and an empty body, so a scrape failure looks like an authentication failure rather than a malformed metrics document.

### Always on, protected by the existing guard

No configuration flag. The endpoint costs one regex-free route and a few dozen series, and a flag would add a config field, profile validation, and a branch in every deployment path.

`/metrics` stays behind the app-wide host/origin guard. Exempting it would mean changing `HostOriginGuardMiddleware` usage or moving the route outside it, which is more code and a second security path. The operational cost is that the scrape's `Host` header must be allowlisted in the container and remote profiles; that belongs in the README next to the existing scrape-unrelated host guidance.

### Buckets sized for SQLite reads

The histogram uses `0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5` seconds. Prometheus's default buckets start at 5 ms, which would put nearly every call in the first bucket and make a p95 useless. The range tops out at 2.5 s, above the slowest plausible bounded query, with `+Inf` closing the tail.

### Private registry without runtime metrics

The private registry deliberately contains only the two tool-call families, so `process_*` and `python_*` metrics do not appear. Platform metrics are cheap to add later with a second collector, but exposing memory and file-descriptor counts is a separate decision from measuring tool calls.

## Risks / Trade-offs

- **Unknown-tool probes inflate the error rate** → documented PromQL excludes `tool="unknown"`; the label keeps the traffic separable rather than mixing it into real tool names.
- **Scrape fails with 421 in container or remote profiles** → the README states that the scrape `Host` must be in `MCP_ALLOWED_HOSTS`; the existing profile validation already forces that variable to be set.
- **Per-worker counters** → rate queries sum across instances; no aggregation is attempted in the process.
- **A future fourth tool must be added to the clamp set** → the mapping lives beside the tool registration, and the integration test asserts the exposed names, so a missed entry fails a test rather than silently collapsing to `unknown`.
- **Repeated `create_app` calls in tests** → per-app registry removes the duplicate-registration failure that module-level metrics would cause.
