from services import ai, fallback_analysis as fb, llm, resumes
from tests.test_resumes import SAMPLE


def test_fallback_scores_and_jd_match():
    parsed = resumes.parse_structure(SAMPLE)
    plain = fb.analyze_resume(SAMPLE, parsed)
    assert 0 <= plain["overallScore"] <= 100 and set(plain["scores"]) == {
        "actionVerbs", "measurability", "formatting", "clarity", "consistency", "keywordOptimization"}
    assert "suitability" not in plain and plain["strengths"] and isinstance(plain["weaknesses"], list)
    match = fb.analyze_resume(SAMPLE, parsed, "We need Python, Docker and AWS experience")
    assert match["jdMatchScore"] >= 40 and match["suitability"] == "suitable" and "python" in match["jdMatchRationale"]
    miss = fb.analyze_resume(SAMPLE, parsed, "Rust, Kubernetes, GraphQL, PHP, Spring expert required")
    assert miss["suitability"] == "unsuitable"


def test_fallback_rules():
    bullets = fb.extract_bullets("• Responsible for tests\n- Led a team of 5 to improve latency by 40%\nplain line")
    assert bullets == ["Responsible for tests", "Led a team of 5 to improve latency by 40%"]
    assert fb.score_measurability(bullets) == 50
    weak = fb.detect_weaknesses("text", {"personal": {}}, bullets)
    assert any(w["category"] == "communication" for w in weak) and any("contact" in w["description"] for w in weak)


def test_analyze_resume_uses_qwen_then_falls_back(monkeypatch):
    parsed = resumes.parse_structure(SAMPLE)
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"overallScore": 91, "weaknesses": []})
    ok = ai.analyze_resume(SAMPLE, parsed)
    assert ok["overallScore"] == 91 and ok["isLocal"] is False

    def down(*a, **k):
        raise llm.LlmError("Local Qwen is not running")

    monkeypatch.setattr(llm, "complete_json", down)
    fallback = ai.analyze_resume(SAMPLE, parsed, "python developer")
    assert fallback["isLocal"] is True and "fallbackReason" in fallback and "jdMatchScore" in fallback


def test_process_resume_completes_when_qwen_down(store, monkeypatch, tmp_path):
    monkeypatch.setattr("services.storage.UPLOAD_DIR", tmp_path)

    def down(*a, **k):
        raise llm.LlmError("down")

    monkeypatch.setattr(llm, "complete_json", down)
    resume = resumes.process_resume("jane.txt", SAMPLE.encode(), jd_text="python", wait=True)
    assert resume["status"] == "completed" and resume["analysis"]["isLocal"] is True and resume["report"]["suitability"]
