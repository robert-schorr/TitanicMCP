# Tasks

## 1. Configuration and profiles

- [x] 1.1 Implement a configuration loader in `server.py` for `TITANIC_MCP_DB_PATH`, `TITANIC_MCP_HOST`, `TITANIC_MCP_PORT`, `MCP_PROFILE`, `MCP_AUTH_TOKEN`, `MCP_ALLOWED_HOSTS`, `MCP_ALLOWED_ORIGINS`, `TITANIC_MCP_LOG_LEVEL`, and `TITANIC_MCP_LOG_FORMAT`, with documented defaults
- [x] 1.2 Implement startup validation: `local` rejects a non-loopback bind, `container` requires allowed hosts, and `remote` requires a non-empty token and allowed hosts; fail before the app accepts requests with an error naming the missing setting
- [x] 1.3 Parse comma-separated host/origin allowlists, discard empty entries, and expose the result to app creation; verify `tests/integration/test_profiles.py` covers every valid and invalid combination

## 2. Streamable HTTP app and health endpoint

- [x] 2.1 Implement `http_app()` using FastMCP's Streamable HTTP transport at `/mcp`, with `stateless_http=True` for the local profile; verify an MCP client initializes, lists tools, and calls `list_tables` without a session ID
- [x] 2.2 Register `GET /healthz` with `@mcp.custom_route` returning HTTP 200 and `{"status": "ok"}` independently of MCP initialization; verify `tests/integration/test_http_app.py`
- [x] 2.3 Configure host/origin protection with `"auto"` for local and `True` for container/remote, passing the configured allowlists; verify allowed requests proceed and disallowed Host or Origin requests are rejected before MCP handling
- [x] 2.4 Verify `/healthz` remains reachable when host/origin protection and token authentication are both enabled

## 3. Authentication

- [x] 3.1 Construct `StaticTokenVerifier` only when `MCP_AUTH_TOKEN` is set and pass it to the FastMCP app; verify a valid bearer token reaches the MCP handler
- [x] 3.2 Verify missing and invalid bearer tokens return HTTP 401 without executing a tool, and that `/healthz` bypasses authentication
- [x] 3.3 Verify the token is never included in logs, startup output, client errors, or tool results

## 4. Entrypoint and operational behavior

- [x] 4.1 Switch `main()` and the `titanic-mcp` entrypoint from stdio to HTTP; verify `uv run titanic-mcp` starts and listens on `127.0.0.1:8000/mcp`
- [x] 4.2 Wire database path, bind host/port, profile, token, allowlists, and logging configuration through `main()`; verify environment overrides behave as documented
- [x] 4.3 Verify the `remote` profile starts with a token and allowlist, while missing settings fail before accepting requests
- [x] 4.4 Confirm the previous tool schemas, safe error contract, and structured tool-call records are unchanged over HTTP

## 5. Documentation and quality gates

- [x] 5.1 Update `README.md` with local HTTP startup, MCP client connection, `/healthz`, and profile/configuration tables; verify the local commands as written
- [x] 5.2 Document authentication, host/origin protection, the remote profile requirements, and the warning that bind address does not equal public exposure
- [x] 5.3 Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run ty check`; verify all pass
- [x] 5.4 Confirm the change adds no Dockerfile, Compose files, or container hardening

## Workflow follow-up

- Archive the change after implementation and review are complete.
- Sync the `mcp-http-service` delta spec into the main OpenSpec specs during archive and verify the resulting capability file.
