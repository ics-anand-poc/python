import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from core.db import get_store
from services import ai, question_gen, question_queue, resumes, settings

log = logging.getLogger("talentscope")

TEMPLATES = [
    "//javascriptcodetemplatefunctionsolution(){//writeyourcodeherereturn;}",
    "functionsolution(){//writeyourcodeherereturn;}",
    "//typescriptcodetemplatefunctionsolution():void{//writeyourcodeherereturn;}",
    "functionsolution():void{//writeyourcodeherereturn;}",
    "#pythoncodetemplatedefsolution():#writeyourcodeherepass",
    "defsolution():#writeyourcodeherepass",
    "defsolution():pass",
    "//c++codetemplate#include<iostream>usingnamespacestd;voidsolution(){//writeyourcodehere}",
    "voidsolution(){//writeyourcodehere}",
    "//javacodetemplatepublicclasssolution{publicstaticsoidsolution(){//writeyourcodehere}}",
    "publicclasssolution{publicstaticsoidsolution(){//writeyourcodehere}}",
    "publicclasssolution{publicstaticsoidmain(string[]args){}}",
]
BOILERPLATES = {
    "functionsolution(){return;}", "functionsolution():void{return;}", "defsolution():pass", "defsolution():",
    "voidsolution(){}", "publicclasssolution{publicstaticsoidsolution(){}}",
}
LOW_QUALITY = {"dontknow", "idontknow", "noidea", "notsure", "na", "none", "nothing", "skip", "skype"}
CODING_PREFIX = "Coding Challenge:"


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def is_default_template_or_empty(answer: str) -> bool:
    if _squash(answer) in TEMPLATES:
        return True
    clean = re.sub(r"/\*[\s\S]*?\*/", "", answer)
    clean = re.sub(r"//.*", "", clean)
    clean = re.sub(r"#.*", "", clean)
    clean = re.sub(r"\s+", "", clean)
    return len(clean) == 0 or clean in BOILERPLATES


def is_wrong_language(question: str, answer: str) -> bool:
    q = question.lower()
    if "javascript" in q or "typescript" in q:
        if re.search(r"def\s+\w+\s*\(", answer) or re.search(r"#\s*(python|code|template)", answer, re.I):
            return True
    if "python" in q:
        if re.search(r"function\s+\w+\s*\(", answer) or re.search(r"//\s*(javascript|typescript|code|template)", answer, re.I):
            return True
    return False


def heuristic_evaluation(question: str, answer: str) -> Optional[dict]:
    trimmed = answer.strip()
    is_coding = question.startswith(CODING_PREFIX)
    if trimmed in ("", "-"):
        return {"score": 0, "feedback": "No code solution was provided." if is_coding else "No response was provided."}
    normalized = re.sub(r"[^a-z0-9]", "", trimmed.lower().replace("'", ""))
    normalized_q = re.sub(r"[^a-z0-9]", "", question.lower())
    if not is_coding and normalized in normalized_q and len(normalized) > 10:
        return {"score": 1, "feedback": "Answer is invalid as it only repeats the question or prompt instructions."}
    if not is_coding:
        words = [w for w in re.split(r"\s+", trimmed) if w]
        if normalized in LOW_QUALITY or len(words) <= 2:
            return {"score": 1, "feedback": f'Answer is too brief, off-topic, or indicates a lack of response ("{trimmed}").'}
    if is_coding:
        if is_default_template_or_empty(answer):
            return {"score": 1, "feedback": "Code solution was not attempted; only the default template boilerplate was submitted."}
        if is_wrong_language(question, answer):
            return {"score": 1, "feedback": "The template/code for the wrong programming language was submitted, and no solution was provided in the requested language."}
        if len(trimmed) < 15:
            return {"score": 1, "feedback": "Code solution is too brief or incomplete to be evaluated."}
    return None


def job_description_text(jd_id: Optional[str]) -> str:
    return question_gen.jd_text(jd_id)


def get_questions(resume_id: str) -> list[str]:
    if not resumes.get_resume(resume_id):
        raise LookupError("Resume not found")
    return question_queue.ensure_sync(resume_id)


