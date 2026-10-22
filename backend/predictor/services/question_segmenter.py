"""Question segmentation service for exam paper analysis."""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import nltk

logger = logging.getLogger(__name__)

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    try:
        nltk.download('punkt', quiet=True)
    except Exception as e:
        logger.warning(f"Could not download NLTK punkt data: {e}")

try:
    # Try to download punkt_tab for newer NLTK versions
    nltk.download('punkt_tab', quiet=True)
except Exception:
    logger.warning("Could not download punkt_tab - using regular punkt tokenizer")


@dataclass
class QuestionSegment:
    """Represents a segmented question from exam text."""
    question_number: int
    question_text: str
    question_type: str  # 'multiple_choice', 'short_answer', 'essay', 'true_false', etc.
    options: List[str]  # For multiple choice questions
    marks: Optional[int] = None
    topic_keywords: List[str] = None
    estimated_difficulty: str = 'medium'  # 'easy', 'medium', 'hard'


@dataclass
class SegmentationResult:
    """Result of question segmentation process."""
    success: bool
    questions: List[QuestionSegment]
    total_questions: int
    processing_stats: Dict[str, Any]
    error: Optional[str] = None


class QuestionSegmenter:
    """Service for segmenting questions from exam papers."""

    def __init__(self):
        """Initialize question segmenter."""
        # Question patterns for different formats
        self.question_patterns = {
            'numbered': re.compile(r'(\d+)\.?\s*(.+?)(?=\d+\.|$)', re.DOTALL),
            'lettered': re.compile(r'([a-zA-Z])\.?\s*(.+?)(?=[a-zA-Z]\.|$)', re.DOTALL),
            'bullet': re.compile(r'[•\-\*]\s*(.+?)(?=[•\-\*]|$)', re.DOTALL),
        }

        # Question type indicators
        self.type_indicators = {
            'multiple_choice': ['choose', 'select', 'which of', 'options:', 'a)', 'b)', 'c)', 'd)'],
            'true_false': ['true or false', 'true/false', 't/f', 'correct/incorrect'],
            'short_answer': ['briefly', 'explain in short', 'define', 'what is'],
            'essay': ['discuss', 'explain', 'describe', 'analyze', 'evaluate', 'critically'],
            'calculation': ['calculate', 'compute', 'find', 'determine', 'solve'],
        }

        logger.info("QuestionSegmenter initialized")

    def segment_questions(self, text: str) -> SegmentationResult:
        """
        Segment questions from exam text.

        Args:
            text: The exam text to segment

        Returns:
            SegmentationResult with segmented questions
        """
        try:
            # Preprocess text
            cleaned_text = self._preprocess_text(text)

            # Try different segmentation strategies
            questions = []

            # Strategy 1: Numbered questions (most common)
            numbered_questions = self._segment_numbered_questions(cleaned_text)
            if numbered_questions:
                questions.extend(numbered_questions)

            # Strategy 2: Lettered questions (sub-questions)
            if not questions:
                lettered_questions = self._segment_lettered_questions(cleaned_text)
                if lettered_questions:
                    questions.extend(lettered_questions)

            # Strategy 3: Bullet point questions
            if not questions:
                bullet_questions = self._segment_bullet_questions(cleaned_text)
                if bullet_questions:
                    questions.extend(bullet_questions)

            # Analyze each question
            analyzed_questions = []
            for question in questions:
                analyzed_question = self._analyze_question(question)
                analyzed_questions.append(analyzed_question)

            # Calculate processing statistics
            processing_stats = {
                'total_text_length': len(text),
                'cleaned_text_length': len(cleaned_text),
                'questions_found': len(analyzed_questions),
                'question_types': {},
                'avg_question_length': 0,
                'difficulty_distribution': {'easy': 0, 'medium': 0, 'hard': 0}
            }

            if analyzed_questions:
                # Count question types
                for q in analyzed_questions:
                    processing_stats['question_types'][q.question_type] = \
                        processing_stats['question_types'].get(q.question_type, 0) + 1
                    processing_stats['difficulty_distribution'][q.estimated_difficulty] += 1

                # Calculate average question length
                total_length = sum(len(q.question_text) for q in analyzed_questions)
                processing_stats['avg_question_length'] = total_length / len(analyzed_questions)

            logger.info(f"Successfully segmented {len(analyzed_questions)} questions")

            return SegmentationResult(
                success=True,
                questions=analyzed_questions,
                total_questions=len(analyzed_questions),
                processing_stats=processing_stats
            )

        except Exception as e:
            logger.error(f"Error segmenting questions: {e}")
            return SegmentationResult(
                success=False,
                questions=[],
                total_questions=0,
                processing_stats={'error': str(e)},
                error=str(e)
            )

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for better segmentation."""
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)

        # Normalize question markers
        text = re.sub(r'(\d+)\s*\.', r'\1.', text)  # Ensure space before numbering
        text = re.sub(r'([a-zA-Z])\s*\.', r'\1.', text)  # Ensure space before lettering

        # Remove page headers/footers (simple patterns)
        lines = text.split('\n')
        filtered_lines = []

        for line in lines:
            line = line.strip()
            # Skip very short lines that might be headers/footers
            if len(line) < 5 and line:
                continue
            # Skip lines that look like page numbers
            if re.match(r'^\d+$', line) and len(line) <= 3:
                continue
            filtered_lines.append(line)

        return '\n'.join(filtered_lines)

    def _segment_numbered_questions(self, text: str) -> List[QuestionSegment]:
        """Segment numbered questions (1., 2., etc.)."""
        questions = []

        # Find all numbered questions
        pattern = r'(\d+)\.\s*([^(\d+\.)]+?)(?=\d+\.|$)'
        matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)

        for match in matches:
            question_num = int(match[0])
            question_text = match[1].strip()

            # Extract options if it's a multiple choice question
            options = self._extract_options(question_text)

            question = QuestionSegment(
                question_number=question_num,
                question_text=question_text,
                question_type='unknown',  # Will be determined later
                options=options
            )
            questions.append(question)

        return questions

    def _segment_lettered_questions(self, text: str) -> List[QuestionSegment]:
        """Segment lettered questions (a., b., etc.)."""
        questions = []

        # Find all lettered questions
        pattern = r'([a-zA-Z])\.\s*([^([a-zA-Z]+\.)]+?)(?=[a-zA-Z]+\.|$)'
        matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)

        for i, match in enumerate(matches, 1):
            question_letter = match[0]
            question_text = match[1].strip()

            question = QuestionSegment(
                question_number=i,  # Convert letter to number
                question_text=f"{question_letter}. {question_text}",
                question_type='unknown',
                options=[]
            )
            questions.append(question)

        return questions

    def _segment_bullet_questions(self, text: str) -> List[QuestionSegment]:
        """Segment bullet point questions."""
        questions = []

        # Find all bullet questions
        pattern = r'[•\-\*]\s*([^•\-\*]+?)(?=[•\-\*]|$)'
        matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)

        for i, match in enumerate(matches, 1):
            question_text = match.strip()

            question = QuestionSegment(
                question_number=i,
                question_text=question_text,
                question_type='unknown',
                options=[]
            )
            questions.append(question)

        return questions

    def _extract_options(self, question_text: str) -> List[str]:
        """Extract multiple choice options from question text."""
        options = []

        # Look for option patterns
        option_patterns = [
            r'\b([a-dA-D])\)\s*([^a-dA-D\)]+?)(?=[a-dA-D]\)|$)',  # a), b), etc.
            r'\b([a-dA-D])\.\s*([^a-dA-D\.]+?)(?=[a-dA-D]\.|$)',  # a., b., etc.
            r'Option\s*([A-D])\s*:\s*([^Option]+?)(?=Option|$)',  # Option A:, etc.
        ]

        for pattern in option_patterns:
            matches = re.findall(pattern, question_text, re.IGNORECASE)
            if matches:
                options.extend([match[1].strip() for match in matches])
                break

        return options

    def _analyze_question(self, question: QuestionSegment) -> QuestionSegment:
        """Analyze a question to determine its type and properties."""
        text_lower = question.question_text.lower()

        # Determine question type
        question_type = 'short_answer'  # Default

        max_score = 0
        detected_type = None

        for q_type, indicators in self.type_indicators.items():
            score = sum(1 for indicator in indicators if indicator in text_lower)
            if score > max_score:
                max_score = score
                detected_type = q_type

        if detected_type:
            question_type = detected_type

        # Special case: if options are present, it's likely multiple choice
        if question.options:
            question_type = 'multiple_choice'

        # Estimate difficulty based on keywords and length
        difficulty = self._estimate_difficulty(question.question_text, question_type)

        # Extract marks if present
        marks = self._extract_marks(question.question_text)

        # Extract topic keywords
        topic_keywords = self._extract_topic_keywords(question.question_text)

        return QuestionSegment(
            question_number=question.question_number,
            question_text=question.question_text,
            question_type=question_type,
            options=question.options,
            marks=marks,
            topic_keywords=topic_keywords or [],
            estimated_difficulty=difficulty
        )

    def _estimate_difficulty(self, text: str, question_type: str) -> str:
        """Estimate question difficulty."""
        text_lower = text.lower()

        # Difficulty indicators
        hard_indicators = ['analyze', 'evaluate', 'critically', 'compare', 'contrast', 'synthesize']
        easy_indicators = ['define', 'list', 'name', 'identify', 'recall']

        hard_score = sum(1 for indicator in hard_indicators if indicator in text_lower)
        easy_score = sum(1 for indicator in easy_indicators if indicator in text_lower)

        # Length-based difficulty
        if len(text) > 500:
            hard_score += 1
        elif len(text) < 100:
            easy_score += 1

        # Type-based difficulty
        if question_type in ['essay', 'calculation']:
            hard_score += 1
        elif question_type == 'multiple_choice':
            easy_score += 1

        if hard_score > easy_score:
            return 'hard'
        elif easy_score > hard_score:
            return 'easy'
        else:
            return 'medium'

    def _extract_marks(self, text: str) -> Optional[int]:
        """Extract marks/points from question text."""
        # Look for patterns like (5 marks), [10], etc.
        patterns = [
            r'\((\d+)\s*marks?\)',
            r'\[(\d+)\s*marks?\]',
            r'(\d+)\s*marks?',
            r'\((\d+)\s*points?\)',
            r'(\d+)\s*points?'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        return None

    def _extract_topic_keywords(self, text: str) -> List[str]:
        """Extract potential topic keywords from question text."""
        # Common academic keywords to look for
        academic_keywords = [
            'algorithm', 'data', 'structure', 'function', 'variable', 'class', 'method',
            'database', 'query', 'table', 'network', 'security', 'protocol', 'system',
            'analysis', 'design', 'implementation', 'testing', 'optimization',
            'mathematics', 'calculus', 'algebra', 'geometry', 'statistics', 'probability',
            'physics', 'chemistry', 'biology', 'quantum', 'mechanics', 'thermodynamics'
        ]

        found_keywords = []
        text_lower = text.lower()

        for keyword in academic_keywords:
            if keyword in text_lower:
                found_keywords.append(keyword)

        return found_keywords[:5]  # Return top 5 keywords
