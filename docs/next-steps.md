# Next steps

The service is functionally complete for its current scope: a private, read-only
MCP endpoint over the Titanic database. The items below are deliberately deferred.
They do not block local or private use, but CI and the security work are needed
before treating an internet-facing deployment as production-grade.

| Priority | Item | Why it matters |
|---|---|---|
| High | CI pipeline and pre-commit hooks | The four quality gates run only by hand |
| Medium | Metrics endpoint | No scrapeable latency or error-rate data |
| High when exposed | Security hardening | Static bearer auth is not production-grade |

## 1. CI pipeline and pre-commit hooks

The repository has no `.github/workflows`. All four gates currently depend on a
developer remembering to run them. The proposed
[`add-github-actions-ci`](../openspec/changes/add-github-actions-ci/proposal.md)
change covers the pipeline.

### Pipeline

1. Add `.github/workflows/ci.yml`, triggered by pull requests and pushes to `main`.
2. Run four jobs on `ubuntu-latest`:
   - `quality`: `ruff check`, `ruff format --check`, `ty check`.
   - `test (unit)`: `pytest tests/domain tests/security`.
   - `test (integration)`: `pytest tests/integration`.
   - `container`: `uv run --no-sync python scripts/container_smoke_test.py`.
3. Install with `uv sync --locked`, then run commands with `uv run --no-sync` so a
   stale lockfile fails instead of being silently refreshed.
4. Set `permissions: contents: read`, a concurrency group with
   `cancel-in-progress: true`, and a job timeout. Add `DOCKER_BUILDKIT=1` for the
   container job.
5. Configure branch protection to require all four checks after the first green run.

### Pre-commit hooks

Keep hooks fast; leave the test suite to CI.

1. Add `pre-commit` as a development dependency and a `.pre-commit-config.yaml`.
2. Use `ruff-pre-commit` for `ruff check --fix` and `ruff format`.
3. Add a local hook for `uv run ty check`.
4. Add the standard whitespace, end-of-file, and YAML checks.
5. Run `uv run pre-commit install` once per checkout and document it in the README.

**Done when:** a pull request cannot merge with a failing gate, and a clean
checkout can install and pass the hooks without manual setup beyond
`pre-commit install`.

## 2. Metrics endpoint

`ToolCallMiddleware` already times every call and classifies its outcome, but the
only sink is stderr. The proposed
[`add-service-metrics`](../openspec/changes/add-service-metrics/proposal.md) change
covers the endpoint.

1. Add `prometheus-client` and expose `GET /metrics` through
   `FastMCP.custom_route`, using a private `CollectorRegistry` per application.
2. Record in the existing middleware `finally` block:
   - `titanic_mcp_tool_calls_total{tool,status,error_type}`
   - `titanic_mcp_tool_call_duration_seconds{tool}`
3. Clamp the client-supplied tool name to the three exposed names plus `unknown`;
   never use it as an unbounded label.
4. Require the same bearer token as `/mcp` when `MCP_AUTH_TOKEN` is set. Leave
   `/metrics` open when no token is configured, matching `/healthz`.
5. Keep host/origin protection unchanged. Document that a scrape must send an
   allowlisted `Host` header.
6. Derive error rate and latency quantiles in PromQL; do not store rates or
   quantiles in the process. Exclude `tool="unknown"` from health alerts.

**Done when:** a scrape works without an MCP session, the label set is bounded,
no request identifiers or filter values appear in metrics, and the integration
tests cover auth parity and host rejection.

## 3. Security hardening

`StaticTokenVerifier` is a single shared bearer token. It is acceptable for a
private read-only service behind a trusted network, but FastMCP documents it as
unsuitable for general production use.

### Authentication

1. Replace `StaticTokenVerifier` with an OAuth 2.1 resource-server/provider that
   validates JWT access tokens against an OIDC issuer's JWKS. Check signature,
   issuer, audience, and expiry; require scopes if clients need differentiation.
2. Alternatively terminate authentication at a trusted reverse proxy and pass a
   verified identity to the service. Do not keep a static shared token for
   internet-facing use.
3. Store secrets in a secret manager, use at least 32 random bytes, and document
   rotation. Never log the token or an Authorization header.

### Transport and abuse limits

1. Terminate TLS at a reverse proxy; redirect HTTP, enable HSTS, and consider mTLS
   for service-to-service callers.
2. Add rate limiting per token or client IP at the proxy or application layer.
3. Cap request body size and string lengths. Table and column names currently have
   no maximum length, and `x-request-id` / `x-correlation-id` are logged without a
   cap; bound both before they reach validation or logs.
4. Add CORS only if a browser client needs it. Host/origin protection is not CORS.

### Supply chain

1. Run `pip-audit` in CI and scan the image with Trivy or an equivalent.
2. Enable Dependabot or Renovate for Python dependencies, base images, and GitHub
   Actions.
3. Pin GitHub Actions by commit SHA once the pipeline is stable.

**Done when:** missing, expired, or wrong-audience credentials are rejected; rate
and size limits are enforced; dependency and image scans run in CI; and no token
appears in logs or error responses.

## Related small follow-ups

- Route Uvicorn's startup and access logs through the JSON formatter. Today stderr
  mixes JSON application records with plain-text Uvicorn lines.
- Add a load test now that all profiles are stateless. Multiple replicas should
  work behind a round-robin load balancer without sticky sessions.
- Revisit the OpenSpec proposals above, implement them as active changes, and
  archive them after their delta specs are synced.
