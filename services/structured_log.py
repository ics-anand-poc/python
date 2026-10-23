import json
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Optional

from core import request_context
from core.config import UPLOAD_DIR

log = logging.getLogger("talentscope")
_lock = threading.Lock()
MODULE_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _dir():
    path = UPLOAD_DIR / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_log(module: str, action: str, status: str, details: str, actor: Optional[str] = None) -> None:
    if not MODULE_RE.match(module):
        return
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "module": module, "action": action,
             "status": status, "details": details, "actor": actor or request_context.actor()}
    client_ip = request_context.ip()
    if client_ip:
        entry["ip"] = client_ip
    line = json.dumps(entry) + "\n"
    try:
        with _lock:
            with open(_dir() / f"{module}.log", "a", encoding="utf-8") as handle:
                handle.write(line)
            if status.lower() in ("failed", "error", "warning") or module == "error":
                with open(_dir() / "error.log", "a", encoding="utf-8") as handle:
                    handle.write(line)
    except OSError as err:
        log.error("Failed to write structured log: %s", err)


def read_logs(module: str = "all") -> list[dict]:
    files = []
    if module and module != "all":
        if MODULE_RE.match(module):
            files = [_dir() / f"{module}.log"]
    else:
        files = [f for f in _dir().glob("*.log") if f.name != "error.log"]
    logs = []
    for path in files:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    logs.append(json.loads(line))
                except ValueError:
                    continue
        except FileNotFoundError:
            continue
    logs.sort(key=lambda entry: entry.get("timestamp") or "", reverse=True)
    return logs


def raw_log(module: str):
    if not MODULE_RE.match(module):
        return None
    path = _dir() / f"{module}.log"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def clear_all() -> None:
    with _lock:
        for path in _dir().glob("*.log"):
            path.write_text("", encoding="utf-8")


AUDIT_ROWS = 5000
SAME_EVENT_S = 3.0
AUTH_ACTIONS = re.compile(r"LOGIN|SSO|PASSWORD|ACCESS")


def _audit_module(action: str) -> str:
    if AUTH_ACTIONS.search(action):
        return "auth"
    if "_JD" in action:
        return "requirements"
    if "PORTAL_SETTINGS" in action:
        return "employee"
    if re.search(r"CANDIDATE|RESUME|UPLOAD", action):
        return "candidate-processing"
    return "audit"


def _epoch(value) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _audit_entry(row: dict) -> dict:
    action = row.get("action") or "UNKNOWN"
    entry = {"timestamp": str(row.get("createdAt")), "module": _audit_module(action), "action": action,
             "status": "failed" if re.search(r"FAIL|DENIED|ERROR", action) else "success",
             "details": ": ".join(p for p in (row.get("target"), row.get("details")) if p),
             "actor": row.get("actorEmail") or "unknown"}
    if row.get("ipAddress"):
        entry["ip"] = row["ipAddress"]
    return entry


def merged_logs(module: str = "all") -> list[dict]:
    from services import audit

    file_logs = read_logs("all")
    stamped = [(entry, _epoch(entry.get("timestamp"))) for entry in file_logs]
    out = list(file_logs)
    for row in audit.get_logs(AUDIT_ROWS):
        entry = _audit_entry(row)
        if entry["module"] != "auth":
            at = _epoch(entry["timestamp"])
            twins = [log for log, when in stamped if abs(when - at) <= SAME_EVENT_S]
            for log in twins:
                if not log.get("actor") or log["actor"] == "public":
                    log["actor"] = entry["actor"]
                if not log.get("ip") and entry.get("ip"):
                    log["ip"] = entry["ip"]
            if twins:
                continue
        out.append(entry)
    out.sort(key=lambda e: _epoch(e.get("timestamp")), reverse=True)
    if module == "error":
        return [e for e in out if str(e.get("status", "")).lower() in ("failed", "error", "warning") or e.get("module") == "error"]
    return out if module == "all" else [e for e in out if e.get("module") == module]
