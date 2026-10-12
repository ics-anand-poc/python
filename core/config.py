import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

# Prefer service-local environment files, then allow the combined local workspace file.
_env_candidates = [ROOT / ".env.local", ROOT.parent / ".env.local", ROOT / ".env", ROOT.parent / ".env"]
for _candidate in _env_candidates:
    if _candidate.is_file():
        load_dotenv(_candidate, override=False)
        break

_default_uploads = ROOT / "uploads"
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR") or str(_default_uploads)).resolve()


def env(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def app_url() -> str:
    return (env("NEXT_PUBLIC_APP_URL") or "http://localhost:3000").rstrip("/")


def frontend_origins() -> list[str]:
    raw = env("FRONTEND_ORIGIN") or app_url()
    return [item.strip() for item in raw.split(",") if item.strip()]


def mssql_settings() -> dict:
    target = (env("MSSQL_TARGET") or "local").lower()
    prefix = f"MSSQL_{target.upper()}_"
    return {
        "target": target,
        "server": env(prefix + "SERVER", "localhost"),
        "port": env_int(prefix + "PORT", 1433),
        "database": env(prefix + "DATABASE", "Talentscope"),
        "user": env(prefix + "USER"),
        "password": env(prefix + "PASSWORD"),
        "encrypt": env_bool(prefix + "ENCRYPT", True),
        "trust_cert": env_bool(prefix + "TRUST_SERVER_CERTIFICATE", target == "local"),
        "driver": env(prefix + "ODBC_DRIVER") or env("MSSQL_ODBC_DRIVER") or "ODBC Driver 18 for SQL Server",
        "pool_max": env_int("MSSQL_POOL_MAX", 10),
        "pool_wait_s": env_int("MSSQL_POOL_WAIT_S", 20),
    }
