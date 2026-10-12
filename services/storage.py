import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

from core.config import UPLOAD_DIR

SAFE_RE = re.compile(r'[\\/:*?"<>|]+')


def safe_name(name: str) -> str:
    return SAFE_RE.sub("_", name or "file")


def bucket_dir(bucket: str) -> Path:
    path = UPLOAD_DIR.joinpath(*bucket.split("/"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(bucket: str, name: str, data: bytes) -> str:
    target = bucket_dir(bucket) / safe_name(name)
    target.write_bytes(data)
    return target.name


def save_stream(bucket: str, name: str, source, max_bytes: int, signature: bytes = b"", chunk: int = 1024 * 1024) -> int:
    target = bucket_dir(bucket) / safe_name(name)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".part")
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                block = source.read(chunk)
                if not block:
                    break
                if size == 0 and signature and not block.startswith(signature):
                    raise ValueError("File verification failed: content does not match the file type")
                size += len(block)
                if size > max_bytes:
                    raise ValueError(f"File too large (max {round(max_bytes / (1024 * 1024))}MB)")
                out.write(block)
        if size == 0:
            raise ValueError("File is empty")
        os.replace(tmp, target)
        return size
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def resolve(bucket: str, name: str) -> Optional[Path]:
    target = (bucket_dir(bucket) / safe_name(name)).resolve()
    if bucket_dir(bucket).resolve() not in target.parents or not target.is_file():
        return None
    return target


def read(bucket: str, name: str) -> Optional[bytes]:
    target = resolve(bucket, name)
    return target.read_bytes() if target else None


def remove_prefix(bucket: str, prefix: str) -> int:
    count = 0
    for item in bucket_dir(bucket).iterdir():
        if item.name.startswith(prefix):
            item.unlink(missing_ok=True)
            count += 1
    return count


def remove(bucket: str, name: str) -> None:
    target = resolve(bucket, name)
    if target:
        target.unlink(missing_ok=True)


def clear_bucket(bucket: str) -> None:
    for item in bucket_dir(bucket).iterdir():
        if item.is_file():
            item.unlink(missing_ok=True)


def prune_older_than(bucket: str, days: int) -> int:
    if days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for path in bucket_dir(bucket).iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
