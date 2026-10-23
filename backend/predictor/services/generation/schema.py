"""Strict JSON contract for the generation model's structured output.

The model must return exactly one envelope holding a list of questions; no
extra keys anywhere. Length caps, grounding (``source_keys`` must match the
retrieved context), syllabus alignment, marks/rubric coherence, duplicate
detection and the numeric check are all enforced *after* validation by
:mod:`predictor.services.generation.validation`; nothing here trusts the
model beyond shape.

The literal sets mirror ``Question.TYPE_CHOICES`` / ``DIFFICULTY_CHOICES``
(excluding the empty "unspecified" values, which a generator must never emit)
so a stray label cannot slip into the database unchecked.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

QuestionType = Literal[
    'multiple_choice',
    'short_answer',
    'essay',
    'numerical',
    'true_false',
    'other',
]

Difficulty = Literal['easy', 'medium', 'hard']

# Only these kinds are independently recomputable by math_checks; anything
# else is stored as UNSUPPORTED and the question is marked needs_review.
NumericKind = Literal['evaluate', 'solve', 'compare', 'equivalent']


class RubricItem(BaseModel):
    """One rubric line: what earns marks and how many."""

    model_config = ConfigDict(extra='forbid')

    criterion: str = Field(min_length=1, max_length=500)
    marks: float = Field(ge=0, le=200)


class NumericProblem(BaseModel):
    """A narrowly-defined, independently recomputable numerical problem.

    ``evaluate``  -> compute ``expression`` (with optional ``assignments``).
    ``solve``     -> solve ``equation`` for ``variable``.
    ``compare``   -> check ``left`` vs ``right`` (``operator``).
    ``equivalent``-> check ``left`` and ``right`` are algebraically equal.

    Expressions are plain text here; math_checks parses them through a
    whitelisted AST walk (never ``eval``) before touching SymPy.
    """

    model_config = ConfigDict(extra='forbid')

    kind: NumericKind
    expression: str = Field(default='', max_length=200)
    equation: str = Field(default='', max_length=200)
    variable: str = Field(default='', max_length=20)
    assignments: dict[str, str] = Field(default_factory=dict)
    left: str = Field(default='', max_length=200)
    right: str = Field(default='', max_length=200)
    operator: str = Field(default='', max_length=4)
    # The model's own claim of the numeric result, verified independently.
    result: str = Field(default='', max_length=100)


class GeneratedQuestionSchema(BaseModel):
    """One generated practice question (shape only; semantics checked later)."""

    model_config = ConfigDict(extra='forbid')

    prompt: str = Field(min_length=1, max_length=4000)
    question_type: QuestionType
    difficulty: Difficulty
    marks: int = Field(ge=1, le=200)
    answer: str = Field(min_length=1, max_length=4000)
    solution: str = Field(default='', max_length=6000)
    marking_rubric: list[RubricItem] = Field(default_factory=list)
    # ``source_key``s taken from the retrieved context; fabricated ones are
    # dropped server-side and the question is flagged.
    source_keys: list[str] = Field(default_factory=list)
    # Topic labels (names) this question covers; resolved against the
    # notebook catalogue, never trusted as ids.
    topics: list[str] = Field(default_factory=list)
    language: str = Field(default='en', max_length=20)
    options: list[str] = Field(default_factory=list)
    numeric_problem: Optional[NumericProblem] = None
    # Optional self-reported confidence in the model's own answer, in [0, 1].
    # Validated against GENERATION_MIN_CONFIDENCE in validation.py.
    answer_confidence: Optional[float] = Field(default=None, ge=0, le=1)


class GenerationEnvelope(BaseModel):
    """The only payload shape the pipeline accepts from the model."""

    model_config = ConfigDict(extra='forbid')

    questions: list[GeneratedQuestionSchema] = Field(min_length=1)
