import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from core.auth import require_admin
from core.db import get_store
from core.errors import json_error, public_error
from core.validation import as_uuid
from services import employee_tests as et, test_video

router = APIRouter(prefix="/api/admin/employee-tests", tags=["admin-employee-tests"], dependencies=[Depends(require_admin)])

NAME_RE = re.compile(r"^[\w.\- ()]+$")
HEADERS = {"Content-Type": "video/webm; codecs=vp8", "Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}


@router.get("/{test_id}/attempts")
def attempts(test_id: str):
    tid = as_uuid(test_id)
    if not tid:
        return json_error(400, "Test ID is required")
    try:
        test = get_store().first("tests", {"id": tid}, ["id", "status"])
        if not test:
            return json_error(404, "Test not found")
        return {"success": True, "testId": tid, "status": test["status"], "questions": et.question_attempts_batch([tid]).get(tid, [])}
    except Exception as err:
        return public_error(err, "Failed to load test attempts")


@router.get("/{test_id}/video")
def video(test_id: str, request: Request):
    tid = as_uuid(test_id)
    data = test_video.read(tid) if tid else None
    if not data:
        return json_error(404, "Recording not found or invalid. The test may have finished before video was saved — ask the employee to retake after confirming camera access.")
    name = request.query_params.get("filename") or ""
    safe = name if NAME_RE.match(name) and name.lower().endswith(".webm") else f"{tid}.webm"
    disposition = f'{"inline" if request.query_params.get("inline") == "1" else "attachment"}; filename="{safe}"'
    size = len(data)
    header = request.headers.get("range")
    if header:
        m = re.match(r"bytes=(\d*)-(\d*)", header)
        start = int(m.group(1)) if m and m.group(1) else 0
        end = min(int(m.group(2)) if m and m.group(2) else size - 1, size - 1)
        if start > end or start >= size:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        return Response(data[start:end + 1], status_code=206,
                        headers={**HEADERS, "Content-Range": f"bytes {start}-{end}/{size}", "Content-Disposition": disposition})
    return Response(data, headers={**HEADERS, "Content-Disposition": disposition})
