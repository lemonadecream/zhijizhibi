"""Onboarding interview service (Phase 1B).

Orchestrates the conversational flow:
  * create/get the interview session
  * bootstrap it from an entry method (upload / paste / scratch)
  * call the ``interview_step`` AI task each turn, persisting the progressive
    understanding + dimension state
  * accept user corrections to the AI's understanding
  * ``finalize`` -> runs F2 with interview context -> stores the career_profile

Business rules honored:
  * The final profile is generated ONLY at finalize (never incrementally).
  * The interview process state lives solely in ``career_interview_session``.
  * No scores / salary / match are ever produced by the AI (enforced in prompts).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.gateway import AIGatewayError, get_gateway, partial_response_text
from app.errors.exceptions import ValidationError_ as AppValidationError
from app.repositories import fill_profile, get_experiences, get_profile
from app.repositories_onboarding import (
    append_turn,
    create_or_get_session,
    get_session,
    mark_finalized,
    record_correction,
    record_entry_experiences,
    update_interview_state,
)


def _to_dimension_state_list(dimension_state: list[dict]) -> list[dict]:
    """Normalize the AI's dimension_state into a stable list keyed by D1..D6."""
    by_dim: dict[str, dict] = {d["dimension"]: d for d in (dimension_state or [])}
    out = []
    for dim in ("D1", "D2", "D3", "D4", "D5", "D6"):
        out.append(by_dim.get(dim, {"dimension": dim, "covered": False, "confidence": 0.0, "note": ""}))
    return out


def get_or_create_session(db: Session, *, user_id: int) -> dict:
    s = create_or_get_session(db, user_id=user_id)
    return _session_out(s)


def bootstrap_from_entry(
    db: Session, *, user_id: int, entry_method: str, resume_id: int | None = None
) -> dict:
    """Called after the user picked an entry and (for upload/paste) confirmed F1.

    Captures the confirmed experiences as the interview context snapshot.
    """
    experiences = get_experiences(db, user_id)
    s = create_or_get_session(db, user_id=user_id, entry_method=entry_method, resume_id=resume_id)
    record_entry_experiences(db, s, experiences)
    return _session_out(s)


def interview_step(db: Session, *, user_id: int, message: str) -> dict:
    s = get_session(db, user_id)
    if s is None:
        raise AppValidationError("访谈会话不存在，请先开始 onboarding", code="no_session")
    if s.status in ("completed", "finalized"):
        raise AppValidationError("访谈已完成，请直接生成职业画像", code="already_completed")

    message = (message or "").strip()
    if len(message) < 1:
        raise AppValidationError("请输入你的回答", code="empty_message")

    # Append the user's message first so the gateway sees the latest turn.
    append_turn(db, s, "user", message)

    gateway = get_gateway()
    try:
        result = gateway.run(
            "interview_step",
            {
                "entry_method": s.entry_method or "scratch",
                "experiences": s.experiences_snapshot or [],
                "history": s.question_history,
                "dimension_state": s.dimension_state or [],
                "understanding": s.understanding or {},
                "wants_to_know": s.wants_to_know or [],
                "latest_message": message,
            },
        )
    except AIGatewayError as exc:
        # Even on a gateway failure we keep the user's message; return a gentle
        # degraded response so the conversation doesn't dead-end.
        return {
            **_session_out(s),
            "ai_response": "我这边网络有点波动，稍等再聊一句？",
            "questions": ["你刚才提到的经历里，最让你有成就感的是哪一件？"],
            "completion_ready": False,
            "summary_candidate": "",
            "ai_status": "fallback",
        }

    out = result.data
    understanding = out.get("understanding", s.understanding or {})
    wants_to_know = out.get("wants_to_know", s.wants_to_know or [])
    dimension_state = _to_dimension_state_list(out.get("dimension_state", s.dimension_state or []))
    completion_ready = bool(out.get("completion_ready", False))
    summary_candidate = out.get("summary_candidate", "")

    update_interview_state(
        db, s,
        understanding=understanding,
        wants_to_know=wants_to_know,
        dimension_state=dimension_state,
        completion_ready=completion_ready,
        summary_candidate=summary_candidate,
    )
    # Persist the AI's reply into history for resume/refresh.
    append_turn(db, s, "ai", out.get("response", ""))

    return {
        **_session_out(s),
        "ai_response": out.get("response", ""),
        "questions": out.get("questions", []),
        "completion_ready": completion_ready,
        "summary_candidate": summary_candidate,
        "ai_status": result.status,
    }


