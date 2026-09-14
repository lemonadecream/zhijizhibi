"""Shared pytest fixtures.

Sets environment BEFORE the application package is imported so ``app.config``
binds to a throwaway SQLite database and the Mock AI provider (no network /
API key needed). The background jobs (F1/F2) use the same ``SessionLocal``
engine, so data written by the request and read by the async job stay
consistent within the single test database.
"""
from __future__ import annotations

import os
import tempfile

# Point the app at an isolated SQLite file and use the deterministic Mock
# provider. JWT secret / limits are also pinned so behaviour is reproducible.
_TMP_DB = os.path.join(tempfile.gettempdir(), "cdp_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DB}")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("AI_BASE_URL", "http://localhost/mock")
os.environ.setdefault("AI_API_KEY", "test-key")
os.environ.setdefault("AI_MODEL", "mock-model")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("STORAGE_ROOT", tempfile.mkdtemp(prefix="cdp_storage_"))
os.environ.setdefault("MAX_UPLOAD_MB", "10")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

import fitz  # noqa: E402  (imported after env is stable)

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base, engine  # noqa: E402
from app.db.migrate import run_migrations  # noqa: E402
from app.main import create_app  # noqa: E402


def make_pdf(path: str, lines) -> None:
    """Write a real, parseable PDF containing ``lines`` of text."""
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 24
    doc.save(path, garbage=4, deflate=True)
    doc.close()


def make_docx(path: str, paragraphs) -> None:
    """Write a real, parseable DOCX containing ``paragraphs``."""
    from docx import Document

    d = Document()
    for p in paragraphs:
        d.add_paragraph(p)
    d.save(path)


def _clean_tables() -> None:
    with engine.connect() as conn:
        # Disable FK checks for SQLite so we can truncate in any order.
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()


import pytest  # noqa: E402

from app.api.auth import _login_limiter, _register_limiter  # noqa: E402


@pytest.fixture(scope="function")
def client():
    """A TestClient whose lifespan runs migrations; tables wiped per test."""
    # 限流器是进程级单例，跨用例持久；测试全部来自同一"IP"，
    # 不重置会让第 11 个注册用户开始被 429。
    _login_limiter.reset_all()
    _register_limiter.reset_all()
    run_migrations(engine)  # ensure schema exists before truncating
    _clean_tables()
    app = create_app()
    with TestClient(app) as c:
        yield c
    _clean_tables()
