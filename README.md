# ChapterScope AI

ChapterScope AI is a course-oriented exam-intelligence platform. A user creates
a private course notebook, uploads syllabi and previous-year papers, extracts
traceable questions, reviews normalized topics, studies deterministic
analytics, searches source material, chats over retrieved evidence, and
generates validated practice questions.

The repository is an incremental modernization of an older EduQuantum/VQE
application. It currently contains a **canonical Django application**, a
separate **legacy FastAPI reporting service**, and a shared **React frontend**.
They are related products in one repository, but they do not share the same
database or business workflow.

---

## 1. System architecture

```mermaid
flowchart TB
    Browser["User browser"]
    React["React + TypeScript frontend<br/>frontend :3000"]

    subgraph Django["Canonical ChapterScope backend :8000"]
        DjangoURLs["Django root URLs"]
        Auth["Session auth + CSRF"]
        NotebookAPI["Notebook REST API<br/>/api/notebooks/*"]
        LegacyViews["Legacy server-rendered views<br/>/exams, /syllabi, /predictions"]
        Extraction["Extraction services"]
        RAG["RAG indexing + retrieval"]
        Analytics["Deterministic analytics"]
        Chat["Source-grounded chat"]
        Generation["Practice-question generation"]
        DjangoDB["Django database<br/>SQLite or PostgreSQL"]
        Media["MEDIA_ROOT<br/>uploaded documents"]
    end

    subgraph FastAPI["Legacy reporting backend :8001"]
        FastAPIApp["FastAPI application"]
        ReportsAPI["Reports router<br/>/api/reports/*"]
        PredictionAPI["Prediction API<br/>/api/v1/*"]
        ReportServices["Report, visualization,<br/>export, VQE services"]
        ReportsDB["SQLAlchemy reports database"]
    end

    Providers["Optional Google Gemini APIs"]
    Vector["PostgreSQL + pgvector<br/>optional vector storage"]

    Browser --> React
    React -->|relative /api/* through CRA proxy| Django
    React -->|REACT_APP_REPORTS_API_URL| FastAPI
    DjangoURLs --> Auth
    DjangoURLs --> NotebookAPI
    DjangoURLs --> LegacyViews
    NotebookAPI --> Extraction
    NotebookAPI --> RAG
    NotebookAPI --> Analytics
    NotebookAPI --> Chat
    NotebookAPI --> Generation
    Extraction --> Media
    Extraction --> DjangoDB
    RAG --> DjangoDB
    RAG -. vectors only .-> Vector
    Analytics --> DjangoDB
    Chat --> RAG
    Generation --> RAG
    Chat -. model .-> Providers
    Generation -. model .-> Providers
    Extraction -. optional OCR/LLM .-> Providers
    Analytics -. optional label proposals .-> Providers
    FastAPIApp --> ReportsAPI
    FastAPIApp --> PredictionAPI
    ReportsAPI --> ReportServices
    PredictionAPI --> ReportServices
    ReportServices --> ReportsDB
```

### Runtime responsibilities

| Component | Directory | Default port | Responsibility |
|---|---|---:|---|
| React frontend | `frontend/` | 3000 | Browser UI, routing, API clients, session-aware screens |
| Django backend | `backend/` | 8000 | Canonical users, notebooks, documents, extraction, RAG, analytics, chat, generation |
| FastAPI backend | `src/` | 8001 when run beside Django | Legacy reports, demo predictions, training, exports, visualizations |
| Django database | `backend/db.sqlite3` or `DATABASE_URL` | — | Users and all ChapterScope notebook data |
| Reports database | `data/reports.db` or `DATABASE_URL` | — | Legacy FastAPI report records |
| Uploaded files | `backend/media/` | — | Syllabi, exam papers, and source files; ignored by Git |
| Vector database | PostgreSQL + pgvector | 5432 | Optional embedding vectors for RAG |

