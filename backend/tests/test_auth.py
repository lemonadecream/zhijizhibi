"""Auth: register, login, /me, and access-control checks."""
from __future__ import annotations


def _register(c, email="u1@test.com", password="secret123", name="测试"):
    return c.post(
        "/api/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def _login(c, identifier, password):
    return c.post("/api/auth/login", json={"identifier": identifier, "password": password})


def test_register_and_login_flow(client):
    r = _register(client)
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"

    # Same credentials can log in.
    r = _login(client, "u1@test.com", "secret123")
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_duplicate_email_rejected(client):
    _register(client)
    r = _register(client)  # same email
    assert r.status_code == 409


def test_weak_password_rejected(client):
    r = _register(client, password="123")
    assert r.status_code == 422


def test_me_requires_auth(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_returns_user(client):
    tok = _register(client).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["email"] == "u1@test.com"


def test_wrong_password_rejected(client):
    _register(client)
    r = _login(client, "u1@test.com", "wrongpass")
    assert r.status_code == 401


def test_invalid_token_rejected(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401
