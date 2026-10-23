"""Reconcile admin Completed-On daily emp counts vs DB after 2026-10-14."""
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import mssql_settings
from core.db import MssqlStore

CUT = "2026-10-14"
PRODUCT = "resource-product-assessment"


def store_for(database: str) -> MssqlStore:
    os.environ["MSSQL_TARGET"] = "remote"
    os.environ["MSSQL_REMOTE_DATABASE"] = database
    import core.db as dbmod

    dbmod._store = None
    return MssqlStore(mssql_settings())


def is_noise(emp_id, name, email) -> bool:
    blob = " ".join(str(x or "") for x in (emp_id, name, email)).upper()
    return "TESTEMP" in blob


SQL_ACTIVITY = """
SELECT
  COALESCE(NULLIF(LTRIM(RTRIM(t.employee_code)), ''), e.employee_id) AS employee_id,
  e.full_name AS name,
  e.email AS email,
  e.product_qb_eligible AS qb_eligible,
  COALESCE(t.topic_title, t.topic_id) AS assessment,
  t.topic_id,
  t.status,
  t.started_at,
  t.completed_at,
  t.created_at,
  CONVERT(char(10), CAST(DATEADD(minute, 330, t.completed_at) AS date), 23) AS completed_ist_day,
  CONVERT(char(10), CAST(t.completed_at AS date), 23) AS completed_utc_day
FROM dbo.tests t
LEFT JOIN dbo.employees e
  ON e.id = t.employee_id
  OR (e.employee_id IS NOT NULL AND LTRIM(RTRIM(e.employee_id)) = LTRIM(RTRIM(t.employee_code)))
WHERE t.completed_at >= ?
   OR t.started_at >= ?
   OR (t.created_at >= ? AND t.status = 'completed')
ORDER BY COALESCE(t.completed_at, t.started_at, t.created_at)
"""

# Current live product assessment per employee (what admin primary prefers)
SQL_CURRENT_PRODUCT = """
SELECT
  COALESCE(NULLIF(LTRIM(RTRIM(t.employee_code)), ''), e.employee_id) AS employee_id,
  e.full_name AS name,
  e.email AS email,
  e.product_qb_eligible AS qb_eligible,
  t.status,
  t.started_at,
  t.completed_at,
  CONVERT(char(10), CAST(DATEADD(minute, 330, t.completed_at) AS date), 23) AS completed_ist_day,
  CONVERT(char(10), CAST(t.completed_at AS date), 23) AS completed_utc_day,
  t.score_percent
FROM dbo.tests t
LEFT JOIN dbo.employees e
  ON e.id = t.employee_id
  OR (e.employee_id IS NOT NULL AND LTRIM(RTRIM(e.employee_id)) = LTRIM(RTRIM(t.employee_code)))
WHERE t.topic_id = ?
  AND t.completed_at >= ?
ORDER BY t.completed_at
"""


def run(label: str, database: str) -> None:
    print(f"\n{'=' * 72}\n{label}: {database}\n{'=' * 72}")
    store = store_for(database)
    if not store.ping():
        print("UNREACHABLE")
        return

    rows = store.query(SQL_ACTIVITY, (CUT, CUT, CUT))
    current = store.query(SQL_CURRENT_PRODUCT, (PRODUCT, CUT))

    print(f"\nRows with any activity since {CUT}: {len(rows)}")
    print(f"Current product-topic completions since {CUT}: {len(current)}")

    print("\n## CURRENT product assessments completed (admin primary / Completed On)")
    by_ist = defaultdict(list)
    by_utc = defaultdict(list)
    for r in current:
        noise = " [TESTEMP]" if is_noise(r.get("employee_id"), r.get("name"), r.get("email")) else ""
        qb = r.get("qb_eligible")
        line = (
            f"{r.get('employee_id')} | {r.get('name')} | {r.get('email')} | "
            f"status={r.get('status')} score={r.get('score_percent')} qb={qb}{noise}\n"
            f"    completed={r.get('completed_at')} IST={r.get('completed_ist_day')} UTC={r.get('completed_utc_day')}"
        )
        print("  " + line)
        if r.get("completed_ist_day"):
            by_ist[r["completed_ist_day"]].append(f"{r.get('employee_id')}{noise}")
        if r.get("completed_utc_day"):
            by_utc[r["completed_utc_day"]].append(f"{r.get('employee_id')}{noise}")

    print("\n## Daily distinct emp (current product completed) — IST (browser India)")
    for day in sorted(by_ist):
        print(f"  {day}: {len(set(by_ist[day]))} -> {sorted(set(by_ist[day]))}")
    print("\n## Daily distinct emp (current product completed) — UTC")
    for day in sorted(by_utc):
        print(f"  {day}: {len(set(by_utc[day]))} -> {sorted(set(by_utc[day]))}")

    print("\n## History-topic completions since cut (resets; NOT admin primary if current pending)")
    hist = [
        r
        for r in rows
        if str(r.get("topic_id") or "").startswith(PRODUCT + "-history")
        and str(r.get("status") or "").lower() == "completed"
        and r.get("completed_at")
    ]
    for r in hist:
        noise = " [TESTEMP]" if is_noise(r.get("employee_id"), r.get("name"), r.get("email")) else ""
        print(
            f"  {r.get('completed_ist_day')} IST | {r.get('employee_id')} | {r.get('name')} | "
            f"{r.get('assessment')}{noise}\n"
            f"    completed={r.get('completed_at')}"
        )

    print("\n## Named people of interest (any topic)")
    names = ("megha", "danish", "aryaman", "gudla", "testemp")
    for r in rows:
        blob = " ".join(str(x or "") for x in (r.get("employee_id"), r.get("name"), r.get("email"))).lower()
        if not any(n in blob for n in names):
            continue
        print(
            f"  {r.get('employee_id')} | {r.get('name')} | topic={r.get('topic_id')} | "
            f"status={r.get('status')} | completed={r.get('completed_at')} | "
            f"IST={r.get('completed_ist_day')} qb={r.get('qb_eligible')}"
        )

    # Count completed product for qb_eligible only (portal roster filter)
    print("\n## Admin portal-eligible only (product_qb_eligible=1, current product completed, IST)")
    eligible_days = defaultdict(set)
    for r in current:
        if not r.get("qb_eligible"):
            continue
        day = r.get("completed_ist_day")
        if day:
            tag = str(r.get("employee_id"))
            if is_noise(r.get("employee_id"), r.get("name"), r.get("email")):
                tag += "[TESTEMP]"
            eligible_days[day].add(tag)
    for day in sorted(eligible_days):
        print(f"  {day}: {len(eligible_days[day])} -> {sorted(eligible_days[day])}")


if __name__ == "__main__":
    run("LIVE", "TalentScope_DB_Live")
    run("DEV", "TalentScope_DB_Dev")
