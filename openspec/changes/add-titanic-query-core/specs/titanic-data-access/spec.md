# Spec Delta

## Purpose

Provide a testable, read-only query core that discovers the Titanic data surface and returns bounded, validated query results independently of any MCP transport.

## ADDED Requirements

### Requirement: Read-only database access

The query core SHALL open the Titanic database in read-only mode and MUST NOT create, alter, or delete database objects or rows during any operation.

#### Scenario: Core operations leave the database unchanged

- **WHEN** any sequence of `list_tables`, `describe_table`, and `query_data` core operations completes
- **THEN** the database schema, row counts, and file content hash are unchanged

### Requirement: Table catalog

`list_tables` SHALL return exactly nine entries: the `passengers` logical view followed by the eight raw tables `Observation`, `Sex`, `Embarked`, `Class`, `Who`, `Deck`, `EmbarkTown`, and `Alive`. Each entry SHALL include `name`, `kind`, `description`, `row_count`, and `recommended`.

#### Scenario: Catalog contents and row counts

- **WHEN** `list_tables` is called
- **THEN** it returns the nine entries in the stated order
- **AND** `passengers` has kind `view`, 891 rows, and `recommended` true
- **AND** the raw tables have kind `table` and report 891, 2, 4, 3, 3, 8, 4, and 2 rows respectively

### Requirement: Table description

`describe_table` SHALL return the table's `name`, `kind`, `description`, `row_count`, `default_order_by`, and an ordered column list. Each column SHALL include `name`, `type`, `nullable`, and `description`.

#### Scenario: Passengers metadata

- **WHEN** `describe_table` is called with `passengers`
- **THEN** `default_order_by` is `passenger_id`
- **AND** the 16 columns are returned in this order: `passenger_id`, `survived`, `pclass`, `sex`, `age`, `sibsp`, `parch`, `fare`, `embarked`, `class`, `who`, `adult_male`, `deck`, `embark_town`, `alive`, `alone`
- **AND** `age`, `embarked`, `deck`, and `embark_town` are marked nullable while the other columns are marked non-nullable

#### Scenario: Raw table metadata

- **WHEN** `describe_table` is called with `Sex`
- **THEN** `default_order_by` is `sex_id`
- **AND** the columns are `sex_id` and `sex`

### Requirement: Passengers semantic view

The `passengers` view SHALL expose one row per `Observation` with `passenger_id` equal to `Observation.rowid`, decoded category labels, and `NULL` for `-1` category sentinels. `survived`, `pclass`, `adult_male`, and `alone` SHALL retain their numeric source values.

#### Scenario: Decoded passenger data

- **WHEN** `query_data` requests the first `passengers` row in `passenger_id` order
- **THEN** the row has `passenger_id` 1, `survived` 0, `pclass` 3, `sex` `male`, `age` 22.0, `sibsp` 1, `parch` 0, `fare` 7.25, `embarked` `S`, `class` `Third`, `who` `man`, `adult_male` 1, `deck` null, `embark_town` `Southampton`, `alive` `no`, and `alone` 0

#### Scenario: Missing categoricals become null

- **WHEN** `query_data` filters `passengers` with `deck` `is_null`
- **THEN** 688 rows are returned with `deck` null
- **AND** the 2 rows whose `embarked_id` or `embark_town_id` is `-1` also expose null for those columns

### Requirement: Raw table access

All eight raw tables SHALL be queryable with their original columns. `Observation` SHALL additionally expose `passenger_id` as an alias for `rowid`, and lookup tables SHALL expose their ID and label columns.

#### Scenario: Observation exposes passenger identity

- **WHEN** `query_data` requests `passenger_id` and `survived` from `Observation`, ordered by `passenger_id`, with limit 1
- **THEN** the row has `passenger_id` 1 and `survived` 0

#### Scenario: Lookup tables expose IDs and labels

- **WHEN** `query_data` requests `sex_id` and `sex` from `Sex`
- **THEN** the rows include `(0, female)` and `(1, male)`

### Requirement: Query projection and response envelope

