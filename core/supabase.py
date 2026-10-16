import logging

from core.config import supabase_db_settings

log = logging.getLogger("talentscope")


def _connection_error_code(err: Exception) -> str:
    message = str(err).casefold()
    if any(text in message for text in ("failed to resolve", "getaddrinfo", "name or service not known")):
        return "dns_resolution_failed"
    if any(text in message for text in ("timed out", "timeout expired", "connection timeout")):
        return "connection_timeout"
    if any(text in message for text in ("connection refused", "actively refused")):
        return "connection_refused"
    if any(text in message for text in ("network is unreachable", "no route to host", "host is unreachable")):
        return "network_unreachable"
    if any(text in message for text in ("password authentication failed", "authentication failed", "invalid authorization")):
        return "authentication_failed"
    if any(text in message for text in ("ssl", "tls", "certificate")):
        return "tls_error"
    return "postgres_connection_failed"


def _connection_error_hint(error_code: str) -> str:
    if error_code == "dns_resolution_failed":
        return (
            "Verify SUPABASE_DB_HOST is the direct db.<project-ref>.supabase.co host, "
            "then check DNS and outbound IPv6 connectivity from this machine."
        )
    if error_code == "connection_timeout":
        return "Check outbound firewall rules and IPv6 routing to the direct Supabase database endpoint."
    if error_code == "connection_refused":
        return "Verify the direct database port and that the Supabase project is active."
    if error_code == "network_unreachable":
        return "This network has no route to the Supabase direct endpoint; check IPv6 routing or request direct IPv4 connectivity."
    if error_code == "authentication_failed":
        return "Verify the Supabase database password, database name, and database username."
    if error_code == "tls_error":
        return "Verify that SSL/TLS traffic to the direct Supabase database endpoint is allowed."
    return "Review the sanitized database connection diagnostic in the API logs."


def health_check() -> dict:
    settings = supabase_db_settings()
    configured = all(settings[key] for key in ("host", "database", "user", "password"))
    if not configured:
        return {
            "configured": False,
            "up": None,
            "error": "missing_database_settings",
            "hint": "Set SUPABASE_DB_HOST, SUPABASE_DB_NAME, SUPABASE_DB_USER, and SUPABASE_DB_PASSWORD.",
        }

    try:
        import psycopg
    except ImportError:
        log.error("Supabase PostgreSQL health check requires psycopg; install requirements.txt")
        return {
            "configured": True,
            "up": False,
            "error": "psycopg_not_installed",
            "hint": "Install requirements.txt in the same Python environment that runs the API, then restart it.",
        }

    try:
        with psycopg.connect(
            host=settings["host"],
            port=settings["port"],
            dbname=settings["database"],
            user=settings["user"],
            password=settings["password"],
            sslmode="require",
            connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                connected = cursor.fetchone()[0] == 1
        return {"configured": True, "up": connected, "error": None, "hint": None}
    except psycopg.Error as err:
        message = str(err)
        if settings["password"]:
            message = message.replace(settings["password"], "[redacted]")
        log.warning("Supabase PostgreSQL health check failed: %s", message)
        error_code = _connection_error_code(err)
        return {
            "configured": True,
            "up": False,
            "error": error_code,
            "hint": _connection_error_hint(error_code),
        }
