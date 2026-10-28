# Tasks

## 1. Dependency

- [ ] 1.1 Add `prometheus-client>=0.26,<1` to the project dependencies, run `uv sync`, and verify `uv run python -c "import prometheus_client; print(prometheus_client.__version__)"` prints a 0.26-or-newer version and `uv.lock` records the package.

## 2. Recorder

- [ ] 2.1 Add the metrics recorder type with a private `CollectorRegistry`, the `titanic_mcp_tool_calls_total` counter, the `titanic_mcp_tool_call_duration_seconds` histogram with the buckets from `design.md`, a `record()` method, and the `tool` name clamp to the three exposed names or `unknown`. Verify with `tests/domain/test_metrics.py` covering the clamp, the bucket list, and that the exported sample values match the recorded calls.
- [ ] 2.2 Pass the recorder into `ToolCallMiddleware` and record one observation per call from the existing `finally` block using the same `status` and `error_type` the log record reports. Verify with an in-process `Client` test that a successful `list_tables` call and a rejected `query_data` call each increment the counter with the expected labels, that the histogram counts both, and that `uv run pytest tests/security/test_mcp_tool_safety.py` passes after its bare `ToolCallMiddleware()` construction is updated.

## 3. Metrics endpoint

- [ ] 3.1 Register `GET /metrics` on the application as a custom route served from the recorder's registry with the Prometheus text content type, and build the recorder inside `create_app` so the route and the middleware share it. Verify with `tests/integration/test_metrics.py` that a scrape on a fresh app returns status 200 with no tool-call samples, and that a scrape after an in-process tool call contains the counter and histogram families for that tool.
- [ ] 3.2 Guard the route with the already-attached authenticated user when a bearer token is configured, returning 401 without a metrics body otherwise. Verify with `tests/integration/test_metrics.py` cases covering: no token configured serves the body, a remote-profile app without an `Authorization` header returns 401, an invalid token returns 401, and a valid token returns 200.

## 4. Host protection and documentation

- [ ] 4.1 Verify that `/metrics` is subject to the existing host/origin guard by adding container-profile cases to `tests/integration/test_metrics.py` for an allowed `Host` header and a disallowed one; confirm the disallowed request is rejected and no metrics body is returned, and that no production code change was needed for the guard.
- [ ] 4.2 Document the endpoint in `README.md`: the route, both metric families with their labels, the derived error-rate and p95 queries, the bearer-token behavior, and the requirement that a scrape `Host` be allowlisted in the container and remote profiles. Verify a local scrape's metric names and label keys match the documented text exactly.
- [ ] 4.3 Update `docs/architecture.md` with the metrics route in the HTTP configuration reference and an observability note explaining that the metric labels mirror the tool-call log record and that rates are derived, pointing at `openspec/changes/add-service-metrics/` and `service-metrics`. Verify the document names both metric families and no longer describes `/healthz` as the only operational route.

## 5. Verification

- [ ] 5.1 Run the four gates and confirm all pass: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check`.
- [ ] 5.2 Run `openspec validate add-service-metrics --strict` and confirm the change validates with every task checked and the delta spec matching the implemented behavior.

## Workflow follow-up

- Archive the change with `openspec archive add-service-metrics` after implementation, tests, and the delta-spec sync are complete.
- `scripts/test_container.py` stays untouched here; a container-side `/metrics` scrape belongs to `add-github-actions-ci`.
