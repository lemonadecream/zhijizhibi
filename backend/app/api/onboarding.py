"""Onboarding interview routes (Phase 1B).

Endpoints:
  GET  /onboarding/session            -> current session (or empty if none)
  POST /onboarding/session            -> start session with an entry method
  POST /onboarding/bootstrap          -> capture confirmed experiences as context
  POST /onboarding/step               -> one interview turn (user message -> AI reply)
  POST /onboarding/correct            -> user corrects the AI's understanding
  POST /onboarding/finalize           -> generate + store career profile (F2)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.base import get_db
from app.services import onboarding_service as svc
from pydantic import BaseModel

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class BootstrapIn(BaseModel):
    entry_method: str  # upload / paste / scratch
    resume_id: int | None = None


class StepIn(BaseModel):
    message: str


class CorrectIn(BaseModel):
    dimension: str
    from_text: str = ""
    to_text: str = ""


@router.get("/session")
def session(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    s = svc.get_or_create_session(db, user_id=user_id)
    return s


@router.post("/session")
def start_session(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    # Entry method is chosen on the client; this just ensures a session exists.
    return svc.get_or_create_session(db, user_id=user_id)


@router.post("/bootstrap")
def bootstrap(
    req: BootstrapIn,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return svc.bootstrap_from_entry(
        db, user_id=user_id, entry_method=req.entry_method, resume_id=req.resume_id
    )


@router.post("/step")
def step(
    req: StepIn,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return svc.interview_step(db, user_id=user_id, message=req.message)


@router.post("/step/stream")
def step_stream(
    req: StepIn,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """访谈轮次的 SSE 流式版本。

    事件流：
      event: delta  data: {"text": "..."}   —— AI 回复增量
      event: done   data: {...}             —— 与 POST /step 返回结构一致的最终结果
      event: error  data: {"message": "...","code": "..."}
    """
    import json as _json

    from fastapi.responses import StreamingResponse

    from app.errors.exceptions import AppError

    def gen():
        try:
            for kind, payload in svc.interview_step_stream(db, user_id=user_id, message=req.message):
                if kind == "delta":
                    yield f"event: delta\ndata: {_json.dumps({'text': payload}, ensure_ascii=False)}\n\n"
                else:
                    yield f"event: done\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
        except AppError as exc:
            yield f"event: error\ndata: {_json.dumps({'message': exc.message, 'code': exc.code}, ensure_ascii=False)}\n\n"
        except Exception:  # noqa: BLE001 — 流里只能尽力通知，不能抛
            yield f"event: error\ndata: {_json.dumps({'message': '流式响应异常，请重试'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/correct")
def correct(
    req: CorrectIn,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return svc.correct_understanding(
        db,
        user_id=user_id,
        dimension=req.dimension,
        from_text=req.from_text,
        to_text=req.to_text,
    )


@router.post("/finalize")
def finalize(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return svc.finalize(db, user_id=user_id)
