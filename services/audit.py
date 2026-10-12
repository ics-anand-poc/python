import logging
import uuid
from datetime import datetime, timezone

from core.db import get_store

log = logging.getLogger("talentscope")


def _map(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "actorEmail": row.get("actor_email"),
        "action": row.get("action"),
        "target": row.get("target"),
        "details": row.get("details"),
        "ipAddress": row.get("ip_address"),
        "createdAt": row.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }


def add_log(actor_email: str, action: str, target: str, details: str, ip_address: str) -> dict:
    record = {
        "id": str(uuid.uuid4()),
        "actor_email": (actor_email or "").lower().strip(),
        "action": action,
        "target": target,
        "details": details,
        "ip_address": ip_address,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        get_store().insert("audit_logs", record)
    except Exception as err:
        log.warning("Failed to write audit log: %s", err)
    return _map(record)


def get_logs() -> list[dict]:
    try:
        rows = get_store().select("audit_logs", order="created_at desc")
    except Exception as err:
        log.warning("Failed to fetch audit logs: %s", err)
        return []
    return [_map(r) for r in rows]


def clear_logs() -> None:
    try:
        get_store().delete("audit_logs", None)
    except Exception as err:
        log.warning("Failed to clear audit logs: %s", err)
