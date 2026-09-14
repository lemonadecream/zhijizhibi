"""Lightweight, versioned migration runner.

Migrations are plain Python modules under ``app.db.migrations`` exposing an
``upgrade(conn)`` callable. Applied versions are tracked in a
``schema_migrations`` table so the runner is idempotent and replayable.

Each migration runs inside ONE transaction that also writes its version row:
either the schema change lands together with its version marker, or everything
rolls back. There is no window for "half-applied schema marked as migrated"
(the failure mode that silently corrupts production databases).

The callable receives a SQLAlchemy ``Connection`` (not an Engine) — use
``conn.execute(...)`` directly; ``Base.metadata.create_all(conn)`` and
``inspect(conn)`` accept a Connection as well.

This keeps schema changes explicit (no ``create_all`` magic in production) while
remaining dialect-agnostic so tests can run on SQLite.
"""
from __future__ import annotations

import importlib
import pkgutil

from sqlalchemy import text

from app.db.base import Base, engine

MIGRATIONS_PACKAGE = "app.db.migrations"


def _ensure_version_table(eng):
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  version VARCHAR(32) PRIMARY KEY,"
                "  name VARCHAR(128) NOT NULL,"
                "  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ")"
            )
        )
        conn.commit()


def _applied_versions(eng) -> set[str]:
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT version FROM schema_migrations")
        ).fetchall()
    return {r[0] for r in rows}


def _discover_migrations() -> list[tuple[str, str, object]]:
    pkg = importlib.import_module(MIGRATIONS_PACKAGE)
    mods = []
    for mod in pkgutil.iter_modules(pkg.__path__):
        name = mod.name
        if not name.startswith("0"):
            continue
        module = importlib.import_module(f"{MIGRATIONS_PACKAGE}.{name}")
        version = getattr(module, "VERSION", name)
        title = getattr(module, "NAME", name)
        mods.append((str(version), title, module))
    mods.sort(key=lambda x: x[0])
    return mods


def run_migrations(eng=None) -> list[str]:
    eng = eng or engine
    _ensure_version_table(eng)
    applied = _applied_versions(eng)
    ran: list[str] = []
    for version, title, module in _discover_migrations():
        if version in applied:
            continue
        # 单事务 = DDL/DML + 版本号写入。失败整体回滚：不会出现
        # "schema 改了一半却记了版本"，也不会"改完了没记版本下次重复执行"。
        with eng.begin() as conn:
            module.upgrade(conn)
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, name) "
                    "VALUES (:v, :n)"
                ),
                {"v": version, "n": title},
            )
        ran.append(f"{version}:{title}")
    return ran


if __name__ == "__main__":
    ran = run_migrations()
    if ran:
        print("Applied migrations:")
        for r in ran:
            print("  -", r)
    else:
        print("No pending migrations.")
