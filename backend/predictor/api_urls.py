"""URL routes for the Phase 2 course-notebook API (`/api/notebooks/`)."""
from django.urls import path

from . import api

app_name = 'notebooks_api'

urlpatterns = [
    # Notebooks (CRUD + archive)
    path('', api.NotebookViewSet.as_view({'get': 'list', 'post': 'create'}),
         name='notebook-list'),
    path('<int:pk>/', api.NotebookViewSet.as_view({
        'get': 'retrieve', 'put': 'update', 'patch': 'partial_update',
        'delete': 'destroy',
    }), name='notebook-detail'),
    path('<int:pk>/archive/', api.NotebookViewSet.as_view({'post': 'archive'}),
         name='notebook-archive'),
    path('<int:pk>/unarchive/', api.NotebookViewSet.as_view({'post': 'unarchive'}),
         name='notebook-unarchive'),

    # Attached syllabus
    path('<int:notebook_pk>/syllabi/', api.NotebookSyllabiListCreateView.as_view(),
         name='notebook-syllabi'),
    path('<int:notebook_pk>/syllabi/upload/', api.NotebookSyllabusUploadView.as_view(),
         name='notebook-syllabus-upload'),
    path('<int:notebook_pk>/syllabi/<int:sid>/',
         api.NotebookSyllabusDetachView.as_view(), name='notebook-syllabus-detach'),
    path('<int:notebook_pk>/syllabi/<int:sid>/file/',
         api.NotebookSyllabusFileView.as_view(), name='notebook-syllabus-file'),

    # Attached exam papers
    path('<int:notebook_pk>/papers/', api.NotebookPapersListCreateView.as_view(),
         name='notebook-papers'),
    path('<int:notebook_pk>/papers/upload/', api.NotebookPaperUploadView.as_view(),
         name='notebook-paper-upload'),
    path('<int:notebook_pk>/papers/<int:pid>/',
         api.NotebookPaperDetachView.as_view(), name='notebook-paper-detach'),
    path('<int:notebook_pk>/papers/<int:pid>/file/',
         api.NotebookPaperFileView.as_view(), name='notebook-paper-file'),

    # Phase 3: exam-paper extraction
    path('<int:notebook_pk>/papers/<int:pid>/process/',
         api.NotebookPaperProcessView.as_view(), name='notebook-paper-process'),
    path('<int:notebook_pk>/papers/<int:pid>/extractions/',
         api.NotebookPaperExtractionListView.as_view(),
         name='notebook-paper-extractions'),
    path(
        '<int:notebook_pk>/papers/<int:pid>/extractions/<int:rid>/',
        api.NotebookPaperExtractionDetailView.as_view(),
        name='notebook-paper-extraction-detail',
    ),
    path(
        '<int:notebook_pk>/papers/<int:pid>/extractions/<int:rid>/chunks/',
        api.NotebookPaperExtractionChunksView.as_view(),
        name='notebook-paper-extraction-chunks',
    ),

    # Phase 3: syllabus extraction
    path('<int:notebook_pk>/syllabi/<int:sid>/process/',
         api.NotebookSyllabusProcessView.as_view(),
         name='notebook-syllabus-process'),
    path('<int:notebook_pk>/syllabi/<int:sid>/extractions/',
         api.NotebookSyllabusExtractionListView.as_view(),
         name='notebook-syllabus-extractions'),
    path(
        '<int:notebook_pk>/syllabi/<int:sid>/extractions/<int:rid>/',
        api.NotebookSyllabusExtractionDetailView.as_view(),
        name='notebook-syllabus-extraction-detail',
    ),
    path(
        '<int:notebook_pk>/syllabi/<int:sid>/extractions/<int:rid>/chunks/',
        api.NotebookSyllabusExtractionChunksView.as_view(),
        name='notebook-syllabus-extraction-chunks',
    ),

    # Phase 4: retrieval over this notebook's indexed sources
    path('<int:notebook_pk>/search/', api.NotebookSearchView.as_view(),
         name='notebook-search'),

    # Phase 5: deterministic course analytics + label review queue
    path('<int:notebook_pk>/analytics/', api.NotebookAnalyticsView.as_view(),
         name='notebook-analytics'),
    path('<int:notebook_pk>/analytics/topics/<int:tid>/',
         api.NotebookTopicAnalyticsView.as_view(),
         name='notebook-analytics-topic'),
    path('<int:notebook_pk>/analytics/proposals/',
         api.NotebookAnalyticsProposalsView.as_view(),
         name='notebook-analytics-proposals'),
    path('<int:notebook_pk>/analytics/review/',
         api.NotebookAnalyticsReviewView.as_view(),
         name='notebook-analytics-review'),
    path('<int:notebook_pk>/analytics/links/',
         api.NotebookQuestionTopicLinkView.as_view(),
         name='notebook-analytics-links'),

    # Questions
    path('<int:notebook_pk>/questions/', api.NotebookQuestionListView.as_view(),
         name='notebook-questions'),
    path('<int:notebook_pk>/questions/<int:qid>/',
         api.NotebookQuestionDetailView.as_view(), name='notebook-question-detail'),

    # Canonical notebook topics
    path('<int:notebook_pk>/topics/', api.NotebookTopicListCreateView.as_view(),
         name='notebook-topics'),
    path('<int:notebook_pk>/topics/<int:tid>/',
         api.NotebookTopicDetailView.as_view(), name='notebook-topic-detail'),

    # Chat sessions + messages
    path('<int:notebook_pk>/chat/sessions/',
         api.NotebookChatSessionListCreateView.as_view(),
         name='notebook-chat-sessions'),
    path('<int:notebook_pk>/chat/sessions/<int:sid>/',
         api.NotebookChatSessionDetailView.as_view(),
         name='notebook-chat-session-detail'),
    path('<int:notebook_pk>/chat/sessions/<int:sid>/messages/',
         api.NotebookChatMessageListCreateView.as_view(),
         name='notebook-chat-messages'),

    # Phase 7: practice-question generation
    path('<int:notebook_pk>/generation/requests/',
         api.NotebookGenerationRequestListCreateView.as_view(),
         name='notebook-generation-requests'),
    path('<int:notebook_pk>/generation/requests/<int:rid>/',
         api.NotebookGenerationRequestDetailView.as_view(),
         name='notebook-generation-request-detail'),
    path('<int:notebook_pk>/generation/questions/<int:qid>/',
         api.NotebookGeneratedQuestionDetailView.as_view(),
         name='notebook-generated-question-detail'),
]
