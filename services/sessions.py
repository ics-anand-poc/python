import uuid
from datetime import datetime, timezone
from typing import Optional

from core.db import get_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map(row: dict) -> dict:
    return {
        "code": row.get("code") or None,
        "email": row.get("email") or None,
        "createdAt": row.get("created_at") or _now(),
        "used": bool(row.get("used")),
        "resumeId": row.get("resume_id") or None,
        "usedAt": row.get("used_at") or None,
    }


def create_session() -> dict:
    code = str(uuid.uuid4()).split("-")[0].upper()
    row = get_store().insert("candidate_sessions", {"code": code, "used": False, "created_at": _now()})[0]
    return _map(row)


def get_session(code: str) -> Optional[dict]:
    row = get_store().first("candidate_sessions", {"code": code.upper().strip()})
    return _map(row) if row else None


def get_session_by_email(email: str) -> Optional[dict]:
    row = get_store().first("candidate_sessions", {"email": email.lower().strip()})
    return _map(row) if row else None


def mark_session_used(code: str, resume_id: str) -> dict:
    store = get_store()
    clean = code.upper().strip()
    if not store.update("candidate_sessions", {"used": True, "resume_id": resume_id, "used_at": _now()}, {"code": clean}):
        raise RuntimeError("Failed to update session: Not found")
    return get_session(clean)


def create_candidate_session(email: str, resume_id: str) -> dict:
    clean = email.lower().strip()
    row = get_store().upsert(
        "candidate_sessions",
        {"email": clean, "resume_id": resume_id, "used": False, "created_at": _now()},
        "email",
    )
    return _map(row)


def reset_session_by_email(email: str, resume_id: Optional[str] = None) -> Optional[dict]:
    store = get_store()
    clean = email.lower().strip()
    if store.update("candidate_sessions", {"used": False, "used_at": None}, {"email": clean}):
        return get_session_by_email(clean)
    return create_candidate_session(clean, resume_id) if resume_id else None


def mark_email_session_used(email: str) -> dict:
    store = get_store()
    clean = email.lower().strip()
    if not store.update("candidate_sessions", {"used": True, "used_at": _now()}, {"email": clean}):
        raise RuntimeError("Failed to mark email session used: Not found")
    return get_session_by_email(clean)


def delete_session_by_resume_id(resume_id: str) -> None:
    get_store().delete("candidate_sessions", {"resume_id": resume_id})


def get_all_sessions() -> list[dict]:
    try:
        return [_map(r) for r in get_store().select("candidate_sessions", order="created_at desc")]
    except Exception:
        return []