The Django and FastAPI services are separate processes. They must not be
started on the same port. The React development server proxies relative
requests to Django on port `8000`; legacy report requests use the explicit
FastAPI URL configured by `REACT_APP_REPORTS_API_URL`.

---

## 2. Frontend architecture

### Entry points and routing

- `frontend/src/index.tsx` mounts the React application.
- `frontend/src/App.tsx` defines routes and wraps the app in `AuthProvider`.
- `ProtectedRoute` redirects unauthenticated users to `/login`.
- `Navigation.tsx` provides shared navigation.

### Main screens

| Route | Component | Backend |
|---|---|---|
| `/login` | `components/Login.tsx` | Django auth |
| `/` | `pages/Dashboard.tsx` | FastAPI legacy reports |
| `/reports/create` | `pages/CreateReport.tsx` | FastAPI legacy reports |
| `/reports/:id` | `pages/ReportDetail.tsx` | FastAPI legacy reports |
| `/notebooks` | `pages/Notebooks.tsx` | Django notebook API |
| `/notebooks/:id` | `pages/NotebookDetail.tsx` | Django notebook API |
| `/notebooks/:id/practice` | `pages/NotebookPractice.tsx` | Django generation API |
| `/notebooks/:id/generated/:qid` | `pages/GeneratedQuestionDetail.tsx` | Django generation API |

Notebook detail tabs are implemented by:

- `NotebookSources.tsx` — syllabi, papers, upload, processing
- `NotebookQuestionBank.tsx` — extracted questions and filters
- `NotebookAnalytics.tsx` — deterministic metrics and review queue
- `NotebookChat.tsx` — sessions, messages, source citations

### API clients

- `services/notebooks.ts` — relative Axios client for Django notebook APIs;
  handles CSRF bootstrap and session cookies.
- `services/analytics.ts` — typed wrapper around notebook analytics routes.
- `services/chat.ts` — typed wrapper around notebook chat routes.
- `services/generation.ts` — typed wrapper around practice-question routes.
- `services/api.ts` — legacy report client; uses
  `REACT_APP_REPORTS_API_URL` and calls `/api/reports/*`.
- `contexts/AuthContext.tsx` — login, registration, logout, and session
  validation against Django `/api/auth/*`.

Only `REACT_APP_*` variables are bundled into the browser. Never put database
URLs, Django `SECRET_KEY`, or `GEMINI_API_KEY` in frontend environment files.

---

## 3. Django backend architecture

The Django project lives in `backend/`.

```text
backend/
├── manage.py
├── eduquantum/
│   ├── settings.py       Environment-driven Django configuration
│   ├── urls.py           Root URLs and API includes
│   ├── db_url.py         DATABASE_URL parser
│   └── wsgi.py
└── predictor/
    ├── models.py         Domain models
    ├── api.py            Notebook REST views
    ├── api_urls.py       Notebook REST routes
    ├── serializers.py    DRF request/response schemas
    ├── permissions.py    Authentication and notebook ownership checks
    ├── views.py          Legacy server-rendered pages and auth endpoints
    ├── urls.py            Legacy HTML routes
    ├── forms.py          Legacy upload/forms
    ├── admin.py          Django admin registration
    ├── migrations/       Additive database migrations
    ├── services/
    ├── utils/             PDF and DOCX extraction helpers
    └── tests/
```

`predictor/apps.py` registers a `post_migrate` hook that keeps the optional
pgvector schema synchronized with `EMBEDDING_DIMENSION`.

### Django URL layers

`backend/eduquantum/urls.py` combines three URL families:

1. `/admin/` — Django admin.
2. Legacy HTML routes from `predictor/urls.py`:
   `/exams/`, `/syllabi/`, `/predictions/`, and topic analysis pages.
3. JSON routes under `/api/`:
   - `/api/health/`
   - `/api/auth/*`
   - `/api/dashboard-data/`
   - `/api/notebooks/*`

