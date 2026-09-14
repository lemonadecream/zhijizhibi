"""FastAPI exception handlers.

All handlers return a consistent ``{error: {code, message}}`` envelope so the
frontend can handle errors uniformly. No raw exception details leak to clients.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors.exceptions import AppError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        # Last-resort guard so the service never returns an unhandled 500 with
        # internal tracebacks. Real errors are logged upstream.
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "服务器内部错误"}},
        )
