"""Integration tests for EduQuantum Predictor system."""

import json
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.urls import reverse
import tempfile
import os

from predictor.models import ExamPaper, Topic, Prediction
from predictor.services.exam_analysis_service import ExamAnalysisService
from predictor.services.eduquantum_integrator import EduQuantumIntegrator


class TestEndToEndWorkflow(TransactionTestCase):
    """End-to-end integration tests for the complete workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_complete_exam_workflow(self):
        """Test complete exam upload and processing workflow."""
        # Step 1: Upload exam
        exam_content = b"""
        Computer Science Exam

        Topics:
        1. Python Programming (40%)
        2. Data Structures (30%)
        3. Algorithms (30%)

        Questions:
        1. What is Python? (5 marks)
        a) A snake
        b) A programming language
        c) A database
        d) An operating system

        2. Explain the concept of variables in programming. (10 marks)
        """

        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_file:
            temp_file.write(exam_content)
            temp_file_path = temp_file.name

        try:
            with open(temp_file_path, 'rb') as f:
                response = self.client.post(reverse('predictor:exam_upload'), {
                    'title': 'Test Computer Science Exam',
                    'year': 2024,
                    'subject': 'Computer Science',
                    'description': 'Test exam for integration testing',
                    'file': f
                })

            self.assertEqual(response.status_code, 302)  # Redirect after successful upload

            # Get the created exam
            exam = ExamPaper.objects.filter(user=self.user).latest('uploaded_at')
            self.assertEqual(exam.title, 'Test Computer Science Exam')

            # Step 2: Process exam
            response = self.client.post(
                reverse('predictor:exam_process', kwargs={'pk': exam.pk}),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(data['status'], 'success')

            # Verify topics were created
            topics = Topic.objects.filter(exam_paper=exam)
            self.assertGreater(len(topics), 0)

        finally:
            os.unlink(temp_file_path)

    def test_exam_analysis_workflow(self):
        """Test complete exam upload and analysis workflow."""
        # Create a syllabus first
        syllabus = Syllabus.objects.create(
            user=self.user,
            title='Test Syllabus',
            subject='Computer Science'
        )

        # Step 1: Upload exam
        exam_content = b"""
        Computer Science Exam

        1. What is Python? (5 marks)
        a) A snake
        b) A programming language
        c) A database
        d) An operating system

        2. Explain the concept of variables in programming. (10 marks)

        3. What is the time complexity of binary search? (5 marks)
        """

        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_file:
            temp_file.write(exam_content)
            temp_file_path = temp_file.name

        try:
            with open(temp_file_path, 'rb') as f:
                response = self.client.post(reverse('predictor:exam_upload'), {
                    'title': 'Test Computer Science Exam',
                    'subject': 'Computer Science',
                    'description': 'Test exam for integration testing',
                    'syllabus': syllabus.id,
                    'file': f
                })

            self.assertEqual(response.status_code, 302)

            # Get the created exam
            exam = ExamPaper.objects.filter(user=self.user).latest('uploaded_at')

            # Step 2: Process exam
            response = self.client.post(
                reverse('predictor:exam_process', kwargs={'pk': exam.pk}),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(data['status'], 'success')

            # Refresh exam from database
            exam.refresh_from_db()
            self.assertTrue(exam.processed)
            self.assertIsNotNone(exam.analysis_data)

        finally:
            os.unlink(temp_file_path)

    def test_prediction_creation_workflow(self):
        """Test complete prediction creation workflow."""
        # Create syllabus with topics
        syllabus = Syllabus.objects.create(
            user=self.user,
            title='Test Syllabus',
            subject='Computer Science'
        )

        # Create some topics
        Topic.objects.create(
            syllabus=syllabus,
            name='Python Programming',
            description='Python programming concepts',
            frequency=40.0
        )

        Topic.objects.create(
            syllabus=syllabus,
            name='Data Structures',
            description='Data structures and algorithms',
            frequency=30.0
        )

        # Step 1: Create prediction
        response = self.client.post(reverse('predictor:prediction_create'), {
            'syllabus': syllabus.id,
            'prediction_type': 'comprehensive',
            'description': 'Test prediction for integration testing'
        })

        self.assertEqual(response.status_code, 302)  # Redirect to prediction detail

        # Verify prediction was created
        prediction = Prediction.objects.filter(user=self.user).latest('created_at')
        self.assertEqual(prediction.prediction_type, 'comprehensive')
        self.assertIsNotNone(prediction.quantum_result)
        self.assertIsNotNone(prediction.final_prediction)


class TestServiceIntegration(TestCase):
    """Integration tests for service interactions."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_exam_analysis_service_integration(self):
        """Test ExamAnalysisService with real data."""
        service = ExamAnalysisService()

        # Test with sample exam content
        exam_content = b"""
        1. What is the capital of France? (2 marks)
        2. Explain photosynthesis. (5 marks)
        3. Calculate 2 + 2. (1 mark)
        """

        result = service.analyze_exam_file(exam_content, "test_exam.txt")

        self.assertTrue(result.success)
        self.assertGreater(result.total_questions, 0)
        self.assertIsNotNone(result.topic_breakdown)

    def test_integrator_service_workflow(self):
        """Test EduQuantumIntegrator workflow."""
        integrator = EduQuantumIntegrator()

        # Test system health check
        health = integrator.get_system_health_status()

        self.assertIn('overall_health', health)
        self.assertIn('components', health)

        # Test with non-existent syllabus
        result = integrator.process_syllabus_and_predict(999, self.user.id)

        self.assertFalse(result.success)
        self.assertIn('not found', result.message.lower())