The notebook API is the canonical API for new ChapterScope functionality.

---

## 4. Django data model

The main model relationship is:

```mermaid
erDiagram
    USER ||--o{ COURSE_NOTEBOOK : owns
    COURSE_NOTEBOOK ||--o{ SYLLABUS : contains
    COURSE_NOTEBOOK ||--o{ EXAM_PAPER : contains
    EXAM_PAPER ||--o{ QUESTION : contains
    QUESTION ||--o{ QUESTION_TOPIC : classified_as
    NOTEBOOK_TOPIC ||--o{ QUESTION_TOPIC : labels
    EXAM_PAPER ||--o{ EXTRACTION_RUN : processed_by
    SYLLABUS ||--o{ EXTRACTION_RUN : processed_by
    EXTRACTION_RUN ||--o{ EXTRACTION_CHUNK : produces
    EXTRACTION_RUN ||--o{ QUESTION : extracts
    EXTRACTION_CHUNK ||--o{ DOCUMENT_CHUNK : indexed_as
    QUESTION ||--o{ DOCUMENT_CHUNK : indexed_as
    EXAM_PAPER ||--o{ DOCUMENT_CHUNK : indexed_as
    DOCUMENT_CHUNK ||--o| DOCUMENT_CHUNK_EMBEDDING : embeds
    COURSE_NOTEBOOK ||--o{ CHAT_SESSION : contains
    CHAT_SESSION ||--o{ CHAT_MESSAGE : contains
    COURSE_NOTEBOOK ||--o{ GENERATION_REQUEST : receives
    GENERATION_REQUEST ||--o{ GENERATED_QUESTION : creates
```

### Core entities

- `CourseNotebook` — owner-scoped course boundary. It has `ACTIVE` and
  `ARCHIVED` states. Archived notebooks are read-only for content writes.
- `Syllabus` — uploaded course syllabus. Its `notebook` relation is nullable
  to preserve legacy unassigned records.
- `ExamPaper` — uploaded previous-year paper. Its `notebook` relation is also
  nullable for legacy compatibility.
- `Question` — extracted or manually entered question. It stores the paper,
  notebook, year, numbering, raw/normalized text, marks, page provenance,
  extraction status, confidence, and source references.
- `NotebookTopic` — canonical topic name and aliases within one notebook.
- `QuestionTopic` — question-to-topic link with role, confidence, source, and
  review status.
- `ExtractionRun` / `ExtractionChunk` — processing metadata and source text.
- `DocumentChunk` — portable RAG text and provenance.
- `DocumentChunkEmbedding` — PostgreSQL vector stored separately from chunk
  text; SQLite never stores/query vectors.
- `ChatSession` / `ChatMessage` — notebook-scoped conversation history and safe
  provenance metadata.
- `GenerationRequest` / `GeneratedQuestion` — practice-question requests,
  generated drafts, validation status, and source references.

Legacy `Topic`, `Prediction`, and older document relations remain for backward
compatibility. Do not remove them while modifying the newer notebook workflow.

### Ownership and isolation

Every notebook API resolves the notebook through the authenticated owner. Child
queries are then filtered by that notebook. Foreign notebook IDs return `404`.
RAG indexing and retrieval must also preserve notebook scope; retrieved text is
treated as untrusted data and never as an instruction.

---

## 5. Document ingestion and extraction flow

```mermaid
sequenceDiagram
    participant UI as React
    participant API as Django API
    participant DB as Django DB
    participant FS as MEDIA_ROOT
    participant V as Validation
    participant T as Text extraction
    participant O as Optional OCR
    participant P as Question parser
    participant R as RAG index

    UI->>API: Multipart upload
    API->>V: Validate extension, magic bytes, size, path
    API->>FS: Store file
    API->>DB: Create document metadata
    UI->>API: POST /process/
    API->>DB: Create or reuse ExtractionRun
    API->>T: Extract PDF, DOCX, or TXT text
    T->>O: OCR low-text pages when configured
    T->>P: Parse numbered questions and subparts
    P->>DB: Store ExtractionChunk and Question rows
    P->>DB: Set status and provenance
    API->>R: Optional automatic indexing
    API-->>UI: Run status, counts, warnings, sources
```

