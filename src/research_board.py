"""Unified Research Board source classification and value-card helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.ev import calculate_expected_value, calculate_kelly_fraction
from src.market_comparison import calculate_market_comparison, selection_label
from src.odds_api import (
    HARD_ROCK_FL_BOOKMAKER,
    HARD_ROCK_GENERIC_BOOKMAKER,
)
from src.probabilities import (
    american_to_implied_probability,
    clamp_probability,
)


SOURCE_RULES = {
    HARD_ROCK_FL_BOOKMAKER: ("Exact Hard Rock Florida API", "High confidence"),
    HARD_ROCK_GENERIC_BOOKMAKER: (
        "Generic Hard Rock API",
        "Medium confidence, may differ from Florida",
    ),
}


@dataclass(frozen=True)
class ResearchBetCard:
    sport: str
    event: str
    market: str
    selection: str
    point: int | float | None
    american_odds: int
    source_type: str
    confidence: str
    implied_probability: float
    no_vig_probability: float | None
    edge: float
    ev_per_1_dollar: float
    fractional_kelly: float
    kelly_stake: float
    stake: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_source(
    bookmaker_key: str | None,
    *,
    manual: bool = False,
) -> tuple[str, str]:
    if manual:
        return ("Manual Hard Rock Florida Entry", "Highest confidence")
    if bookmaker_key in SOURCE_RULES:
        return SOURCE_RULES[bookmaker_key]
    return ("Market Reference", "Comparison only")


def enrich_odds_rows(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for outcome in outcomes:
        price = outcome.get("price")
        if not isinstance(price, (int, float)):
            continue
        source_type, confidence = classify_source(outcome.get("bookmaker_key"))
        rows.append(
            {
                "bookmaker": outcome.get("bookmaker", ""),
                "bookmaker_key": outcome.get("bookmaker_key", ""),
                "source_type": source_type,
                "confidence": confidence,
                "market": outcome.get("market_key", ""),
                "selection": outcome.get("selection", ""),
                "point": outcome.get("point"),
                "american_odds": int(price),
                "implied_probability": american_to_implied_probability(price),
            }
        )
    return rows


def source_summary(rows: list[dict[str, Any]]) -> dict[str, bool]:
    keys = {row.get("bookmaker_key") for row in rows}
    hardrock_fl = HARD_ROCK_FL_BOOKMAKER in keys
    generic = HARD_ROCK_GENERIC_BOOKMAKER in keys
    other = any(key and key not in SOURCE_RULES for key in keys)
    return {
        "hardrock_fl_available": hardrock_fl,
        "generic_hardrock_available": generic,
        "other_books_available": other,
        "manual_entry_required": not (hardrock_fl or generic),
    }


def market_availability_row(
    market_name: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = source_summary(rows)
    return {
        "market": market_name,
        "hardrockbet_fl available": summary["hardrock_fl_available"],
        "hardrockbet available": summary["generic_hardrock_available"],
        "other books available": summary["other_books_available"],
        "manual entry available": True,
    }


def market_consensus(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return calculate_market_comparison(outcomes)


def find_no_vig_probability(
    comparison: list[dict[str, Any]],
    selection: str,
    point: int | float | None,
) -> tuple[float | None, int]:
    label = selection_label(selection, point)
    row = next(
        (item for item in comparison if item["selection"] == label),
        None,
    )
    if not row:
        return None, 0
    return row["market_no_vig_probability"], row["bookmaker_count"]


def build_research_card(
    *,
    sport: str,
    event: str,
    market: str,
    selection: str,
    point: int | float | None,
    american_odds: int,
    estimated_probability: float,
    no_vig_probability: float | None,
    stake: float,
    bankroll: float,
    kelly_multiplier: float,
    bookmaker_key: str | None = None,
    manual: bool = False,
) -> ResearchBetCard:
    if not selection.strip():
        raise ValueError("Selection is required.")
    probability = clamp_probability(
        no_vig_probability
        if no_vig_probability is not None
        else estimated_probability
    )
    if probability <= 0 or probability >= 1:
        raise ValueError("Probability must be between 0 and 1.")
    implied = american_to_implied_probability(american_odds)
    full_kelly = calculate_kelly_fraction(american_odds, probability)
    fractional_kelly = max(0.0, full_kelly * kelly_multiplier)
    source_type, confidence = classify_source(bookmaker_key, manual=manual)
    return ResearchBetCard(
        sport=sport,
        event=event,
        market=market,
        selection=selection,
        point=point,
        american_odds=american_odds,
        source_type=source_type,
        confidence=confidence,
        implied_probability=implied,
        no_vig_probability=no_vig_probability,
        edge=probability - implied,
        ev_per_1_dollar=calculate_expected_value(
            american_odds,
            probability,
            1.0,
        ),
        fractional_kelly=fractional_kelly,
        kelly_stake=max(0.0, bankroll * fractional_kelly),
        stake=stake,
    )
