"""Application-specific exceptions."""
from __future__ import annotations


class AppError(Exception):
    """Base class for expected, user-facing errors.

    ``status_code`` is returned to the client; ``code`` is a stable machine code.
    """

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class PermissionError_(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationError_(AppError):
    status_code = 422
    code = "validation_error"


class AIGatewayError(AppError):
    """Raised when the AI Gateway exhausts retries and cannot produce a result.

    ``fallback_available`` tells the caller whether a manual/degraded path exists.
    """

    status_code = 502
    code = "ai_gateway_error"

    def __init__(self, message: str, *, fallback_available: bool = False, task: str | None = None):
        super().__init__(message)
        self.fallback_available = fallback_available
        self.task = task
