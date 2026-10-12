import json
import logging
import re
import threading
from datetime import datetime, timezone

from core.config import UPLOAD_DIR

log = logging.getLogger("talentscope")
_lock = threading.Lock()
MODULE_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _dir():
    path = UPLOAD_DIR / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_log(module: str, action: str, status: str, details: str) -> None:
    if not MODULE_RE.match(module):
        return
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "module": module, "action": action,
             "status": status, "details": details}
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
