"""Dialect-aware JSON column.

Uses PostgreSQL JSONB in production (as required by the design) and falls back
to generic JSON on SQLite so the same models can run in local/test environments
without a live Postgres.
"""
from __future__ import annotations

from sqlalchemy import JSON as _SAJSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class JSONCol(TypeDecorator):
    impl = _SAJSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(_SAJSON())
