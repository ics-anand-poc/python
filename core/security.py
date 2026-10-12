import ipaddress
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from core.config import env_int
from core.validation import LIMITS


@dataclass
class RateResult:
    limited: bool
    remaining: int
    reset: float


_tracker: dict[str, dict] = {}
_lock = threading.Lock()


def _now_ms() -> float:
    return time.time() * 1000


def is_rate_limited(key: str, limit: int = 60, window_ms: int = 60_000) -> RateResult:
    now = _now_ms()
    with _lock:
        if len(_tracker) > 5000:
            for stale in [k for k, v in _tracker.items() if now > v["reset"] and now > v["blocked"]]:
                _tracker.pop(stale, None)
        rec = _tracker.get(key)
        if rec and now < rec["blocked"]:
            return RateResult(True, 0, rec["blocked"])
        if not rec or now > rec["reset"]:
            reset = now + window_ms
            strikes = max(0, rec["strikes"] - 1) if rec and now > rec["blocked"] else 0
            _tracker[key] = {"count": 1, "reset": reset, "strikes": strikes, "blocked": 0}
            return RateResult(False, limit - 1, reset)
        if rec["count"] >= limit:
            rec["strikes"] = min(rec["strikes"] + 1, 6)
            backoff = window_ms * math.pow(2, min(rec["strikes"] - 1, 4))
            rec["blocked"] = now + backoff
            rec["reset"] = rec["blocked"]
            return RateResult(True, 0, rec["blocked"])
        rec["count"] += 1
        return RateResult(False, limit - rec["count"], rec["reset"])


def is_rate_limited_any(keys: list[Optional[str]], limit: int, window_ms: int) -> RateResult:
    worst = RateResult(False, limit, _now_ms() + window_ms)
    for key in keys:
        if not key:
            continue
        res = is_rate_limited(key, limit, window_ms)
        if res.limited:
            return res
        if res.remaining < worst.remaining:
            worst = res
    return worst


def reset_rate_limits() -> None:
    with _lock:
        _tracker.clear()


def rate_limited_response(check: RateResult, message: str = "Too many attempts. Please try again later.") -> JSONResponse:
    retry_after = max(1, math.ceil((check.reset - _now_ms()) / 1000))
    return JSONResponse(
        status_code=429,
        content={"error": message, "message": message},
        headers={"Retry-After": str(retry_after), "X-RateLimit-Reset": str(math.ceil(check.reset / 1000))},
    )


def _is_private(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


def get_client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or not _is_private(peer):
        return peer
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _is_private(hop):
            return hop
    return hops[0] if hops else peer


HEAVY_ROUTES = (
    ("/upload_video", "upload", "UPLOAD_CONCURRENCY", 3),
    ("/verify_id", "face", "FACE_CONCURRENCY", 2),
    ("/run_code", "code", "CODE_CONCURRENCY", 2),
)
_heavy: dict[str, threading.BoundedSemaphore] = {}
_inflight = {"count": 0}
_inflight_lock = threading.Lock()
EXEMPT_PREFIXES = ("/api/health",)
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                    "Cross-Origin-Resource-Policy": "same-origin"}
BODY_LIMITS = (("/upload_video", "MAX_VIDEO_BODY_MB", 130), ("/", "MAX_BODY_MB", 25))


def _body_limit(path: str) -> int:
    for suffix, name, default in BODY_LIMITS:
        if path.endswith(suffix) or suffix == "/":
            return env_int(name, default) * 1024 * 1024
    return 25 * 1024 * 1024


def _declared_length(request: Request) -> Optional[int]:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    if not raw.isdigit():
        return -1
    return int(raw)


def _harden(response, path: str):
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    if path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def _heavy_gate(path: str):
    for suffix, name, env_name, default in HEAVY_ROUTES:
        if path.endswith(suffix):
            if name not in _heavy:
                _heavy[name] = threading.BoundedSemaphore(env_int(env_name, default))
            return _heavy[name]
    return None


def _busy(message: str, retry_after: int = 5) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": message, "message": message},
                        headers={"Retry-After": str(retry_after)})


def install_traffic_controls(app) -> None:
    @app.middleware("http")
    async def traffic_controls(request: Request, call_next):
        path = request.url.path
        if path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)
        declared = _declared_length(request)
        if declared is not None and (declared < 0 or declared > _body_limit(path)):
            return _harden(JSONResponse(status_code=413 if declared > 0 else 400,
                                        content={"error": "Request body too large or invalid", "message": "Request body too large or invalid"}), path)
        ip_limit = is_rate_limited(f"global:ip:{get_client_ip(request)}", env_int("RATE_LIMIT_IP_PER_MIN", 600), 60_000)
        if ip_limit.limited:
            return rate_limited_response(ip_limit, "Too many requests. Please slow down.")
        with _inflight_lock:
            if _inflight["count"] >= env_int("MAX_INFLIGHT", 80):
                return _busy("The server is busy. Please retry in a few seconds.")
            _inflight["count"] += 1
        gate = _heavy_gate(path)
        acquired = gate.acquire(blocking=False) if gate else True
        try:
            if not acquired:
                return _busy("This operation is busy right now. Please retry in a few seconds.")
            return _harden(await call_next(request), path)
        finally:
            if gate and acquired:
                gate.release()
            with _inflight_lock:
                _inflight["count"] -= 1


def traffic_snapshot() -> dict:
    return {"inflight": _inflight["count"], "trackedKeys": len(_tracker),
            "heavyFree": {name: sem._value for name, sem in _heavy.items()}}


UPLOAD_ALLOWED_EXTS = ("pdf", "doc", "docx", "txt", "html", "htm", "xlsx", "xls", "csv", "zip")


def validate_file_signature(buffer: bytes, filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not ext or not buffer:
        return False
    head = buffer[:8].hex().upper()
    if ext == "pdf":
        return head.startswith("25504446")
    if ext in ("docx", "xlsx", "xlsm", "zip"):
        return head.startswith(("504B0304", "504B0506", "504B0708"))
    if ext in ("doc", "xls"):
        return head.startswith("D0CF11E0")
    if ext == "png":
        return head.startswith("89504E47")
    if ext in ("jpg", "jpeg"):
        return head.startswith("FFD8FF")
    if ext in ("webm", "mkv"):
        return head.startswith("1A45DFA3")
    if ext in ("txt", "html", "htm", "csv"):
        sample = buffer[:4096].decode("utf-8", errors="replace")
        return not any(ord(c) < 32 and c not in "\t\n\r" for c in sample)
    return False


def safe_storage_filename(name: str) -> str:
    base = (name or "").replace("\\", "/").split("/")[-1].replace("\0", "").strip()
    if not base or base in (".", "..") or ".." in base:
        return ""
    limit = LIMITS["filename"]
    if len(base) <= limit:
        return base
    ext = base[base.rfind("."):] if "." in base else ""
    return base[: max(1, limit - len(ext))] + ext


def inspect_upload(buffer: bytes, filename: str, max_bytes: int, allowed_exts=UPLOAD_ALLOWED_EXTS) -> tuple[bool, str]:
    safe = safe_storage_filename(filename)
    if not safe:
        return False, "Invalid file name"
    ext = safe.rsplit(".", 1)[-1].lower() if "." in safe else ""
    if ext not in allowed_exts:
        return False, "Invalid file type"
    if not buffer:
        return False, "File is empty"
    if len(buffer) > max_bytes:
        return False, f"File too large (max {round(max_bytes / (1024 * 1024))}MB)"
    if not validate_file_signature(buffer, safe):
        return False, "File verification failed: content does not match the file type"
    return True, safe
