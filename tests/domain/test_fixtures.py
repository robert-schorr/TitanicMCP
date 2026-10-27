from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def test_database_path_exists(db_path: Path) -> None:
    assert db_path.is_file()


def test_database_hash_is_stable(database_hash: Callable[[], str]) -> None:
    digest = database_hash()

    assert len(digest) == 64
    assert digest == database_hash()
