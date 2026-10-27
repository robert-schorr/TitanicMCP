from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
from fastmcp import Client

from titanic_mcp.database import Database
from titanic_mcp.server import create_app

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


@pytest.fixture
def mcp_app(database: Database):
    """Return a FastMCP app backed by the project database."""

    return create_app(database)


@pytest.fixture
async def mcp_client(mcp_app) -> AsyncIterator[Client]:
    """Return an initialized in-process MCP client."""

    async with Client(mcp_app) as client:
        yield client


class _RecordingHandler(logging.Handler):
    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self.records = records

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def tool_log_records() -> Iterator[list[logging.LogRecord]]:
    """Capture records emitted by the tool-call middleware."""

    records: list[logging.LogRecord] = []
    handler = _RecordingHandler(records)
    logger = logging.getLogger("titanic_mcp.server")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
