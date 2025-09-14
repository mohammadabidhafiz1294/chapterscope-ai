from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
import json

class Syllabus(models.Model):
    """Model for storing syllabi and their analysis"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='syllabi')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(
        upload_to='syllabi/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt'])]
    )
    subject = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    topic_count = models.PositiveIntegerField(default=0)
    extracted_text = models.TextField(blank=True)
    topics_covered = models.JSONField(default=list, blank=True)  # Topics found in syllabus

    class Meta:
        ordering = ['-uploaded_at']
        unique_together = ['user', 'title', 'subject']

    def __str__(self):
        return f"{self.title} ({self.subject}) - {self.user.username}"

class ExamPaper(models.Model):
    """Model for storing exam papers and their analysis"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_papers')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(
        upload_to='exams/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt'])]
    )
    year = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    topic_count = models.PositiveIntegerField(default=0)
    question_count = models.PositiveIntegerField(default=0)
    extracted_text = models.TextField(blank=True)
    questions_data = models.JSONField(default=list, blank=True)  # Store segmented questions
    topics_covered = models.JSONField(default=list, blank=True)  # Topics found in exam

    class Meta:
        ordering = ['-uploaded_at']
        unique_together = ['user', 'title', 'year']

    def __str__(self):
        return f"{self.title} ({self.year}) - {self.user.username}"

class Topic(models.Model):
    """Model for storing topics extracted from syllabi and exam papers"""
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name='topics', null=True, blank=True)
    exam_paper = models.ForeignKey(ExamPaper, on_delete=models.CASCADE, related_name='topics', null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    frequency = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)  # Additional topic information

    class Meta:
        ordering = ['-frequency', '-last_seen']
        # Allow topics to be associated with either syllabus or exam_paper, but not both
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(syllabus__isnull=False, exam_paper__isnull=True) |
                    models.Q(syllabus__isnull=True, exam_paper__isnull=False)
                ),
                name='topic_source_constraint'
            )
        ]

    def __str__(self):
        source = self.syllabus.title if self.syllabus else self.exam_paper.title
        return f"{self.name} ({self.frequency}) - {source}"

class Prediction(models.Model):
    """Model for storing quantum and classical predictions"""
    PREDICTION_TYPES = [
        ('QUANTUM', 'Quantum VQE Prediction'),
        ('CLASSICAL', 'Classical ML Prediction'),
        ('HYBRID', 'Hybrid Prediction'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='predictions')
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name='predictions', null=True, blank=True)
    exam_paper = models.ForeignKey(ExamPaper, on_delete=models.CASCADE, related_name='predictions', null=True, blank=True)
    prediction_type = models.CharField(max_length=20, choices=PREDICTION_TYPES, default='HYBRID')
    created_at = models.DateTimeField(auto_now_add=True)
    accuracy_score = models.FloatField(null=True, blank=True)
    quantum_result = models.JSONField(default=dict, blank=True)  # VQE results
    classical_result = models.JSONField(default=dict, blank=True)  # Classical ML results
    final_prediction = models.JSONField(default=dict, blank=True)  # Combined/selected result
    description = models.TextField(blank=True)
    processing_time = models.FloatField(null=True, blank=True)  # Time taken for prediction

    class Meta:
        ordering = ['-created_at']
        # Allow predictions to be associated with either syllabus or exam_paper, but not both
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(syllabus__isnull=False, exam_paper__isnull=True) |
                    models.Q(syllabus__isnull=True, exam_paper__isnull=False)
                ),
                name='prediction_source_constraint'
            )
        ]

    def __str__(self):
        source = self.syllabus.title if self.syllabus else self.exam_paper.title
        return f"{self.prediction_type} - {self.user.username} ({self.created_at.date()}) - {source}"
