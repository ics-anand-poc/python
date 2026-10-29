"""Check TPM upskilling assessment status vs email claim list."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import mssql_settings
from core.db import MssqlStore, set_store

# From Shruti's mail
COMPLETED_CLAIMED = ["1037289", "1043140", "1036625"]
MUKESH = "1040695"
SAMPLE_NOT_STARTED = [
    "1040695",  # Mukesh - claims completed
    "1035040",
    "1036337",
    "1038104",
    "1040593",
    "1039587",
    "1037757",
]


def run(db_name: str, ids: list[str]) -> None:
    os.environ["MSSQL_REMOTE_DATABASE"] = db_name
    # Rebuild settings from env
    import importlib
    import core.config as cfg
    import core.db as dbmod

    importlib.reload(cfg)
    s = cfg.mssql_settings()
    print(f"\n=== {s['database']} @ {s['server']} ===")
    store = MssqlStore(s)
    set_store(store)

    placeholders = ",".join(["?"] * len(ids))
    emps = store.query(
        f"""
        SELECT employee_id, full_name, email, product, product_qb_eligible, assessment_only, role
        FROM employees
        WHERE employee_id IN ({placeholders})
        ORDER BY employee_id
        """,
        ids,
    )
    print(f"employees matched: {len(emps)}")
    for e in emps:
        print(
            f"  EMP {e['employee_id']} | {e.get('full_name')} | {e.get('email')} | "
            f"product={e.get('product')} qb={e.get('product_qb_eligible')} ao={e.get('assessment_only')}"
        )

    tests = store.query(
        f"""
        SELECT t.employee_id, t.id AS test_id, t.title, t.status, t.score,
               t.started_at, t.completed_at, t.created_at,
               (SELECT COUNT(*) FROM test_questions tq WHERE tq.test_id = t.id) AS qcount
        FROM tests t
        WHERE t.employee_id IN ({placeholders})
        ORDER BY t.employee_id, t.created_at DESC
        """,
        ids,
    )
    print(f"tests matched: {len(tests)}")
    for t in tests:
        print(
            f"  TEST emp={t['employee_id']} id={t['test_id']} status={t['status']} "
            f"score={t.get('score')} q={t.get('qcount')} title={str(t.get('title') or '')[:60]} "
            f"started={t.get('started_at')} completed={t.get('completed_at')}"
        )

    # Aggregate TPM-like: product upskilling / title contains Upskilling
    agg = store.query(
        """
        SELECT
          CASE
            WHEN LOWER(ISNULL(t.status,'')) IN ('completed','submitted','passed','failed') THEN 'completed'
            WHEN LOWER(ISNULL(t.status,'')) IN ('in_progress','started','active')
                 OR t.started_at IS NOT NULL THEN 'in_progress'
            ELSE 'not_started'
          END AS bucket,
          COUNT(*) AS cnt
        FROM tests t
        INNER JOIN employees e ON e.employee_id = t.employee_id
        WHERE (
          LOWER(ISNULL(t.title,'')) LIKE '%upskilling%'
          OR LOWER(ISNULL(e.product,'')) LIKE '%upskilling%'
          OR LOWER(ISNULL(e.product,'')) LIKE '%tpm%'
        )
        GROUP BY
          CASE
            WHEN LOWER(ISNULL(t.status,'')) IN ('completed','submitted','passed','failed') THEN 'completed'
            WHEN LOWER(ISNULL(t.status,'')) IN ('in_progress','started','active')
                 OR t.started_at IS NOT NULL THEN 'in_progress'
            ELSE 'not_started'
          END
        ORDER BY bucket
        """
    )
    print("TPM/Upskilling test buckets:")
    for a in agg:
        print(f"  {a['bucket']}: {a['cnt']}")

    # Recent completions
    recent = store.query(
        """
        SELECT TOP 30 t.employee_id, e.full_name, t.status, t.score, t.completed_at, t.title
        FROM tests t
        INNER JOIN employees e ON e.employee_id = t.employee_id
        WHERE (
          LOWER(ISNULL(t.title,'')) LIKE '%upskilling%'
          OR LOWER(ISNULL(e.product,'')) LIKE '%upskilling%'
          OR LOWER(ISNULL(e.product,'')) LIKE '%tpm%'
        )
        AND (
          LOWER(ISNULL(t.status,'')) IN ('completed','submitted','passed','failed')
          OR t.completed_at IS NOT NULL
        )
        ORDER BY ISNULL(t.completed_at, t.created_at) DESC
        """
    )
    print(f"recent completed-ish ({len(recent)}):")
    for r in recent:
        print(
            f"  {r['employee_id']} {r.get('full_name')} status={r['status']} "
            f"score={r.get('score')} completed={r.get('completed_at')} title={str(r.get('title') or '')[:50]}"
        )


def main() -> int:
    os.environ.setdefault("MSSQL_TARGET", "remote")
    ids = sorted(set(COMPLETED_CLAIMED + SAMPLE_NOT_STARTED + [MUKESH]))
    for db in ("TalentScope_DB_Dev", "TalentScope_DB_Live"):
        run(db, ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
