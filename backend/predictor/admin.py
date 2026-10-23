from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import (
    ExamPaper, Topic, Prediction, Syllabus,
    CourseNotebook, Question, NotebookTopic, QuestionTopic,
    ChatSession, ChatMessage, GeneratedQuestion, GenerationRequest,
    ExtractionRun, ExtractionChunk, DocumentChunk,
)

# Unregister the default User admin
admin.site.unregister(User)

# Register the default User admin with customizations
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'subject', 'uploaded_at', 'processed', 'topic_count')
    list_filter = ('subject', 'uploaded_at', 'processed', 'user')
    search_fields = ('title', 'description', 'user__username', 'subject')
    readonly_fields = ('uploaded_at', 'processed_at')
    ordering = ('-uploaded_at',)

@admin.register(ExamPaper)
class ExamPaperAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'user', 'year', 'total_marks', 'uploaded_at', 'processed',
        'topic_count',
    )
    list_filter = ('year', 'uploaded_at', 'processed', 'user')
    search_fields = ('title', 'description', 'user__username')
    readonly_fields = ('uploaded_at', 'processed_at')
    ordering = ('-uploaded_at',)

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_source', 'frequency', 'last_seen')
    list_filter = ('last_seen',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'last_seen')

    def get_source(self, obj):
        if obj.syllabus:
            return f"Syllabus: {obj.syllabus.title}"
        elif obj.exam_paper:
            return f"Exam: {obj.exam_paper.title}"
        return "Unknown"
    get_source.short_description = 'Source'
    get_source.admin_order_field = 'name'

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_source', 'created_at', 'accuracy_score', 'prediction_type')
    list_filter = ('prediction_type', 'created_at', 'user')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at', 'quantum_result', 'classical_result')

    def get_source(self, obj):
        if obj.syllabus:
            return f"Syllabus: {obj.syllabus.title}"
        elif obj.exam_paper:
            return f"Exam: {obj.exam_paper.title}"
        return "Unknown"
    get_source.short_description = 'Source'
    get_source.admin_order_field = 'created_at'

# Phase 2: course notebooks and scoped records.


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    readonly_fields = ('created_at', 'updated_at')
    fields = (
        'question_number', 'parent_number', 'year', 'marks',
        'extraction_status', 'extraction_confidence', 'question_type',
        'difficulty', 'created_at',
    )


@admin.register(CourseNotebook)
class CourseNotebookAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'course_code', 'owner', 'status', 'created_at',
        'updated_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'course_code', 'institution', 'owner__username')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [QuestionInline]
    ordering = ('-updated_at',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'get_label', 'exam_paper', 'notebook', 'year', 'marks',
        'extraction_status', 'difficulty', 'extraction_method',
    )
    list_filter = (
        'extraction_status', 'extraction_method', 'difficulty',
        'question_type', 'type_source', 'type_review_status', 'year',
    )
    search_fields = ('raw_text', 'normalized_text', 'question_number')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('exam_paper', 'parent_number', 'question_number')

    def get_label(self, obj):
        label = (
            f"{obj.parent_number}{obj.question_number}"
            if obj.parent_number
            else obj.question_number
        )
        return f"Q{label}"
    get_label.short_description = 'Question'


class QuestionTopicInline(admin.TabularInline):
    model = QuestionTopic
    extra = 0
    fields = (
        'topic', 'role', 'review_status', 'classification_source',
        'confidence', 'classifier_version', 'created_at',
    )
    readonly_fields = ('created_at',)


@admin.register(NotebookTopic)
class NotebookTopicAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'notebook', 'normalized_name', 'review_status', 'created_at',
    )
    list_filter = ('review_status',)
    search_fields = ('name', 'normalized_name', 'notebook__title')
    readonly_fields = ('normalized_name', 'created_at', 'updated_at')
    inlines = [QuestionTopicInline]


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('created_at',)
    fields = ('role', 'content', 'created_at')


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'notebook', 'user', 'created_at', 'updated_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'notebook__title', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ChatMessageInline]


@admin.register(GeneratedQuestion)
class GeneratedQuestionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'notebook', 'review_status', 'difficulty', 'marks',
        'creator', 'created_at',
    )
    list_filter = ('review_status', 'difficulty', 'question_type')
    search_fields = ('question_text', 'answer_text', 'notebook__title')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(GenerationRequest)
class GenerationRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'notebook', 'status', 'topic', 'question_count',
        'questions_created', 'questions_validated', 'creator', 'created_at',
    )
    list_filter = ('status', 'difficulty', 'language', 'created_at')
    search_fields = ('error_code', 'error_message', 'notebook__title')
    readonly_fields = ('created_at', 'updated_at', 'finished_at')
    ordering = ('-created_at',)


# Phase 3: source-traceable extraction.


class ExtractionChunkInline(admin.TabularInline):
    model = ExtractionChunk
    extra = 0
    readonly_fields = ('char_start', 'char_end')
    fields = (
        'chunk_index', 'page_number', 'kind', 'method', 'confidence',
        'is_low_text', 'char_start', 'char_end',
    )
    ordering = ('chunk_index',)


@admin.register(ExtractionRun)
class ExtractionRunAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'source_type', 'get_source', 'status', 'extraction_method',
        'file_hash', 'question_count', 'page_count', 'created_at',
    )
    list_filter = ('source_type', 'status', 'extraction_method', 'created_at')
    search_fields = ('file_hash', 'error_code', 'error_message')
    readonly_fields = ('created_at', 'started_at', 'finished_at')
    inlines = [ExtractionChunkInline]
    ordering = ('-created_at',)

    def get_source(self, obj):
        source = obj.source_document
        if source is None:
            return "Unknown"
        return f"{obj.source_type}: {source}"
    get_source.short_description = 'Source'


@admin.register(ExtractionChunk)
class ExtractionChunkAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'extraction', 'chunk_index', 'page_number', 'kind',
        'method', 'is_low_text', 'created_len',
    )
    list_filter = ('kind', 'method', 'is_low_text')
    search_fields = ('text',)
    readonly_fields = ('char_start', 'char_end')
    ordering = ('extraction', 'chunk_index')

    def created_len(self, obj):
        return len(obj.text)
    created_len.short_description = 'Chars'


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = (
        'source_key', 'notebook', 'source_type', 'year', 'page_number',
        'embedding_status', 'embedding_model', 'updated_at',
    )
    list_filter = ('source_type', 'embedding_status', 'notebook')
    search_fields = ('source_key', 'text', 'question_number')
    # Embedding bookkeeping and text are managed by `manage.py index_rag`;
    # admins may inspect but not hand-edit them.
    readonly_fields = (
        'content_hash', 'embedding_status', 'embedding_model', 'embedding_dim',
        'embedded_at', 'embedding_error', 'source_key', 'created_at',
        'updated_at',
    )
    ordering = ('-updated_at',)


# Custom admin site header
admin.site.site_header = 'EduQuantum Predictor Administration'
admin.site.site_title = 'EduQuantum Admin'
admin.site.index_title = 'EduQuantum Dashboard'
