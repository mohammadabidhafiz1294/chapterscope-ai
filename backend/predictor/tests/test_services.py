"""Unit tests for EduQuantum Predictor services."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime
from django.test import TestCase
from django.contrib.auth.models import User

from predictor.services.gemini_client import GeminiClient
from predictor.services.question_segmenter import QuestionSegmenter, QuestionSegment
from predictor.services.question_classifier import QuestionClassifier, TopicClassification
from predictor.services.topic_frequency_tracker import TopicFrequencyTracker
from predictor.services.exam_analysis_service import ExamAnalysisService
from predictor.services.quantum_prediction_engine import QuantumPredictionEngine
from predictor.services.eduquantum_integrator import EduQuantumIntegrator


class TestGeminiClient(TestCase):
    """Test cases for GeminiClient service."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = GeminiClient()

    @patch('predictor.services.gemini_client.requests.post')
    def test_make_request_success(self, mock_post):
        """Test successful API request."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{'text': 'Test response'}]
                }
            }]
        }
        mock_post.return_value = mock_response

        result = self.client._make_request("Test prompt")

        self.assertIsNotNone(result)
        self.assertIn('candidates', result)
        mock_post.assert_called_once()

    @patch('predictor.services.gemini_client.requests.post')
    def test_make_request_failure(self, mock_post):
        """Test API request failure."""
        mock_post.side_effect = Exception("API Error")

        result = self.client._make_request("Test prompt")

        self.assertIsNone(result)


class TestQuestionSegmenter(TestCase):
    """Test cases for QuestionSegmenter service."""

    def setUp(self):
        """Set up test fixtures."""
        self.segmenter = QuestionSegmenter()

    def test_segment_questions_empty_file(self):
        """Test segmentation with empty file."""
        result = self.segmenter.segment_questions(b"", "empty.txt")

        self.assertEqual(len(result), 0)

    def test_segment_questions_text_file(self):
        """Test segmentation with text content."""
        content = b"""
        1. What is Python?
        2. Explain variables in programming.
        3. What are loops?
        """

        result = self.segmenter.segment_questions(content, "test.txt")

        self.assertGreater(len(result), 0)
        self.assertIsInstance(result[0], QuestionSegment)

    def test_question_type_detection(self):
        """Test question type detection."""
        questions = [
            "What is the capital of France?",
            "Explain the process of photosynthesis.",
            "Calculate the area of a circle with radius 5.",
            "Compare and contrast mitosis and meiosis."
        ]

        for question in questions:
            segment = self.segmenter._detect_question_type(question)
            self.assertIsNotNone(segment.question_type)


class TestQuestionClassifier(TestCase):
    """Test cases for QuestionClassifier service."""

    def setUp(self):
        """Set up test fixtures."""
        self.gemini_client = Mock()
        self.classifier = QuestionClassifier(self.gemini_client)

    def test_classify_questions_empty_list(self):
        """Test classification with empty question list."""
        result = self.classifier.classify_questions([])

        self.assertFalse(result.success)
        self.assertEqual(len(result.classifications), 0)

    @patch('predictor.services.question_classifier.json.loads')
    def test_classify_questions_with_mock_response(self, mock_json_loads):
        """Test classification with mocked API response."""
        # Mock Gemini response
        mock_response = {
            'candidates': [{
                'content': {
                    'parts': [{'text': '{"classifications": [{"primary_topic": "Python", "secondary_topics": ["Programming"], "confidence": 0.9, "reasoning": "Test", "academic_level": "undergraduate", "prerequisites": ["Basic Programming"]}]}'}]
                }
            }]
        }

        self.gemini_client._make_request.return_value = mock_response
        mock_json_loads.return_value = {
            "classifications": [{
                "primary_topic": "Python",
                "secondary_topics": ["Programming"],
                "confidence": 0.9,
                "reasoning": "Question involves Python programming",
                "academic_level": "undergraduate",
                "prerequisites": ["Basic Programming"]
            }]
        }

        questions = [QuestionSegment(
            question_text="What is Python?",
            question_type="multiple_choice",
            difficulty="easy",
            marks=5,
            options=["Language", "Snake", "Tool"]
        )]

        result = self.classifier.classify_questions(questions)

        self.assertTrue(result.success)
        self.assertEqual(len(result.classifications), 1)
        self.assertEqual(result.classifications[0].primary_topic, "Python")


class TestTopicFrequencyTracker(TestCase):
    """Test cases for TopicFrequencyTracker service."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = TopicFrequencyTracker()

    def test_analyze_frequencies_empty(self):
        """Test frequency analysis with empty data."""
        result = self.tracker.analyze_frequencies([])

        self.assertFalse(result.success)
        self.assertEqual(len(result.topic_frequencies), 0)

    def test_calculate_current_frequencies(self):
        """Test current frequency calculation."""
        classifications = [
            TopicClassification(
                primary_topic="Python",
                secondary_topics=["Programming"],
                confidence=0.9,
                reasoning="Test",
                academic_level="undergraduate",
                prerequisites=["Basic Programming"]
            ),
            TopicClassification(
                primary_topic="Python",
                secondary_topics=["Programming"],
                confidence=0.8,
                reasoning="Test",
                academic_level="undergraduate",
                prerequisites=["Basic Programming"]
            )
        ]

        frequencies = self.tracker._calculate_current_frequencies(classifications)

        self.assertIn("Python", frequencies)
        self.assertEqual(frequencies["Python"]["count"], 2)
        self.assertAlmostEqual(frequencies["Python"]["percentage"], 100.0)


