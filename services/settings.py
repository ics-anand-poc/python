import logging
from typing import Any, Optional

from core.db import get_store

log = logging.getLogger("talentscope")

PORTAL_FEATURES_KEY = "portal_features"


def get_setting(key: str) -> Optional[Any]:
    row = get_store().first("portal_settings", {"key": key})
    return row["value"] if row else None


def set_setting(key: str, value: Any) -> None:
    get_store().upsert("portal_settings", {"key": key, "value": value}, "key")


def get_portal_features() -> dict:
    try:
        value = get_setting(PORTAL_FEATURES_KEY)
    except Exception as err:
        log.warning("getSettings failed: %s", err)
        value = None
    parsed = value if isinstance(value, dict) else {}
    return {"showSystemLogsViewer": parsed.get("showSystemLogsViewer") is not False}


def update_portal_features(settings: dict) -> dict:
    updated = {**get_portal_features(), **{k: v for k, v in settings.items() if k == "showSystemLogsViewer"}}
    set_setting(PORTAL_FEATURES_KEY, updated)
    return updated


INTERVIEW_DEFAULTS_KEY = "interview_defaults"
DURATION_MIN, DURATION_MAX, DURATION_DEFAULT = 5, 180, 15


def clamp_duration(value, fallback: int = DURATION_DEFAULT) -> int:
    try:
        return max(DURATION_MIN, min(DURATION_MAX, int(value)))
    except (TypeError, ValueError):
        return fallback


def get_interview_defaults() -> dict:
    try:
        value = get_setting(INTERVIEW_DEFAULTS_KEY)
    except Exception as err:
        log.warning("interview defaults unavailable: %s", err)
        value = None
    parsed = value if isinstance(value, dict) else {}
    return {"durationMinutes": clamp_duration(parsed.get("durationMinutes"))}


def update_interview_defaults(values: dict) -> dict:
    updated = {**get_interview_defaults(), "durationMinutes": clamp_duration(values.get("durationMinutes"), get_interview_defaults()["durationMinutes"])}
    set_setting(INTERVIEW_DEFAULTS_KEY, updated)
    return updated
