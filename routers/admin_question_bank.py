from fastapi import APIRouter, Body, Depends

from core.auth import require_permission
from core.db import get_store
from core.errors import json_error, public_error
from core.validation import as_uuid
from services import question_gen, question_queue

router = APIRouter(prefix="/api/admin/question-bank", tags=["question-bank"], dependencies=[Depends(require_permission("adminControls"))])


def _summary() -> dict:
    question_gen.reset_bank_cache()
    rows = question_gen.bank_rows()
    stored: dict[str, dict] = {}
    for row in rows:
        entry = stored.setdefault(row["bank_key"], {"verbal": 0, "coding": 0})
        entry[row["kind"]] = entry.get(row["kind"], 0) + 1
    preset = question_gen.preset_bank()
    return {"queue": question_queue.snapshot(), "generated": stored,
            "preset": {"verbal": {k: len(v) for k, v in preset["verbal"].items()}, "coding": {k: len(v) for k, v in preset["coding"].items()}}}


@router.get("")
def overview():
    try:
        return _summary()
    except Exception as err:
        return public_error(err, "Failed to read the question bank")


@router.post("/pregenerate")
def pregenerate(body: dict = Body(default_factory=dict)):
    keys = body.get("keys") if isinstance(body.get("keys"), list) else []
    jd_id = body.get("jdId")
    if jd_id:
        keys = [*keys, *question_gen.bank_keys_for(question_gen.jd_text(str(jd_id)))]
    allowed = {*question_gen.SUPPORTED, "sql", "devops", "testing", "general"}
    clean = [k for k in dict.fromkeys(str(k).strip().lower() for k in keys) if k in allowed]
    if not clean:
        return json_error(400, "Provide keys (python, javascript, typescript, java, cpp, sql, devops, testing, general) or a jdId")
    for key in clean:
        question_queue.enqueue_bank(key)
    return {"success": True, "queued": clean}


@router.post("/warm")
def warm(body: dict = Body(default_factory=dict)):
    raw = body.get("resumeIds") if isinstance(body.get("resumeIds"), list) else []
    ids = [i for i in (as_uuid(str(r)) for r in raw[:500]) if i]
    if not ids:
        return json_error(400, "Provide resumeIds")
    store = get_store()
    queued = []
    for rid in ids:
        if not store.first("resumes", {"id": rid}, ["id"]) or question_queue.existing_questions(rid):
            continue
        question_queue.enqueue(rid, force=bool(body.get("force")))
        queued.append(rid)
    return {"success": True, "queued": len(queued)}
