"""Tests for predictor services."""

from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase

from predictor.models import ExamPaper, Prediction, Syllabus, Topic
from predictor.services.eduquantum_integrator import EduQuantumIntegrator
from predictor.services.exam_analysis_service import ExamAnalysisService
from predictor.services.question_classifier import (
    ClassificationResult,
    TopicClassification,
)
from predictor.services.question_segmenter import QuestionSegmenter


def upload_file(
    name="paper.txt",
    content=b"1. What is a qubit?\n2. Calculate the eigenvalue.",
):
    return SimpleUploadedFile(name, content, content_type="text/plain")


class TestDecodeContent(TestCase):
    def test_decodes_bytes(self):
        self.assertEqual(
            ExamAnalysisService._decode_content(b"1. Question"), "1. Question"
        )

    def test_passes_through_text(self):
        self.assertEqual(
            ExamAnalysisService._decode_content("already text"), "already text"
        )

    def test_invalid_bytes_do_not_raise(self):
        self.assertEqual(ExamAnalysisService._decode_content(b"\xff\xfe"), "")


class TestQuestionSegmenter(TestCase):
    def setUp(self):
        self.segmenter = QuestionSegmenter()

    def test_segments_numbered_questions(self):
        text = (
            "1. Explain the concept of quantum entanglement.\n"
            "2. Calculate the energy of a photon with wavelength 500 nm.\n"
            "3. Define the Pauli exclusion principle."
        )

        result = self.segmenter.segment_questions(text)

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.total_questions, 2)

    def test_empty_text_returns_no_questions(self):
        result = self.segmenter.segment_questions("   ")

        self.assertTrue(result.success)
        self.assertEqual(result.questions, [])
        self.assertEqual(result.total_questions, 0)


class TestExamAnalysisService(TestCase):
    def test_analysis_with_mocked_classifier(self):
        service = ExamAnalysisService()
        service.classifier = MagicMock()
        service.classifier.classify_questions.return_value = ClassificationResult(
            success=True,
            classifications=[
                TopicClassification(
                    primary_topic="Quantum Mechanics",
                    secondary_topics=[],
                    confidence=0.9,
                    reasoning="mentions qubit",
                    academic_level="undergraduate",
                    prerequisites=[],
                )
            ],
            processing_stats={"ai_requests_count": 1},
        )
        service.frequency_tracker.ai_requests_count = 0
        service.classifier.get_topic_hierarchy.return_value = {
            "topics": {"Quantum Mechanics": {"question_count": 1}}
        }

        result = service.analyze_exam_file(
            b"1. What is a qubit?\n2. Explain superposition.",
            "exam.txt",
        )

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.total_questions, 1)
        self.assertIn("topics", result.topic_breakdown)


class TestIntegratorTopicExtraction(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw12345!")
        self.syllabus = Syllabus.objects.create(
            user=self.user,
            title="Syllabus",
            subject="Physics",
            file=upload_file("syllabus.txt"),
        )
        self.exam = ExamPaper.objects.create(
            user=self.user, title="Exam", year=2024, file=upload_file()
        )
        self.integrator = EduQuantumIntegrator()

    def test_extract_syllabus_topics(self):
        Topic.objects.create(
            syllabus=self.syllabus,
            name="Kinematics",
            frequency=4,
            metadata={"confidence": 0.8, "category": "Physics"},
        )

        topics = self.integrator._extract_syllabus_topics(self.syllabus)

        self.assertEqual(topics["total_topics"], 1)
        self.assertEqual(topics["topics"][0]["name"], "Kinematics")
        self.assertEqual(topics["topics"][0]["frequency"], 4)
        self.assertAlmostEqual(topics["confidence"], 0.8)

    def test_extract_exam_topics(self):
        Topic.objects.create(exam_paper=self.exam, name="Optics", frequency=2)

        topics = self.integrator._extract_exam_topics(self.exam)

        self.assertEqual(topics["total_topics"], 1)
        self.assertEqual(topics["topics"][0]["name"], "Optics")
        self.assertAlmostEqual(topics["confidence"], 0.5)

    def test_syllabus_prediction_is_created_as_hybrid(self):
        Topic.objects.create(syllabus=self.syllabus, name="Kinematics", frequency=2)
        self.integrator.quantum_engine = MagicMock()
        self.integrator.quantum_engine.predict_topic_probabilities.return_value = {
            "prediction_confidence": 0.8,
            "topic_probabilities": {"Kinematics": 0.8},
        }

        result = self.integrator.process_syllabus_and_predict(
            self.syllabus.id, self.user.id
        )

        self.assertTrue(result.success)
        prediction = Prediction.objects.get(pk=result.data["prediction_id"])
        self.assertEqual(prediction.prediction_type, "HYBRID")
        self.assertEqual(prediction.syllabus, self.syllabus)


class TestPredictionSourceConstraint(TestCase):
    def test_prediction_cannot_reference_syllabus_and_exam(self):
        user = User.objects.create_user("bob", password="pw12345!")
        syllabus = Syllabus.objects.create(
            user=user, title="S", subject="Physics", file=upload_file("s.txt")
        )
        exam = ExamPaper.objects.create(
            user=user, title="E", year=2024, file=upload_file()
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Prediction.objects.create(
                    user=user, syllabus=syllabus, exam_paper=exam
                )
