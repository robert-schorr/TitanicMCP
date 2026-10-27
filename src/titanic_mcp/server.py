from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterable, Sequence
from functools import wraps
from pathlib import Path
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware, MiddlewareContext
from pydantic import Field, StrictInt, StrictStr
from pydantic import ValidationError as PydanticValidationError

from . import queries
from .database import Database
from .errors import InvalidArgumentsError, QueryValidationError, SafeToolError
from .logging_config import configure_logging
from .models import FilterPredicate, OrderBy, QueryDataInput

logger = logging.getLogger("titanic_mcp.server")

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "titanic.db"

SERVER_INSTRUCTIONS = (
    "Read-only access to the Titanic passenger manifest. Call list_tables first; "
    "the passengers view is the recommended starting point for analysis. "
    "All queries are bounded and return only catalog columns."
)


def _format_field_path(location: Sequence[Any]) -> str:
    """Format a Pydantic location tuple as a dotted path with indices."""

    path = ""
    for part in location:
        if part == "__root__":
            continue
        if isinstance(part, int):
            path += f"[{part}]"
        elif path:
            path += f".{part}"
        else:
            path = str(part)
    return path or "request"


def _sorted_field_paths(locations: Iterable[Sequence[Any]]) -> list[str]:
    return sorted({_format_field_path(location) for location in locations})


def _validation_field_paths(error: PydanticValidationError) -> list[str]:
    return _sorted_field_paths(tuple(item["loc"]) for item in error.errors())


def _request_id(context: MiddlewareContext[Any]) -> str | int:
    fastmcp_context: Context | None = context.fastmcp_context
    if fastmcp_context is not None:
        request_id = fastmcp_context.request_id
        if request_id is not None:
            return request_id
    return str(uuid.uuid4())


def _correlation_id() -> str | None:
    headers = get_http_headers()
    return headers.get("x-request-id") or headers.get("x-correlation-id")


def _root_cause(error: BaseException) -> BaseException:
    current = error
    seen: set[int] = set()
    while current.__cause__ is not None and id(current) not in seen:
        seen.add(id(current))
        current = current.__cause__
    return current


def _tool_metadata(arguments: dict[str, Any]) -> tuple[str | None, int]:
    table = arguments.get("table")
    table_name = table if isinstance(table, str) else None
    filters = arguments.get("filter")
    filter_count = len(filters) if isinstance(filters, list) else 0
    return table_name, filter_count


class _ClassifiedToolError(ToolError):
    """A tool failure that already carries its safe client classification.

    FastMCP masks unclassified exceptions before middleware sees them, so the
    tool wrapper raises this type to preserve domain-safe classifications.
    """

    def __init__(
        self,
        message: str,
        *,
        status: str,
        error_type: str,
        field_paths: Sequence[str] = (),
    ) -> None:
        self.status = status
        self.error_type = error_type
        self.field_paths = tuple(field_paths)
        super().__init__(message)


def _safe_tool(function: Any) -> Any:
    """Convert classified tool errors into middleware-visible exceptions."""

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except QueryValidationError as exc:
            raise _ClassifiedToolError(
                str(exc),
                status="invalid_arguments",
                error_type="domain_validation",
                field_paths=exc.field_paths,
            ) from exc
        except SafeToolError as exc:
            raise _ClassifiedToolError(
                str(exc),
                status="safe_error",
                error_type="safe_tool_error",
            ) from exc

    return wrapper


