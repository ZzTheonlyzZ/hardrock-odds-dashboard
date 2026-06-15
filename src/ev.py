"""Expected value, edge, Kelly, and bet classification helpers."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from src.probabilities import (
    american_to_decimal,
    american_to_implied_probability,
    clamp_probability,
    profit_if_win,
    total_payout_if_win,
)


@dataclass
class BetResult:
    sport: str
    event: str
    market: str
    selection: str
    hardrock_odds: int
    stake: float
    decimal_odds: float
    implied_probability: float
    model_probability: float
    edge: float
    ev: float
    ev_per_1_dollar: float
    profit_if_win: float
    potential_payout: float
    kelly_fraction: float
    fractional_kelly: float
    recommended_stake: float
    bankroll: float
    confidence: str
    risk_level: str
    category: str
    recommendation: str
    reasoning: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_expected_value(
    american_odds: int,
    model_probability: float,
    stake: float = 1.0,
) -> float:
    """Calculate EV in dollars for a given stake."""
    p = clamp_probability(model_probability)
    win_profit = profit_if_win(american_odds, stake)
    loss_amount = stake
    return (p * win_profit) - ((1 - p) * loss_amount)


def calculate_edge(american_odds: int, model_probability: float) -> float:
    """Model probability minus sportsbook implied probability."""
    p = clamp_probability(model_probability)
    implied = american_to_implied_probability(american_odds)
    return p - implied


def calculate_kelly_fraction(american_odds: int, model_probability: float) -> float:
    """Full Kelly fraction. Negative values mean no bet."""
    p = clamp_probability(model_probability)
    q = 1 - p
    decimal_odds = american_to_decimal(american_odds)
    b = decimal_odds - 1

    if b <= 0:
        return 0.0

    return (b * p - q) / b


def get_risk_level(american_odds: int, model_probability: float, leg_count: int = 1) -> str:
    """Simple risk label for single bets and parlays."""
    p = clamp_probability(model_probability)

    if leg_count >= 5:
        return "Very high variance"
    if leg_count >= 3:
        return "High variance"
    if p < 0.15:
        return "Lottery / very high variance"
    if p < 0.30:
        return "High variance longshot"
    if p < 0.45:
        return "Medium-high risk"
    if american_odds > 250:
        return "High payout risk"
    return "Standard betting risk"


def get_confidence(edge: float, model_probability: float, notes_quality: str = "normal") -> str:
    """Conservative confidence label."""
    p = clamp_probability(model_probability)

    if notes_quality == "poor":
        return "Low - manual review only"
    if edge >= 0.07 and p >= 0.35:
        return "Medium"
    if edge >= 0.03 and p >= 0.30:
        return "Low-medium"
    if edge > 0:
        return "Low"
    return "Low / no edge"


def classify_bet(
    american_odds: int,
    model_probability: float,
    ev_per_1_dollar: float,
    edge: float,
    data_quality: str = "normal",
) -> tuple[str, str, list[str]]:
    """Return category, recommendation, and reasoning."""
    p = clamp_probability(model_probability)
    implied = american_to_implied_probability(american_odds)
    reasoning: list[str] = []

    reasoning.append(f"Your model probability is {p:.2%}.")
    reasoning.append(f"The line's implied probability is {implied:.2%}.")
    reasoning.append(f"Estimated edge is {edge:.2%}.")
    reasoning.append(f"Estimated EV is ${ev_per_1_dollar:.2f} per $1 stake.")

    if data_quality == "poor":
        return (
            "Manual review only",
            "Do not treat this as a strong signal because the data quality is poor.",
            reasoning + ["Missing or weak supporting data lowers confidence."],
        )

    if ev_per_1_dollar > 0 and edge > 0.05 and p < 0.20:
        return (
            "Value longshot / high variance",
            "Potential value bet, but only for very small stakes if you accept high variance.",
            reasoning + ["Positive EV longshots can still lose most of the time."],
        )

    if ev_per_1_dollar > 0 and edge > 0.05:
        return (
            "Potential value bet",
            "Possible bet candidate after manual line confirmation.",
            reasoning + ["The model probability is meaningfully above the line's implied probability."],
        )

    if ev_per_1_dollar > 0 and 0.02 <= edge <= 0.05:
        return (
            "Lean / watchlist",
            "Small possible edge. Re-check the line before betting.",
            reasoning + ["The edge is positive but not large."],
        )

    if abs(ev_per_1_dollar) <= 0.02:
        return (
            "Fair line",
            "No clear advantage. Usually not worth forcing.",
            reasoning + ["EV is close to break-even."],
        )

    if ev_per_1_dollar < 0 and american_odds > 250:
        return (
            "Bad payout trap",
            "The payout looks attractive, but the estimated value is negative.",
            reasoning + ["Big odds do not automatically mean good value."],
        )

    return (
        "Negative EV / pass",
        "Pass unless you have better information than the current estimate.",
        reasoning + ["The estimated probability does not justify the price."],
    )


def build_bet_result(
    sport: str,
    event: str,
    market: str,
    selection: str,
    american_odds: int,
    model_probability: float,
    stake: float,
    bankroll: float,
    kelly_multiplier: float = 0.25,
    data_quality: str = "normal",
) -> BetResult:
    """Create the universal Stage 1 bet result object."""
    p = clamp_probability(model_probability)
    decimal_odds = american_to_decimal(american_odds)
    implied = american_to_implied_probability(american_odds)
    edge = p - implied
    ev = calculate_expected_value(american_odds, p, stake)
    ev_1 = calculate_expected_value(american_odds, p, 1.0)
    full_kelly = calculate_kelly_fraction(american_odds, p)
    fractional_kelly = max(0.0, full_kelly * kelly_multiplier)
    recommended_stake = max(0.0, bankroll * fractional_kelly)
    category, recommendation, reasoning = classify_bet(
        american_odds=american_odds,
        model_probability=p,
        ev_per_1_dollar=ev_1,
        edge=edge,
        data_quality=data_quality,
    )

    return BetResult(
        sport=sport,
        event=event,
        market=market,
        selection=selection,
        hardrock_odds=american_odds,
        stake=stake,
        decimal_odds=decimal_odds,
        implied_probability=implied,
        model_probability=p,
        edge=edge,
        ev=ev,
        ev_per_1_dollar=ev_1,
        profit_if_win=profit_if_win(american_odds, stake),
        potential_payout=total_payout_if_win(american_odds, stake),
        kelly_fraction=full_kelly,
        fractional_kelly=fractional_kelly,
        recommended_stake=recommended_stake,
        bankroll=bankroll,
        confidence=get_confidence(edge, p, notes_quality=data_quality),
        risk_level=get_risk_level(american_odds, p),
        category=category,
        recommendation=recommendation,
        reasoning=reasoning,
    )
