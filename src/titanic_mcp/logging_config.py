from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

_LOG_RECORD_ATTRIBUTES = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    """Serialize log records as single-line JSON objects on stderr."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_ATTRIBUTES or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            exception_type, exception, exception_traceback = record.exc_info
            payload["exception"] = {
                "type": exception_type.__name__ if exception_type else None,
                "message": str(exception) if exception is not None else None,
                "traceback": "".join(
                    traceback.format_exception(
                        exception_type,
                        exception,
                        exception_traceback,
                    )
                ),
            }

        return json.dumps(payload, default=str, ensure_ascii=False)


class DropFastMCPValidationWarning(logging.Filter):
    """Drop FastMCP's duplicate raw validation warning.

    The tool-call middleware emits the canonical safe record instead. The
    filter is intentionally narrow so other FastMCP diagnostics stay visible.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not (
            record.name.startswith("fastmcp")
            and record.getMessage().startswith("Invalid arguments for tool")
        )


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure application logging once, without FastMCP's own handlers."""

    import fastmcp

    fastmcp.settings.log_enabled = False
    fastmcp_logger = logging.getLogger("fastmcp")
    fastmcp_logger.handlers.clear()
    fastmcp_logger.propagate = True
    fastmcp_logger.setLevel(logging.NOTSET)

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(DropFastMCPValidationWarning())
    handler.setFormatter(
        JsonFormatter()
        if json_output
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
