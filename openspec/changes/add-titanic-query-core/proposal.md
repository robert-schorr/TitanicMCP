# Proposal

## Why

The repository has a Titanic SQLite database but no data-access layer. Before exposing tools to MCP clients, the project needs a tested, read-only query core that owns the catalog, passenger semantics, validation, and SQL compilation. Building this layer first keeps SQL and data rules independent from transport and framework concerns.

## What Changes

- Add typed query inputs, filter predicates, ordering, metadata, and response models.
- Add the catalog for `passengers` and the eight raw tables, including descriptions, column types, nullability, allowed operations, and default ordering.
- Implement the `passengers` logical view without modifying `titanic.db`: decode lookup labels, map `-1` categorical sentinels to `NULL`, and expose `Observation.rowid` as `passenger_id`.
- Add read-only SQLite access using a read-only URI and `PRAGMA query_only`.
- Add semantic filter validation, static SQL compilation, parameter binding, null-last ordering, ID tiebreakers, and `limit + 1` pagination.
- Add domain and security unit tests for the catalog, SQL compiler, read-only behavior, and passenger semantics.
- Document the core data contract in `README.md`.

This change does **not** add FastMCP tools, HTTP serving, authentication, logging middleware, or container packaging. Those are delivered by later changes.

## Capabilities

### New Capabilities

- `titanic-data-access`: Read-only catalog and query behavior over the Titanic database, including the `passengers` view, allowlists, typed filters, deterministic ordering, and pagination.

### Modified Capabilities

None. No existing OpenSpec capabilities are present.

## Impact

- **Code:** Add `models.py`, `errors.py`, `database.py`, and `queries.py`; tests under `tests/domain` and `tests/security`.
- **Dependencies:** No new runtime dependency is required; Pydantic is already present.
- **Data:** No schema changes, migrations, or writes to `data/titanic.db`.
- **Documentation:** Add the core data contract and usage examples to `README.md`.
- **Depends on:** Nothing.
- **Unblocks:** `add-mcp-query-tools`.
