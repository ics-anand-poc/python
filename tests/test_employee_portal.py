import pytest

from core.tokens import sign_token

EMP = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@pytest.fixture()
def auth(store):
    store.seed("employees", [{"id": EMP, "employee_id": "EMP1", "email": "e@x.com", "full_name": "E", "role": "employee",
                              "product": "One-NDS", "product_qb_eligible": True}])
    return {"Authorization": "Bearer " + sign_token("EMP1")}


def test_catalog_and_subjects(client, auth):
    subjects = client.get("/api/employee/subjects", headers=auth).json()
    assert subjects[0]["id"] == "resource-product-assessment" and subjects[0]["title"] == "One-SDL Question Bank"
    catalog = client.get("/api/employee/catalog", headers=auth).json()
    assert catalog[0]["modules"][0]["topics"][0]["id"] == "resource-product-assessment-test"
    assert len(catalog) == len(subjects)
    assert client.get("/api/employee/catalog").json() == []
    assert client.get("/api/employee/subjects").status_code == 401


def test_ai_quiz_creates_resumes_and_resets(client, auth, store):
    first = client.post("/api/employee/learning/ai-fundamentals/ai-quiz", headers=auth, json={"difficulty": "easy"})
    assert first.status_code == 200 and first.json()["isResume"] is False and first.json()["total_questions"] == 10
    test_id = first.json()["test_id"]
    assert store.count("test_questions", {"test_id": test_id}) == 10
    again = client.post("/api/employee/learning/ai-fundamentals/ai-quiz", headers=auth).json()
    assert again["isResume"] is True and again["test_id"] == test_id
    store.update("tests", {"status": "completed"}, {"id": test_id})
    fresh = client.post("/api/employee/learning/ai-fundamentals/ai-quiz", headers=auth).json()
    assert fresh["isResume"] is False and fresh["test_id"] == test_id and store.count("test_questions", {"test_id": test_id}) == 10
    assert client.post("/api/employee/learning/does-not-exist-zzz/ai-quiz", headers=auth).status_code == 404


def test_ai_quiz_blocked_for_assessment_only(client, auth, store):
    store.update("employees", {"assessment_only": True}, {"employee_id": "EMP1"})
    assert client.post("/api/employee/learning/ai-fundamentals/ai-quiz", headers=auth).status_code == 403


def test_assigned_test_states(client, auth, store):
    empty = client.get("/api/employee/assigned-test", headers=auth).json()
    assert empty == {"active_test": None, "completed_test": None}
    store.seed("tests", [{"id": "t1", "employee_id": EMP, "employee_code": "EMP1", "topic_id": "resource-product-assessment", "subject_id": "s",
                          "topic_title": "Prod", "total_questions": 25, "status": "pending", "created_at": "2026-10-01T00:00:00Z"},
                         {"id": "t2", "employee_id": EMP, "employee_code": "EMP1", "topic_id": "resource-product-assessment-history:x", "subject_id": "s",
                          "topic_title": "Prod (previous)", "total_questions": 25, "status": "completed", "score_correct": 20,
                          "completed_at": "2026-09-01T00:00:00Z"}])
    res = client.get("/api/employee/assigned-test", headers=auth).json()
    assert res["active_test"]["test_id"] == "t1" and res["completed_test"]["score_percent"] == 80 and res["completed_test"]["recording_missing"] is True


def test_results_and_analytics(client, auth, store):
    for i, (pct, when) in enumerate([(80, "2026-09-01T10:00:00Z"), (60, "2026-09-09T10:00:00Z")]):
        tid = f"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb0{i}"
        qid = f"cccccccc-cccc-4ccc-8ccc-cccccccccc0{i}"
        store.seed("tests", [{"id": tid, "employee_id": EMP, "employee_code": "EMP1", "topic_id": f"topic{i}", "subject_id": "sub1",
                              "topic_title": f"Topic {i}", "subject_title": "Sub", "difficulty": "medium", "total_questions": 10,
                              "status": "completed", "score_correct": pct // 10, "score_percent": pct, "completed_at": when}])
        store.seed("test_attempts", [{"id": f"a{i}", "test_id": tid, "employee_id": EMP, "question_id": qid, "is_correct": True}])
    results = client.get("/api/employee/results", headers=auth).json()
    assert [r["accuracy_pct"] for r in results] == [60, 80]
    assert client.get("/api/employee/results?employee_id=OTHER", headers=auth).status_code == 403
    data = client.get("/api/employee/analytics", headers=auth).json()
    assert data["total_tests_taken"] == 2 and data["total_learning_hours"] == 1 and data["average_score"] == 100
    assert [h["score"] for h in data["score_history"]] == [80, 60]
    assert len(data["weekly_activity"]) == 2 and data["skill_level"] == "advanced"
    assert data["strongest_subject"] is None
