# Spec Delta

## Purpose

Define a strict, non-leaky MCP tool contract with predictable client errors and structured observability for every tool call.

## ADDED Requirements

### Requirement: Strict input validation

Tool inputs SHALL be validated strictly. Unexpected fields, type mismatches, unknown tables, unknown columns, unknown operators, and out-of-range pagination values MUST be rejected before any data access.

#### Scenario: Unexpected field rejected

- **WHEN** a tool call includes an unsupported field named `foo`
- **THEN** the request is rejected with `Invalid arguments: foo`

#### Scenario: Type mismatch rejected

- **WHEN** `query_data` receives the string `"10"` for `limit`
- **THEN** the request is rejected with `Invalid arguments: limit`

#### Scenario: Unknown table rejected

- **WHEN** `query_data` receives a table name that is not in the catalog
- **THEN** the request is rejected with `Invalid arguments: table`

#### Scenario: Unknown filter operator rejected

- **WHEN** `query_data` receives a filter operator that is not supported
- **THEN** the request is rejected with `Invalid arguments: filter[0].op`

#### Scenario: Pagination bounds enforced

- **WHEN** `query_data` receives `limit` 0 or 501, or a negative `offset`
- **THEN** the request is rejected with the corresponding field path

### Requirement: Safe argument error format

Validation failures SHALL return a tool error whose message is exactly `Invalid arguments: ` followed by sorted, de-duplicated field paths. The message MUST NOT contain Pydantic text, SQL, parameter values, stack traces, or implementation paths.

#### Scenario: Multiple field paths

- **WHEN** a request fails validation for `filter[0].op` and `limit`
- **THEN** the client receives exactly `Invalid arguments: filter[0].op, limit`

#### Scenario: Root-level validation failure

- **WHEN** a validation failure has no specific field location
- **THEN** the client receives exactly `Invalid arguments: request`

#### Scenario: No internal detail leaks

- **WHEN** a validation failure includes a Pydantic message, a SQL fragment, or an input value
- **THEN** the client response contains none of those details

### Requirement: Safe domain and internal errors

Only errors explicitly classified as client-safe SHALL be exposed to clients. All other exceptions SHALL return the message `Internal error.`

#### Scenario: Unexpected exception is masked

- **WHEN** a tool encounters an unexpected database or runtime exception
- **THEN** the client receives `Internal error.` with an error result

#### Scenario: Classified safe error passes through

- **WHEN** a tool raises an error explicitly classified as client-safe
- **THEN** its safe message is returned unchanged

### Requirement: Internal diagnostics

The server SHALL log full internal validation and exception detail, including Pydantic error types and locations and exception tracebacks, while excluding that detail from client responses.

#### Scenario: Validation detail is logged

- **WHEN** a tool call fails validation
- **THEN** the server log records the error types and field locations
- **AND** the client response contains only the safe argument message

#### Scenario: Unexpected exception is logged

- **WHEN** a tool call raises an unexpected exception
- **THEN** the server log records the exception type and traceback
- **AND** the client response contains only `Internal error.`

### Requirement: Structured tool-call logs

Every tool call SHALL emit exactly one JSON log record with `event` set to `tool_call`, `tool_name`, `duration_ms`, `status`, and `error_type`. `status` SHALL be one of `ok`, `invalid_arguments`, `safe_error`, or `internal_error`; `error_type` SHALL be one of `none`, `validation_error`, `domain_validation`, `safe_tool_error`, or `unexpected_exception`.

#### Scenario: Successful call log

- **WHEN** a tool call succeeds
- **THEN** exactly one `tool_call` record is emitted with status `ok`, error type `none`, and a non-negative duration

#### Scenario: Validation failure log

- **WHEN** a tool call fails validation
- **THEN** exactly one `tool_call` record is emitted with status `invalid_arguments`, error type `validation_error`, and the affected field paths

#### Scenario: Internal failure log

- **WHEN** a tool call raises an unexpected exception
- **THEN** exactly one `tool_call` record is emitted with status `internal_error` and error type `unexpected_exception`

### Requirement: Request correlation

Each tool-call record SHALL include `request_id` from the MCP request, or a generated identifier when no request ID is available. It SHALL include `correlation_id` from an `x-request-id` or `x-correlation-id` header when present.

#### Scenario: MCP request identifier

- **WHEN** a tool is called through an MCP session
- **THEN** the record contains the MCP request ID as `request_id`

#### Scenario: HTTP correlation header

- **WHEN** a tool is called over HTTP with an `x-request-id` header
- **THEN** the record contains that value as `correlation_id`

#### Scenario: Missing correlation header

- **WHEN** no correlation header is present
- **THEN** `correlation_id` is null and `request_id` remains non-null

### Requirement: Log privacy

Tool-call logs MUST NOT contain filter values, SQL text, SQL parameters, request bodies, authentication tokens, or raw tool arguments.

#### Scenario: Sensitive values are excluded

- **WHEN** a query includes a filter value or an HTTP request includes an authentication token
- **THEN** the serialized tool-call log contains neither the filter value nor the token
- **AND** it may contain the table name, filter count, and field paths
