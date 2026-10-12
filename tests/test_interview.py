import base64
import json

import pytest

from services import ai, face, identity, interviews, llm, resumes

RID = "11111111-1111-4111-8111-111111111111"


def seed_candidate(store, **report):
    store.seed("resumes", [{"id": RID, "filename": "a.pdf", "parsed": json.dumps({"personal": {"email": "c@x.com"}, "skills": {"technical": ["python"], "tools": []}, "projects": []}),
                            "report": json.dumps(report), "analysis": "{}", "enhanced": "{}"}])
    store.seed("candidate_sessions", [{"id": "s1", "email": "c@x.com", "resume_id": RID, "used": False, "code": None}])


def test_access_flow(client, store):
    seed_candidate(store)
    ok = client.post("/api/interview/access", json={"email": "C@x.com"})
    assert ok.json() == {"success": True, "resumeId": RID}
    assert client.post("/api/interview/access", json={"email": "nobody@x.com"}).status_code == 404
    assert client.post("/api/interview/access", json={}).status_code == 400


def test_conclude_marks_session_used_and_blocks_reentry(client, store):
    seed_candidate(store)
    assert client.post(f"/api/interview/{RID}/conclude").json() == {"success": True}
    again = client.post("/api/interview/access", json={"email": "c@x.com"})
    assert again.status_code == 403


def test_questions_fall_back_to_defaults_when_qwen_down(client, store, monkeypatch):
    seed_candidate(store, interviewConfig={"interviewType": "technical", "sections": {"overlapping": 2, "gap": 1, "projects": 1, "coding": 1}})
    monkeypatch.setattr(ai, "generate_json", lambda *a, **k: (_ for _ in ()).throw(llm.LlmError("down")))
    res = client.get(f"/api/interview/{RID}/questions")
    assert res.status_code == 200 and len(res.json()) == 5
    assert res.json()[-1].startswith("Coding Challenge:")
    assert client.get(f"/api/interview/{RID}/questions").json() == res.json()
    assert store.count("interview_questions", {"resume_id": RID}) == 5


def test_questions_use_qwen_output(client, store, monkeypatch):
    seed_candidate(store, interviewConfig={"interviewType": "technical", "sections": {"overlapping": 1, "gap": 1, "projects": 0, "coding": 1}})
    replies = iter([[{"question": "Q one?"}, {"question": "Q two?"}], [{"question": "Coding Challenge: do x"}]])
    monkeypatch.setattr(ai, "generate_json", lambda *a, **k: next(replies))
    assert client.get(f"/api/interview/{RID}/questions").json() == ["Q one?", "Q two?", "Coding Challenge: do x"]


def test_questions_unknown_resume_and_bad_id(client, store):
    assert client.get("/api/interview/22222222-2222-4222-8222-222222222222/questions").status_code == 404
    assert client.get("/api/interview/not-a-uuid/questions").status_code == 400


def test_submit_answer_heuristics_and_ai(client, store, monkeypatch):
    seed_candidate(store)
    monkeypatch.setattr(ai, "generate_json", lambda *a, **k: {"score": 8, "feedback": "Solid."})
    q = "Explain indexing in databases"
    for idx, ans in enumerate(["", "idk", "A b-tree index speeds lookups by keeping keys ordered so the engine can avoid scanning the table."]):
        res = client.post(f"/api/interview/{RID}/submit_answer", json={"question_index": idx, "question": q, "answer": ans})
        assert res.json() == {"status": "success"}
    scores = [r["mock_score"] for r in sorted(store.select("interview_attempts"), key=lambda r: r["question_index"])]
    assert scores == [0, 1, 8]
    answers = client.get(f"/api/interview/{RID}/answers").json()
    assert len(answers) == 3
    assert client.post(f"/api/interview/{RID}/submit_answer", json={"question_index": "x", "question": q}).status_code == 400


def test_coding_template_scores_one():
    got = interviews.heuristic_evaluation("Coding Challenge: write in JavaScript", "function solution() {\n // write your code here\n return;\n}")
    assert got["score"] == 1
    wrong = interviews.heuristic_evaluation("Coding Challenge: write in JavaScript please", "def solve(x):\n    return x * 2 + 1")
    assert wrong["score"] == 1


