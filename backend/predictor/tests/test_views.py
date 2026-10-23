"""Tests for predictor views."""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from predictor.models import ExamPaper, Syllabus, Topic
from predictor.services.eduquantum_integrator import (
    EduQuantumIntegrator,
    IntegrationResult,
)
from predictor.services.gemini_client import GeminiClient, GeminiResponse, TopicResult


def upload_file(
    name="paper.txt",
    content=b"1. What is a qubit?\n2. Calculate the eigenvalue.",
):
    return SimpleUploadedFile(name, content, content_type="text/plain")


class TestAuthAndPages(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("alice", password="pw12345!")
        self.client.login(username="alice", password="pw12345!")

    def test_pages_require_login(self):
        self.client.logout()
        for url_name in (
            "predictor:dashboard",
            "predictor:exam_list",
            "predictor:syllabus_list",
            "predictor:prediction_list",
            "predictor:topic_analysis",
        ):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302, url_name)

    def test_list_pages_render(self):
        for url_name in (
            "predictor:dashboard",
            "predictor:exam_list",
            "predictor:syllabus_list",
            "predictor:prediction_list",
            "predictor:topic_analysis",
        ):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, url_name)

    def test_syllabus_upload_creates_record(self):
        response = self.client.post(
            reverse("predictor:syllabus_upload"),
            {
                "title": "Physics Syllabus",
                "description": "Term 1",
                "subject": "Physics",
                "file": upload_file("syllabus.txt"),
            },
        )
        self.assertEqual(response.status_code, 302)
        syllabus = Syllabus.objects.get()
        self.assertEqual(syllabus.user, self.user)
        self.assertEqual(syllabus.title, "Physics Syllabus")

    def test_exam_upload_creates_record(self):
        response = self.client.post(
            reverse("predictor:exam_upload"),
            {
                "title": "Physics Paper",
                "description": "Final",
                "year": 2024,
                "file": upload_file("exam.txt"),
            },
        )
        self.assertEqual(response.status_code, 302)
        exam = ExamPaper.objects.get()
        self.assertEqual(exam.user, self.user)
        self.assertEqual(exam.year, 2024)

    def test_exam_detail_is_scoped_to_owner(self):
        exam = ExamPaper.objects.create(
            user=self.user, title="Owned exam", year=2024, file=upload_file()
        )
        other = User.objects.create_user("bob", password="pw12345!")
        self.client.force_login(other)

        response = self.client.get(reverse("predictor:exam_detail", args=[exam.pk]))

        self.assertEqual(response.status_code, 404)


@override_settings(GEMINI_API_KEY="test-key")
class TestAIEndpointGuards(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("alice", password="pw12345!")
        self.client.login(username="alice", password="pw12345!")
        self.syllabus = Syllabus.objects.create(
            user=self.user,
            title="Syllabus",
            subject="Physics",
            file=upload_file("syllabus.txt"),
        )
        self.exam = ExamPaper.objects.create(
            user=self.user, title="Exam", year=2024, file=upload_file()
        )

    def test_syllabus_process_without_api_key_returns_503(self):
        with self.settings(GEMINI_API_KEY=""):
            response = self.client.post(
                reverse("predictor:syllabus_process", args=[self.syllabus.pk])
            )

        self.assertEqual(response.status_code, 503)
        self.syllabus.refresh_from_db()
        self.assertFalse(self.syllabus.processed)

    def test_exam_process_without_api_key_returns_503(self):
        with self.settings(GEMINI_API_KEY=""):
            response = self.client.post(
                reverse("predictor:exam_process", args=[self.exam.pk])
            )

        self.assertEqual(response.status_code, 503)
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.processed)

    def test_syllabus_process_saves_json_serializable_topics(self):
        gemini_result = GeminiResponse(
            success=True,
            content="",
            processing_time=0.0,
            topics=[
                TopicResult(
                    name="Kinematics",
                    description="Motion of bodies",
                    confidence=0.9,
                    category="Physics",
                    keywords=["motion"],
                )
            ],
        )

        with patch.object(
            GeminiClient, "extract_topics", return_value=gemini_result
        ), patch.object(
            EduQuantumIntegrator,
            "process_syllabus_and_predict",
            return_value=IntegrationResult(
                success=True, message="ok", data={"prediction_id": 1}
            ),
        ):
            response = self.client.post(
                reverse("predictor:syllabus_process", args=[self.syllabus.pk])
            )

        self.assertEqual(response.status_code, 200)
        self.syllabus.refresh_from_db()
        self.assertTrue(self.syllabus.processed)
        self.assertEqual(self.syllabus.topic_count, 1)
        self.assertEqual(self.syllabus.topics_covered[0]["name"], "Kinematics")
        self.assertEqual(Topic.objects.filter(syllabus=self.syllabus).count(), 1)

    def test_prediction_create_uses_integrator(self):
        with patch.object(
            EduQuantumIntegrator,
            "analyze_exam_and_update_predictions",
            return_value=IntegrationResult(
                success=True, message="ok", data={"updated_predictions": 0}
            ),
        ) as analyze:
            response = self.client.post(
                reverse("predictor:prediction_create"),
                {"exam_paper": self.exam.pk, "prediction_type": "HYBRID"},
            )

        self.assertRedirects(response, reverse("predictor:prediction_list"))
        analyze.assert_called_once_with(exam_id=self.exam.pk, user_id=self.user.pk)


