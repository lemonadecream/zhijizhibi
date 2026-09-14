"""Career profile (F2) routes: generate, view, edit."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.base import get_db
from app.schemas import ProfileGenerateOut, ProfileOut, ProfileUpdate
from app.services.profile_service import (
    generate_profile,
    get_current_profile,
    update_current_profile,
)

router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/generate", response_model=ProfileGenerateOut)
def generate(
    bg: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return generate_profile(db, user_id=user_id, bg=bg)


@router.get("", response_model=ProfileOut)
def view(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    p = get_current_profile(db, user_id=user_id)
    if p is None:
        return ProfileOut(status=None)
    return ProfileOut(
        profile_id=p.profile_id,
        status=p.status,
        version=p.version,
        ability_tags=p.ability_tags,
        interest_tags=p.interest_tags,
        strengths=p.strengths,
        risks=p.risks,
        preference_infer=p.preference_infer,
        ai_failed=bool(p.preference_infer.get("_ai_failed")),
    )


@router.put("", response_model=ProfileOut)
def update(
    req: ProfileUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    p = update_current_profile(
        db,
        user_id=user_id,
        data={
            "ability_tags": req.ability_tags,
            "interest_tags": req.interest_tags,
            "strengths": req.strengths,
            "risks": req.risks,
            "preference_infer": req.preference_infer,
        },
    )
    return ProfileOut(
        profile_id=p.profile_id,
        status=p.status,
        version=p.version,
        ability_tags=p.ability_tags,
        interest_tags=p.interest_tags,
        strengths=p.strengths,
        risks=p.risks,
        preference_infer=p.preference_infer,
        ai_failed=bool(p.preference_infer.get("_ai_failed")),
    )
