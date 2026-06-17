"""Stage 3.5 advanced market templates, availability, and bet cards."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.ev import calculate_expected_value, calculate_kelly_fraction
from src.odds_api import (
    HARD_ROCK_FL_BOOKMAKER,
    HARD_ROCK_GENERIC_BOOKMAKER,
)
from src.probabilities import (
    american_to_implied_probability,
    clamp_probability,
    total_payout_if_win,
)


@dataclass(frozen=True)
class MarketTemplate:
    name: str
    api_market_keys: tuple[str, ...]
    tier: str
    group: str
    manual_only: bool = False
    dynamic_player: bool = False


SOCCER_MARKET_TEMPLATES = (
    MarketTemplate("Moneyline / 1X2", ("h2h",), "Tier 1", "Match"),
    MarketTemplate("Draw No Bet", ("draw_no_bet",), "Tier 1", "Match"),
    MarketTemplate("Winner (Push if Tied)", ("draw_no_bet",), "Tier 1", "Match"),
    MarketTemplate("Double Chance", ("double_chance",), "Tier 1", "Match"),
    MarketTemplate("Correct Score", ("correct_score",), "Tier 1", "Match"),
    MarketTemplate("Game Result 90 Minutes + Stoppage Time", ("h2h",), "Tier 1", "Match"),
    MarketTemplate("Halftime / Fulltime", (), "Tier 2", "Match", manual_only=True),
    MarketTemplate("First Half Result", ("h2h_1h",), "Tier 1", "Match"),
    MarketTemplate("Second Half Result", ("h2h_2h",), "Tier 1", "Match"),
    MarketTemplate("Total Goals", ("totals", "alternate_totals"), "Tier 1", "Goals"),
    MarketTemplate(
        "Team Total Goals",
        ("team_totals", "alternate_team_totals"),
        "Tier 1",
        "Goals",
    ),
    MarketTemplate("BTTS", ("btts",), "Tier 1", "Goals"),
    MarketTemplate("Both Teams To Score", ("btts",), "Tier 1", "Goals"),
    MarketTemplate("1st Half Total Goals", ("totals_1h",), "Tier 1", "Goals"),
    MarketTemplate("2nd Half Total Goals", ("totals_2h",), "Tier 1", "Goals"),
    MarketTemplate("Home Team Total Goals", ("team_totals", "alternate_team_totals"), "Tier 1", "Goals"),
    MarketTemplate("Away Team Total Goals", ("team_totals", "alternate_team_totals"), "Tier 1", "Goals"),
    MarketTemplate("First Half Team Total Goals", (), "Tier 2", "Goals", manual_only=True),
    MarketTemplate("Second Half Team Total Goals", (), "Tier 2", "Goals", manual_only=True),
    MarketTemplate("Team To Score First", (), "Tier 2", "Goals", manual_only=True),
    MarketTemplate("Score 1st Goal", (), "Tier 2", "Goals", manual_only=True),
    MarketTemplate("Win To Nil / Win & Keep Clean Sheet", (), "Tier 2", "Goals", manual_only=True),
    MarketTemplate("To Win Either Half", (), "Tier 2", "Goals", manual_only=True),
    MarketTemplate("Woodwork Hit", (), "Tier 3", "Goals", manual_only=True),
    MarketTemplate("1st Half BTTS", ("btts_1h",), "Tier 1", "Goals"),
    MarketTemplate("2nd Half BTTS", ("btts_2h",), "Tier 1", "Goals"),
    MarketTemplate(
        "Spread / Handicap",
        ("spreads", "alternate_spreads"),
        "Tier 1",
        "Spread",
    ),
    MarketTemplate("Asian Handicap", ("alternate_spreads",), "Tier 1", "Spread"),
    MarketTemplate("First Half Handicap", (), "Tier 2", "Spread", manual_only=True),
    MarketTemplate("Second Half Handicap", (), "Tier 2", "Spread", manual_only=True),
    MarketTemplate("Total Corners", ("alternate_corners", "corners"), "Tier 1", "Corners"),
    MarketTemplate("Team Total Corners", ("team_totals_corners",), "Tier 1", "Corners"),
    MarketTemplate("First Team To Corner", ("first_corner",), "Tier 1", "Corners"),
    MarketTemplate("Team To Take Most Corners", ("most_corners",), "Tier 1", "Corners"),
    MarketTemplate("Most Corners", ("most_corners",), "Tier 1", "Corners"),
    MarketTemplate("1st Half Corners", ("corners_1h",), "Tier 1", "Corners"),
    MarketTemplate("2nd Half Corners", ("corners_2h",), "Tier 1", "Corners"),
    MarketTemplate("First Half Team Corners", (), "Tier 2", "Corners", manual_only=True),
    MarketTemplate("Second Half Team Corners", (), "Tier 2", "Corners", manual_only=True),
    MarketTemplate("First Half Most Corners", (), "Tier 2", "Corners", manual_only=True),
    MarketTemplate("Second Half Most Corners", (), "Tier 2", "Corners", manual_only=True),
    MarketTemplate("To Get Corner 1", (), "Tier 2", "Corners", manual_only=True),
    MarketTemplate("Over/Under corners by minute", (), "Tier 3", "Corners", manual_only=True),
    MarketTemplate("1st Half Winner", ("h2h_1h",), "Tier 1", "Half"),
    MarketTemplate("2nd Half Winner", ("h2h_2h",), "Tier 1", "Half"),
    MarketTemplate("1st Half Double Chance", ("double_chance_1h",), "Tier 1", "Half"),
    MarketTemplate("2nd Half Double Chance", ("double_chance_2h",), "Tier 1", "Half"),
    MarketTemplate(
        "Anytime Goalscorer",
        ("player_goal_scorer_anytime",),
        "Tier 2",
        "Player Prop",
        dynamic_player=True,
    ),
    MarketTemplate(
        "First Goalscorer",
        ("player_goal_scorer_first",),
        "Tier 2",
        "Player Prop",
        dynamic_player=True,
    ),
    MarketTemplate("Either Player To Score First", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Either Player To Score Or Assist", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Last Goalscorer", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("Player To Score 2+ Goals", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("Player To Score 3+ Goals", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("To Record An Assist", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("Player Shots", ("player_shots",), "Tier 2", "Player Prop", dynamic_player=True),
    MarketTemplate("Player Shots On Target", ("player_shots_on_target",), "Tier 2", "Player Prop", dynamic_player=True),
    MarketTemplate("Goalkeeper Saves", ("player_saves",), "Tier 2", "Player Prop", dynamic_player=True),
    MarketTemplate("Player Tackles", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("Player Fouls", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("Player Cards", ("player_cards",), "Tier 2", "Player Prop", dynamic_player=True),
    MarketTemplate("Player Saves / Goalkeeper Saves", ("player_saves",), "Tier 2", "Player Prop", dynamic_player=True),
    MarketTemplate("To Score Or Assist", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("To Score A Header", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("To Score From Outside The Penalty Box", (), "Tier 2", "Player Prop", manual_only=True, dynamic_player=True),
    MarketTemplate("Either Player To Score", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Either Player To Assist", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Player vs Player Goals", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Player vs Player Shots", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Player vs Player Shots On Target", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Player vs Player Assists", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Player vs Goalkeeper Saves", (), "Tier 3", "Head-to-Head / Player-vs-Player Specials", manual_only=True, dynamic_player=True),
    MarketTemplate("Triple Double", (), "Tier 3", "Special", manual_only=True, dynamic_player=True),
    MarketTemplate("Double Double", (), "Tier 3", "Special", manual_only=True, dynamic_player=True),
    MarketTemplate("Match Exclusives", (), "Tier 3", "Special", manual_only=True),
    MarketTemplate("Quarter Specials", (), "Tier 3", "Special", manual_only=True),
    MarketTemplate("Cards", ("alternate_cards", "cards"), "Tier 1", "Cards"),
    MarketTemplate("Total Cards", ("alternate_cards", "cards"), "Tier 1", "Cards"),
    MarketTemplate("Team Cards", (), "Tier 2", "Cards", manual_only=True),
    MarketTemplate("First Card", (), "Tier 2", "Cards", manual_only=True),
    MarketTemplate("Most Cards", (), "Tier 2", "Cards", manual_only=True),
    MarketTemplate("First Half Cards", (), "Tier 2", "Cards", manual_only=True),
    MarketTemplate("Second Half Cards", (), "Tier 2", "Cards", manual_only=True),
    MarketTemplate("Corners", ("alternate_corners", "corners"), "Tier 1", "Corners"),
    MarketTemplate("Other Manual Market", (), "Tier 3", "Other", manual_only=True),
)

TEMPLATE_BY_NAME = {template.name: template for template in SOCCER_MARKET_TEMPLATES}


@dataclass(frozen=True)
class AdvancedMarketCard:
    sport: str
    league: str
    event: str
    market_category: str
    selection: str
    point: int | float | None
    american_odds: int
    estimated_probability: float
    implied_probability: float
    edge: float
    ev_per_1_dollar: float
    potential_payout: float
    fractional_kelly: float
    recommended_stake: float
    stake: float
    source_label: str
    market_source: str
    confidence: str
    analysis_label: str
    bookmaker_key: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_market_template(name: str) -> MarketTemplate:
    try:
        return TEMPLATE_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported market category: {name}") from exc


def determine_api_availability(
    template: MarketTemplate,
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    matching = [
        row
        for row in outcomes
        if row.get("market_key") in template.api_market_keys
    ]
    if template.manual_only:
        return {
            "available": False,
            "label": "Manual-only",
            "outcomes": [],
        }
    return {
        "available": bool(matching),
        "label": "API-backed" if matching else "Manual-only",
        "outcomes": matching,
    }


def source_label_for_bookmaker(bookmaker_key: str | None) -> str:
    if bookmaker_key == HARD_ROCK_GENERIC_BOOKMAKER:
        return "Generic Hard Rock-backed"
    if bookmaker_key == HARD_ROCK_FL_BOOKMAKER:
        return "API-backed"
    if bookmaker_key:
        return "Market-reference only"
    return "Manual-only"


def source_details(bookmaker_key: str | None) -> tuple[str, str]:
    if bookmaker_key == HARD_ROCK_FL_BOOKMAKER:
        return ("Hard Rock Florida confirmed", "High")
    if bookmaker_key == HARD_ROCK_GENERIC_BOOKMAKER:
        return ("Hard Rock generic feed", "Medium")
    if bookmaker_key:
        return ("Alternative sportsbook source", "Medium")
    return ("Manual entry only", "Low")


def market_support_matrix() -> list[dict[str, str]]:
    return [
        {
            "Tier": template.tier,
            "Group": template.group,
            "Market": template.name,
            "Hard Rock FL": "Check live",
            "Generic Hard Rock": "Check live",
            "Other APIs": (
                "Mapped" if template.api_market_keys else "Unsupported"
            ),
            "Manual": "Yes",
        }
        for template in SOCCER_MARKET_TEMPLATES
    ]


def build_advanced_market_card(
    *,
    sport: str,
    event: str,
    market_category: str,
    selection: str,
    point: int | float | None,
    american_odds: int,
    estimated_probability: float,
    stake: float,
    bankroll: float,
    kelly_multiplier: float,
    bookmaker_key: str | None = None,
) -> AdvancedMarketCard:
    if not selection.strip():
        raise ValueError("Selection is required.")
    create_market_template(market_category)
    probability = clamp_probability(estimated_probability)
    if probability <= 0 or probability >= 1:
        raise ValueError("Estimated probability must be between 0 and 1.")

    implied = american_to_implied_probability(american_odds)
    full_kelly = calculate_kelly_fraction(american_odds, probability)
    fractional_kelly = max(0.0, full_kelly * kelly_multiplier)
    market_source, confidence = source_details(bookmaker_key)
    return AdvancedMarketCard(
        sport=sport,
        league=sport,
        event=event,
        market_category=market_category,
        selection=selection.strip(),
        point=point,
        american_odds=american_odds,
        estimated_probability=probability,
        implied_probability=implied,
        edge=probability - implied,
        ev_per_1_dollar=calculate_expected_value(
            american_odds,
            probability,
            1.0,
        ),
        potential_payout=total_payout_if_win(american_odds, stake),
        fractional_kelly=fractional_kelly,
        recommended_stake=max(0.0, bankroll * fractional_kelly),
        stake=stake,
        source_label=source_label_for_bookmaker(bookmaker_key),
        market_source=market_source,
        confidence=confidence,
        analysis_label=(
            "Potential Value Bet"
            if calculate_expected_value(american_odds, probability, 1.0) > 0
            else "Research only / no positive edge"
        ),
        bookmaker_key=bookmaker_key,
    )
