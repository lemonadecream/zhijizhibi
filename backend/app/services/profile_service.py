"""Career profile service (F2 generation, retrieval, user edits)."""
from __future__ import annotations

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.errors.exceptions import ValidationError_ as AppValidationError
from app.repositories import (
    create_profile_placeholder,
    get_experiences,
    get_profile,
    update_profile,
)
from app.services.jobs import run_f2


def generate_profile(db: Session, *, user_id: int, bg: BackgroundTasks) -> dict:
    experiences = get_experiences(db, user_id)
    if not experiences:
        raise AppValidationError(
            "请先录入个人经历（上传简历 / 文本 / 手动）后再生成画像", code="no_experience"
        )
    # Avoid duplicate in-flight generation.
    existing = get_profile(db, user_id)
    if existing and existing.status == "generating":
        return {"status": "generating", "profile_id": existing.profile_id}
    placeholder = create_profile_placeholder(db, user_id)
    bg.add_task(run_f2, user_id, placeholder.profile_id)
    return {"status": "generating", "profile_id": placeholder.profile_id}


def get_current_profile(db: Session, *, user_id: int):
    return get_profile(db, user_id)


def update_current_profile(db: Session, *, user_id: int, data: dict):
    return update_profile(db, user_id, data)
