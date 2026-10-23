"""Dense (+ optional keyword) retrieval over one notebook's chunks.

Read-only and permission-safe by construction: the SQL always filters on
``c.notebook_id``, and the caller resolves that notebook owner-scoped, so a
foreign notebook id can never widen the result set.

The pipeline is deterministic:

1. validate the query and filters (never trust them),
2. embed the query with the *query* task type,
3. verify the vector store is usable and dimensionally consistent,
4. fetch a bounded candidate pool with pgvector cosine distance,
5. optionally fetch keyword candidates with full-text ranking,
6. fuse the rankings with reciprocal-rank fusion (or rank dense only),
7. return the top N with their source references.

Failures surface as :mod:`predictor.services.rag.errors.RAGError` with a
stable code. No query text, snippet or file name is ever written to the log.
"""

import json
import logging
import re
import time
from collections import defaultdict

from django.conf import settings
from django.db import connection, transaction

from ...models import (
    MAX_EXAM_YEAR,
    CourseNotebook,
    DocumentChunk,
    DocumentChunkEmbedding,
)
from . import embeddings, schema
from .errors import (
    InvalidQuery,
    RAGError,
    RetrievalTimeout,
    VectorBackendUnavailable,
)

logger = logging.getLogger(__name__)

_SNIPPET_TERMS = 10


def _int_setting(name, default):
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def _float_setting(name, default):
    try:
        return float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def validate_params(
    query, *, source_type=None, year=None, topic=None, limit=None
) -> dict:
    """Normalize and range-check every caller-supplied parameter."""
    cleaned = (query or '').strip()
    if not cleaned:
        raise InvalidQuery('Missing search query: provide the `q` parameter.')
    max_chars = _int_setting('RAG_MAX_QUERY_CHARS', 500)
    embed_cap = _int_setting('EMBEDDING_MAX_TEXT_CHARS', 0)
    if embed_cap > 0:
        # A query the embedding layer would refuse later must fail here, as
        # invalid input, instead of surfacing as a provider error.
        max_chars = min(max_chars, embed_cap)
    if len(cleaned) > max_chars:
        raise InvalidQuery(
            f'Search query is {len(cleaned)} characters; the limit is {max_chars}.'
        )

    if source_type is not None:
        source_type = str(source_type).strip().upper()
        if source_type not in dict(DocumentChunk.SOURCE_CHOICES):
            allowed = ', '.join(value for value, _ in DocumentChunk.SOURCE_CHOICES)
            raise InvalidQuery(
                f'Unknown source_type {source_type!r}; expected one of {allowed}.'
            )

    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            raise InvalidQuery('The `year` filter must be an integer.')
        if year < 1900 or year > MAX_EXAM_YEAR:
            raise InvalidQuery(
                f'The `year` filter must be between 1900 and {MAX_EXAM_YEAR}.'
            )

    if topic is not None:
        topic = ' '.join(str(topic).split())
        if not topic:
            topic = None

    top_k = _int_setting('RAG_TOP_K', 8)
    max_top_k = _int_setting('RAG_MAX_TOP_K', 20)
    if limit is None:
        limit = top_k
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise InvalidQuery('The `limit` parameter must be an integer.')
    if limit < 1 or limit > max_top_k:
        raise InvalidQuery(
            f'The `limit` parameter must be between 1 and {max_top_k}.'
        )

    return {
        'query': cleaned,
        'source_type': source_type,
        'year': year,
        'topic': topic,
        'limit': limit,
    }


