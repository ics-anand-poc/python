import logging
from datetime import datetime, timezone

from core import request_context
from services import settings

log = logging.getLogger("talentscope")
SYNC_KEY = "dashboard_sync"


def read_sync() -> dict:
    try:
        value = settings.get_setting(SYNC_KEY)
    except Exception as err:
        log.warning("Failed to read dashboard sync: %s", err)
        value = None
    value = value if isinstance(value, dict) else {}
    try:
        revision = max(0, int(value.get("revision") or 0))
    except (TypeError, ValueError):
        revision = 0
    return {"revision": revision, "at": str(value.get("at") or ""), "source": str(value.get("source") or ""), "client": str(value.get("client") or "")}


def bump_sync(source: str = "") -> None:
    try:
        current = read_sync()
        settings.set_setting(SYNC_KEY, {"revision": current["revision"] + 1, "at": datetime.now(timezone.utc).isoformat(), "source": source[:80], "client": request_context.client_id()})
    except Exception as err:
        log.warning("Failed to bump dashboard sync: %s", err)