`query_data` SHALL accept an optional `columns` list and SHALL return `{table, columns, rows, row_count, limit, offset, truncated, next_offset}`. Omitted columns SHALL return all catalog columns in catalog order; requested columns SHALL be returned in the requested order.

#### Scenario: Requested projection order

- **WHEN** `query_data` requests `columns` as `["sex", "passenger_id"]`
- **THEN** the response `columns` array is `["sex", "passenger_id"]`
- **AND** every row object presents those keys in that order

#### Scenario: Default projection

- **WHEN** `query_data` omits `columns`
- **THEN** all columns from the table catalog are returned in catalog order

#### Scenario: Response envelope

- **WHEN** `query_data` completes successfully
- **THEN** `row_count` equals the number of objects in `rows`
- **AND** `limit` and `offset` echo the effective request values

### Requirement: Filter predicates

`query_data` SHALL accept up to 20 predicates combined with AND. Supported operators SHALL be `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `is_null`, and `not_null`. `is_null` and `not_null` SHALL take no value; `in` SHALL take 1–100 scalar values.

#### Scenario: Predicates are combined with AND

- **WHEN** `query_data` filters `passengers` with `age >= 30` and `sex = female`
- **THEN** every returned row has an age of at least 30 and sex `female`
- **AND** the result contains fewer than 891 rows

#### Scenario: Membership filter

- **WHEN** `query_data` filters `passengers` with `class` `in` `["First", "Second"]`
- **THEN** every returned row has class `First` or `Second`

#### Scenario: Null filters

- **WHEN** `query_data` filters `passengers` with `deck` `is_null`
- **THEN** 688 rows are returned
- **WHEN** `query_data` filters `passengers` with `deck` `not_null`
- **THEN** 203 rows are returned

### Requirement: Filter type compatibility

Numeric columns SHALL accept every supported operator. Text columns SHALL accept only `eq`, `ne`, `in`, `is_null`, and `not_null`. Supplied values MUST match the column's type.

#### Scenario: Numeric range accepted

- **WHEN** `query_data` filters `passengers` with `age` `gte` 30
- **THEN** the request succeeds

#### Scenario: Text range rejected

- **WHEN** `query_data` filters `passengers` with `sex` `gt` `male`
- **THEN** the request is rejected as invalid for the filter operator

#### Scenario: Type mismatch rejected

- **WHEN** `query_data` filters `passengers` with `pclass` `eq` `First`
- **THEN** the request is rejected as invalid for the filter value

### Requirement: Deterministic ordering

`query_data` SHALL support optional single-column ordering with `asc` or `desc`. Results MUST be deterministic by adding the table's ID tiebreaker, and NULL values MUST sort after non-NULL values in both directions.

#### Scenario: Descending order

- **WHEN** `query_data` orders `passengers` by `fare` `desc` with limit 5
- **THEN** the returned fares are non-increasing

#### Scenario: Ties use the ID tiebreaker

- **WHEN** two returned rows share the requested order value
- **THEN** the row with the lower `passenger_id` appears first

#### Scenario: Nulls sort last

- **WHEN** `query_data` orders `passengers` by `age` `asc` or `desc`
- **THEN** rows with null `age` appear after all rows with a non-null age

### Requirement: Pagination

`query_data` SHALL default to `limit` 100, accept limits from 1 to 500, and accept `offset` greater than or equal to 0. `truncated` SHALL indicate whether more matching rows exist; `next_offset` SHALL be `offset + row_count` when truncated and `null` otherwise.

#### Scenario: First page

- **WHEN** `query_data` requests limit 5 and offset 0 from a result with more than 5 rows
- **THEN** 5 rows are returned
- **AND** `truncated` is true and `next_offset` is 5

#### Scenario: Final page

- **WHEN** `query_data` requests offset 890 with limit 5 from `passengers`
- **THEN** 1 row is returned
- **AND** `truncated` is false and `next_offset` is null

#### Scenario: Offset paging is stable

- **WHEN** the first page uses limit 5 and offset 0
- **AND** the second page uses limit 5 and offset 5 with the same ordering
- **THEN** the two pages contain no overlapping `passenger_id` values
