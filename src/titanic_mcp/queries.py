from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from .errors import QueryValidationError
from .models import (
    ColumnMetadata,
    ColumnType,
    FilterOperator,
    FilterPredicate,
    OrderBy,
    OrderDirection,
    QueryDataInput,
    QueryResponse,
    ScalarValue,
    TableDescription,
    TableKind,
    TableSummary,
)

NUMERIC_OPERATORS = frozenset(FilterOperator)
SQL_OPERATORS = {
    FilterOperator.eq: "=",
    FilterOperator.ne: "!=",
    FilterOperator.gt: ">",
    FilterOperator.gte: ">=",
    FilterOperator.lt: "<",
    FilterOperator.lte: "<=",
}
TEXT_OPERATORS = frozenset(
    {
        FilterOperator.eq,
        FilterOperator.ne,
        FilterOperator.in_,
        FilterOperator.is_null,
        FilterOperator.not_null,
    }
)


class SupportsCount(Protocol):
    """The database capability needed to build catalog metadata."""

    def count(self, source_sql: str) -> int: ...


class SupportsQuery(SupportsCount, Protocol):
    """The database capabilities needed to execute a compiled query."""

    def fetch_all(
        self,
        sql: str,
        params: Sequence[object] = (),
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class CompiledQuery:
    """A static SQL statement with bound parameters."""

    sql: str
    params: tuple[object, ...]
    columns: list[str]
    fetch_limit: int


@dataclass(frozen=True)
class ColumnSpec:
    """Static metadata for one catalog column."""

    name: str
    type: ColumnType
    nullable: bool
    description: str
    allowed_operators: frozenset[FilterOperator]


@dataclass(frozen=True)
class TableSpec:
    """Static metadata and source SQL for one catalog entry."""

    name: str
    kind: TableKind
    description: str
    recommended: bool
    source_sql: str
    columns: tuple[ColumnSpec, ...]
    default_order_by: str
    tiebreaker: str

    @property
    def column_map(self) -> dict[str, ColumnSpec]:
        return {column.name: column for column in self.columns}


def _column(
    name: str,
    column_type: ColumnType,
    nullable: bool,
    description: str,
) -> ColumnSpec:
    operators = TEXT_OPERATORS if column_type is ColumnType.text else NUMERIC_OPERATORS
    return ColumnSpec(
        name=name,
        type=column_type,
        nullable=nullable,
        description=description,
        allowed_operators=operators,
    )


_PASSENGERS_SOURCE = """
SELECT
  o.rowid AS passenger_id,
  o.survived AS survived,
  o.pclass AS pclass,
  s.sex AS sex,
  o.age AS age,
  o.sibsp AS sibsp,
  o.parch AS parch,
  o.fare AS fare,
  CASE WHEN o.embarked_id = -1 THEN NULL ELSE e.embarked END AS embarked,
  c."class" AS "class",
  w.who AS who,
  o.adult_male AS adult_male,
  CASE WHEN o.deck_id = -1 THEN NULL ELSE d.deck END AS deck,
  CASE WHEN o.embark_town_id = -1 THEN NULL ELSE et.embark_town END AS embark_town,
  a.alive AS alive,
  o.alone AS alone
FROM "Observation" AS o
LEFT JOIN "Sex" AS s ON s.sex_id = o.sex_id
LEFT JOIN "Embarked" AS e ON e.embarked_id = o.embarked_id
LEFT JOIN "Class" AS c ON c.class_id = o.class_id
LEFT JOIN "Who" AS w ON w.who_id = o.who_id
LEFT JOIN "Deck" AS d ON d.deck_id = o.deck_id
LEFT JOIN "EmbarkTown" AS et ON et.embark_town_id = o.embark_town_id
LEFT JOIN "Alive" AS a ON a.alive_id = o.alive_id
""".strip()

_OBSERVATION_SOURCE = """
SELECT
  rowid AS passenger_id,
  survived,
  pclass,
  age,
  sibsp,
  parch,
  fare,
  adult_male,
  alone,
  sex_id,
  embarked_id,
  class_id,
  who_id,
  deck_id,
  embark_town_id,
  alive_id
FROM "Observation"
""".strip()

_PASSENGER_COLUMNS = (
    _column(
        "passenger_id",
        ColumnType.integer,
        False,
        "Observation row identifier (Observation.rowid).",
    ),
    _column(
        "survived",
        ColumnType.integer,
        False,
        "Survival indicator (0 = died, 1 = survived).",
    ),
    _column("pclass", ColumnType.integer, False, "Passenger class (1, 2, or 3)."),
    _column("sex", ColumnType.text, False, "Passenger sex label."),
    _column("age", ColumnType.number, True, "Age in years; null when unknown."),
    _column(
        "sibsp", ColumnType.integer, False, "Number of siblings or spouses aboard."
    ),
    _column(
        "parch", ColumnType.integer, False, "Number of parents or children aboard."
    ),
    _column("fare", ColumnType.number, False, "Passenger fare."),
    _column(
        "embarked",
        ColumnType.text,
        True,
        "Port of embarkation code; null when unknown.",
    ),
    _column("class", ColumnType.text, False, "Passenger class label."),
    _column("who", ColumnType.text, False, "Passenger category label."),
    _column(
        "adult_male",
        ColumnType.boolean,
        False,
        "Whether the passenger is an adult male (0/1).",
    ),
    _column("deck", ColumnType.text, True, "Cabin deck label; null when unknown."),
    _column(
        "embark_town", ColumnType.text, True, "Embarkation town; null when unknown."
    ),
    _column("alive", ColumnType.text, False, "Survival label."),
    _column(
        "alone",
        ColumnType.boolean,
        False,
        "Whether the passenger traveled alone (0/1).",
    ),
)

_OBSERVATION_COLUMNS = (
    _column(
        "passenger_id",
        ColumnType.integer,
        False,
        "Observation row identifier (Observation.rowid).",
    ),
    _column("survived", ColumnType.integer, True, "Survival indicator (0/1)."),
    _column("pclass", ColumnType.integer, True, "Passenger class (1, 2, or 3)."),
    _column("age", ColumnType.number, True, "Age in years; null when unknown."),
    _column("sibsp", ColumnType.integer, True, "Number of siblings or spouses aboard."),
    _column("parch", ColumnType.integer, True, "Number of parents or children aboard."),
    _column("fare", ColumnType.number, True, "Passenger fare."),
    _column("adult_male", ColumnType.boolean, True, "Adult male indicator (0/1)."),
    _column("alone", ColumnType.boolean, True, "Traveling alone indicator (0/1)."),
    _column("sex_id", ColumnType.integer, True, "Foreign key to the Sex lookup."),
    _column(
        "embarked_id", ColumnType.integer, True, "Foreign key to the Embarked lookup."
    ),
    _column("class_id", ColumnType.integer, True, "Foreign key to the Class lookup."),
    _column("who_id", ColumnType.integer, True, "Foreign key to the Who lookup."),
    _column("deck_id", ColumnType.integer, True, "Foreign key to the Deck lookup."),
    _column(
        "embark_town_id",
        ColumnType.integer,
        True,
        "Foreign key to the EmbarkTown lookup.",
    ),
    _column("alive_id", ColumnType.integer, True, "Foreign key to the Alive lookup."),
)

TABLES: dict[str, TableSpec] = {
    "passengers": TableSpec(
        name="passengers",
        kind=TableKind.view,
        description=(
            "Logical view of the Titanic manifest with decoded labels and one row per "
            "observation; recommended as the starting point for analysis."
        ),
        recommended=True,
        source_sql=_PASSENGERS_SOURCE,
        columns=_PASSENGER_COLUMNS,
        default_order_by="passenger_id",
        tiebreaker="passenger_id",
    ),
    "Observation": TableSpec(
        name="Observation",
        kind=TableKind.table,
        description="Raw Titanic observation rows with lookup IDs.",
        recommended=False,
        source_sql=_OBSERVATION_SOURCE,
        columns=_OBSERVATION_COLUMNS,
        default_order_by="passenger_id",
        tiebreaker="passenger_id",
    ),
    "Sex": TableSpec(
        name="Sex",
        kind=TableKind.table,
        description="Lookup table mapping sex IDs to labels.",
        recommended=False,
        source_sql='SELECT sex_id, sex FROM "Sex"',
        columns=(
            _column("sex_id", ColumnType.integer, True, "Sex lookup identifier."),
            _column("sex", ColumnType.text, True, "Sex label."),
        ),
        default_order_by="sex_id",
        tiebreaker="sex_id",
    ),
    "Embarked": TableSpec(
        name="Embarked",
        kind=TableKind.table,
        description="Lookup table mapping embarkation codes to IDs.",
        recommended=False,
        source_sql='SELECT embarked_id, embarked FROM "Embarked"',
        columns=(
            _column(
                "embarked_id",
                ColumnType.integer,
                True,
                "Embarkation lookup identifier.",
            ),
            _column("embarked", ColumnType.text, True, "Embarkation code label."),
        ),
        default_order_by="embarked_id",
        tiebreaker="embarked_id",
    ),
    "Class": TableSpec(
        name="Class",
        kind=TableKind.table,
        description="Lookup table mapping passenger class IDs to labels.",
        recommended=False,
        source_sql='SELECT class_id, "class" FROM "Class"',
        columns=(
            _column(
                "class_id", ColumnType.integer, True, "Passenger class identifier."
            ),
            _column("class", ColumnType.text, True, "Passenger class label."),
        ),
        default_order_by="class_id",
        tiebreaker="class_id",
    ),
    "Who": TableSpec(
        name="Who",
        kind=TableKind.table,
        description="Lookup table mapping passenger category IDs to labels.",
        recommended=False,
        source_sql='SELECT who_id, who FROM "Who"',
        columns=(
            _column(
                "who_id", ColumnType.integer, True, "Passenger category identifier."
            ),
            _column("who", ColumnType.text, True, "Passenger category label."),
        ),
        default_order_by="who_id",
        tiebreaker="who_id",
    ),
    "Deck": TableSpec(
        name="Deck",
        kind=TableKind.table,
        description="Lookup table mapping cabin deck IDs to labels.",
        recommended=False,
        source_sql='SELECT deck_id, deck FROM "Deck"',
        columns=(
            _column("deck_id", ColumnType.integer, True, "Cabin deck identifier."),
            _column("deck", ColumnType.text, True, "Cabin deck label."),
        ),
        default_order_by="deck_id",
        tiebreaker="deck_id",
    ),
    "EmbarkTown": TableSpec(
        name="EmbarkTown",
        kind=TableKind.table,
        description="Lookup table mapping embarkation town IDs to labels.",
        recommended=False,
        source_sql='SELECT embark_town_id, embark_town FROM "EmbarkTown"',
        columns=(
            _column(
                "embark_town_id",
                ColumnType.integer,
                True,
                "Embarkation town identifier.",
            ),
            _column("embark_town", ColumnType.text, True, "Embarkation town label."),
        ),
        default_order_by="embark_town_id",
        tiebreaker="embark_town_id",
    ),
    "Alive": TableSpec(
        name="Alive",
        kind=TableKind.table,
        description="Lookup table mapping survival IDs to labels.",
        recommended=False,
        source_sql='SELECT alive_id, alive FROM "Alive"',
        columns=(
            _column("alive_id", ColumnType.integer, True, "Survival label identifier."),
            _column("alive", ColumnType.text, True, "Survival label."),
        ),
        default_order_by="alive_id",
        tiebreaker="alive_id",
    ),
}


def get_table_spec(table_name: str) -> TableSpec:
    """Return a catalog entry or raise a field-scoped validation error."""

    try:
        return TABLES[table_name]
    except KeyError:
        raise QueryValidationError("table", f"Unknown table: {table_name!r}") from None


def list_tables(database: SupportsCount) -> list[TableSummary]:
    """Return the nine-entry catalog with live row counts."""

    return [
        TableSummary(
            name=spec.name,
            kind=spec.kind,
            description=spec.description,
            row_count=database.count(spec.source_sql),
            recommended=spec.recommended,
        )
        for spec in TABLES.values()
    ]


def describe_table(database: SupportsCount, table_name: str) -> TableDescription:
    """Return full metadata for one catalog entry."""

    spec = get_table_spec(table_name)
    return TableDescription(
        name=spec.name,
        kind=spec.kind,
        description=spec.description,
        row_count=database.count(spec.source_sql),
        default_order_by=spec.default_order_by,
        columns=[
            ColumnMetadata(
                name=column.name,
                type=column.type,
                nullable=column.nullable,
                description=column.description,
            )
            for column in spec.columns
        ],
    )


def validate_query(request: QueryDataInput) -> TableSpec:
    """Validate a request against the catalog and return its table spec."""

    spec = get_table_spec(request.table)

    if request.filter is not None and len(request.filter) > 20:
        raise QueryValidationError("filter", "At most 20 predicates are allowed.")

    if request.columns is not None:
        for index, column_name in enumerate(request.columns):
            if column_name not in spec.column_map:
                raise QueryValidationError(
                    f"columns[{index}]",
                    f"Unknown column {column_name!r} for table {spec.name!r}.",
                )

    if request.order_by is not None and request.order_by.column not in spec.column_map:
        raise QueryValidationError(
            "order_by.column",
            f"Unknown column {request.order_by.column!r} for table {spec.name!r}.",
        )

    for index, predicate in enumerate(request.filter or ()):
        _validate_predicate(spec, index, predicate)

    return spec


def _validate_predicate(
    spec: TableSpec,
    index: int,
    predicate: FilterPredicate,
) -> None:
    column = spec.column_map.get(predicate.column)
    if column is None:
        raise QueryValidationError(
            f"filter[{index}].column",
            f"Unknown column {predicate.column!r} for table {spec.name!r}.",
        )

    if predicate.op not in column.allowed_operators:
        raise QueryValidationError(
            f"filter[{index}].op",
            f"Operator {predicate.op.value!r} is not allowed for column {column.name!r}.",
        )

    if predicate.op in {FilterOperator.is_null, FilterOperator.not_null}:
        if predicate.value is not None:
            raise QueryValidationError(
                f"filter[{index}].value",
                f"Operator {predicate.op.value!r} does not take a value.",
            )
        return

    if predicate.op is FilterOperator.in_:
        _validate_in_value(index, column, predicate.value)
        return

    _validate_scalar_value(index, column, predicate.value)


def _validate_in_value(index: int, column: ColumnSpec, value: object) -> None:
    if not isinstance(value, list):
        raise QueryValidationError(
            f"filter[{index}].value",
            "Operator 'in' requires a list of values.",
        )
    if not 1 <= len(value) <= 100:
        raise QueryValidationError(
            f"filter[{index}].value",
            "Operator 'in' requires between 1 and 100 values.",
        )

    for value_index, item in enumerate(value):
        if item is None:
            raise QueryValidationError(
                f"filter[{index}].value[{value_index}]",
                "Null is not allowed in 'in' values.",
            )
        if not _value_matches(column.type, item):
            raise QueryValidationError(
                f"filter[{index}].value[{value_index}]",
                f"Value {item!r} does not match column {column.name!r} "
                f"type {column.type.value!r}.",
            )


def _validate_scalar_value(index: int, column: ColumnSpec, value: object) -> None:
    if value is None:
        raise QueryValidationError(
            f"filter[{index}].value",
            "A value is required for this operator.",
        )
    if isinstance(value, list):
        raise QueryValidationError(
            f"filter[{index}].value",
            "A scalar value is required for this operator.",
        )
    if not _value_matches(column.type, value):
        raise QueryValidationError(
            f"filter[{index}].value",
            f"Value {value!r} does not match column {column.name!r} "
            f"type {column.type.value!r}.",
        )


def _value_matches(column_type: ColumnType, value: object) -> bool:
    if column_type is ColumnType.text:
        return isinstance(value, str)
    if column_type is ColumnType.integer:
        return isinstance(value, int) and not isinstance(value, bool)
    if column_type is ColumnType.number:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if column_type is ColumnType.boolean:
        return isinstance(value, bool) or (isinstance(value, int) and value in (0, 1))
    return False


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _compile_filters(
    spec: TableSpec,
    predicates: tuple[FilterPredicate, ...] | list[FilterPredicate],
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    for predicate in predicates:
        column = spec.column_map[predicate.column]
        expression = _quote_identifier(column.name)

        if predicate.op is FilterOperator.is_null:
            clauses.append(f"{expression} IS NULL")
        elif predicate.op is FilterOperator.not_null:
            clauses.append(f"{expression} IS NOT NULL")
        elif predicate.op is FilterOperator.in_:
            values = cast(list[object], predicate.value)
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{expression} IN ({placeholders})")
            params.extend(values)
        else:
            clauses.append(f"{expression} {SQL_OPERATORS[predicate.op]} ?")
            params.append(predicate.value)

    return " AND ".join(clauses), params


def _compile_order(spec: TableSpec, order_by: OrderBy | None) -> str:
    if order_by is None:
        return f"{_quote_identifier(spec.default_order_by)} ASC"

    expression = _quote_identifier(order_by.column)
    direction = "ASC" if order_by.direction is OrderDirection.asc else "DESC"
    terms = [f"({expression} IS NULL) ASC", f"{expression} {direction}"]
    if order_by.column != spec.tiebreaker:
        terms.append(f"{_quote_identifier(spec.tiebreaker)} ASC")
    return ", ".join(terms)


def compile_query(request: QueryDataInput) -> CompiledQuery:
    """Validate a request and compile it to static SQL with bound parameters."""

    spec = validate_query(request)
    selected_columns = (
        list(request.columns)
        if request.columns is not None
        else [column.name for column in spec.columns]
    )

    select_sql = ", ".join(_quote_identifier(name) for name in selected_columns)
    where_sql, params = _compile_filters(spec, request.filter or ())
    order_sql = _compile_order(spec, request.order_by)

    sql_parts = [
        f"SELECT {select_sql}",
        f"FROM ({spec.source_sql}) AS source",
    ]
    if where_sql:
        sql_parts.append(f"WHERE {where_sql}")
    sql_parts.extend([f"ORDER BY {order_sql}", "LIMIT ? OFFSET ?"])

    params.extend([request.limit + 1, request.offset])
    return CompiledQuery(
        sql="\n".join(sql_parts),
        params=tuple(params),
        columns=selected_columns,
        fetch_limit=request.limit + 1,
    )


def build_response(
    request: QueryDataInput,
    compiled: CompiledQuery,
    rows: Sequence[Mapping[str, ScalarValue]],
) -> QueryResponse:
    """Slice a ``limit + 1`` fetch into the public response envelope."""

    page = rows[: request.limit]
    truncated = len(rows) > request.limit
    next_offset = request.offset + len(page) if truncated else None
    ordered_rows = [
        {column: row[column] for column in compiled.columns} for row in page
    ]

    return QueryResponse(
        table=request.table,
        columns=compiled.columns,
        rows=ordered_rows,
        row_count=len(ordered_rows),
        limit=request.limit,
        offset=request.offset,
        truncated=truncated,
        next_offset=next_offset,
    )


def query_data(database: SupportsQuery, request: QueryDataInput) -> QueryResponse:
    """Validate, compile, execute, and paginate one query request."""

    compiled = compile_query(request)
    rows = database.fetch_all(compiled.sql, compiled.params)
    return build_response(request, compiled, rows)