def search(
    notebook: CourseNotebook,
    query: str,
    *,
    source_type=None,
    year=None,
    topic=None,
    keyword=False,
    limit=None,
) -> dict:
    """Return the best matching passages from ``notebook``."""
    started = time.monotonic()
    params = validate_params(
        query, source_type=source_type, year=year, topic=topic, limit=limit
    )
    filters = {
        'source_type': params['source_type'],
        'year': params['year'],
        'topic': params['topic'],
    }

    vector = _embed_query(params['query'])
    dimension = schema.require_ready()

    clause, values = _filters_clause(filters)
    candidate_limit = max(
        1, params['limit'] * _int_setting('RAG_CANDIDATE_MULTIPLIER', 3)
    )
    dense_rows = _dense_candidates(notebook, vector, clause, values, candidate_limit)

    use_keyword = bool(keyword) and bool(
        getattr(settings, 'RAG_FUSION_ENABLED', True)
    )
    keyword_rows = (
        _keyword_candidates(
            notebook, params['query'], clause, values, candidate_limit
        )
        if use_keyword
        else []
    )

    min_score = _float_setting('RAG_MIN_SCORE', 0.0)
    dense_rows = [
        row for row in dense_rows
        if (1.0 - float(row['distance'])) >= min_score
    ]

    rows_by_id = {}
    for row in list(dense_rows) + list(keyword_rows):
        rows_by_id[row['id']] = row

    if keyword_rows:
        scores = _reciprocal_rank_fusion(
            [row['id'] for row in dense_rows],
            [row['id'] for row in keyword_rows],
            k=_int_setting('RAG_RRF_K', 60),
        )
        order = sorted(scores, key=lambda key: (-scores[key], key))
        fusion = 'rrf'
    else:
        scores = {
            row['id']: 1.0 - float(row['distance']) for row in dense_rows
        }
        order = [row['id'] for row in dense_rows]
        fusion = 'dense'

    results = [
        _render(rows_by_id[chunk_id], scores.get(chunk_id), params['query'])
        for chunk_id in order[:params['limit']]
    ]

    status = 'ok' if results else 'insufficient_evidence'
    meta = {
        'model': embeddings.get_config().model,
        'dimension': dimension,
        'fusion': fusion,
        'keyword': use_keyword,
        'dense_candidates': len(dense_rows),
        'keyword_candidates': len(keyword_rows),
        'candidate_limit': candidate_limit,
        'filters': filters,
        'query_chars': len(params['query']),
        'took_ms': int((time.monotonic() - started) * 1000),
        'untrusted': True,
    }
    logger.info(
        'rag_search notebook=%s status=%s results=%d dense=%d keyword=%d '
        'query_chars=%d took_ms=%d',
        notebook.pk, status, len(results), meta['dense_candidates'],
        meta['keyword_candidates'], meta['query_chars'], meta['took_ms'],
    )
    return {'status': status, 'results': results, 'meta': meta}


def _embed_query(query: str):
    """Embed the query at a boundary that only ever yields a ``RAGError``.

    The Gemini provider translates its own exceptions; a fake provider, a
    future provider or a local bug must not be able to leak a raw exception
    (``TimeoutError``, ``ValueError``) past the API's error contract.
    """
    try:
        return embeddings.embed_query(query)
    except RAGError:
        raise
    except Exception as exc:
        raise embeddings.translate_exception(exc) from exc


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SELECT_COLUMNS = """
    c.id, c.source_key, c.source_type, c.syllabus_id, c.exam_paper_id,
    c.question_id, c.question_number, c.parent_number, c.page_number,
    c.chunk_index, c.year, c.text, c.metadata
"""


def _filters_clause(filters):
    """Build trusted SQL fragments + parameters for the optional filters."""
    clauses = []
    values = []
    if filters.get('source_type'):
        clauses.append('c.source_type = %s')
        values.append(filters['source_type'])
    if filters.get('year') is not None:
        clauses.append('c.year = %s')
        values.append(filters['year'])
    if filters.get('topic'):
        # Normalized at index time so the match is case-insensitive.
        clauses.append("c.metadata -> 'topics_normalized' @> %s::jsonb")
        values.append(json.dumps([filters['topic'].lower()]))
    return clauses, values


def _dense_candidates(notebook, vector, clauses, values, candidate_limit):
    sql = (
        f"SELECT {_SELECT_COLUMNS}, (e.embedding <=> %s::vector) AS distance "
        f"FROM {DocumentChunkEmbedding._meta.db_table} e "
        f"JOIN {DocumentChunk._meta.db_table} c ON c.id = e.chunk_id "
        f"WHERE c.notebook_id = %s AND c.embedding_status = %s"
    )
    params = [
        '[' + ','.join(_float(value) for value in vector) + ']',
        notebook.pk,
        DocumentChunk.STATUS_EMBEDDED,
    ]
    for clause, value in zip(clauses, values):
        sql += f' AND {clause}'
        params.append(value)
    sql += ' ORDER BY distance ASC LIMIT %s'
    params.append(candidate_limit)
    return _execute(sql, params)


