from __future__ import annotations

from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
)


class FilterOperator(StrEnum):
    """Supported filter operators."""

    eq = "eq"
    ne = "ne"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    in_ = "in"
    is_null = "is_null"
    not_null = "not_null"


class OrderDirection(StrEnum):
    """Supported ordering directions."""

    asc = "asc"
    desc = "desc"


class ColumnType(StrEnum):
    """Semantic column types exposed by the catalog."""

    integer = "integer"
    number = "number"
    boolean = "boolean"
    text = "text"


class TableKind(StrEnum):
    """Whether a catalog entry is a logical view or a physical table."""

    view = "view"
    table = "table"


type FilterScalar = StrictStr | StrictInt | StrictFloat | StrictBool | None
type FilterValue = FilterScalar | list[FilterScalar]
type ScalarValue = str | int | float | None


class _InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FilterPredicate(_InputModel):
    """One predicate in a query's AND-combined filter list."""

    column: StrictStr = Field(min_length=1)
    op: FilterOperator
    value: FilterValue = None


class OrderBy(_InputModel):
    """Optional single-column ordering."""

    column: StrictStr = Field(min_length=1)
    direction: OrderDirection = OrderDirection.asc


class QueryDataInput(_InputModel):
    """A bounded, read-only query request."""

    table: StrictStr = Field(min_length=1)
    columns: list[StrictStr] | None = None
    filter: list[FilterPredicate] | None = None
    order_by: OrderBy | None = None
    limit: StrictInt = Field(default=100, ge=1, le=500)
    offset: StrictInt = Field(default=0, ge=0)

    @field_validator("columns")
    @classmethod
    def _validate_columns(cls, columns: list[str] | None) -> list[str] | None:
        if columns is None:
            return None
        if not columns:
            raise ValueError("columns must contain at least one column")
        if any(not column for column in columns):
            raise ValueError("column names must not be empty")
        if len(set(columns)) != len(columns):
            raise ValueError("columns must not contain duplicates")
        return columns


class ColumnMetadata(BaseModel):
    """Public metadata for one catalog column."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: ColumnType
    nullable: bool
    description: str


class TableSummary(BaseModel):
    """One entry in the table catalog."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: TableKind
    description: str
    row_count: int
    recommended: bool


class TableDescription(BaseModel):
    """Full table metadata returned by ``describe_table``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: TableKind
    description: str
    row_count: int
    default_order_by: str
    columns: list[ColumnMetadata]


class QueryResponse(BaseModel):
    """Envelope returned by ``query_data``."""

    model_config = ConfigDict(extra="forbid")

    table: str
    columns: list[str]
    rows: list[dict[str, ScalarValue]]
    row_count: int
    limit: int
    offset: int
    truncated: bool
    next_offset: int | None
