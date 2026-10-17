"""Check the Supabase Auth API and direct PostgreSQL database connection."""

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import env, supabase_db_settings


def check_supabase_api(project_url: str, anon_key: str) -> dict:
    parsed = urlparse(project_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return {"ok": False, "error": "supabase_url_must_be_https"}

    headers = {
        "apikey": anon_key,
        "Accept": "application/json",
    }
    if not anon_key.startswith("sb_publishable_"):
        headers["Authorization"] = f"Bearer {anon_key}"
    request = Request(f"{project_url.rstrip('/')}/auth/v1/health", headers=headers)
    try:
        with urlopen(request, timeout=8) as response:
            status = response.status
            body = response.read(1024 * 1024)
        payload = json.loads(body)
        valid = isinstance(payload, dict) and payload.get("name") == "GoTrue" and bool(payload.get("version"))
        return {
            "ok": status == 200 and valid,
            "http_status": status,
            "response_valid": valid,
            "error": None if status == 200 and valid else "unexpected_supabase_api_response",
        }
    except HTTPError as err:
        return {"ok": False, "http_status": err.code, "error": "supabase_api_http_error"}
    except (URLError, TimeoutError, OSError) as err:
        return {"ok": False, "error": "supabase_api_unreachable", "detail": type(err).__name__}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "error": "supabase_api_invalid_json"}


def check_direct_database(host: str, port: int, database: str, user: str, password: str) -> dict:
    try:
        import psycopg
    except ImportError:
        return {"ok": False, "error": "psycopg_not_installed"}

    try:
        with psycopg.connect(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=password,
            sslmode="require",
            connect_timeout=8,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                result = cursor.fetchone()[0]
        return {"ok": result == 1, "query_result": result, "error": None if result == 1 else "unexpected_query_result"}
    except psycopg.Error as err:
        return {"ok": False, "error": type(err).__name__, "detail": str(err).replace(password, "[redacted]")}


def main() -> int:
    settings = supabase_db_settings()
    names = {
        "SUPABASE_DB_HOST": settings["host"],
        "SUPABASE_DB_PORT": settings["port"],
        "SUPABASE_DB_NAME": settings["database"],
        "SUPABASE_DB_USER": settings["user"],
        "SUPABASE_DB_PASSWORD": settings["password"],
    }
    missing = [name for name, value in names.items() if not value]
    project_url = env("NEXT_PUBLIC_SUPABASE_URL")
    api_key = env("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or env("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not project_url:
        missing.append("NEXT_PUBLIC_SUPABASE_URL")
    if not api_key:
        missing.append("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if missing:
        print(json.dumps({"ok": False, "error": "missing_properties_or_environment_overrides", "missing": missing}, indent=2))
        return 2

    api = check_supabase_api(project_url, api_key)
    database = check_direct_database(
        settings["host"],
        settings["port"],
        settings["database"],
        settings["user"],
        settings["password"],
    )
    result = {"ok": api["ok"] and database["ok"], "supabase_api": api, "direct_postgres": database}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