class TestExamAnalysisService(TestCase):
    """Test cases for ExamAnalysisService."""

    def setUp(self):
        """Set up test fixtures."""
        self.gemini_client = Mock()
        self.service = ExamAnalysisService(self.gemini_client)

    def test_analyze_exam_questions_empty(self):
        """Test analysis with empty question list."""
        result = self.service.analyze_exam_questions([])

        self.assertFalse(result.success)
        self.assertEqual(result.total_questions, 0)

    def test_validate_analysis_quality(self):
        """Test analysis quality validation."""
        result = Mock()
        result.success = True
        result.processing_stats = {'success_rate': 85}
        result.topic_breakdown = {'avg_confidence': 0.8}

        quality = self.service.validate_analysis_quality(result)

        self.assertTrue(quality['is_valid'])
        self.assertGreater(quality['quality_score'], 0)


class TestQuantumPredictionEngine(TestCase):
    """Test cases for QuantumPredictionEngine."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = QuantumPredictionEngine(num_qubits=4, max_iterations=10)

    @patch('predictor.services.quantum_prediction_engine.VQE')
    def test_predict_topic_probabilities(self, mock_vqe):
        """Test quantum prediction with mocked VQE."""
        # Mock VQE result
        mock_result = Mock()
        mock_result.optimal_parameters = [0.1, 0.2, 0.3, 0.4]
        mock_result.eigenvalue = -2.5
        mock_vqe.return_value.compute_minimum_eigenvalue.return_value = mock_result

        topic_frequencies = {"Python": 20.0, "Java": 15.0}

        result = self.engine.predict_topic_probabilities(topic_frequencies, [])

        self.assertTrue(result.success)
        self.assertIsNotNone(result.topic_probabilities)
        self.assertGreater(result.prediction_confidence, 0)

    def test_construct_hamiltonian(self):
        """Test Hamiltonian construction."""
        topic_frequencies = {"Python": 20.0, "Java": 15.0}
        relationships = []

        hamiltonian = self.engine._construct_hamiltonian(topic_frequencies, relationships)

        self.assertIsNotNone(hamiltonian)


class TestEduQuantumIntegrator(TestCase):
    """Test cases for EduQuantumIntegrator."""

    def setUp(self):
        """Set up test fixtures."""
        self.integrator = EduQuantumIntegrator()

    def test_get_system_health_status(self):
        """Test system health status check."""
        status = self.integrator.get_system_health_status()

        self.assertIn('overall_health', status)
        self.assertIn('components', status)
        self.assertIn('database', status['components'])

    @patch('predictor.services.eduquantum_integrator.ExamAnalysisService')
    def test_process_syllabus_and_predict(self, mock_analysis_service):
        """Test syllabus processing workflow."""
        # This would require more complex mocking of database objects
        # For now, just test that the method exists and handles errors
        result = self.integrator.process_syllabus_and_predict(999, 1)

        self.assertFalse(result.success)
        self.assertIn('not found', result.message.lower())


class TestIntegrationScenarios(TestCase):
    """Integration test scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_full_workflow_simulation(self):
        """Test a simulated full workflow."""
        # This would be an integration test that creates actual database objects
        # and tests the full pipeline

        # Create mock syllabus
        syllabus_data = {
            'title': 'Test Syllabus',
            'subject': 'Computer Science',
            'topics': [
                {'name': 'Python', 'frequency': 20.0},
                {'name': 'Java', 'frequency': 15.0}
            ]
        }

        # Test that services can handle the data structures
        segmenter = QuestionSegmenter()
        questions = segmenter.segment_questions(b"1. What is Python?", "test.txt")

        self.assertGreater(len(questions), 0)

        # Test classifier with mock
        classifier = QuestionClassifier(Mock())
        # Note: Would need more complex mocking for full integration test


if __name__ == '__main__':
    unittest.main()
