"""Employee portal assessment activity from 2026-10-14 onward (Dev + Live)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import mssql_settings
from core.db import MssqlStore

CUT = "2026-10-14"
PRODUCT_TOPIC = "resource-product-assessment"

SQL = """
SELECT
  COALESCE(NULLIF(LTRIM(RTRIM(t.employee_code)), ''), e.employee_id) AS employee_id,
  e.full_name AS name,
  e.email AS email,
  COALESCE(t.topic_title, t.topic_id) AS assessment,
  t.topic_id,
  t.started_at,
  t.completed_at,
  t.status,
  t.score_percent,
  t.created_at,
  -- UTC calendar day of completed_at
  CONVERT(char(10), CAST(t.completed_at AS date), 23) AS completed_utc_day,
  -- IST calendar day of completed_at (UTC+5:30)
  CONVERT(char(10), CAST(DATEADD(minute, 330, t.completed_at) AS date), 23) AS completed_ist_day,
  CONVERT(char(10), CAST(t.started_at AS date), 23) AS started_utc_day,
  CONVERT(char(10), CAST(DATEADD(minute, 330, t.started_at) AS date), 23) AS started_ist_day
FROM dbo.tests t
LEFT JOIN dbo.employees e
  ON e.id = t.employee_id
  OR (e.employee_id IS NOT NULL AND LTRIM(RTRIM(e.employee_id)) = LTRIM(RTRIM(t.employee_code)))
WHERE
  (
    t.completed_at >= ?
    OR t.started_at >= ?
    OR t.created_at >= ?
  )
ORDER BY COALESCE(t.completed_at, t.started_at, t.created_at)
"""


def is_testemp(emp_id, name, email) -> bool:
    blob = " ".join(str(x or "") for x in (emp_id, name, email)).upper()
    return "TESTEMP" in blob or blob.startswith("TEST") and "EMP" in blob


def run_db(label: str, database: str) -> None:
    os.environ["MSSQL_TARGET"] = "remote"
    os.environ["MSSQL_REMOTE_DATABASE"] = database
    import core.db as dbmod

    dbmod._store = None
    settings = mssql_settings()
    print(f"\n{'=' * 72}")
    print(f"{label}: {settings['server']}/{settings['database']}")
    print("=" * 72)
    store = MssqlStore(settings)
    if not store.ping():
        print("UNREACHABLE")
        return

    rows = store.query(SQL, (CUT, CUT, CUT))
    real = []
    noise = []
    for r in rows:
        bucket = noise if is_testemp(r.get("employee_id"), r.get("name"), r.get("email")) else real
        bucket.append(r)

    def show(title: str, items: list) -> None:
        print(f"\n--- {title} ({len(items)}) ---")
        if not items:
            print("  (none)")
            return
        for r in items:
            print(
                f"  emp={r.get('employee_id')} | {r.get('name')} | {r.get('email')}\n"
                f"    assessment={r.get('assessment')} topic={r.get('topic_id')}\n"
                f"    status={r.get('status')} score={r.get('score_percent')}\n"
                f"    started={r.get('started_at')}  (UTC day {r.get('started_utc_day')} / IST day {r.get('started_ist_day')})\n"
                f"    completed={r.get('completed_at')} (UTC day {r.get('completed_utc_day')} / IST day {r.get('completed_ist_day')})"
            )

    show("REAL employees", real)
    show("TESTEMP / noise", noise)

    # Admin-chart style: one row per employee using primary product assessment completed_at (IST day)
    print("\n--- Admin-style daily counts (product topic, completed, distinct emp, IST day) ---")
    by_day: dict[str, set] = {}
    for r in real:
        if r.get("topic_id") != PRODUCT_TOPIC:
            continue
        if str(r.get("status") or "").lower() != "completed":
            continue
        day = r.get("completed_ist_day")
        if not day:
            continue
        by_day.setdefault(day, set()).add(str(r.get("employee_id") or r.get("name")))
    for day in sorted(by_day):
        emps = sorted(by_day[day])
        print(f"  {day}: {len(emps)} emp -> {', '.join(emps)}")

    print("\n--- Same but UTC completed day ---")
    by_day_utc: dict[str, set] = {}
    for r in real:
        if r.get("topic_id") != PRODUCT_TOPIC:
            continue
        if str(r.get("status") or "").lower() != "completed":
            continue
        day = r.get("completed_utc_day")
        if not day:
            continue
        by_day_utc.setdefault(day, set()).add(str(r.get("employee_id") or r.get("name")))
    for day in sorted(by_day_utc):
        emps = sorted(by_day_utc[day])
        print(f"  {day}: {len(emps)} emp -> {', '.join(emps)}")

    # Also any completed tests (not just product topic)
    print("\n--- All completed tests (any topic), IST day, real only ---")
    by_any: dict[str, list] = {}
    for r in real:
        if str(r.get("status") or "").lower() != "completed":
            continue
        day = r.get("completed_ist_day") or "?"
        by_any.setdefault(day, []).append(
            f"{r.get('employee_id')}:{r.get('name')}:{r.get('topic_id')}"
        )
    for day in sorted(by_any):
        print(f"  {day}: {len(by_any[day])} -> {by_any[day]}")


if __name__ == "__main__":
    run_db("LIVE", "TalentScope_DB_Live")
    run_db("DEV", "TalentScope_DB_Dev")