def interview_step_stream(db: Session, *, user_id: int, message: str):
    """interview_step 的流式版本（SSE）。

    依次产出：
      ("delta", text) —— AI 回复的增量文本（已从流式 JSON 中提取 response 字段）
      ("done", out)   —— 与 interview_step 返回结构完全一致的最终结果
    校验/降级/持久化语义与非流式版本一致（单次尝试，失败走 fallback）。
    """
    s = get_session(db, user_id)
    if s is None:
        raise AppValidationError("访谈会话不存在，请先开始 onboarding", code="no_session")
    if s.status in ("completed", "finalized"):
        raise AppValidationError("访谈已完成，请直接生成职业画像", code="already_completed")

    message = (message or "").strip()
    if len(message) < 1:
        raise AppValidationError("请输入你的回答", code="empty_message")

    append_turn(db, s, "user", message)

    gateway = get_gateway()
    input_dict = {
        "entry_method": s.entry_method or "scratch",
        "experiences": s.experiences_snapshot or [],
        "history": s.question_history,
        "dimension_state": s.dimension_state or [],
        "understanding": s.understanding or {},
        "wants_to_know": s.wants_to_know or [],
        "latest_message": message,
    }

    sent_len = 0
    raw_parts: list[str] = []
    final_result = None
    for kind, payload in gateway.run_interview_stream(input_dict):
        if kind == "delta":
            # 累积原始输出，从中增量提取已生成的 response 文本
            raw_parts.append(payload)
            text = partial_response_text("".join(raw_parts))
            if len(text) > sent_len:
                yield ("delta", text[sent_len:])
                sent_len = len(text)
        else:
            final_result = payload

    result = final_result
    out = result.data
    understanding = out.get("understanding", s.understanding or {})
    wants_to_know = out.get("wants_to_know", s.wants_to_know or [])
    dimension_state = _to_dimension_state_list(out.get("dimension_state", s.dimension_state or []))

    update_interview_state(
        db, s,
        understanding=understanding,
        wants_to_know=wants_to_know,
        dimension_state=dimension_state,
        completion_ready=bool(out.get("completion_ready", False)),
        summary_candidate=out.get("summary_candidate", ""),
    )
    append_turn(db, s, "ai", out.get("response", ""))

    yield ("done", {
        **_session_out(s),
        "ai_response": out.get("response", ""),
        "questions": out.get("questions", []),
        "completion_ready": bool(out.get("completion_ready", False)),
        "summary_candidate": out.get("summary_candidate", ""),
        "ai_status": result.status,
    })


def correct_understanding(
    db: Session, *, user_id: int, dimension: str, from_text: str, to_text: str
) -> dict:
    """User edits the AI's understanding (click tag -> edit/delete OR free text)."""
    s = get_session(db, user_id)
    if s is None:
        raise AppValidationError("访谈会话不存在", code="no_session")

    record_correction(db, s, dimension=dimension, from_text=from_text, to_text=to_text)

    # Reflect the correction in the understanding snapshot immediately.
    understanding = dict(s.understanding or {})
    tags = list(understanding.get("tags", []))
    if from_text and from_text in tags:
        if to_text:
            tags[tags.index(from_text)] = to_text
        else:
            tags.remove(from_text)
    elif to_text and to_text not in tags:
        tags.append(to_text)
    understanding["tags"] = tags
    s.understanding = understanding
    from app.repositories_onboarding import save_session
    save_session(db, s)

    return _session_out(s)


def finalize(db: Session, *, user_id: int) -> dict:
    """Generate the career profile via F2 using interview context, then store it."""
    s = get_session(db, user_id)
    if s is None:
        raise AppValidationError("访谈会话不存在", code="no_session")

    experiences = get_experiences(db, user_id)
    understanding = s.understanding or {}
    # 从零开始 (scratch) 路径下用户可能尚未确认任何结构化经历,
    # 此时允许仅基于访谈理解生成画像; 但若理解与经历皆为空则仍报错。
    if not experiences and not (understanding.get("tags") or understanding.get("sentences")):
        raise AppValidationError("请先告诉我一些你的经历或想法，我再帮你生成画像", code="no_experience")

    interview_context = {
        "understanding": s.understanding or {},
        "corrections": s.corrections or [],
        "dimension_state": s.dimension_state or [],
        "wants_to_know": s.wants_to_know or [],
    }

    gateway = get_gateway()
    ai_failed = False
    try:
        result = gateway.run(
            "f2_profile",
            {
                "experiences": experiences,
                "preference": None,
                "career_goal": None,
                "interview_context": interview_context,
            },
        )
        data = result.data
        ai_failed = result.status == "fallback"
    except AIGatewayError:
        data = {}
        ai_failed = True

    # Reuse the existing profile persistence path (keeps versioning / revision log).
    existing = get_profile(db, user_id)
    if existing is None:
        placeholder_id = None
        # Build inline to avoid circular import with jobs.run_f2.
        from app.repositories import create_profile_placeholder
        ph = create_profile_placeholder(db, user_id)
        placeholder_id = ph.profile_id
        profile = fill_profile(db, placeholder_id, data, ai_failed=ai_failed)
    else:
        # Update the latest profile in place (edited version).
        from app.repositories import update_profile
        profile = update_profile(db, user_id, data)

    mark_finalized(db, s)

    return {
        "profile_id": profile.profile_id,
        "status": profile.status,
        "version": profile.version,
        "ai_failed": ai_failed,
    }


def _session_out(s) -> dict:
    return {
        "session_id": s.id,
        "status": s.status,
        "entry_method": s.entry_method,
        "resume_id": s.resume_id,
        "understanding": s.understanding or {},
        "wants_to_know": s.wants_to_know or [],
        "dimension_state": s.dimension_state or [],
        "history": s.question_history or [],
        "corrections": s.corrections or [],
        "summary_pending": s.summary_pending or {},
    }
