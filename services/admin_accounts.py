import hashlib
import hmac
import logging
import re
import time
from typing import Optional

from core.config import env
from services import settings
from services.accounts import hash_password, verify_password

log = logging.getLogger("talentscope")

DEFAULT_SUPER_ADMIN = "admin@infinite.com"
SCREENING_ONLY_ADMIN_EMAILS = {"ramendras@infinite.com", "nehalathar@infinite.com", "shwethab@infinite.com"}
PERMISSIONS = (
    ("requirements", "Requirements (BR / JD) tab"),
    ("corpPool", "Corp Pool tab"),
    ("candidates", "Suitable & Non-Suitable Candidates tabs"),
    ("employeePortal", "Employee Portal tab (employee tests, scores, videos)"),
    ("emailOutbox", "Email Outbox tab"),
    ("allScreeningData", "Everyone's requirements, candidates and emails (untick = only their own)"),
    ("adminControls", "Admin Controls (ingestion, uploads, match scores, reset candidate)"),
    ("systemLogs", "System Logs viewer"),
    ("systemMonitor", "System Monitor"),
    ("changePassword", "Change their own password"),
)
PERMISSION_KEYS = tuple(key for key, _ in PERMISSIONS)
ACCOUNTS_KEY = "admin_named_accounts"
LEGACY_KEY = "admin_named_passwords"

_cache: Optional[tuple[float, dict]] = None


ADMIN_PASSWORD_NOT_SETUP = "Admin password not setup"


class AdminPasswordNotSetup(Exception):
    pass


CONSOLE_PASSWORD_KEY = "admin_console_password"


def console_secret() -> Optional[dict]:
    try:
        raw = settings.get_setting(CONSOLE_PASSWORD_KEY)
    except Exception as err:
        log.warning("Failed to load the admin console password: %s", err)
        return None
    return raw if isinstance(raw, dict) and _secret_ok(raw) else None


def set_console_password(password: str) -> None:
    hashed, salt = hash_password(password)
    settings.set_setting(CONSOLE_PASSWORD_KEY, {"hash": hashed, "salt": salt})
    invalidate_cache()


def _screening_password() -> str:
    value = env("SCREENING_ADMIN_PASSWORD")
    if not value:
        raise AdminPasswordNotSetup(ADMIN_PASSWORD_NOT_SETUP)
    return value


def _supervisor_password() -> str:
    value = env("SUPERVISOR_PASSWORD")
    if not value:
        raise AdminPasswordNotSetup("Supervisor password not setup in .env.local")
    return value


def verify_supervisor(password: str) -> bool:
    return bool(password and password == _supervisor_password())


def clean_email(email: str) -> str:
    return str(email or "").strip().lower()


def is_screening_only(email: str) -> bool:
    return clean_email(email) in SCREENING_ONLY_ADMIN_EMAILS


def _secret_ok(stored: Optional[dict]) -> bool:
    return bool(stored and stored.get("hash") and stored.get("salt"))


def _matches(password: str, stored: dict) -> bool:
    try:
        return verify_password(password, stored["salt"], stored["hash"])
    except Exception:
        return False


def _normalize(raw: dict) -> tuple[dict, bool]:
    plaintext = str((raw or {}).get("password") or "").strip()
    hashed = hash_password(plaintext) if plaintext else None
    ok = _secret_ok(raw)
    record = {
        "hash": raw.get("hash") if ok else (hashed[0] if hashed else None),
        "salt": raw.get("salt") if ok else (hashed[1] if hashed else None),
        "canViewEmployeePortal": raw.get("canViewEmployeePortal") is not False,
        "canChangePassword": raw.get("canChangePassword") is not False,
        "canViewOrgScreeningData": raw.get("canViewOrgScreeningData") is not False,
    }
    if isinstance(raw.get("permissions"), dict):
        record["permissions"] = {k: bool(v) for k, v in raw["permissions"].items() if k in PERMISSION_KEYS}
    return record, bool(plaintext)


def _parse(value) -> tuple[dict, bool]:
    if not isinstance(value, dict):
        return {}, False
    accounts, stripped = {}, False
    for email, raw in value.items():
        user = clean_email(email)
        if not user.endswith("@infinite.com") or not isinstance(raw, dict):
            continue
        record, had_plain = _normalize(raw)
        accounts[user] = record
        stripped = stripped or had_plain
    return accounts, stripped


def _read_map(key: str) -> dict:
    try:
        value = settings.get_setting(key)
        return value if isinstance(value, dict) else {}
    except Exception as err:
        log.warning("Failed to load %s: %s", key, err)
        return {}


def invalidate_cache() -> None:
    global _cache
    _cache = None


def load_accounts() -> dict:
    global _cache
    if _cache and time.time() - _cache[0] < 4:
        return _cache[1]
    accounts, dirty = _parse(_read_map(ACCOUNTS_KEY))
    for email, secret in _read_map(LEGACY_KEY).items():
        user = clean_email(email)
        if user not in accounts or not _secret_ok(secret) or _secret_ok(accounts[user]):
            continue
        accounts[user] = {**accounts[user], "hash": secret["hash"], "salt": secret["salt"]}
        dirty = True
    for email in SCREENING_ONLY_ADMIN_EMAILS:
        if accounts.get(email, {}).get("canViewEmployeePortal"):
            accounts[email] = {**accounts[email], "canViewEmployeePortal": False}
            dirty = True
    if dirty:
        save_accounts(accounts)
    else:
        _cache = (time.time(), accounts)
    return accounts


