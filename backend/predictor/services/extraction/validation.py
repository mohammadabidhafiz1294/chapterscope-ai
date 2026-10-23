"""File-level guards for the Phase 3 extraction pipeline.

Defends against malformed files, oversized content, unsupported types and
path escapes before any parser touches the bytes. Never executes macros or
embedded content; PDFs are parsed with PyPDF2 and DOCX with python-docx,
both of which are read-only and do not run scripts.
"""

import hashlib
import logging
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from django.conf import settings

from .types import (
    ERROR_CORRUPT,
    ERROR_EMPTY,
    ERROR_ENCRYPTED,
    ERROR_FILE_MISSING,
    ERROR_PAGE_LIMIT,
    ERROR_TOO_LARGE,
    ERROR_UNSAFE_PATH,
    ERROR_UNSUPPORTED,
)

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
DOC_CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass
class FileCheck:
    """Outcome of a pre-parse file guard."""

    ok: bool
    error_code: str = ""
    error_message: str = ""
    file_hash: str = ""
    file_size: int = 0
    page_count: Optional[int] = None  # PDFs only


def _extension(filename: str) -> str:
    name = filename or ""
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def resolve_safe_path(django_file) -> Tuple[Optional[str], str]:
    """Resolve a stored FileField to an absolute path under MEDIA_ROOT.

    Returns (path, error_code). Rejects anything that resolves outside
    MEDIA_ROOT (defends against path traversal via a crafted storage name).
    """
    if not django_file:
        return None, ERROR_FILE_MISSING
    try:
        raw_path = django_file.path
    except (NotImplementedError, ValueError):
        return None, ERROR_FILE_MISSING
    if not raw_path or not os.path.exists(raw_path):
        return None, ERROR_FILE_MISSING

    media_root = Path(getattr(settings, "MEDIA_ROOT", "") or "/").resolve()
    try:
        resolved = Path(raw_path).resolve()
        resolved.relative_to(media_root)
    except (ValueError, OSError):
        logger.warning("File path escaped MEDIA_ROOT; rejecting")
        return None, ERROR_UNSAFE_PATH
    return str(resolved), ""


