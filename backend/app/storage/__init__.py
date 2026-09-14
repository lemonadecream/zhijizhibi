"""Storage package."""
from app.storage.base import BaseStorage
from app.storage.local import LocalStorage

__all__ = ["BaseStorage", "LocalStorage"]
