"""Authentication routes (register / login)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.base import get_db
from app.errors.exceptions import AppError, AuthError
from app.repositories import get_user_by_id
from app.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.security.rate_limit import SlidingWindowLimiter
from app.services.auth_service import authenticate, register

router = APIRouter(prefix="/auth", tags=["auth"])

# 登录：同一 IP+账号 15 分钟内最多 5 次失败；注册：同一 IP 每小时最多 10 次。
_login_limiter = SlidingWindowLimiter(max_events=5, window_seconds=15 * 60)
_register_limiter = SlidingWindowLimiter(max_events=10, window_seconds=60 * 60)


def _client_ip(request: Request) -> str:
    # 反向代理场景取 X-Forwarded-For 首段；直连场景用 socket 地址。
    fwd = request.headers.get("x-forwarded-for", "")
    first = fwd.split(",")[0].strip() if fwd else ""
    if first:
        return first
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=TokenResponse)
def register_user(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    key = f"register:{_client_ip(request)}"
    if not _register_limiter.allow(key):
        raise AppError("注册尝试过于频繁，请稍后再试", code="rate_limited", status_code=429)
    token = register(db, email=req.email, phone=req.phone, password=req.password)
    _register_limiter.hit(key)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login_user(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    key = f"login:{_client_ip(request)}:{req.identifier.strip().lower()}"
    if not _login_limiter.allow(key):
        raise AuthError("失败次数过多，请 15 分钟后再试", code="rate_limited", status_code=429)
    try:
        token = authenticate(db, identifier=req.identifier, password=req.password)
    except AuthError:
        # 只记失败尝试；成功后清除计数。
        _login_limiter.hit(key)
        raise
    _login_limiter.reset(key)
    return TokenResponse(access_token=token)


@router.get("/me")
def me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if user is None:
        raise AuthError("账号不存在")
    return {"user_id": user.id, "email": user.email, "phone": user.phone}
