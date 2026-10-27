# Design

## Context

See `proposal.md` for motivation. The MCP tools and tool-safety middleware already exist and are tested over an in-process client and a minimal ASGI seam. This change turns that app into the production HTTP service and adds operational configuration. Container packaging is separate so the application behavior can be reviewed and tested without a Docker dependency.

## Goals / Non-Goals

**Goals:**

- Serve Streamable HTTP at `/mcp`.
- Safe loopback defaults with stateless request handling.
- `/healthz` for probes.
- Explicit `local`, `container`, and `remote` profiles with startup validation.
- Optional bearer-token auth and host/origin protection.
- HTTP integration tests and operational documentation.

**Non-Goals:**

- Dockerfile, Compose files, or container hardening.
- OAuth/OIDC, user accounts, or per-user authorization.
- TLS termination, reverse-proxy configuration, or cloud deployment.
- Changes to query semantics, tool schemas, or the logging contract.

## Decisions

### 1. Transport and entrypoint

Use FastMCP's Streamable HTTP transport:

- `mcp.run(transport="http", ...)` in `main()`
- `mcp.http_app(...)` for ASGI tests
- endpoint path `/mcp`
- `stateless_http=True` for the default local profile

The `titanic-mcp` entrypoint switches from stdio to HTTP. The default is still local and unauthenticated.

### 2. Configuration

`server.py` gains a small configuration loader with these environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `TITANIC_MCP_DB_PATH` | `data/titanic.db` | Read-only SQLite file |
| `TITANIC_MCP_HOST` | `127.0.0.1` | Bind host |
| `TITANIC_MCP_PORT` | `8000` | Bind port |
| `MCP_PROFILE` | `local` | `local`, `container`, or `remote` |
| `MCP_AUTH_TOKEN` | unset | Optional bearer token; required for `remote` |
| `MCP_ALLOWED_HOSTS` | loopback for local | Comma-separated Host allowlist |
| `MCP_ALLOWED_ORIGINS` | unset | Comma-separated Origin allowlist |
| `TITANIC_MCP_LOG_LEVEL` | `INFO` | Log level |
| `TITANIC_MCP_LOG_FORMAT` | `json` | `json` or `text` |

Startup validation rejects contradictory combinations:

- `local` with a non-loopback bind
- `container` without allowed hosts
- `remote` without a token or allowed hosts

### 3. Profiles

- **Local:** bind loopback, no auth, `stateless_http=True`, host/origin protection `"auto"`, loopback Host allowlist.
- **Container:** bind `0.0.0.0`, no auth by default, host/origin protection `True`, explicit `MCP_ALLOWED_HOSTS`. The deployment layer is responsible for publishing only to loopback; the later container change pins that mapping.
- **Remote:** bind `0.0.0.0`, require `MCP_AUTH_TOKEN` and `MCP_ALLOWED_HOSTS`, host/origin protection `True`.

`MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS` are parsed from comma-separated strings into the lists FastMCP expects. Empty entries are discarded.

### 4. Health endpoint

`GET /healthz` is registered with `@mcp.custom_route("/healthz", methods=["GET"])` and returns:

```json
{"status": "ok"}
```

FastMCP custom routes are intentionally outside MCP authentication, so container and load-balancer probes work without a token.

### 5. Authentication

When `MCP_AUTH_TOKEN` is set, construct `StaticTokenVerifier` with a single token and pass it to the `FastMCP` constructor. MCP requests must send `Authorization: Bearer <token>`; missing or invalid tokens receive HTTP 401. The token is read from the environment, never logged, and never embedded in source or images.

### 6. Host and origin protection

The app is created with:

- `host_origin_protection="auto"` for local
- `host_origin_protection=True` for container and remote
- `allowed_hosts` from the profile configuration
- `allowed_origins` when configured

This guards against DNS rebinding and rejects unlisted browser origins before MCP handling. Health checks remain reachable.

### 7. Tests

- `tests/integration/test_profiles.py`: local/container/remote validation, missing token, missing hosts, non-loopback local bind.
- `tests/integration/test_http_app.py`: `/mcp` initialization and tool calls, `/healthz`, stateless requests, and allowed/disallowed Host/Origin.
- Auth tests: 401 for missing/invalid token, success for the configured token, and `/healthz` bypass.
- A local server smoke test using the documented `uv run titanic-mcp` command.

## Risks / Trade-offs

- **Bind address is not the same as public exposure** → the explicit `container` profile allows `0.0.0.0` while the deployment layer pins loopback publication; `remote` requires auth.
- **Host/origin protection is not CORS** → browser clients that need CORS still require separate configuration; this is documented.
- **Static token auth is limited** → suitable for a private read-only service; OAuth is out of scope.
- **Stateless mode has no server-initiated session features** → acceptable for bounded queries.
- **Reverse-proxy TLS is deployment-specific** → documented as an operational concern, not automated.

## Migration Plan

1. Add configuration and HTTP app creation to `server.py`.
2. Add `/healthz`, auth, and host/origin settings.
3. Switch `main()` and the `titanic-mcp` entrypoint from stdio to HTTP.
4. Add HTTP integration tests.
5. Update README with local HTTP usage and profile/security instructions.

Rollback is a source revert; the tool layer and database remain unchanged.

## Open Questions

None.
