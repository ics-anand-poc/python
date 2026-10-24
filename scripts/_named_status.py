import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import mssql_settings
from core.db import MssqlStore

IDS = ("1040066", "1034853", "1040783", "1042494")


def run(database: str) -> None:
    os.environ["MSSQL_TARGET"] = "remote"
    os.environ["MSSQL_REMOTE_DATABASE"] = database
    import core.db as dbmod

    dbmod._store = None
    store = MssqlStore(mssql_settings())
    print(f"\n=== {database} ===")
    rows = store.query(
        """
        SELECT
          COALESCE(NULLIF(LTRIM(RTRIM(t.employee_code)), ''), e.employee_id) AS emp,
          e.full_name AS name,
          t.topic_id,
          t.status,
          t.completed_at,
          t.started_at,
          t.created_at
        FROM dbo.tests t
        LEFT JOIN dbo.employees e
          ON e.id = t.employee_id
          OR LTRIM(RTRIM(e.employee_id)) = LTRIM(RTRIM(t.employee_code))
        WHERE e.employee_id IN (?, ?, ?, ?)
           OR t.employee_code IN (?, ?, ?, ?)
        ORDER BY emp, COALESCE(t.completed_at, t.created_at)
        """,
        IDS + IDS,
    )
    for r in rows:
        print(
            f"  {r.get('emp')} | {r.get('name')} | {r.get('topic_id')} | "
            f"{r.get('status')} | completed={r.get('completed_at')} | created={r.get('created_at')}"
        )
    completed = store.query(
        "SELECT COUNT(*) AS n FROM dbo.tests WHERE status = 'completed' AND completed_at >= ?",
        ("2026-10-14",),
    )[0]["n"]
    created = store.query(
        "SELECT COUNT(*) AS n FROM dbo.tests WHERE created_at >= ?",
        ("2026-10-14",),
    )[0]["n"]
    print(f"  completed_since_cut={completed} created_since_cut={created}")


if __name__ == "__main__":
    run("TalentScope_DB_Live")
    run("TalentScope_DB_Dev")
