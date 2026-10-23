"""Phase 7: grounded practice-question generation.

Layered like :mod:`predictor.services.chat` and
:mod:`predictor.services.analytics`, so each module is single-responsibility
and independently testable:

``errors``
    Stable machine-readable failure codes the API maps to HTTP statuses.
``schema``
    Strict Pydantic contract the model must satisfy (``extra='forbid'``).
``prompts``
    Deterministic, injection-safe prompt construction.
``context``
    Deterministic-first retrieval of the two separately labelled contexts
    (syllabus / historical questions), scoped to one notebook + topic.
``model``
    Lazy LangChain chat-model factory plus provider-exception translation.
``math_checks``
    Safe (AST-walked, no ``eval``) SymPy verification for a narrow subset of
    numerical answers.
``validation``
    Server-side validation of a parsed question: schema, grounding,
    syllabus alignment, marks/rubric coherence, duplicate detection and the
    numeric check.
``pipeline``
    ``generate``: the single ordered turn that persists the request, asks
    the model for new questions, validates each and stores the results.

The LLM is used only to *draft* new questions; every displayed fact and
source reference is rebuilt server-side from ORM rows, never trusted from
the model output. Tests inject a fake model and never call a provider.
"""

from .pipeline import generate  # noqa: F401

__all__ = ['generate']
