"""Strict JSON contract for the chat model's answer.

The model must return exactly this shape (no extra keys). Length caps and
grounding (citations must match retrieved ``source_key``s) are enforced by
:mod:`predictor.services.chat.pipeline` after validation; nothing here
trusts the model beyond shape.
"""

from pydantic import BaseModel, ConfigDict, Field


class CitationSchema(BaseModel):
    """A pointer to one retrieved passage, never a free-form reference."""

    model_config = ConfigDict(extra='forbid')

    source_key: str
    # Optional verbatim fragment of the cited passage; dropped server-side
    # unless it appears in the retrieved snippet.
    quote: str = ''


class ChatAnswer(BaseModel):
    """The only payload shape the pipeline accepts from the model."""

    model_config = ConfigDict(extra='forbid')

    answer: str
    citations: list[CitationSchema] = Field(default_factory=list)
    insufficient_evidence: bool = False
