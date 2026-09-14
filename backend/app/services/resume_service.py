"""Resume upload / parse (F1) and experience confirmation service."""
from __future__ import annotations

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.config import settings
from app.errors.exceptions import ValidationError_ as AppValidationError
from app.repositories import (
    create_resume,
    get_resume,
    save_experiences_from_parsed,
    set_resume_text,
)
from app.services.jobs import run_f1
from app.storage.local import LocalStorage
from app.utils.parse_file import extract_text, validate_file

_storage = LocalStorage()


def _check_size(data: bytes) -> None:
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise AppValidationError(
            f"文件超过 {settings.MAX_UPLOAD_MB}MB 限制", code="file_too_large"
        )


def upload_resume(db: Session, *, user_id: int, filename: str, data: bytes, bg: BackgroundTasks):
    _check_size(data)
    # 扩展名 + 魔数双重校验：扩展名可伪造，落盘前必须确认内容真实格式。
    validate_file(filename, data)
    file_id = _storage.save(user_id=user_id, filename=filename, data=data)
    resume = create_resume(db, user_id=user_id, file_id=file_id, filename=filename)
    try:
        raw_text = extract_text(filename, data)
    except AppValidationError:
        # Parsing failed (e.g. scanned PDF): keep record, let F1 degrade.
        raw_text = ""
    set_resume_text(db, resume.id, raw_text)
    bg.add_task(run_f1, resume.id)
    return resume


def parse_text(db: Session, *, user_id: int, text: str, bg: BackgroundTasks):
    text = (text or "").strip()
    if len(text) < 10:
        raise AppValidationError("请输入至少 10 个字符的经历描述", code="text_too_short")
    if len(text) > 20000:
        raise AppValidationError("文本过长（上限 20000 字符）", code="text_too_long")
    resume = create_resume(db, user_id=user_id, file_id=None, filename=None)
    set_resume_text(db, resume.id, text)
    bg.add_task(run_f1, resume.id)
    return resume


def get_resume_status(db: Session, *, user_id: int, resume_id: int):
    r = get_resume(db, resume_id, user_id)
    if r is None:
        raise AppValidationError("简历记录不存在", code="not_found")
    return r


def confirm_resume(db: Session, *, user_id: int, resume_id: int, parsed_json: dict):
    r = get_resume(db, resume_id, user_id)
    if r is None:
        raise AppValidationError("简历记录不存在", code="not_found")
    save_experiences_from_parsed(db, user_id, parsed_json)
    return True
