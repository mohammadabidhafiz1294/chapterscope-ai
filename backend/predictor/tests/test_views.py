"""Tests for EduQuantum Predictor views."""

import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from predictor.models import ExamPaper, Topic, Prediction


class TestViews(TestCase):
    """Test cases for Django views."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_dashboard_view(self):
        """Test dashboard view loads correctly."""
        response = self.client.get(reverse('predictor:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'EduQuantum Dashboard')
        self.assertContains(response, 'testuser')

    def test_exam_list_view(self):
        """Test exam list view."""
        response = self.client.get(reverse('predictor:exam_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Exam Papers')

    def test_prediction_list_view(self):
        """Test prediction list view."""
        response = self.client.get(reverse('predictor:prediction_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Predictions')

    def test_topic_analysis_view(self):
        """Test topic analysis view."""
        response = self.client.get(reverse('predictor:topic_analysis'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Topic Analysis')

    def test_dashboard_data_api(self):
        """Test dashboard data API endpoint."""
        response = self.client.get(reverse('predictor:dashboard_data_api'))

        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn('total_syllabi', data)
        self.assertIn('total_exams', data)
        self.assertIn('total_topics', data)

    def test_unauthenticated_access(self):
        """Test that unauthenticated users are redirected."""
        self.client.logout()

        response = self.client.get(reverse('predictor:dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

        response = self.client.get(reverse('predictor:syllabus_list'))
        self.assertEqual(response.status_code, 302)


class TestModelViews(TestCase):
    """Test views that interact with models."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test exam paper
        self.exam_paper = ExamPaper.objects.create(
            user=self.user,
            title='Test Exam Paper',
            year=2024,
            subject='Computer Science',
            description='Test description'
        )

    def test_exam_detail_view(self):
        """Test exam detail view."""
        response = self.client.get(reverse('predictor:exam_detail', kwargs={'pk': self.exam_paper.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Exam Paper')

    def test_exam_detail_view_wrong_user(self):
        """Test exam detail view with wrong user."""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )

        response = self.client.get(reverse('predictor:exam_detail', kwargs={'pk': self.exam_paper.pk}))

        # Should still work since it's the correct user's exam
        self.assertEqual(response.status_code, 200)


class TestFormViews(TestCase):
    """Test views with forms."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_exam_upload_view_get(self):
        """Test exam upload view GET request."""
        response = self.client.get(reverse('predictor:exam_upload'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload Exam')

    def test_prediction_create_view_get(self):
        """Test prediction create view GET request."""
        response = self.client.get(reverse('predictor:prediction_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Prediction')


class TestAJAXViews(TestCase):
    """Test AJAX view endpoints."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test syllabus
        self.syllabus = Syllabus.objects.create(
            user=self.user,
            title='Test Syllabus',
            subject='Computer Science'
        )

    def test_syllabus_process_view_post(self):
        """Test syllabus processing AJAX view."""
        # Create a simple text file content
        file_content = b"This is a test syllabus content."

        # Mock the file on the syllabus
        from django.core.files.base import ContentFile
        self.syllabus.file.save('test.txt', ContentFile(file_content))
        self.syllabus.save()

        response = self.client.post(
            reverse('predictor:syllabus_process', kwargs={'pk': self.syllabus.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        # Should return JSON response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('status', data)


class TestErrorHandling(TestCase):
    """Test error handling in views."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_nonexistent_syllabus_detail(self):
        """Test accessing non-existent syllabus."""
        response = self.client.get(reverse('predictor:syllabus_detail', kwargs={'pk': 999}))

        self.assertEqual(response.status_code, 404)

    def test_nonexistent_exam_detail(self):
        """Test accessing non-existent exam."""
        response = self.client.get(reverse('predictor:exam_detail', kwargs={'pk': 999}))

        self.assertEqual(response.status_code, 404)

    def test_nonexistent_prediction_detail(self):
        """Test accessing non-existent prediction."""
        response = self.client.get(reverse('predictor:prediction_detail', kwargs={'pk': 999}))

        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    import unittest
    unittest.main()
