from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from pgvector.django import VectorField
import json

# Upper bound for exam paper years. Kept as a constant so the generated
# migration does not change every year (a dynamic datetime.now() bound caused
# a new AlterField migration on each calendar year).
MAX_EXAM_YEAR = 2100

class Syllabus(models.Model):
    """Model for storing syllabi and their analysis"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='syllabi')
    # Phase 2: optional parent course notebook. Nullable so pre-notebook
    # (legacy) records stay valid; SET_NULL keeps the file if the notebook
    # itself is deleted. Assignment is explicit (attach endpoint / form), never
    # inferred.
    notebook = models.ForeignKey(
        'CourseNotebook', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='syllabi'
    )
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
    analysis_data = models.JSONField(default=dict, blank=True)  # Structured analysis results
    # Phase 3: source-traceable extraction state. `processed` is the legacy
    # flag kept for the pre-Phase-3 UI; `processing_status` is the new
    # source-of-truth state machine (pending/processing/processed/
    # needs_review/ocr_required/failed). Both stay consistent on success only.
    content_hash = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text="SHA-256 of the uploaded file, used for idempotent processing."
    )
    processing_status = models.CharField(
        max_length=20, default='PENDING',
        choices=[
            ('PENDING', 'Pending'), ('PROCESSING', 'Processing'),
            ('PROCESSED', 'Processed'), ('NEEDS_REVIEW', 'Needs review'),
            ('OCR_REQUIRED', 'OCR required'), ('FAILED', 'Failed'),
        ]
    )
    processing_error = models.TextField(blank=True, default='')
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        unique_together = ['user', 'title', 'subject']

    def __str__(self):
        return f"{self.title} ({self.subject}) - {self.user.username}"

class ExamPaper(models.Model):
    """Model for storing exam papers and their analysis"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_papers')
    # Phase 2: optional parent course notebook. Nullable / SET_NULL for the
    # same compatibility reasons as Syllabus.notebook.
    notebook = models.ForeignKey(
        'CourseNotebook', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='exam_papers'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(
        upload_to='exams/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt'])]
    )
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(1900), MaxValueValidator(MAX_EXAM_YEAR)],
        help_text="Year of the exam paper"
    )
    # Phase 5: paper-level total used to normalise marks before aggregation,
    # so a 100-mark paper and a 200-mark paper are compared fairly. Blank means
    # "unknown": analytics derives it from the sum of parsed question marks and
    # labels the figure as derived (see services/analytics/metrics.py).
    total_marks = models.PositiveIntegerField(
        null=True, blank=True,
        help_text=(
            "Total marks of the paper. When blank, analytics derives it from "
            "the sum of parsed question marks and flags it as derived."
        ),
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    topic_count = models.PositiveIntegerField(default=0)
    question_count = models.PositiveIntegerField(default=0)
    extracted_text = models.TextField(blank=True)
    questions_data = models.JSONField(default=list, blank=True)  # Store segmented questions
    topics_covered = models.JSONField(default=list, blank=True)  # Topics found in exam
    analysis_data = models.JSONField(default=dict, blank=True)  # Structured analysis results
    # Phase 3: source-traceable extraction state (same semantics as Syllabus).
    content_hash = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text="SHA-256 of the uploaded file, used for idempotent processing."
    )
    processing_status = models.CharField(
        max_length=20, default='PENDING',
        choices=[
            ('PENDING', 'Pending'), ('PROCESSING', 'Processing'),
            ('PROCESSED', 'Processed'), ('NEEDS_REVIEW', 'Needs review'),
            ('OCR_REQUIRED', 'OCR required'), ('FAILED', 'Failed'),
        ]
    )
    processing_error = models.TextField(blank=True, default='')
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_finished_at = models.DateTimeField(null=True, blank=True)

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


# ---------------------------------------------------------------------------
# Phase 2: Course notebooks
# A notebook is the parent scope for one course: its syllabus, exam papers,
# normalized questions, canonical topics, chat history and generated study
# material. Everything below is additive and does not alter the pre-existing
# Syllabus / ExamPaper / Topic / Prediction behaviour.
# ---------------------------------------------------------------------------

class CourseNotebook(models.Model):
    """A user-owned notebook representing a single course.

    Parent scope for syllabus/exam papers (via optional FKs), questions,
    canonical topics, chat sessions and generated material.
    """
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_ARCHIVED = 'ARCHIVED'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notebooks'
    )
    title = models.CharField(max_length=200)
    course_code = models.CharField(max_length=50, blank=True, default='')
    institution = models.CharField(max_length=200, blank=True, default='')
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'title', 'course_code'],
                name='notebook_owner_title_code_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['owner', 'status'], name='notebook_owner_status_idx'),
        ]

    @property
    def is_archived(self):
        return self.status == self.STATUS_ARCHIVED

    def __str__(self):
        return f"{self.title} ({self.course_code or 'no code'}) - {self.owner.username}"


