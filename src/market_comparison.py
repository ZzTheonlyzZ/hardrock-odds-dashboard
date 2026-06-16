"""Stage 3 market consensus, no-vig, and manual override calculations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from src.ev import calculate_expected_value, calculate_kelly_fraction
from src.probabilities import (
    american_to_decimal,
    american_to_implied_probability,
    total_payout_if_win,
)


@dataclass(frozen=True)
class Stage3BetCard:
    sport: str
    event: str
    market: str
    selection: str
    hardrock_odds: int
    stake: float
    hardrock_implied_probability: float
    market_no_vig_probability: float
    edge: float
    ev_per_1_dollar: float
    potential_payout: float
    full_kelly: float
    fractional_kelly: float
    recommended_stake: float
    market_average_american_odds: int
    bookmaker_count: int
    category: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decimal_to_american(decimal_odds: float) -> int:
    if decimal_odds <= 1:
        raise ValueError("Decimal odds must be greater than 1.")
    if decimal_odds >= 2:
        return int(round((decimal_odds - 1) * 100))
    return int(round(-100 / (decimal_odds - 1)))


def selection_label(selection: str, point: int | float | None) -> str:
    return f"{selection} {point:+g}" if point is not None else selection


def calculate_market_comparison(
    outcomes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Average prices and average per-book no-vig probabilities by selection."""
    books: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in outcomes:
        price = row.get("price")
        if not isinstance(price, (int, float)):
            continue
        key = str(row.get("bookmaker_key") or "")
        if not key:
            continue
        label = selection_label(str(row.get("selection") or ""), row.get("point"))
        books[key].append(
            {
                "label": label,
                "price": int(price),
                "decimal_odds": american_to_decimal(price),
                "implied_probability": american_to_implied_probability(price),
            }
        )

    prices_by_selection: dict[str, list[float]] = defaultdict(list)
    fair_by_selection: dict[str, list[float]] = defaultdict(list)
    books_by_selection: dict[str, set[str]] = defaultdict(set)

    for bookmaker_key, rows in books.items():
        if len(rows) < 2:
            continue
        total_implied = sum(row["implied_probability"] for row in rows)
        if total_implied <= 0:
            continue
        for row in rows:
            label = row["label"]
            prices_by_selection[label].append(row["decimal_odds"])
            fair_by_selection[label].append(
                row["implied_probability"] / total_implied
            )
            books_by_selection[label].add(bookmaker_key)

    comparison = []
    for label in sorted(prices_by_selection):
        average_decimal = sum(prices_by_selection[label]) / len(
            prices_by_selection[label]
        )
        fair_probabilities = fair_by_selection[label]
        comparison.append(
            {
                "selection": label,
                "market_average_decimal_odds": average_decimal,
                "market_average_american_odds": decimal_to_american(
                    average_decimal
                ),
                "market_no_vig_probability": (
                    sum(fair_probabilities) / len(fair_probabilities)
                ),
                "bookmaker_count": len(books_by_selection[label]),
            }
        )
    return comparison


def classify_stage3_result(
    *,
    american_odds: int,
    edge: float,
    ev_per_1_dollar: float,
    bookmaker_count: int,
    data_quality: str,
) -> tuple[str, str]:
    if data_quality == "poor" or bookmaker_count < 2:
        return (
            "Manual review only",
            "The market sample or manual line quality is too weak for a confident label.",
        )
    if ev_per_1_dollar > 0 and edge > 0.05:
        return (
            "Potential value bet",
            "The manual Hard Rock line is meaningfully better than the no-vig market estimate.",
        )
    if ev_per_1_dollar > 0 and edge >= 0.02:
        return (
            "Lean/watchlist",
            "The estimated edge is positive but small. Confirm the line before acting.",
        )
    if abs(ev_per_1_dollar) <= 0.02:
        return ("Fair line", "The manual line is close to the no-vig market estimate.")
    if ev_per_1_dollar < 0 and american_odds > 250:
        return (
            "Bad payout trap",
            "The payout is large, but the no-vig market estimate still implies negative value.",
        )
    return (
        "Negative EV",
        "The manual Hard Rock price is worse than the no-vig market estimate.",
    )


def build_stage3_bet_card(
    *,
    sport: str,
    event: str,
    market: str,
    selection: str,
    hardrock_odds: int,
    market_no_vig_probability: float,
    market_average_american_odds: int,
    bookmaker_count: int,
    stake: float,
    bankroll: float,
    kelly_multiplier: float,
    data_quality: str = "normal",
) -> Stage3BetCard:
    hardrock_implied = american_to_implied_probability(hardrock_odds)
    edge = market_no_vig_probability - hardrock_implied
    ev_per_1 = calculate_expected_value(
        hardrock_odds,
        market_no_vig_probability,
        1.0,
    )
    full_kelly = calculate_kelly_fraction(
        hardrock_odds,
        market_no_vig_probability,
    )
    fractional_kelly = max(0.0, full_kelly * kelly_multiplier)
    category, recommendation = classify_stage3_result(
        american_odds=hardrock_odds,
        edge=edge,
        ev_per_1_dollar=ev_per_1,
        bookmaker_count=bookmaker_count,
        data_quality=data_quality,
    )
    return Stage3BetCard(
        sport=sport,
        event=event,
        market=market,
        selection=selection,
        hardrock_odds=hardrock_odds,
        stake=stake,
        hardrock_implied_probability=hardrock_implied,
        market_no_vig_probability=market_no_vig_probability,
        edge=edge,
        ev_per_1_dollar=ev_per_1,
        potential_payout=total_payout_if_win(hardrock_odds, stake),
        full_kelly=full_kelly,
        fractional_kelly=fractional_kelly,
        recommended_stake=max(0.0, bankroll * fractional_kelly),
        market_average_american_odds=market_average_american_odds,
        bookmaker_count=bookmaker_count,
        category=category,
        recommendation=recommendation,
    )
