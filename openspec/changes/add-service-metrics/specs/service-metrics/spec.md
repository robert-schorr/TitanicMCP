# Spec Delta

## Purpose

Expose scrapeable Prometheus metrics for MCP tool calls so operators can measure call volume, tail latency, and error rate without parsing application logs.

## ADDED Requirements

### Requirement: Metrics endpoint

The service SHALL expose `GET /metrics` in the Prometheus text exposition format. The endpoint MUST NOT require MCP initialization, a session, or a preceding tool call.

#### Scenario: Scrape without an MCP session

- **WHEN** a client sends `GET /metrics` without initializing an MCP session
- **THEN** the response has status 200 and a Prometheus text exposition body

#### Scenario: Scrape before any tool call

- **WHEN** a client scrapes `/metrics` on a freshly created application
- **THEN** the response has status 200 and contains no tool-call samples

### Requirement: Tool-call counter

Each tool call SHALL increment `titanic_mcp_tool_calls_total` with labels `tool`, `status`, and `error_type`, using the same classification the structured tool-call log record reports for that call.

#### Scenario: Successful call counted

- **WHEN** a client calls `list_tables` and it succeeds
- **THEN** the counter increases by one with `tool="list_tables"`, `status="ok"`, and `error_type="none"`

#### Scenario: Rejected call counted

- **WHEN** a client calls `query_data` with a table that is not in the catalog
- **THEN** the counter increases by one with `status="invalid_arguments"` and `error_type="domain_validation"`

### Requirement: Tool-call duration histogram

Each tool call SHALL observe its duration in `titanic_mcp_tool_call_duration_seconds` with the label `tool`, in seconds, including calls that fail.

#### Scenario: Duration recorded once per call

- **WHEN** a client calls `describe_table` once
- **THEN** the sample count for `tool="describe_table"` increases by one and the observed sum is at least zero

#### Scenario: Failed call still records duration

- **WHEN** a tool call fails validation
- **THEN** the sample count for that tool still increases by one

### Requirement: Bounded metric labels

Metric labels SHALL be bounded and free of sensitive data. The `tool` label MUST be one of the tool names the service exposes or `unknown`, and MUST NOT carry a client-supplied string. Labels MUST NOT include request identifiers, correlation identifiers, filter values, SQL text, field values, or credentials.

#### Scenario: Unknown tool name clamped

- **WHEN** a client calls a tool name the service does not expose
- **THEN** the call is recorded with `tool="unknown"`

#### Scenario: Repeated unknown names do not grow the label set

- **WHEN** a client calls several distinct unrecognized tool names
- **THEN** every such call is recorded under `tool="unknown"` and no new `tool` label value appears

### Requirement: Metrics authentication parity

When the service is configured with an MCP bearer token, `/metrics` SHALL require a valid bearer token and MUST reject a missing or invalid token with status 401. When no token is configured, `/metrics` SHALL be reachable without authentication, consistent with the health endpoint.

#### Scenario: Token configured and missing

- **WHEN** the service runs with a bearer token configured and a client scrapes `/metrics` without an `Authorization` header
- **THEN** the response has status 401 and no metric samples

#### Scenario: Token configured and valid

- **WHEN** the service runs with a bearer token configured and a client scrapes `/metrics` with that token as a bearer credential
- **THEN** the response has status 200 and the exposition body

#### Scenario: No token configured

- **WHEN** the service runs without a bearer token and a client scrapes `/metrics`
- **THEN** the response has status 200

### Requirement: Metrics host protection

`/metrics` SHALL be subject to the same host and origin protection as the rest of the application and MUST NOT be exempted from it.

#### Scenario: Disallowed host rejected

- **WHEN** a client scrapes `/metrics` with a `Host` header the active profile does not allow
- **THEN** the request is rejected before any metrics body is returned

#### Scenario: Allowed host served

- **WHEN** a client scrapes `/metrics` with an allowed `Host` header
- **THEN** the request is served

### Requirement: Derived rates

The service SHALL expose counts and duration observations only. It MUST NOT expose a stored error-rate, success-rate, or latency-quantile value computed over a process-local window.

#### Scenario: No stored rate exposed

- **WHEN** a client scrapes `/metrics` after both successful and failing tool calls
- **THEN** the exposition contains no error-rate, success-rate, or quantile metric family