def test_proctor_violation_accumulates_and_auto_submits(client, store):
    seed_candidate(store)
    for count in (1, 2, 3):
        res = client.post(f"/api/interview/{RID}/proctor_violation", json={"violationType": "tab_switch", "warningCount": count})
        assert res.status_code == 200
    silent = client.post(f"/api/interview/{RID}/proctor_violation", json={"violationType": "noise", "warningCount": 9, "silent": True}).json()
    proctoring = silent["proctoring"]
    assert proctoring["autoSubmitted"] is True and proctoring["warningCount"] == 3 and proctoring["eventCount"] == 4
    assert client.post(f"/api/interview/{RID}/proctor_violation", json={"warningCount": 1}).status_code == 400


def test_run_code_returns_503_when_qwen_down(client, store, monkeypatch):
    monkeypatch.setattr(ai, "generate_json", lambda *a, **k: (_ for _ in ()).throw(llm.LlmError("down")))
    res = client.post(f"/api/interview/{RID}/run_code", json={"question": "q", "language": "python", "code": "print(1)"})
    assert res.status_code == 503 and res.json()["compiles"] is False and "error" in res.json()


def jpeg_b64(size=3000):
    return "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"0" * size).decode()


def test_verify_id_with_face_service(client, store, monkeypatch, tmp_path):
    seed_candidate(store)
    monkeypatch.setattr("services.storage.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(face, "compare", lambda a, b: {"matched": True, "confidence": 91})
    body = {"idType": "pan", "idImage": jpeg_b64(), "selfieImage": jpeg_b64()}
    res = client.post(f"/api/interview/{RID}/verify_id", json=body)
    assert res.status_code == 200 and res.json()["matched"] is True and res.json()["engine"] == "facenet"
    report = json.loads(store.first("resumes", {"id": RID})["report"])
    assert report["verification"]["status"] == "verified"
    assert client.get(f"/api/interview/{RID}/verification/id").status_code == 200
    assert client.get(f"/api/interview/{RID}/verification/other").status_code == 404


def test_verify_id_engine_down_is_system_error(client, store, monkeypatch, tmp_path):
    seed_candidate(store)
    monkeypatch.setattr("services.storage.UPLOAD_DIR", tmp_path)

    def boom(a, b):
        raise face.FaceServiceError("down")

    monkeypatch.setattr(face, "compare", boom)
    res = client.post(f"/api/interview/{RID}/verify_id", json={"idType": "pan", "idImage": jpeg_b64(), "selfieImage": jpeg_b64()})
    assert res.json()["isSystemError"] is True and res.json()["matched"] is False


def test_verify_id_rejects_bad_input(client, store):
    seed_candidate(store)
    assert client.post(f"/api/interview/{RID}/verify_id", json={"idType": "passport", "idImage": jpeg_b64(), "selfieImage": jpeg_b64()}).status_code == 400
    assert client.post(f"/api/interview/{RID}/verify_id", json={"idType": "pan", "idImage": jpeg_b64(10), "selfieImage": jpeg_b64(10)}).status_code == 400


def test_descriptor_fallback_match():
    vec = [0.1] * 128
    assert identity.match_descriptors(vec, vec)["matched"] is True
    far = [0.9] * 128
    assert identity.match_descriptors(vec, far)["matched"] is False


def test_video_upload_and_range_streaming(client, store, monkeypatch, tmp_path):
    seed_candidate(store)
    monkeypatch.setattr("services.storage.UPLOAD_DIR", tmp_path)
    webm = b"\x1a\x45\xdf\xa3" + b"v" * 5000
    res = client.post(f"/api/interview/{RID}/upload_video", files={"video": ("rec.webm", webm, "video/webm")}, data={"duration": "12.5"})
    assert res.status_code == 200 and res.json()["videoUrl"].endswith("/video")
    full = client.get(f"/api/interview/{RID}/video")
    assert full.status_code == 200 and len(full.content) == len(webm)
    part = client.get(f"/api/interview/{RID}/video", headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.headers["content-range"] == f"bytes 0-9/{len(webm)}"
    bad = client.post(f"/api/interview/{RID}/upload_video", files={"video": ("x.webm", b"not video data", "video/webm")})
    assert bad.status_code == 400