def sha256_file(path: str) -> str:
    """SHA-256 of a file, streamed in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_head(path: str, size: int = 16) -> bytes:
    with open(path, "rb") as handle:
        return handle.read(size)


def _docx_uncompressed_size(path: str) -> Optional[int]:
    """Total uncompressed size of entries inside a DOCX (zip) archive."""
    try:
        with zipfile.ZipFile(path) as archive:
            return sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, OSError):
        return None


def check_document_file(django_file) -> FileCheck:
    """Run every pre-parse guard for an uploaded document.

    Checks, in order: presence, size, extension, magic bytes, PDF
    readability / page cap, DOCX zip-bomb cap, TXT sanity. Returns a
    FileCheck whose ``file_hash`` is only set when the file passed.
    """
    path, path_err = resolve_safe_path(django_file)
    if path_err:
        msg = {
            ERROR_FILE_MISSING: "The source file is missing from storage.",
            ERROR_UNSAFE_PATH: "The source file path is invalid.",
        }.get(path_err, "The source file could not be read.")
        return FileCheck(ok=False, error_code=path_err, error_message=msg)

    size = os.path.getsize(path)
    max_size = getattr(settings, "MAX_FILE_SIZE", 10 * 1024 * 1024)
    if size > max_size:
        return FileCheck(
            ok=False,
            error_code=ERROR_TOO_LARGE,
            error_message=(
                f"The file exceeds the maximum allowed size "
                f"({max_size} bytes)."
            ),
            file_size=size,
        )
    if size == 0:
        return FileCheck(
            ok=False,
            error_code=ERROR_EMPTY,
            error_message="The uploaded file is empty.",
            file_size=0,
        )

    ext = _extension(getattr(django_file, "name", "") or path)
    head = _read_head(path)

    if ext == "pdf":
        return _check_pdf(path, size, head)
    if ext == "docx":
        return _check_docx(path, size, head)
    if ext == "doc":
        return FileCheck(
            ok=False,
            error_code=ERROR_UNSUPPORTED,
            error_message=(
                "Legacy .doc files are not supported. "
                "Convert the file to .docx or .pdf and re-upload."
            ),
            file_size=size,
        )
    if ext == "txt":
        return _check_txt(path, size, head)

    return FileCheck(
        ok=False,
        error_code=ERROR_UNSUPPORTED,
        error_message=(
            f"Unsupported file type '{ext}'. "
            "Allowed types: PDF, DOCX, TXT."
        ),
        file_size=size,
    )


def _check_pdf(path: str, size: int, head: bytes) -> FileCheck:
    if not head.startswith(PDF_MAGIC):
        return FileCheck(
            ok=False,
            error_code=ERROR_CORRUPT,
            error_message="The file is not a valid PDF.",
            file_size=size,
        )
    try:
        import PyPDF2

        with open(path, "rb") as handle:
            reader = PyPDF2.PdfReader(handle)
            page_count = len(reader.pages)
            if reader.is_encrypted:
                return FileCheck(
                    ok=False,
                    error_code=ERROR_ENCRYPTED,
                    error_message="The PDF is password-protected.",
                    file_size=size,
                )
            if page_count == 0:
                return FileCheck(
                    ok=False,
                    error_code=ERROR_EMPTY,
                    error_message="The PDF contains no pages.",
                    file_size=size,
                )
    except Exception as exc:  # PyPDF2 raises several exception types
        logger.warning("PDF pre-parse check failed: %s", exc)
        return FileCheck(
            ok=False,
            error_code=ERROR_CORRUPT,
            error_message="The PDF could not be read.",
            file_size=size,
        )

    max_pages = getattr(settings, "EXTRACTION_MAX_PAGES", 300)
    if page_count > max_pages:
        return FileCheck(
            ok=False,
            error_code=ERROR_PAGE_LIMIT,
            error_message=(
                f"The PDF has {page_count} pages, exceeding the limit "
                f"of {max_pages}."
            ),
            file_size=size,
            page_count=page_count,
        )

    return FileCheck(
        ok=True, file_hash=sha256_file(path), file_size=size,
        page_count=page_count,
    )


def _check_docx(path: str, size: int, head: bytes) -> FileCheck:
    if not head.startswith(ZIP_MAGIC):
        return FileCheck(
            ok=False,
            error_code=ERROR_CORRUPT,
            error_message="The file is not a valid DOCX document.",
            file_size=size,
        )
    uncompressed = _docx_uncompressed_size(path)
    if uncompressed is None:
        return FileCheck(
            ok=False,
            error_code=ERROR_CORRUPT,
            error_message="The DOCX archive is corrupt.",
            file_size=size,
        )
    max_uncompressed = getattr(
        settings, "EXTRACTION_MAX_DOCX_UNCOMPRESSED", 50 * 1024 * 1024
    )
    if uncompressed > max_uncompressed:
        return FileCheck(
            ok=False,
            error_code=ERROR_TOO_LARGE,
            error_message=(
                "The DOCX archive expands to more than the allowed size. "
                "It may be a compressed (zip-bomb) file."
            ),
            file_size=size,
        )
    try:
        from docx import Document

        Document(path)
    except Exception as exc:
        logger.warning("DOCX pre-parse check failed: %s", exc)
        return FileCheck(
            ok=False,
            error_code=ERROR_CORRUPT,
            error_message="The DOCX document could not be read.",
            file_size=size,
        )
    return FileCheck(ok=True, file_hash=sha256_file(path), file_size=size)


def _check_txt(path: str, size: int, head: bytes) -> FileCheck:
    # A NUL byte in the first block almost always means this is not text.
    if b"\x00" in head:
        return FileCheck(
            ok=False,
            error_code=ERROR_CORRUPT,
            error_message="The file does not appear to be plain text.",
            file_size=size,
        )
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            handle.read(1)
    except UnicodeDecodeError:
        return FileCheck(
            ok=False,
            error_code=ERROR_CORRUPT,
            error_message="The text file could not be decoded as UTF-8.",
            file_size=size,
        )
    return FileCheck(ok=True, file_hash=sha256_file(path), file_size=size)
