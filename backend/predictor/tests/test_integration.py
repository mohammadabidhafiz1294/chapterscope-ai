"""End-to-end tests for the upload -> analysis -> record workflow."""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from predictor.models import ExamPaper, Syllabus, Topic
from predictor.services.eduquantum_integrator import EduQuantumIntegrator
from predictor.services.exam_analysis_service import (
    ExamAnalysisResult,
    ExamAnalysisService,
)
from predictor.services.gemini_client import GeminiClient, GeminiResponse, TopicResult


def upload_file(
    name="paper.txt",
    content=b"1. What is a qubit?\n2. Explain superposition.",
):
    return SimpleUploadedFile(name, content, content_type="text/plain")


def successful_analysis():
    return ExamAnalysisResult(
        success=True,
        exam_id=None,
        total_questions=2,
        processed_questions=2,
        topic_breakdown={
            "topics": {"Quantum Mechanics": {"count": 2}},
            "question_details": [
                {
                    "question_number": 1,
                    "question_text": "What is a qubit?",
                    "question_type": "short_answer",
                    "difficulty": "medium",
                    "primary_topic": "Quantum Mechanics",
                }
            ],
        },
        frequency_analysis={"topic_frequencies": {"Quantum Mechanics": 2}},
        predictions={"predicted_topics": ["Quantum Mechanics"]},
        processing_stats={"total_processing_time": 0.1, "success_rate": 100.0},
    )


@override_settings(GEMINI_API_KEY="test-key")
class TestExamWorkflow(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("alice", password="pw12345!")
        self.client.login(username="alice", password="pw12345!")

    def test_upload_then_process_exam(self):
        upload_response = self.client.post(
            reverse("predictor:exam_upload"),
            {
                "title": "Physics Paper",
                "description": "Final",
                "year": 2024,
                "file": upload_file(),
            },
        )
        self.assertEqual(upload_response.status_code, 302)
        exam = ExamPaper.objects.get()

        with patch.object(
            ExamAnalysisService,
            "analyze_exam_file",
            return_value=successful_analysis(),
        ):
            response = self.client.post(
                reverse("predictor:exam_process", args=[exam.pk])
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["analysis_data"]["total_questions"], 2)

        exam.refresh_from_db()
        self.assertTrue(exam.processed)
        self.assertEqual(exam.topics_covered, ["Quantum Mechanics"])
        breakdown = exam.analysis_data["topic_breakdown"]["topics"]
        self.assertEqual(breakdown["Quantum Mechanics"]["count"], 2)

    def test_process_records_failure(self):
        exam = ExamPaper.objects.create(
            user=self.user, title="Broken", year=2024, file=upload_file()
        )

        with patch.object(
            ExamAnalysisService,
            "analyze_exam_file",
            return_value=ExamAnalysisResult(
                success=False,
                exam_id=None,
                total_questions=0,
                processed_questions=0,
                topic_breakdown={},
                frequency_analysis={},
                predictions={},
                processing_stats={},
                error="No questions found",
            ),
        ):
            response = self.client.post(
                reverse("predictor:exam_process", args=[exam.pk])
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["status"], "error")
        exam.refresh_from_db()
        self.assertFalse(exam.processed)


@override_settings(GEMINI_API_KEY="test-key")
class TestSyllabusWorkflow(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("bob", password="pw12345!")
        self.client.login(username="bob", password="pw12345!")

    def test_syllabus_upload_and_process(self):
        upload_response = self.client.post(
            reverse("predictor:syllabus_upload"),
            {
                "title": "Physics Syllabus",
                "description": "Term 1",
                "subject": "Physics",
                "file": upload_file("syllabus.txt", b"Kinematics\nDynamics\nOptics"),
            },
        )
        self.assertEqual(upload_response.status_code, 302)
        syllabus = Syllabus.objects.get()

        gemini_result = GeminiResponse(
            success=True,
            content="",
            processing_time=0.0,
            topics=[
                TopicResult(
                    name="Kinematics",
                    description="Motion",
                    confidence=0.9,
                    category="Physics",
                    keywords=["velocity"],
                )
            ],
        )

        with patch.object(
            GeminiClient, "extract_topics", return_value=gemini_result
        ), patch.object(
            EduQuantumIntegrator,
            "process_syllabus_and_predict",
            side_effect=RuntimeError("prediction unavailable"),
        ):
            response = self.client.post(
                reverse("predictor:syllabus_process", args=[syllabus.pk])
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "success")
        self.assertFalse(payload["prediction_created"])

        syllabus.refresh_from_db()
        self.assertTrue(syllabus.processed)
        self.assertEqual(Topic.objects.filter(syllabus=syllabus).count(), 1)
        self.assertEqual(syllabus.topics_covered[0]["name"], "Kinematics")
