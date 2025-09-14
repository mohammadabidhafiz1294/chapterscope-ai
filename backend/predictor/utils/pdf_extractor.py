"""PDF text extraction utilities for syllabus processing."""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path

try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    PyPDF2 = None

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extract text content from PDF files."""

    def __init__(self):
        if not PDF_AVAILABLE:
            raise ImportError("PyPDF2 is required for PDF processing. Install with: pip install PyPDF2")

    def extract_text(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text from PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            Dict containing extracted text and metadata
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"PDF file not found: {file_path}")

            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                # Extract metadata
                metadata = {}
                if pdf_reader.metadata:
                    metadata = {
                        'title': pdf_reader.metadata.get('/Title', ''),
                        'author': pdf_reader.metadata.get('/Author', ''),
                        'subject': pdf_reader.metadata.get('/Subject', ''),
                        'creator': pdf_reader.metadata.get('/Creator', ''),
                        'producer': pdf_reader.metadata.get('/Producer', ''),
                        'pages': len(pdf_reader.pages)
                    }

                # Extract text from all pages
                text_content = []
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text.strip():  # Only add non-empty pages
                            text_content.append({
                                'page_number': page_num + 1,
                                'content': page_text.strip(),
                                'char_count': len(page_text)
                            })
                    except Exception as e:
                        logger.warning(f"Error extracting text from page {page_num + 1}: {e}")
                        continue

                # Combine all text
                full_text = '\n\n'.join([page['content'] for page in text_content])

                result = {
                    'success': True,
                    'text': full_text,
                    'pages': text_content,
                    'metadata': metadata,
                    'total_pages': len(pdf_reader.pages),
                    'total_chars': len(full_text)
                }

                logger.info(f"Successfully extracted text from PDF: {len(full_text)} characters, {len(pdf_reader.pages)} pages")
                return result

        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {e}")
            return {
                'success': False,
                'error': str(e),
                'text': '',
                'pages': [],
                'metadata': {},
                'total_pages': 0,
                'total_chars': 0
            }

    def get_page_count(self, file_path: str) -> int:
        """Get the number of pages in a PDF file."""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                return len(pdf_reader.pages)
        except Exception as e:
            logger.error(f"Error getting page count for PDF {file_path}: {e}")
            return 0

    def validate_pdf(self, file_path: str) -> bool:
        """Validate if the file is a valid PDF."""
        try:
            with open(file_path, 'rb') as file:
                PyPDF2.PdfReader(file)
                return True
        except Exception as e:
            logger.error(f"Invalid PDF file {file_path}: {e}")
            return False