The pipeline is synchronous and deterministic-first:

1. Validate the file and restrict paths to `MEDIA_ROOT`.
2. Reuse `predictor/utils/pdf_extractor.py` and `docx_extractor.py`.
3. Reconstruct page and character boundaries into extraction chunks.
4. Parse top-level questions, subparts, MCQ options, marks, and basic types.
5. Use OCR only when configured and available.
6. Optionally use Gemini structured fallback after deterministic parsing.
7. Upsert questions using `(exam_paper, parent_number, question_number)`.
8. Preserve manual and needs-review questions when replacing stale extraction.
9. Report `OCR_REQUIRED`, `FAILED`, or `NEEDS_REVIEW` honestly; never fabricate
   questions from unreadable documents.

Run statuses are:

```text
PENDING → PROCESSING → PROCESSED
                    ├→ NEEDS_REVIEW
                    ├→ OCR_REQUIRED
                    └→ FAILED
```

---

## 6. RAG architecture

RAG is implemented in `backend/predictor/services/rag/`:

```text
errors.py       Stable API error codes
schema.py       pgvector schema creation and repair
embeddings.py   Provider abstraction and Gemini embeddings
indexing.py     Notebook-scoped chunk synchronization and embedding
retrieval.py    Notebook-scoped dense/keyword retrieval
```

### Indexing

Sources become stable chunk keys:

| Source | Key pattern |
|---|---|
| Syllabus passage | `syl:<id>:c:<index>` |
| Question text | `q:<id>:c:<index>` |
| Exam paper passage | `p:<id>:c:<index>` |

`content_hash` prevents re-embedding unchanged text. `DocumentChunk` stores
portable text/provenance. `DocumentChunkEmbedding` stores vectors only on
PostgreSQL with pgvector and HNSW indexing.

Indexing can run automatically after extraction or manually:

```bash
cd backend
python3 manage.py index_rag
python3 manage.py index_rag --notebook 3
python3 manage.py index_rag --sync-only
python3 manage.py index_rag --reset-vectors
python3 manage.py index_rag --strict
```

### Retrieval

Retrieval always receives a notebook ID and filters candidate rows in SQL.
Results contain source keys, document/question references, page/year metadata,
snippets, similarity/score, and `untrusted: true`.

No results are returned as a normal `200` insufficient-evidence response.
Provider, dimension, vector-backend, quota, and timeout failures are translated
to stable machine-readable API errors.

---

## 7. Analytics architecture

Analytics lives in `backend/predictor/services/analytics/`:

```text
catalog.py    Topic catalog and normalized aliases
labels.py     Label normalization and validation
metrics.py    SQL/ORM measures
ranking.py    Weighted ranking
proposer.py   Optional Gemini label proposals
classify.py   Deterministic and proposed classifications
review.py     Confirm/reject review actions
errors.py     Analytics error taxonomy
```

All historical values are calculated from ORM rows. The LLM cannot provide
counts, marks, prevalence, slopes, or rankings. Metrics exclude failed
questions and count only confirmed topic links.

Important measures include:

- paper prevalence
- question share
- weighted and primary question counts
- raw and normalized marks
- recent and long-term frequency
- per-year trend slope
- syllabus importance
- question-type distribution

The resulting `score` is a ranking aid, not an exam prediction or guarantee.

---

## 8. Chat architecture

Chat is implemented in `backend/predictor/services/chat/`:

```text
pipeline.py    Ordered source-grounded turn workflow
context.py     Bounded notebook history and retrieval context
prompts.py     Delimited system and user messages
model.py       Lazy ChatGoogleGenerativeAI factory and error mapping
schema.py      Strict model response contract
errors.py      Stable chat error codes
```

