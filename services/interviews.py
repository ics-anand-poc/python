import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from core.db import get_store
from services import ai, resumes, settings

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
DEFAULT_SECTIONS = {"overlapping": 8, "gap": 3, "projects": 4, "coding": 2}
CODING_PREFIX = "Coding Challenge:"

FALLBACK_CODING = [
    "Coding Challenge: Write a function in JavaScript to check if a string is a palindrome. The function should ignore case and non-alphanumeric characters. Include examples and edge case handling.",
    "Coding Challenge: Write a function in JavaScript that takes an array of integers and a target sum, and returns an array of indices of the two numbers that add up to the target sum (Two Sum problem).",
]
BEHAVIORAL = [
    "Describe a time when you had to work with a difficult team member or client. How did you resolve the situation?",
    "Explain a time when you made a mistake on a project. How did you address it and what did you learn?",
    "Describe a situation where you had to quickly adapt to a major change at work (e.g., new tool, team restructure).",
    "How do you prioritize your tasks when handling multiple deadlines or high-pressure projects?",
    "What motivates you in your professional career, and how do you align it with company goals?",
]
LEADERSHIP = [
    "Can you share an experience where you led a project or initiative? What was the outcome?",
    "How do you handle constructive feedback or disagreement with a supervisor's decision?",
    "Describe a time when you went above and beyond your standard job responsibilities to deliver a project.",
    "How do you mentor junior team members or share knowledge across your team?",
    "Describe a time you had to persuade stakeholders to adopt your proposed design or plan.",
]
SOFT_SKILLS = [
    "Describe a time you solved a complex problem. What steps did you take to find the solution?",
    "How do you explain technical or complex concepts to non-technical stakeholders or team members?",
    "How do you handle ambiguous requirements when starting a new task or project?",
    "Describe how you build trust and maintain strong relationships with your cross-functional partners.",
    "What strategies do you use to manage your time and avoid burnout during busy quarters?",
]


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
    if not jd_id:
        return ""
    try:
        row = get_store().first("job_descriptions", {"id": jd_id}, ["jd_text"])
        return (row or {}).get("jd_text") or ""
    except Exception as err:
        log.error("Error fetching JD: %s", err)
        return ""


def _section(config: dict, key: str, default: int) -> int:
    value = (config.get("sections") or {}).get(key)
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _question_list(raw, expected: int, label: str) -> list[str]:
    if not isinstance(raw, list) or len(raw) < expected:
        raise ValueError(f"Invalid format: expected {expected} {label}")
    out = []
    for item in raw[:expected]:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get("question"), str):
            out.append(item["question"])
        else:
            raise ValueError("Invalid question object format")
    return out


def _verbal_prompt(total: int, o: int, g: int, p: int, jd: str, resume: dict) -> str:
    return f"""You are an elite technical interviewer. Generate {total} highly specific, exclusively technical verbal interview questions tailored to the candidate's CV and the Job Description (JD).

Job Description (JD):
{jd or "No JD specified. Generate questions focusing on candidate's primary skills and experience."}

Resume Profile (CV):
{json.dumps(resume.get("parsed"), indent=2)}

Target Roles:
{json.dumps((resume.get("report") or {}).get("targetRoles") or [])}

RULES:
1. Match question depth to the seniority of the candidate shown by the JD and CV. No architecture questions for juniors, no trivia for seniors.
2. Distribution (EXACTLY {total} questions): {o} Overlapping Competencies (JD+CV Match), {g} JD-Specific / Gap Assessment (JD Skill, framed as transferability), {p} CV-Specific Projects/Experience (CV Skill).
3. Use scenarios, troubleshooting, optimization and trade-offs, not definition trivia.
4. Return ONLY a JSON array of exactly {total} objects:
[{{"question": "...", "difficulty": "Easy|Medium|Hard", "source": "JD+CV Match|JD Skill|CV Skill", "skill": "...", "expectedPoints": ["..."]}}]"""


def _coding_prompt(count: int, jd: str, resume: dict) -> str:
    return f"""You are an elite technical interviewer. Generate {count} hands-on coding challenges tailored to the candidate's CV and the Job Description (JD).

Job Description (JD):
{jd or "No JD specified. Generate coding challenges focusing on candidate's primary programming language."}

Resume Profile (CV):
{json.dumps(resume.get("parsed"), indent=2)}

RULES:
1. Match difficulty to seniority. Challenges must be real programming tasks ("Write a function that..."), never conceptual questions.
2. Infer the primary language from the JD/CV. Supported: JavaScript, TypeScript, Python, C++, Java. Name the language explicitly and give a matching starter signature.
3. Each question must start with 'Coding Challenge: ' and contain a problem description, input/output, constraints, at least 2 examples, and the starter signature.
4. Return ONLY a JSON array of exactly {count} objects:
[{{"question": "Coding Challenge: ...", "difficulty": "Easy|Medium|Hard", "source": "JD+CV Match", "skill": "Algorithms", "expectedPoints": ["..."]}}]"""


def _non_tech_prompt(total: int, b: int, l: int, s: int, jd: str, resume: dict) -> str:
    return f"""You are an elite HR interviewer. Generate {total} professional non-technical verbal interview questions tailored to the candidate's CV and the Job Description (JD).

Job Description (JD):
{jd or "No JD specified."}

Resume Profile (CV):
{json.dumps(resume.get("parsed"), indent=2)}

RULES:
1. Adjust to candidate seniority.
2. Distribution (EXACTLY {total}): {b} Behavioral, {l} Leadership & Collaboration, {s} Problem Solving & Soft Skills.
3. Frame as behavioral/situational prompts ("Tell me about a time when...").
4. Return ONLY a JSON array of exactly {total} objects:
[{{"question": "...", "difficulty": "Easy|Medium|Hard", "source": "Behavioral|Leadership|Soft Skills", "skill": "...", "expectedPoints": ["..."]}}]"""


