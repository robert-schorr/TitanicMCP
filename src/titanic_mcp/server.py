from __future__ import annotations

import ipaddress
import logging
import os
import sqlite3
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.server.auth import StaticTokenVerifier
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.http import HostOriginProtection
from fastmcp.server.middleware import Middleware, MiddlewareContext
from pydantic import Field, StrictInt, StrictStr
from pydantic import ValidationError as PydanticValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import queries
from .database import Database
from .errors import InvalidArgumentsError, QueryValidationError, SafeToolError
from .logging_config import configure_logging
from .models import FilterPredicate, OrderBy, QueryDataInput

logger = logging.getLogger("titanic_mcp.server")

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "titanic.db"

Profile = Literal["local", "container", "remote"]
LogFormat = Literal["json", "text"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_CONTAINER_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_PROFILE: Profile = "local"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT: LogFormat = "json"
MCP_PATH = "/mcp"
HEALTH_PATH = "/healthz"


class ConfigurationError(ValueError):
    """Raised when startup configuration is inconsistent or incomplete."""


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Resolved server configuration with safe local defaults."""

    database_path: Path = DEFAULT_DATABASE_PATH
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    profile: Profile = DEFAULT_PROFILE
    auth_token: str | None = field(default=None, repr=False)
    allowed_hosts: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = ()
    log_level: str = DEFAULT_LOG_LEVEL
    log_format: LogFormat = DEFAULT_LOG_FORMAT

    @property
    def stateless_http(self) -> bool:
        """Stateless requests are the local default; sessions remain opt-in."""

        return self.profile == "local"

    @property
    def host_origin_protection(self) -> HostOriginProtection:
        """Use automatic loopback protection locally and strict protection elsewhere."""

        return "auto" if self.profile == "local" else True


def _optional(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_profile(value: str) -> Profile:
    if value not in ("local", "container", "remote"):
        raise ConfigurationError(
            f"MCP_PROFILE must be 'local', 'container', or 'remote'; got {value!r}."
        )
    return value


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ConfigurationError(
            f"TITANIC_MCP_PORT must be an integer; got {value!r}."
        ) from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError(
            f"TITANIC_MCP_PORT must be between 1 and 65535; got {port}."
        )
    return port


def _parse_log_level(value: str) -> str:
    level = value.upper()
    if level not in logging.getLevelNamesMapping():
        raise ConfigurationError(
            f"TITANIC_MCP_LOG_LEVEL is not a known logging level: {value!r}."
        )
    return level


def _parse_log_format(value: str) -> LogFormat:
    log_format = value.lower()
    if log_format not in ("json", "text"):
        raise ConfigurationError(
            f"TITANIC_MCP_LOG_FORMAT must be 'json' or 'text'; got {value!r}."
        )
    return log_format


def _parse_allowlist(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(entry.strip() for entry in value.split(",") if entry.strip())


def _is_loopback(host: str) -> bool:
    candidate = host.strip().lower()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    if candidate == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def validate_config(config: ServerConfig) -> ServerConfig:
    """Reject contradictory profile combinations before the app starts."""

    if config.profile == "local" and not _is_loopback(config.host):
        raise ConfigurationError(
            "MCP_PROFILE=local requires a loopback TITANIC_MCP_HOST; "
            f"got {config.host!r}."
        )

    if config.profile == "container" and not config.allowed_hosts:
        raise ConfigurationError("MCP_PROFILE=container requires MCP_ALLOWED_HOSTS.")

    if config.profile == "remote":
        missing: list[str] = []
        if not config.auth_token:
            missing.append("MCP_AUTH_TOKEN")
        if not config.allowed_hosts:
            missing.append("MCP_ALLOWED_HOSTS")
        if missing:
            raise ConfigurationError(
                f"MCP_PROFILE=remote requires {' and '.join(missing)}."
            )

    return config


def load_config(environ: Mapping[str, str] | None = None) -> ServerConfig:
    """Load and validate configuration from environment variables.

    Defaults: ``TITANIC_MCP_DB_PATH=data/titanic.db``, loopback host for
    ``local`` (``0.0.0.0`` for ``container`` and ``remote``), port ``8000``,
    profile ``local``, no token, no extra allowed hosts/origins, log level
    ``INFO``, and JSON logs.
    """

    source = os.environ if environ is None else environ
    profile = _parse_profile(
        (_optional(source, "MCP_PROFILE") or DEFAULT_PROFILE).lower()
    )
    default_host = DEFAULT_HOST if profile == "local" else DEFAULT_CONTAINER_HOST
    host = _optional(source, "TITANIC_MCP_HOST") or default_host
    port = _parse_port(_optional(source, "TITANIC_MCP_PORT") or str(DEFAULT_PORT))
    database_path = Path(
        _optional(source, "TITANIC_MCP_DB_PATH") or DEFAULT_DATABASE_PATH
    )
    log_level = _parse_log_level(
        _optional(source, "TITANIC_MCP_LOG_LEVEL") or DEFAULT_LOG_LEVEL
    )
    log_format = _parse_log_format(
        _optional(source, "TITANIC_MCP_LOG_FORMAT") or DEFAULT_LOG_FORMAT
    )

    return validate_config(
        ServerConfig(
            database_path=database_path,
            host=host,
            port=port,
            profile=profile,
            auth_token=_optional(source, "MCP_AUTH_TOKEN"),
            allowed_hosts=_parse_allowlist(source.get("MCP_ALLOWED_HOSTS")),
            allowed_origins=_parse_allowlist(source.get("MCP_ALLOWED_ORIGINS")),
            log_level=log_level,
            log_format=log_format,
        )
    )


def default_config() -> ServerConfig:
    """Return the default local configuration without reading the environment."""

    return load_config({})


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


async def _healthz(_: Request) -> JSONResponse:
    """Report readiness without requiring MCP initialization or authentication."""

    return JSONResponse({"status": "ok"})


def _auth_provider(config: ServerConfig) -> StaticTokenVerifier | None:
    if not config.auth_token:
        return None
    return StaticTokenVerifier(
        tokens={
            config.auth_token: {
                "client_id": "titanic-mcp",
                "scopes": [],
            }
        }
    )


def create_app(
    database: Database | None = None,
    config: ServerConfig | None = None,
) -> FastMCP:
    """Create the FastMCP application without opening the database."""

    resolved = validate_config(config or default_config())
    mcp = FastMCP(
        name="titanic-mcp",
        instructions=SERVER_INSTRUCTIONS,
        strict_input_validation=True,
        mask_error_details=True,
        auth=_auth_provider(resolved),
        middleware=[ToolCallMiddleware()],
    )
    mcp.custom_route(HEALTH_PATH, methods=["GET"], name="healthz")(_healthz)
    _register_tools(mcp, database or Database(resolved.database_path))
    return mcp


def http_app(
    database: Database | None = None,
    config: ServerConfig | None = None,
) -> Any:
    """Return the Streamable HTTP ASGI application for the selected profile."""

    resolved = validate_config(config or default_config())
    return create_app(database, resolved).http_app(
        path=MCP_PATH,
        stateless_http=resolved.stateless_http,
        host_origin_protection=resolved.host_origin_protection,
        allowed_hosts=list(resolved.allowed_hosts) or None,
        allowed_origins=list(resolved.allowed_origins) or None,
    )


def main() -> None:
    """Run the MCP server over Streamable HTTP."""

    try:
        config = load_config()
    except ConfigurationError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    try:
        Database(config.database_path).fetch_one("SELECT 1")
    except (OSError, sqlite3.Error) as exc:
        raise SystemExit(
            f"Configuration error: database is not readable: {config.database_path}"
        ) from exc

    configure_logging(
        level=config.log_level,
        json_output=config.log_format == "json",
    )
    create_app(config=config).run(
        transport="http",
        host=config.host,
        port=config.port,
        path=MCP_PATH,
        stateless_http=config.stateless_http,
        host_origin_protection=config.host_origin_protection,
        allowed_hosts=list(config.allowed_hosts) or None,
        allowed_origins=list(config.allowed_origins) or None,
        show_banner=False,
    )
