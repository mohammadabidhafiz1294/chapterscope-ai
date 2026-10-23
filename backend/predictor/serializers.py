from rest_framework import serializers

from .models import (
    ChatMessage,
    ChatSession,
    CourseNotebook,
    ExamPaper,
    ExtractionChunk,
    ExtractionRun,
    GeneratedQuestion,
    GenerationRequest,
    NotebookTopic,
    Question,
    QuestionTopic,
    Syllabus,
)
from .services.analytics.catalog import topic_label_index
from .services.analytics.labels import normalize_label


class CourseNotebookSerializer(serializers.ModelSerializer):
    """Read/write representation of a course notebook.

    Counts are read-only and provided by the view via queryset annotations
    (falling back to a query when not annotated, e.g. on a fresh create).
    """
    syllabus_count = serializers.IntegerField(read_only=True, default=0)
    paper_count = serializers.IntegerField(read_only=True, default=0)
    question_count = serializers.IntegerField(read_only=True, default=0)
    is_archived = serializers.BooleanField(read_only=True)

    class Meta:
        model = CourseNotebook
        fields = [
            'id', 'title', 'course_code', 'institution', 'description',
            'status', 'archived_at', 'is_archived',
            'syllabus_count', 'paper_count', 'question_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'archived_at', 'created_at', 'updated_at']

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Title must not be empty.')
        return value


class SyllabusSummarySerializer(serializers.ModelSerializer):
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = Syllabus
        fields = [
            'id', 'title', 'subject', 'processed', 'processed_at',
            'topic_count', 'uploaded_at', 'has_file', 'notebook',
            'content_hash', 'processing_status', 'processing_error',
        ]
        read_only_fields = fields

    def get_has_file(self, obj):
        return bool(obj.file)


class ExamPaperSummarySerializer(serializers.ModelSerializer):
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = ExamPaper
        fields = [
            'id', 'title', 'year', 'total_marks', 'processed',
            'processed_at',
            'question_count', 'topic_count', 'uploaded_at', 'has_file',
            'notebook', 'content_hash', 'processing_status', 'processing_error',
        ]
        read_only_fields = fields

    def get_has_file(self, obj):
        return bool(obj.file)


class TopicLinkSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)

    class Meta:
        model = QuestionTopic
        fields = [
            'id', 'topic', 'topic_name', 'role', 'confidence',
            'classification_source', 'classifier_version', 'review_status',
        ]
        read_only_fields = fields


class QuestionSerializer(serializers.ModelSerializer):
    exam_paper_title = serializers.CharField(
        source='exam_paper.title', read_only=True
    )
    source_page_number = serializers.SerializerMethodField()
    parent_question_label = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id', 'exam_paper', 'exam_paper_title', 'notebook',
            'question_number', 'parent_number', 'raw_text', 'normalized_text',
            'page_reference', 'marks', 'year',
            'extraction_status', 'extraction_confidence',
            'question_type', 'difficulty',
            # Phase 5 label provenance (written by the classifier/review flow).
            'type_source', 'type_confidence', 'type_classifier_version',
            'type_review_status',
            # Phase 3 source traceability.
            'source_run', 'source_chunk', 'source_page_number',
            'parent_question', 'parent_question_label',
            'extraction_method', 'options', 'extraction_warnings',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'notebook', 'year', 'created_at', 'updated_at',
            'source_run', 'source_chunk', 'source_page_number',
            'parent_question', 'parent_question_label',
            'extraction_method', 'options', 'extraction_warnings',
            'type_source', 'type_confidence', 'type_classifier_version',
            'type_review_status',
        ]

    def get_source_page_number(self, obj):
        if obj.source_chunk is not None:
            return obj.source_chunk.page_number
        return None

    def get_parent_question_label(self, obj):
        if obj.parent_question is not None:
            parent = obj.parent_question
            return parent.question_number
        return None


class QuestionDetailSerializer(QuestionSerializer):
    topic_links = TopicLinkSerializer(many=True, read_only=True)

    class Meta(QuestionSerializer.Meta):
        fields = QuestionSerializer.Meta.fields + ['topic_links']


