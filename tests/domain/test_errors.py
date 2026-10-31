from __future__ import annotations

import inspect
import sys

from titanic_mcp.errors import (
    InvalidArgumentsError,
    QueryValidationError,
)


def test_field_paths_are_normalized_and_deduplicated() -> None:
    error = QueryValidationError(
        [" filter[1].op ", "", "filter[0].value", "filter[1].op"],
    )

    assert error.field_paths == ("filter[0].value", "filter[1].op")
    assert str(error) == "Invalid arguments: filter[0].value, filter[1].op"


def test_string_field_path_is_accepted() -> None:
    error = QueryValidationError("  table  ")

    assert error.field_paths == ("table",)
    assert str(error) == "Invalid arguments: table"


def test_blank_paths_fall_back_to_request() -> None:
    error = QueryValidationError(["", "   "])

    assert error.field_paths == ("request",)
    assert str(error) == "Invalid arguments: request"


def test_invalid_arguments_error_uses_the_safe_path_format() -> None:
    error = InvalidArgumentsError([" limit ", "filter[0].op", "limit"])

    assert error.field_paths == ("filter[0].op", "limit")
    assert str(error) == "Invalid arguments: filter[0].op, limit"


def test_invalid_arguments_error_falls_back_to_request() -> None:
    error = InvalidArgumentsError([])

    assert error.field_paths == ("request",)
    assert str(error) == "Invalid arguments: request"


def test_errors_module_has_no_framework_imports() -> None:
    source = inspect.getsource(sys.modules[QueryValidationError.__module__])

    assert "pydantic" not in source
    assert "fastmcp" not in source
    assert "mcp" not in source
