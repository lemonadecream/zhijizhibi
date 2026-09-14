"""Read-only runtime configuration endpoint.

Exposes ONLY non-sensitive runtime configuration so the frontend can
distinguish real AI vs mock vs degraded (fallback) responses.

NEVER returns secrets: API keys, tokens, endpoint URLs that embed secrets,
environment variable dumps, or any credentials. See P0-1 (AI 真实性失真).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.ai.metrics import metrics
from app.api.deps import get_current_user_id
from app.config import settings

router = APIRouter(prefix="/config", tags=["config"])


class AiConfigOut(BaseModel):
    ai_provider: str
    ai_available: bool


def compute_ai_available() -> bool:
    """True only when a real, usable AI provider is configured.

    Rules (per acceptance criteria):
      - provider == "mock"                                  -> False (demo only)
      - any real provider AND a non-empty API key present    -> True
      - otherwise                                           -> False
    """
    if settings.AI_PROVIDER == "mock":
        return False
    key = (settings.AI_API_KEY or "").strip()
    return bool(key)


@router.get("", response_model=AiConfigOut)
def get_config(user_id: int = Depends(get_current_user_id)):
    return AiConfigOut(
        ai_provider=settings.AI_PROVIDER,
        ai_available=compute_ai_available(),
    )


@router.get("/ai-stats")
def get_ai_stats(user_id: int = Depends(get_current_user_id)):
    """AI 调用指标（按任务聚合）：调用量 / 成功 / 降级 / 失败 / 延迟。

    登录即可读（聚合数据，无敏感字段，不含任何用户内容）。
    产品用途：成本与可靠性的"报表"——每个 AI 功能降级率多高、平均多慢。
    """
    return {"provider": settings.AI_PROVIDER, "tasks": metrics.snapshot()}