def _keyword_candidates(notebook, query, clauses, values, candidate_limit):
    sql = (
        f"SELECT {_SELECT_COLUMNS}, "
        f"ts_rank_cd(to_tsvector('simple', c.text), tsquery) AS rank "
        f"FROM {DocumentChunk._meta.db_table} c, "
        f"websearch_to_tsquery('simple', %s) AS tsquery "
        f"WHERE c.notebook_id = %s AND c.embedding_status = %s"
    )
    params = [query, notebook.pk, DocumentChunk.STATUS_EMBEDDED]
    for clause, value in zip(clauses, values):
        sql += f' AND {clause}'
        params.append(value)
    sql += ' ORDER BY rank DESC, c.id ASC LIMIT %s'
    params.append(candidate_limit)
    return _execute(sql, params)


def _execute(sql, params):
    timeout_ms = int(_float_setting('RAG_QUERY_TIMEOUT_SECONDS', 5) * 1000)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # SET LOCAL only applies inside the transaction opened here,
                # so a slow scan can never outlive its budget.
                cursor.execute(
                    'SET LOCAL statement_timeout = %s', [f'{timeout_ms}ms']
                )
                cursor.execute(sql, params)
                columns = [column.name for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as exc:
        if _is_statement_timeout(exc):
            raise RetrievalTimeout(
                f'The search exceeded the {timeout_ms}ms query budget.'
            ) from exc
        if _is_dimension_error(exc):
            from .errors import DimensionMismatch

            raise DimensionMismatch(
                'The stored query vector does not match the vector column.'
            ) from exc
        logger.warning(
            'rag_query failed status=%s type=%s',
            getattr(exc, 'pgcode', None), type(exc).__name__,
        )
        raise VectorBackendUnavailable(
            'The vector store could not be queried.'
        ) from exc


def _is_statement_timeout(exc) -> bool:
    if getattr(exc, 'pgcode', None) == '57014':
        return True
    return 'statement timeout' in str(exc)


def _is_dimension_error(exc) -> bool:
    # pgvector reports `expected 768 dimensions, not 4` with no mention of the
    # column type, so the word "dimensions" is the reliable marker.
    message = str(exc).lower()
    return 'dimensions' in message and (
        'expected' in message or 'vector' in message
    )


def _float(value):
    return format(float(value), '.8g')


# ---------------------------------------------------------------------------
# Ranking + rendering
# ---------------------------------------------------------------------------

def _reciprocal_rank_fusion(dense_ids, keyword_ids, *, k):
    scores = defaultdict(float)
    for ranking in (dense_ids, keyword_ids):
        for position, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + position)
    return scores


def _snippet(text, query, width):
    """A short window of the passage, centred on the first query term hit."""
    source = text or ''
    width = max(40, width)
    if len(source) <= width:
        return source

    terms = re.findall(r'[0-9a-zA-Z]+', query.lower())[:_SNIPPET_TERMS]
    match_at = -1
    haystack = source.lower()
    for term in terms:
        found = haystack.find(term)
        if found >= 0 and (match_at < 0 or found < match_at):
            match_at = found
    if match_at < 0:
        return source[:width].rstrip() + '…'

    start = max(0, match_at - width // 3)
    end = min(len(source), start + width)
    prefix = '…' if start > 0 else ''
    suffix = '…' if end < len(source) else ''
    return prefix + source[start:end].strip() + suffix


def _decode_metadata(value):
    """``jsonb`` arrives as a ``str`` from a raw cursor, as a dict from the ORM."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _render(row, score, query):
    metadata = _decode_metadata(row.get('metadata'))
    document_id = row['syllabus_id'] or row['exam_paper_id']
    distance = row.get('distance')
    return {
        'chunk_id': row['id'],
        'source_key': row['source_key'],
        'source_type': row['source_type'],
        'document_id': document_id,
        'document_type': ('syllabus' if row['syllabus_id'] else 'exam_paper')
        if document_id else None,
        'document_title': metadata.get('document'),
        'question_id': row['question_id'],
        'question_number': row['question_number'],
        'parent_number': row['parent_number'],
        'page_number': row['page_number'],
        'year': row['year'],
        'chunk_index': row['chunk_index'],
        'topics': metadata.get('topics', []),
        'snippet': _snippet(
            row['text'], query, _int_setting('RAG_SNIPPET_CHARS', 400)
        ),
        'similarity': (
            round(1.0 - float(distance), 6) if distance is not None else None
        ),
        'score': round(float(score), 6) if score is not None else None,
        'untrusted': True,
    }
