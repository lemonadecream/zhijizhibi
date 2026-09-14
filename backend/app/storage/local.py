"""Local-disk storage backend (development).

Files are kept outside the web root under ``STORAGE_ROOT`` and never served via a
public URL. Production swaps this for private object storage; the interface is identical.
"""
from __future__ import annotations

import os
import re
import uuid

from app.config import settings
from app.errors.exceptions import NotFoundError
from app.storage.base import BaseStorage

# save() 生成的 key 形如 "{user_id}/{uuid4().hex}"。这里用严格白名单而非
# 过滤黑名单：任何不含规整 user_id + 32位十六进制 的 key 一律拒绝，
# 从根上杜绝 "../" 路径穿越。
_KEY_RE = re.compile(r"^\d+/[0-9a-f]{32}$")


class LocalStorage(BaseStorage):
    def __init__(self, root: str | None = None):
        self.root = root or settings.STORAGE_ROOT
        os.makedirs(self.root, exist_ok=True)

    def _path(self, user_id: int, file_id: str) -> str:
        d = os.path.join(self.root, str(user_id))
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, file_id)

    def save(self, *, user_id: int, filename: str, data: bytes) -> str:
        file_id = uuid.uuid4().hex
        # Composite key encodes the owner dir so read/delete are self-locating.
        key = f"{user_id}/{file_id}"
        # Store original filename alongside for reference (metadata only).
        with open(self._path(user_id, file_id + ".name"), "w", encoding="utf-8") as f:
            f.write(filename)
        with open(self._path(user_id, file_id), "wb") as f:
            f.write(data)
        return key

    def read(self, file_id: str, *, user_id: int | None = None) -> bytes:
        path, owner = self._resolve(file_id)
        if user_id is not None and owner is not None and owner != user_id:
            # 不区分"不存在"与"非本人"，避免探测他人文件是否存活。
            raise NotFoundError("file not found")
        if path is None or not os.path.exists(path):
            raise NotFoundError("file not found")
        with open(path, "rb") as f:
            return f.read()

    def delete(self, file_id: str, *, user_id: int | None = None) -> None:
        path, owner = self._resolve(file_id)
        if user_id is not None and owner is not None and owner != user_id:
            raise NotFoundError("file not found")
        if path and os.path.exists(path):
            os.remove(path)
            name_file = path + ".name"
            if os.path.exists(name_file):
                os.remove(name_file)

    def _resolve(self, key: str) -> tuple[str | None, int | None]:
        """Validate key format and map it to an absolute path under the root.

        Returns ``(path, owner_user_id)``; ``(None, None)`` when malformed.
        """
        if not isinstance(key, str) or not _KEY_RE.match(key):
            return None, None
        user_id_str, file_id = key.split("/", 1)
        return self._path(int(user_id_str), file_id), int(user_id_str)