def _eval_prompt(question: str, answer: str, resume: Optional[dict], jd: str) -> str:
    cv = json.dumps(resume.get("parsed"), indent=2) if resume else "Not specified."
    if question.startswith(CODING_PREFIX):
        return f"""You are an elite technical interviewer and expert code reviewer. Evaluate the candidate's code submission.

Job Description (JD):
{jd or "Not specified."}

Candidate's CV / Experience Level:
{cv}

Coding Challenge Asked: "{question}"
Candidate's Submitted Code Solution:
```
{answer}
```

INSTRUCTIONS:
1. Rate the solution from 1 to 10. Be extremely critical.
2. Score 0 or 1 for empty code, default boilerplate, wrong-language code, or comments/stubs only.
3. Calibrate expectations to the candidate's seniority.
4. Review correctness, logic, efficiency (Big O) and formatting.
5. Give 1-2 sentences of constructive feedback.

Return ONLY a JSON object: {{"score": 8, "feedback": "..."}}"""
    roles = json.dumps((resume.get("report") or {}).get("targetRoles") or []) if resume else "Not specified."
    return f"""You are an elite technical interviewer evaluating a candidate's verbal response.

Job Description (JD):
{jd or "Not specified."}

Candidate's CV / Professional Experience:
{cv}

Target Roles:
{roles}

Question asked: "{question}"
Candidate's Answer: "{answer}"

INSTRUCTIONS:
1. Rate the answer from 1 to 10. Be extremely critical and do not inflate scores.
2. Score 0 or 1 for empty answers, one- or two-word replies, off-topic replies, or answers that only repeat the question.
3. Calibrate expectations to the candidate's seniority.
4. Verify technical accuracy, depth and relevance.
5. Give 1-2 sentences of concise feedback.

Return ONLY a JSON object: {{"score": 8, "feedback": "..."}}"""


def _fallback_score(question: str, answer: str) -> tuple[int, str]:
    size = len(answer.strip())
    if question.startswith(CODING_PREFIX):
        return (7, "Code solution submitted. Basic structure and logic appear complete.") if size > 100 else (3, "Code solution was too brief or incomplete.")
    if size > 150:
        return 8, "Detailed answer provided. Ensure your points remain concise and relevant."
    if size > 50:
        return 6, "Acceptable answer, but could benefit from more specific technical details."
    return 3, "Answer was too brief. Try to use the STAR method to provide complete examples."


def evaluate_answer(resume_id: str, question_index: int, question: str, answer: str) -> None:
    score, feedback = 5, "Answer recorded."
    heuristic = heuristic_evaluation(question, answer)
    if heuristic:
        score, feedback = heuristic["score"], heuristic["feedback"]
    else:
        try:
            resume = resumes.get_resume(resume_id)
            jd = job_description_text((resume or {}).get("report", {}).get("jdId")) if resume else ""
            result = ai.generate_json(_eval_prompt(question, answer, resume, jd), max_tokens=512, timeout_s=300)
            if isinstance(result, dict) and isinstance(result.get("score"), (int, float)) and isinstance(result.get("feedback"), str):
                score, feedback = int(round(result["score"])), result["feedback"]
        except Exception as err:
            log.warning("Failed to evaluate answer with Qwen, using fallback: %s", err)
            score, feedback = _fallback_score(question, answer)
    get_store().insert("interview_attempts", {
        "resume_id": resume_id, "question_index": question_index, "question_text": question,
        "candidate_answer": answer, "mock_score": max(0, min(10, score)), "mock_feedback": feedback,
    })


SUBMIT_GRACE_S = 60


def _parse_time(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def duration_minutes(resume: Optional[dict]) -> int:
    configured = (((resume or {}).get("report") or {}).get("interviewConfig") or {}).get("durationMinutes")
    default = settings.get_interview_defaults()["durationMinutes"]
    return settings.clamp_duration(configured, default) if configured else default


def _started_at(resume_id: str, resume: Optional[dict]) -> Optional[datetime]:
    row = None
    try:
        row = get_store().first("candidate_interview_data", {"id": resume_id}, ["interview_started_at"])
    except Exception as err:
        log.warning("candidate_interview_data read failed: %s", err)
    started = _parse_time((row or {}).get("interview_started_at"))
    return started or _parse_time(((resume or {}).get("report") or {}).get("interviewStartedAt"))


def timing(resume_id: str) -> dict:
    resume = resumes.get_resume(resume_id)
    total = duration_minutes(resume) * 60
    started = _started_at(resume_id, resume)
    now = datetime.now(timezone.utc)
    remaining = total if not started else max(0, int(total - (now - started).total_seconds()))
    return {"durationSeconds": total, "startedAt": started.isoformat() if started else None,
            "remainingSeconds": remaining, "serverNow": now.isoformat()}


def mark_started(resume_id: str) -> dict:
    existing = timing(resume_id)
    if existing["startedAt"]:
        return existing
    now = datetime.now(timezone.utc).isoformat()
    store = get_store()
    saved = False
    try:
        saved = bool(store.update("candidate_interview_data", {"interview_started_at": now}, {"id": resume_id}))
    except Exception as err:
        log.warning("candidate_interview_data update failed, falling back: %s", err)
    if not saved:
        resume = resumes.get_resume(resume_id, True)
        if resume:
            resume["report"] = {**(resume.get("report") or {}), "interviewStartedAt": now}
            resumes.save_row(resume)
    return timing(resume_id)


def is_expired(resume_id: str) -> bool:
    info = timing(resume_id)
    started = _parse_time(info["startedAt"])
    if not started:
        return False
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return elapsed > info["durationSeconds"] + SUBMIT_GRACE_S
