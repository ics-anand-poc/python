import logging
import time
from typing import Optional

from core.config import env
from services import settings
from services.accounts import hash_password, verify_password

log = logging.getLogger("talentscope")

SUPER_ADMIN_EMAIL = "admin@infinite.com"
SCREENING_ONLY_ADMIN_EMAILS = {"ramendras@infinite.com", "nehalathar@infinite.com", "shwethab@infinite.com"}
ACCOUNTS_KEY = "admin_named_accounts"
LEGACY_KEY = "admin_named_passwords"

_cache: Optional[tuple[float, dict]] = None


ADMIN_PASSWORD_NOT_SETUP = "Admin password not setup"


class AdminPasswordNotSetup(Exception):
    pass


def _default_password() -> str:
    value = env("ADMIN_PASSWORD")
    if not value:
        raise AdminPasswordNotSetup(ADMIN_PASSWORD_NOT_SETUP)
    return value


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


def get_access(email: str) -> dict:
    user = clean_email(email)
    named = get_named_record(user)
    hide = is_screening_only(user)
    if named:
        return {
            "email": user,
            "canViewEmployeePortal": bool(named["canViewEmployeePortal"]) and not hide,
            "canChangePassword": bool(named["canChangePassword"]),
        }
    return {"email": user, "canViewEmployeePortal": not hide, "canChangePassword": False}


def can_change_password(email: str) -> bool:
    named = get_named_record(email)
    return bool(named and named.get("canChangePassword"))


def can_view_org_screening_data(email: str) -> bool:
    user = clean_email(email)
    if user == SUPER_ADMIN_EMAIL or is_screening_only(user):
        return True
    named = get_named_record(user)
    return bool(named and named.get("canViewOrgScreeningData"))


def authenticate(email: str, password: str) -> Optional[dict]:
    user = clean_email(email)
    if not user.endswith("@infinite.com") or not password:
        return None
    named = get_named_record(user)
    if named and _secret_ok(named) and _matches(password, named):
        return get_access(user)
    if is_screening_only(user) and password == _screening_password():
        return get_access(user)
    if named:
        return None
    if password != _default_password():
        return None
    return get_access(user)


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
