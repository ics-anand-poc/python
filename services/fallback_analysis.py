import math
import re
from typing import Any, Optional

WEAK_VERBS = ["responsible for", "helped with", "assisted in", "worked on", "involved in", "duties included", "job was",
              "tasked with", "had to", "needed to"]
STRONG_VERBS = {
    "leadership": ["led", "directed", "orchestrated", "spearheaded", "championed", "mentored"],
    "technical": ["engineered", "architected", "developed", "implemented", "optimized", "deployed"],
    "business": ["increased", "reduced", "improved", "streamlined", "accelerated", "generated"],
    "creative": ["designed", "crafted", "innovated", "revolutionized", "transformed"],
}
ALL_STRONG = [v for group in STRONG_VERBS.values() for v in group]
METRIC_PATTERNS = [
    re.compile(r"\d+%"), re.compile(r"\$[\d,]"),
    re.compile(r"[\d,]+(?:users?|clients?|customers?|projects?|applications?)", re.I),
    re.compile(r"[\d,]+(?:months?|years?|weeks?|days?)", re.I), re.compile(r"team of \d+", re.I),
    re.compile(r"[\d,]+(?:increase|decrease|growth)", re.I),
]
PASSIVE = [re.compile(p, re.I) for p in (r"was\s+\w+ed", r"were\s+\w+ed", r"has\s+been", r"have\s+been", r"had\s+been",
                                          r"is\s+\w+ed", r"are\s+\w+ed", r"be\s+\w+ed")]
REDUNDANT = ["in order to", "in an effort to", "at this point in time", "due to the fact that", "for the purpose of",
             "with regards to", "in the process of"]
BULLET_START = re.compile(r"^(led|developed|created|managed|designed|implemented|improved|increased)", re.I)
BULLET_MARKER = re.compile(r"^[•\-*‣⁃]\s*")
OUTCOMES = ["resulted in", "led to", "improved", "increased", "decreased", "reduced", "saved", "generated", "achieved"]
JD_SKILLS = ["javascript", "typescript", "python", "react", "vue", "angular", "node", "express", "java", "spring", "c#", ".net",
             "go", "rust", "php", "docker", "kubernetes", "aws", "azure", "gcp", "postgresql", "mongodb", "mysql", "redis", "git",
             "ci/cd", "html", "css", "sass", "webpack", "linux", "bash", "next.js", "nextjs", "tailwind", "tailwindcss",
             "rest api", "graphql", "devops", "machine learning", "ai", "llm"]
SCORE_KEYWORDS = ["javascript", "python", "react", "node", "typescript", "java", "aws", "docker", "kubernetes", "postgresql",
                  "mongodb", "git", "agile", "scrum", "ci/cd", "api", "rest", "graphql", "html", "css", "sql", "nosql", "linux", "devops"]
TECH_TERMS = ["algorithm", "architecture", "framework", "library", "api", "database", "backend", "frontend", "full-stack", "deployment",
              "testing", "security", "scalability", "performance", "optimization", "microservices", "restful", "cloud", "infrastructure",
              "pipeline", "ci/cd", "containerization", "orchestration", "machine learning", "analytics", "data modeling", "agile", "scrum"]
DEEP_TERMS = ["designed", "architected", "implemented", "built from scratch", "proprietary", "invented", "patent", "published",
              "open source", "contributed", "spearheaded", "mentored", "led"]


def js_round(value: float) -> int:
    return int(math.floor(value + 0.5))


