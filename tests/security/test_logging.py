from __future__ import annotations

import json
import logging
import sys
from typing import Any

import fastmcp

from titanic_mcp.logging_config import (
    DropFastMCPValidationWarning,
    JsonFormatter,
    configure_logging,
)


def _record(
    message: str = "hello",
    *,
    level: int = logging.INFO,
    exc_info: Any = None,
) -> logging.LogRecord:
    return logging.LogRecord(
        name="titanic_mcp.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


def test_json_formatter_includes_required_fields() -> None:
    record = _record("tool_call")
    record.event = "tool_call"
    record.tool_name = "list_tables"
    record.request_id = "request-1"
    record.correlation_id = None
    record.duration_ms = 12.5
    record.status = "ok"
    record.error_type = "none"
    record.table = None
    record.filter_count = 0
    record.field_paths = []

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "titanic_mcp.test"
    assert payload["message"] == "tool_call"
    assert payload["event"] == "tool_call"
    assert payload["tool_name"] == "list_tables"
    assert payload["request_id"] == "request-1"
    assert payload["correlation_id"] is None
    assert payload["duration_ms"] == 12.5
    assert payload["status"] == "ok"
    assert payload["error_type"] == "none"
    assert payload["table"] is None
    assert payload["filter_count"] == 0
    assert payload["field_paths"] == []
    assert payload["timestamp"].endswith("Z")


def test_json_formatter_serializes_exceptions() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record("failed", level=logging.ERROR, exc_info=sys.exc_info())

    payload = json.loads(JsonFormatter().format(record))
    exception = payload["exception"]

    assert exception["type"] == "ValueError"
    assert exception["message"] == "boom"
    assert "ValueError: boom" in exception["traceback"]


def test_duplicate_validation_warning_filter_is_narrow() -> None:
    warning_filter = DropFastMCPValidationWarning()
    duplicate = logging.LogRecord(
        name="fastmcp.server.server",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Invalid arguments for tool %r: %s",
        args=("query_data", {}),
        exc_info=None,
    )
    other_fastmcp = logging.LogRecord(
        name="fastmcp.server.server",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Starting server",
        args=(),
        exc_info=None,
    )
    other_logger = logging.LogRecord(
        name="titanic_mcp.server",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Invalid arguments for tool query_data",
        args=(),
        exc_info=None,
    )

    assert warning_filter.filter(duplicate) is False
    assert warning_filter.filter(other_fastmcp) is True
    assert warning_filter.filter(other_logger) is True


def test_configure_logging_sets_json_handler_and_disables_fastmcp_logging(
    capsys: Any,
) -> None:
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    fastmcp_logger = logging.getLogger("fastmcp")
    previous_propagate = fastmcp_logger.propagate
    previous_fastmcp_level = fastmcp_logger.level
    previous_log_enabled = fastmcp.settings.log_enabled

    try:
        configure_logging("INFO", json_output=True)
        logging.getLogger("titanic_mcp.test").info(
            "configured", extra={"event": "configuration_test"}
        )

        captured = capsys.readouterr().err
        payload = json.loads(captured.strip().splitlines()[-1])
        assert payload["message"] == "configured"
        assert payload["event"] == "configuration_test"
        assert fastmcp.settings.log_enabled is False
        assert fastmcp_logger.propagate is True
        assert any(
            isinstance(item, DropFastMCPValidationWarning)
            for item in root.handlers[0].filters
        )
    finally:
        root.handlers[:] = previous_handlers
        root.setLevel(previous_level)
        fastmcp_logger.propagate = previous_propagate
        fastmcp_logger.setLevel(previous_fastmcp_level)
        fastmcp.settings.log_enabled = previous_log_enabled
