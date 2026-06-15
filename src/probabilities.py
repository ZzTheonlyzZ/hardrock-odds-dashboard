"""Probability and odds conversion helpers for Stage 1."""

from __future__ import annotations


def validate_american_odds(american_odds: int | float) -> int:
    """Validate and normalize American odds.

    American odds are usually <= -100 or >= +100. Even money can be +100 or -100.
    Odds between -99 and +99 are not valid sportsbook-style American odds.
    """
    try:
        odds = int(american_odds)
    except (TypeError, ValueError) as exc:
        raise ValueError("American odds must be a number like -110 or +150.") from exc

    if odds == 0 or -99 <= odds <= 99:
        raise ValueError("American odds must be <= -100 or >= +100.")

    return odds


def american_to_decimal(american_odds: int | float) -> float:
    """Convert American odds to decimal odds."""
    odds = validate_american_odds(american_odds)

    if odds > 0:
        return 1 + odds / 100

    return 1 + 100 / abs(odds)


def american_to_implied_probability(american_odds: int | float) -> float:
    """Convert American odds to implied probability as a decimal from 0 to 1."""
    odds = validate_american_odds(american_odds)

    if odds > 0:
        return 100 / (odds + 100)

    return abs(odds) / (abs(odds) + 100)


def profit_if_win(american_odds: int | float, stake: float = 1.0) -> float:
    """Return profit only, not including returned stake."""
    decimal_odds = american_to_decimal(american_odds)
    return stake * (decimal_odds - 1)


def total_payout_if_win(american_odds: int | float, stake: float = 1.0) -> float:
    """Return total payout including returned stake."""
    decimal_odds = american_to_decimal(american_odds)
    return stake * decimal_odds


def probability_to_percent(probability: float) -> float:
    """Convert decimal probability to percentage."""
    return probability * 100


def clamp_probability(probability: float) -> float:
    """Keep probability inside the valid 0-1 range."""
    return max(0.0, min(1.0, float(probability)))
