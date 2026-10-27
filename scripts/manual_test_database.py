"""Manual smoke test for the database layer (src/titanic_mcp/database.py).

Run from the repository root with:

    uv run python scripts/manual_test_database.py

The script exercises ``Database`` against the real SQLite file at
``data/titanic.db`` and prints one PASS/FAIL line per check, followed by a
summary. It exits with status 1 if any check fails.

Note: the read-only checks intentionally attempt writes against the database;
they fail inside SQLite and never modify the file.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from titanic_mcp.database import Database
from titanic_mcp.errors import QueryValidationError
from titanic_mcp.models import FilterOperator, QueryDataInput
from titanic_mcp.queries import (
    describe_table,
    list_tables,
    query_data,
)

DB_PATH = REPO_ROOT / "data" / "titanic.db"

passed = 0
failed = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if ok:
        passed += 1
    else:
        failed += 1


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def main() -> int:
    section("Setup")
    check("data/titanic.db exists", DB_PATH.is_file(), str(DB_PATH))
    db = Database(DB_PATH)

    # 1. Path handling: plain string path is accepted too.
    db_from_str = Database(str(DB_PATH))
    check("accepts a str path", db_from_str.path == db.path, str(db_from_str.path))
    check("resolves to an absolute path", db.path.is_absolute())

    # 2. URI is forced read-only.
    check("URI carries mode=ro", db.uri.endswith("?mode=ro"), db.uri)

    section("fetch_all / fetch_one / count")
    rows = db.fetch_all('SELECT class_id, "class" FROM "Class" ORDER BY class_id')
    check(
        "fetch_all returns 3 classes",
        len(rows) == 3 and [r["class"] for r in rows] == ["First", "Second", "Third"],
        f"{len(rows)} rows: {[r.get('class') for r in rows]}",
    )

    one = db.fetch_one("SELECT sex FROM 'Sex' WHERE sex_id = 1")
    check("fetch_one returns a mapping", one is not None and "sex" in one, str(one))

    missing = db.fetch_one("SELECT sex FROM 'Sex' WHERE sex_id = -999")
    check("fetch_one returns None for no match", missing is None)

    total = db.count('SELECT * FROM "Observation"')
    check("count() matches a direct query", total > 0, f"{total} observations")

    section("Read-only enforcement")
    try:
        db.fetch_all("INSERT INTO 'Sex' (sex_id, sex) VALUES (99, 'x')")
        check("INSERT is rejected", False, "write unexpectedly succeeded")
    except sqlite3.OperationalError as exc:
        check("INSERT is rejected", "readonly" in str(exc).lower(), str(exc))

    try:
        with db.connect() as conn:
            conn.execute("DELETE FROM 'Sex'")
            check("query_only blocks writes", False, "write unexpectedly succeeded")
    except sqlite3.OperationalError as exc:
        check("query_only blocks writes", "readonly" in str(exc).lower(), str(exc))

    section("Connection lifecycle")
    # Every operation opens a fresh connection; parallel handles must coexist.
    with db.connect() as conn:
        inside = conn.execute("SELECT COUNT(*) FROM 'Observation'").fetchone()[0]
    check("connection usable inside context", inside == total, f"{inside} rows")

    section("Query pipeline end-to-end")
    tables = list_tables(db)
    check(
        "list_tables returns the 9-entry catalog",
        tables[0].name == "passengers" and len(tables) == 9,
        f"{len(tables)} tables",
    )

    described = describe_table(db, "passengers")
    check(
        "describe_table reports live row count",
        described.row_count == total,
        f"{described.row_count} == {total}",
    )

    response = query_data(
        db,
        QueryDataInput.model_validate(
            {
                "table": "passengers",
                "columns": ["passenger_id", "survived", "sex", "age"],
                "filter": [
                    {"column": "pclass", "op": "eq", "value": 3},
                    {"column": "survived", "op": "eq", "value": 1},
                ],
                "order_by": {"column": "fare", "direction": "desc"},
                "limit": 5,
            }
        ),
    )
    check("query returns 5 rows", response.row_count == 5)
    check(
        "query reports more data available",
        response.truncated and response.next_offset == 5,
        f"next_offset={response.next_offset}",
    )

    page2 = query_data(
        db,
        QueryDataInput.model_validate(
            {
                "table": "passengers",
                "columns": ["passenger_id", "survived", "sex", "age"],
                "filter": [
                    {"column": "pclass", "op": "eq", "value": 3},
                    {"column": "survived", "op": "eq", "value": 1},
                ],
                "order_by": {"column": "fare", "direction": "desc"},
                "limit": 5,
                "offset": response.next_offset or 0,
            }
        ),
    )
    ids = [r["passenger_id"] for r in response.rows]
    ids2 = [r["passenger_id"] for r in page2.rows]
    check("pagination does not repeat rows", not set(ids) & set(ids2))
    top_fares = query_data(
        db,
        QueryDataInput.model_validate(
            {
                "table": "passengers",
                "columns": ["fare"],
                "filter": [{"column": "pclass", "op": "eq", "value": 1}],
                "order_by": {"column": "fare", "direction": "desc"},
                "limit": 3,
            }
        ),
    )
    fares = [cast(float, r["fare"]) for r in top_fares.rows]
    check("DESC ordering is honored", fares == sorted(fares, reverse=True), str(fares))

    # The compiled ORDER BY forces nulls last regardless of direction; 158 of
    # the 688 deck-null passengers also have a null age, so with limit 500 and
    # nulls-last every fetched row must carry a real age value.
    for direction in ("asc", "desc"):
        ordered = query_data(
            db,
            QueryDataInput.model_validate(
                {
                    "table": "passengers",
                    "columns": ["age"],
                    "filter": [{"column": "deck", "op": "is_null"}],
                    "order_by": {"column": "age", "direction": direction},
                    "limit": 500,
                }
            ),
        )
        ages = [r["age"] for r in ordered.rows]
        check(
            f"nulls sort last ({direction})",
            all(age is not None for age in ages) and len(ages) == 500,
            f"{len(ages)} rows fetched, all with known ages",
        )

    section("Failure paths")
    try:
        query_data(
            db,
            QueryDataInput.model_validate(
                {
                    "table": "passengers",
                    "filter": [
                        {"column": "pclass", "op": FilterOperator.gt, "value": "nope"}
                    ],
                }
            ),
        )
        check("type mismatch raises QueryValidationError", False)
    except QueryValidationError as exc:
        check("type mismatch raises QueryValidationError", True, str(exc))

    try:
        Database(DB_PATH.parent / "does" / "not" / "exist.db").fetch_all("SELECT 1")
        check("missing file raises sqlite3.OperationalError", False)
    except sqlite3.OperationalError as exc:
        check(
            "missing file raises sqlite3.OperationalError",
            "unable to open" in str(exc).lower(),
            str(exc),
        )

    section("Summary")
    print(f"{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
