"""Integration service for EduQuantum Predictor system."""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import json

from django.db import transaction
from django.utils import timezone

from ..models import ExamPaper, Topic, Prediction, Syllabus
from .exam_analysis_service import ExamAnalysisService
from .quantum_prediction_engine import QuantumPredictionEngine
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)


@dataclass
class IntegrationResult:
    """Result of integration operation."""
    success: bool
    message: str
    data: Dict[str, Any]
    error: Optional[str] = None
    processing_time: float = 0.0


@dataclass
class PredictionWorkflow:
    """Complete prediction workflow data."""
    exam_analysis: Dict[str, Any]
    quantum_prediction: Dict[str, Any]
    final_recommendations: List[str]
    confidence_score: float


class EduQuantumIntegrator:
    """Main integration service for the EduQuantum Predictor system."""

    def __init__(self):
        """Initialize the integrator."""
        self.exam_analysis_service = ExamAnalysisService()
        self.quantum_engine = QuantumPredictionEngine()
        self.gemini_client = GeminiClient()

        logger.info("EduQuantumIntegrator initialized")

    def process_syllabus_and_predict(self, syllabus_id: int, user_id: int) -> IntegrationResult:
        """
        Complete workflow: Process syllabus -> Extract topics -> Generate quantum predictions.

        Args:
            syllabus_id: ID of the syllabus to process
            user_id: ID of the user

        Returns:
            IntegrationResult with complete analysis
        """
        import time
        start_time = time.time()

        try:
            # Step 1: Get syllabus and validate
            syllabus = Syllabus.objects.get(id=syllabus_id, user_id=user_id)

            # Step 2: Extract syllabus topics
            syllabus_topics = self._extract_syllabus_topics(syllabus)

            # Step 3: Generate quantum predictions based on syllabus topics
            quantum_result = self._generate_quantum_predictions_from_syllabus(
                syllabus_topics
            )

            # Step 4: Create final recommendations
            recommendations = self._generate_syllabus_recommendations(
                syllabus_topics, quantum_result
            )

            # Step 5: Calculate overall confidence
            confidence_score = self._calculate_syllabus_confidence(
                syllabus_topics, quantum_result
            )

            # Step 6: Create prediction record
            workflow_data = PredictionWorkflow(
                exam_analysis={
                    'syllabus_topics': syllabus_topics,
                    'topic_count': len(syllabus_topics.get('topics', []))
                },
                quantum_prediction=quantum_result,
                final_recommendations=recommendations,
                confidence_score=confidence_score
            )

            prediction = self._create_syllabus_prediction_record(
                syllabus, workflow_data, user_id
            )

            processing_time = time.time() - start_time

            return IntegrationResult(
                success=True,
                message=f"Successfully processed syllabus and generated predictions",
                data={
                    'prediction_id': prediction.id,
                    'syllabus_topics': len(syllabus_topics.get('topics', [])),
                    'recommendations': len(recommendations),
                    'confidence_score': confidence_score,
                    'workflow_data': workflow_data
                },
                processing_time=processing_time
            )

        except Syllabus.DoesNotExist:
            return IntegrationResult(
                success=False,
                message="Syllabus not found",
                data={},
                error="Syllabus not found",
                processing_time=time.time() - start_time
            )
        except Exception as e:
            logger.error(f"Error in syllabus prediction workflow: {e}")
            return IntegrationResult(
                success=False,
                message="Failed to process syllabus and generate predictions",
                data={},
                error=str(e),
                processing_time=time.time() - start_time
            )

    def analyze_exam_and_update_predictions(self, exam_id: int, user_id: int) -> IntegrationResult:
        """
        Analyze a new exam and update existing predictions.

        Args:
            exam_id: ID of the exam to analyze
            user_id: ID of the user

        Returns:
            IntegrationResult with updated analysis
        """
        import time
        start_time = time.time()

        try:
            # Step 1: Get exam and validate
            exam = ExamPaper.objects.get(id=exam_id, user_id=user_id)

            # Step 2: Analyze the exam
            with exam.file.open('rb') as f:
                file_content = f.read()

            result = self.exam_analysis_service.analyze_exam_file(
                file_content=file_content,
                filename=exam.file.name
            )

            if not result.success:
                return IntegrationResult(
                    success=False,
                    message="Failed to analyze exam",
                    data={},
                    error=result.error,
                    processing_time=time.time() - start_time
                )

            # Step 3: Update exam with analysis results
            exam.questions_data = result.topic_breakdown.get('question_details', [])
            exam.topics_covered = list(result.topic_breakdown.get('topics', {}).keys())
            exam.analysis_data = {
                'topic_breakdown': result.topic_breakdown,
                'frequency_analysis': result.frequency_analysis,
                'predictions': result.predictions,
                'processing_stats': result.processing_stats
            }
            exam.processed = True
            exam.processed_at = timezone.now()
            exam.save()

            # Step 4: Update related predictions
            updated_predictions = self._update_related_predictions(exam, result)

            processing_time = time.time() - start_time

            return IntegrationResult(
                success=True,
                message=f"Successfully analyzed exam and updated {updated_predictions} predictions",
                data={
                    'exam_id': exam.id,
                    'topics_found': len(result.topic_breakdown.get('topics', {})),
                    'questions_analyzed': result.total_questions,
                    'updated_predictions': updated_predictions
                },
                processing_time=processing_time
            )

        except ExamPaper.DoesNotExist:
            return IntegrationResult(
                success=False,
                message="Exam paper not found",
                data={},
                error="Exam paper not found",
                processing_time=time.time() - start_time
            )
        except Exception as e:
            logger.error(f"Error analyzing exam: {e}")
            return IntegrationResult(
                success=False,
                message="Failed to analyze exam",
                data={},
                error=str(e),
                processing_time=time.time() - start_time
            )

    def _extract_syllabus_topics(self, syllabus: Syllabus) -> Dict[str, Any]:
        """Load normalized syllabus topics from the database."""
        topics_data = {
            'topics': [],
            'total_topics': 0,
            'extraction_method': 'database',
            'confidence': 0.0,
        }

        topics = Topic.objects.filter(syllabus=syllabus)
        topics_data['total_topics'] = topics.count()

        for topic in topics:
            metadata = topic.metadata or {}
            topics_data['topics'].append({
                'name': topic.name,
                'frequency': topic.frequency,
                'description': topic.description,
                'confidence': metadata.get('confidence', 0.5),
                'category': metadata.get('category', 'general'),
                'keywords': metadata.get('keywords', []),
            })

        if topics_data['topics']:
            topics_data['confidence'] = (
                sum(t['confidence'] for t in topics_data['topics'])
                / len(topics_data['topics'])
            )

        return topics_data

    def _extract_exam_topics(self, exam_paper: ExamPaper) -> Dict[str, Any]:
        """Load normalized exam topics from the database."""
        topics_data = {
            'topics': [],
            'total_topics': 0,
            'extraction_method': 'database',
            'confidence': 0.0,
        }

        topics = Topic.objects.filter(exam_paper=exam_paper)
        topics_data['total_topics'] = topics.count()

        for topic in topics:
            metadata = topic.metadata or {}
            topics_data['topics'].append({
                'name': topic.name,
                'frequency': topic.frequency,
                'description': topic.description,
                'confidence': metadata.get('confidence', 0.5),
                'category': metadata.get('category', 'general'),
            })

        if topics_data['topics']:
            topics_data['confidence'] = (
                sum(t['confidence'] for t in topics_data['topics'])
                / len(topics_data['topics'])
            )

        return topics_data

    def _generate_quantum_predictions_from_syllabus(self, syllabus_topics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate quantum-based predictions from syllabus topics."""
        try:
            # Prepare topic frequencies
            topic_frequencies = {}
            for topic in syllabus_topics.get('topics', []):
                topic_frequencies[topic['name']] = topic['frequency']

            # Generate quantum predictions
            quantum_result = self.quantum_engine.predict_topic_probabilities(
                topic_frequencies=topic_frequencies,
                topic_relationships=[],  # Could be enhanced with relationship data
                historical_patterns=None
            )

            return quantum_result

        except Exception as e:
            logger.error(f"Error generating quantum predictions from syllabus: {e}")
            return {
                'prediction_confidence': 0.0,
                'error': str(e)
            }

    def _generate_syllabus_recommendations(self, syllabus_topics: Dict[str, Any],
                                         quantum_result: Dict[str, Any]) -> List[str]:
        """Generate final recommendations based on syllabus analysis."""
        recommendations = []

        try:
            # Analyze topic coverage
            topics = syllabus_topics.get('topics', [])

            # Find well-covered topics
            well_covered = []
            poorly_covered = []

            for topic in topics:
                topic_name = topic['name']
                frequency = topic['frequency']

                if frequency > 10:  # Well covered in syllabus
                    well_covered.append(topic_name)
                elif frequency < 3:  # Poorly covered in syllabus
                    poorly_covered.append(topic_name)

            if well_covered:
                recommendations.append(f"Strong syllabus coverage in: {', '.join(well_covered[:3])}")

            if poorly_covered:
                recommendations.append(f"Consider expanding coverage of: {', '.join(poorly_covered[:3])}")

            # Quantum-based recommendations
            quantum_conf = quantum_result.get('prediction_confidence', 0.5)
            if quantum_conf > 0.8:
                recommendations.append("High confidence in quantum predictions - syllabus structure is optimal")
            elif quantum_conf < 0.3:
                recommendations.append("Low confidence in predictions - consider revising syllabus structure")

            if len(topics) < 5:
                recommendations.append("Syllabus has limited topics - consider adding more comprehensive coverage")

        except Exception as e:
            logger.error(f"Error generating syllabus recommendations: {e}")
            recommendations.append("Unable to generate specific recommendations due to analysis error")

        return recommendations

    def _calculate_syllabus_confidence(self, syllabus_topics: Dict[str, Any],
                                     quantum_result: Dict[str, Any]) -> float:
        """Calculate overall confidence score for syllabus analysis."""
        confidence_factors = []

        # Syllabus topics confidence
        syllabus_conf = syllabus_topics.get('confidence', 0.5)
        confidence_factors.append(syllabus_conf)

        # Quantum prediction confidence
        quantum_conf = quantum_result.get('prediction_confidence', 0.5)
        confidence_factors.append(quantum_conf)

        # Topic diversity factor
        topic_count = len(syllabus_topics.get('topics', []))
        diversity_factor = min(1.0, topic_count / 10)  # Max confidence with 10+ topics
        confidence_factors.append(diversity_factor)

        # Calculate weighted average
        if confidence_factors:
            return sum(confidence_factors) / len(confidence_factors)
        else:
            return 0.5

    def _create_syllabus_prediction_record(self, syllabus: Syllabus,
                                         workflow_data: PredictionWorkflow,
                                         user_id: int) -> Prediction:
        """Create a prediction record for syllabus analysis."""
        with transaction.atomic():
            prediction = Prediction.objects.create(
                user_id=user_id,
                syllabus=syllabus,
                prediction_type='HYBRID',
                description=f"Syllabus analysis for {syllabus.title}",
                accuracy_score=workflow_data.confidence_score * 100,
                quantum_result=workflow_data.quantum_prediction,
                classical_result={
                    'syllabus_analysis': workflow_data.exam_analysis
                },
                final_prediction={
                    'recommendations': workflow_data.final_recommendations,
                    'confidence_score': workflow_data.confidence_score
                },
                processing_time=0.0  # Could be calculated separately
            )

        return prediction

    def _generate_quantum_predictions(self, exam_topics: Dict[str, Any],
                                    exam_analysis_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate quantum-based predictions."""
        try:
            # Prepare topic frequencies
            topic_frequencies = {}
            for topic in exam_topics.get('topics', []):
                topic_frequencies[topic['name']] = topic['frequency']

            # Add exam analysis data
            for exam_result in exam_analysis_results:
                exam_topics_data = exam_result.get('topic_breakdown', {}).get('topics', {})
                for topic_name, topic_data in exam_topics_data.items():
                    if topic_name in topic_frequencies:
                        # Weight exam data more heavily
                        topic_frequencies[topic_name] = (topic_frequencies[topic_name] + topic_data.get('percentage', 0)) / 2

            # Generate quantum predictions
            quantum_result = self.quantum_engine.predict_topic_probabilities(
                topic_frequencies=topic_frequencies,
                topic_relationships=[],  # Could be enhanced with relationship data
                historical_patterns=None
            )

            return {
                'success': quantum_result.success,
                'topic_probabilities': quantum_result.topic_probabilities,
                'prediction_confidence': quantum_result.prediction_confidence,
                'execution_time': quantum_result.execution_time,
                'error': quantum_result.error
            }

        except Exception as e:
            logger.error(f"Error generating quantum predictions: {e}")
            return {
                'success': False,
                'error': str(e),
                'topic_probabilities': {},
                'prediction_confidence': 0.0
            }

    def _generate_recommendations(self, exam_topics: Dict[str, Any],
                                exam_analysis_results: List[Dict[str, Any]],
                                quantum_result: Dict[str, Any]) -> List[str]:
        """Generate final recommendations based on all analysis."""
        recommendations = []

        try:
            # Analyze topic coverage
            exam_topic_names = {t['name'] for t in exam_topics.get('topics', [])}

            # Find well-covered topics
            well_covered = []
            poorly_covered = []

            for topic in exam_topics.get('topics', []):
                topic_name = topic['name']
                frequency = topic['frequency']

                if frequency > 15:  # Well covered
                    well_covered.append(topic_name)
                elif frequency < 5:  # Poorly covered
                    poorly_covered.append(topic_name)

            # Generate recommendations
            if well_covered:
                recommendations.append(f"Topics well-covered in exams: {', '.join(well_covered[:3])}")

            if poorly_covered:
                recommendations.append(f"Consider increasing focus on: {', '.join(poorly_covered[:3])}")

            # Quantum-based recommendations
            if quantum_result.get('success', False):
                probabilities = quantum_result.get('topic_probabilities', {})
                high_prob_topics = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)[:3]
                if high_prob_topics:
                    topic_names = [name for name, prob in high_prob_topics]
                    recommendations.append(f"Quantum analysis suggests focusing on: {', '.join(topic_names)}")

            # General recommendations
            if len(exam_analysis_results) < 3:
                recommendations.append("Consider analyzing more exam papers for better predictions")

            if exam_topics.get('confidence', 0) < 0.7:
                recommendations.append("Exam topic extraction confidence is low - consider manual review")

        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            recommendations.append("Unable to generate specific recommendations due to analysis error")

        return recommendations

    def _calculate_overall_confidence(self, exam_topics: Dict[str, Any],
                                    exam_analysis_results: List[Dict[str, Any]],
                                    quantum_result: Dict[str, Any]) -> float:
        """Calculate overall confidence score for the prediction."""
        confidence_factors = []

        # Exam topics confidence
        exam_conf = exam_topics.get('confidence', 0.5)
        confidence_factors.append(exam_conf)

        # Exam analysis confidence
        if exam_analysis_results:
            exam_confidences = []
            for result in exam_analysis_results:
                processing_stats = result.get('processing_stats', {})
                success_rate = processing_stats.get('success_rate', 50) / 100
                exam_confidences.append(success_rate)

            if exam_confidences:
                avg_exam_conf = sum(exam_confidences) / len(exam_confidences)
                confidence_factors.append(avg_exam_conf)

        # Quantum prediction confidence
        quantum_conf = quantum_result.get('prediction_confidence', 0.5)
        confidence_factors.append(quantum_conf)

        # Data availability factor
        data_factor = min(1.0, (len(exam_analysis_results) + 1) / 5)  # Max confidence with 5+ exams
        confidence_factors.append(data_factor)

        # Calculate weighted average
        if confidence_factors:
            return sum(confidence_factors) / len(confidence_factors)
        else:
            return 0.5

    def _create_prediction_record(self, exam_paper: ExamPaper,
                                workflow_data: PredictionWorkflow,
                                user_id: int) -> Prediction:
        """Create a prediction record in the database."""
        with transaction.atomic():
            prediction = Prediction.objects.create(
                user_id=user_id,
                exam_paper=exam_paper,
                prediction_type='HYBRID',
                description=f"Comprehensive analysis of {exam_paper.title}",
                accuracy_score=workflow_data.confidence_score * 100,
                quantum_result=workflow_data.quantum_prediction,
                classical_result={
                    'exam_analysis': workflow_data.exam_analysis
                },
                final_prediction={
                    'recommendations': workflow_data.final_recommendations,
                    'confidence_score': workflow_data.confidence_score
                },
                processing_time=0.0  # Could be calculated separately
            )

        return prediction

    def _update_related_predictions(self, exam: ExamPaper,
                                  analysis_result: Any) -> int:
        """Update predictions related to the exam."""
        updated_count = 0

        try:
            # Find predictions for the same exam paper
            related_predictions = Prediction.objects.filter(
                user=exam.user,
                exam_paper=exam
            )

            for prediction in related_predictions:
                # Update classical results with new exam data
                classical_result = prediction.classical_result or {}
                exam_analysis = classical_result.get('exam_analysis', {})

                # Add new exam analysis
                exam_results = exam_analysis.get('results', [])
                exam_results.append({
                    'exam_id': exam.id,
                    'exam_title': exam.title,
                    'analysis': {
                        'topic_breakdown': analysis_result.topic_breakdown,
                        'frequency_analysis': analysis_result.frequency_analysis,
                        'processing_stats': analysis_result.processing_stats
                    }
                })

                exam_analysis['results'] = exam_results
                exam_analysis['total_exams'] = len(exam_results)
                classical_result['exam_analysis'] = exam_analysis

                prediction.classical_result = classical_result
                prediction.save()
                updated_count += 1

        except Exception as e:
            logger.error(f"Error updating related predictions: {e}")

        return updated_count

    def get_system_health_status(self) -> Dict[str, Any]:
        """Get overall system health status."""
        status = {
            'overall_health': 'unknown',
            'components': {},
            'issues': [],
            'recommendations': []
        }

        try:
            # Check database connectivity
            exam_count = ExamPaper.objects.count()
            status['components']['database'] = {
                'status': 'healthy',
                'details': f'{exam_count} exam papers in database'
            }

            # Check service availability
            try:
                # Test Gemini client
                self.gemini_client._make_request("Test", max_tokens=10)
                status['components']['gemini_api'] = {'status': 'healthy'}
            except Exception as e:
                status['components']['gemini_api'] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
                status['issues'].append('Gemini API connection failed')

            # Check quantum engine
            try:
                circuit_info = self.quantum_engine.get_quantum_circuit_info()
                status['components']['quantum_engine'] = {
                    'status': 'healthy',
                    'details': f"{circuit_info['num_qubits']} qubits configured"
                }
            except Exception as e:
                status['components']['quantum_engine'] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
                status['issues'].append('Quantum engine initialization failed')

            # Determine overall health
            unhealthy_components = [c for c in status['components'].values() if c.get('status') == 'unhealthy']
            if unhealthy_components:
                status['overall_health'] = 'degraded'
                status['recommendations'].append('Some components are unhealthy - check system logs')
            else:
                status['overall_health'] = 'healthy'

        except Exception as e:
            status['overall_health'] = 'critical'
            status['issues'].append(f'System health check failed: {str(e)}')

        return status
