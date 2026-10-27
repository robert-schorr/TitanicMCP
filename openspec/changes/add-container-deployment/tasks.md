# Tasks

## 1. Container image

- [ ] 1.1 Add a multi-stage `Dockerfile` using `python:3.13-slim` and a pinned uv builder image; install from `uv.lock` with `--frozen --no-dev --no-editable`, copy only the prepared environment and application, and start `titanic-mcp`
- [ ] 1.2 Create a non-root `titanic` user (UID/GID 10001), set ownership and `PATH`, and ensure the runtime stage contains no compiler toolchain, uv cache, tests, secrets, or database file
- [ ] 1.3 Verify the image builds, starts as UID 10001, reads the database only from the mounted path, and needs no writable root filesystem

## 2. Build context

- [ ] 2.1 Add `.dockerignore` excluding `.git`, `.github`, virtual environments, caches, `tests`, `openspec`, `.env*`, `*.db`, `data/`, logs, coverage, editor settings, and OS metadata
- [ ] 2.2 Verify the build context excludes `data/titanic.db` and every secret path, and that the image contains no `.env` file or token value

## 3. Default Compose profile

- [ ] 3.1 Add `compose.yaml` with `MCP_PROFILE=container`, `TITANIC_MCP_DB_PATH=/app/data/titanic.db`, `MCP_ALLOWED_HOSTS=localhost:8000,127.0.0.1:8000`, and a read-only mount of `./data/titanic.db`
- [ ] 3.2 Set `read_only: true`, a `noexec,nosuid,size=64m` tmpfs at `/tmp`, `no-new-privileges:true`, and a `restart` policy; verify `docker compose config`
- [ ] 3.3 Publish port 8000 only on `127.0.0.1` and define a Python stdlib healthcheck against `/healthz` with a start period; verify the container reports healthy and `GET /healthz` returns 200 from the host
- [ ] 3.4 Verify an MCP client can call `list_tables` and `query_data` through the published port and that the source database hash is unchanged

## 4. Remote Compose override

- [ ] 4.1 Add `compose.remote.yaml` setting `MCP_PROFILE=remote`, publishing `8000:8000`, and requiring `MCP_AUTH_TOKEN` and `MCP_ALLOWED_HOSTS` through Compose interpolation
- [ ] 4.2 Support optional `MCP_ALLOWED_ORIGINS` without embedding a token or origin default in the file; verify the overlay inherits the hardened runtime settings from the default profile
- [ ] 4.3 Verify the overlay fails before serving when the token or host allowlist is missing, starts with both, returns 401 without a token, and executes tools with a valid token

## 5. Documentation and verification

- [ ] 5.1 Update `README.md` with image build, default Compose run, remote overlay run, healthcheck, and troubleshooting commands; verify each documented command
- [ ] 5.2 Add a prominent warning that the default profile publishes only to loopback and that external publication requires the remote profile, a token, and explicit allowed hosts
- [ ] 5.3 Verify `docker compose down` removes the container, no writable database volume exists, and `data/titanic.db` remains byte-identical
- [ ] 5.4 Confirm the change modifies no query semantics, tool schemas, HTTP profile behavior, or Python application code

## Workflow follow-up

- Archive the change after implementation and review are complete.
- Sync the `container-deployment` delta spec into the main OpenSpec specs during archive and verify the resulting capability file.
