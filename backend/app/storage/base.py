"""File storage abstraction.

Swappable backend: local disk for dev, object storage (S3/OSS/COS) for prod.
Business code depends only on ``BaseStorage``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseStorage(ABC):
    @abstractmethod
    def save(self, *, user_id: int, filename: str, data: bytes) -> str:
        """Store ``data`` and return a stable ``file_id``."""

    @abstractmethod
    def read(self, file_id: str, *, user_id: int | None = None) -> bytes:
        """Read a file. ``user_id`` enforces ownership when provided."""
        ...

    @abstractmethod
    def delete(self, file_id: str, *, user_id: int | None = None) -> None:
        """Delete a file. ``user_id`` enforces ownership when provided."""
        ...
