"""Shared API dependencies: authentication."""
from __future__ import annotations

from fastapi import Header

from app.errors.exceptions import AuthError
from app.security.jwt import decode_access_token


def get_current_user_id(authorization: str | None = Header(default=None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("缺少访问令牌")
    token = authorization[len("Bearer "):]
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        return int(sub)
    except Exception as exc:  # noqa: BLE001
        raise AuthError("访问令牌无效或已过期") from exc
