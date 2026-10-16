import re
import time
from contextvars import ContextVar
from typing import Optional

from fastapi import Request

from core.tokens import token_claims

_current: ContextVar[Optional[dict]] = ContextVar("request_context", default=None)
_names: dict[str, tuple[float, str]] = {}
NAME_TTL_S = 300
CANDIDATE_PATH = re.compile(r"^/api/interview/([0-9a-fA-F-]{36})(?:/|$)")


def bind(request: Request, ip: str) -> None:
    header = request.headers.get("authorization") or ""
    token = header[7:] if header.startswith("Bearer ") else header
    client = re.sub(r"[^A-Za-z0-9-]", "", request.headers.get("x-client-id") or "")[:64]
    _current.set({"ip": ip, "token": token, "path": request.url.path, "client": client})


def client_id() -> str:
    context = _current.get()
    return context.get("client", "") if context else ""


def ip() -> Optional[str]:
    context = _current.get()
    return context["ip"] if context else None


def _cached(key: str, load) -> str:
    hit = _names.get(key)
    if hit and time.monotonic() - hit[0] < NAME_TTL_S:
        return hit[1]
    try:
        value = load()
    except Exception:
        value = ""
    _names[key] = (time.monotonic(), value)
    return value


def _employee_label(employee_id: str) -> str:
    from services import accounts

    def load() -> str:
        employee = accounts.get_account(employee_id)
        if not employee:
            return f"employee {employee_id}"
        return f"{employee.get('full_name') or employee_id} <{employee.get('email')}>" if employee.get("email") else f"employee {employee_id}"

    return _cached(f"emp:{employee_id}", load)


def _candidate_label(resume_id: str) -> str:
    from core.db import get_store
    import json

    def load() -> str:
        row = get_store().first("resumes", {"id": resume_id}, ["parsed"])
        parsed = row.get("parsed") if row else None
        parsed = json.loads(parsed) if isinstance(parsed, str) else (parsed or {})
        email = (parsed.get("personal") or {}).get("email")
        return f"candidate <{email}>" if email else f"candidate {resume_id}"

    return _cached(f"cand:{resume_id}", load)


def actor() -> str:
    context = _current.get()
    if not context:
        return "system"
    claims = token_claims(context["token"])
    if claims:
        subject = claims.get("employee_id")
        if subject == "ADMIN":
            return claims.get("email") or "admin (session started before upgrade)"
        if subject:
            return _employee_label(subject)
    match = CANDIDATE_PATH.match(context["path"])
    if match:
        return _candidate_label(match.group(1))
    return "public"