class NotebookTopicSerializer(serializers.ModelSerializer):
    """Topic catalogue entry: name, curated aliases and review status.

    Labels are unique per notebook across names *and* aliases (Phase 5), so
    both fields are validated against the other topics' labels with the same
    normalisation the classifier uses.
    """
    normalized_name = serializers.CharField(read_only=True)
    MAX_ALIASES = 10

    class Meta:
        model = NotebookTopic
        fields = [
            'id', 'name', 'normalized_name', 'aliases', 'description',
            'review_status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def _other_labels(self):
        notebook = self.context.get('notebook')
        if notebook is None:
            return {}
        others = NotebookTopic.objects.filter(notebook=notebook)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        return topic_label_index(others)

    def validate_name(self, value):
        value = str(value).strip()
        if not value:
            raise serializers.ValidationError('Topic name must not be empty.')
        normalized = normalize_label(value)
        if not normalized:
            raise serializers.ValidationError(
                'Topic name must contain letters or digits.'
            )
        if len(value) > 200:
            raise serializers.ValidationError(
                'Topic name must be at most 200 characters.'
            )
        if normalized in self._other_labels():
            raise serializers.ValidationError(
                'A topic with this name already exists in this notebook.'
            )
        return value

    def validate_aliases(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('aliases must be a list of strings.')
        if len(value) > self.MAX_ALIASES:
            raise serializers.ValidationError(
                f'aliases may contain at most {self.MAX_ALIASES} items.'
            )
        incoming_name = self.initial_data.get('name')
        if incoming_name is None and self.instance is not None:
            incoming_name = self.instance.name
        own_name = normalize_label(str(incoming_name or ''))
        others = self._other_labels()
        seen: set[str] = set()
        cleaned: list[str] = []
        for item in value:
            label = str(item).strip()
            normalized = normalize_label(label)
            if not normalized:
                raise serializers.ValidationError(
                    'Aliases must contain letters or digits.'
                )
            if len(label) > 200:
                raise serializers.ValidationError(
                    'Aliases must be at most 200 characters.'
                )
            if normalized == own_name:
                raise serializers.ValidationError(
                    f'Alias "{label}" duplicates the topic name.'
                )
            if normalized in seen:
                raise serializers.ValidationError(f'Duplicate alias "{label}".')
            if normalized in others:
                raise serializers.ValidationError(
                    f'Alias "{label}" is already used by another topic.'
                )
            seen.add(normalized)
            cleaned.append(label)
        return cleaned

    def validate_review_status(self, value):
        if value not in ('CONFIRMED', 'NEEDS_REVIEW'):
            raise serializers.ValidationError(
                'review_status must be CONFIRMED or NEEDS_REVIEW.'
            )
        return value


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = [
            'id', 'notebook', 'title', 'message_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['notebook', 'created_at', 'updated_at']

    def get_message_count(self, obj):
        # Views annotate message_count; fall back to a query otherwise.
        annotated = getattr(obj, 'message_count', None)
        if annotated is not None:
            return annotated
        return obj.messages.count()


class ChatMessageSerializer(serializers.ModelSerializer):
    """Read shape for stored chat turns.

    ``sources`` / ``status`` are derived from the server-controlled
    ``metadata`` written by the Phase 6 pipeline (assistant turns only);
    client-supplied metadata is never persisted.
    """
    sources = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = [
            'id', 'session', 'role', 'content', 'metadata', 'sources',
            'status', 'created_at',
        ]
        read_only_fields = [
            'session', 'role', 'metadata', 'sources', 'status', 'created_at',
        ]

    def get_sources(self, obj):
        meta = obj.metadata or {}
        sources = meta.get('sources')
        return sources if isinstance(sources, list) else []

    def get_status(self, obj):
        meta = obj.metadata or {}
        status = meta.get('status')
        return status if isinstance(status, str) else ''


class ChatMessageCreateSerializer(serializers.Serializer):
    """Write serializer for one chat turn (user text only).

    The Phase 6 pipeline generates both the USER and ASSISTANT rows; clients
    cannot forge roles or attach metadata (``metadata`` is accepted for
    backward compatibility and ignored).
    """
    content = serializers.CharField(
        allow_blank=False, trim_whitespace=True, max_length=20000
    )
    # Optional safe metadata (e.g. client-side UI state). Never secrets.
    # Accepted but not persisted: assistant metadata is server-controlled.
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_metadata(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Metadata must be a JSON object.')
        return value


class GeneratedQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedQuestion
        fields = [
            'id', 'notebook', 'creator', 'source_question', 'topic',
            'question_text', 'answer_text', 'solution_text',
            'question_type', 'marks', 'difficulty', 'review_status',
            'source_refs', 'created_at', 'updated_at',
        ]
        read_only_fields = ['notebook', 'creator', 'created_at', 'updated_at']


# Phase 3: source-traceable extraction.


class ExtractionRunSerializer(serializers.ModelSerializer):
    """Summary of one extraction run (no chunk text; use the chunks endpoint)."""

    class Meta:
        model = ExtractionRun
        fields = [
            'id', 'source_type', 'syllabus', 'exam_paper', 'file_hash',
            'status', 'extraction_method', 'page_count', 'chunk_count',
            'total_chars', 'question_count', 'low_text_pages', 'warnings',
            'ocr_required', 'error_code', 'error_message',
            'started_at', 'finished_at', 'created_at',
        ]
        read_only_fields = fields


class ExtractionChunkSerializer(serializers.ModelSerializer):
    """One extracted text chunk with page/chunk boundaries."""

    class Meta:
        model = ExtractionChunk
        fields = [
            'id', 'extraction', 'chunk_index', 'page_number', 'kind',
            'text', 'char_start', 'char_end', 'method', 'confidence',
            'is_low_text', 'warnings',
        ]
        read_only_fields = fields


# Phase 7: practice-question generation.


class GenerationRequestSerializer(serializers.ModelSerializer):
    """One generation request with its outcome (no provider payloads)."""

    topic_name = serializers.CharField(source='topic.name', read_only=True,
                                       default=None)

    class Meta:
        model = GenerationRequest
        fields = [
            'id', 'notebook', 'creator', 'topic', 'topic_name', 'topic_ids',
            'question_count', 'question_types', 'difficulty', 'marks',
            'language', 'include_answers', 'year_from', 'year_to',
            'status', 'questions_created', 'questions_validated',
            'questions_needs_review', 'generation_model',
            'generation_version', 'request_meta', 'error_code',
            'error_message', 'created_at', 'updated_at', 'finished_at',
        ]
        read_only_fields = fields


class GeneratedQuestionDetailSerializer(serializers.ModelSerializer):
    """Full detail for one generated question (all Phase 7 fields)."""

    topic_name = serializers.CharField(source='topic.name', read_only=True,
                                       default=None)

    class Meta:
        model = GeneratedQuestion
        fields = [
            'id', 'notebook', 'creator', 'request', 'source_question',
            'topic', 'topic_name', 'topic_ids', 'question_text',
            'answer_text', 'solution_text', 'question_type', 'marks',
            'difficulty', 'review_status', 'source_refs', 'language',
            'marking_rubric', 'generation_model', 'generation_version',
            'validation_status', 'validation_report', 'answer_confidence',
            'options', 'numeric_report', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class GenerationRequestDetailSerializer(GenerationRequestSerializer):
    """One generation request with its persisted questions, in paper order.

    This is what makes a generated paper reopenable: the list endpoint stays
    lightweight, while the detail endpoint returns the full request plus the
    questions it produced.
    """

    questions = serializers.SerializerMethodField()

    class Meta(GenerationRequestSerializer.Meta):
        fields = GenerationRequestSerializer.Meta.fields + ['questions']
        read_only_fields = fields

    def get_questions(self, obj):
        rows = obj.questions.order_by('id')
        return GeneratedQuestionDetailSerializer(
            rows, many=True, context=self.context
        ).data


class GenerationRequestCreateSerializer(serializers.Serializer):
    """Validates the request shape before anything is written."""

    topic_id = serializers.IntegerField()
    count = serializers.IntegerField(required=False, default=5, min_value=1,
                                     max_value=20)
    question_types = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    difficulty = serializers.ChoiceField(
        choices=[c for c in Question.DIFFICULTY_CHOICES if c[0]],
        required=False, allow_blank=True, default=''
    )
    marks = serializers.IntegerField(required=False, min_value=1, max_value=200,
                                     allow_null=True, default=None)
    language = serializers.CharField(required=False, default='en',
                                     max_length=20)
    include_answers = serializers.BooleanField(required=False, default=True)
    year_from = serializers.IntegerField(required=False, allow_null=True,
                                         default=None)
    year_to = serializers.IntegerField(required=False, allow_null=True,
                                       default=None)

    def validate_question_types(self, value):
        valid = {c[0] for c in Question.TYPE_CHOICES if c[0]}
        unknown = [t for t in value if t not in valid]
        if unknown:
            raise serializers.ValidationError(
                'Unknown question type(s): ' + ', '.join(sorted(unknown))
            )
        return value

    def validate(self, attrs):
        if (attrs.get('year_from') is not None
                and attrs.get('year_to') is not None
                and attrs['year_from'] > attrs['year_to']):
            raise serializers.ValidationError(
                {'year_from': 'Must not be greater than year_to.'}
            )
        return attrs
