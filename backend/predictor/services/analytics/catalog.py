"""Notebook topic catalogue and the syllabus-importance signal.

The catalogue is the single source of truth for what a label may resolve to
inside one notebook: every topic name plus its curated aliases, normalised
exactly the way ``labels.normalize_label`` normalises proposals. The
syllabus-importance signal is deliberately simple and auditable: the fraction
of the notebook's attached syllabi whose extracted text mentions the topic
name or one of its aliases. A notebook with no syllabus text has importance
0.0 for every topic, and that is reported as data, never as an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass

from predictor.models import NotebookTopic, Syllabus
from predictor.services.analytics.labels import normalize_label


@dataclass(frozen=True)
class CatalogueEntry:
    """One topic as it may be referenced by name or alias."""

    id: int
    name: str
    normalized: str
    aliases: tuple[str, ...]
    review_status: str

    @property
    def labels(self) -> list[str]:
        return [self.name, *self.aliases]

    @property
    def pending(self) -> bool:
        return self.review_status == 'NEEDS_REVIEW'


@dataclass
class TopicCatalogue:
    """All topics of one notebook plus lookup helpers."""

    notebook_id: int
    entries: tuple[CatalogueEntry, ...]
    index: dict[str, list[int]]
    importance: dict[int, float]
    syllabus_documents: int
    syllabi_with_text: int

    @property
    def names(self) -> list[str]:
        return [entry.name for entry in self.entries]

    @property
    def topics_needs_review(self) -> int:
        return sum(1 for entry in self.entries if entry.pending)

    def get(self, topic_id: int) -> CatalogueEntry | None:
        for entry in self.entries:
            if entry.id == topic_id:
                return entry
        return None

    def importance_of(self, topic_id: int) -> float:
        return self.importance.get(topic_id, 0.0)


def syllabus_importance(labels: list[str], texts: list[str]) -> float:
    """Fraction of syllabus texts mentioning any of ``labels`` (0.0 if none)."""
    if not texts:
        return 0.0
    needles = [
        needle
        for needle in (normalize_label(label) for label in labels)
        if needle
    ]
    if not needles:
        return 0.0
    corpus = [normalize_label(text) for text in texts]
    hits = sum(1 for text in corpus if any(needle in text for needle in needles))
    return round(hits / len(texts), 4)


def topic_label_index(topics) -> dict[str, list[int]]:
    """Normalised label (name or alias) -> topic ids, for any topic iterable."""
    index: dict[str, list[int]] = {}
    for topic in topics:
        name_key = topic.normalized_name or normalize_label(topic.name)
        if name_key:
            index.setdefault(name_key, []).append(topic.id)
        for alias in topic.aliases or []:
            alias_key = normalize_label(str(alias))
            if alias_key:
                index.setdefault(alias_key, []).append(topic.id)
    return index


def _syllabus_stats(notebook) -> tuple[list[str], int, int]:
    """Normalised extracted texts, syllabi with text, syllabi attached."""
    texts: list[str] = []
    with_text = 0
    documents = 0
    queryset = Syllabus.objects.filter(notebook=notebook).values_list(
        'extracted_text', flat=True,
    )
    for raw in queryset:
        documents += 1
        if not raw or not raw.strip():
            continue
        with_text += 1
        texts.append(normalize_label(raw))
    return texts, with_text, documents


def build_catalogue(notebook, *, texts: list[str] | None = None) -> TopicCatalogue:
    """Load this notebook's topics and its syllabus-importance per topic."""
    topics = list(
        NotebookTopic.objects.filter(notebook=notebook)
        .order_by('normalized_name', 'id')
    )
    if texts is None:
        texts, with_text, documents = _syllabus_stats(notebook)
    else:
        with_text, documents = len(texts), len(texts)

    entries: tuple[CatalogueEntry, ...] = tuple(
        CatalogueEntry(
            id=topic.id,
            name=topic.name,
            normalized=topic.normalized_name,
            aliases=tuple(str(alias) for alias in (topic.aliases or [])),
            review_status=topic.review_status,
        )
        for topic in topics
    )
    importance: dict[int, float] = {}
    for entry in entries:
        importance[entry.id] = syllabus_importance(entry.labels, texts)

    return TopicCatalogue(
        notebook_id=notebook.id,
        entries=entries,
        index=topic_label_index(topics),
        importance=importance,
        syllabus_documents=documents,
        syllabi_with_text=with_text,
    )
