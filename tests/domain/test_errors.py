from __future__ import annotations

import inspect
import sys

from titanic_mcp.errors import (
    InvalidArgumentsError,
    QueryValidationError,
    SafeToolError,
)


def test_field_paths_are_normalized_and_deduplicated() -> None:
    error = QueryValidationError(
        [" filter[1].op ", "", "filter[0].value", "filter[1].op"],
        "operator is not allowed",
    )

    assert error.field_paths == ("filter[0].value", "filter[1].op")
    assert str(error) == "Invalid arguments: filter[0].value, filter[1].op"
    assert error.detail == "operator is not allowed"


def test_string_field_path_is_accepted() -> None:
    error = QueryValidationError("  table  ", "unknown table")

    assert error.field_paths == ("table",)
    assert str(error) == "Invalid arguments: table"


def test_blank_paths_fall_back_to_request() -> None:
    error = QueryValidationError(["", "   "], "unlocatable error")

    assert error.field_paths == ("request",)
    assert str(error) == "Invalid arguments: request"


def test_detail_is_not_part_of_the_safe_string() -> None:
    error = QueryValidationError("filter[0].value", "value 'secret' is invalid")

    assert "secret" not in str(error)
    assert "secret" not in repr(error)
    assert error.detail == "value 'secret' is invalid"


def test_invalid_arguments_error_uses_the_safe_path_format() -> None:
    error = InvalidArgumentsError([" limit ", "filter[0].op", "limit"])

    assert error.field_paths == ("filter[0].op", "limit")
    assert str(error) == "Invalid arguments: filter[0].op, limit"
    assert error.detail == "Invalid tool arguments."


def test_invalid_arguments_error_falls_back_to_request() -> None:
    error = InvalidArgumentsError([])

    assert error.field_paths == ("request",)
    assert str(error) == "Invalid arguments: request"


def test_safe_tool_error_exposes_only_its_safe_message() -> None:
    error = SafeToolError("The catalog is unavailable.")

    assert str(error) == "The catalog is unavailable."
    assert "unavailable" in repr(error)


def test_errors_module_has_no_framework_imports() -> None:
    source = inspect.getsource(sys.modules[QueryValidationError.__module__])

    assert "pydantic" not in source
    assert "fastmcp" not in source
    assert "mcp" not in source
