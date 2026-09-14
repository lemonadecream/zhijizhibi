"""Background jobs for long AI tasks (F1 resume parse, F2 profile generation).

These run outside the request lifecycle (FastAPI BackgroundTasks / a worker
process). They open their own DB session and never return data to the caller;
progress is observed by polling the entity status. This satisfies the
"only resume parsing + profile generation are asynchronous" rule without
introducing a message broker.
"""
from __future__ import annotations

from app.ai.gateway import get_gateway
from app.db.base import SessionLocal
from app.errors.exceptions import AIGatewayError
from app.logging_config import logger
from app.models.resume import Resume
from app.repositories import (
    create_profile_placeholder,
    fill_profile,
    get_experiences,
    get_preference,
    get_profile,
    save_resume_parse_result,
)


def run_f1(resume_id: int) -> None:
    db = SessionLocal()
    try:
        r = db.get(Resume, resume_id)
        if r is None or not r.raw_text:
            return
        gateway = get_gateway()
        try:
            result = gateway.run("f1_resume_parse", {"raw_text": r.raw_text})
            save_resume_parse_result(db, resume_id, result.data)
        except AIGatewayError as exc:
            # No fallback path configured -> record failure so UI can recover.
            save_resume_parse_result(db, resume_id, {}, failed=True, error=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("run_f1 failed: %s", exc)
        try:
            save_resume_parse_result(db, resume_id, {}, failed=True, error=str(exc))
        except Exception:
            pass
    finally:
        db.close()


def run_f2(user_id: int, profile_id: int) -> None:
    db = SessionLocal()
    try:
        gateway = get_gateway()
        experiences = get_experiences(db, user_id)
        preference = get_preference(db, user_id)
        try:
            result = gateway.run(
                "f2_profile",
                {"experiences": experiences, "preference": preference},
            )
            fill_profile(db, profile_id, result.data, ai_failed=(result.status == "fallback"))
        except AIGatewayError as exc:
            fill_profile(db, profile_id, {}, ai_failed=True)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("run_f2 failed: %s", exc)
        try:
            fill_profile(db, profile_id, {}, ai_failed=True)
        except Exception:
            pass
    finally:
        db.close()
