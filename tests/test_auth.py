from core.tokens import sign_token
from services import accounts


def seed_employee(store, **over):
    row = {"id": "e1", "employee_id": "EMP1", "email": "emp1@infinite.com", "full_name": "Emp One",
           "department": "eng", "role": "employee", "is_first_login": True}
    row.update(over)
    store.seed("employees", [row])


def test_admin_login_requires_configured_password(client):
    res = client.post("/api/admin/auth/login", json={"email": "someone@infinite.com", "password": "x"})
    assert res.status_code == 503
    assert res.json()["error"] == "Admin password not setup"


def test_admin_login_success_and_wrong_password(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "S3cret!pw")
    ok = client.post("/api/admin/auth/login", json={"email": "someone@infinite.com", "password": "S3cret!pw"})
    assert ok.status_code == 200 and ok.json()["token"]
    bad = client.post("/api/admin/auth/login", json={"email": "someone@infinite.com", "password": "nope"})
    assert bad.status_code == 401
    valid = client.get("/api/admin/auth/validate", headers={"Authorization": f"Bearer {ok.json()['token']}"})
    assert valid.status_code == 200
    assert client.get("/api/admin/auth/validate").status_code == 401


def test_screening_admin_needs_its_own_env_password(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "AdminPw1!")
    res = client.post("/api/admin/auth/login", json={"email": "ramendras@infinite.com", "password": "x"})
    assert res.status_code == 503 and res.json()["error"] == "Admin password not setup"
    monkeypatch.setenv("SCREENING_ADMIN_PASSWORD", "ScreenPw1!")
    ok = client.post("/api/admin/auth/login", json={"email": "ramendras@infinite.com", "password": "ScreenPw1!"})
    assert ok.status_code == 200 and ok.json()["canViewEmployeePortal"] is False


def test_admin_rejects_foreign_domain(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "AdminPw1!")
    res = client.post("/api/admin/auth/login", json={"email": "x@gmail.com", "password": "AdminPw1!"})
    assert res.status_code == 400


def test_employee_first_login_flow(client, store):
    seed_employee(store)
    res = client.post("/api/employee/auth/login", json={"employee_id": "EMP1", "password": ""})
    assert res.status_code == 200 and res.json()["status"] == "first_time_modal"
    token = res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    changed = client.post("/api/employee/auth/confirm-password", headers=headers,
                          json={"action": "change", "password": "Str0ng!Passw"})
    assert changed.status_code == 200
    again = client.post("/api/employee/auth/login", json={"employee_id": "EMP1", "password": "Str0ng!Passw"})
    assert again.json()["status"] == "ok"
    wrong = client.post("/api/employee/auth/login", json={"employee_id": "EMP1", "password": "bad"})
    assert wrong.status_code == 401
    me = client.get("/api/employee/auth/validate", headers=headers)
    assert me.status_code == 200 and me.json()["employee"]["employee_id"] == "EMP1"


def test_employee_unknown_id_and_weak_password(client, store):
    seed_employee(store)
    assert client.post("/api/employee/auth/login", json={"employee_id": "NOPE", "password": ""}).status_code == 401
    weak = client.post("/api/employee/auth/set-password", json={"employee_id": "EMP1", "password": "weak"})
    assert weak.status_code == 400


def test_reset_password_requires_matching_email(client, store):
    seed_employee(store, is_first_login=False)
    bad = client.post("/api/employee/auth/reset-password",
                      json={"employee_id": "EMP1", "email": "other@x.com", "password": "Str0ng!Passw"})
    assert bad.status_code == 400
    good = client.post("/api/employee/auth/reset-password",
                       json={"employee_id": "EMP1", "email": "emp1@infinite.com", "password": "Str0ng!Passw"})
    assert good.status_code == 200
    assert accounts.verify_password("Str0ng!Passw", store.first("employees", {"employee_id": "EMP1"})["password_salt"],
                                    store.first("employees", {"employee_id": "EMP1"})["password_hash"])


def test_login_rate_limit(client, store):
    seed_employee(store)
    codes = [client.post("/api/employee/auth/login", json={"employee_id": "NOPE", "password": ""}).status_code for _ in range(9)]
    assert 429 in codes


def test_token_roundtrip_and_tamper():
    from core.tokens import verify_token

    token = sign_token("emp1")
    assert verify_token(token) == "EMP1"
    assert verify_token(token[:-1] + ("0" if token[-1] != "0" else "1")) is None
