"""Storage layer + file-validation unit tests (P0/P2 hardening).

Covers the security contract introduced in the P0 收口:
  * path traversal is structurally impossible (strict key whitelist);
  * ownership is enforced on read/delete when a user_id is provided;
  * uploaded files are validated by magic number, not just extension.
"""
from __future__ import annotations

import pytest

from app.errors.exceptions import NotFoundError, ValidationError_ as AppValidationError
from app.storage.local import LocalStorage
from app.utils.parse_file import validate_file


@pytest.fixture()
def storage(tmp_path):
    return LocalStorage(root=str(tmp_path / "storage_root"))


# ----------------------------- LocalStorage -----------------------------
def test_save_read_delete_roundtrip(storage):
    key = storage.save(user_id=1, filename="简历.pdf", data=b"%PDF-1.4 fake")
    assert key.startswith("1/") and len(key.split("/")[1]) == 32

    assert storage.read(key, user_id=1) == b"%PDF-1.4 fake"
    storage.delete(key, user_id=1)
    with pytest.raises(NotFoundError):
        storage.read(key, user_id=1)


def test_read_rejects_wrong_owner(storage):
    key = storage.save(user_id=1, filename="a.pdf", data=b"x")
    # 属主校验：他人读取返回"不存在"，不泄露文件是否存活。
    with pytest.raises(NotFoundError):
        storage.read(key, user_id=2)
    with pytest.raises(NotFoundError):
        storage.delete(key, user_id=2)
    # 属主本人不受影响
    assert storage.read(key, user_id=1) == b"x"


@pytest.mark.parametrize(
    "bad_key",
    [
        "1/../../users.db",       # 经典穿越
        "1/..%2f..%2fsecret",     # 编码穿越（非十六进制，必被拒）
        "1/short",                # 非 uuid hex
        "abc/0123456789abcdef0123456789abcdef",  # user_id 非数字
        "1/0123456789abcdef0123456789abcdef/extra",  # 多段
        "no-slash-key",
        "",
    ],
)
def test_malformed_keys_cannot_escape_root(storage, bad_key):
    with pytest.raises(NotFoundError):
        storage.read(bad_key)
    # delete 对非法 key 同样安全（静默拒绝，不抛未捕获异常）
    storage.delete(bad_key)


# ----------------------------- validate_file -----------------------------
PDF_MAGIC = b"%PDF-1.7\n..."
DOCX_MAGIC = b"PK\x03\x04" + b"\x14\x00\x00\x00" + b"\x00" * 16


def test_validate_file_accepts_real_pdf_and_docx():
    validate_file("resume.pdf", PDF_MAGIC)
    validate_file("resume.docx", DOCX_MAGIC)
    validate_file("简历.PDF", PDF_MAGIC)  # 大小写不敏感


def test_validate_file_rejects_content_mismatch():
    # 扩展名是 .pdf 但内容不是 PDF：伪装文件
    with pytest.raises(AppValidationError) as e:
        validate_file("evil.pdf", b"MZ\x90\x00 binary")
    assert e.value.code == "file_content_mismatch"

    with pytest.raises(AppValidationError):
        validate_file("fake.docx", b"%PDF-1.7")


def test_validate_file_rejects_bad_types():
    with pytest.raises(AppValidationError) as e:
        validate_file("notes.txt", b"hello")
    assert e.value.code == "unsupported_file_type"

    with pytest.raises(AppValidationError) as e:
        validate_file("empty.pdf", b"")
    assert e.value.code == "empty_file"

    with pytest.raises(AppValidationError):
        validate_file("noext", PDF_MAGIC)
