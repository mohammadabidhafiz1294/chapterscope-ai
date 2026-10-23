"""In-memory data structures for the Phase 3 extraction pipeline.

These mirror the persisted ExtractionRun / ExtractionChunk / Question rows
but are produced first by the extractors and parsers, then saved by the
processor. Keeping them separate lets unit tests exercise parsing without a
database.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Extraction method labels (kept in sync with ExtractionRun.METHOD_CHOICES).
METHOD_PDF_TEXT = "PDF_TEXT"
METHOD_DOCX_TEXT = "DOCX_TEXT"
METHOD_PLAIN_TEXT = "PLAIN_TEXT"
METHOD_OCR = "OCR"
METHOD_MIXED = "MIXED"
METHOD_NONE = "NONE"

# Question extraction methods (kept in sync with Question.METHOD_CHOICES).
QMETHOD_RULE = "RULE"
QMETHOD_LLM = "LLM"
QMETHOD_OCR = "OCR"

# Chunk kinds (kept in sync with ExtractionChunk.KIND_CHOICES).
KIND_PAGE = "PAGE"
KIND_PARAGRAPH = "PARAGRAPH"
KIND_TABLE = "TABLE"
KIND_TEXT = "TEXT"

# Safe, user-facing error codes produced by the pipeline. These are stored in
# ExtractionRun.error_code and never include internal exception text.
ERROR_UNSUPPORTED = "unsupported_format"
ERROR_TOO_LARGE = "file_too_large"
ERROR_FILE_MISSING = "file_missing"
ERROR_CORRUPT = "corrupt_file"
ERROR_ENCRYPTED = "encrypted_pdf"
ERROR_PAGE_LIMIT = "page_limit_exceeded"
ERROR_CHAR_LIMIT = "char_limit_exceeded"
ERROR_EMPTY = "empty_document"
ERROR_OCR_REQUIRED = "ocr_required"
ERROR_OCR_FAILED = "ocr_failed"
ERROR_PARSER = "parser_error"
ERROR_INTERRUPTED = "interrupted"
ERROR_UNSAFE_PATH = "unsafe_path"


@dataclass
class ChunkText:
    """One extracted text unit with its boundary into the full document."""

    chunk_index: int
    text: str
    kind: str = KIND_TEXT
    page_number: Optional[int] = None
    method: str = METHOD_NONE
    char_start: int = 0
    char_end: int = 0
    confidence: Optional[float] = None
    is_low_text: bool = False
    warnings: List[str] = field(default_factory=list)


@dataclass
class DocumentExtraction:
    """Result of extracting one source file into ordered text chunks."""

    source_type: str  # "SYLLABUS" or "EXAM_PAPER"
    source_id: int
    file_hash: str
    method: str = METHOD_NONE
    chunks: List[ChunkText] = field(default_factory=list)
    full_text: str = ""
    page_count: int = 0
    total_chars: int = 0
    low_text_pages: List[int] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ocr_required: bool = False
    error_code: str = ""
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return not self.error_code and bool(self.chunks)


@dataclass
class OCRPageResult:
    """Result of OCR on a single PDF page."""

    text: str
    confidence: Optional[float] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExtractedQuestion:
    """One question (or subpart) parsed out of the reconstructed text.

    The raw span is preserved verbatim; ``normalized_text`` is the cleaned
    form used for search and dedup. Offsets reference the full reconstructed
    document text so the source chunk/page can be resolved.
    """

    question_number: str  # printed identifier, e.g. "2" or "a"
    parent_number: str = ""  # parent printed number for subparts, e.g. "2"
    raw_text: str = ""
    normalized_text: str = ""
    page_number: Optional[int] = None
    page_reference: str = ""
    chunk_index: Optional[int] = None
    char_start: int = 0
    char_end: int = 0
    marks: Optional[int] = None
    question_type: str = ""
    difficulty: str = ""
    options: List[str] = field(default_factory=list)
    confidence: float = 0.5
    method: str = QMETHOD_RULE
    warnings: List[str] = field(default_factory=list)
    # Transient: set by the processor after the parent row is created so
    # subparts can link to it. Not part of the parser output.
    parent_pk: Optional[int] = None
