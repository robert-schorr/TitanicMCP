# Design

## Context

See `proposal.md` for motivation. This change creates the query core that later MCP changes depend on. The target database has eight normalized tables and 891 `Observation` rows, uses `-1` lookup rows for missing categoricals, and has no primary keys, foreign keys, or indexes. The current package is a hello-world scaffold with Pydantic and `mcp[cli]`; this change does not need either MCP framework path.

## Goals / Non-Goals

**Goals:**

- A read-only, typed query core with no MCP or HTTP dependency.
- A static catalog that defines `passengers` and the eight raw tables.
- Safe SQL compilation with bound parameters and no user-controlled identifiers.
- Deterministic filtering, ordering, and pagination.
- Domain and security tests that can run without a server.

**Non-Goals:**

- MCP tools, FastMCP, stdio, HTTP, authentication, or logging middleware.
- Container packaging.
- Arbitrary SQL, joins, aggregates, `GROUP BY`, OR filters, multi-column ordering, or text range operators.
- Database writes, schema changes, or migrations.

## Decisions

### 1. Core module boundaries

```text
src/titanic_mcp/
  models.py      # Pydantic inputs/outputs, enums, metadata models
  errors.py      # QueryValidationError only in this change
  database.py    # read-only SQLite connection and execution
  queries.py     # static catalog, semantic validation, SQL compiler
```

Dependency direction:

```text
models.py     -> pydantic only
errors.py     -> stdlib only
database.py   -> sqlite3 only
queries.py    -> models.py, errors.py
```

`database.py` does not import the catalog. `queries.py` does not open a database. The eventual `server.py` will orchestrate the two.

### 2. Read-only database access

`database.py` opens SQLite with `file:<path>?mode=ro`, `uri=True`, sets `PRAGMA query_only=ON`, and uses `sqlite3.Row` for mapping. A connection is opened per operation; there is no shared mutable connection across requests. This works with synchronous tool execution in a thread pool and keeps lifecycle simple.

The database file is never copied, vacuumed, migrated, or written. Tests hash the file before and after operations.

### 3. Static catalog and source SQL

`queries.py` owns a `TableSpec` registry:

- `name`, `kind`, `description`, `recommended`
- `source_sql`: a complete static `SELECT`
- `columns`: ordered `ColumnSpec` objects with `name`, `type`, `nullable`, `description`, and allowed operators
- `default_order_by`

The compiler wraps the static source:

```sql
SELECT <static column expressions>
FROM (<source_sql>) AS source
WHERE <bound predicates>
ORDER BY <static ordering>
LIMIT ? OFFSET ?
```

User input selects catalog entries; it never becomes a table name, column expression, or SQL fragment. Even the table name is only used for a dictionary lookup.

The `passengers` source decodes lookup labels and maps sentinels:

```sql
SELECT
  o.rowid AS passenger_id,
  o.survived,
  o.pclass,
  s.sex,
  o.age,
  o.sibsp,
  o.parch,
  o.fare,
  CASE WHEN o.embarked_id = -1 THEN NULL ELSE e.embarked END AS embarked,
  c.class,
  w.who,
  o.adult_male,
  CASE WHEN o.deck_id = -1 THEN NULL ELSE d.deck END AS deck,
  CASE WHEN o.embark_town_id = -1 THEN NULL ELSE et.embark_town END AS embark_town,
  a.alive,
  o.alone
FROM Observation AS o
LEFT JOIN Sex AS s ON s.sex_id = o.sex_id
LEFT JOIN Embarked AS e ON e.embarked_id = o.embarked_id
LEFT JOIN Class AS c ON c.class_id = o.class_id
LEFT JOIN Who AS w ON w.who_id = o.who_id
LEFT JOIN Deck AS d ON d.deck_id = o.deck_id
LEFT JOIN EmbarkTown AS et ON et.embark_town_id = o.embark_town_id
LEFT JOIN Alive AS a ON a.alive_id = o.alive_id
```

Raw `Observation` projects `rowid AS passenger_id` followed by its original columns. Lookup sources project their ID and label explicitly.

`list_tables` and `describe_table` compute counts with `SELECT COUNT(*) FROM (<source_sql>)`. Nine counts are cheap at 891 rows and avoid a second metadata cache with invalidation questions.

### 4. Validation split

Pydantic handles structural constraints:

- `QueryDataInput`: table, optional columns, optional filter, optional order_by, limit 1–500, offset >= 0.
- `FilterPredicate`: column, operator enum, scalar/list/null value.
- `OrderBy`: column and `asc`/`desc`.
- All models use `extra="forbid"`; columns reject duplicates and preserve their order.

`queries.py` handles semantic constraints:

- table, columns, and ordering column must exist in the catalog
- numeric columns accept all operators; text columns accept `eq`, `ne`, `in`, `is_null`, `not_null`
- `is_null`/`not_null` carry no value; `eq: null` is rejected
- `in` has 1–100 values of the column type; `None` is rejected inside `in`
- at most 20 predicates
- values must match the column type

Failures raise `QueryValidationError(field_paths, detail)` from `errors.py`. This core change does not define the MCP-facing safe error message; the later server layer maps field paths to its client contract.

### 5. SQL compilation

`compile_query` returns:

```text
CompiledQuery(
  sql: str,
  params: tuple[object, ...],
  columns: list[str],
  fetch_limit: int,
)
```

Filter compilation uses `?` placeholders only:

```sql
"age" >= ?
"sex" = ?
"class" IN (?, ?)
"deck" IS NULL
"deck" IS NOT NULL
```

`in` expands one placeholder per value. The only interpolated token is `ASC` or `DESC` from a closed enum.

Ordering is:

```sql
ORDER BY (<column_expr> IS NULL) ASC,
         <column_expr> ASC|DESC,
         <tiebreaker_expr> ASC
```

The tiebreaker is `passenger_id` for `passengers` and `Observation`, and the ID column for lookup tables. If the requested order column is already the tiebreaker, the duplicate term is omitted.

### 6. Pagination

`fetch_limit` is `limit + 1`. `database.py` returns up to that many rows; a pure response builder in the core slices to `limit`, sets `truncated` from the extra row, and computes `next_offset`. This avoids a separate total-count query and keeps the response envelope independent of transport.

### 7. Tests

Domain tests:

- catalog contents, row counts, order, and descriptions
- catalog consistency against `PRAGMA table_info` and the actual `passengers` source
- Pydantic structural constraints
- query compiler SQL/params, null filters, `in` expansion, ordering, tiebreakers, and `limit + 1`
- read-only URI, write rejection, row mapping, and counts
- passenger row count, decoded values, sentinels, and unique IDs

Security tests:

- malicious table/column/order names are rejected by the catalog
- filter values remain bound parameters
- a database hash is unchanged before and after queries

## Risks / Trade-offs

- **Static catalog drift** → schema-consistency tests compare the catalog with the live database.
- **No indexes** → the dataset is tiny; full scans are acceptable.
- **Text range filters unavailable** → equality, membership, and null filters remain sufficient for the dataset.
- **No total count** → `row_count` is the page size and `truncated` uses `limit + 1`; this is intentional.
- **Per-operation connections** → a small connection overhead in exchange for simple, read-only lifecycle handling.

## Migration Plan

1. Add the four core modules and their tests.
2. Add README documentation for the core data contract.
3. Run the domain/security tests, lint, and type checks.
4. No data migration or entrypoint change is required.

Rollback is a source revert; `data/titanic.db` is untouched.

## Open Questions

None.
