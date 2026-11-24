"""Named dashboard users (harvey/dashboard_users.py) and their place in the guard.

All users here are invented (example.test); the users file, token and
database live in tmp_path.
"""

import io
import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

import harvey.dashboard as dash
from harvey import dashboard_users as users

ORIGIN = "http://127.0.0.1:5555"
HOSTED = "harvey-demo.example.test"
EMAIL = "ana@example.test"
PASSWORD = "correct horse battery"


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(dash, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(dash, "DB_PATH", tmp_path / "data" / "harvey.db")
    dash.token_store.configure(tmp_path / "data" / "dashboard-token")
    users.user_store.configure(tmp_path / "data" / "dashboard-users.json")
    users.sessions.clear()
    users.throttle._fails.clear()
    users.user_store.set_password(EMAIL, PASSWORD, create=True)
    yield tmp_path
    users.user_store.configure(users.USERS_FILE)
    users.sessions.clear()
    users.throttle._fails.clear()


@pytest.fixture
def anon(env):
    with TestClient(dash.app, base_url=ORIGIN) as c:
        yield c


def _login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/login", json={"email": email, "password": password})


# ── Store ──


def test_passwords_are_stored_only_as_scrypt_hashes(env):
    raw = (env / "data" / "dashboard-users.json").read_text(encoding="utf-8")
    assert PASSWORD not in raw
    assert json.loads(raw)["users"][EMAIL]["hash"].startswith("scrypt$")


def test_emails_are_normalised_and_duplicates_refused(env):
    with pytest.raises(users.UserError):
        users.user_store.set_password("  ANA@Example.TEST ", PASSWORD, create=True)


def test_short_passwords_and_bad_emails_are_refused(env):
    with pytest.raises(users.UserError):
        users.user_store.set_password("luis@example.test", "short", create=True)
    with pytest.raises(users.UserError):
        users.user_store.set_password("not-an-email", PASSWORD, create=True)


def test_authenticate(env):
    assert users.user_store.authenticate("Ana@example.test", PASSWORD) == EMAIL
    assert users.user_store.authenticate(EMAIL, PASSWORD + "x") is None
    assert users.user_store.authenticate("nobody@example.test", PASSWORD) is None


# ── Login through the API ──


def test_login_gives_a_session_that_opens_the_api(anon):
    r = _login(anon)
    assert r.status_code == 200
    token = r.json()["token"]
    assert anon.get("/api/stats").status_code == 401
    r = anon.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json() == {"email": EMAIL, "admin": False}


def test_the_dashboard_token_still_works_as_admin(anon, env):
    r = anon.get("/api/me", headers={"Authorization": f"Bearer {dash.token_store.get()}"})
    assert r.status_code == 200 and r.json()["admin"] is True


def test_wrong_password_and_unknown_user_get_the_same_answer(anon):
    a = _login(anon, password="wrong password here")
    b = _login(anon, email="nobody@example.test")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_logout_ends_the_session(anon):
    token = _login(anon).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert anon.post("/api/logout", headers=h).status_code == 200
    assert anon.get("/api/me", headers=h).status_code == 401


def test_changing_or_removing_a_user_ends_their_sessions(anon):
    token = _login(anon).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    users.user_store.set_password(EMAIL, PASSWORD + "!", create=False)
    assert anon.get("/api/me", headers=h).status_code == 401
    token = _login(anon, password=PASSWORD + "!").json()["token"]
    users.user_store.remove(EMAIL)
    assert anon.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_sessions_expire(anon, monkeypatch):
    token = _login(anon).json()["token"]
    now = users.time.time()
    monkeypatch.setattr(users.time, "time", lambda: now + users.SESSION_HOURS * 3600 + 1)
    assert anon.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_repeated_failures_lock_the_email(anon):
    for _ in range(users.MAX_FAILURES):
        assert _login(anon, password="wrong password here").status_code == 401
    r = _login(anon)  # even the right password, while locked
    assert r.status_code == 429


def test_login_needs_json(anon):
    r = anon.post("/api/login", data={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 415


def test_login_keeps_the_host_and_origin_checks(env):
    with TestClient(dash.app, base_url="http://evil.example.test") as c:
        assert _login(c).status_code == 400
    with TestClient(dash.app, base_url=ORIGIN) as c:
        r = c.post("/api/login", json={"email": EMAIL, "password": PASSWORD},
                   headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403


def test_login_works_on_the_hosted_domain(env, monkeypatch):
    monkeypatch.setenv("HARVEY_PUBLIC_HOSTS", HOSTED)
    with TestClient(dash.app, base_url=f"https://{HOSTED}") as c:
        r = _login(c)
        assert r.status_code == 200
        me = c.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
        assert me.json()["email"] == EMAIL


# ── CLI ──


def test_cli_add_reads_the_password_from_stdin(env, monkeypatch, capsys):
    from harvey.cli_users import cmd_users

    monkeypatch.setattr(sys, "stdin", io.StringIO("another long secret\n"))
    cmd_users(types.SimpleNamespace(users_action="add", email="luis@example.test",
                                    password_stdin=True))
    assert users.user_store.authenticate("luis@example.test", "another long secret")
    cmd_users(types.SimpleNamespace(users_action="list", email="", password_stdin=False))
    out = capsys.readouterr().out
    assert "luis@example.test" in out and EMAIL in out
