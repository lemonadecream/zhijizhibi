"""Resume file + F1 parsed draft, and the AI-generated career profile (F2)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONCol


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Resume(Base):
    """Uploaded resume file + extracted text + F1 structured draft (parsed_json).

    parse_status drives the async F1 job: pending -> parsing -> parsed / failed.
    The structured draft in ``parsed_json`` is NOT yet saved to experience tables
    until the user confirms it.
    """

    __tablename__ = "resume"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # storage key
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_json: Mapped[dict | None] = mapped_column(JSONCol(), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(12), default="pending", nullable=False)  # pending/parsing/parsed/failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class CareerProfile(Base):
    """AI-generated career profile (F2). The single source of truth for downstream modules.

    status: generating -> ready <-> edited.
    """

    __tablename__ = "career_profile"

    profile_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    ability_tags: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    interest_tags: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    strengths: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    risks: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    preference_infer: Mapped[dict] = mapped_column(JSONCol(), default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="generating", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class ProfileRevisionLog(Base):
    __tablename__ = "profile_revision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)  # create/edit/revert
    changed_fields: Mapped[list] = mapped_column(JSONCol(), default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