class Question(models.Model):
    """One normalized record per individual question / sub-question.

    Linked to the source ExamPaper (mandatory) and, explicitly, to a notebook.
    The notebook is denormalized from the exam paper when blank so that
    notebook-scoped queries stay cheap; a mismatch is rejected on clean().
    A question number may repeat across different papers (years) but is unique
    within one paper.
    """
    STATUS_PENDING = 'PENDING'
    STATUS_EXTRACTED = 'EXTRACTED'
    STATUS_MANUAL = 'MANUAL'
    STATUS_FAILED = 'FAILED'
    STATUS_NEEDS_REVIEW = 'NEEDS_REVIEW'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_EXTRACTED, 'Extracted'),
        (STATUS_MANUAL, 'Manual'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_NEEDS_REVIEW, 'Needs review'),
    ]
    # Phase 3: provenance for automated extraction (rule-based, LLM-assisted
    # or OCR). Blank for legacy or manually created questions.
    METHOD_RULE = 'RULE'
    METHOD_LLM = 'LLM'
    METHOD_OCR = 'OCR'
    METHOD_MANUAL = 'MANUAL'
    METHOD_CHOICES = [
        (METHOD_RULE, 'Rule-based'),
        (METHOD_LLM, 'LLM-assisted'),
        (METHOD_OCR, 'OCR'),
        (METHOD_MANUAL, 'Manual'),
    ]
    TYPE_CHOICES = [
        ('multiple_choice', 'Multiple choice'),
        ('short_answer', 'Short answer'),
        ('essay', 'Essay'),
        ('numerical', 'Numerical'),
        ('true_false', 'True/False'),
        ('other', 'Other'),
        ('', 'Unspecified'),
    ]
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
        ('', 'Unspecified'),
    ]

    notebook = models.ForeignKey(
        CourseNotebook, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='questions'
    )
    exam_paper = models.ForeignKey(
        ExamPaper, on_delete=models.CASCADE, related_name='questions'
    )
    question_number = models.CharField(
        max_length=20,
        help_text="Question identifier as printed, e.g. '2' or '2a'."
    )
    # Blank (not null) so the unique constraint treats repeated '' uniformly.
    parent_number = models.CharField(
        max_length=20, blank=True, default='',
        help_text="Parent question number for sub-questions, e.g. '2' for '2a'."
    )
    raw_text = models.TextField()
    normalized_text = models.TextField(blank=True)
    page_reference = models.CharField(max_length=50, blank=True)
    marks = models.PositiveIntegerField(null=True, blank=True)
    # Year denormalized from the source paper; filled on save when blank.
    year = models.PositiveIntegerField(null=True, blank=True)
    extraction_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    extraction_confidence = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    question_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, blank=True, default=''
    )
    # Phase 5: provenance for the type label itself. Extraction fills it as
    # RULE; the classifier proposes LLM values that only stick after review.
    type_source = models.CharField(
        max_length=10,
        choices=[
            ('', 'Unset'), ('RULE', 'Rule-based'), ('LLM', 'LLM'),
            ('MANUAL', 'Manual'),
        ],
        blank=True,
        default='',
    )
    type_confidence = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    # Model + prompt version that produced the LLM type label, for audit.
    type_classifier_version = models.CharField(max_length=100, blank=True, default='')
    # '' = nothing pending (label came from extraction or a human),
    # NEEDS_REVIEW = an LLM proposal is filled in but not yet accepted,
    # CONFIRMED = a human accepted the proposal.
    type_review_status = models.CharField(
        max_length=16,
        choices=[
            ('', 'None'), ('NEEDS_REVIEW', 'Needs review'),
            ('CONFIRMED', 'Confirmed'),
        ],
        blank=True,
        default='',
        db_index=True,
    )
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, blank=True, default=''
    )
    # Phase 3: source traceability for RAG citation. Point at the extraction
    # run and exact chunk/page that produced this question. SET_NULL so
    # cleaning up runs never cascades into question loss.
    source_run = models.ForeignKey(
        'ExtractionRun', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='questions'
    )
    source_chunk = models.ForeignKey(
        'ExtractionChunk', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='questions'
    )
    # Explicit subpart -> parent question link (complements parent_number).
    parent_question = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='subparts'
    )
    extraction_method = models.CharField(
        max_length=10, choices=METHOD_CHOICES, blank=True, default=''
    )
    # Multiple-choice options preserved verbatim (never silently dropped).
    options = models.JSONField(default=list, blank=True)
    # Per-question extraction warnings (formula detected, OCR low
    # confidence, table flattened, figure reference, ...).
    extraction_warnings = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['parent_number', 'question_number']
        constraints = [
            models.UniqueConstraint(
                fields=['exam_paper', 'parent_number', 'question_number'],
                name='question_paper_number_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['notebook', 'year'], name='question_notebook_year_idx'),
            models.Index(
                fields=['exam_paper', 'question_number'],
                name='question_paper_number_idx',
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.exam_paper_id and self.notebook_id:
            paper_notebook_id = (
                ExamPaper.objects.filter(pk=self.exam_paper_id)
                .values_list('notebook_id', flat=True).first()
            )
            if paper_notebook_id is not None and paper_notebook_id != self.notebook_id:
                raise ValidationError(
                    {'notebook': 'Question notebook must match the exam paper notebook.'}
                )
        # Phase 3: a subpart's parent must belong to the same exam paper and
        # must not be itself.
        if self.parent_question_id:
            if self.parent_question_id == self.pk:
                raise ValidationError(
                    {'parent_question': 'A question cannot be its own parent.'}
                )
            parent_paper_id = (
                ExamPaper.objects.filter(
                    questions__pk=self.parent_question_id
                ).values_list('pk', flat=True).first()
            )
            if parent_paper_id is not None and self.exam_paper_id:
                if parent_paper_id != self.exam_paper_id:
                    raise ValidationError(
                        {'parent_question': 'Parent question must belong to the same exam paper.'}
                    )

    def save(self, *args, **kwargs):
        # Denormalize notebook + year from the source paper when not set, so
        # callers do not have to repeat data the paper already owns.
        if self.exam_paper_id:
            paper = self.exam_paper  # uses FK cache when available
            if self.notebook_id is None:
                self.notebook = paper.notebook
            if self.year is None:
                self.year = paper.year
        super().save(*args, **kwargs)

    def __str__(self):
        label = f"{self.parent_number}{self.question_number}" if self.parent_number else self.question_number
        return f"Q{label} ({self.exam_paper_id})"


class NotebookTopic(models.Model):
    """Canonical topic scoped to one notebook.

    Distinct from the legacy per-document Topic model, which stays untouched.
    This is the stable identity questions are classified against.
    """
    notebook = models.ForeignKey(
        CourseNotebook, on_delete=models.CASCADE, related_name='topics'
    )
    name = models.CharField(max_length=200)
    # Normalized (trimmed / whitespace-collapsed / lowercased) copy used for
    # uniqueness; computed in save().
    normalized_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # Phase 5: alternative labels accepted for this topic (display strings).
    # Normalised with services/analytics.labels.normalize_label(); element
    # uniqueness is enforced at write time (JSON lists cannot be indexed
    # per element), and an alias may never collide with another topic's name
    # or alias in the same notebook.
    aliases = models.JSONField(default=list, blank=True)
    # CONFIRMED = curated (created manually or reviewed); NEEDS_REVIEW =
    # proposed by the classifier and not yet accepted by a human. The
    # analytics layer counts both but always reports how many are pending.
    review_status = models.CharField(
        max_length=16,
        choices=[('CONFIRMED', 'Confirmed'), ('NEEDS_REVIEW', 'Needs review')],
        default='CONFIRMED',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['notebook', 'normalized_name'],
                name='notebook_topic_uniq',
            ),
        ]

    def _normalize(self):
        return ' '.join(self.name.split()).lower()

    def save(self, *args, **kwargs):
        self.normalized_name = self._normalize()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.notebook_id})"


