"""Extract plain text from uploaded resume files (PDF / DOCX only).

OCR is explicitly out of MVP scope; scanned/image-only PDFs will yield little or
no text and are handled by the caller's degradation path.
"""
from __future__ import annotations

import io

from app.errors.exceptions import ValidationError_ as AppValidationError

ALLOWED_EXT = {".pdf", ".docx"}
# 简历不可能超过 50 页；超出视为异常/恶意文件，尽早拒绝以保护解析 worker。
MAX_PDF_PAGES = 50

# 魔数（文件头）校验：扩展名可伪造，内容不能。
_MAGIC = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",  # DOCX 本质是 ZIP 容器
}


def validate_file(filename: str, data: bytes) -> None:
    """Extension + magic-number check, called BEFORE persisting the upload."""
    ext = _ext_of(filename)
    if ext not in ALLOWED_EXT:
        raise AppValidationError(
            f"不支持的文件类型，仅支持 PDF / DOCX（{filename}）", code="unsupported_file_type"
        )
    if not data:
        raise AppValidationError("文件内容为空", code="empty_file")
    magic = _MAGIC[ext]
    if not data.startswith(magic):
        raise AppValidationError(
            "文件内容与扩展名不符（可能已损坏或被重命名）", code="file_content_mismatch"
        )


def _ext_of(filename: str) -> str:
    lower = (filename or "").lower()
    dot = lower.rfind(".")
    return lower[dot:] if dot != -1 else ""


def extract_text(filename: str, data: bytes) -> str:
    ext = _ext_of(filename)
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    raise AppValidationError(
        f"不支持的文件类型，仅支持 PDF / DOCX（{filename}）", code="unsupported_file_type"
    )


def _extract_pdf(data: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise AppValidationError("PDF 解析依赖未安装 (PyMuPDF)", code="deps_missing") from exc
    text_parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        if doc.page_count > MAX_PDF_PAGES:
            raise AppValidationError(
                f"PDF 页数超过上限（{MAX_PDF_PAGES} 页）", code="pdf_too_many_pages"
            )
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts).strip()


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise AppValidationError("DOCX 解析依赖未安装 (python-docx)", code="deps_missing") from exc
    doc = Document(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(paragraphs).strip()
