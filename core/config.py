import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(__file__).resolve().parents[1]
PROPERTIES_PATH = APP_ROOT / "conf" / "application.properties"
DOTENV_PATH = APP_ROOT / ".env"
_PROPERTY_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}$")
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _read_properties(path: Path) -> dict[str, str]:
    properties = {}
    if not path.is_file():
        return properties
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"Invalid property at {path}:{line_number}")
        properties[key.strip()] = value.strip()
    return properties


def _read_dotenv(path: Path) -> dict[str, str]:
    values = {}
    if not path.is_file():
        return values
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, value = stripped.partition("=")
        key = key.strip()
        if not separator or not _ENV_KEY.fullmatch(key):
            raise ValueError(f"Invalid environment variable at {path}:{line_number}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


_PROPERTIES = _read_properties(PROPERTIES_PATH)
_DOTENV = _read_dotenv(DOTENV_PATH)


def _property(name: str, default: str = "") -> str:
    value = os.environ.get(name) or _DOTENV.get(name)
    if value:
        return value.strip()
    value = _PROPERTIES.get(name, default).strip()
    match = _PROPERTY_REF.fullmatch(value)
    if match:
        return (
            os.environ.get(match.group(1))
            or _DOTENV.get(match.group(1))
            or match.group(2)
            or ""
        ).strip()
    return value


def active_profile() -> str:
    profile = (os.environ.get("APP_PROFILE") or _DOTENV.get("APP_PROFILE", "")).strip().lower()
    if not profile and os.environ.get("VERCEL"):
        profile = "vercel"
    if not profile and os.environ.get("NODE_ENV", "").strip().lower() == "production":
        profile = "production"
    if not profile:
        profile = _property("app.profile", "local").lower()
    if profile not in {"local", "vercel", "production"}:
        raise ValueError("APP_PROFILE must be local, vercel, or production")
    return profile


_default_uploads = Path("/tmp/talentscope-uploads") if active_profile() == "vercel" else APP_ROOT / "uploads"
_upload_path = Path(_property("UPLOAD_DIR", str(_default_uploads)))
UPLOAD_DIR = (_upload_path if _upload_path.is_absolute() else APP_ROOT / _upload_path).resolve()


def env(name: str, default: str = "") -> str:
    return _property(name, default)


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
    profile = active_profile()
    if profile == "vercel":
        raise ValueError("The vercel profile uses PostgreSQL, not SQL Server")
    prefix = f"database.{profile}."
    legacy_target = "azure" if profile == "production" else "local"
    return {
        "target": profile,
        "server": _property(prefix + "host") or env(f"MSSQL_{legacy_target.upper()}_SERVER", "localhost"),
        "port": int(_property(prefix + "port") or env(f"MSSQL_{legacy_target.upper()}_PORT", "1433")),
        "database": _property(prefix + "database") or env(f"MSSQL_{legacy_target.upper()}_DATABASE", "Talentscope"),
        "user": _property(prefix + "user") or env(f"MSSQL_{legacy_target.upper()}_USER"),
        "password": _property(prefix + "password") or env(f"MSSQL_{legacy_target.upper()}_PASSWORD"),
        "encrypt": (_property(prefix + "encrypt") or env(f"MSSQL_{legacy_target.upper()}_ENCRYPT", "true")).lower()
        in {"1", "true", "yes", "on"},
        "trust_cert": (_property(prefix + "trust_certificate") or
                       env(f"MSSQL_{legacy_target.upper()}_TRUST_SERVER_CERTIFICATE",
                           "true" if profile == "local" else "false")).lower() in {"1", "true", "yes", "on"},
        "driver": _property(prefix + "driver") or env("MSSQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
        "pool_max": env_int("MSSQL_POOL_MAX", 10),
        "pool_wait_s": env_int("MSSQL_POOL_WAIT_S", 20),
    }


def postgres_settings() -> dict:
    prefix = "database.vercel."
    return {
        "host": _property(prefix + "host") or env("SUPABASE_DB_HOST"),
        "port": int(_property(prefix + "port") or env("SUPABASE_DB_PORT", "5432")),
        "database": _property(prefix + "database") or env("SUPABASE_DB_NAME", "postgres"),
        "user": _property(prefix + "user") or env("SUPABASE_DB_USER"),
        "password": _property(prefix + "password") or env("SUPABASE_DB_PASSWORD"),
        "sslmode": _property(prefix + "sslmode", "require"),
        "pool_max": env_int("POSTGRES_POOL_MAX", 5),
        "pool_wait_s": env_int("POSTGRES_POOL_WAIT_S", 15),
    }


def supabase_db_settings() -> dict:
    return postgres_settings()
