# Proposal

## Why

The MCP tools currently run over stdio and are not reachable by remote or browser-based MCP clients. This change adds the Streamable HTTP service, operational health endpoint, local/container/remote profiles, and the authentication and host/origin controls needed to expose the tools safely.

## What Changes

- Serve MCP over Streamable HTTP at `/mcp`.
- Make the default local profile bind `127.0.0.1:8000`, use stateless requests, require no auth, and enable host/origin protection.
- Add `GET /healthz` returning `{"status": "ok"}` without MCP initialization or authentication.
- Add explicit `local`, `container`, and `remote` profiles with startup validation.
- Add optional bearer-token authentication via `StaticTokenVerifier`; the `remote` profile requires a token.
- Add host/origin allowlists and reject unlisted requests before MCP handling.
- Switch the `titanic-mcp` entrypoint from stdio to HTTP.
- Add HTTP integration tests and update `README.md` with client, profile, and security instructions.

This change does **not** add the Dockerfile, Compose profiles, or container hardening. Those are delivered by `add-container-deployment`.

## Capabilities

### New Capabilities

- `mcp-http-service`: Streamable HTTP serving, health checks, local/container/remote profiles, bearer-token authentication, and host/origin protection.

### Modified Capabilities

None.

## Impact

- **Code:** Extend `server.py` with configuration loading, HTTP app creation, health routing, auth, and the HTTP entrypoint; add HTTP integration tests.
- **Runtime:** The default `titanic-mcp` command now serves Streamable HTTP on `127.0.0.1:8000/mcp`.
- **Dependencies:** No new runtime dependency is expected beyond FastMCP's server stack; HTTP test support is already present from the previous change.
- **Data:** No schema changes or writes to `data/titanic.db`.
- **Depends on:** `add-mcp-query-tools`.
- **Unblocks:** `add-container-deployment`.
