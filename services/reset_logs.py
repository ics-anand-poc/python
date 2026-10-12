import logging
import uuid
from datetime import datetime, timezone

from core.db import get_store

log = logging.getLogger("talentscope")


def _map(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "candidateEmail": row.get("candidate_email"),
        "resetBy": row.get("reset_by"),
        "source": row.get("source"),
        "createdAt": row.get("created_at") or datetime.now(timezone.utc).isoformat(),
    }


def add_log(candidate_email: str, reset_by: str, source: str) -> dict:
    record = {
        "id": str(uuid.uuid4()),
        "candidate_email": candidate_email.lower().strip(),
        "reset_by": reset_by.lower().strip(),
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        get_store().insert("reset_logs", record)
    except Exception as err:
        log.warning("Failed to write reset log: %s", err)
    return _map(record)


def get_logs() -> list[dict]:
    try:
        return [_map(r) for r in get_store().select("reset_logs", order="created_at desc")]
    except Exception as err:
        log.warning("Failed to fetch reset logs: %s", err)
        return []


def clear_logs() -> None:
    try:
        get_store().delete("reset_logs", None)
    except Exception as err:
        log.warning("Failed to clear reset logs: %s", err)
