"""PostgreSQL + pgvector schema helpers for the RAG layer.

This module owns every piece of vector-store DDL and the read gate that
decides whether a query may run at all: only PostgreSQL ever stores or
queries a vector (``models.DynamicVectorField`` merely picks the column type).
Indexing, retrieval and the API call these helpers and react to the errors
they raise, so the SQLite dev/test workflow keeps working unchanged.

Two responsibilities:

* :func:`ensure_extension` + :func:`ensure_vector_schema` -- idempotent DDL:
  pgvector extension, table, column type and HNSW index, plus a self-healing
  rebuild when ``EMBEDDING_DIMENSION`` changed. The rebuild only ever drops
  *vectors* (regenerable), never ``DocumentChunk`` rows or their text. Called
  from migration ``0013_phase4_rag``, from ``post_migrate`` (so a SQLite ->
  PostgreSQL switch is repaired on the next ``migrate``) and from the
  indexing path before any write.
* :func:`require_ready` -- read-only introspection used by retrieval to fail
  fast with a clear error instead of sending a doomed query.

Schema facts this module relies on (verified against pgvector 0.8.x):
``vector(N)`` rejects a wrong number of dimensions on insert, HNSW indexes
only work on a dimensioned column, and an existing column cannot be cast
between dimensions while it holds rows -- hence "delete vectors, then alter".
"""

import logging

from django.conf import settings
from django.db import connection

from .errors import DimensionMismatch, VectorBackendUnavailable

logger = logging.getLogger(__name__)

# Outcome labels returned by ensure_vector_schema().
RESULT_SKIPPED = 'skipped'
RESULT_OK = 'ok'
RESULT_CREATED = 'created'
RESULT_ALTERED = 'altered'

# Embedding bookkeeping columns that become meaningless when vectors are
# dropped. `text`, provenance and metadata are never touched.
_STALE_EMBEDDING_STATUSES = ('EMBEDDED', 'FAILED')

_HNSW_INDEX_NAME = 'predictor_documentchunkembedding_hnsw_idx'


def is_postgres() -> bool:
    return connection.vendor == 'postgresql'


def extension_present() -> bool:
    if not is_postgres():
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        return bool(cursor.fetchone()[0])


def vector_backend_available() -> bool:
    """True when this connection can store and query pgvector columns."""
    if not is_postgres():
        return False
    try:
        return extension_present()
    except Exception:  # pragma: no cover - unreachable in the SQLite suite
        logger.warning('Could not check the pgvector extension', exc_info=True)
        return False


def column_dimensions(table):
    """Return the declared dimension of the `embedding` column, else None."""
    if not is_postgres():
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = to_regclass(%s) AND attname = %s AND NOT attisdropped",
            [table, 'embedding'],
        )
        row = cursor.fetchone()
    if row is None or row[0] is None or row[0] < 0:
        return None
    return int(row[0])


def vector_status(model=None):
    """Read-only snapshot of the vector store for one embedding model."""
    model = model or _embedding_model()
    table = model._meta.db_table
    status = {
        'backend': 'postgresql' if is_postgres() else connection.vendor,
        'extension': False,
        'table': False,
        'column_dimensions': None,
        'configured_dimensions': int(settings.EMBEDDING_DIMENSION),
        'ready': False,
    }
    if not is_postgres():
        return status
    try:
        status['extension'] = extension_present()
        dims = column_dimensions(table)
    except Exception:  # pragma: no cover - defensive, never breaks a caller
        logger.warning('Could not introspect the vector schema', exc_info=True)
        return status
    if dims is None:
        return status
    status['table'] = True
    status['column_dimensions'] = dims
    status['ready'] = status['extension'] and dims == status['configured_dimensions']
    return status


def require_ready(model=None, *, dimensions=None):
    """Validate the vector store for a read; return the column dimension.

    Raises :class:`VectorBackendUnavailable` when PostgreSQL + pgvector is
    missing and :class:`DimensionMismatch` when the column was built for a
    different ``EMBEDDING_DIMENSION`` than the one configured now.
    """
    model = model or _embedding_model()
    expected = int(dimensions or settings.EMBEDDING_DIMENSION)
    if not is_postgres():
        raise VectorBackendUnavailable('Vector search requires PostgreSQL.')
    if not extension_present():
        raise VectorBackendUnavailable(
            'The pgvector extension is not available on this database.'
        )
    stored = column_dimensions(model._meta.db_table)
    if stored is None:
        raise VectorBackendUnavailable(
            'The embedding table does not exist yet.',
            hint='Run `python3 manage.py migrate` to create it.',
        )
    if stored != expected:
        raise DimensionMismatch(
            f'Vector column has {stored} dimensions but EMBEDDING_DIMENSION is '
            f'{expected}.'
        )
    return stored


def ensure_extension():
    """Create the pgvector extension when it is missing. PostgreSQL only.

    Called on its own from migration ``0013_phase4_rag`` *before* the
    embedding table is created: ``CREATE TABLE ... vector(N)`` fails while the
    type does not exist yet.
    """
    if not is_postgres():
        return False
    with connection.cursor() as cursor:
        try:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
        except Exception as exc:
            raise VectorBackendUnavailable(
                'Could not enable the pgvector extension.',
                hint='Enable it as a superuser with '
                     '`CREATE EXTENSION IF NOT EXISTS vector`.',
            ) from exc
    return True


