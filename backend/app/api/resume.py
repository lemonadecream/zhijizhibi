"""Resume / F1 parsing routes.

Upload or paste text -> async F1 parse -> poll status -> confirm draft.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.config import settings
from app.db.base import get_db
from app.errors.exceptions import ValidationError_ as AppValidationError
from app.schemas import ParseTextIn, ResumeConfirmIn, ResumeStatusOut
from app.services.resume_service import (
    confirm_resume,
    get_resume_status,
    parse_text,
    upload_resume,
)

router = APIRouter(prefix="/resume", tags=["resume"])

# 流式读取的块大小（1 MiB）。上限在读取过程中强制执行，
# 避免先整读进内存再校验被超大请求体打爆进程。
_CHUNK = 1024 * 1024


def _read_bounded(file: UploadFile) -> bytes:
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise AppValidationError(
                f"文件超过 {settings.MAX_UPLOAD_MB}MB 限制", code="file_too_large"
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/upload", response_model=ResumeStatusOut)
def upload(
    file: UploadFile = File(...),
    bg: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    data = _read_bounded(file)
    resume = upload_resume(
        db, user_id=user_id, filename=file.filename or "resume", data=data, bg=bg
    )
    return _to_out(resume)


@router.post("/parse-text", response_model=ResumeStatusOut)
def parse_free_text(
    req: ParseTextIn,
    bg: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    resume = parse_text(db, user_id=user_id, text=req.text, bg=bg)
    return _to_out(resume)


@router.get("/{resume_id}", response_model=ResumeStatusOut)
def status(
    resume_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    r = get_resume_status(db, user_id=user_id, resume_id=resume_id)
    return _to_out(r)


@router.post("/{resume_id}/confirm", response_model=dict)
def confirm(
    resume_id: int,
    req: ResumeConfirmIn,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    ok = confirm_resume(db, user_id=user_id, resume_id=resume_id, parsed_json=req.parsed_json)
    return {"confirmed": ok}


def _to_out(r):
    return ResumeStatusOut(
        resume_id=r.id,
        parse_status=r.parse_status,
        filename=r.filename,
        parsed_json=r.parsed_json,
        error=r.error,
    )
