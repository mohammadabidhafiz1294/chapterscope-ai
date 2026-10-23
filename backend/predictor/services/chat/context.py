"""Bounded context assembly: recent history and retrieval parameters.

Deterministic by construction: the newest USER/ASSISTANT turns are kept
until the configured message and character budgets run out (oldest first to
be dropped), and the retrieval query is a truncation of the user's message.
SYSTEM messages and anything outside the session are never replayed.
"""

from django.conf import settings


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


def load_history(session, *, message_limit=None, char_cap=None):
    """Newest-first window of USER/ASSISTANT turns, returned oldest-first."""
    from ...models import ChatMessage

    limit = message_limit if message_limit is not None else _int_setting(
        'CHAT_HISTORY_MESSAGES', 10
    )
    cap = char_cap if char_cap is not None else _int_setting(
        'CHAT_HISTORY_CHARS', 4000
    )
    if limit < 0 or cap < 0:
        return []

    rows = list(
        session.messages
        .filter(role__in=[ChatMessage.ROLE_USER, ChatMessage.ROLE_ASSISTANT])
        .order_by('-created_at')[:limit]
    )
    kept = []
    used = 0
    for row in rows:
        content = row.content or ''
        if used + len(content) > cap and kept:
            break
        if len(content) > cap:
            content = content[:cap]
            kept.append({'role': row.role, 'content': content})
            break
        used += len(content)
        kept.append({'role': row.role, 'content': content})
    kept.reverse()
    return kept


def retrieval_params():
    """Clamped retrieval settings for the chat query."""
    top_k = _int_setting('CHAT_RETRIEVAL_TOP_K', 5)
    max_top_k = _int_setting('RAG_MAX_TOP_K', 20)
    top_k = max(1, min(top_k, max_top_k))
    min_score = max(0.0, min(_float_setting('CHAT_RETRIEVAL_MIN_SCORE', 0.0), 1.0))
    query_chars = max(
        1, _int_setting('CHAT_RETRIEVAL_QUERY_CHARS', 500)
    )
    return {
        'top_k': top_k,
        'min_score': min_score,
        'keyword': bool(getattr(settings, 'CHAT_RETRIEVAL_KEYWORD', True)),
        'query_chars': query_chars,
    }


def retrieval_query(text, *, query_chars=None):
    """Deterministic truncation so long messages stay embeddable."""
    limit = query_chars if query_chars is not None else (
        retrieval_params()['query_chars']
    )
    cleaned = ' '.join((text or '').split())
    return cleaned[:limit]


def filter_results(results, min_score):
    """Apply the chat similarity floor on top of the RAG layer's."""
    if min_score <= 0:
        return list(results or [])
    kept = []
    for row in results or []:
        similarity = row.get('similarity')
        if similarity is None or float(similarity) >= min_score:
            kept.append(row)
    return kept


def source_budget():
    """Total character budget for source blocks in the prompt."""
    return max(200, _int_setting('CHAT_CONTEXT_CHARS', 6000))


def bound_sources(results, *, budget=None):
    """Keep sources (in rank order) until the prompt budget runs out."""
    budget = source_budget() if budget is None else budget
    kept = []
    used = 0
    for row in results or []:
        snippet = str(row.get('snippet') or '')
        cost = len(snippet) + 200  # block overhead (keys, metadata, markers)
        if kept and used + cost > budget:
            break
        kept.append(row)
        used += cost
    return kept