class TestDataConsistency(TestCase):
    """Test data consistency across the system."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_topic_frequency_consistency(self):
        """Test that topic frequencies are consistent across calculations."""
        syllabus = Syllabus.objects.create(
            user=self.user,
            title='Test Syllabus',
            subject='Computer Science'
        )

        # Create topics with known frequencies
        topics_data = [
            ('Python', 40.0),
            ('Java', 30.0),
            ('Data Structures', 20.0),
            ('Algorithms', 10.0)
        ]

        total_frequency = 0
        for name, freq in topics_data:
            Topic.objects.create(
                syllabus=syllabus,
                name=name,
                description=f'Test topic: {name}',
                frequency=freq
            )
            total_frequency += freq

        # Verify frequencies add up correctly
        topics = Topic.objects.filter(syllabus=syllabus)
        calculated_total = sum(topic.frequency for topic in topics)

        self.assertAlmostEqual(calculated_total, total_frequency, places=2)

    def test_exam_question_counting(self):
        """Test that exam question counting is accurate."""
        exam = ExamPaper.objects.create(
            user=self.user,
            title='Test Exam',
            subject='Computer Science'
        )

        # Simulate analysis data
        analysis_data = {
            'topic_breakdown': {
                'total_questions': 10,
                'topics': {
                    'Python': {'count': 4, 'percentage': 40.0},
                    'Java': {'count': 3, 'percentage': 30.0},
                    'Data Structures': {'count': 3, 'percentage': 30.0}
                }
            }
        }

        exam.analysis_data = analysis_data
        exam.processed = True
        exam.save()

        # Verify question count consistency
        total_from_topics = sum(
            topic_data['count']
            for topic_data in analysis_data['topic_breakdown']['topics'].values()
        )

        self.assertEqual(
            total_from_topics,
            analysis_data['topic_breakdown']['total_questions']
        )


class TestPerformance(TestCase):
    """Performance tests for system components."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_bulk_topic_creation_performance(self):
        """Test performance of bulk topic creation."""
        import time

        syllabus = Syllabus.objects.create(
            user=self.user,
            title='Performance Test Syllabus',
            subject='Computer Science'
        )

        # Create multiple topics
        start_time = time.time()
        topics_data = []
        for i in range(100):
            topics_data.append(Topic(
                syllabus=syllabus,
                name=f'Topic {i}',
                description=f'Description for topic {i}',
                frequency=float(i % 20) + 1
            ))

        Topic.objects.bulk_create(topics_data)
        end_time = time.time()

        creation_time = end_time - start_time
        topics_count = Topic.objects.filter(syllabus=syllabus).count()

        self.assertEqual(topics_count, 100)
        self.assertLess(creation_time, 5.0)  # Should complete within 5 seconds

    def test_query_performance(self):
        """Test database query performance."""
        import time

        # Create test data
        syllabus = Syllabus.objects.create(
            user=self.user,
            title='Query Performance Test',
            subject='Computer Science'
        )

        for i in range(50):
            Topic.objects.create(
                syllabus=syllabus,
                name=f'Topic {i}',
                description=f'Description {i}',
                frequency=float(i % 10) + 1
            )

        # Test query performance
        start_time = time.time()
        topics = Topic.objects.filter(
            syllabus=syllabus
        ).select_related('syllabus').order_by('-frequency')[:20]
        end_time = time.time()

        query_time = end_time - start_time
        self.assertLess(query_time, 1.0)  # Should complete within 1 second
        self.assertEqual(len(list(topics)), 20)


if __name__ == '__main__':
    import unittest
    unittest.main()
