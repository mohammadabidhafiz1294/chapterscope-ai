"""Phase 2 course-notebook REST API.

Every endpoint is owner-scoped (``owner=request.user``) and nested under a
notebook that is itself fetched owner-scoped, so a foreign notebook id yields
404 before any object-level check is needed. ``IsNotebookOwner`` adds
defence-in-depth. Archived notebooks are read-only for content writes.
"""
import mimetypes
import os

from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

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
    Syllabus,
)
from .permissions import IsNotebookOwner
from .serializers import (
    ChatMessageCreateSerializer,
    ChatMessageSerializer,
    ChatSessionSerializer,
    CourseNotebookSerializer,
    ExamPaperSummarySerializer,
    ExtractionChunkSerializer,
    ExtractionRunSerializer,
    GeneratedQuestionDetailSerializer,
    GenerationRequestCreateSerializer,
    GenerationRequestDetailSerializer,
    GenerationRequestSerializer,
    NotebookTopicSerializer,
    QuestionDetailSerializer,
    QuestionSerializer,
    SyllabusSummarySerializer,
)


class NotebookScopedMixin:
    """Resolves the notebook from the URL, scoped to the request user."""
    permission_classes = [IsAuthenticated, IsNotebookOwner]

    def get_notebook(self):
        notebook = getattr(self, '_notebook', None)
        if notebook is None:
            notebook = get_object_or_404(
                CourseNotebook,
                pk=self.kwargs['notebook_pk'],
                owner=self.request.user,
            )
            self._notebook = notebook
        return notebook

    def ensure_writable(self, notebook):
        if notebook.is_archived:
            raise ValidationError(
                {'detail': 'Notebook is archived; it is read-only.'}
            )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['notebook'] = self.get_notebook()
        return context


