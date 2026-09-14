"""Personal experience entities collected in Phase 1 (F1 input data)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONCol


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EducationExp(Base):
    __tablename__ = "education_exp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    school: Mapped[str] = mapped_column(String(120), nullable=False)
    major: Mapped[str] = mapped_column(String(120), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(20), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gpa: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="user", nullable=False)  # user/ai


class InternshipExp(Base):
    __tablename__ = "internship_exp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    company: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duty_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="user", nullable=False)


class ProjectExp(Base):
    __tablename__ = "project_exp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="user", nullable=False)


class Skill(Base):
    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)  # 1-5
    source: Mapped[str] = mapped_column(String(10), default="user", nullable=False)  # user/ai


class Interest(Base):
    __tablename__ = "interest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    tag: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(10), default="user", nullable=False)


class WorkPreference(Base):
    __tablename__ = "work_preference"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    city: Mapped[list | None] = mapped_column(JSONCol(), nullable=True)
    company_types: Mapped[list | None] = mapped_column(JSONCol(), nullable=True)
    industries: Mapped[list | None] = mapped_column(JSONCol(), nullable=True)
    salary_expect: Mapped[dict | None] = mapped_column(JSONCol(), nullable=True)
    overtime_tolerance: Mapped[str | None] = mapped_column(String(20), nullable=True)
    stability_pref: Mapped[str | None] = mapped_column(String(20), nullable=True)


class CareerGoal(Base):
    __tablename__ = "career_goal"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    target_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