class QuestionTopic(models.Model):
    """Mapping of a question to a canonical notebook topic.

    Supports primary/secondary roles and an optional classification
    confidence. At most one PRIMARY topic per question (partial unique
    constraint).
    """
    ROLE_PRIMARY = 'PRIMARY'
    ROLE_SECONDARY = 'SECONDARY'
    ROLE_CHOICES = [
        (ROLE_PRIMARY, 'Primary'),
        (ROLE_SECONDARY, 'Secondary'),
    ]

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name='topic_links'
    )
    topic = models.ForeignKey(
        NotebookTopic, on_delete=models.CASCADE, related_name='question_links'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_PRIMARY)
    confidence = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    # Phase 5: how this link was produced and whether it has been reviewed.
    # Manual/API links default to CONFIRMED so existing data keeps counting;
    # classifier output is stored as NEEDS_REVIEW and excluded from the
    # "confirmed" metric slice until a human accepts it.
    classification_source = models.CharField(
        max_length=10,
        choices=[
            ('MANUAL', 'Manual'), ('RULE', 'Rule-based'),
            ('ALIAS', 'Alias match'), ('LLM', 'LLM'),
        ],
        default='MANUAL',
    )
    # Model + prompt version that produced an LLM link (empty otherwise).
    classifier_version = models.CharField(max_length=100, blank=True, default='')
    review_status = models.CharField(
        max_length=16,
        choices=[
            ('CONFIRMED', 'Confirmed'), ('NEEDS_REVIEW', 'Needs review'),
            ('REJECTED', 'Rejected'),
        ],
        default='CONFIRMED',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['role', 'topic__name']
        constraints = [
            models.UniqueConstraint(
                fields=['question', 'topic'],
                name='question_topic_uniq',
            ),
            models.UniqueConstraint(
                fields=['question'],
                condition=models.Q(role='PRIMARY'),
                name='question_one_primary_topic',
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if (
            self.question_id
            and self.topic_id
            and self.topic.notebook_id
            and self.question.notebook_id
            and self.topic.notebook_id != self.question.notebook_id
        ):
            raise ValidationError(
                {'topic': 'Topic must belong to the same notebook as the question.'}
            )

    def __str__(self):
        return f"{self.question_id}:{self.topic_id} ({self.role})"


class ChatSession(models.Model):
    """A chat session scoped to one notebook and one user.

    History only; no LLM wiring in this phase.
    """
    notebook = models.ForeignKey(
        CourseNotebook, on_delete=models.CASCADE, related_name='chat_sessions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions'
    )
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(
                fields=['notebook', 'user'], name='chatsession_notebook_user_idx'
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if (
            self.notebook_id
            and self.user_id
            and self.notebook.owner_id != self.user_id
        ):
            raise ValidationError(
                {'user': 'Chat session user must be the notebook owner.'}
            )

    def __str__(self):
        return f"{self.title or 'Session'} ({self.notebook_id})"


class ChatMessage(models.Model):
    """A single chat message.

    Stores only the role, the visible content and safe metadata (e.g. source
    references). No API secrets or hidden reasoning.
    """
    ROLE_USER = 'USER'
    ROLE_ASSISTANT = 'ASSISTANT'
    ROLE_SYSTEM = 'SYSTEM'
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ASSISTANT, 'Assistant'),
        (ROLE_SYSTEM, 'System'),
    ]

    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    # Safe, non-secret metadata (e.g. {"sources": [...]}). Never store keys.
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'created_at'], name='chatmessage_session_idx'),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


