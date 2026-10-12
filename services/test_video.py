import logging
from typing import Optional

from services import storage

log = logging.getLogger("talentscope")

BUCKET = "employee_test_recordings"
MIN_WEBM_BYTES = 4096
CLUSTER_MAGIC = bytes([0x1F, 0x43, 0xB6, 0x75])
EBML_MAGIC = bytes([0x1A, 0x45, 0xDF, 0xA3])


def has_ebml_header(buf: bytes) -> bool:
    return len(buf) >= 4 and buf[:4] == EBML_MAGIC


def has_cluster_data(buf: bytes) -> bool:
    return len(buf) >= 512 and CLUSTER_MAGIC in buf[: 4 * 1024 * 1024]


def is_playable(buf: bytes, min_bytes: int = MIN_WEBM_BYTES) -> bool:
    return len(buf) >= min_bytes and has_ebml_header(buf) and has_cluster_data(buf)


def repair(buf: bytes) -> bytes:
    if not buf or buf[:4] == EBML_MAGIC:
        return buf
    idx = buf.find(EBML_MAGIC, 1, min(len(buf), 512 * 1024 + 4))
    return buf[idx:] if idx > 0 else buf


def admin_url(test_id: str) -> str:
    return f"/api/admin/employee-tests/{test_id}/video"


def _name(test_id: str) -> str:
    return f"{test_id}.webm"


def save_progress(test_id: str, buf: bytes) -> bool:
    cleaned = repair(buf)
    if not has_ebml_header(cleaned) or len(cleaned) < 1024:
        return False
    try:
        storage.save(BUCKET, _name(test_id), cleaned)
        return True
    except OSError as err:
        log.error("Employee test video progress save failed for %s: %s", test_id, err)
        return False


def save(test_id: str, buf: bytes) -> bool:
    cleaned = repair(buf)
    if not is_playable(cleaned):
        return False
    try:
        storage.save(BUCKET, _name(test_id), cleaned)
        return True
    except OSError as err:
        log.error("Employee test video save failed for %s: %s", test_id, err)
        return False


def save_lenient(test_id: str, buf: bytes) -> bool:
    return save(test_id, buf) or save_progress(test_id, buf)


def read(test_id: str) -> Optional[bytes]:
    data = storage.read(BUCKET, _name(test_id))
    return repair(data) if data else None


def exists(test_id: str) -> bool:
    return storage.resolve(BUCKET, _name(test_id)) is not None


def delete(test_id: str) -> None:
    storage.remove(BUCKET, _name(test_id))


def list_ids() -> set[str]:
    return {name[:-5] for name in (p.name for p in storage.bucket_dir(BUCKET).iterdir() if p.is_file()) if name.endswith(".webm")}