def tokenize(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", re.sub(r"[^\w\s]", "", text.lower())) if w]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def extract_bullets(text: str) -> list[str]:
    out = []
    for line in text.split("\n"):
        trimmed = line.strip()
        if trimmed.startswith(("•", "-", "*")) or BULLET_START.match(trimmed):
            out.append(BULLET_MARKER.sub("", line).strip())
    return out


def has_metric(text: str) -> bool:
    return any(p.search(text) for p in METRIC_PATTERNS)


def score_action_verbs(bullets: list[str]) -> int:
    if not bullets:
        return 50
    strong = total = 0
    for bullet in bullets:
        lower = bullet.lower()
        weak = any(lower.startswith(v) for v in WEAK_VERBS)
        has_strong = any(f" {v} " in lower or lower.startswith(v + " ") for v in ALL_STRONG)
        if not weak:
            total += 1
        if has_strong:
            strong += 1
    return js_round(strong / max(total, 1) * 100) if total else 50


def score_measurability(bullets: list[str]) -> int:
    if not bullets:
        return 50
    return js_round(sum(1 for b in bullets if has_metric(b)) / len(bullets) * 100)


def score_formatting(text: str, sections: dict) -> int:
    score = 100
    lines = text.split("\n")
    if sum(1 for ln in lines if ln.strip() == "") > len(lines) * 0.3:
        score -= 20
    essential = ["experience", "education", "skills"]
    if not all(sections.get(s) or s in text.lower() for s in essential):
        score -= 30
    if sum(1 for ln in lines if len(ln) > 120) > 5:
        score -= 15
    return max(0, score)


def score_clarity(sentences: list[str]) -> int:
    if not sentences:
        return 50
    issues = 0
    for sentence in sentences:
        lower = sentence.lower()
        if any(p.search(lower) for p in PASSIVE):
            issues += 1
        if any(phrase in lower for phrase in REDUNDANT):
            issues += 1
        if len(sentence) > 200:
            issues += 1
    return js_round((1 - issues / (len(sentences) * 2)) * 100)


def score_keywords(text: str, sections: dict) -> int:
    lower = text.lower()
    found = sum(1 for k in SCORE_KEYWORDS if k in lower)
    score = found / len(SCORE_KEYWORDS) * 100
    if sections.get("skills"):
        score *= 1.5
    return min(100, js_round(score))


def score_consistency(text: str) -> int:
    patterns = [r"\d{4}\s*-\s*\d{4}", r"\d{2}/\d{2}/\d{4}", r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}"]
    formats = sum(1 for p in patterns if re.search(p, text, re.I))
    return 80 if formats > 2 else 100


def overall_score(text: str, sections: dict, bullets: list[str]) -> int:
    parts = [score_action_verbs(bullets) * 0.20, score_measurability(bullets) * 0.20, score_formatting(text, sections) * 0.15,
             score_clarity(split_sentences(text)) * 0.15, score_keywords(text, sections) * 0.20, score_consistency(text) * 0.10]
    return js_round(sum(parts))


def ats_score(text: str, sections: dict) -> int:
    score = 40
    if sections.get("skills") and any(sections["skills"].values()):
        score += 15
    if sections.get("experience"):
        score += 20
    if sections.get("education"):
        score += 15
    if sections.get("summary"):
        score += 10
    personal = sections.get("personal") or {}
    if personal.get("email") or personal.get("phone"):
        score += 10
    if len(re.findall(r"    ", text)) > 10:
        score -= 10
    trimmed = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 10]
    duplicates = sum(1 for i, ln in enumerate(trimmed) if trimmed.index(ln) != i)
    if duplicates > 2:
        score -= 15
    return max(0, min(100, js_round(score)))


def technical_score(text: str, sections: dict) -> int:
    lower = text.lower()
    score = 20.0
    score += min(40, sum(1 for t in TECH_TERMS if t in lower) * 3.5)
    score += min(25, sum(1 for t in DEEP_TERMS if t in lower) * 5)
    technical = (sections.get("skills") or {}).get("technical")
    if technical:
        score += min(15, len(technical) * 1.5)
    return max(0, min(100, js_round(score)))


def communication_score(sentences: list[str], bullets: list[str]) -> int:
    score = 100
    if not sentences:
        return score
    joined = " ".join(sentences + bullets).lower()
    fillers = sum(len(re.findall(rf"\b{w}\b", joined)) for w in ("basically", "actually", "literally", "very", "really", "just", "stuff", "things"))
    if fillers > 5:
        score -= 20
    average = sum(len(s) for s in sentences) / len(sentences)
    if average < 8:
        score -= 15
    if average > 40:
        score -= 15
    proper = sum(1 for s in sentences if s and s[0] == s[0].upper())
    if proper / len(sentences) < 0.9:
        score -= 20
    return max(0, score)


def project_score(sections: dict) -> int:
    projects = sections.get("projects") or []
    if not projects:
        return 30
    score = 65
    for project in projects:
        bullets = project.get("bulletPoints") or []
        if any("used " in b.lower() or "technology " in b.lower() for b in bullets):
            score += 5
        if any(has_metric(b) for b in bullets):
            score += 10
    return min(100, score)


def impact_score(bullets: list[str]) -> int:
    if not bullets:
        return 30
    total = 0
    for bullet in bullets:
        lower = bullet.lower()
        value = 20
        if has_metric(bullet):
            value += 35
        if any(lower.startswith(v) or f" {v} " in lower for v in ALL_STRONG):
            value += 25
        if any(o in lower for o in OUTCOMES):
            value += 20
        total += min(100, value)
    return max(0, min(100, js_round(total / len(bullets))))