class GenerationRequest(models.Model):
    """One request to generate a small practice paper for one topic.

    Phase 7. Groups the generated questions so the same generated paper can
    be reopened. Synchronous: the POST creates the request, generates, then
    marks it COMPLETED / PARTIAL / FAILED. `creator` + notebook scoping give
    the same ownership guarantees as every other notebook route.
    """
    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_PARTIAL = 'PARTIAL'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_PARTIAL, 'Partial'),
        (STATUS_FAILED, 'Failed'),
    ]

    notebook = models.ForeignKey(
        CourseNotebook, on_delete=models.CASCADE,
        related_name='generation_requests'
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='generation_requests'
    )
    # Primary topic the request targets; SET_NULL so a deleted topic never
    # cascades into losing an already-generated paper.
    topic = models.ForeignKey(
        NotebookTopic, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generation_requests'
    )
    # Primary + secondary topic ids as requested (JSON; validated at write).
    topic_ids = models.JSONField(default=list, blank=True)
    # Requested shape (echoed so the paper is self-describing when reopened).
    question_count = models.PositiveIntegerField(default=5)
    question_types = models.JSONField(default=list, blank=True)
    difficulty = models.CharField(
        max_length=10, choices=Question.DIFFICULTY_CHOICES, blank=True, default=''
    )
    marks = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=20, blank=True, default='en')
    include_answers = models.BooleanField(default=True)
    year_from = models.PositiveIntegerField(null=True, blank=True)
    year_to = models.PositiveIntegerField(null=True, blank=True)
    # Outcome.
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    questions_created = models.PositiveIntegerField(default=0)
    questions_validated = models.PositiveIntegerField(default=0)
    questions_needs_review = models.PositiveIntegerField(default=0)
    # Provenance + machine-readable notices (never provider payloads).
    generation_model = models.CharField(max_length=100, blank=True, default='')
    generation_version = models.CharField(max_length=100, blank=True, default='')
    request_meta = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default='')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['notebook', 'creator'],
                name='genreq_notebook_creator_idx',
            ),
            models.Index(
                fields=['notebook', 'status'],
                name='genreq_notebook_status_idx',
            ),
        ]

    def __str__(self):
        return f"GenReq {self.pk} ({self.status}) - {self.notebook_id}"


