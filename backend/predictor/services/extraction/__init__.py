"""Source-traceable document extraction (Phase 3).

Splits uploaded syllabus / exam-paper files into page- and chunk-level text
with provenance, detects likely-scanned PDFs via a pluggable OCR interface,
and segments individual questions with subpart linkage. No vector search,
chat generation or autonomous agents live here.
"""

from .processor import SourceProcessingService, process_source  # noqa: F401
