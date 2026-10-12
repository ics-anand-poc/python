import io
import json
import zipfile

import pytest

from services import hr_files, llm, resumes
from tests.test_resumes import SAMPLE

PDFISH = b"%PDF-1.4 " + SAMPLE.encode()


@pytest.fixture()
def admin(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "AdminPw1!")
    token = client.post("/api/admin/auth/login", json={"email": "boss@infinite.com", "password": "AdminPw1!"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fast(monkeypatch, tmp_path):
    monkeypatch.setattr("services.storage.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(resumes, "extract_text", lambda data, name=None: SAMPLE)
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: (_ for _ in ()).throw(llm.LlmError("down")))


def test_single_cv_upload_creates_session(client, store, admin):
    res = client.post("/api/admin/resumes/upload_bulk", headers=admin, files={"file": ("jane.pdf", PDFISH, "application/pdf")},
                      data={"jdText": "python dev", "rmEmail": "rm@infinite.com"})
    body = res.json()
    assert res.status_code == 200 and body["resume"]["status"] == "completed" and body["resume"]["analysis"]["isLocal"] is True
    assert store.first("candidate_sessions", {"email": "jane.doe@example.com"})["resume_id"] == body["resume"]["id"]


def test_upload_rejects_bad_files(client, admin):
    assert client.post("/api/admin/resumes/upload_bulk", headers=admin, files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 400
    assert client.post("/api/admin/resumes/upload_bulk", headers=admin, files={"file": ("x.png", b"\x89PNG....", "image/png")}).status_code == 400
    assert client.post("/api/admin/resumes/upload_bulk", headers=admin).status_code == 400
    assert client.post("/api/admin/resumes/upload_bulk", files={"file": ("x.pdf", PDFISH, "application/pdf")}).status_code == 401


def test_zip_upload_skips_hidden_and_bad_entries(client, store, admin):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a/jane.pdf", PDFISH)
        z.writestr("__MACOSX/._jane.pdf", PDFISH)
        z.writestr("notes.png", b"xx")
        z.writestr("../evil.pdf", PDFISH)
        z.writestr("bad.pdf", b"not pdf bytes")
    res = client.post("/api/admin/resumes/upload_bulk", headers=admin, files={"file": ("pack.zip", buf.getvalue(), "application/zip")}).json()
    assert res["isZip"] is True and len(res["resumes"]) == 1


def test_jd_text_lookup_by_id(client, store, admin):
    store.seed("job_descriptions", [{"id": "jd1", "jd_text": "Need Rust and Kubernetes", "rm_email": "rm@infinite.com", "file_name": "1BR"}])
    res = client.post("/api/admin/resumes/upload_bulk", headers=admin, files={"file": ("jane.pdf", PDFISH, "application/pdf")}, data={"jdId": "jd1"}).json()
    assert res["resume"]["report"]["jdId"] == "jd1" and res["resume"]["report"]["suitability"] in ("suitable", "unsuitable")


def test_placement_rules():
    assert hr_files.place_file("51210BR.pdf")["kind"] == "jd"
    assert hr_files.place_file("BR_RawData.xlsx", "Sheet: x\nAuto req ID | Title\n50001BR | Dev")["kind"] == "br"
    pool = hr_files.place_file("Corp Pool.xlsx", "Sheet: a\nEmp No | Emp Name | Skills\n1 | A | x\n2 | B | y")
    assert pool["kind"] == "corp_pool" and pool["category"] == "employee" and pool["peopleCount"] == 2
    assert hr_files.place_file("Resource_Question_Mapping.xlsx")["kind"] == "portal_mapping"
    assert hr_files.place_file("Employee User Credentials.xlsx")["kind"] == "unknown"
    assert hr_files.place_file("random.xlsx")["kind"] == "unknown"


def test_llm_place_uses_rules_then_qwen(client, admin, monkeypatch):
    first = client.post("/api/admin/files/llm-place", headers=admin, files={"file": ("51210BR.txt", b"Job title: Dev")}).json()
    assert first["placement"]["kind"] == "jd"
    monkeypatch.setattr(llm, "is_up", lambda: True)
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"kind": "corp_pool", "why": "roster", "peopleCount": 4})
    second = client.post("/api/admin/files/llm-place", headers=admin, files={"file": ("mystery.txt", b"some people list")}).json()
    assert second["placement"]["kind"] == "corp_pool" and second["placement"]["peopleCount"] == 4
    assert client.post("/api/admin/files/llm-place", headers=admin, files={"file": ("x.exe", b"MZ")}).status_code == 400
