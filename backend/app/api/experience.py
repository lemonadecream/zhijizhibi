"""Manual experience entry (no AI)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.base import get_db
from app.schemas import ExperienceIn
from app.services.experience_service import save_manual

router = APIRouter(prefix="/experience", tags=["experience"])


@router.post("")
def create_manual_experience(req: ExperienceIn, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    save_manual(db, user_id=user_id, parsed=req.model_dump())
    return {"saved": True}
