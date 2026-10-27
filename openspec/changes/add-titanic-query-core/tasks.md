# Tasks

## 1. Test scaffolding, errors, and models

- [x] 1.1 Create `tests/domain/`, `tests/security/`, and `tests/conftest.py` with repository paths, the database path, and a database file-hash fixture; verify `uv run pytest --collect-only` discovers the new suites
- [x] 1.2 Implement `errors.py` with `QueryValidationError(field_paths, detail)` and no framework imports; verify `tests/domain/test_errors.py` covers field-path normalization and safe string behavior
- [x] 1.3 Implement `models.py` with filter/order/query enums, strict input models, column and table metadata models, and the query response envelope; verify `tests/domain/test_models.py` covers extra fields, duplicate columns, `limit` 1–500, `offset >= 0`, and filter shape
- [x] 1.4 Implement `database.py` with a read-only SQLite URI (`mode=ro`, `uri=True`), `PRAGMA query_only=ON`, `sqlite3.Row` mapping, `fetch_all`, `fetch_one`, and `count`; verify `tests/domain/test_database.py` rejects writes and returns expected rows and counts
- [x] 1.5 Add a database integrity test that records the schema, row counts, and SHA-256 hash before and after core operations; verify the file is byte-identical afterward

## 2. Static catalog and schema consistency

- [x] 2.1 Implement the `TableSpec`/`ColumnSpec` registry in `queries.py` for `passengers` and the eight raw tables, including descriptions, types, nullability, allowed operators, source SQL, and default ordering; verify `tests/domain/test_catalog.py`
- [x] 2.2 Implement `list_tables` and `describe_table` core functions that compute counts from each static source; verify the nine entries, stated order, row counts, `recommended` flags, and 16 passenger columns
- [x] 2.3 Add a catalog/schema consistency test that compares catalog columns, types, and nullability with `PRAGMA table_info` and validates every source SQL statement against the live database; verify `tests/domain/test_catalog_matches_schema.py` passes

## 3. Semantic validation and SQL compilation

- [x] 3.1 Implement semantic validation for table, column, ordering, and operator allowlists; numeric columns accept all operators, text columns accept only `eq`, `ne`, `in`, `is_null`, and `not_null`; reject mismatched types and more than 20 predicates with `QueryValidationError` field paths
- [x] 3.2 Implement `compile_query` with catalog-selected column expressions, bound `?` predicates, `in` placeholder expansion, null filters, null-last ordering, and the ID tiebreaker; verify SQL text never contains user values and parameters are ordered as expected in `tests/domain/test_query_builder.py`
- [x] 3.3 Implement a response builder that slices `limit + 1` rows to `limit`, computes `truncated` and `next_offset`, and preserves requested column order; verify projection, envelope, first-page, final-page, and stable-offset scenarios in `tests/domain/test_pagination.py`
- [x] 3.4 Add security tests for malicious table names, column names, ordering names, operators, and filter values; verify `tests/security/test_query_injection.py` rejects catalog misses and confirms values remain bound parameters

## 4. Passengers semantics

- [x] 4.1 Implement the `passengers` source SQL to expose `Observation.rowid` as `passenger_id`, decode lookup labels, and map `-1` category sentinels to `NULL` without modifying the database
- [x] 4.2 Verify passenger semantics in `tests/domain/test_passengers.py`: 891 rows, the documented first row, 688 null decks, 203 non-null decks, two null embarked/embark-town rows, and unique `passenger_id` values
- [x] 4.3 Verify raw access in `tests/domain/test_raw_tables.py`: `Observation.passenger_id` aliases `rowid`, lookup tables expose ID/label pairs, and all eight tables are queryable

## 5. Documentation and quality gates

- [x] 5.1 Add a README core section covering `passengers` versus raw tables, column semantics, supported filters, ordering, pagination, and the read-only guarantee; verify documented examples against the core functions
- [x] 5.2 Run `uv run pytest tests/domain tests/security`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run ty check`; verify all pass
- [x] 5.3 Confirm no MCP, FastMCP, HTTP, Docker, or database schema changes were introduced by this change

## Workflow follow-up

- Archive the change after implementation and review are complete.
- Sync the `titanic-data-access` delta spec into the main OpenSpec specs during archive and verify the resulting capability file.
