from typing import Any, Optional

import logging

from services import fallback_analysis, llm

log = logging.getLogger("talentscope")

ANALYSIS_SCHEMA = """{
  "executiveSummary": "A 2-3 sentence summary of the candidate's profile.",
  "overallScore": 85,
  "atsScore": 80,
  "technicalScore": 90,
  "impactScore": 75,
  "communicationScore": 85,
  "scores": {"actionVerbs": 80, "measurability": 70, "formatting": 90, "clarity": 85, "consistency": 95, "keywordOptimization": 80},
  "weaknesses": [{"category": "impact", "severity": "high", "location": "Experience Section", "description": "Lacks quantifiable metrics in the recent role", "suggestion": "Add concrete numbers to demonstrate impact", "examples": ["Developed new feature"]}],
  "strengths": [{"category": "Technical", "description": "Strong full-stack experience", "impact": "high"}],
  "targetRoles": ["Senior Frontend Developer", "Full Stack Engineer"],
  "industryFit": [{"industry": "Software Development", "matchScore": 95, "rationale": "Extensive experience with modern web frameworks"}],
  "keywordAnalysis": {"suggestedKeywords": ["Docker", "CI/CD", "Testing"]}__JD_FIELDS__
}"""

JD_FIELDS = """,
  "suitability": "suitable",
  "jdMatchScore": 75,
  "jdMatchRationale": "Detailed 2-3 sentence reason. Must name specifically: 1. Core tech that matched, 2. Core tech/experience elements that were missing/weak, 3. Summary of experience fit." """

JD_PROMPT = """You are a principal technical recruiter and an elite CV-to-Job-Description matching engine.
Perform a highly precise, critical, and objective evaluation of the candidate's suitability for the provided Job Description (JD).

Job Description:
__JD__

Resume Text:
__TEXT__

Parsed Structure:
__PARSED__

RIGOROUS EVALUATION CRITERIA:
1. CORE VS. PREFERRED SKILLS: identify must-have (core) and nice-to-have skills in the JD. Look for evidence of these technologies in work experience. If a skill only appears in a skills dump list without experience context, reduce its matching weight by 50%.
2. RECENCY & DURATION: assess how long and how recently core skills were used.
3. ROLE LEVEL & SENIORITY FIT: compare the candidate's seniority with the JD requirements.
4. STRICT SCORING RUBRIC (BE EXTREMELY CRITICAL - DO NOT INFLATE SCORES):
   - 85-100 Exceptional Fit: meets all core and almost all secondary requirements with extensive, recent, hands-on experience at or above the required seniority.
   - 70-84 Strong Fit: meets all core requirements and some preferred skills, with recent experience.
   - 55-69 Moderate Fit: meets most core requirements but has gaps, limited depth, or non-recent usage.
   - 40-54 Weak Fit: missing major core requirements or seniority, but has basic overlapping competencies.
   - Under 40 Unsuitable: missing core requirements or severe seniority mismatch.
5. SUITABILITY: "suitable" strictly if jdMatchScore >= 40 AND the baseline core technical skills are present; otherwise "unsuitable".

Return ONLY a raw JSON object with no markdown formatting, matching this exact structure:
__SCHEMA__"""

PLAIN_PROMPT = """You are an expert technical recruiter and resume analyst.
Analyze the following resume text and parsed structure. Provide a highly accurate, critical evaluation.
Return ONLY a raw JSON object with no markdown formatting.

Resume Text:
__TEXT__

Parsed Structure:
__PARSED__

Ensure the JSON matches this exact structure:
__SCHEMA__"""


def analyze_resume(text: str, parsed: dict, jd_text: Optional[str] = None) -> dict:
    import json

    has_jd = bool(jd_text and jd_text.strip())
    schema = ANALYSIS_SCHEMA.replace("__JD_FIELDS__", JD_FIELDS if has_jd else "")
    template = JD_PROMPT if has_jd else PLAIN_PROMPT
    prompt = (template.replace("__JD__", jd_text or "").replace("__TEXT__", text[: 10000 if has_jd else 5000])
              .replace("__PARSED__", json.dumps(parsed, indent=2)).replace("__SCHEMA__", schema))
    try:
        result = llm.complete_json(prompt, temperature=0.2, max_tokens=3072, timeout_s=300)
        if not isinstance(result, dict):
            raise llm.LlmError("unexpected response shape")
        result["isLocal"] = False
        return result
    except llm.LlmError as err:
        log.warning("Qwen analysis unavailable, using the built-in rule-based fallback: %s", err)
        result = fallback_analysis.analyze_resume(text, parsed, jd_text)
        result["isLocal"] = True
        result["fallbackReason"] = str(err)[:240]
        return result


def generate_json(prompt: str, max_tokens: int = 3072, timeout_s: float = 300) -> Any:
    return llm.complete_json(prompt, temperature=0.2, max_tokens=max_tokens, timeout_s=timeout_s, priority=llm.PRIORITY_LIVE)


def generate_suggestions(analysis: dict) -> list[dict]:
    weaknesses = (analysis or {}).get("weaknesses") or []
    out = []
    for w in weaknesses:
        location = str(w.get("location") or "")
        out.append({
            "type": "modify",
            "section": "experience" if "experience" in location.lower() else "summary",
            "priority": w.get("severity"),
            "description": w.get("description") or "",
            "rationale": w.get("suggestion"),
        })
    return out
