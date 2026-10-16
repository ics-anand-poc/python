"""Check the Supabase Auth API and direct PostgreSQL database connection."""

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


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
    names = (
        "NEXT_PUBLIC_SUPABASE_URL",
        "SUPABASE_DB_HOST",
        "SUPABASE_DB_PORT",
        "SUPABASE_DB_NAME",
        "SUPABASE_DB_USER",
        "SUPABASE_DB_PASSWORD",
    )
    missing = [name for name in names if not os.environ.get(name)]
    if not (os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")):
        missing.append("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if missing:
        print(json.dumps({"ok": False, "error": "missing_environment_variables", "missing": missing}, indent=2))
        return 2

    try:
        port = int(os.environ["SUPABASE_DB_PORT"])
    except ValueError:
        print(json.dumps({"ok": False, "error": "SUPABASE_DB_PORT_must_be_an_integer"}, indent=2))
        return 2

    api_key = os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
    api = check_supabase_api(os.environ["NEXT_PUBLIC_SUPABASE_URL"], api_key)
    database = check_direct_database(
        os.environ["SUPABASE_DB_HOST"],
        port,
        os.environ["SUPABASE_DB_NAME"],
        os.environ["SUPABASE_DB_USER"],
        os.environ["SUPABASE_DB_PASSWORD"],
    )
    result = {"ok": api["ok"] and database["ok"], "supabase_api": api, "direct_postgres": database}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
