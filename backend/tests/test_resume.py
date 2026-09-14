"""Resume upload edge cases: auth, file type, file size."""
from __future__ import annotations


def _register(client, email="edge@test.com"):
    return client.post("/api/auth/register", json={"email": email, "password": "secret123", "name": "边"})


def test_upload_requires_auth(client):
    r = client.post("/api/resume/upload", files={"file": ("a.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 401


def test_resume_status_requires_auth(client):
    r = client.get("/api/resume/1")
    assert r.status_code == 401


def test_unsupported_file_type_rejected(client):
    tok = _register(client).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/resume/upload", files={"file": ("notes.txt", b"hello world", "text/plain")}, headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_file_type"


def test_file_too_large_rejected(client):
    tok = _register(client, email="big@test.com").json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    # MAX_UPLOAD_MB is 10 in the test env; send ~11 MB.
    big = b"x" * (11 * 1024 * 1024)
    r = client.post("/api/resume/upload", files={"file": ("big.pdf", big, "application/pdf")}, headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "file_too_large"


def test_free_text_too_short_rejected(client):
    tok = _register(client, email="short@test.com").json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/resume/parse-text", json={"text": "太短"}, headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "text_too_short"
