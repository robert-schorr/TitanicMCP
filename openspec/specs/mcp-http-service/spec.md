# mcp-http-service Specification

## Purpose

Serve the MCP tools over Streamable HTTP with safe local defaults, an operational health endpoint, and explicit local, container, and remote profiles.

## Requirements

### Requirement: Streamable HTTP endpoint

The server SHALL expose MCP over Streamable HTTP at `/mcp` and SHALL support initialization, tool listing, and tool calls over that endpoint.

#### Scenario: HTTP client can query the catalog

- **WHEN** an MCP client initializes against the HTTP endpoint and calls `list_tables`
- **THEN** the call succeeds and returns the nine catalog entries

#### Scenario: Tool schemas are advertised

- **WHEN** an MCP client lists tools over HTTP
- **THEN** `list_tables`, `describe_table`, and `query_data` are present with input schemas

### Requirement: Local stateless default

The default runtime profile SHALL bind `127.0.0.1:8000`, require no authentication, operate without server-side session affinity, and enable host/origin protection for loopback-bound serving.

#### Scenario: Default startup

- **WHEN** the server starts without deployment overrides
- **THEN** it listens on `127.0.0.1:8000`
- **AND** MCP tool calls succeed without an authentication token

#### Scenario: No session affinity required

- **WHEN** successive MCP requests do not carry an `Mcp-Session-Id` header
- **THEN** the server still handles them independently

#### Scenario: Untrusted host rejected locally

- **WHEN** a request reaches the default local profile with a Host header that is not a loopback host
- **THEN** the request is rejected before MCP handling

### Requirement: Health check

`GET /healthz` SHALL return HTTP 200 and JSON `{"status": "ok"}` whenever the server is accepting requests. It SHALL NOT require MCP initialization or authentication.

#### Scenario: Health endpoint responds

- **WHEN** `GET /healthz` is requested
- **THEN** the response status is 200
- **AND** the JSON body is `{"status": "ok"}`

#### Scenario: Health check bypasses MCP auth

- **WHEN** token authentication is enabled and `GET /healthz` is requested without an Authorization header
- **THEN** the health check still returns 200

### Requirement: Container profile

The `container` profile SHALL allow a `0.0.0.0` bind inside a container, require an explicit allowed-host list, enable host/origin protection, and permit token omission because the provided container deployment publishes only to loopback.

#### Scenario: Container profile starts without a token

- **WHEN** `MCP_PROFILE` is `container`, the bind host is `0.0.0.0`, and an allowed-host list is provided
- **THEN** the server starts without requiring `MCP_AUTH_TOKEN`

#### Scenario: Container profile requires allowed hosts

- **WHEN** `MCP_PROFILE` is `container` without an allowed-host list
- **THEN** startup fails before accepting requests
- **AND** the error identifies the missing host configuration

#### Scenario: Local profile rejects a non-loopback bind

- **WHEN** `MCP_PROFILE` is `local` and the bind host is not a loopback address
- **THEN** startup fails before accepting requests

### Requirement: Remote exposure profile

The `remote` profile SHALL require a non-empty `MCP_AUTH_TOKEN` and an explicit allowed-host list. Startup SHALL fail with a clear error if either is missing.

#### Scenario: Missing remote token

- **WHEN** `MCP_PROFILE` is `remote` without `MCP_AUTH_TOKEN`
- **THEN** startup fails before accepting requests
- **AND** the error identifies the missing token configuration

#### Scenario: Missing remote host allowlist

- **WHEN** `MCP_PROFILE` is `remote` with a token but without an allowed-host list
- **THEN** startup fails before accepting requests
- **AND** the error identifies the missing host configuration

#### Scenario: Remote profile starts with required settings

- **WHEN** `MCP_PROFILE` is `remote`, a non-empty token is configured, and an allowed-host list is configured
- **THEN** the server starts successfully

### Requirement: Bearer token authentication

When a token is configured, MCP requests SHALL require `Authorization: Bearer <token>`. Missing or invalid tokens SHALL be rejected with HTTP 401 and SHALL NOT reach tool execution.

#### Scenario: Valid bearer token accepted

- **WHEN** an MCP request includes the configured bearer token
- **THEN** the request reaches the MCP handler and can call a tool

#### Scenario: Missing token rejected

- **WHEN** an MCP request omits the Authorization header while token auth is enabled
- **THEN** the response status is 401
- **AND** no tool executes

#### Scenario: Invalid token rejected

- **WHEN** an MCP request includes a token that does not match the configured token
- **THEN** the response status is 401
- **AND** no tool executes

### Requirement: Host and origin protection

When host/origin protection is enabled, requests with a Host or Origin that is not in the configured allowlists SHALL be rejected before MCP handling. The health endpoint SHALL remain available.

#### Scenario: Allowed host and origin

- **WHEN** a request carries an allowed Host and Origin
- **THEN** it proceeds to MCP handling

#### Scenario: Disallowed host rejected

- **WHEN** a request carries a Host that is not in the allowlist
- **THEN** the request is rejected before MCP handling

#### Scenario: Disallowed origin rejected

- **WHEN** a browser request carries an Origin that is not in the allowlist
- **THEN** the request is rejected before MCP handling

#### Scenario: Health check remains reachable

- **WHEN** host/origin protection is enabled
- **THEN** `GET /healthz` still returns 200 for the container or load balancer probe
