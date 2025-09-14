"""Topic extraction service for processing exam paper documents."""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import re

from .gemini_client import GeminiClient, TopicResult
from ..utils.pdf_extractor import PDFExtractor
from ..utils.docx_extractor import DOCXExtractor

logger = logging.getLogger(__name__)


@dataclass
class ProcessedTopic:
    """Processed topic with additional metadata."""
    name: str
    description: str
    confidence: float
    category: str
    keywords: List[str]
    frequency: int = 1
    source_text: str = ""


@dataclass
class TopicExtractionResult:
    """Result of topic extraction process."""
    success: bool
    topics: List[ProcessedTopic]
    processing_stats: Dict[str, Any]
    error: Optional[str] = None


class TopicExtractor:
    """Service for extracting and processing topics from exam paper documents."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """Initialize topic extractor."""
        self.gemini_client = gemini_client or GeminiClient()
        self.pdf_extractor = PDFExtractor()
        self.docx_extractor = DOCXExtractor()

        logger.info("TopicExtractor initialized")

    def extract_text_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text from various file formats.

        Args:
            file_path: Path to the file

        Returns:
            Dict containing extracted text and metadata
        """
        file_extension = file_path.lower().split('.')[-1]

        if file_extension == 'pdf':
            return self.pdf_extractor.extract_text(file_path)
        elif file_extension in ['docx', 'doc']:
            return self.docx_extractor.extract_text(file_path)
        elif file_extension == 'txt':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                return {
                    'success': True,
                    'text': text,
                    'total_chars': len(text),
                    'metadata': {}
                }
            except Exception as e:
                logger.error(f"Error reading text file {file_path}: {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'text': '',
                    'total_chars': 0,
                    'metadata': {}
                }
        else:
            return {
                'success': False,
                'error': f'Unsupported file format: {file_extension}',
                'text': '',
                'total_chars': 0,
                'metadata': {}
            }

    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text for better topic extraction.

        Args:
            text: Raw text from document

        Returns:
            Preprocessed text
        """
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)

        # Remove page numbers and headers/footers (simple pattern)
        text = re.sub(r'\n\s*\d+\s*\n', '\n', text)

        # Remove very short lines (likely headers/footers)
        lines = text.split('\n')
        filtered_lines = []
        for line in lines:
            line = line.strip()
            if len(line) > 10 or not line:  # Keep lines longer than 10 chars or empty lines
                filtered_lines.append(line)

        return '\n'.join(filtered_lines)

    def extract_topics(self, file_path: str, max_topics: int = 15) -> TopicExtractionResult:
        """
        Extract topics from an exam paper file.

        Args:
            file_path: Path to the exam paper file
            max_topics: Maximum number of topics to extract

        Returns:
            TopicExtractionResult with extracted topics
        """
        try:
            # Step 1: Extract text from file
            text_result = self.extract_text_from_file(file_path)
            if not text_result['success']:
                return TopicExtractionResult(
                    success=False,
                    topics=[],
                    processing_stats={'text_extraction': 'failed'},
                    error=text_result.get('error', 'Text extraction failed')
                )

            raw_text = text_result['text']
            if not raw_text.strip():
                return TopicExtractionResult(
                    success=False,
                    topics=[],
                    processing_stats={'text_extraction': 'empty'},
                    error='No text content found in file'
                )

            # Step 2: Preprocess text
            processed_text = self.preprocess_text(raw_text)

            # Step 3: Extract topics using Gemini
            gemini_result = self.gemini_client.extract_topics(processed_text, max_topics)

            if not gemini_result.success:
                return TopicExtractionResult(
                    success=False,
                    topics=[],
                    processing_stats={
                        'text_extraction': 'success',
                        'text_length': len(processed_text),
                        'gemini_processing': 'failed'
                    },
                    error=gemini_result.error
                )

            # Step 4: Process and enhance topics
            processed_topics = []
            for topic_result in gemini_result.topics:
                # Find source text snippets for this topic
                source_snippets = self._find_topic_context(processed_text, topic_result.name, topic_result.keywords)

                processed_topic = ProcessedTopic(
                    name=topic_result.name,
                    description=topic_result.description,
                    confidence=topic_result.confidence,
                    category=topic_result.category,
                    keywords=topic_result.keywords,
                    source_text=' | '.join(source_snippets[:3])  # Keep top 3 snippets
                )
                processed_topics.append(processed_topic)

            # Step 5: Calculate processing statistics
            processing_stats = {
                'text_extraction': 'success',
                'text_length': len(processed_text),
                'gemini_processing': 'success',
                'topics_found': len(processed_topics),
                'avg_confidence': sum(t.confidence for t in processed_topics) / len(processed_topics) if processed_topics else 0,
                'processing_time': gemini_result.processing_time,
                'file_metadata': text_result.get('metadata', {})
            }

            logger.info(f"Successfully extracted {len(processed_topics)} topics from {file_path}")

            return TopicExtractionResult(
                success=True,
                topics=processed_topics,
                processing_stats=processing_stats
            )

        except Exception as e:
            logger.error(f"Error extracting topics from {file_path}: {e}")
            return TopicExtractionResult(
                success=False,
                topics=[],
                processing_stats={'error': str(e)},
                error=str(e)
            )

    def _find_topic_context(self, text: str, topic_name: str, keywords: List[str], context_chars: int = 100) -> List[str]:
        """
        Find context snippets for a topic in the text.

        Args:
            text: The full text
            topic_name: Name of the topic
            keywords: Keywords associated with the topic
            context_chars: Number of characters for context

        Returns:
            List of context snippets
        """
        snippets = []
        text_lower = text.lower()
        topic_lower = topic_name.lower()

        # Find occurrences of topic name
        topic_positions = []
        start = 0
        while True:
            pos = text_lower.find(topic_lower, start)
            if pos == -1:
                break
            topic_positions.append(pos)
            start = pos + 1

        # Find occurrences of keywords
        for keyword in keywords[:3]:  # Check top 3 keywords
            keyword_lower = keyword.lower()
            start = 0
            while True:
                pos = text_lower.find(keyword_lower, start)
                if pos == -1:
                    break
                if pos not in topic_positions:  # Avoid duplicates
                    topic_positions.append(pos)
                start = pos + 1

        # Extract context for each position
        for pos in sorted(set(topic_positions))[:5]:  # Top 5 unique positions
            start_pos = max(0, pos - context_chars // 2)
            end_pos = min(len(text), pos + context_chars // 2)

            # Find sentence boundaries
            while start_pos > 0 and text[start_pos] not in '.!?\n':
                start_pos -= 1
            while end_pos < len(text) and text[end_pos] not in '.!?\n':
                end_pos += 1

            snippet = text[start_pos:end_pos].strip()
            if snippet and len(snippet) > 20:  # Only keep meaningful snippets
                snippets.append(snippet)

        return snippets

    def validate_topics(self, topics: List[ProcessedTopic]) -> Dict[str, Any]:
        """
        Validate extracted topics for quality and consistency.

        Args:
            topics: List of processed topics

        Returns:
            Validation results
        """
        validation_results = {
            'total_topics': len(topics),
            'avg_confidence': 0.0,
            'high_confidence_count': 0,
            'unique_categories': set(),
            'validation_issues': []
        }

        if not topics:
            validation_results['validation_issues'].append('No topics extracted')
            return validation_results

        confidences = []
        for topic in topics:
            confidences.append(topic.confidence)
            if topic.confidence > 0.8:
                validation_results['high_confidence_count'] += 1
            validation_results['unique_categories'].add(topic.category)

            # Check for issues
            if len(topic.name) < 3:
                validation_results['validation_issues'].append(f"Topic name too short: '{topic.name}'")
            if not topic.keywords:
                validation_results['validation_issues'].append(f"No keywords for topic: '{topic.name}'")

        validation_results['avg_confidence'] = sum(confidences) / len(confidences)
        validation_results['unique_categories'] = len(validation_results['unique_categories'])

        return validation_results
