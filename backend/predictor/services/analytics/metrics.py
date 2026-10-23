"""Deterministic Phase 5 metrics, computed from ORM rows only.

Nothing in this module calls an LLM. Every number is derived from
``ExamPaper``/``Question``/``QuestionTopic`` rows of one notebook and every
definition below is the one published in ``README.md``:

* **Scope** - papers with ``notebook=<id>``; questions with
  ``exam_paper.notebook=<id>`` whose own notebook is this one or unset;
  ``extraction_status=FAILED`` questions excluded. Cross-notebook rows are
  impossible by construction, so a notebook's report never leaks another
  notebook's data.
* **Weighting** - ``primary`` (default): a question counts once for its
  confirmed PRIMARY topic only. ``weighted``: primary gets
  ``1/(1+s*W)``, each of its ``s`` secondaries ``W/(1+s*W)``; a question with
  no primary splits ``1/s`` across its secondaries; every question's weights
  sum to 1.0, so secondaries can never inflate totals.
* **Counts** - ``distinct_questions`` counts distinct question ids (never
  rows), ``weighted_questions`` sums the per-question weights.
* **Paper prevalence** - distinct papers containing the topic divided by the
  papers *that have at least one question* (papers with no extracted
  questions cannot evidence a topic's absence, so they are in no denominator
  and are reported separately in ``coverage``).
* **Marks** - ``paper_total(p)`` = ``ExamPaper.total_marks`` when set, else
  the sum of that paper's parsed question marks (flagged *derived*). A paper
  with a total <= 0 is not normalisable: it contributes nothing and raises
  the ``missing_marks`` notice. ``normalized_marks`` = sum over papers of
  ``topic_marks / paper_total``; ``marks_share`` = ``normalized_marks``
  divided by the papers that have a usable total.
* **Question share** - weighted topic questions over *all* questions in
  scope, unclassified ones included in the denominator.
* **Trend** - OLS slope of per-year paper prevalence against the actual
  year; ``null`` with the ``insufficient_history`` notice below two years.
* **Ranking** - see ``ranking.py``; the score is never a prediction.

Fractions are returned in 0..1 and rounded to four decimals, matching the
hand-computable expectations in ``predictor/tests/phase5_fixtures.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from predictor.models import ExamPaper, Question, QuestionTopic
from predictor.services.analytics import ranking
from predictor.services.analytics.catalog import TopicCatalogue, build_catalogue
from predictor.services.analytics.errors import InvalidRequest

WEIGHTINGS = ('primary', 'weighted')
DEFINITIONS_VERSION = '1'
MAX_TOPICS_HARD_CAP = 50
DEFAULT_TYPE = 'unspecified'

MEASURE_LABELS = {
    'counts': 'Raw question counts (primary topic, one count per question)',
    'weighted_counts': 'Weighted question counts (multi-topic allocation)',
    'paper_prevalence': (
        'Paper prevalence: share of papers (with questions) containing '
        'the topic'
    ),
    'question_share': (
        'Question share: topic questions divided by questions in scope'
    ),
    'raw_marks': 'Raw marks (summed as-is; papers have different totals)',
    'normalized_marks': (
        'Normalized marks: marks divided by each paper total, then summed'
    ),
    'marks_share': (
        'Marks share: normalized marks averaged over papers with a usable '
        'total'
    ),
    'recent_frequency': (
        'Recent frequency: paper prevalence within the most recent years'
    ),
    'long_term_frequency': (
        'Long-term frequency: paper prevalence across all papers with '
        'questions'
    ),
    'trend': 'Paper prevalence by year (per-year denominator)',
}

NOTICE_TEXT = {
    'no_papers': 'This notebook has no exam papers yet.',
    'no_questions': 'No extracted questions are available for metrics.',
    'no_classified_questions': (
        'No confirmed topic links exist yet; topic metrics are all zero. '
        'Classify or review questions to populate them.'
    ),
    'insufficient_history': (
        'Fewer than two years with questions: trend is not computable and '
        'defaults to the neutral 0.5 ranking component.'
    ),
    'missing_marks': (
        'Some papers have no usable total (total_marks unset and no parsed '
        'question marks): mark shares exclude them.'
    ),
    'derived_totals': (
        'Some papers have no explicit total_marks: their total is derived '
        'from the sum of parsed question marks.'
    ),
    'inconsistent_totals': (
        'Parsed marks exceed the declared total on at least one paper: '
        'marks shares above 1.0 reflect that data, not a bug.'
    ),
    'needs_review_topics': (
        'Some topics were proposed by the classifier and still need review.'
    ),
    'needs_review_links': (
        'Some question-topic links still need review; they are excluded '
        'from the metrics below.'
    ),
    'type_labels_pending_review': (
        'Some question type labels were proposed by the classifier and '
        'still need review; they are counted as their current value.'
    ),
    'no_syllabus': (
        'No syllabus text is attached: every syllabus alignment is 0.0.'
    ),
    'needs_review': (
        'This topic was proposed by the classifier and still needs review.'
    ),
}


def _secondary_weight() -> float:
    return float(getattr(settings, 'ANALYTICS_SECONDARY_WEIGHT', 0.5))


def _recent_years() -> int:
    return max(1, int(getattr(settings, 'ANALYTICS_RECENT_YEARS', 3)))


def _trend_topics() -> int:
    """How many top-ranked topics get a per-year prevalence series."""
    return max(1, int(getattr(settings, 'ANALYTICS_TREND_TOPICS', 8)))


def validate_weighting(weighting: Any) -> str:
    if weighting in (None, ''):
        return 'primary'
    if weighting not in WEIGHTINGS:
        raise InvalidRequest(
            "weighting must be 'primary' or 'weighted'.",
            hint="Use weighting=primary for counts that ignore secondary "
                 "topics, or weighting=weighted for shared counts.",
        )
    return str(weighting)


def validate_top_n(topics: Any) -> int:
    configured = max(1, int(getattr(settings, 'ANALYTICS_MAX_TOPICS', 20)))
    if topics in (None, ''):
        return configured
    try:
        value = int(topics)
    except (TypeError, ValueError) as exc:
        raise InvalidRequest('topics must be a positive integer.') from exc
    if value < 1:
        raise InvalidRequest('topics must be a positive integer.')
    return min(value, MAX_TOPICS_HARD_CAP)


@dataclass
class Analysis:
    """Scope rows plus the per-topic accumulators built from them."""

    notebook_id: int
    weighting: str
    secondary_weight: float
    catalogue: TopicCatalogue
    papers: list[ExamPaper]
    paper_year: dict[int, int | None]
    paper_total: dict[int, int]
    paper_usable: dict[int, bool]
    paper_derived: dict[int, bool]
    paper_marks_sum: dict[int, int]
    questions: list[Question]
    question_paper: dict[int, int]
    question_year: dict[int, int | None]
    question_marks: dict[int, int]
    question_type: dict[int, str]
    question_type_pending: dict[int, bool]
    link_weights: dict[int, dict[int, float]]
    link_primary: dict[int, int]
    links_confirmed: int
    topic_ids: set[int] = field(default_factory=set)
    topic_weighted_questions: dict[int, float] = field(default_factory=dict)
    topic_primary_questions: dict[int, int] = field(default_factory=dict)
    topic_distinct_questions: dict[int, int] = field(default_factory=dict)
    topic_papers: dict[int, set[int]] = field(default_factory=dict)
    topic_year_papers: dict[int, dict[int, set[int]]] = field(default_factory=dict)
    topic_year_questions: dict[int, dict[int, float]] = field(default_factory=dict)
    topic_marks: dict[int, dict[int, float]] = field(default_factory=dict)
    topic_types: dict[int, dict[str, float]] = field(default_factory=dict)
    global_types: dict[str, int] = field(default_factory=dict)
    papers_with_questions: set[int] = field(default_factory=set)
    papers_usable: list[int] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    year_papers: dict[int, set[int]] = field(default_factory=dict)
    links_pending: int = 0
    links_rejected: int = 0

    @property
    def questions_total(self) -> int:
        return len(self.questions)

    @property
    def paper_count(self) -> int:
        return len(self.papers)


def _question_weights(links: list[tuple[int, str]], weighting: str,
                      secondary_weight: float) -> dict[int, float]:
    primary = [topic_id for topic_id, role in links if role == 'PRIMARY']
    secondary = [topic_id for topic_id, role in links if role == 'SECONDARY']
    if weighting == 'primary':
        if len(primary) != 1:
            return {}
        return {primary[0]: 1.0}
    if primary:
        denominator = 1.0 + len(secondary) * secondary_weight
        weights = {primary[0]: 1.0 / denominator}
        for topic_id in secondary:
            weights[topic_id] = weights.get(topic_id, 0.0) + (
                secondary_weight / denominator
            )
        return weights
    if not secondary:
        return {}
    share = 1.0 / len(secondary)
    return {topic_id: share for topic_id in secondary}


def _ols_slope(points: list[tuple[int, float]]) -> float | None:
    """OLS slope of y on x; ``None`` below two points or with zero variance."""
    if len(points) < 2:
        return None
    count = len(points)
    mean_x = sum(x for x, _ in points) / count
    mean_y = sum(y for _, y in points) / count
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator


def scope_papers(notebook):
    """Exam papers attached to this notebook (the report's paper scope)."""
    return ExamPaper.objects.filter(notebook=notebook).order_by('year', 'id')


def scope_questions(notebook):
    """In-scope questions: reachable from this notebook's papers only.

    Shared by metrics and classification so both always agree on what "this
    notebook's questions" means, including the cross-notebook guard.
    """
    return Question.objects.filter(
        Q(notebook=notebook) | Q(notebook__isnull=True),
        exam_paper__notebook=notebook,
    ).exclude(extraction_status=Question.STATUS_FAILED)


def analyze(notebook, weighting: str) -> Analysis:
    """Load the notebook scope and accumulate every metric input."""
    weighting = validate_weighting(weighting)
    secondary_weight = _secondary_weight()
    catalogue = build_catalogue(notebook)

    papers = list(scope_papers(notebook))
    questions = list(
        scope_questions(notebook).select_related('exam_paper').order_by('id')
    )

    paper_year = {paper.id: paper.year for paper in papers}
    paper_marks_sum: dict[int, int] = {paper.id: 0 for paper in papers}
    for question in questions:
        if question.marks is not None:
            paper_id = question.exam_paper_id
            paper_marks_sum[paper_id] = paper_marks_sum.get(paper_id, 0) + int(
                question.marks
            )
    paper_total: dict[int, int] = {}
    paper_derived: dict[int, bool] = {}
    paper_usable: dict[int, bool] = {}
    for paper in papers:
        if paper.total_marks is not None:
            total, derived = int(paper.total_marks), False
        else:
            total, derived = paper_marks_sum.get(paper.id, 0), True
        paper_total[paper.id] = total
        paper_derived[paper.id] = derived
        paper_usable[paper.id] = total > 0

    question_ids = [question.id for question in questions]
    confirmed: list[tuple[int, int, str]] = []
    if question_ids:
        confirmed = list(
            QuestionTopic.objects.filter(
                question_id__in=question_ids,
                review_status='CONFIRMED',
                topic__notebook=notebook,
            ).values_list('question_id', 'topic_id', 'role')
        )
    links_by_question: dict[int, list[tuple[int, str]]] = {}
    for question_id, topic_id, role in confirmed:
        links_by_question.setdefault(question_id, []).append((topic_id, role))
    for entries in links_by_question.values():
        entries.sort()

    analysis = Analysis(
        notebook_id=notebook.id,
        weighting=weighting,
        secondary_weight=secondary_weight,
        catalogue=catalogue,
        papers=papers,
        paper_year=paper_year,
        paper_total=paper_total,
        paper_usable=paper_usable,
        paper_derived=paper_derived,
        paper_marks_sum=paper_marks_sum,
        questions=questions,
        question_paper={},
        question_year={},
        question_marks={},
        question_type={},
        question_type_pending={},
        link_weights={},
        link_primary={},
        links_confirmed=len(confirmed),
        papers_usable=[paper.id for paper in papers if paper_usable[paper.id]],
    )

    for question in questions:
        paper_id = question.exam_paper_id
        year = paper_year.get(paper_id)
        analysis.question_paper[question.id] = paper_id
        analysis.question_year[question.id] = year
        analysis.question_marks[question.id] = (
            int(question.marks) if question.marks is not None else 0
        )
        type_name = question.question_type or DEFAULT_TYPE
        analysis.question_type[question.id] = type_name
        analysis.question_type_pending[question.id] = (
            question.type_review_status == 'NEEDS_REVIEW'
        )
        analysis.global_types[type_name] = (
            analysis.global_types.get(type_name, 0) + 1
        )
        analysis.papers_with_questions.add(paper_id)
        if year is not None:
            analysis.year_papers.setdefault(year, set()).add(paper_id)

        links = links_by_question.get(question.id, [])
        weights = _question_weights(links, weighting, secondary_weight)
        analysis.link_weights[question.id] = weights
        primary_ids = [topic_id for topic_id, role in links if role == 'PRIMARY']
        if len(primary_ids) == 1:
            analysis.link_primary[question.id] = primary_ids[0]
        if not links:
            continue
        analysis.topic_ids.update(topic_id for topic_id, _role in links)

        marks = analysis.question_marks[question.id]
        for topic_id, weight in weights.items():
            analysis.topic_weighted_questions[topic_id] = (
                analysis.topic_weighted_questions.get(topic_id, 0.0) + weight
            )
            analysis.topic_distinct_questions[topic_id] = (
                analysis.topic_distinct_questions.get(topic_id, 0) + 1
            )
            analysis.topic_papers.setdefault(topic_id, set()).add(paper_id)
            if year is not None:
                year_bucket = analysis.topic_year_papers.setdefault(topic_id, {})
                year_bucket.setdefault(year, set()).add(paper_id)
                question_bucket = analysis.topic_year_questions.setdefault(
                    topic_id, {},
                )
                question_bucket[year] = question_bucket.get(year, 0.0) + weight
            paper_bucket = analysis.topic_marks.setdefault(topic_id, {})
            paper_bucket[paper_id] = paper_bucket.get(paper_id, 0.0) + (
                marks * weight
            )
            type_bucket = analysis.topic_types.setdefault(topic_id, {})
            type_bucket[type_name] = type_bucket.get(type_name, 0.0) + weight

    for topic_id in analysis.topic_ids:
        analysis.topic_primary_questions[topic_id] = 0
    for topic_id in analysis.link_primary.values():
        analysis.topic_primary_questions[topic_id] = (
            analysis.topic_primary_questions.get(topic_id, 0) + 1
        )
    analysis.years = sorted(analysis.year_papers)

    if question_ids:
        analysis.links_pending = QuestionTopic.objects.filter(
            question_id__in=question_ids, review_status='NEEDS_REVIEW',
        ).count()
        analysis.links_rejected = QuestionTopic.objects.filter(
            question_id__in=question_ids, review_status='REJECTED',
        ).count()
    return analysis


def _topic_row(analysis: Analysis, topic_id: int) -> dict:
    entry = analysis.catalogue.get(topic_id)
    papers_with_questions = len(analysis.papers_with_questions)
    total_questions = analysis.questions_total
    weighted_questions = analysis.topic_weighted_questions.get(topic_id, 0.0)
    distinct_questions = analysis.topic_distinct_questions.get(topic_id, 0)
    topic_papers = analysis.topic_papers.get(topic_id, set())
    topic_year_map = analysis.topic_year_papers.get(topic_id, {})

    paper_prevalence = (
        len(topic_papers) / papers_with_questions
        if papers_with_questions else 0.0
    )

    recent_year_values = analysis.years[-_recent_years():]
    recent_papers = {
        paper_id for paper_id in analysis.papers_with_questions
        if analysis.paper_year.get(paper_id) in recent_year_values
    }
    recent_frequency = (
        len(topic_papers & recent_papers) / len(recent_papers)
        if recent_papers else 0.0
    )

    points: list[tuple[int, float]] = []
    for year in analysis.years:
        denominator = len(analysis.year_papers.get(year, ()))
        if denominator:
            points.append((
                year,
                len(topic_year_map.get(year, ())) / denominator,
            ))
    slope = _ols_slope(points)

    topic_marks = analysis.topic_marks.get(topic_id, {})
    raw_marks = sum(topic_marks.values())
    normalized_marks = sum(
        marks / analysis.paper_total[paper_id]
        for paper_id, marks in topic_marks.items()
        if analysis.paper_usable.get(paper_id)
    )
    usable_total = len(analysis.papers_usable)
    marks_share = normalized_marks / usable_total if usable_total else 0.0

    components = {
        'frequency': paper_prevalence,
        'recency': recent_frequency,
        'trend': ranking.trend_component(slope),
        'syllabus': analysis.catalogue.importance_of(topic_id),
    }
    score, breakdown = ranking.score(components)

    notices: list[str] = []
    if slope is None:
        notices.append('insufficient_history')
    if entry is not None and entry.pending:
        notices.append('needs_review')

    years_with_papers = sorted(topic_year_map)
    return {
        'id': topic_id,
        'name': entry.name if entry else str(topic_id),
        'aliases': list(entry.aliases) if entry else [],
        'review_status': entry.review_status if entry else 'CONFIRMED',
        'primary_questions': analysis.topic_primary_questions.get(topic_id, 0),
        'weighted_questions': round(weighted_questions, 4),
        'distinct_questions': distinct_questions,
        'distinct_papers': len(topic_papers),
        'paper_prevalence': round(paper_prevalence, 4),
        'question_share': (
            round(weighted_questions / total_questions, 4)
            if total_questions else 0.0
        ),
        'raw_marks': round(raw_marks, 2),
        'normalized_marks': round(normalized_marks, 4),
        'marks_share': round(marks_share, 4),
        'type_distribution': {
            type_name: round(count, 2)
            for type_name, count in sorted(
                analysis.topic_types.get(topic_id, {}).items(),
            )
        },
        'recent_frequency': round(recent_frequency, 4),
        'long_term_frequency': round(paper_prevalence, 4),
        'trend_slope': round(slope, 4) if slope is not None else None,
        'trend_direction': (
            None if slope is None
            else 'up' if slope > 0 else 'down' if slope < 0 else 'flat'
        ),
        'syllabus_importance': analysis.catalogue.importance_of(topic_id),
        'first_year': years_with_papers[0] if years_with_papers else None,
        'last_year': years_with_papers[-1] if years_with_papers else None,
        'score': score,
        'components': breakdown,
        'notices': notices,
    }


def _coverage(analysis: Analysis) -> dict:
    catalogue = analysis.catalogue
    type_pending = sum(
        1 for pending in analysis.question_type_pending.values() if pending
    )
    classified = sum(1 for weights in analysis.link_weights.values() if weights)
    active_topics = [
        topic_id for topic_id in analysis.topic_ids
        if analysis.topic_distinct_questions.get(topic_id, 0) > 0
    ]
    return {
        'weighting': analysis.weighting,
        'secondary_weight': analysis.secondary_weight,
        'papers_total': analysis.paper_count,
        'papers_with_questions': len(analysis.papers_with_questions),
        'papers_without_questions': (
            analysis.paper_count - len(analysis.papers_with_questions)
        ),
        'papers_total_explicit': sum(
            1 for derived in analysis.paper_derived.values() if not derived
        ),
        'papers_total_derived': sum(
            1 for derived in analysis.paper_derived.values() if derived
        ),
        'papers_usable_total': len(analysis.papers_usable),
        'questions_total': analysis.questions_total,
        'questions_classified': classified,
        'questions_unclassified': analysis.questions_total - classified,
        'questions_with_marks': sum(
            1 for question in analysis.questions if question.marks is not None
        ),
        'questions_with_type': sum(
            1 for question in analysis.questions if question.question_type
        ),
        'questions_type_pending_review': type_pending,
        'topics_total': len(catalogue.entries),
        'topics_confirmed': (
            len(catalogue.entries) - catalogue.topics_needs_review
        ),
        'topics_needs_review': catalogue.topics_needs_review,
        'topics_with_questions': len(active_topics),
        'topics_without_questions': max(
            0, len(catalogue.entries) - len(active_topics),
        ),
        'links_confirmed': analysis.links_confirmed,
        'links_pending_review': analysis.links_pending,
        'links_rejected': analysis.links_rejected,
        'years_total': len(analysis.years),
        'recent_years_window': _recent_years(),
        'year_min': analysis.years[0] if analysis.years else None,
        'year_max': analysis.years[-1] if analysis.years else None,
        'syllabus_documents': catalogue.syllabus_documents,
        'syllabi_with_text': catalogue.syllabi_with_text,
    }


def _notice_labels(codes: list[str]) -> dict[str, str]:
    """Human-readable text for each notice code (self-describing payload)."""
    return {code: NOTICE_TEXT.get(code, code) for code in codes}


def _notices(analysis: Analysis) -> list[str]:
    notices: list[str] = []
    if analysis.paper_count == 0:
        notices.append('no_papers')
    if analysis.questions_total == 0:
        notices.append('no_questions')
    elif not any(analysis.link_weights.values()):
        notices.append('no_classified_questions')
    if len(analysis.years) < 2:
        notices.append('insufficient_history')
    if len(analysis.papers_usable) < analysis.paper_count:
        notices.append('missing_marks')
    if any(analysis.paper_derived.values()):
        notices.append('derived_totals')
    if any(
        analysis.paper_marks_sum.get(paper_id, 0)
        > analysis.paper_total.get(paper_id, 0)
        for paper_id in analysis.paper_marks_sum
        if analysis.paper_total.get(paper_id, 0) > 0
        and not analysis.paper_derived.get(paper_id)
    ):
        notices.append('inconsistent_totals')
    if analysis.catalogue.topics_needs_review:
        notices.append('needs_review_topics')
    if analysis.links_pending:
        notices.append('needs_review_links')
    if any(analysis.question_type_pending.values()):
        notices.append('type_labels_pending_review')
    if not analysis.catalogue.syllabi_with_text:
        notices.append('no_syllabus')
    return notices


def _years_payload(analysis: Analysis, topic_ids: list[int]) -> list[dict]:
    payload: list[dict] = []
    for year in analysis.years:
        year_papers = len(analysis.year_papers.get(year, ()))
        prevalence: dict[str, float] = {}
        for topic_id in topic_ids:
            papers_in_year = len(
                analysis.topic_year_papers.get(topic_id, {}).get(year, ())
            )
            prevalence[str(topic_id)] = (
                round(papers_in_year / year_papers, 4) if year_papers else 0.0
            )
        payload.append({
            'year': year,
            'papers': year_papers,
            'topic_prevalence': prevalence,
        })
    return payload


def build_report(notebook, *, weighting: Any = None,
                 topics: Any = None) -> dict:
    """Full analytics report for one notebook (the summary endpoint)."""
    analysis = analyze(notebook, validate_weighting(weighting))
    limit = validate_top_n(topics)

    rows = [
        _topic_row(analysis, topic_id)
        for topic_id in analysis.topic_ids
        if analysis.topic_distinct_questions.get(topic_id, 0) > 0
    ]
    rows.sort(key=lambda row: (-row['score'], row['name']))
    visible = rows[:limit]
    ranked_ids = [row['id'] for row in visible]

    return {
        'notebook_id': analysis.notebook_id,
        'definitions_version': DEFINITIONS_VERSION,
        'generated_at': timezone.now().isoformat(),
        'weighting': analysis.weighting,
        'coverage': _coverage(analysis),
        'notices': _notices(analysis),
        'notice_labels': _notice_labels(_notices(analysis)),
        'measure_labels': MEASURE_LABELS,
        'ranking': {
            'disclaimer': ranking.DISCLAIMER,
            'weights': ranking.weights(),
            'component_labels': ranking.COMPONENT_LABELS,
            'trend_cap': float(getattr(settings, 'ANALYTICS_TREND_CAP', 0.25)),
        },
        'topics': visible,
        'topics_truncated': len(rows) > len(visible),
        'years': _years_payload(analysis, ranked_ids[:_trend_topics()]),
        'question_types': [
            {'type': type_name, 'count': count}
            for type_name, count in sorted(
                analysis.global_types.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
    }


def build_topic_report(notebook, topic, *, weighting: Any = None) -> dict:
    """Detail payload for one topic: series, splits, links and score."""
    if topic.notebook_id != notebook.id:
        raise InvalidRequest('That topic does not belong to this notebook.')
    analysis = analyze(notebook, validate_weighting(weighting))
    row = _topic_row(analysis, topic.id)

    year_rows: list[dict] = []
    topic_papers = analysis.topic_papers.get(topic.id, set())
    for year in analysis.years:
        year_papers = len(analysis.year_papers.get(year, ()))
        papers_in_year = len(
            analysis.topic_year_papers.get(topic.id, {}).get(year, ())
        )
        year_questions = analysis.topic_year_questions.get(topic.id, {}).get(
            year, 0.0,
        )
        year_marks = sum(
            analysis.topic_marks.get(topic.id, {}).get(paper_id, 0.0)
            for paper_id in topic_papers
            if analysis.paper_year.get(paper_id) == year
        )
        year_rows.append({
            'year': year,
            'papers': year_papers,
            'topic_papers': papers_in_year,
            'prevalence': (
                round(papers_in_year / year_papers, 4) if year_papers else 0.0
            ),
            'weighted_questions': round(year_questions, 4),
            'raw_marks': round(year_marks, 2),
        })

    combined = list(dict.fromkeys(_notices(analysis) + row['notices']))
    question_ids = [question.id for question in analysis.questions]
    link_rows = []
    if question_ids:
        link_rows = list(
            QuestionTopic.objects.filter(
                question_id__in=question_ids, topic_id=topic.id,
            ).values_list('role', 'review_status')
        )
    links = {
        'primary': sum(
            1 for role, status in link_rows
            if role == 'PRIMARY' and status == 'CONFIRMED'
        ),
        'secondary': sum(
            1 for role, status in link_rows
            if role == 'SECONDARY' and status == 'CONFIRMED'
        ),
        'pending_review': sum(
            1 for _role, status in link_rows if status == 'NEEDS_REVIEW'
        ),
        'rejected': sum(
            1 for _role, status in link_rows if status == 'REJECTED'
        ),
    }

    return {
        'notebook_id': analysis.notebook_id,
        'definitions_version': DEFINITIONS_VERSION,
        'generated_at': timezone.now().isoformat(),
        'weighting': analysis.weighting,
        'topic': row,
        'links': links,
        'years': year_rows,
        'measure_labels': MEASURE_LABELS,
        'ranking': {
            'disclaimer': ranking.DISCLAIMER,
            'weights': ranking.weights(),
            'component_labels': ranking.COMPONENT_LABELS,
        },
        'notices': combined,
        'notice_labels': _notice_labels(combined),
        'coverage': _coverage(analysis),
    }