def _ai_questions(resume: dict, config: dict, jd: str, include_tech: bool, include_non_tech: bool) -> list[str]:
    questions: list[str] = []
    if include_tech:
        o, g = _section(config, "overlapping", 8), _section(config, "gap", 3)
        p, c = _section(config, "projects", 4), _section(config, "coding", 2)
        total = o + g + p
        questions += _question_list(ai.generate_json(_verbal_prompt(total, o, g, p, jd, resume)), total, "verbal questions")
        if c > 0:
            questions += _question_list(ai.generate_json(_coding_prompt(c, jd, resume)), c, "coding challenges")
    if include_non_tech:
        b, l, s = _section(config, "behavioral", 5), _section(config, "leadership", 5), _section(config, "softskills", 5)
        questions += _question_list(ai.generate_json(_non_tech_prompt(b + l + s, b, l, s, jd, resume)), b + l + s, "non-technical questions")
    if not questions:
        raise ValueError("No questions generated for the selected assessment focus.")
    return questions


def _fallback_questions(resume: dict, config: dict, jd: str, include_tech: bool, include_non_tech: bool) -> list[str]:
    questions: list[str] = []
    if include_tech:
        o, g = _section(config, "overlapping", 8), _section(config, "gap", 3)
        p, c = _section(config, "projects", 4), _section(config, "coding", 2)
        skills = resume.get("parsed", {}).get("skills") or {}
        all_skills = [*(skills.get("technical") or []), *(skills.get("tools") or [])]
        primary, secondary, tertiary = "JavaScript", "React", "SQL"
        if jd:
            overlap = [s for s in all_skills if s.lower() in jd.lower()]
            picks = overlap
        else:
            picks = all_skills
        if len(picks) > 0:
            primary = picks[0]
        if len(picks) > 1:
            secondary = picks[1]
        if len(picks) > 2:
            tertiary = picks[2]
        projects = resume.get("parsed", {}).get("projects") or []
        project = (projects[0].get("name") if projects else None) or "a recent project"
        defaults = [
            f"Can you explain a challenging scenario you faced while working on {project}?",
            f"How does {primary} handle memory management and concurrency in production environments?",
            f"What are the most common performance bottlenecks you've encountered with {primary} and how did you resolve them?",
            "Describe a time you had to optimize a slow database query or search process. What was the underlying issue?",
            "How do you ensure the code quality, unit testing, and scalability of the features you write?",
            f"Can you explain the architecture of a complex system you built or contributed to using {secondary}?",
            f"How would you design a scalable microservices architecture or component structure using {secondary} for a high-traffic app?",
            f"Explain the concept of CI/CD and how you've implemented or interacted with it for {primary} deployments.",
            f"What design patterns do you most frequently use in {primary} and why?",
            "How do you approach debugging a critical production issue where logging is minimal or absent?",
            f"Explain how you handle global or local state management and consistency in a large application using {secondary}.",
            f"What security vulnerabilities do you proactively look for when writing or reviewing code in {primary}?",
            f"Describe how you would approach migrating a legacy feature or application using {tertiary} to a modern stack.",
            "Describe your approach to containerizing an application using Docker. What are the benefits of multi-stage builds?",
            "How do you handle secrets management and environment configurations securely in a cloud deployment?",
        ]
        questions += [defaults[i % len(defaults)] for i in range(o + g + p)]
        questions += [FALLBACK_CODING[i % len(FALLBACK_CODING)] for i in range(c)]
    if include_non_tech:
        b, l, s = _section(config, "behavioral", 5), _section(config, "leadership", 5), _section(config, "softskills", 5)
        questions += [BEHAVIORAL[i % 5] for i in range(b)] + [LEADERSHIP[i % 5] for i in range(l)] + [SOFT_SKILLS[i % 5] for i in range(s)]
    return questions


def generate_questions(resume_id: str) -> list[str]:
    resume = resumes.get_resume(resume_id)
    if not resume:
        raise LookupError("Resume not found")
    report = resume.get("report") or {}
    config = report.get("interviewConfig") or {"interviewType": "technical", "sections": dict(DEFAULT_SECTIONS)}
    kind = config.get("interviewType") or "technical"
    include_tech = kind in ("technical", "both")
    include_non_tech = kind in ("non-technical", "both")
    jd = job_description_text(report.get("jdId"))
    try:
        questions = _ai_questions(resume, config, jd, include_tech, include_non_tech)
    except Exception as err:
        log.warning("Failed to generate questions with Qwen, using dynamic defaults: %s", err)
        questions = _fallback_questions(resume, config, jd, include_tech, include_non_tech)
    rows = [{"resume_id": resume_id, "question_index": i, "question_text": q} for i, q in enumerate(questions)]
    try:
        get_store().insert("interview_questions", rows)
    except Exception as err:
        log.error("Error inserting questions: %s", err)
    return questions


def get_questions(resume_id: str) -> list[str]:
    existing = get_store().select("interview_questions", {"resume_id": resume_id}, ["question_text"], "question_index asc")
    if existing:
        return [r["question_text"] for r in existing]
    return generate_questions(resume_id)


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
