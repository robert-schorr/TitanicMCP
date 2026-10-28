# Proposal

## Why

Every tool call already produces one canonical JSON log record with a duration, status, and error type, but nothing scrapeable. Call volume, tail latency, and error rate can only be obtained by parsing stderr logs, so the container and remote deployments have no time series to alert on.

## What Changes

- Add `GET /metrics` to the existing HTTP application, serving the Prometheus text exposition format from `prometheus-client`.
- Record one counter and one duration histogram inside the existing `ToolCallMiddleware` finally-block, reusing the `status` and `error_type` values it already computes. No second timer, no new classification.
- Clamp the `tool` label to the three exposed tool names plus `unknown`, because the middleware sees the client-supplied name before resolution and must not mint a series per arbitrary string.
- Require the same bearer token on `/metrics` when `MCP_AUTH_TOKEN` is configured, by reading the authenticated user the auth middleware already attaches to the request. Leave `/metrics` open when no token is configured, matching `/healthz`.
- Keep host/origin protection unchanged, so a scrape must send an allowlisted `Host`; document that requirement instead of exempting the route.
- Leave error rate and latency as derived PromQL over the counter and histogram. No process-local rate gauge, no HTTP-level metrics, no OpenTelemetry SDK or exporter, and no configuration flag.

## Capabilities

### New Capabilities

- `service-metrics`: Prometheus scrape endpoint for MCP tool calls, including the metric contract, label boundedness, authentication parity, and the rule that rates are derived rather than stored.

### Modified Capabilities

None. `mcp-http-service` already requires bearer authentication and host/origin protection for the application, and `mcp-tool-safety` defines the `status` and `error_type` values this change mirrors. Neither requirement text changes: the tool-call contract, log records, and error behavior stay identical.

## Impact

- Adds the runtime dependency `prometheus-client>=0.26,<1` (no default transitive dependencies) to `pyproject.toml` and `uv.lock`.
- Changes `src/titanic_mcp/server.py`: a metrics recorder type, a `ToolCallMiddleware` constructor argument, and one custom route in `create_app`.
- Adds `tests/integration/test_metrics.py` and updates the bare `ToolCallMiddleware()` construction in `tests/security/test_mcp_tool_safety.py`.
- Documents the endpoint in `README.md` and `docs/architecture.md`, including the scrape-authorization and allowed-host requirements.
- Does not change tool behavior, tool schemas, log records, the database, profiles, or configuration surface.
- Leaves `scripts/test_container.py` untouched; that file belongs to the unimplemented `add-github-actions-ci` change.