The pipeline order is deliberate:

1. Validate the user message before writing.
2. Resolve configuration and model availability.
3. Load bounded recent history.
4. Persist the user message.
5. Retrieve notebook-scoped evidence.
6. Make one LangChain `ChatGoogleGenerativeAI` call.
7. Validate and filter model citations against actual retrieval rows.
8. Persist only a grounded assistant answer.

If retrieval is empty, citations are invalid, or the model reports insufficient
evidence, the fixed insufficient-evidence response is used. Provider payloads,
prompts, hidden reasoning, and retrieved text are not logged.

---

## 9. Practice-question generation

Generation is implemented in `backend/predictor/services/generation/`:

```text
pipeline.py    Request validation, context, model call, persistence
context.py     Notebook evidence selection
prompts.py     LangChain system/human messages
model.py       Lazy ChatGoogleGenerativeAI factory
validation.py  Question schema and output validation
math_checks.py Formula/numerical consistency checks
schema.py      Request/result structures
errors.py      Stable generation errors
```

The service:

1. Validates count, topic, difficulty, marks, year bounds, and language.
2. Builds bounded notebook context from retrieved/indexed source material.
3. Calls the configured model using a strict JSON contract.
4. Validates question text, answers, marks, type, and source references.
5. Runs mathematical checks when applicable.
6. Stores generated questions as drafts with validation/provenance state.

Generated content is never treated as authoritative source material.

---

## 10. Legacy FastAPI architecture

The FastAPI service under `src/` is independent from Django:

```text
src/
├── api/
│   ├── main.py       Prediction, topics, training, health, data routes
│   └── reports.py    CRUD, generation, data, visualization, export routes
├── cli/main.py       Command-line prediction entry point
├── config/
│   ├── settings.py   Pydantic settings
│   ├── database.py   SQLAlchemy database setup
│   └── logging.py    File/application logging
├── models/
│   └── database.py   SQLAlchemy report models
└── services/
    ├── report_service.py
    ├── data_loader.py
    ├── visualization_service.py
    ├── export_service.py
    └── vqe_predictor.py
```

Routes are mounted as:

- `/api/v1/predict`
- `/api/v1/topics`
- `/api/v1/train`
- `/api/v1/health`
- `/api/v1/data/*`
- `/api/reports/*`

This service powers the older report screens. Its historical prediction data
contains demo/mock behavior and is not the source of truth for notebook
analytics or RAG.

---

## 11. Authentication and request flow

```mermaid
sequenceDiagram
    participant Browser
    participant React
    participant Django
    participant DB

    Browser->>React: Open application
    React->>Django: GET /api/auth/validate/
    Django->>DB: Resolve session user
    Django-->>React: User or unauthenticated response
    Browser->>React: Submit login
    React->>Django: POST /api/auth/login/
    Django->>DB: Authenticate user
    Django-->>Browser: Session cookie
    React->>Django: GET /api/auth/csrf-token/
    Django-->>React: CSRF token
    React->>Django: Authenticated write + X-CSRFToken
    Django->>DB: Owner-scoped mutation
    Django-->>React: JSON response
```

The session cookie is authoritative. The legacy `token` field returned by older
auth endpoints is not a bearer credential. Django APIs use session
authentication, CSRF for writes, and owner-scoped lookups.

---

## 12. Configuration

Backend template: `backend/.env.example`

Frontend template: `frontend/.env.example`

### Backend settings

