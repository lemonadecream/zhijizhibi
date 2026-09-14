"""API request/response schemas (distinct from AI task schemas)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ----------------------------- Auth -----------------------------
class RegisterRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    identifier: str  # email or phone
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ----------------------------- Resume / F1 -----------------------------
class ResumeStatusOut(BaseModel):
    resume_id: int
    parse_status: str  # pending / parsing / parsed / failed
    filename: Optional[str] = None
    parsed_json: Optional[Any] = None
    error: Optional[str] = None


class ResumeConfirmIn(BaseModel):
    parsed_json: dict


class ParseTextIn(BaseModel):
    # Length limits are enforced in the service layer so failures return our
    # consistent ``{error:{code,message}}`` envelope rather than FastAPI's
    # native 422 shape.
    text: str


# ----------------------------- Experience (manual) -----------------------------
class ExperienceItem(BaseModel):
    school: Optional[str] = None
    major: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    level: Optional[int] = Field(default=None, ge=1, le=5)
    start: Optional[str] = None
    end: Optional[str] = None
    detail: Optional[str] = None


class ExperienceIn(BaseModel):
    education: list[dict] = Field(default_factory=list)
    internships: list[dict] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    skills: list[dict] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)


# ----------------------------- Profile / F2 -----------------------------
class ProfileOut(BaseModel):
    profile_id: Optional[int] = None
    status: Optional[str] = None  # None if not generated yet
    version: Optional[int] = None
    ability_tags: list[dict] = Field(default_factory=list)
    interest_tags: list[dict] = Field(default_factory=list)
    strengths: list[dict] = Field(default_factory=list)
    risks: list[dict] = Field(default_factory=list)
    preference_infer: dict = Field(default_factory=dict)
    ai_failed: bool = False


class ProfileUpdate(BaseModel):
    ability_tags: list[dict] = Field(default_factory=list)
    interest_tags: list[dict] = Field(default_factory=list)
    strengths: list[dict] = Field(default_factory=list)
    risks: list[dict] = Field(default_factory=list)
    preference_infer: dict = Field(default_factory=dict)


class ProfileGenerateOut(BaseModel):
    status: str
    profile_id: Optional[int] = None