class NotebookViewSet(viewsets.ModelViewSet):
    """CRUD + archive/unarchive for the caller's own notebooks."""
    serializer_class = CourseNotebookSerializer
    permission_classes = [IsAuthenticated, IsNotebookOwner]

    def get_queryset(self):
        qs = CourseNotebook.objects.filter(owner=self.request.user).annotate(
            syllabus_count=Count('syllabi', distinct=True),
            paper_count=Count('exam_papers', distinct=True),
            question_count=Count('questions', distinct=True),
        ).order_by('-updated_at')
        # Status filter applies to list only; detail/archive/unarchive must
        # still resolve archived notebooks.
        if self.action != 'list':
            return qs
        status_param = self.request.query_params.get('status', '')
        if status_param == 'archived':
            qs = qs.filter(status=CourseNotebook.STATUS_ARCHIVED)
        elif status_param == 'all':
            pass
        else:
            qs = qs.filter(status=CourseNotebook.STATUS_ACTIVE)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def destroy(self, request, *args, **kwargs):
        notebook = self.get_object()
        # Deleting a notebook with attached source documents would silently
        # orphan their files; require an explicit detach first.
        if notebook.syllabi.exists() or notebook.exam_papers.exists():
            return Response(
                {'detail': 'Detach syllabus/papers before deleting this notebook.'},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        notebook = self.get_object()
        notebook.status = CourseNotebook.STATUS_ARCHIVED
        notebook.archived_at = timezone.now()
        notebook.save(update_fields=['status', 'archived_at', 'updated_at'])
        serializer = self.get_serializer(notebook)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        notebook = self.get_object()
        notebook.status = CourseNotebook.STATUS_ACTIVE
        notebook.archived_at = None
        notebook.save(update_fields=['status', 'archived_at', 'updated_at'])
        serializer = self.get_serializer(notebook)
        return Response(serializer.data)


class NotebookSyllabiListCreateView(NotebookScopedMixin, generics.ListCreateAPIView):
    """List syllabi attached to the notebook; attach an owned syllabus by id."""
    serializer_class = SyllabusSummarySerializer

    def get_queryset(self):
        return Syllabus.objects.filter(
            notebook=self.get_notebook(), user=self.request.user
        ).order_by('-uploaded_at')

    def create(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        syllabus_id = request.data.get('syllabus_id')
        if not syllabus_id:
            raise ValidationError({'syllabus_id': 'This field is required.'})
        syllabus = get_object_or_404(
            Syllabus, pk=syllabus_id, user=request.user
        )
        if syllabus.notebook_id == notebook.pk:
            raise ValidationError(
                {'detail': 'Syllabus is already attached to this notebook.'}
            )
        if syllabus.notebook_id is not None:
            return Response(
                {'detail': 'Syllabus is already attached to another notebook.'},
                status=status.HTTP_409_CONFLICT,
            )
        syllabus.notebook = notebook
        syllabus.save(update_fields=['notebook'])
        return Response(
            self.get_serializer(syllabus).data, status=status.HTTP_200_OK
        )


class NotebookSyllabusUploadView(NotebookScopedMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        title = str(request.data.get('title', '')).strip()
        subject = str(request.data.get('subject', '')).strip()
        uploaded = request.FILES.get('file')
        if not title or not subject or uploaded is None:
            raise ValidationError({'detail': 'title, subject and file are required.'})
        syllabus = Syllabus.objects.create(
            user=request.user, notebook=notebook, title=title,
            subject=subject, file=uploaded,
        )
        return Response(SyllabusSummarySerializer(syllabus).data, status=status.HTTP_201_CREATED)


class NotebookSyllabusDetachView(NotebookScopedMixin, generics.DestroyAPIView):
    """Detach (unassign) a syllabus from the notebook; the file is preserved."""
    serializer_class = SyllabusSummarySerializer

    def get_object(self):
        return get_object_or_404(
            Syllabus,
            pk=self.kwargs['sid'],
            notebook=self.get_notebook(),
            user=self.request.user,
        )

    def perform_destroy(self, instance):
        instance.notebook = None
        instance.save(update_fields=['notebook'])


class NotebookSyllabusFileView(NotebookScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsNotebookOwner]

    def get(self, request, *args, **kwargs):
        syllabus = get_object_or_404(
            Syllabus,
            pk=self.kwargs['sid'],
            notebook=self.get_notebook(),
            user=request.user,
        )
        if not syllabus.file:
            return Response(
                {'detail': 'This syllabus has no file.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _file_response(syllabus.file)


class NotebookPapersListCreateView(NotebookScopedMixin, generics.ListCreateAPIView):
    """List exam papers attached to the notebook; attach an owned paper by id."""
    serializer_class = ExamPaperSummarySerializer

    def get_queryset(self):
        return ExamPaper.objects.filter(
            notebook=self.get_notebook(), user=self.request.user
        ).order_by('-uploaded_at')

    def create(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        paper_id = request.data.get('paper_id')
        if not paper_id:
            raise ValidationError({'paper_id': 'This field is required.'})
        paper = get_object_or_404(ExamPaper, pk=paper_id, user=request.user)
        if paper.notebook_id == notebook.pk:
            raise ValidationError(
                {'detail': 'Exam paper is already attached to this notebook.'}
            )
        if paper.notebook_id is not None:
            return Response(
                {'detail': 'Exam paper is already attached to another notebook.'},
                status=status.HTTP_409_CONFLICT,
            )
        paper.notebook = notebook
        paper.save(update_fields=['notebook'])
        return Response(
            self.get_serializer(paper).data, status=status.HTTP_200_OK
        )


class NotebookPaperUploadView(NotebookScopedMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        title = str(request.data.get('title', '')).strip()
        uploaded = request.FILES.get('file')
        try:
            year = int(request.data.get('year', ''))
        except (TypeError, ValueError):
            year = 0
        if not title or uploaded is None or not year:
            raise ValidationError({'detail': 'title, year and file are required.'})
        total_marks = request.data.get('total_marks') or None
        paper = ExamPaper.objects.create(
            user=request.user, notebook=notebook, title=title, year=year,
            total_marks=total_marks, file=uploaded,
        )
        return Response(ExamPaperSummarySerializer(paper).data, status=status.HTTP_201_CREATED)


class NotebookPaperDetachView(NotebookScopedMixin, generics.DestroyAPIView):
    """Detach (unassign) an exam paper from the notebook; the file is preserved."""
    serializer_class = ExamPaperSummarySerializer

    def get_object(self):
        return get_object_or_404(
            ExamPaper,
            pk=self.kwargs['pid'],
            notebook=self.get_notebook(),
            user=self.request.user,
        )

    def perform_destroy(self, instance):
        instance.notebook = None
        instance.save(update_fields=['notebook'])


class NotebookPaperFileView(NotebookScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsNotebookOwner]

    def get(self, request, *args, **kwargs):
        paper = get_object_or_404(
            ExamPaper,
            pk=self.kwargs['pid'],
            notebook=self.get_notebook(),
            user=request.user,
        )
        if not paper.file:
            return Response(
                {'detail': 'This exam paper has no file.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _file_response(paper.file)


def _file_response(django_file):
    """Stream a stored file with a safe content type and attachment name."""
    content_type, _ = mimetypes.guess_type(django_file.name)
    django_file.open('rb')
    response = FileResponse(
        django_file, content_type=content_type or 'application/octet-stream'
    )
    filename = os.path.basename(django_file.name)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


class NotebookQuestionListView(NotebookScopedMixin, generics.ListAPIView):
    """Notebook-scoped, filterable question list."""
    serializer_class = QuestionSerializer

    def get_queryset(self):
        notebook = self.get_notebook()
        qs = Question.objects.filter(
            notebook=notebook, exam_paper__user=self.request.user
        ).select_related('exam_paper', 'notebook')

        params = self.request.query_params
        paper = params.get('paper')
        if paper:
            qs = qs.filter(exam_paper_id=paper)
        year = params.get('year')
        if year:
            qs = qs.filter(year=year)
        topic = params.get('topic')
        if topic:
            qs = qs.filter(topic_links__topic_id=topic)
        extraction_status = params.get('status')
        if extraction_status:
            qs = qs.filter(extraction_status__iexact=extraction_status)
        question_type = params.get('question_type')
        if question_type:
            qs = qs.filter(question_type=question_type)
        difficulty = params.get('difficulty')
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        marks = params.get('marks')
        if marks:
            qs = qs.filter(marks=marks)
        search = params.get('search')
        if search:
            from django.db.models import Q

            qs = qs.filter(
                Q(raw_text__icontains=search) | Q(question_number__icontains=search)
            )
        return qs


class NotebookQuestionDetailView(NotebookScopedMixin, generics.RetrieveAPIView):
    """Single question with its topic links."""
    serializer_class = QuestionDetailSerializer

    def get_object(self):
        return get_object_or_404(
            Question.objects.select_related('exam_paper', 'notebook'),
            pk=self.kwargs['qid'],
            notebook=self.get_notebook(),
            exam_paper__user=self.request.user,
        )


class NotebookTopicListCreateView(NotebookScopedMixin, generics.ListCreateAPIView):
    """Notebook-scoped canonical topic list; manual topic create."""
    serializer_class = NotebookTopicSerializer

    def get_queryset(self):
        return NotebookTopic.objects.filter(notebook=self.get_notebook())

    def perform_create(self, serializer):
        self.ensure_writable(self.get_notebook())
        serializer.save(notebook=self.get_notebook())


class NotebookChatSessionListCreateView(
    NotebookScopedMixin, generics.ListCreateAPIView
):
    """List/create chat sessions for the notebook."""
    serializer_class = ChatSessionSerializer

    def get_queryset(self):
        return (
            ChatSession.objects
            .filter(notebook=self.get_notebook(), user=self.request.user)
            .annotate(message_count=Count('messages'))
            .order_by('-updated_at')
        )

    def perform_create(self, serializer):
        self.ensure_writable(self.get_notebook())
        serializer.save(notebook=self.get_notebook(), user=self.request.user)


class NotebookChatSessionDetailView(NotebookScopedMixin, generics.RetrieveAPIView):
    serializer_class = ChatSessionSerializer

    def get_object(self):
        return get_object_or_404(
            ChatSession.objects.annotate(message_count=Count('messages')),
            pk=self.kwargs['sid'],
            notebook=self.get_notebook(),
            user=self.request.user,
        )


def _chat_error_response(exc):
    """Chat/RAG error payload, plus the request id and any persisted turn.

    The pipeline attaches them when the user message was already written so
    the client can reconcile its transcript; config failures (503 before any
    write) carry no user_message.
    """
    body = exc.as_dict()
    request_id = getattr(exc, 'request_id', None)
    if request_id:
        body['request_id'] = request_id
    user_message = getattr(exc, 'user_message', None)
    if user_message is not None:
        body['user_message'] = user_message
    return Response(body, status=exc.http_status)


class NotebookChatMessageListCreateView(
    NotebookScopedMixin, generics.ListCreateAPIView
):
    """Read chat history; POST one turn through the source-grounded pipeline.

    The POST persists the USER message first, retrieves notebook-scoped
    passages, asks the configured LangChain model for a strictly-shaped JSON
    answer, keeps only citations that name a retrieved ``source_key`` and
    persists the ASSISTANT message with server-built source references. Chat
    failures map to ``{"error": {code, message, hint?}, request_id?,
    user_message?}`` and never leak provider payloads.
    """

    def get_queryset(self):
        return ChatMessage.objects.filter(
            session__pk=self.kwargs['sid'],
            session__notebook=self.get_notebook(),
            session__user=self.request.user,
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ChatMessageCreateSerializer
        return ChatMessageSerializer

    def create(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        session = get_object_or_404(
            ChatSession,
            pk=self.kwargs['sid'],
            notebook=notebook,
            user=request.user,
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .services.chat import pipeline
        from .services.chat.errors import ChatError
        from .services.rag.errors import RAGError

        try:
            payload = pipeline.respond(
                session, serializer.validated_data['content']
            )
        except (ChatError, RAGError) as exc:
            return _chat_error_response(exc)
        return Response(payload, status=status.HTTP_201_CREATED)


def _generation_error_response(exc):
    """Map a ``GenerationError`` onto its stable ``{error:{...}}`` envelope."""
    return Response(exc.as_dict(), status=exc.http_status)


class NotebookGenerationRequestListCreateView(
    NotebookScopedMixin, generics.ListCreateAPIView
):
    """List the caller's generation requests; POST to generate a paper.

    POST is the single Phase 7 entry point: it validates the request shape,
    resolves the model (503 ``generation_unavailable`` *before* any write if
    disabled/unconfigured), then generates, validates and persists a small
    batch of grounded questions. Failures return ``{error:{code,message,hint}}``
    and never leak provider payloads.
    """
    serializer_class = GenerationRequestSerializer

    def get_queryset(self):
        return (
            GenerationRequest.objects
            .filter(notebook=self.get_notebook(), creator=self.request.user)
            .order_by('-created_at')
        )

    def create(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        serializer = GenerationRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from .services.generation import pipeline
        from .services.generation.errors import GenerationError

        try:
            payload = pipeline.generate(
                notebook, request.user, serializer.validated_data
            )
        except GenerationError as exc:
            return _generation_error_response(exc)
        return Response(payload, status=status.HTTP_201_CREATED)


class NotebookGenerationRequestDetailView(
    NotebookScopedMixin, generics.RetrieveAPIView
):
    """Reopen one generation request (owner-scoped), with its questions."""
    serializer_class = GenerationRequestDetailSerializer

    def get_object(self):
        return get_object_or_404(
            GenerationRequest.objects,
            pk=self.kwargs['rid'],
            notebook=self.get_notebook(),
            creator=self.request.user,
        )


class NotebookGeneratedQuestionDetailView(
    NotebookScopedMixin, generics.RetrieveAPIView
):
    """Reopen one generated question (owner-scoped)."""
    serializer_class = GeneratedQuestionDetailSerializer

    def get_object(self):
        return get_object_or_404(
            GeneratedQuestion.objects,
            pk=self.kwargs['qid'],
            notebook=self.get_notebook(),
            creator=self.request.user,
        )


# ---------------------------------------------------------------------------
# Phase 3: source-traceable extraction (process / extractions / chunks).
# ---------------------------------------------------------------------------


class _SourceScopedMixin(NotebookScopedMixin):
    """Resolves a syllabus or exam paper attached to the caller's notebook.

    Subclasses set ``source_type`` and the URL kwarg name for the document id
    (``pid`` for papers, ``sid`` for syllabi). Cross-user or unattached
    documents yield 404 before any processing.
    """

    source_type = None  # "EXAM_PAPER" or "SYLLABUS"
    doc_kwarg = None

    def get_source(self):
        notebook = self.get_notebook()
        if self.source_type == ExtractionRun.SOURCE_EXAM_PAPER:
            return get_object_or_404(
                ExamPaper,
                pk=self.kwargs[self.doc_kwarg],
                notebook=notebook,
                user=self.request.user,
            )
        return get_object_or_404(
            Syllabus,
            pk=self.kwargs[self.doc_kwarg],
            notebook=notebook,
            user=self.request.user,
        )


class NotebookPaperProcessView(_SourceScopedMixin, APIView):
    """POST: run source-traceable extraction for one exam paper."""

    source_type = ExtractionRun.SOURCE_EXAM_PAPER
    doc_kwarg = 'pid'

    def post(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        paper = self.get_source()
        force = bool(request.data.get('force'))
        from .services.extraction.processor import SourceProcessingService

        service = SourceProcessingService()
        run, outcome = service.process(
            paper, ExtractionRun.SOURCE_EXAM_PAPER, force=force
        )
        if outcome == 'conflict':
            return Response(
                {
                    'detail': 'Processing is already in progress for this paper.',
                    'run': ExtractionRunSerializer(run).data,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(ExtractionRunSerializer(run).data)


class NotebookSyllabusProcessView(_SourceScopedMixin, APIView):
    """POST: run source-traceable extraction for one syllabus."""

    source_type = ExtractionRun.SOURCE_SYLLABUS
    doc_kwarg = 'sid'

    def post(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        syllabus = self.get_source()
        force = bool(request.data.get('force'))
        from .services.extraction.processor import SourceProcessingService

        service = SourceProcessingService()
        run, outcome = service.process(
            syllabus, ExtractionRun.SOURCE_SYLLABUS, force=force
        )
        if outcome == 'conflict':
            return Response(
                {
                    'detail': 'Processing is already in progress for this syllabus.',
                    'run': ExtractionRunSerializer(run).data,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(ExtractionRunSerializer(run).data)


class _ExtractionListView(_SourceScopedMixin, generics.ListAPIView):
    """List extraction runs for one attached source document."""

    serializer_class = ExtractionRunSerializer

    def get_queryset(self):
        source = self.get_source()
        if self.source_type == ExtractionRun.SOURCE_EXAM_PAPER:
            return ExtractionRun.objects.filter(exam_paper=source)
        return ExtractionRun.objects.filter(syllabus=source)


class NotebookPaperExtractionListView(_ExtractionListView):
    source_type = ExtractionRun.SOURCE_EXAM_PAPER
    doc_kwarg = 'pid'


class NotebookSyllabusExtractionListView(_ExtractionListView):
    source_type = ExtractionRun.SOURCE_SYLLABUS
    doc_kwarg = 'sid'


class _ExtractionDetailView(_SourceScopedMixin, generics.RetrieveAPIView):
    """Retrieve one extraction run belonging to the source document."""

    serializer_class = ExtractionRunSerializer

    def get_object(self):
        source = self.get_source()
        qs = ExtractionRun.objects.filter(pk=self.kwargs['rid'])
        if self.source_type == ExtractionRun.SOURCE_EXAM_PAPER:
            qs = qs.filter(exam_paper=source)
        else:
            qs = qs.filter(syllabus=source)
        return get_object_or_404(qs)


class NotebookPaperExtractionDetailView(_ExtractionDetailView):
    source_type = ExtractionRun.SOURCE_EXAM_PAPER
    doc_kwarg = 'pid'


class NotebookSyllabusExtractionDetailView(_ExtractionDetailView):
    source_type = ExtractionRun.SOURCE_SYLLABUS
    doc_kwarg = 'sid'


class _ExtractionChunksView(_SourceScopedMixin, generics.ListAPIView):
    """List text chunks for one extraction run (paginated).

    Optional ``?page=<n>`` filters to a single PDF page. Chunks carry the
    exact source text and page/char boundaries for later RAG citation.
    """

    serializer_class = ExtractionChunkSerializer
    pagination_class = None  # return all chunks (bounded by page cap)

    def get_queryset(self):
        source = self.get_source()
        qs = ExtractionChunk.objects.filter(
            extraction__pk=self.kwargs['rid']
        ).order_by('chunk_index')
        if self.source_type == ExtractionRun.SOURCE_EXAM_PAPER:
            qs = qs.filter(extraction__exam_paper=source)
        else:
            qs = qs.filter(extraction__syllabus=source)
        page = self.request.query_params.get('page')
        if page and page.isdigit():
            qs = qs.filter(page_number=int(page))
        return qs


class NotebookPaperExtractionChunksView(_ExtractionChunksView):
    source_type = ExtractionRun.SOURCE_EXAM_PAPER
    doc_kwarg = 'pid'


class NotebookSyllabusExtractionChunksView(_ExtractionChunksView):
    source_type = ExtractionRun.SOURCE_SYLLABUS
    doc_kwarg = 'sid'


class NotebookSearchView(NotebookScopedMixin, APIView):
    """GET: retrieve indexed passages from one notebook (Phase 4, RAG).

    Read-only, so archived notebooks stay searchable. Every RAG failure is
    returned as ``{"error": {"code", "message", "hint"}}`` with the status the
    RAG layer chose (400 / 500 / 503 / 504); success returns
    ``{"status", "results", "meta"}`` where every result carries its source
    references and is marked ``untrusted``.
    """

    def get(self, request, *args, **kwargs):
        notebook = self.get_notebook()
        from .services.rag import retrieval
        from .services.rag.errors import RAGError

        params = request.query_params
        keyword = str(params.get('keyword', '')).strip().lower()
        try:
            payload = retrieval.search(
                notebook,
                params.get('q', ''),
                source_type=params.get('source_type'),
                year=params.get('year'),
                topic=params.get('topic'),
                keyword=keyword in ('1', 'true', 'yes', 'on'),
                limit=params.get('limit'),
            )
        except RAGError as exc:
            return Response(exc.as_dict(), status=exc.http_status)
        return Response(payload)


# ---------------------------------------------------------------------------
# Phase 5: deterministic course analytics (metrics from ORM rows only) plus
# the label review queue. AnalyticsError maps to {"error": {code, message,
# hint}} with the status the analytics layer chose (400 / 404 / 502 / 503).
# ---------------------------------------------------------------------------


def _bool_param(value, default=True):
    """Parse a JSON/bool/string flag ('true', '1', 'yes' -> True)."""
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def _analytics_error(exc):
    return Response(exc.as_dict(), status=exc.http_status)


class NotebookAnalyticsView(NotebookScopedMixin, APIView):
    """GET: analytics report (coverage, topics, trends, ranking).

    Read-only, so an archived notebook still reports. Every measure is
    defined in README.md and computed from this notebook's ORM rows; the
    payload carries the definitions version, measure labels, ranking
    weights, per-topic components and a non-prediction disclaimer.
    """

    def get(self, request, *args, **kwargs):
        from .services.analytics import metrics
        from .services.analytics.errors import AnalyticsError

        try:
            payload = metrics.build_report(
                self.get_notebook(),
                weighting=request.query_params.get('weighting'),
                topics=request.query_params.get('topics'),
            )
        except AnalyticsError as exc:
            return _analytics_error(exc)
        return Response(payload)


class NotebookTopicAnalyticsView(NotebookScopedMixin, APIView):
    """GET: one topic's per-year series, splits, link roles and components."""

    def get(self, request, *args, **kwargs):
        from .services.analytics import metrics
        from .services.analytics.errors import AnalyticsError

        notebook = self.get_notebook()
        topic = get_object_or_404(
            NotebookTopic, pk=self.kwargs['tid'], notebook=notebook,
        )
        try:
            payload = metrics.build_topic_report(
                notebook,
                topic,
                weighting=request.query_params.get('weighting'),
            )
        except AnalyticsError as exc:
            return _analytics_error(exc)
        return Response(payload)


class NotebookAnalyticsProposalsView(NotebookScopedMixin, APIView):
    """POST: create review-queue rows from proposed topic/type labels.

    Body: ``{"question_ids": [..], "limit": 10, "use_llm": true}``. The
    deterministic keyword pass always runs; ``use_llm=false`` skips the
    model, while an explicit LLM request without a usable model fails 503/502
    *before* anything is written. New links are ``NEEDS_REVIEW``, so the
    metrics do not move until the review endpoint confirms them.
    """

    def post(self, request, *args, **kwargs):
        from .services.analytics import classify
        from .services.analytics.errors import AnalyticsError

        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            payload = classify.propose_classifications(
                notebook,
                question_ids=body.get('question_ids'),
                limit=body.get('limit'),
                use_llm=_bool_param(body.get('use_llm'), default=True),
            )
        except AnalyticsError as exc:
            return _analytics_error(exc)
        created = bool(payload['links_created'] or payload['topics_created'])
        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class NotebookAnalyticsReviewView(NotebookScopedMixin, APIView):
    """GET: the pending review queue; POST: confirm/reject its entries.

    GET returns ``{"links", "topics", "types"}`` still marked
    ``NEEDS_REVIEW`` for this notebook (capped, notebook-scoped), so a
    half-reviewed batch can be resumed after a reload.

    POST body: ``{"links": [{"id", "action"}], "topics": [{"id", "action"}],
    "types": [{"question_id", "action"}]}`` with action = confirm|reject.
    Unknown ids and foreign-notebook ids are both ``400 invalid_request``,
    so the response never reveals another notebook's identifiers.
    """

    def get(self, request, *args, **kwargs):
        from .services.analytics import review as review_service
        from .services.analytics.errors import AnalyticsError

        try:
            return Response(
                review_service.pending_queue(
                    self.get_notebook(),
                    limit=request.query_params.get('limit'),
                ),
            )
        except AnalyticsError as exc:
            return _analytics_error(exc)

    def post(self, request, *args, **kwargs):
        from .services.analytics import review as review_service
        from .services.analytics.errors import AnalyticsError

        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            payload = review_service.apply_review(
                notebook,
                links=body.get('links'),
                topics=body.get('topics'),
                types=body.get('types'),
            )
        except AnalyticsError as exc:
            return _analytics_error(exc)
        return Response(payload)


class NotebookQuestionTopicLinkView(NotebookScopedMixin, APIView):
    """POST: manually assign one of this notebook's topics to one of its questions.

    Body: ``{"question_id", "topic_id", "role": "PRIMARY"|"SECONDARY",
    "confidence": 0..1}``. The link is created/updated as CONFIRMED with
    source ``MANUAL``; any previous PRIMARY link on that question is demoted
    to a rejected SECONDARY row so history is preserved while the
    one-PRIMARY-per-question constraint keeps holding.
    """

    def post(self, request, *args, **kwargs):
        from .services.analytics import review as review_service
        from .services.analytics.errors import AnalyticsError

        notebook = self.get_notebook()
        self.ensure_writable(notebook)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            payload = review_service.assign_link(
                notebook,
                question_id=body.get('question_id'),
                topic_id=body.get('topic_id'),
                role=body.get('role'),
                confidence=body.get('confidence'),
            )
        except AnalyticsError as exc:
            return _analytics_error(exc)
        return Response(
            payload,
            status=(
                status.HTTP_201_CREATED if payload['created']
                else status.HTTP_200_OK
            ),
        )


class NotebookTopicDetailView(NotebookScopedMixin, generics.RetrieveUpdateAPIView):
    """GET/PATCH one topic: read it, or edit name, aliases, notes, status.

    Label collisions inside a notebook surface as DRF 400 field errors
    (names and aliases are unique per notebook).
    """
    serializer_class = NotebookTopicSerializer

    def get_object(self):
        return get_object_or_404(
            NotebookTopic,
            pk=self.kwargs['tid'],
            notebook=self.get_notebook(),
        )

    def perform_update(self, serializer):
        self.ensure_writable(self.get_notebook())
        serializer.save()