def detect_weaknesses(text: str, sections: dict, bullets: list[str]) -> list[dict]:
    out: list[dict] = []
    weak_found, no_metric = [], []
    for idx, bullet in enumerate(bullets):
        lower = bullet.lower()
        if any(lower.startswith(v) for v in WEAK_VERBS):
            weak_found.append(bullet)
        if not has_metric(bullet):
            no_metric.append(bullet)
        if len(bullet) > 200:
            out.append({"category": "format", "severity": "medium", "location": f"Bullet {idx + 1}",
                        "description": "Bullet point too long (>200 chars)", "suggestion": "Split into two focused bullet points",
                        "examples": [bullet[:100] + "..."]})
    if weak_found:
        out.append({"category": "communication", "severity": "high" if len(weak_found) > 3 else "medium", "location": "Experience Section",
                    "description": f"Found {len(weak_found)} bullet point(s) starting with weak or passive verbs.",
                    "suggestion": "Start bullet points with strong action verbs (e.g., led, developed, increased) to show ownership.",
                    "examples": weak_found[:2]})
    if no_metric:
        out.append({"category": "impact", "severity": "high" if len(no_metric) > 3 else "medium", "location": "Experience Section",
                    "description": f"Found {len(no_metric)} bullet point(s) lacking quantifiable metrics.",
                    "suggestion": "Quantify your impact using numbers, percentages, or dollar amounts to make achievements concrete.",
                    "examples": no_metric[:2]})
    if not sections.get("summary") and "summary" not in text.lower():
        out.append({"category": "format", "severity": "high", "location": "Top of resume", "description": "Missing professional summary",
                    "suggestion": "Add 3-4 line professional summary highlighting key achievements", "examples": []})
    personal = sections.get("personal")
    if personal is not None:
        if not personal.get("email") and not personal.get("phone"):
            out.append({"category": "format", "severity": "high", "location": "Header",
                        "description": "Missing critical contact information (email or phone)",
                        "suggestion": "Ensure your email and phone number are clearly visible at the top", "examples": []})
        if not personal.get("linkedin") and not personal.get("github"):
            out.append({"category": "format", "severity": "medium", "location": "Header", "description": "Missing professional links",
                        "suggestion": "Add a link to your LinkedIn profile or portfolio", "examples": []})
    lower_text = text.lower()
    for word in ("expert in", "mastered", "guru", "ninja", "visionary", "world-class"):
        if word in lower_text:
            out.append({"category": "content", "severity": "medium", "location": "General",
                        "description": f"Use of grandiose or subjective terms ('{word}')",
                        "suggestion": "Replace subjective claims with objective achievements and metrics", "examples": [word]})
    return out


def detect_strengths(text: str, sections: dict, bullets: list[str]) -> list[dict]:
    out: list[dict] = []
    lower = text.lower()
    if sum(1 for b in bullets if any(v in b.lower() for v in ALL_STRONG)) > len(bullets) * 0.4:
        out.append({"category": "Communication", "description": "Uses strong action verbs effectively to describe responsibilities.", "impact": "medium"})
    if sum(1 for b in bullets if has_metric(b)) > len(bullets) * 0.3:
        out.append({"category": "Impact", "description": "Exceptional use of quantifiable metrics across professional experiences.", "impact": "high"})
    terms = ["framework", "api", "database", "backend", "frontend", "cloud", "pipeline", "deployment", "ai", "ml", "machine learning", "llm", "rag"]
    if sum(1 for t in terms if t in lower) >= 4:
        out.append({"category": "Technical", "description": "Deep expertise in modern technical stacks, tools, and systems.", "impact": "high"})
    leadership = ["led", "directed", "managed", "orchestrated", "spearheaded", "mentored", "coordinated"]
    if sum(1 for t in leadership if t in lower) >= 2:
        out.append({"category": "Leadership", "description": "Proven ability to lead projects, guide teams, and coordinate delivery.", "impact": "medium"})
    return out or [{"category": "Structure", "description": "Clear and standard resume formatting with solid sections.", "impact": "low"}]


def syllables(word: str) -> int:
    word = word.lower()
    if len(word) <= 3:
        return 1
    if re.match(r"^[aeiou]+", word) or re.search(r"[aeiou]{2,}", word):
        return 2
    return math.ceil(len(word) / 2.5)


