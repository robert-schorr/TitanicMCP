from __future__ import annotations

from collections.abc import Iterable


class QueryValidationError(ValueError):
    """Raised when a query request violates the core's semantic rules.

    The detail is kept for internal diagnostics, but the string form is safe to
    show to clients because it only contains normalized field paths.
    """

    def __init__(self, field_paths: str | Iterable[str], detail: str) -> None:
        self.field_paths = _normalize_field_paths(field_paths)
        self.detail = detail
        super().__init__(self._safe_message())

    def _safe_message(self) -> str:
        return f"Invalid arguments: {', '.join(self.field_paths)}"

    def __str__(self) -> str:
        return self._safe_message()


def _normalize_field_paths(field_paths: str | Iterable[str]) -> tuple[str, ...]:
    candidates = [field_paths] if isinstance(field_paths, str) else list(field_paths)
    cleaned = {path.strip() for path in candidates if path and path.strip()}
    return tuple(sorted(cleaned)) or ("request",)
