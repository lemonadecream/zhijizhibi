"""Authentication service."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors.exceptions import AuthError, ValidationError_ as AppValidationError
from app.repositories import create_user, get_user_by_email, get_user_by_phone
from app.security.password import hash_password, verify_password
from app.security.jwt import create_access_token


def register(db: Session, *, email: str | None, phone: str | None, password: str) -> str:
    if not email and not phone:
        raise AppValidationError("邮箱或手机号至少填写一项", code="missing_identifier")
    if len(password) < 6:
        raise AppValidationError("密码至少 6 位", code="weak_password")
    if email and get_user_by_email(db, email):
        raise AppValidationError("邮箱已被注册", code="email_taken", status_code=409)
    if phone and get_user_by_phone(db, phone):
        raise AppValidationError("手机号已被注册", code="phone_taken", status_code=409)
    user = create_user(db, email=email, phone=phone, password_hash=hash_password(password))
    return create_access_token(user.id)


def authenticate(db: Session, *, identifier: str, password: str) -> str:
    user = get_user_by_email(db, identifier) or get_user_by_phone(db, identifier)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("账号或密码错误")
    if user.status != 1:
        raise AuthError("账号已被禁用")
    return create_access_token(user.id)
