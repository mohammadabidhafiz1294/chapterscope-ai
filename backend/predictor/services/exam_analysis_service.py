"""Exam analysis service that orchestrates question processing and analysis."""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import json

from django.core.files.base import ContentFile
from django.utils import timezone

from .question_segmenter import QuestionSegmenter, QuestionSegment
from .question_classifier import QuestionClassifier, TopicClassification, ClassificationResult
from .topic_frequency_tracker import TopicFrequencyTracker, FrequencyAnalysis
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)


@dataclass
class ExamAnalysisResult:
    """Result of complete exam analysis."""
    success: bool
    exam_id: Optional[int]
    total_questions: int
    processed_questions: int
    topic_breakdown: Dict[str, Any]
    frequency_analysis: Dict[str, Any]
    predictions: Dict[str, Any]
    processing_stats: Dict[str, Any]
    error: Optional[str] = None


@dataclass
class AnalysisMetadata:
    """Metadata about the analysis process."""
    processing_time: float
    ai_requests_count: int
    confidence_score: float
    analysis_timestamp: datetime
    version: str = "1.0"


class ExamAnalysisService:
    """Service for comprehensive exam analysis using AI and quantum-inspired algorithms."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """Initialize exam analysis service."""
        self.gemini_client = gemini_client or GeminiClient()
        self.segmenter = QuestionSegmenter()
        self.classifier = QuestionClassifier(self.gemini_client)
        self.frequency_tracker = TopicFrequencyTracker()

        self.analysis_version = "1.0"
        logger.info("ExamAnalysisService initialized")

    def analyze_exam_file(self, file_content: bytes, filename: str,
                         syllabus_topics: Optional[List[str]] = None,
                         exam_history: Optional[List[Dict[str, Any]]] = None) -> ExamAnalysisResult:
        """
        Perform complete analysis of an exam file.

        Args:
            file_content: Raw file content
            filename: Name of the file
            syllabus_topics: Optional syllabus topics for context
            exam_history: Optional historical exam data

        Returns:
            ExamAnalysisResult with complete analysis
        """
        start_time = timezone.now()
        processing_stats = {
            'start_time': start_time,
            'segmentation_time': 0,
            'classification_time': 0,
            'frequency_analysis_time': 0,
            'total_processing_time': 0,
            'ai_requests_count': 0,
            'success_rate': 0.0
        }

        try:
            # Step 1: Segment questions from the file
            logger.info(f"Starting exam analysis for file: {filename}")
            segmentation_start = timezone.now()

            questions = self.segmenter.segment_questions(file_content, filename)
            processing_stats['segmentation_time'] = (timezone.now() - segmentation_start).total_seconds()

            if not questions:
                return ExamAnalysisResult(
                    success=False,
                    exam_id=None,
                    total_questions=0,
                    processed_questions=0,
                    topic_breakdown={},
                    frequency_analysis={},
                    predictions={},
                    processing_stats=processing_stats,
                    error="No questions found in the file"
                )

            processing_stats['total_questions'] = len(questions)
            logger.info(f"Segmented {len(questions)} questions from {filename}")

            # Step 2: Classify questions by topic
            classification_start = timezone.now()
            classification_result = self.classifier.classify_questions(questions, syllabus_topics)
            processing_stats['classification_time'] = (timezone.now() - classification_start).total_seconds()
            processing_stats['ai_requests_count'] = classification_result.processing_stats.get('ai_requests_count', 1)

            if not classification_result.success or not classification_result.classifications:
                return ExamAnalysisResult(
                    success=False,
                    exam_id=None,
                    total_questions=len(questions),
                    processed_questions=0,
                    topic_breakdown={},
                    frequency_analysis={},
                    predictions={},
                    processing_stats=processing_stats,
                    error="Failed to classify questions"
                )

            # Step 3: Analyze topic frequencies and trends
            frequency_start = timezone.now()
            frequency_result = self.frequency_tracker.analyze_frequencies(
                classification_result.classifications, exam_history
            )
            processing_stats['frequency_analysis_time'] = (timezone.now() - frequency_start).total_seconds()

            # Step 4: Generate comprehensive analysis report
            analysis_report = self._generate_analysis_report(
                questions, classification_result, frequency_result, processing_stats
            )

            # Calculate final statistics
            processing_stats['total_processing_time'] = (timezone.now() - start_time).total_seconds()
            processing_stats['processed_questions'] = len(classification_result.classifications)
            processing_stats['success_rate'] = (processing_stats['processed_questions'] / processing_stats['total_questions']) * 100

            logger.info(f"Successfully analyzed exam with {len(questions)} questions")

            return ExamAnalysisResult(
                success=True,
                exam_id=None,  # Will be set when saved to database
                total_questions=len(questions),
                processed_questions=len(classification_result.classifications),
                topic_breakdown=analysis_report['topic_breakdown'],
                frequency_analysis=analysis_report['frequency_analysis'],
                predictions=analysis_report['predictions'],
                processing_stats=processing_stats
            )

        except Exception as e:
            logger.error(f"Error analyzing exam file: {e}")
            processing_stats['total_processing_time'] = (timezone.now() - start_time).total_seconds()

            return ExamAnalysisResult(
                success=False,
                exam_id=None,
                total_questions=0,
                processed_questions=0,
                topic_breakdown={},
                frequency_analysis={},
                predictions={},
                processing_stats=processing_stats,
                error=str(e)
            )

    def analyze_exam_questions(self, questions: List[QuestionSegment],
                             syllabus_topics: Optional[List[str]] = None,
                             exam_history: Optional[List[Dict[str, Any]]] = None) -> ExamAnalysisResult:
        """
        Analyze a list of pre-segmented questions.

        Args:
            questions: List of question segments
            syllabus_topics: Optional syllabus topics for context
            exam_history: Optional historical exam data

        Returns:
            ExamAnalysisResult with complete analysis
        """
        start_time = timezone.now()
        processing_stats = {
            'start_time': start_time,
            'classification_time': 0,
            'frequency_analysis_time': 0,
            'total_processing_time': 0,
            'ai_requests_count': 0,
            'success_rate': 0.0
        }

        try:
            if not questions:
                return ExamAnalysisResult(
                    success=False,
                    exam_id=None,
                    total_questions=0,
                    processed_questions=0,
                    topic_breakdown={},
                    frequency_analysis={},
                    predictions={},
                    processing_stats=processing_stats,
                    error="No questions provided"
                )

            processing_stats['total_questions'] = len(questions)

            # Step 1: Classify questions by topic
            classification_start = timezone.now()
            classification_result = self.classifier.classify_questions(questions, syllabus_topics)
            processing_stats['classification_time'] = (timezone.now() - classification_start).total_seconds()
            processing_stats['ai_requests_count'] = classification_result.processing_stats.get('ai_requests_count', 1)

            if not classification_result.success or not classification_result.classifications:
                return ExamAnalysisResult(
                    success=False,
                    exam_id=None,
                    total_questions=len(questions),
                    processed_questions=0,
                    topic_breakdown={},
                    frequency_analysis={},
                    predictions={},
                    processing_stats=processing_stats,
                    error="Failed to classify questions"
                )

            # Step 2: Analyze topic frequencies and trends
            frequency_start = timezone.now()
            frequency_result = self.frequency_tracker.analyze_frequencies(
                classification_result.classifications, exam_history
            )
            processing_stats['frequency_analysis_time'] = (timezone.now() - frequency_start).total_seconds()

            # Step 3: Generate comprehensive analysis report
            analysis_report = self._generate_analysis_report(
                questions, classification_result, frequency_result, processing_stats
            )

            # Calculate final statistics
            processing_stats['total_processing_time'] = (timezone.now() - start_time).total_seconds()
            processing_stats['processed_questions'] = len(classification_result.classifications)
            processing_stats['success_rate'] = (processing_stats['processed_questions'] / processing_stats['total_questions']) * 100

            return ExamAnalysisResult(
                success=True,
                exam_id=None,
                total_questions=len(questions),
                processed_questions=len(classification_result.classifications),
                topic_breakdown=analysis_report['topic_breakdown'],
                frequency_analysis=analysis_report['frequency_analysis'],
                predictions=analysis_report['predictions'],
                processing_stats=processing_stats
            )

        except Exception as e:
            logger.error(f"Error analyzing exam questions: {e}")
            processing_stats['total_processing_time'] = (timezone.now() - start_time).total_seconds()

            return ExamAnalysisResult(
                success=False,
                exam_id=None,
                total_questions=len(questions) if questions else 0,
                processed_questions=0,
                topic_breakdown={},
                frequency_analysis={},
                predictions={},
                processing_stats=processing_stats,
                error=str(e)
            )

    def _generate_analysis_report(self, questions: List[QuestionSegment],
                                classification_result: ClassificationResult,
                                frequency_result: FrequencyAnalysis,
                                processing_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive analysis report."""
        report = {
            'topic_breakdown': {},
            'frequency_analysis': {},
            'predictions': {},
            'question_details': [],
            'metadata': {
                'analysis_version': self.analysis_version,
                'timestamp': timezone.now().isoformat(),
                'total_questions': len(questions),
                'classified_questions': len(classification_result.classifications)
            }
        }

        # Topic breakdown
        topic_hierarchy = self.classifier.get_topic_hierarchy(classification_result.classifications)
        report['topic_breakdown'] = topic_hierarchy

        # Frequency analysis
        frequency_report = self.frequency_tracker.generate_frequency_report(frequency_result)
        report['frequency_analysis'] = frequency_report

        # Predictions
        if frequency_result.predictions:
            top_predicted = self.frequency_tracker.get_top_predicted_topics(frequency_result.predictions, 10)
            report['predictions'] = {
                'top_topics': top_predicted,
                'summary': frequency_report['predictions']
            }

        # Question details
        for i, (question, classification) in enumerate(zip(questions, classification_result.classifications)):
            question_detail = {
                'id': i + 1,
                'question_text': question.question_text[:200] + '...' if len(question.question_text) > 200 else question.question_text,
                'question_type': question.question_type,
                'difficulty': question.difficulty,
                'marks': question.marks,
                'topic': classification.primary_topic,
                'secondary_topics': classification.secondary_topics,
                'confidence': classification.confidence,
                'academic_level': classification.academic_level,
                'prerequisites': classification.prerequisites
            }
            report['question_details'].append(question_detail)

        return report

    def get_analysis_metadata(self, result: ExamAnalysisResult) -> AnalysisMetadata:
        """Extract analysis metadata from result."""
        confidence_score = 0.0
        if result.topic_breakdown:
            confidence_score = result.topic_breakdown.get('avg_confidence', 0.0)

        return AnalysisMetadata(
            processing_time=result.processing_stats.get('total_processing_time', 0.0),
            ai_requests_count=result.processing_stats.get('ai_requests_count', 0),
            confidence_score=confidence_score,
            analysis_timestamp=timezone.now(),
            version=self.analysis_version
        )

    def validate_analysis_quality(self, result: ExamAnalysisResult) -> Dict[str, Any]:
        """Validate the quality of analysis results."""
        validation = {
            'overall_quality': 'unknown',
            'issues': [],
            'recommendations': [],
            'quality_score': 0.0
        }

        if not result.success:
            validation['overall_quality'] = 'failed'
            validation['issues'].append('Analysis failed')
            return validation

        # Check processing success rate
        success_rate = result.processing_stats.get('success_rate', 0)
        if success_rate < 70:
            validation['issues'].append(f'Low processing success rate: {success_rate:.1f}%')
            validation['recommendations'].append('Consider improving question segmentation')

        # Check classification confidence
        if result.topic_breakdown:
            avg_confidence = result.topic_breakdown.get('avg_confidence', 0)
            if avg_confidence < 0.6:
                validation['issues'].append(f'Low classification confidence: {avg_confidence:.2f}')
                validation['recommendations'].append('Review topic classifications manually')

        # Check topic diversity
        if result.topic_breakdown and result.topic_breakdown.get('topics'):
            topic_count = len(result.topic_breakdown['topics'])
            if topic_count < 3:
                validation['issues'].append(f'Low topic diversity: only {topic_count} topics identified')
                validation['recommendations'].append('Consider broader topic coverage in analysis')

        # Calculate quality score
        quality_score = success_rate * 0.4
        if result.topic_breakdown:
            quality_score += result.topic_breakdown.get('avg_confidence', 0) * 0.4
        if result.frequency_analysis:
            quality_score += 0.2  # Bonus for having frequency analysis

        validation['quality_score'] = min(quality_score, 1.0)

        # Determine overall quality
        if validation['quality_score'] > 0.8:
            validation['overall_quality'] = 'excellent'
        elif validation['quality_score'] > 0.6:
            validation['overall_quality'] = 'good'
        elif validation['quality_score'] > 0.4:
            validation['overall_quality'] = 'fair'
        else:
            validation['overall_quality'] = 'poor'

        return validation