def readability(sentences: list[str], words: list[str]) -> dict:
    if not sentences or not words:
        return {"fleschReadingEase": 50, "averageSentenceLength": 15, "passiveVoiceCount": 0, "jargonCount": 0, "readingTime": 1}
    avg_len = len(words) / len(sentences)
    avg_syll = sum(syllables(w) for w in words) / len(words)
    flesch = 206.835 - 1.015 * avg_len - 84.6 * avg_syll
    buzz = {"synergy", "leverage", "holistic", "paradigm", "streamline", "bandwidth"}
    return {
        "fleschReadingEase": js_round(max(0, min(100, flesch))), "averageSentenceLength": js_round(avg_len * 10) / 10,
        "passiveVoiceCount": sum(1 for s in sentences if any(p.search(s) for p in PASSIVE)),
        "jargonCount": sum(1 for w in words if w.lower() in buzz), "readingTime": math.ceil(len(words) / 200),
    }


def analyze_keywords(text: str) -> dict:
    lower = text.lower()
    industries = {"software": ["javascript", "python", "react", "node", "api", "database", "git", "agile"],
                  "data": ["sql", "python", "analytics", "visualization", "etl", "warehouse", "tableau"],
                  "design": ["ui", "ux", "figma", "sketch", "prototyping", "wireframe", "responsive"]}
    matched, missing = [], []
    for keywords in industries.values():
        for keyword in keywords:
            (matched if keyword in lower else missing).append(keyword)
    role = next((t for t in ("full stack", "frontend", "backend", "devops", "manager") if t in lower), None)
    counts: dict[str, int] = {}
    for word in tokenize(lower):
        if len(word) > 4:
            counts[word] = counts.get(word, 0) + 1
    total = len(matched) + len(missing)
    return {
        "matchedKeywords": list(dict.fromkeys(matched)), "missingKeywords": list(dict.fromkeys(missing))[:10],
        "overusedKeywords": [w for w, c in counts.items() if c >= 3][:5],
        "industryRelevance": js_round(len(matched) / total * 100) if total else 0,
        "suggestedKeywords": [role, "collaboration", "problem-solving"] if role else [],
    }


def _jd_match(text: str, words: list[str], jd_text: str) -> dict:
    lower_jd, lower_text = jd_text.lower(), text.lower()
    jd_keywords = [s for s in JD_SKILLS if s in lower_jd]
    resume_keywords = [s for s in JD_SKILLS if s in lower_text]
    skill_score, matched_skills = 50, []
    if jd_keywords:
        matched_skills = [k for k in jd_keywords if k in resume_keywords]
        skill_score = js_round(len(matched_skills) / len(jd_keywords) * 100)
    jd_words = {w for w in tokenize(jd_text) if len(w) > 4}
    resume_words = set(words)
    matches = sum(1 for w in jd_words if w in resume_words)
    overlap = min(100, js_round(matches / len(jd_words) * 100)) if jd_words else 50
    score = js_round(skill_score * 0.65 + overlap * 0.35) if jd_keywords else overlap
    rationale = (
        f"Matched {len(matched_skills)} of {len(jd_keywords)} core JD skills ({', '.join(matched_skills)}). "
        f"Vocabulary overlap matched {matches} keywords. Strict calculated compatibility: {score}%."
        if jd_keywords else
        f"Vocabulary overlap matched {matches} out of {len(jd_words)} unique keywords in the Job Description. Calculated match score: {score}%."
    )
    return {"suitability": "suitable" if score >= 40 else "unsuitable", "jdMatchScore": score, "jdMatchRationale": rationale}


def analyze_resume(text: str, sections: dict, jd_text: Optional[str] = None) -> dict[str, Any]:
    words = tokenize(text)
    sentences = split_sentences(text)
    bullets = extract_bullets(text)
    result = {
        "overallScore": overall_score(text, sections, bullets), "atsScore": ats_score(text, sections),
        "technicalScore": technical_score(text, sections), "communicationScore": communication_score(sentences, bullets),
        "projectQualityScore": project_score(sections), "impactScore": impact_score(bullets),
        "scores": {"actionVerbs": score_action_verbs(bullets), "measurability": score_measurability(bullets),
                   "formatting": score_formatting(text, sections), "clarity": score_clarity(sentences),
                   "consistency": score_consistency(text), "keywordOptimization": score_keywords(text, sections)},
        "weaknesses": detect_weaknesses(text, sections, bullets), "strengths": detect_strengths(text, sections, bullets),
        "readability": readability(sentences, words), "keywordAnalysis": analyze_keywords(text),
    }
    if jd_text and jd_text.strip():
        result.update(_jd_match(text, words, jd_text))
    return result
