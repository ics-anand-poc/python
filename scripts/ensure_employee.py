"""Create or update an employee portal account (password + SSO email).

Usage (from python/):
  set MSSQL_TARGET=remote
  venv\\Scripts\\python.exe scripts\\ensure_employee.py --email kavanan@infinite.com --password 12345 --employee-id KAVANAN --name \"Kavan Anselm\"
"""
from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import accounts


def tcp_open(host: str, port: int, timeout_s: float = 5.0) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout_s)
    try:
        sock.connect((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--employee-id", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--department", default="general")
    args = parser.parse_args()

    email = args.email.strip().lower()
    employee_id = args.employee_id.strip()
    full_name = (args.name or email.split("@")[0]).strip()

    from core.config import mssql_settings

    settings = mssql_settings()
    print(
        f"DB target={settings['target']} "
        f"{settings['server']}:{settings['port']}/{settings['database']}"
    )
    if not tcp_open(settings["server"], settings["port"], 8):
        print(
            f"ERROR: SQL Server not reachable at {settings['server']}:{settings['port']}. "
            "Connect VPN (for Azure VM DB) or start local SQL, then retry."
        )
        return 2

    existing = accounts.get_account(employee_id) or accounts.get_account_by_email(email)
    pwd_hash, pwd_salt = accounts.hash_password(args.password)
    account = {
        "employee_id": employee_id if not existing else existing["employee_id"],
        "email": email,
        "full_name": full_name or (existing or {}).get("full_name") or employee_id,
        "department": (existing or {}).get("department") or args.department,
        "role": (existing or {}).get("role") or "employee",
        "is_first_login": False,
        "password_hash": pwd_hash,
        "password_salt": pwd_salt,
        "product_qb_eligible": (existing or {}).get("product_qb_eligible", False),
        "assessment_only": (existing or {}).get("assessment_only", False),
        "xp_points": (existing or {}).get("xp_points", 0),
        "streak_days": (existing or {}).get("streak_days", 0),
        "skill_level": (existing or {}).get("skill_level") or "beginner",
        "ai_readiness_score": (existing or {}).get("ai_readiness_score", 0),
        "product": (existing or {}).get("product"),
    }
    # Prefer the requested employee_id when creating new
    if not existing:
        account["employee_id"] = employee_id

    ok = accounts.upsert_account(account)
    if not ok:
        print("ERROR: upsert failed")
        return 1

    saved = accounts.get_account(account["employee_id"])
    by_email = accounts.get_account_by_email(email)
    print("OK employee_id=", saved["employee_id"] if saved else None)
    print("OK email=", saved["email"] if saved else None)
    print("OK full_name=", saved["full_name"] if saved else None)
    print("OK has_password=", accounts.has_password(saved) if saved else False)
    print("OK sso_email_lookup=", bool(by_email))
    print(
        "Password login: use Employee ID",
        account["employee_id"],
        "with the password you set.",
    )
    print(
        "SSO login: Microsoft account must be",
        email,
        "(must match employees.email).",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
