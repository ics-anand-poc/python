import httpx

from core.config import env


def base_url() -> str:
    return (env("LAYA_URL") or "http://127.0.0.1:8090").rstrip("/")


def enabled() -> bool:
    raw = env("LAYA_ENABLED", "1").lower()
    return raw not in {"0", "false", "off"}


def model_name() -> str:
    return "convaiinnovations/laya"


def is_up() -> bool:
    if not enabled():
        return False
    try:
        return httpx.get(f"{base_url()}/health", timeout=2.0).status_code < 400
    except Exception:
        return False