class GeneratedQuestion(models.Model):
    """A generated practice question, solution and review state.

    Phase 7 fills the columns that were deferred: the owning request, the
    language, the marking rubric, the generating model/version and the
    automatic validation outcome. Every new column keeps a default that
    preserves the meaning of pre-Phase-7 rows (empty/None = unknown).
    """
    REVIEW_DRAFT = 'DRAFT'
    REVIEW_PENDING = 'PENDING_REVIEW'
    REVIEW_APPROVED = 'APPROVED'
    REVIEW_REJECTED = 'REJECTED'
    REVIEW_CHOICES = [
        (REVIEW_DRAFT, 'Draft'),
        (REVIEW_PENDING, 'Pending review'),
        (REVIEW_APPROVED, 'Approved'),
        (REVIEW_REJECTED, 'Rejected'),
    ]
    # Automatic validation outcome (independent of the human review_status).
    # VALIDATED = passed every automatic check; it is NOT a human approval
    # and it is NOT a claim that the answer is correct.
    VALIDATION_VALIDATED = 'VALIDATED'
    VALIDATION_NEEDS_REVIEW = 'NEEDS_REVIEW'
    VALIDATION_CHOICES = [
        (VALIDATION_VALIDATED, 'Validated'),
        (VALIDATION_NEEDS_REVIEW, 'Needs review'),
    ]

    notebook = models.ForeignKey(
        CourseNotebook, on_delete=models.CASCADE, related_name='generated_questions'
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='generated_questions'
    )
    source_question = models.ForeignKey(
        Question, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generated_questions'
    )
    topic = models.ForeignKey(
        NotebookTopic, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generated_questions'
    )
    # Phase 7: owning generation request (NULL for any pre-Phase-7 row).
    request = models.ForeignKey(
        GenerationRequest, on_delete=models.CASCADE, null=True, blank=True,
        related_name='questions'
    )
    question_text = models.TextField()
    answer_text = models.TextField(blank=True)
    solution_text = models.TextField(blank=True)
    question_type = models.CharField(
        max_length=20, choices=Question.TYPE_CHOICES, blank=True, default=''
    )
    marks = models.PositiveIntegerField(null=True, blank=True)
    difficulty = models.CharField(
        max_length=10, choices=Question.DIFFICULTY_CHOICES, blank=True, default=''
    )
    review_status = models.CharField(
        max_length=20, choices=REVIEW_CHOICES, default=REVIEW_DRAFT
    )
    # Source references (paper/question/topic ids, page refs) for grounding.
    source_refs = models.JSONField(default=list, blank=True)
    # Phase 7 additions.
    language = models.CharField(max_length=20, blank=True, default='en')
    # Rubric as [{"criterion": "...", "marks": N}, ...]; checked against marks.
    marking_rubric = models.JSONField(default=list, blank=True)
    generation_model = models.CharField(max_length=100, blank=True, default='')
    generation_version = models.CharField(max_length=100, blank=True, default='')
    validation_status = models.CharField(
        max_length=16, choices=VALIDATION_CHOICES, default=VALIDATION_NEEDS_REVIEW
    )
    # Machine-readable reasons (['duplicate_of_past_paper', ...]; never prose).
    validation_report = models.JSONField(default=list, blank=True)
    answer_confidence = models.FloatField(null=True, blank=True)
    # Primary + secondary NotebookTopic ids this question was generated for.
    topic_ids = models.JSONField(default=list, blank=True)
    # Multiple-choice options (empty for non-MC).
    options = models.JSONField(default=list, blank=True)
    # Numeric problem/check audit trail (never a provider payload).
    numeric_report = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['notebook', 'review_status'],
                name='genq_notebook_status_idx',
            ),
            models.Index(
                fields=['notebook', 'validation_status'],
                name='genq_notebook_validation_idx',
            ),
        ]

    def __str__(self):
        return f"GenQ {self.pk} ({self.review_status}) - {self.notebook_id}"


# ---------------------------------------------------------------------------
# Phase 3: source-traceable extraction.
# An ExtractionRun records one processing attempt of one source document
# version (identified by file hash). ExtractionChunk stores the exact text
# units (pages for PDFs, paragraphs/tables for DOCX, one blob for TXT) with
# their page/chunk boundaries so later RAG answers can cite the precise
# source location.
# ---------------------------------------------------------------------------