def save_accounts(accounts: dict) -> None:
    global _cache
    _cache = (time.time(), accounts)
    try:
        settings.set_setting(ACCOUNTS_KEY, accounts)
    except Exception as err:
        log.warning("Failed to save named admin accounts: %s", err)


def get_named_record(email: str) -> Optional[dict]:
    return load_accounts().get(clean_email(email))


def all_permissions(value: bool) -> dict:
    return {key: value for key in PERMISSION_KEYS}


def super_admin_email() -> str:
    return clean_email(env("ADMIN_EMAIL")) or DEFAULT_SUPER_ADMIN


def is_super_admin(email: str) -> bool:
    return clean_email(email) == super_admin_email()


def _record_permissions(record: dict) -> dict:
    out = {**all_permissions(True), "employeePortal": bool(record.get("canViewEmployeePortal", True)),
           "changePassword": bool(record.get("canChangePassword", True)),
           "allScreeningData": bool(record.get("canViewOrgScreeningData", True))}
    for key, value in (record.get("permissions") or {}).items():
        if key in PERMISSION_KEYS and isinstance(value, bool):
            out[key] = value
    return out


def _access(email: str, super_admin: bool, permissions: dict) -> dict:
    return {"email": email, "isSuperAdmin": super_admin, "permissions": permissions,
            "canViewEmployeePortal": permissions["employeePortal"], "canChangePassword": permissions["changePassword"]}


def get_access(email: str) -> dict:
    user = clean_email(email)
    if is_super_admin(user):
        return _access(user, True, {**all_permissions(True), "changePassword": False})
    named = get_named_record(user)
    if named:
        return _access(user, False, _record_permissions(named))
    if is_screening_only(user) and env("SCREENING_ADMIN_PASSWORD"):
        return _access(user, False, {**all_permissions(True), "employeePortal": False, "changePassword": False})
    return _access(user, False, all_permissions(False))


def has_permission(email: str, permission: str) -> bool:
    return bool(get_access(email)["permissions"].get(permission))


def can_change_password(email: str) -> bool:
    named = get_named_record(email)
    return bool(named and _record_permissions(named)["changePassword"])


def can_view_org_screening_data(email: str) -> bool:
    return has_permission(email, "allScreeningData")


def _env_match(password: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(hashlib.sha256(password.encode()).digest(), hashlib.sha256(expected.encode()).digest())


def authenticate(email: str, password: str) -> Optional[dict]:
    user = clean_email(email)
    if not user.endswith("@infinite.com") or not password:
        return None
    if user == super_admin_email():
        stored = console_secret()
        if not stored:
            raise AdminPasswordNotSetup(ADMIN_PASSWORD_NOT_SETUP)
        return get_access(user) if _matches(password, stored) else None
    named = get_named_record(user)
    if named and _secret_ok(named) and _matches(password, named):
        return get_access(user)
    if is_screening_only(user) and _env_match(password, _screening_password()):
        return get_access(user)
    return None


def list_named() -> list[dict]:
    return sorted(({"email": email, "hasPassword": _secret_ok(record), "permissions": _record_permissions(record)}
                   for email, record in load_accounts().items()), key=lambda item: item["email"])


def save_named(email: str, permissions: dict, password: Optional[str]) -> tuple[bool, str, bool]:
    user = clean_email(email)
    if not re.fullmatch(r"[^\s@]+@infinite\.com", user):
        return False, "Use an @infinite.com email address.", False
    if user == super_admin_email():
        return False, "The main admin account always has full access.", False
    password = str(password or "")
    if password and len(password) < 8:
        return False, "The password must be at least 8 characters.", False
    accounts = dict(load_accounts())
    existing = accounts.get(user)
    if not existing and not password:
        return False, "Set a password for the new admin.", False
    merged = {key: (permissions or {}).get(key) is True for key in PERMISSION_KEYS}
    hashed, salt = hash_password(password) if password else ((existing or {}).get("hash"), (existing or {}).get("salt"))
    accounts[user] = {"hash": hashed, "salt": salt, "permissions": merged, "canViewEmployeePortal": merged["employeePortal"],
                      "canChangePassword": merged["changePassword"], "canViewOrgScreeningData": merged["allScreeningData"]}
    save_accounts(accounts)
    return True, "", existing is None


def remove_named(email: str) -> bool:
    user = clean_email(email)
    accounts = dict(load_accounts())
    if user not in accounts:
        return False
    del accounts[user]
    save_accounts(accounts)
    return True


def change_password(email: str, current_password: str, new_password: str) -> tuple[bool, str]:
    user = clean_email(email)
    named = get_named_record(user)
    if not named or not named.get("canChangePassword"):
        return False, "This account cannot change its password here."
    if len(str(new_password or "")) < 5:
        return False, "New password must be at least 5 characters."
    if not authenticate(user, current_password):
        return False, "Current password is incorrect."
    accounts = load_accounts()
    current = accounts.get(user)
    if not current:
        return False, "This account cannot change its password here."
    hashed, salt = hash_password(new_password)
    accounts[user] = {**current, "hash": hashed, "salt": salt}
    save_accounts(accounts)
    return True, ""
