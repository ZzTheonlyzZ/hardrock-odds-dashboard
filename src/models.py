"""Stage 1 placeholder model helpers.

Stage 1 does not use real sports models yet. The user manually enters their estimated
probability. Later stages can replace this with market-based and sport-specific models.
"""

from __future__ import annotations

from src.probabilities import clamp_probability


def manual_probability_model(user_probability_percent: float) -> float:
    """Convert user's entered probability percentage into 0-1 decimal format."""
    return clamp_probability(user_probability_percent / 100)