class ExtractionRun(models.Model):
    """One processing attempt for one source document version (file hash).

    Statuses: PENDING -> PROCESSING -> PROCESSED / NEEDS_REVIEW /
    OCR_REQUIRED / FAILED. `file_hash` makes repeated processing of the same
    source version idempotent (the service returns the existing successful
    run instead of creating duplicate questions).
    """
    SOURCE_SYLLABUS = 'SYLLABUS'
    SOURCE_EXAM_PAPER = 'EXAM_PAPER'
    SOURCE_CHOICES = [
        (SOURCE_SYLLABUS, 'Syllabus'),
        (SOURCE_EXAM_PAPER, 'Exam paper'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_PROCESSED = 'PROCESSED'
    STATUS_NEEDS_REVIEW = 'NEEDS_REVIEW'
    STATUS_OCR_REQUIRED = 'OCR_REQUIRED'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_NEEDS_REVIEW, 'Needs review'),
        (STATUS_OCR_REQUIRED, 'OCR required'),
        (STATUS_FAILED, 'Failed'),
    ]

    METHOD_PDF_TEXT = 'PDF_TEXT'
    METHOD_DOCX_TEXT = 'DOCX_TEXT'
    METHOD_PLAIN_TEXT = 'PLAIN_TEXT'
    METHOD_OCR = 'OCR'
    METHOD_MIXED = 'MIXED'
    METHOD_NONE = 'NONE'
    METHOD_CHOICES = [
        (METHOD_PDF_TEXT, 'PDF text extraction'),
        (METHOD_DOCX_TEXT, 'DOCX text extraction'),
        (METHOD_PLAIN_TEXT, 'Plain text'),
        (METHOD_OCR, 'OCR'),
        (METHOD_MIXED, 'Mixed (text + OCR)'),
        (METHOD_NONE, 'No extraction'),
    ]

    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    # Exactly one of these is set (CheckConstraint below). CASCADE so deleting
    # a source document removes its orphaned extraction history.
    syllabus = models.ForeignKey(
        Syllabus, on_delete=models.CASCADE, null=True, blank=True,
        related_name='extraction_runs'
    )
    exam_paper = models.ForeignKey(
        ExamPaper, on_delete=models.CASCADE, null=True, blank=True,
        related_name='extraction_runs'
    )
    file_hash = models.CharField(
        max_length=64, db_index=True,
        help_text="SHA-256 of the source file at processing time."
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    extraction_method = models.CharField(
        max_length=20, choices=METHOD_CHOICES, default=METHOD_NONE
    )
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    total_chars = models.PositiveIntegerField(default=0)
    question_count = models.PositiveIntegerField(default=0)
    low_text_pages = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    ocr_required = models.BooleanField(default=False)
    error_code = models.CharField(max_length=40, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(syllabus__isnull=False, exam_paper__isnull=True)
                    | models.Q(syllabus__isnull=True, exam_paper__isnull=False)
                ),
                name='extraction_one_source',
            ),
        ]
        indexes = [
            models.Index(
                fields=['source_type', 'status'],
                name='extraction_type_status_idx',
            ),
            models.Index(
                fields=['exam_paper', 'file_hash'],
                name='extraction_paper_hash_idx',
            ),
            models.Index(
                fields=['syllabus', 'file_hash'],
                name='extraction_syllabus_hash_idx',
            ),
        ]

    @property
    def source_document(self):
        """Return the linked Syllabus or ExamPaper, whichever is set."""
        return self.syllabus if self.syllabus_id else self.exam_paper

    def __str__(self):
        src = self.syllabus_id or self.exam_paper_id
        return f"Run {self.pk} [{self.source_type}:{src}] {self.status}"


