import re
from typing import Any, Optional

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
EMPLOYEE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)
PATH_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")

LIMITS = {
    "email": 254,
    "password": 256,
    "employee_id": 40,
    "name": 120,
    "filename": 180,
    "text_field": 2000,
    "json_body_chars": 200_000,
    "jd_text": 500_000,
}


def as_trimmed(value: Any, max_len: int) -> str:
    return value.strip()[:max_len] if isinstance(value, str) else ""


def as_bounded(value: Any, max_len: int, min_len: int = 0) -> Optional[str]:
    if not isinstance(value, str) or len(value) < min_len or len(value) > max_len:
        return None
    return value


def as_email(value: Any) -> Optional[str]:
    email = as_trimmed(value, LIMITS["email"]).lower()
    return email if email and EMAIL_RE.match(email) else None


def as_employee_id(value: Any) -> Optional[str]:
    ident = as_trimmed(value, LIMITS["employee_id"])
    return ident if ident and EMPLOYEE_ID_RE.match(ident) else None


def as_uuid(value: Any) -> Optional[str]:
    ident = as_trimmed(value, 36)
    return ident if UUID_RE.match(ident) else None


def as_path_id(value: Any) -> Optional[str]:
    ident = as_trimmed(value, 80)
    return ident if ident and PATH_ID_RE.match(ident) else None


def as_password(value: Any, allow_empty: bool = False) -> Optional[str]:
    if not isinstance(value, str) or len(value) > LIMITS["password"]:
        return None
    if not allow_empty and not value:
        return None
    return value
