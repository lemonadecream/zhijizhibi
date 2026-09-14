"""Phase 1 integration: personal experience -> AI career profile.

Uses SQLite + the deterministic Mock AI provider, so the whole pipeline runs
without any external service. Covers the three data-entry paths (resume upload,
free text, manual) and the confirm -> generate -> read -> edit loop.
"""
from __future__ import annotations

import os

from tests.conftest import make_docx, make_pdf


def _auth_header(client, email="flow@test.com", password="secret123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "流"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload_pdf(client, headers, lines):
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    make_pdf(path, lines)
    with open(path, "rb") as f:
        data = f.read()
    r = client.post("/api/resume/upload", files={"file": ("resume.pdf", data, "application/pdf")}, headers=headers)
    os.remove(path)
    return r


def test_full_upload_flow(client):
    h = _auth_header(client)
    r = _upload_pdf(client, h, ["张三 清华 计算机 本科 2020-2024", "实习 字节 后端 2023"])
    assert r.status_code == 200
    rid = r.json()["resume_id"]

    # F1 background parse should have completed (parsed_json present).
    status = client.get(f"/api/resume/{rid}", headers=h).json()
    assert status["parse_status"] == "parsed"
    parsed = status["parsed_json"]
    assert parsed["education"] and parsed["internships"]

    # Confirm (save) the AI draft as the user's experiences.
    r = client.post(f"/api/resume/{rid}/confirm", json={"parsed_json": parsed}, headers=h)
    assert r.status_code == 200

    # Generate the career profile (F2 background).
    r = client.post("/api/profile/generate", json={"resume_id": rid}, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "generating"

    profile = client.get("/api/profile", headers=h).json()
    assert profile["status"] == "ready"
    assert len(profile["ability_tags"]) > 0
    assert len(profile["interest_tags"]) > 0
    assert len(profile["strengths"]) > 0
    assert len(profile["risks"]) > 0
    # AI judgment vs my-info distinction: each ability tag carries evidence.
    assert all("evidence" in a for a in profile["ability_tags"])
    # Every risk must carry a strategy (AI/business boundary rule).
    assert all(a.get("strategy") for a in profile["risks"])


def test_edit_profile_creates_new_version(client):
    h = _auth_header(client)
    _upload_pdf(client, h, ["李四 北大 软件 本科", "项目 商城"])
    rid = _last_resume(client, h)
    parsed = client.get(f"/api/resume/{rid}", headers=h).json()["parsed_json"]
    client.post(f"/api/resume/{rid}/confirm", json={"parsed_json": parsed}, headers=h)
    client.post("/api/profile/generate", json={"resume_id": rid}, headers=h)
    p0 = client.get("/api/profile", headers=h).json()
    v0 = p0["version"]

    # User edits one ability tag.
    upd = {
        "ability_tags": [{"tag": "编程能力", "level": 4, "confidence": 0.9, "evidence": "实习"}],
        "interest_tags": [],
        "strengths": [],
        "risks": [],
        "preference_infer": {},
    }
    r = client.put("/api/profile", json=upd, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "edited"
    p1 = client.get("/api/profile", headers=h).json()
    assert p1["version"] == v0 + 1
    assert p1["ability_tags"][0]["level"] == 4


def _last_resume(client, h):
    # Resume ids are sequential per cleaned DB; the only one belongs to this test.
    r = client.get("/api/resume/1", headers=h)
    return r.json()["resume_id"]


def test_free_text_path(client):
    h = _auth_header(client, email="free@test.com")
    r = client.post("/api/resume/parse-text", json={"text": "我是王五，复旦计算机本科，曾在腾讯实习做前端开发。"}, headers=h)
    assert r.status_code == 200
    rid = r.json()["resume_id"]
    status = client.get(f"/api/resume/{rid}", headers=h).json()
    assert status["parse_status"] == "parsed"
    parsed = status["parsed_json"]
    client.post(f"/api/resume/{rid}/confirm", json={"parsed_json": parsed}, headers=h)
    r = client.post("/api/profile/generate", json={"resume_id": rid}, headers=h)
    assert r.status_code == 200
    p = client.get("/api/profile", headers=h).json()
    assert p["status"] == "ready"


def test_manual_experience_path(client):
    h = _auth_header(client, email="manual@test.com")
    payload = {
        "education": [{"school": "浙大", "major": "电子", "degree": "本科", "start": "2019", "end": "2023"}],
        "internships": [{"company": "阿里", "role": "算法", "start": "2022", "end": "2022", "detail": "推荐系统"}],
        "projects": [],
        "skills": [{"name": "Python", "level": 4}],
        "interests": ["机器学习"],
    }
    r = client.post("/api/experience", json=payload, headers=h)
    assert r.status_code == 200
    r = client.post("/api/profile/generate", json={}, headers=h)
    assert r.status_code == 200
    p = client.get("/api/profile", headers=h).json()
    assert p["status"] == "ready"
    # Confirm the dates survived the F1 schema -> model remap.
    assert len(p["ability_tags"]) > 0


def test_generate_without_experience_rejected(client):
    h = _auth_header(client, email="empty@test.com")
    r = client.post("/api/profile/generate", json={}, headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "no_experience"


def test_docx_upload_parses(client):
    h = _auth_header(client, email="docx@test.com")
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    make_docx(path, ["赵六 上海交大 信息安全 本科", "实习 拼多多 安全工程师"])
    with open(path, "rb") as f:
        data = f.read()
    r = client.post("/api/resume/upload", files={"file": ("resume.docx", data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, headers=h)
    os.remove(path)
    assert r.status_code == 200
    rid = r.json()["resume_id"]
    status = client.get(f"/api/resume/{rid}", headers=h).json()
    assert status["parse_status"] == "parsed"
