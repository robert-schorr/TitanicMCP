# Design

## Context

See `proposal.md` for motivation. The HTTP service from `add-mcp-http-service` runs from `uv` and already supports `local`, `container`, and `remote` profiles, a `/healthz` endpoint, bearer authentication, and host/origin protection. This change packages that service without changing application behavior. The database is a single read-only SQLite file, so the container needs no writable volume.

## Goals / Non-Goals

**Goals:**

- A reproducible, non-root image built with `uv`.
- A default Compose profile that is safe for local use and publishes only to loopback.
- A hardened runtime: read-only root filesystem, read-only database mount, `tmpfs` for `/tmp`, and `no-new-privileges`.
- An explicit remote override that requires authentication and an allowed-host list.
- A healthcheck that reflects actual HTTP readiness.
- Container documentation with a clear exposure warning.

**Non-Goals:**

- Application, query, tool, or HTTP profile changes.
- Kubernetes manifests, cloud infrastructure, or a reverse proxy.
- TLS termination or certificate management.
- Multi-architecture publishing or registry automation.
- A writable database volume, migrations, or backups.

## Decisions

### 1. Image build

Use a multi-stage build:

```text
Stage 1 (builder): python:3.13-slim + pinned uv image
  - copy pyproject.toml and uv.lock
  - uv sync --frozen --no-dev --no-editable
  - copy src/ and build/install the project into .venv

Stage 2 (runtime): python:3.13-slim
  - copy the prepared .venv and application source from the builder
  - create a non-root user `titanic` (UID/GID 10001)
  - set PATH to the virtual environment
  - run `titanic-mcp` as `titanic`
```

Dependencies are installed from the lockfile with `--frozen` so the image matches local development. The runtime stage contains no compiler toolchain, `uv` cache, tests, or build context. The image tag is pinned to Python 3.13 and the uv builder image is pinned to a specific version rather than `latest`.

The base image is `python:3.13-slim`; no `curl` is added. Healthchecks use the Python standard library.

### 2. Runtime layout and mounts

```text
/app/.venv            application environment (read-only at runtime)
/app/src/titanic_mcp  source (read-only at runtime)
/app/data/titanic.db  mounted read-only from the host
```

`TITANIC_MCP_DB_PATH=/app/data/titanic.db` points at the mount. `data/` is excluded from the build context so the image never contains a stale database copy and always uses the mounted file. The application only needs to read this path; `/tmp` is provided as `tmpfs` for any library scratch use.

### 3. Default Compose profile

A single `compose.yaml` defines the default profile:

| Setting | Value |
|---|---|
| `MCP_PROFILE` | `container` |
| Internal bind | `0.0.0.0:8000` |
| Published port | `127.0.0.1:8000:8000` |
| `MCP_ALLOWED_HOSTS` | `localhost:8000,127.0.0.1:8000` |
| `TITANIC_MCP_DB_PATH` | `/app/data/titanic.db` |
| Database mount | `./data/titanic.db:/app/data/titanic.db:ro` |
| Root filesystem | `read_only: true` |
| `/tmp` | `tmpfs` with `noexec,nosuid,size=64m` |
| Privileges | `security_opt: [no-new-privileges:true]` |
| Restart policy | `unless-stopped` |
| Healthcheck | `GET http://127.0.0.1:8000/healthz` |

The container binds `0.0.0.0` because the `container` profile requires it, but the host mapping restricts reachability to loopback. The profile permits token omission only because of that publication rule; the README states that changing the mapping requires switching to the remote profile.

No `MCP_AUTH_TOKEN` is set by default. Compose reads overrides from the operator environment, not from a committed `.env` file.

### 4. Healthcheck

The Compose healthcheck uses Python, which is already in the image:

```text
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
```

Settings: interval 5s, timeout 3s, retries 5, start period 5s. The service is healthy only after `/healthz` returns 200, which happens once the HTTP app is accepting requests. `/healthz` bypasses MCP authentication, so the probe needs no token.

### 5. Remote override

`compose.remote.yaml` is an overlay applied with `docker compose -f compose.yaml -f compose.remote.yaml up`:

| Setting | Value |
|---|---|
| `MCP_PROFILE` | `remote` |
| Published port | `8000:8000` (all interfaces) |
| `MCP_AUTH_TOKEN` | `${MCP_AUTH_TOKEN:?MCP_AUTH_TOKEN is required}` |
| `MCP_ALLOWED_HOSTS` | `${MCP_ALLOWED_HOSTS:?MCP_ALLOWED_HOSTS is required}` |
| `MCP_ALLOWED_ORIGINS` | `${MCP_ALLOWED_ORIGINS:-}` |

Compose interpolation fails before the container starts when the token or host allowlist is missing. The application also validates the `remote` profile, so a direct `docker run` without the token fails closed. All hardened runtime settings from the default file are inherited; the override only changes profile, publication, and environment.

The token is supplied at runtime and never baked into the image or committed. Operators are responsible for TLS termination and for choosing an allowed origin that matches their client.

### 6. Build-context exclusions

`.dockerignore` excludes:

- `.git`, `.github`, `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.ty_cache`
- `tests`, `openspec`, `.env*`, `*.db`, `data/`
- local logs, coverage output, editor settings, and OS metadata

This keeps the context small, prevents secrets or a stale database from entering the image, and ensures tests and planning artifacts are not shipped.

### 7. Tests and verification

No new Python tests are needed; application behavior is already covered by the previous change. Verification is operational:

- `docker compose config` renders the expected profile, mounts, publication, and security settings.
- The image builds, runs as UID 10001, and becomes healthy.
- `GET http://127.0.0.1:8000/healthz` returns 200 from the host.
- An MCP client can call `list_tables` through the published port.
- The source `data/titanic.db` hash is unchanged after container queries.
- The remote overlay fails to start without `MCP_AUTH_TOKEN` and without `MCP_ALLOWED_HOSTS`, then starts with both.
- The image contains no `.env` file or token value.
- `docker compose down` removes the container; no writable database volume exists.

## Risks / Trade-offs

- **The container profile permits token omission** → safe only because publication is loopback; the remote overlay is mandatory for external exposure and enforced by Compose interpolation and application validation.
- **Read-only root filesystem** → any future feature that needs persistent local writes must add an explicit writable mount; the current read-only service does not.
- **Database is not in the image** → the Compose deployment must mount `data/titanic.db`; a missing file makes queries fail rather than silently serving stale data.
- **Python-based healthcheck** → avoids adding `curl` to the runtime image at the cost of a slightly slower probe.
- **Single-architecture build** → acceptable for local and small deployments; multi-arch publishing is out of scope.
- **Static token in the environment** → visible to the container runtime and operators; suitable for a private read-only service, not a multi-tenant one.

## Migration Plan

1. Add `Dockerfile` and `.dockerignore`.
2. Add `compose.yaml` and `compose.remote.yaml`.
3. Build and run the default profile; verify health, loopback-only publication, and tool calls.
4. Run the remote overlay with a test token and allowlist; verify 401 without a token and success with one.
5. Update README with build, local run, remote run, and troubleshooting instructions.

Rollback is removing the container artifacts; the application and database remain unchanged.

## Open Questions

None.
