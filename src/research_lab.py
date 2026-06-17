"""Research Lab support helpers for API status, context, and signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from src.ev import calculate_expected_value, calculate_kelly_fraction
from src.probabilities import american_to_decimal, american_to_implied_probability


def quota_status(
    remaining: int | float | None,
    limit: int | float | None,
    *,
    status_code: int | None = None,
) -> str:
    if status_code == 429:
        return "Limit reached"
    if remaining is None or limit in (None, 0):
        return "Unknown"
    ratio = float(remaining) / float(limit)
    if ratio < 0.05:
        return "Limit reached"
    if ratio < 0.15:
        return "Critical"
    if ratio < 0.30:
        return "Warning"
    if ratio <= 0.50:
        return "Watch"
    return "Healthy"


def parse_the_odds_api_headers(
    headers: Mapping[str, Any],
    *,
    status_code: int | None = None,
) -> dict[str, Any]:
    remaining = _int_header(headers, "x-requests-remaining")
    used = _int_header(headers, "x-requests-used")
    last = _int_header(headers, "x-requests-last")
    limit = remaining + used if remaining is not None and used is not None else None
    return {
        "API name": "The Odds API",
        "Plan/configured limit": limit,
        "Requests used": used,
        "Requests remaining": remaining,
        "Last request cost": last,
        "Minute remaining": None,
        "Daily remaining": remaining,
        "Reset time": None,
        "Status": quota_status(remaining, limit, status_code=status_code),
    }


def parse_api_football_headers(
    headers: Mapping[str, Any],
    *,
    status_code: int | None = None,
) -> dict[str, Any]:
    daily_limit = _int_header(headers, "x-ratelimit-requests-limit")
    daily_remaining = _int_header(headers, "x-ratelimit-requests-remaining")
    minute_limit = _int_header(headers, "X-RateLimit-Limit")
    minute_remaining = _int_header(headers, "X-RateLimit-Remaining")
    return {
        "API name": "API-Football",
        "Plan/configured limit": daily_limit,
        "Requests used": (
            daily_limit - daily_remaining
            if daily_limit is not None and daily_remaining is not None
            else None
        ),
        "Requests remaining": daily_remaining,
        "Last request cost": None,
        "Minute remaining": minute_remaining,
        "Daily remaining": daily_remaining,
        "Reset time": None,
        "Status": quota_status(
            minute_remaining if minute_remaining is not None else daily_remaining,
            minute_limit if minute_limit is not None else daily_limit,
            status_code=status_code,
        ),
    }


def parse_football_data_headers(
    headers: Mapping[str, Any],
    *,
    status_code: int | None = None,
) -> dict[str, Any]:
    minute_remaining = _int_header(headers, "X-Requests-Available-Minute")
    reset = headers.get("X-RequestCounter-Reset")
    return {
        "API name": "football-data.org",
        "Plan/configured limit": None,
        "Requests used": None,
        "Requests remaining": minute_remaining,
        "Last request cost": None,
        "Minute remaining": minute_remaining,
        "Daily remaining": None,
        "Reset time": reset,
        "Status": quota_status(minute_remaining, 10, status_code=status_code),
    }


@dataclass
class OpenMeteoQuotaTracker:
    minute_calls: int = 0
    hour_calls: int = 0
    day_calls: int = 0
    minute_limit: int = 600
    hour_limit: int = 5000
    day_limit: int = 10000

    def record_call(self) -> None:
        self.minute_calls += 1
        self.hour_calls += 1
        self.day_calls += 1

    def status_row(self) -> dict[str, Any]:
        minute_remaining = max(0, self.minute_limit - self.minute_calls)
        hour_remaining = max(0, self.hour_limit - self.hour_calls)
        day_remaining = max(0, self.day_limit - self.day_calls)
        return {
            "API name": "Open-Meteo",
            "Plan/configured limit": self.day_limit,
            "Requests used": self.day_calls,
            "Requests remaining": day_remaining,
            "Last request cost": 1 if self.day_calls else 0,
            "Minute remaining": minute_remaining,
            "Daily remaining": day_remaining,
            "Reset time": "Local rolling windows",
            "Status": quota_status(day_remaining, self.day_limit),
        }


def default_api_usage_rows() -> list[dict[str, Any]]:
    return [
        parse_the_odds_api_headers({}),
        parse_api_football_headers({}),
        parse_football_data_headers({}),
        OpenMeteoQuotaTracker().status_row(),
    ]


def request_budget_preview(mode: str) -> list[dict[str, Any]]:
    budgets = {
        "basic": (1, 0, 0, 0, 1),
        "full": (1, 4, 3, 1, 9),
        "player_props": (1, 1, 4, 0, 6),
        "weather": (0, 0, 0, 1, 1),
        "package_only": (0, 0, 0, 0, 0),
    }
    odds, team, player, weather, total = budgets[mode]
    return [
        {"Research area": "Odds", "Estimated calls": odds},
        {"Research area": "Team form", "Estimated calls": team},
        {"Research area": "Player stats", "Estimated calls": player},
        {"Research area": "Injuries", "Estimated calls": 1 if player else 0},
        {"Research area": "Weather", "Estimated calls": weather},
        {"Research area": "Total", "Estimated calls": total},
    ]


def unavailable_research_snapshot(reason: str = "Unavailable - API key missing") -> dict[str, Any]:
    return {
        "team_form": [
            {
                "Team": "Home",
                "Status": "Placeholder - API-Football not connected",
                "Last 5": "",
                "Last 10": "",
                "Wins": "",
                "Draws": "",
                "Losses": "",
                "Goals scored": "",
                "Goals conceded": "",
                "Goal differential": "",
                "BTTS rate": "",
                "Over 2.5 rate": "",
                "Clean sheets": "",
                "Failed to score": "",
            },
            {
                "Team": "Away",
                "Status": "Placeholder - API-Football not connected",
                "Last 5": "",
                "Last 10": "",
                "Wins": "",
                "Draws": "",
                "Losses": "",
                "Goals scored": "",
                "Goals conceded": "",
                "Goal differential": "",
                "BTTS rate": "",
                "Over 2.5 rate": "",
                "Clean sheets": "",
                "Failed to score": "",
            },
        ],
        "players": [
            {
                "Name": "Manual input available",
                "Team": "",
                "Position": "",
                "Expected starter": "Unknown",
                "Minutes per match": "",
                "Goals per 90": "",
                "Assists per 90": "",
                "Shots per 90": "",
                "Injury status": "Confirmed lineup required",
                "Rotation risk": "Unknown",
                "Notes": "Player prop requires confirmed lineup.",
            }
        ],
        "context": [
            {"Factor": "Schedule/fatigue", "Value": "Placeholder", "Betting note": "Manual review required."},
            {"Factor": "Travel", "Value": reason, "Betting note": "Label estimated if entered manually."},
            {"Factor": "Weather", "Value": "Placeholder - venue weather not connected", "Betting note": "Weather is context only, not a standalone betting reason."},
            {"Factor": "Venue", "Value": "Manual estimate available", "Betting note": "Manual venue confirmation available."},
            {"Factor": "Referee", "Value": "Placeholder - referee feed not connected", "Betting note": "Cards prop confidence reduced if missing."},
        ],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def build_betting_signals(
    lines: list[dict[str, Any]],
    *,
    bankroll: float,
    kelly_multiplier: float,
) -> list[dict[str, Any]]:
    signals = []
    for line in lines:
        odds = line["Odds"]
        implied = american_to_implied_probability(odds)
        true_probability = line.get("Consensus implied probability") or implied
        edge = true_probability - implied
        ev = calculate_expected_value(odds, true_probability, 1.0)
        kelly = calculate_kelly_fraction(odds, true_probability)
        fractional = max(0.0, kelly * kelly_multiplier)
        confidence = line["Confidence Label"]
        classification = classify_signal(
            edge=edge,
            ev=ev,
            fractional_kelly=fractional,
            confidence=confidence,
            odds=odds,
        )
        signals.append(
            {
                "Market Category": line.get("Market Category", ""),
                "Specific Market": line.get("Specific Market", ""),
                "Selection": line["Selection"],
                "Point / Line": line.get("Point / Line"),
                "Sportsbook/source": line["Source Label"],
                "American odds": odds,
                "Decimal odds": american_to_decimal(odds),
                "Implied probability": implied,
                "No-vig probability": line.get("Consensus implied probability"),
                "Estimated true probability": true_probability,
                "Edge": edge,
                "EV per $1": ev,
                "Kelly fraction": kelly,
                "Fractional Kelly": fractional,
                "Suggested stake": bankroll * fractional,
                "Confidence": confidence,
                "Risk level": risk_level(odds, confidence),
                "Classification": classification,
                "Data Status": "Odds only",
                "Top reasons": "Market price signal only; team/player/context data may be unavailable.",
                "Contradiction flags": contradiction_flags(line, edge),
            }
        )
    return deduplicate_betting_signals(signals)


def deduplicate_betting_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for signal in signals:
        key = (
            signal.get("Market Category", ""),
            signal.get("Specific Market", ""),
            signal.get("Selection"),
            signal.get("Point / Line"),
            signal.get("Sportsbook/source"),
            signal.get("American odds"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)
    return deduped


def source_status_summary(found_lines: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "Live odds": "Connected" if found_lines else "Not connected",
        "Exact Hard Rock FL": (
            "Available"
            if any(row["Hard Rock FL Available"] == "Yes" for row in found_lines)
            else "Not available"
        ),
        "Generic Hard Rock": (
            "Available"
            if any(row["Generic Hard Rock Available"] == "Yes" for row in found_lines)
            else "Not available"
        ),
        "Team/player data": "Placeholder",
        "Manual confirmation": "Required",
    }


def coverage_counts(
    found_lines: list[dict[str, Any]],
    missing_fl: list[dict[str, Any]],
    missing_markets: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "Total rows found": len(found_lines),
        "Exact Hard Rock FL rows": sum(
            row["Hard Rock FL Available"] == "Yes" for row in found_lines
        ),
        "Generic Hard Rock rows": sum(
            row["Generic Hard Rock Available"] == "Yes" for row in found_lines
        ),
        "Consensus-only rows": sum(
            row["Consensus Available"] == "Yes"
            and row["Hard Rock FL Available"] == "No"
            and row["Generic Hard Rock Available"] == "No"
            for row in found_lines
        ),
        "Missing from Hard Rock FL rows": len(missing_fl),
        "Manual-only markets": len(missing_markets),
    }


def classify_signal(
    *,
    edge: float,
    ev: float,
    fractional_kelly: float,
    confidence: str,
    odds: int,
) -> str:
    if ev <= 0 or fractional_kelly <= 0 or "Comparison" in confidence:
        return "No Bet"
    if edge >= 0.05 and "High" in confidence and odds < 500:
        return "Serious EV Bet"
    if edge >= 0.02:
        return "Small Edge Lean"
    if odds >= 500:
        return "Lottery Ticket"
    return "No Bet"


def risk_level(odds: int, confidence: str) -> str:
    if odds >= 500:
        return "High variance"
    if "High" in confidence:
        return "Medium"
    return "Elevated"


def contradiction_flags(line: dict[str, Any], edge: float) -> str:
    flags = []
    if line["Hard Rock FL Available"] == "No":
        flags.append("Manual confirmation required")
    if line["Source Label"] == "Generic Hard Rock":
        flags.append("Generic Hard Rock only, not Hard Rock FL")
    if edge <= 0.01:
        flags.append("No bet if edge is unclear")
    if "Player" in line["Market Category"]:
        flags.append("Player prop requires confirmed lineup")
    return "; ".join(flags) if flags else "None"


def _int_header(headers: Mapping[str, Any], key: str) -> int | None:
    value = headers.get(key) or headers.get(key.lower()) or headers.get(key.upper())
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
