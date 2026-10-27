from __future__ import annotations

import inspect
import sys

from titanic_mcp.errors import QueryValidationError


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


def test_errors_module_has_no_framework_imports() -> None:
    source = inspect.getsource(sys.modules[QueryValidationError.__module__])

    assert "pydantic" not in source
    assert "fastmcp" not in source
    assert "mcp" not in source
