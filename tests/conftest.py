from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from titanic_mcp.database import Database

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "titanic.db"


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the repository root."""

    return PROJECT_ROOT


@pytest.fixture(scope="session")
def db_path() -> Path:
    """Return the Titanic SQLite database path."""

    return DATABASE_PATH


@pytest.fixture
def database(db_path: Path) -> Database:
    """Return a read-only database wrapper for the Titanic data."""

    return Database(db_path)


@pytest.fixture
def database_hash() -> Callable[[], str]:
    """Return a callable that hashes the database file with SHA-256."""

    def hash_database() -> str:
        return hashlib.sha256(DATABASE_PATH.read_bytes()).hexdigest()

    return hash_database
