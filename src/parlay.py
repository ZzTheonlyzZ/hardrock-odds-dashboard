"""Simple parlay math for Stage 1."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from src.probabilities import american_to_decimal, clamp_probability


@dataclass
class ParlayResult:
    leg_count: int
    stake: float
    combined_decimal_odds: float
    estimated_probability: float
    implied_probability: float
    profit_if_win: float
    potential_payout: float
    ev: float
    ev_per_1_dollar: float
    risk_level: str
    category: str
    warning: str
    legs_summary: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decimal_to_american(decimal_odds: float) -> int:
    """Convert decimal odds to approximate American odds."""
    if decimal_odds < 1:
        raise ValueError("Decimal odds must be >= 1.")

    if decimal_odds >= 2:
        return int(round((decimal_odds - 1) * 100))

    return int(round(-100 / (decimal_odds - 1)))


def calculate_parlay(
    legs: list[dict[str, Any]],
    stake: float = 1.0,
    correlation_warning: bool = False,
) -> ParlayResult:
    """Calculate a simple independent-leg parlay estimate.

    This assumes independent legs. If the legs are correlated, the probability estimate
    can be very wrong. Stage 1 only warns the user instead of trying to model correlation.
    """
    if not legs:
        raise ValueError("Select at least one leg for the parlay.")

    combined_decimal = 1.0
    estimated_probability = 1.0
    implied_probability = 1.0
    legs_summary: list[str] = []

    for leg in legs:
        american_odds = int(leg["hardrock_odds"])
        model_probability = clamp_probability(float(leg["model_probability"]))
        decimal_odds = american_to_decimal(american_odds)

        combined_decimal *= decimal_odds
        estimated_probability *= model_probability
        implied_probability *= 1 / decimal_odds
        legs_summary.append(
            f'{leg["event"]} | {leg["market"]} | {leg["selection"]} ({american_odds:+d})'
        )

    profit = stake * (combined_decimal - 1)
    payout = stake * combined_decimal
    ev = (estimated_probability * profit) - ((1 - estimated_probability) * stake)
    ev_1 = ev / stake if stake else 0.0

    leg_count = len(legs)
    if leg_count >= 5:
        risk_level = "Lottery parlay / extreme variance"
    elif leg_count >= 3:
        risk_level = "High variance parlay"
    elif leg_count == 2:
        risk_level = "Medium-high variance parlay"
    else:
        risk_level = "Single-leg calculation"

    if correlation_warning:
        risk_level += " + correlation risk"

    if ev_1 > 0 and leg_count <= 2:
        category = "Possible value parlay"
    elif ev_1 > 0:
        category = "Positive EV estimate, but high variance"
    elif abs(ev_1) <= 0.02:
        category = "Near fair parlay"
    else:
        category = "Bad parlay / negative EV estimate"

    warning = (
        "Parlay math assumes each leg is independent. Same-game legs, player props, "
        "team totals, spreads, and game totals can be correlated. Manual review required."
    )

    if correlation_warning:
        warning += " You marked possible correlation, so treat this estimate as less reliable."

    return ParlayResult(
        leg_count=leg_count,
        stake=stake,
        combined_decimal_odds=combined_decimal,
        estimated_probability=estimated_probability,
        implied_probability=implied_probability,
        profit_if_win=profit,
        potential_payout=payout,
        ev=ev,
        ev_per_1_dollar=ev_1,
        risk_level=risk_level,
        category=category,
        warning=warning,
        legs_summary=legs_summary,
    )