def ensure_vector_schema(model=None, *, editor=None, dimensions=None):
    """Create or repair the pgvector table for ``model``. PostgreSQL only.

    Returns one of ``created`` / ``altered`` / ``ok`` / ``skipped``. Pass the
    schema editor of an in-flight migration to reuse its transaction; otherwise
    a private one is opened.
    """
    model = model or _embedding_model()
    dims = int(dimensions or settings.EMBEDDING_DIMENSION)
    if not is_postgres():
        return RESULT_SKIPPED
    if editor is not None:
        return _ensure(model, editor, dims)
    with connection.schema_editor(atomic=True) as own_editor:
        return _ensure(model, own_editor, dims)


def _ensure(model, editor, dims):
    table = model._meta.db_table
    ensure_extension()
    with connection.cursor() as cursor:
        stored = column_dimensions(table)
        if stored is None:
            editor.create_model(model)
            _create_hnsw_index(cursor, table)
            logger.info(
                'RAG vector table %s created at %d dimensions', table, dims
            )
            return RESULT_CREATED
        if stored == dims:
            _create_hnsw_index(cursor, table)
            return RESULT_OK
        _reproject(model, editor, cursor, table, dims, stored)
        return RESULT_ALTERED


def _reproject(model, editor, cursor, table, dims, stored):
    """Rebuild the vector column for a new configured dimension.

    Vectors cannot be cast between dimensions, so the rows are dropped (they
    are reproducible) and every chunk is queued for re-embedding. Source text
    and provenance on ``DocumentChunk`` are untouched.
    """
    from ...models import DocumentChunk

    logger.warning(
        'RAG vector column %s holds %d dimensions but EMBEDDING_DIMENSION is '
        '%d; dropping vectors and rebuilding the column.',
        table, stored, dims,
    )
    quoted = connection.ops.quote_name(table)
    _flush_deferred_triggers(cursor, table)
    cursor.execute(f'DELETE FROM {quoted}')
    cursor.execute(
        f'ALTER TABLE {quoted} '
        f'ALTER COLUMN {connection.ops.quote_name("embedding")} '
        f'TYPE vector(%s)',
        [dims],
    )
    _create_hnsw_index(cursor, table)
    queued = DocumentChunk.objects.filter(
        embedding_status__in=_STALE_EMBEDDING_STATUSES
    ).update(
        embedding_status=DocumentChunk.STATUS_PENDING,
        embedding_error='',
        embedding_model='',
        embedding_dim=None,
        embedded_at=None,
    )
    logger.warning(
        'RAG vectors rebuilt for %s; %d chunk(s) queued for re-embedding.',
        table, queued,
    )


def _flush_deferred_triggers(cursor, table):
    """Fire this table's queued DEFERRED FK triggers now.

    Django foreign keys are ``DEFERRABLE INITIALLY DEFERRED``, so INSERTs and
    DELETEs queue trigger events until COMMIT -- and PostgreSQL refuses both
    ``CREATE INDEX`` and ``ALTER TABLE ... TYPE`` while any exist. Making the
    constraints immediate runs those checks straight away (they pass: the rows
    are valid), which keeps the whole repair inside the caller's transaction.
    """
    cursor.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = %s::regclass AND contype = 'f' AND condeferrable",
        [table],
    )
    names = [row[0] for row in cursor.fetchall()]
    if not names:
        return
    cursor.execute(
        'SET CONSTRAINTS %s IMMEDIATE'
        % ', '.join(connection.ops.quote_name(name) for name in names)
    )


def _create_hnsw_index(cursor, table):
    """Create the cosine HNSW index when it is missing.

    Probe ``pg_indexes`` first instead of relying on ``IF NOT EXISTS``:
    PostgreSQL refuses *any* ``CREATE INDEX`` on a table that has queued
    trigger events, which is exactly the state ``embed_pending`` leaves the
    embedding table in right after writing vectors in the same transaction.
    An aborted statement would also poison the surrounding test/migration
    transaction, so the index must never be attempted when it already exists.
    """
    cursor.execute(
        'SELECT 1 FROM pg_indexes WHERE indexname = %s', [_HNSW_INDEX_NAME]
    )
    if cursor.fetchone():
        return False
    _flush_deferred_triggers(cursor, table)
    cursor.execute(
        f'CREATE INDEX IF NOT EXISTS {_HNSW_INDEX_NAME} '
        f'ON {connection.ops.quote_name(table)} '
        f'USING hnsw (embedding vector_cosine_ops)'
    )
    return True


def _embedding_model():
    from ...models import DocumentChunkEmbedding

    return DocumentChunkEmbedding


def ensure_on_migrate(sender, **kwargs):
    """``post_migrate`` hook: keep the vector schema in step with settings.

    Repairs a database that was migrated before pgvector/PostgreSQL was
    configured, and rebuilds the column after an ``EMBEDDING_DIMENSION``
    change. Never raises -- a schema hiccup must not fail ``migrate``.
    """
    try:
        ensure_vector_schema()
    except VectorBackendUnavailable as exc:
        logger.warning('RAG vector schema not ready: %s', exc.message)
    except Exception:  # pragma: no cover - defensive
        logger.warning('Could not ensure the RAG vector schema', exc_info=True)