class TestHealthEndpoint(TestCase):
    def test_health_is_anonymous_and_leaks_nothing(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        body = response.content.decode("utf-8").lower()
        for forbidden in (
            "secret",
            "key",
            "password",
            "database",
            "traceback",
            "stack",
            "gemini",
        ):
            self.assertNotIn(forbidden, body, forbidden)


class TestAPIIsolationAndAuthHygiene(TestCase):
    def setUp(self):
        self.client = Client()
        self.alice = User.objects.create_user("alice", password="pw12345!")
        self.bob = User.objects.create_user("bob", password="pw12345!")
        # Records owned by each user
        self.alice_exam = ExamPaper.objects.create(
            user=self.alice, title="Alice secret exam", year=2024,
            file=upload_file("alice.txt"),
        )
        self.bob_exam = ExamPaper.objects.create(
            user=self.bob, title="Bob secret exam", year=2024,
            file=upload_file("bob.txt"),
        )

    def test_dashboard_api_requires_login(self):
        response = self.client.get(reverse("dashboard_data_api"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_api_returns_only_own_records(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("dashboard_data_api"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_exams"], 1)
        self.assertEqual(data["total_predictions"], 0)

    def test_user_cannot_read_other_users_exam_via_detail(self):
        self.client.force_login(self.alice)
        response = self.client.get(
            reverse("predictor:exam_detail", args=[self.bob_exam.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Bob secret exam", status_code=404)

    def test_validate_token_returns_only_caller_identity(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("api_validate_token"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user"]["username"], "alice")
        self.assertNotIn("bob", response.content.decode("utf-8"))

    def test_responses_include_a_request_id(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response["X-Request-ID"], r"^[a-f0-9]{32}$")

    def test_registration_never_logs_the_password(self):
        payload = {
            "username": "carol",
            "email": "carol@example.com",
            "password": "S3cretPass!should-not-log",
        }
        with self.assertLogs("predictor.views", level="INFO") as captured:
            response = self.client.post(
                reverse("api_register"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        joined = "\n".join(captured.output)
        self.assertNotIn("S3cretPass", joined)
        self.assertNotIn("Request body", joined)

    def test_registration_500_response_hides_exception_details(self):
        payload = {
            "username": "dave",
            "email": "dave@example.com",
            "password": "pw12345!",
        }
        with patch(
            "predictor.views.User.objects.create_user",
            side_effect=RuntimeError("boom-internal-detail"),
        ):
            response = self.client.post(
                reverse("api_register"),
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("boom-internal-detail", response.content.decode("utf-8"))