class ExtractionChunk(models.Model):
    """One text unit extracted from a source document.

    PDFs produce one PAGE chunk per page; DOCX produces PARAGRAPH / TABLE
    chunks; TXT produces a single TEXT chunk. `char_start`/`char_end` are
    offsets into the reconstructed full document text so questions can be
    mapped back to their exact source location. `page_number` is set only for
    paginated formats (PDF).
    """
    KIND_PAGE = 'PAGE'
    KIND_PARAGRAPH = 'PARAGRAPH'
    KIND_TABLE = 'TABLE'
    KIND_TEXT = 'TEXT'
    KIND_CHOICES = [
        (KIND_PAGE, 'Page'),
        (KIND_PARAGRAPH, 'Paragraph'),
        (KIND_TABLE, 'Table'),
        (KIND_TEXT, 'Text'),
    ]

    extraction = models.ForeignKey(
        ExtractionRun, on_delete=models.CASCADE, related_name='chunks'
    )
    chunk_index = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="1-based page number (PDF only; null for DOCX/TXT)."
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_TEXT)
    text = models.TextField()
    char_start = models.PositiveIntegerField(default=0)
    char_end = models.PositiveIntegerField(default=0)
    method = models.CharField(
        max_length=20, choices=ExtractionRun.METHOD_CHOICES,
        default=ExtractionRun.METHOD_NONE
    )
    confidence = models.FloatField(
        null=True, blank=True,
        help_text="OCR/extraction confidence (null for deterministic text)."
    )
    is_low_text = models.BooleanField(default=False)
    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['chunk_index']
        constraints = [
            models.UniqueConstraint(
                fields=['extraction', 'chunk_index'],
                name='extraction_chunk_uniq',
            ),
        ]

    def __str__(self):
        loc = f"p{self.page_number}" if self.page_number else f"c{self.chunk_index}"
        return f"Chunk {loc} ({self.kind}, {len(self.text)} chars)"


class DocumentChunk(models.Model):
    """A retrievable text unit for one course notebook (Phase 4, RAG).

    Deliberately portable: it stores text, provenance, metadata and the
    embedding *status*, but never the vector itself. The sibling
    ``DocumentChunkEmbedding`` row exists on every backend, yet only holds a
    real vector on PostgreSQL (``vector(N)`` + cosine HNSW index); on SQLite
    its column is typed ``text`` and stays empty, so the dev/test workflow
    keeps working without a vector server.

    Three kinds of rows are indexed:
      * ``SYLLABUS`` -> one row per syllabus passage (from ``ExtractionChunk``
        when a run exists, else the reconstructed syllabus text)
      * ``QUESTION`` -> one row per extracted ``Question``
      * ``EXAM_PAPER`` -> paper passages not claimed by an extracted question

    ``source_key`` is a stable unique identity so re-indexing upserts instead
    of duplicating rows; ``content_hash`` (SHA-256 of the normalized text)
    is what makes an unchanged passage skip re-embedding.
    """
    SOURCE_SYLLABUS = 'SYLLABUS'
    SOURCE_QUESTION = 'QUESTION'
    SOURCE_EXAM_PAPER = 'EXAM_PAPER'
    SOURCE_CHOICES = [
        (SOURCE_SYLLABUS, 'Syllabus passage'),
        (SOURCE_QUESTION, 'Question'),
        (SOURCE_EXAM_PAPER, 'Exam paper passage'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_EMBEDDED = 'EMBEDDED'
    STATUS_FAILED = 'FAILED'
    STATUS_STALE = 'STALE'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_EMBEDDED, 'Embedded'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_STALE, 'Stale'),
    ]

    notebook = models.ForeignKey(
        CourseNotebook, on_delete=models.CASCADE,
        related_name='document_chunks'
    )
    source_type = models.CharField(
        max_length=16, choices=SOURCE_CHOICES, default=SOURCE_SYLLABUS,
        db_index=True
    )
    # Exactly one source document + optional question link; which FK is set
    # depends on source_type (see clean()). CASCADE so a deleted paper /
    # syllabus / question never leaves an orphan retrievable fragment.
    syllabus = models.ForeignKey(
        Syllabus, on_delete=models.CASCADE, null=True, blank=True,
        related_name='document_chunks'
    )
    exam_paper = models.ForeignKey(
        ExamPaper, on_delete=models.CASCADE, null=True, blank=True,
        related_name='document_chunks'
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, null=True, blank=True,
        related_name='document_chunks'
    )
    # Human-facing coordinates kept on the row so a result can cite a source
    # without a second join.
    question_number = models.CharField(max_length=20, blank=True, default='')
    parent_number = models.CharField(max_length=20, blank=True, default='')
    page_number = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="1-based page number when the source has pages."
    )
    chunk_index = models.PositiveIntegerField(default=0)
    text = models.TextField()
    content_hash = models.CharField(
        max_length=64, db_index=True,
        help_text="SHA-256 of the normalized text; drives skip/reindex."
    )
    metadata = models.JSONField(default=dict, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    embedding_status = models.CharField(
        max_length=16, choices=STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True
    )
    embedding_model = models.CharField(max_length=100, blank=True, default='')
    embedding_dim = models.PositiveIntegerField(null=True, blank=True)
    embedded_at = models.DateTimeField(null=True, blank=True)
    # Machine-readable error code only (e.g. 'quota_exceeded'); never raw
    # provider output or source text, so it is safe to log/return.
    embedding_error = models.CharField(max_length=64, blank=True, default='')
    source_key = models.CharField(max_length=120, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source_key']
        indexes = [
            models.Index(fields=['notebook', 'source_type'],
                         name='docchunk_nb_type_idx'),
            models.Index(fields=['notebook', 'year'],
                         name='docchunk_nb_year_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        source_type='SYLLABUS', syllabus__isnull=False,
                        question__isnull=True, exam_paper__isnull=True
                    )
                    | models.Q(
                        source_type='QUESTION', question__isnull=False,
                        exam_paper__isnull=False, syllabus__isnull=True
                    )
                    | models.Q(
                        source_type='EXAM_PAPER', exam_paper__isnull=False,
                        question__isnull=True, syllabus__isnull=True
                    )
                ),
                name='docchunk_source_valid',
            ),
        ]

    @staticmethod
    def hash_text(text: str) -> str:
        """SHA-256 of normalized text (NFC + whitespace collapsed).

        Two renderings of the same passage normalize to the same hash, which
        is what makes re-embedding skippable.
        """
        import hashlib
        import unicodedata

        normalized = unicodedata.normalize('NFC', text or '')
        normalized = ' '.join(normalized.split())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def build_source_key(self) -> str:
        """Stable unique identity used for upserts during (re)indexing."""
        if self.source_type == self.SOURCE_SYLLABUS and self.syllabus_id:
            return f"syl:{self.syllabus_id}:c:{self.chunk_index}"
        if self.source_type == self.SOURCE_QUESTION and self.question_id:
            return f"q:{self.question_id}:c:{self.chunk_index}"
        if self.source_type == self.SOURCE_EXAM_PAPER and self.exam_paper_id:
            return f"p:{self.exam_paper_id}:c:{self.chunk_index}"
        return ''

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        expected = {
            self.SOURCE_SYLLABUS: ('syllabus_id', self.syllabus_id),
            self.SOURCE_QUESTION: ('question_id', self.question_id),
            self.SOURCE_EXAM_PAPER: ('exam_paper_id', self.exam_paper_id),
        }
        if self.source_type in expected:
            field_name, value = expected[self.source_type]
            if not value:
                raise ValidationError({
                    field_name: (
                        f"{self.source_type} chunks require a linked "
                        f"{field_name}."
                    )
                })

    def save(self, *args, **kwargs):
        if not self.source_key:
            self.source_key = self.build_source_key()
        if not self.content_hash:
            self.content_hash = self.hash_text(self.text)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.source_key} [{self.embedding_status}]"


