"""Transparent, configurable topic ranking - explicitly not a prediction.

The ranking is a weighted blend of four *computed* components, each already
normalised to 0..1 and each documented in ``README.md``. The weights are
plain settings (``ANALYTICS_WEIGHT_*``), the result is rounded to four
decimals and the full breakdown is returned next to the score so the order
can be reproduced by hand from the numbers in the payload. Nothing here is
modelled, extrapolated or randomised, and the API always ships the
disclaimer below with the ranking table.
"""

from __future__ import annotations

from django.conf import settings

from predictor.services.analytics.errors import InvalidRequest

DISCLAIMER = (
    'This ordering is a transparent weighted blend of historical frequency, '
    'recency, trend and syllabus alignment. It is not a prediction or a '
    'guarantee of what will appear in any exam.'
)

COMPONENT_LABELS = {
    'frequency': 'Long-term frequency: share of papers containing the topic',
    'recency': 'Recent frequency: share of papers in the most recent years',
    'trend': 'Trend: normalised slope of per-year paper prevalence',
    'syllabus': 'Syllabus alignment: share of syllabus texts mentioning it',
}

WEIGHT_NAMES = ('frequency', 'recency', 'trend', 'syllabus')


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp ``value`` into ``[low, high]``."""
    return max(low, min(high, value))


def weights() -> dict[str, float]:
    """Current ranking weights keyed by component name."""
    return {
        'frequency': float(getattr(settings, 'ANALYTICS_WEIGHT_FREQUENCY', 0.35)),
        'recency': float(getattr(settings, 'ANALYTICS_WEIGHT_RECENCY', 0.25)),
        'trend': float(getattr(settings, 'ANALYTICS_WEIGHT_TREND', 0.2)),
        'syllabus': float(getattr(settings, 'ANALYTICS_WEIGHT_SYLLABUS', 0.2)),
    }


def trend_component(slope: float | None) -> float:
    """Map a per-year prevalence slope onto 0..1 with a neutral 0.5 at zero."""
    cap = float(getattr(settings, 'ANALYTICS_TREND_CAP', 0.25))
    if slope is None or cap <= 0:
        return 0.5
    return 0.5 + 0.5 * clamp(slope / cap, -1.0, 1.0)


def score(components: dict[str, float],
          current_weights: dict[str, float] | None = None) -> tuple[float, dict]:
    """Weighted score plus the rounded component breakdown used to build it."""
    current_weights = current_weights if current_weights is not None else weights()
    total = sum(current_weights.get(name, 0.0) for name in WEIGHT_NAMES)
    if total <= 0:
        raise InvalidRequest(
            'The ranking weights must not all be zero.',
            hint='Set at least one ANALYTICS_WEIGHT_* setting to a positive '
                 'value.',
        )
    breakdown = {
        name: round(clamp(float(components.get(name, 0.0))), 4)
        for name in WEIGHT_NAMES
    }
    weighted_sum = sum(
        breakdown[name] * current_weights[name] for name in WEIGHT_NAMES
    )
    return round(weighted_sum / total, 4), breakdown
