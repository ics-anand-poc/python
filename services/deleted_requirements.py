import hashlib
import logging
import re
from typing import Iterable, Optional

from services import settings

log = logging.getLogger("talentscope")
SETTINGS_KEY = "deleted_requirements"


def _clean(values) -> list[str]:
    seen = dict.fromkeys(str(v or "").strip().lower() for v in (values if isinstance(values, list) else []))
    return [v for v in seen if v]


def extract_br_id(file_name: Optional[str]) -> str:
    prefix = str(file_name or "").split("|")[0].strip()
    match = re.search(r"(\d+)\s*BR", prefix, re.I)
    if match:
        return f"{match.group(1)}BR".lower()
    if re.fullmatch(r"\d{4,}", prefix):
        return f"{prefix}br"
    return prefix.lower()


def file_name_has_br_id(file_name: Optional[str]) -> bool:
    prefix = str(file_name or "").split("|")[0].strip()
    return bool(re.search(r"(\d+)\s*BR", prefix, re.I) or re.fullmatch(r"\d{4,}", prefix))


def next_synthetic_br_id(labels: Iterable[str]) -> str:
    highest = 0
    for label in labels:
        match = re.fullmatch(r"0+(\d+)\s*BR", str(label or "").split("|")[0].strip(), re.I)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{highest + 1:05d}BR"


def load() -> dict:
    try:
        raw = settings.get_setting(SETTINGS_KEY)
    except Exception as err:
        log.warning("Failed to load deleted requirements: %s", err)
        raw = None
    raw = raw if isinstance(raw, dict) else {}
    return {"ids": _clean(raw.get("ids")), "brIds": _clean(raw.get("brIds"))}


def _save(value: dict) -> None:
    try:
        settings.set_setting(SETTINGS_KEY, {"ids": _clean(value["ids"]), "brIds": _clean(value["brIds"]), "groupKeys": []})
    except Exception as err:
        log.warning("Failed to save deleted requirements: %s", err)


def is_deleted(deleted: dict, row_id: Optional[str] = None, file_name: Optional[str] = None, br_id: Optional[str] = None) -> bool:
    rid = str(row_id or "").strip().lower()
    if rid and rid in deleted["ids"]:
        return True
    ids = {extract_br_id(br_id), extract_br_id(file_name)} - {""}
    return any(i in deleted["brIds"] for i in ids)


def mark_deleted(rows: list[dict]) -> None:
    deleted = load()
    ids, br_ids = set(deleted["ids"]), set(deleted["brIds"])
    for row in rows:
        rid = str(row.get("id") or "").strip().lower()
        if rid:
            ids.add(rid)
        for candidate in (extract_br_id(row.get("brId")), extract_br_id(row.get("fileName"))):
            if candidate:
                br_ids.add(candidate.lower())
    _save({"ids": list(ids), "brIds": list(br_ids)})


def br_id_to_uuid(br_id: str) -> str:
    if not br_id:
        return br_id
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", br_id, re.I):
        return br_id
    h = hashlib.md5(br_id.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def unmark_deleted(rows: list[dict]) -> None:
    deleted = load()
    ids = set(deleted["ids"]) - {str(r.get("id") or "").strip().lower() for r in rows}
    drop = {extract_br_id(r.get("brId")) for r in rows} | {extract_br_id(r.get("fileName")) for r in rows}
    br_ids = set(deleted["brIds"]) - {d.lower() for d in drop if d}
    _save({"ids": list(ids), "brIds": list(br_ids)})


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def UUID_OK(value) -> bool:
    return bool(UUID_RE.match(str(value or "")))