class DynamicVectorField(VectorField):
    """A ``vector`` column whose dimension comes from settings.

    ``EMBEDDING_DIMENSION`` is environment configuration, not a schema
    migration input: ``deconstruct()`` drops the dimension so changing the
    setting never emits a half-applied ``AlterField``. The column is created
    by ``predictor.services.rag.schema.ensure_vector_schema()``, which also
    rebuilds it when the configured dimension changes -- that rebuild only
    ever drops *vectors*, never ``DocumentChunk`` rows or their text.

    The table itself exists on every backend (so Django's cascade collector
    can delete chunks on SQLite too); only the column type differs, and only
    PostgreSQL ever stores or queries a vector in it.
    """
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('dimensions', settings.EMBEDDING_DIMENSION)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop('dimensions', None)
        return name, path, args, kwargs

    def db_type(self, connection):
        if connection.vendor != 'postgresql':
            return 'text'
        return 'vector(%d)' % (self.dimensions or settings.EMBEDDING_DIMENSION)


class DocumentChunkEmbedding(models.Model):
    """The pgvector vector for one ``DocumentChunk``.

    Split from ``DocumentChunk`` so SQLite can still run the full Django
    suite: the table is created everywhere (a FK/cascade target must exist on
    every backend), but the ``embedding`` column is typed ``text`` there and
    is never written -- only PostgreSQL stores or queries a vector in it. DDL
    plus the HNSW index come from ``0013_phase4_rag`` /
    ``schema.ensure_vector_schema()``.

    ``embedding_model``/``dim``/``content_hash`` are denormalized so a model
    or dimension change (or a text edit) makes the row detectably stale.
    """
    chunk = models.OneToOneField(
        DocumentChunk, on_delete=models.CASCADE, related_name='embedding_record'
    )
    embedding = DynamicVectorField()
    embedding_model = models.CharField(max_length=100)
    dim = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'predictor_documentchunkembedding'
        ordering = ['chunk_id']

    def __str__(self):
        return f"Emb({self.chunk_id}, {self.dim}d, {self.embedding_model})"
