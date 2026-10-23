"""Count rows created/updated after 2026-10-14 (and 2025-10-14 for safety)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import mssql_settings
from core.db import MssqlStore

CUTS = ["2026-10-14", "2025-10-14"]

# table -> date column used for "gone in" (new activity)
CHECKS = [
    ("employees", "created_at"),
    ("resumes", "created_at"),
    ("job_descriptions", "created_at"),
    ("candidate_sessions", "created_at"),
    ("interview_attempts", "created_at"),
    ("interview_questions", "created_at"),
    ("tests", "created_at"),
    ("test_attempts", "created_at"),
    ("evaluations", "created_at"),
    ("simulated_emails", "created_at"),
    ("audit_logs", "created_at"),
    ("reset_logs", "created_at"),
    ("behavior_evaluations", "submitted_at"),
    ("business_impacts", "created_at"),
    ("candidate_interview_data", "created_at"),
]


def count_after(store: MssqlStore, table: str, col: str, cut: str) -> int | None:
    try:
        rows = store.query(
            f"SELECT COUNT(*) AS n FROM dbo.[{table}] WHERE [{col}] >= ?",
            (cut,),
        )
        return int(rows[0]["n"]) if rows else 0
    except Exception as err:
        print(f"  FAIL {table}.{col}: {err}")
        return None


def totals(store: MssqlStore, table: str) -> int | None:
    try:
        rows = store.query(f"SELECT COUNT(*) AS n FROM dbo.[{table}]")
        return int(rows[0]["n"]) if rows else 0
    except Exception:
        return None


def run_db(label: str, database: str) -> None:
    os.environ["MSSQL_TARGET"] = "remote"
    os.environ["MSSQL_REMOTE_DATABASE"] = database
    # reset store singleton
    import core.db as dbmod

    dbmod._store = None
    settings = mssql_settings()
    print(f"\n=== {label}: {settings['server']}/{settings['database']} ===")
    store = MssqlStore(settings)
    if not store.ping():
        print("UNREACHABLE")
        return

    for cut in CUTS:
        print(f"\nAfter {cut} (inclusive):")
        grand = 0
        for table, col in CHECKS:
            n = count_after(store, table, col, cut)
            total = totals(store, table)
            if n is None:
                continue
            grand += n
            if n or (total and total > 0):
                print(f"  {table:28} +{n:6}  (total {total})")
        print(f"  {'SUM (listed tables)':28} +{grand:6}")

    # Also: employee portal logins via audit after cut
    print("\nAudit log actions after 2026-10-14 (top):")
    try:
        rows = store.query(
            """
            SELECT TOP 20 action, COUNT(*) AS n
            FROM dbo.audit_logs
            WHERE created_at >= ?
            GROUP BY action
            ORDER BY n DESC
            """,
            ("2026-10-14",),
        )
        for r in rows:
            print(f"  {r['action']}: {r['n']}")
    except Exception as err:
        print("  audit breakdown failed:", err)


if __name__ == "__main__":
    run_db("LIVE", "TalentScope_DB_Live")
    run_db("DEV", "TalentScope_DB_Dev")
