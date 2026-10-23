import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from main import app

CALL_RE = re.compile(r"/api/[A-Za-z0-9_\-/.${}\[\]]*")
SKIP = ("node_modules", ".next")


def route_table() -> list[tuple[list[str], str, set]]:
    out = []
    for path, methods in app.openapi()["paths"].items():
        if path.startswith("/api"):
            out.append((path.strip("/").split("/"), path, {m.upper() for m in methods}))
    return out


def compare(ui: list[str], route: list[str]) -> str:
    if len(ui) != len(route):
        return "no"
    weak = False
    for u, r in zip(ui, route):
        is_param = r.startswith("{")
        if u == "x":
            continue
        if is_param:
            weak = True
        elif u != r:
            return "no"
    return "weak" if weak else "exact"


def ui_calls() -> dict[str, set]:
    calls: dict[str, set] = {}
    for file in (ROOT / "UI" / "src").rglob("*.ts*"):
        if any(part in file.parts for part in SKIP):
            continue
        for match in CALL_RE.finditer(file.read_text(encoding="utf-8", errors="ignore")):
            raw = match.group(0).rstrip(".,)")
            path = re.sub(r"\$\{[^}]*\}", "x", raw).split("?")[0].rstrip("/")
            if path == "/api":
                continue
            calls.setdefault(path, set()).add(str(file.relative_to(ROOT)))
    return calls


def main() -> int:
    table = route_table()
    calls = ui_calls()
    missing, weak = [], []
    for path, files in sorted(calls.items()):
        parts = path.strip("/").split("/")
        results = [compare(parts, r) for r, _, _ in table]
        if "exact" in results:
            continue
        (weak if "weak" in results else missing).append((path, sorted(files)))
    print(f"UI endpoints found: {len(calls)} | FastAPI routes: {len(table)}")
    for path, files in missing:
        print(f"MISSING  {path}   <- {', '.join(files)}")
    for path, files in weak:
        print(f"WEAK     {path}   (only a {{param}} route matches; literal route missing)   <- {', '.join(files)}")
    if not missing and not weak:
        print("All UI API calls have a matching FastAPI route.")
    return 1 if (missing or weak) else 0


if __name__ == "__main__":
    raise SystemExit(main())
