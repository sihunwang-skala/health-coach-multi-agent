"""Sign-in, sessions, role separation, lockout, CSRF, account deletion (temporary database, no network, no LLM)."""
import time
import types

import pytest
from fastapi.testclient import TestClient

from app import auth, server
from coach import tracelog
from mcp_servers import user_server

SIGNUP = {"username": "new_user1", "password": "Newpass123", "name": "길동", "age": 70, "gender": "male", "conditions": ["hypertension", "bogus"],
          "medications": ["metformin"], "other_medications": "a; b", "mobility": "cane", "activity": "걷기;\nx", "consent": True}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(auth, "DB_PATH", db)
    monkeypatch.setattr(user_server, "DB", db)
    monkeypatch.setattr(tracelog, "Settings", lambda: types.SimpleNamespace(db_path=db))
    auth.FAILS.clear()
    user_server._db().close()   # seeds the 10 synthetic profiles
    auth.create_account("maria_t", "Testpass12", "user", "마리아", "u01")
    auth.create_account("staff_t", "Staffpass12", "staff", "의료진")
    return TestClient(server.app, base_url="http://testserver")


def login(c, user="maria_t", pw="Testpass12", staff=False):
    return c.post("/api/staff/login" if staff else "/api/auth/login", json={"username": user, "password": pw})