| Variable group | Purpose |
|---|---|
| `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS` | Django runtime and production fail-safe |
| `DATABASE_URL` | SQLite, PostgreSQL, or MySQL connection |
| `GEMINI_API_KEY` | Optional provider access |
| `MAX_FILE_SIZE`, `ALLOWED_FILE_TYPES` | Upload validation |
| `EXTRACTION_*`, `OCR_ENGINE` | Extraction limits and OCR |
| `EMBEDDING_*`, `RAG_*` | Embedding and retrieval tuning |
| `ANALYTICS_*`, `TOPIC_LLM_*` | Analytics limits and label proposals |
| `CHAT_*` | Chat provider, context, and response limits |
| `GENERATION_*` | Practice-question generation limits |

### Frontend settings

```env
# Legacy FastAPI report service
REACT_APP_REPORTS_API_URL=http://localhost:8001

# Optional browser-visible UI flags
REACT_APP_ENABLE_DEBUG=true
```

Notebook and authentication clients use relative URLs and the CRA proxy to
Django. Do not set notebook clients to the FastAPI host.

---

## 13. Running the project

### Django and React

```bash
source hybrid-venv/bin/activate
cp backend/.env.example backend/.env

cd backend
python3 manage.py migrate
python3 manage.py runserver 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm start
```

Open <http://localhost:3000>.

### FastAPI reports

Run FastAPI separately on `8001` when Django is already using `8000`:

```bash
PYTHONPATH=. uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8001
```

Health checks:

```bash
curl http://localhost:8000/api/health/
curl http://localhost:8001/api/v1/health
```

### PostgreSQL and pgvector

```bash
docker compose up -d postgres
cd backend
DATABASE_URL=postgresql://chapterscope:chapterscope_dev@localhost:5432/chapterscope \
  python3 manage.py migrate
```

Use PostgreSQL for vector-backed retrieval tests. SQLite is sufficient for
portable model, API, extraction, analytics, chat-contract, and generation
tests; provider calls are faked in tests.

---

## 14. Tests and checks

```bash
# FastAPI and shared tests
pytest -q

# Django
cd backend
python3 manage.py check
python3 manage.py test predictor
python3 manage.py makemigrations --check --dry-run

# Frontend
cd frontend
npm run build
npm test

# FastAPI formatting and linting
make format
make lint
```

PostgreSQL-specific tests are skipped on SQLite and must be run separately with
the pgvector database. Live Gemini calls are not used by the test suite.

---

## 15. Repository structure

```text
backend/                 Canonical Django backend
  eduquantum/            Settings, database URL parser, root URLs
  predictor/
    models.py            Notebook and legacy domain models
    api.py               Notebook REST implementation
    serializers.py       API schemas
    permissions.py       Ownership/auth rules
    services/
      extraction/        File validation, text, OCR, parsing, persistence
      rag/               Chunking, embeddings, indexing, retrieval
      analytics/          Metrics, ranking, labels, review
      chat/              Source-grounded LangChain chat
      generation/        Validated LangChain practice-question generation
    tests/               Django test suite and provider fakes
frontend/                React + TypeScript UI
src/                     Independent FastAPI legacy service
tests/                   FastAPI tests
data/                    Sample CSV and local report database location
docs/                    Phase notes and transcripts
scripts/                 Project/spec workflow helpers
docker-compose.yml       Local PostgreSQL + pgvector
```

---

## 16. Design rules for future changes

1. Add new course functionality to the Django notebook architecture; do not
   duplicate it in FastAPI.
2. Keep every notebook query owner-scoped and notebook-filtered.
3. Preserve source references when extracting, retrieving, chatting, or
   generating.
4. Treat uploaded documents, retrieved text, and model output as untrusted
   data.
5. Keep analytics deterministic; models may propose labels but may not invent
   historical values.
6. Translate provider failures into stable API errors at the provider boundary.
7. Keep migrations additive and preserve legacy nullable notebook relations.
8. Never commit secrets, uploads, local databases, logs, caches, virtual
   environments, or generated tooling output.
9. Add focused tests for every new behavior and run the relevant backend,
   frontend, and PostgreSQL checks when applicable.
10. Keep the README and `.env.example` files synchronized with actual routes,
    ports, providers, and configuration.
