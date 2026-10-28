# Proposal

## Why

The HTTP service works directly from `uv`, but operators also need an optional hardened container deployment. Packaging is separable from the application behavior and can be reviewed, built, and rolled back on its own.

## What Changes

- Add a Python 3.13 container image built with `uv`, running as a non-root user.
- Add a default Compose profile that publishes only to `127.0.0.1:8000`, uses a read-only root filesystem, mounts `data/titanic.db` read-only, sets `no-new-privileges`, provides `/tmp` as tmpfs, and defines a `/healthz` healthcheck.
- Add a remote Compose override using `MCP_PROFILE=remote`, external publication, `MCP_AUTH_TOKEN`, and explicit allowed hosts.
- Add `.dockerignore` to keep caches, tests, secrets, and local artifacts out of the image.
- Document local and remote container usage, including the loopback-publication warning and the requirement to switch to the remote profile before exposing the service.

This change does **not** change query semantics, tool schemas, or HTTP profile behavior. It packages the service delivered by `add-mcp-http-service`.

## Capabilities

### New Capabilities

- `container-deployment`: Hardened container packaging, Compose profiles, healthcheck integration, and remote-publication safeguards.

### Modified Capabilities

None.

## Impact

- **Artifacts:** Add `Dockerfile`, `.dockerignore`, a default Compose file, and a remote Compose override.
- **Runtime:** The container binds `0.0.0.0` internally but is published only to loopback by default.
- **Security:** Non-root execution, read-only root and database mounts, `no-new-privileges`, a healthcheck, and no embedded secrets.
- **Data:** The database is mounted read-only; no schema changes or migrations.
- **Documentation:** Add container build, local run, remote run, and troubleshooting instructions to `README.md`.
- **Depends on:** `add-mcp-http-service`.
- **Unblocks:** Nothing.