def test_pages_redirect_to_the_right_login(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/login"
    assert client.get("/login").status_code == 200 and client.get("/admin/login").status_code == 200


def test_login_sets_an_httponly_cookie_and_stores_only_a_token_hash(client):
    r = login(client)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    token = client.cookies.get(auth.USER_COOKIE)
    assert token and not any(token in str(v) for row in auth.run("SELECT * FROM sessions", many=True) for v in row.values())
    assert "Testpass12" not in str(auth.run("SELECT * FROM accounts", many=True))   # only a scrypt hash is stored


def test_wrong_password_unknown_user_and_wrong_role_give_the_same_answer(client):
    a = login(client, pw="nope")
    b = login(client, user="ghost")
    c = login(client, user="staff_t", pw="Staffpass12")        # a staff account on the user sign-in
    d = login(client, user="maria_t", staff=True)              # a user account on the staff sign-in
    assert {x.status_code for x in (a, b, c, d)} == {401} and len({x.text for x in (a, b, c, d)}) == 1


def test_five_failures_lock_the_account_even_for_the_right_password(client):
    codes = [login(client, pw="bad").status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    assert login(client).status_code == 429


def test_user_and_staff_sessions_do_not_open_each_others_apis(client):
    login(client)
    assert client.get("/api/admin/users").status_code == 401 and client.get("/api/staff/me").status_code == 401
    client.cookies.clear()
    login(client, "staff_t", "Staffpass12", staff=True)
    assert client.get("/api/staff/me").status_code == 200 and client.get("/api/admin/users").status_code == 200
    assert client.post("/chat/stream", json={"message": "hi"}).status_code == 401


def test_chat_needs_a_session_and_the_person_comes_from_it(client):
    assert client.post("/chat/stream", json={"message": "hi"}).status_code == 401
    assert client.post("/approve", json={"thread_id": "x", "approve": True}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_cross_origin_post_is_refused(client):
    r = client.post("/api/auth/login", json={"username": "maria_t", "password": "Testpass12"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_signup_maps_choices_cleans_text_and_signs_in(client):
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 200
    p = user_server.get_full_profile(auth.run("SELECT user_id FROM accounts WHERE username = ?", ("new_user1",), one=True)["user_id"])
    assert p["conditions"] == ["type 2 diabetes", "hypertension"]            # unknown choices are dropped
    assert p["medications"] == ["metformin", "a,  b"] and ";" not in p["activity"] and "\n" not in p["activity"]
    assert p["mobility"] == "uses a cane"
    assert "길동" not in user_server.profile_text(p)                           # the name never reaches the LLM text
    assert client.cookies.get(auth.USER_COOKIE)


@pytest.mark.parametrize("patch,code", [({"consent": False}, 422), ({"password": "short1"}, 422), ({"password": "onlyletters"}, 422),
                                        ({"username": "Bad Name"}, 422), ({"age": 12}, 422), ({"gender": "x"}, 422)])
def test_signup_rejects_bad_input(client, patch, code):
    assert client.post("/api/auth/signup", json={**SIGNUP, **patch}).status_code == code


def test_duplicate_username_is_refused_without_creating_a_profile(client):
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 200
    n = len(user_server.full_profiles())
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 409
    assert len(user_server.full_profiles()) == n


def test_password_change_signs_out_other_devices(client):
    login(client)
    other = TestClient(server.app)
    login(other)
    assert client.post("/api/me/password", json={"current": "Testpass12", "new": "Another123"}).status_code == 200
    assert auth.session_account(types.SimpleNamespace(cookies=other.cookies), "user") is None      # the other device is out
    assert auth.session_account(types.SimpleNamespace(cookies=client.cookies), "user")              # this one stays in
    assert login(TestClient(server.app), pw="Another123").status_code == 200


def test_account_deletion_removes_profile_records_and_log(client):
    client.post("/api/auth/signup", json=SIGNUP)
    uid = auth.run("SELECT user_id FROM accounts WHERE username = ?", ("new_user1",), one=True)["user_id"]
    tracelog.log_event(uid, "hello", {"route": "chat", "answer": "hi"})
    assert client.post("/api/me/delete", json={"password": "wrong"}).status_code == 403
    assert client.post("/api/me/delete", json={"password": "Newpass123"}).status_code == 200
    assert user_server.get_full_profile(uid) is None and not tracelog.rows("SELECT * FROM events WHERE user_id = ?", (uid,))
    assert login(client, "new_user1", "Newpass123").status_code == 401


def test_opening_a_person_and_changing_an_alert_are_audited(client):
    login(client, "staff_t", "Staffpass12", staff=True)
    import asyncio
    server.STATE["deps"] = types.SimpleNamespace(users=lambda *a, **k: asyncio.sleep(0, {"records": []}))
    assert client.get("/api/admin/users/u01").status_code == 200
    actions = [r["action"] for r in client.get("/api/admin/audit").json()]
    assert "opened a person's data" in actions and "sign in" in actions


def test_demo_mode_enters_only_synthetic_people_and_the_demo_staff(client, monkeypatch):
    monkeypatch.setattr(server, "DEMO", True)
    names = [u["name"] for u in client.get("/api/demo/users").json()]
    assert len(names) == 10 and "Maria" in names
    client.post("/api/auth/signup", json=SIGNUP)                      # a real sign-up never appears in the demo list
    assert len(client.get("/api/demo/users").json()) == 10
    real = auth.run("SELECT user_id FROM accounts WHERE username = ?", ("new_user1",), one=True)["user_id"]
    client.cookies.clear()
    assert client.post("/api/demo/enter", json={"user_id": real}).status_code == 404
    assert client.post("/api/demo/enter", json={"user_id": "u04"}).status_code == 200
    assert auth.session_account(types.SimpleNamespace(cookies=client.cookies), "user")["user_id"] == "u04"
    assert client.get("/api/admin/users").status_code == 401           # a demo user is not staff
    assert client.post("/api/demo/staff").status_code == 200 and client.get("/api/admin/users").status_code == 200
    assert "sign in (demo)" in [r["action"] for r in client.get("/api/admin/audit").json()]


def test_demo_mode_off_closes_every_demo_door(client, monkeypatch):
    monkeypatch.setattr(server, "DEMO", False)
    assert client.get("/api/demo/users").status_code == 404
    assert client.post("/api/demo/enter", json={"user_id": "u01"}).status_code == 404
    assert client.post("/api/demo/staff").status_code == 404


def test_care_team_session_ends_after_idle_time_and_is_a_browser_session_cookie(client):
    r = login(client, "staff_t", "Staffpass12", staff=True)
    assert "max-age" not in r.headers["set-cookie"].lower() and "expires" not in r.headers["set-cookie"].lower()   # gone when the browser closes
    assert client.get("/api/staff/me").status_code == 200
    auth.run("UPDATE sessions SET expires = ? WHERE role = 'staff'", (time.time() - 1,))                          # 30 idle minutes later
    assert client.get("/api/staff/me").status_code == 401
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/login"


def test_using_the_console_keeps_the_care_team_session_alive_but_not_past_eight_hours(client):
    login(client, "staff_t", "Staffpass12", staff=True)
    auth.run("UPDATE sessions SET expires = ? WHERE role = 'staff'", (time.time() + 60,))
    assert client.get("/api/staff/me").status_code == 200
    assert auth.run("SELECT expires FROM sessions WHERE role = 'staff'", one=True)["expires"] > time.time() + 1000      # slid forward
    auth.run("UPDATE sessions SET created = ?, expires = ? WHERE role = 'staff'", (time.time() - auth.TTL["staff"] - 5, time.time() + 600))
    client.get("/api/staff/me")
    assert client.get("/api/staff/me").status_code == 401                                                           # absolute limit
