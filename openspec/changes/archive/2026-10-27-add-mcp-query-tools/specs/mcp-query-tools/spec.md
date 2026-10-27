# Spec Delta

## Purpose

Expose the Titanic query core as MCP tools with stable names, descriptions, and input schemas so clients can discover and call the read-only data surface.

## ADDED Requirements

### Requirement: Tool exposure

The server SHALL advertise exactly three tools: `list_tables`, `describe_table`, and `query_data`. Each tool SHALL include a description and an input schema.

#### Scenario: Tools are listed

- **WHEN** an MCP client lists tools
- **THEN** the response contains `list_tables`, `describe_table`, and `query_data`
- **AND** each tool has a non-empty description

#### Scenario: Query schema is advertised

- **WHEN** an MCP client inspects `query_data`
- **THEN** the input schema includes `table`, optional `columns`, optional `filter`, optional `order_by`, `limit`, and `offset`
- **AND** the schema marks `table` as required

### Requirement: Catalog tool delegation

`list_tables` SHALL accept no arguments and SHALL return the query core's nine-entry catalog unchanged.

#### Scenario: Catalog tool call

- **WHEN** an MCP client calls `list_tables`
- **THEN** the result contains the `passengers` view and the eight raw tables
- **AND** the row counts and `recommended` values match the core catalog

### Requirement: Description tool delegation

`describe_table` SHALL accept a table name and SHALL return the query core's table metadata unchanged.

#### Scenario: Passengers description call

- **WHEN** an MCP client calls `describe_table` with `passengers`
- **THEN** the result contains the 16 passenger columns, their types and nullability, and `default_order_by` set to `passenger_id`

### Requirement: Query tool delegation

`query_data` SHALL accept a typed query request and SHALL return the query core's response envelope unchanged.

#### Scenario: Query tool call

- **WHEN** an MCP client calls `query_data` with `table` set to `passengers`, `columns` set to `["sex", "age"]`, and `limit` set to 3
- **THEN** the result contains the same table, columns, rows, row count, limit, offset, truncated, and next-offset fields as the core query

#### Scenario: Recommended surface is discoverable

- **WHEN** a client reads the `list_tables` or `query_data` description
- **THEN** the `passengers` view is identified as the recommended starting point for analysis

### Requirement: Runnable MCP entrypoint

The package SHALL provide the `titanic-mcp` entrypoint that starts the MCP server without requiring a separate HTTP deployment.

#### Scenario: Entrypoint starts the server

- **WHEN** `titanic-mcp` is started over the default stdio transport
- **THEN** an MCP client can initialize the session and list the three tools
