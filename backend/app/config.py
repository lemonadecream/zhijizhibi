"""Application configuration loaded from environment variables.

All secrets and environment-specific values come from the environment
(or a local .env file during development). Nothing sensitive is hard-coded.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Core ---
    APP_NAME: str = "Career Decision Platform"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api"

    # --- Database ---
    # Production uses PostgreSQL. For local/testing you may point this at SQLite.
    DATABASE_URL: str = "sqlite:///./dev.db"

    # --- Auth ---
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # --- AI (OpenAI-compatible) ---
    # Never hard-code a model name or vendor in business code.
    # The gateway talks to any OpenAI-compatible Chat Completions endpoint.
    AI_BASE_URL: str = "https://api.openai.com/v1"
    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"
    # Provider selector: "openai" (OpenAI-compatible) or "mock" (testing only).
    AI_PROVIDER: Literal["openai", "mock"] = "openai"
    AI_REQUEST_TIMEOUT_SECONDS: float = 60.0
    AI_MAX_RETRIES: int = 2

    # --- Storage ---
    # Local disk storage root for uploaded files (dev). Swap for object storage in prod.
    STORAGE_ROOT: str = "./storage"
    MAX_UPLOAD_MB: int = 10

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173"


INSECURE_DEFAULT_JWT_SECRET = "change-me-in-production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_production_ready() -> None:
    """Fail fast at startup when running with an insecure JWT secret.

    DEBUG 模式（本地开发/测试）允许占位密钥；非 DEBUG 必须显式注入。
    """
    if not settings.DEBUG and settings.JWT_SECRET == INSECURE_DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is insecure (default placeholder). "
            "Set a real JWT_SECRET env var, or set DEBUG=true for local dev."
        )


settings = get_settings()