class ToolCallMiddleware(Middleware):
    """Apply the safe error contract and emit one canonical tool-call record."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Any,
    ) -> Any:
        started = time.perf_counter()
        tool_name = context.message.name
        arguments = context.message.arguments or {}
        table, filter_count = _tool_metadata(arguments)
        request_id = _request_id(context)
        correlation_id = _correlation_id()
        status = "ok"
        error_type = "none"
        field_paths: list[str] = []

        def log_internal(message: str, **extra: Any) -> None:
            logger.warning(
                message,
                extra={
                    "event": "tool_call_internal_error",
                    "tool_name": tool_name,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    **extra,
                },
            )

        try:
            return await call_next(context)
        except ValidationError as exc:
            status = "invalid_arguments"
            error_type = "validation_error"
            cause = exc.__cause__
            if isinstance(cause, PydanticValidationError):
                field_paths = _validation_field_paths(cause)
                error_types = sorted({str(error["type"]) for error in cause.errors()})
            else:
                field_paths = ["request"]
                error_types = ["validation_error"]
            log_internal(
                "Tool argument validation failed",
                error_types=error_types,
                field_paths=field_paths,
            )
            raise ToolError(f"Invalid arguments: {', '.join(field_paths)}") from exc
        except _ClassifiedToolError as exc:
            status = exc.status
            error_type = exc.error_type
            field_paths = list(exc.field_paths)
            log_internal(
                "Tool call failed with a classified error",
                field_paths=field_paths,
            )
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            status = "internal_error"
            error_type = "unexpected_exception"
            logger.exception(
                "Unhandled tool error",
                extra={
                    "event": "tool_call_unhandled_error",
                    "tool_name": tool_name,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "exception_type": type(_root_cause(exc)).__name__,
                },
            )
            raise ToolError("Internal error.") from exc
        finally:
            duration_ms = max(0.0, (time.perf_counter() - started) * 1000)
            logger.info(
                "tool_call",
                extra={
                    "event": "tool_call",
                    "tool_name": tool_name,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "duration_ms": round(duration_ms, 3),
                    "status": status,
                    "error_type": error_type,
                    "table": table,
                    "filter_count": filter_count,
                    "field_paths": field_paths,
                },
            )


def _register_tools(mcp: FastMCP, database: Database) -> None:
    @mcp.tool
    @_safe_tool
    def list_tables() -> list[dict[str, Any]]:
        """List the nine catalog entries with row counts.

        The passengers logical view is the recommended starting point for
        analysis; the other entries are the eight raw lookup and observation
        tables.
        """

        return [
            summary.model_dump(mode="json") for summary in queries.list_tables(database)
        ]

    @mcp.tool
    @_safe_tool
    def describe_table(
        table: Annotated[StrictStr, Field(min_length=1)],
    ) -> dict[str, Any]:
        """Describe one catalog table, including columns, types, and nullability."""

        return queries.describe_table(database, table).model_dump(mode="json")

    @mcp.tool
    @_safe_tool
    def query_data(
        table: Annotated[StrictStr, Field(min_length=1)],
        columns: list[StrictStr] | None = None,
        filter: list[FilterPredicate] | None = None,
        order_by: OrderBy | None = None,
        limit: Annotated[StrictInt, Field(ge=1, le=500)] = 100,
        offset: Annotated[StrictInt, Field(ge=0)] = 0,
    ) -> dict[str, Any]:
        """Run a bounded, read-only query.

        The passengers view is the recommended starting point for analysis.
        Columns, filters, ordering, and pagination are validated against the
        catalog before any data is read.
        """

        try:
            request = QueryDataInput(
                table=table,
                columns=columns,
                filter=filter,
                order_by=order_by,
                limit=limit,
                offset=offset,
            )
        except PydanticValidationError as exc:
            raise InvalidArgumentsError(_validation_field_paths(exc)) from exc

        return queries.query_data(database, request).model_dump(mode="json")


def create_app(database: Database | None = None) -> FastMCP:
    """Create the FastMCP application without opening the database."""

    mcp = FastMCP(
        name="titanic-mcp",
        instructions=SERVER_INSTRUCTIONS,
        strict_input_validation=True,
        mask_error_details=True,
        middleware=[ToolCallMiddleware()],
    )
    _register_tools(mcp, database or Database(DEFAULT_DATABASE_PATH))
    return mcp


def http_app(database: Database | None = None) -> Any:
    """Return the minimal ASGI application used by transport seam tests."""

    return create_app(database).http_app()


def main() -> None:
    """Run the MCP server over the default stdio transport."""

    configure_logging()
    create_app().run(transport="stdio")
