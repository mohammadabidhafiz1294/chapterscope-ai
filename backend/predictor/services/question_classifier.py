"""Question classification service using Gemini AI."""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

from .gemini_client import GeminiClient
from .question_segmenter import QuestionSegment

logger = logging.getLogger(__name__)


@dataclass
class TopicClassification:
    """Classification result for a question."""
    primary_topic: str
    secondary_topics: List[str]
    confidence: float
    reasoning: str
    academic_level: str  # 'undergraduate', 'graduate', 'phd'
    prerequisites: List[str]


@dataclass
class ClassificationResult:
    """Result of question classification process."""
    success: bool
    classifications: List[TopicClassification]
    processing_stats: Dict[str, Any]
    error: Optional[str] = None


class QuestionClassifier:
    """Service for classifying exam questions by topic using AI."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """Initialize question classifier."""
        self.gemini_client = gemini_client or GeminiClient()

        # Academic topic categories
        self.topic_categories = {
            'computer_science': [
                'algorithms', 'data structures', 'programming', 'software engineering',
                'databases', 'networks', 'security', 'artificial intelligence', 'machine learning'
            ],
            'mathematics': [
                'calculus', 'algebra', 'geometry', 'statistics', 'probability',
                'discrete mathematics', 'linear algebra', 'numerical methods'
            ],
            'physics': [
                'mechanics', 'thermodynamics', 'electromagnetism', 'quantum physics',
                'optics', 'nuclear physics', 'astrophysics'
            ],
            'engineering': [
                'electrical', 'mechanical', 'civil', 'chemical', 'aerospace',
                'biomedical', 'environmental', 'materials science'
            ],
            'business': [
                'finance', 'marketing', 'management', 'economics', 'accounting',
                'operations research', 'strategy'
            ],
            'other': ['general', 'miscellaneous']
        }

        logger.info("QuestionClassifier initialized")

    def classify_questions(self, questions: List[QuestionSegment],
                          syllabus_topics: Optional[List[str]] = None) -> ClassificationResult:
        """
        Classify a list of questions by topic.

        Args:
            questions: List of question segments to classify
            syllabus_topics: Optional list of topics from syllabus for context

        Returns:
            ClassificationResult with topic classifications
        """
        try:
            classifications = []
            processing_stats = {
                'total_questions': len(questions),
                'successful_classifications': 0,
                'failed_classifications': 0,
                'topic_distribution': {},
                'avg_confidence': 0.0
            }

            # Process questions in batches to avoid API limits
            batch_size = 5
            for i in range(0, len(questions), batch_size):
                batch = questions[i:i + batch_size]
                batch_result = self._classify_batch(batch, syllabus_topics)

                if batch_result.success:
                    classifications.extend(batch_result.classifications)
                    processing_stats['successful_classifications'] += len(batch_result.classifications)
                else:
                    processing_stats['failed_classifications'] += len(batch)
                    logger.error(f"Failed to classify batch {i//batch_size + 1}: {batch_result.error}")

            # Calculate statistics
            if classifications:
                confidences = [c.confidence for c in classifications]
                processing_stats['avg_confidence'] = sum(confidences) / len(confidences)

                for classification in classifications:
                    topic = classification.primary_topic
                    processing_stats['topic_distribution'][topic] = \
                        processing_stats['topic_distribution'].get(topic, 0) + 1

            logger.info(f"Successfully classified {len(classifications)} out of {len(questions)} questions")

            return ClassificationResult(
                success=len(classifications) > 0,
                classifications=classifications,
                processing_stats=processing_stats
            )

        except Exception as e:
            logger.error(f"Error classifying questions: {e}")
            return ClassificationResult(
                success=False,
                classifications=[],
                processing_stats={'error': str(e)},
                error=str(e)
            )

    def _classify_batch(self, questions: List[QuestionSegment],
                       syllabus_topics: Optional[List[str]] = None) -> ClassificationResult:
        """Classify a batch of questions."""
        try:
            # Prepare context from syllabus topics
            context = ""
            if syllabus_topics:
                context = f"Syllabus topics for context: {', '.join(syllabus_topics[:10])}"

            # Prepare questions for classification
            questions_text = []
            for i, question in enumerate(questions, 1):
                question_info = f"Question {i}: {question.question_text}"
                if question.options:
                    question_info += f" Options: {', '.join(question.options[:4])}"
                questions_text.append(question_info)

            # Create classification prompt
            prompt = f"""
            Analyze the following exam questions and classify each by academic topic.
            {context}

            For each question, provide:
            1. Primary topic (most specific academic subject)
            2. Secondary topics (related subjects, max 2)
            3. Confidence score (0.0-1.0)
            4. Brief reasoning for classification
            5. Academic level (undergraduate/graduate/phd)
            6. Prerequisites (required background knowledge, max 3)

            Return a JSON object with this structure:
            {{
                "classifications": [
                    {{
                        "primary_topic": "Computer Science",
                        "secondary_topics": ["Algorithms", "Data Structures"],
                        "confidence": 0.95,
                        "reasoning": "Question involves algorithm analysis and data structure manipulation",
                        "academic_level": "undergraduate",
                        "prerequisites": ["Basic Programming", "Discrete Mathematics"]
                    }}
                ]
            }}

            Questions to classify:
            {' | '.join(questions_text)}

            Return only valid JSON.
            """

            # Get classification from Gemini
            response = self.gemini_client._make_request(prompt, max_tokens=1500)

            if 'candidates' in response and response['candidates']:
                content = response['candidates'][0]['content']['parts'][0]['text']

                # Parse JSON response
                try:
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1

                    if json_start != -1 and json_end > json_start:
                        json_content = content[json_start:json_end]
                        parsed_data = json.loads(json_content)

                        classifications = []
                        for i, class_data in enumerate(parsed_data.get('classifications', [])):
                            if i < len(questions):  # Ensure we don't exceed questions list
                                classification = TopicClassification(
                                    primary_topic=class_data.get('primary_topic', 'Unknown'),
                                    secondary_topics=class_data.get('secondary_topics', []),
                                    confidence=float(class_data.get('confidence', 0.5)),
                                    reasoning=class_data.get('reasoning', ''),
                                    academic_level=class_data.get('academic_level', 'undergraduate'),
                                    prerequisites=class_data.get('prerequisites', [])
                                )
                                classifications.append(classification)

                        return ClassificationResult(
                            success=True,
                            classifications=classifications,
                            processing_stats={'batch_size': len(questions)}
                        )
                    else:
                        raise ValueError("No JSON found in response")

                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.error(f"Failed to parse classification response: {e}")
                    return ClassificationResult(
                        success=False,
                        classifications=[],
                        processing_stats={'error': str(e)},
                        error=f"Failed to parse response: {e}"
                    )
            else:
                return ClassificationResult(
                    success=False,
                    classifications=[],
                    processing_stats={'error': 'No candidates in response'},
                    error="No candidates in response"
                )

        except Exception as e:
            logger.error(f"Error classifying batch: {e}")
            return ClassificationResult(
                success=False,
                classifications=[],
                processing_stats={'error': str(e)},
                error=str(e)
            )

    def get_topic_hierarchy(self, classifications: List[TopicClassification]) -> Dict[str, Any]:
        """
        Build a topic hierarchy from classifications.

        Args:
            classifications: List of topic classifications

        Returns:
            Hierarchical topic structure
        """
        hierarchy = {
            'topics': {},
            'total_questions': len(classifications),
            'avg_confidence': 0.0
        }

        if not classifications:
            return hierarchy

        # Calculate average confidence
        confidences = [c.confidence for c in classifications]
        hierarchy['avg_confidence'] = sum(confidences) / len(confidences)

        # Build topic hierarchy
        for classification in classifications:
            primary = classification.primary_topic

            if primary not in hierarchy['topics']:
                hierarchy['topics'][primary] = {
                    'count': 0,
                    'secondary_topics': {},
                    'avg_confidence': 0.0,
                    'academic_levels': {},
                    'questions': []
                }

            topic_data = hierarchy['topics'][primary]
            topic_data['count'] += 1
            topic_data['questions'].append({
                'confidence': classification.confidence,
                'academic_level': classification.academic_level,
                'prerequisites': classification.prerequisites
            })

            # Track secondary topics
            for secondary in classification.secondary_topics:
                topic_data['secondary_topics'][secondary] = \
                    topic_data['secondary_topics'].get(secondary, 0) + 1

            # Track academic levels
            level = classification.academic_level
            topic_data['academic_levels'][level] = \
                topic_data['academic_levels'].get(level, 0) + 1

        # Calculate averages
        for topic_data in hierarchy['topics'].values():
            if topic_data['questions']:
                topic_data['avg_confidence'] = sum(q['confidence'] for q in topic_data['questions']) / len(topic_data['questions'])

        return hierarchy

    def validate_classifications(self, classifications: List[TopicClassification]) -> Dict[str, Any]:
        """
        Validate classification quality and consistency.

        Args:
            classifications: List of classifications to validate

        Returns:
            Validation results
        """
        validation = {
            'total_classifications': len(classifications),
            'high_confidence_count': 0,
            'low_confidence_count': 0,
            'unique_primary_topics': set(),
            'validation_issues': []
        }

        if not classifications:
            validation['validation_issues'].append('No classifications to validate')
            return validation

        for classification in classifications:
            # Count confidence levels
            if classification.confidence > 0.8:
                validation['high_confidence_count'] += 1
            elif classification.confidence < 0.5:
                validation['low_confidence_count'] += 1

            # Track unique topics
            validation['unique_primary_topics'].add(classification.primary_topic)

            # Check for issues
            if not classification.primary_topic or classification.primary_topic == 'Unknown':
                validation['validation_issues'].append('Missing or unknown primary topic')
            if classification.confidence < 0.3:
                validation['validation_issues'].append('Very low confidence classification')
            if not classification.reasoning:
                validation['validation_issues'].append('Missing classification reasoning')

        validation['unique_primary_topics'] = len(validation['unique_primary_topics'])

        return validation
