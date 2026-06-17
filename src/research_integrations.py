"""Stage 4B orchestration for safe live soccer research integrations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from src.api_football import build_api_football_snapshot, read_api_football_key
from src.football_data import backup_context_row, read_football_data_key
from src.open_meteo import build_weather_snapshot
from src.research_lab import default_api_usage_rows, parse_the_odds_api_headers
from src.research_lab import aggregate_api_usage_rows


SAFE_RESEARCH_BOUNDARY = (
    "No Hard Rock scraping, sportsbook login, proxy use, hidden endpoints, "
    "captcha bypass, or automated betting."
)


def build_live_soccer_research_snapshot(
    *,
    secrets: Mapping[str, Any] | None,
    home_team: str,
    away_team: str,
    commence_time: str,
    venue_latitude: float | None = None,
    venue_longitude: float | None = None,
    odds_usage_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_date = _date_part(commence_time)
    api_football = build_api_football_snapshot(
        api_key=read_api_football_key(secrets),
        home_team=home_team,
        away_team=away_team,
        event_date=event_date,
    )
    weather = build_weather_snapshot(
        latitude=venue_latitude,
        longitude=venue_longitude,
    )
    backup_context, backup_usage, backup_missing = backup_context_row(
        read_football_data_key(secrets)
    )

    context = list(api_football["context"])
    context.extend(weather["context"])
    context.append(
        {
            "Factor": "Travel estimate",
            "Value": "Manual estimate required",
            "Betting note": "Travel is not inferred without reliable venue coordinates.",
        }
    )
    context.append(
        {
            "Factor": "Schedule/fatigue",
            "Value": f"Match date {event_date}",
            "Betting note": "Review fixture congestion manually before upgrading confidence.",
        }
    )
    context.append(backup_context)
    context.append(
        {
            "Factor": "Safety boundary",
            "Value": SAFE_RESEARCH_BOUNDARY,
            "Betting note": "Final wager must be manually confirmed in Hard Rock FL.",
        }
    )

    raw_usage = default_api_usage_rows()
    raw_usage[0] = odds_usage_row or parse_the_odds_api_headers({})
    raw_usage.extend(api_football["usage"])
    raw_usage.extend(weather["usage"])
    raw_usage.append(backup_usage)

    missing = []
    missing.extend(api_football.get("missing", []))
    missing.extend(weather.get("missing", []))
    missing.extend(backup_missing)

    diagnostics = dict(api_football.get("diagnostics", {}))
    diagnostics.update(weather.get("diagnostics", {}))
    diagnostics["API diagnostics summary"] = "; ".join(missing) if missing else "No safe API errors captured"

    return {
        "team_form": api_football["team_form"],
        "players": api_football["players"],
        "context": context,
        "api_usage": aggregate_api_usage_rows(raw_usage),
        "api_request_log": raw_usage,
        "missing_data": missing,
        "data_quality": _data_quality(api_football, weather),
        "integration_diagnostics": diagnostics,
        "team_mappings": api_football.get("team_mappings", {}),
        "player_summary": api_football.get("player_summary", {}),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def _date_part(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).date().isoformat()
    return value.split("T", 1)[0]


def _data_quality(api_football: dict[str, Any], weather: dict[str, Any]) -> str:
    has_team = any(
        row.get("Status") == "Live API-Football"
        for row in api_football.get("team_form", [])
    )
    has_mapping = bool(api_football.get("team_mappings"))
    squad_loaded = (
        int(api_football.get("player_summary", {}).get("Squad players loaded") or 0)
        > 0
    )
    if has_team:
        return "Odds + team form"
    if squad_loaded:
        return "Partial — squad only"
    if has_mapping:
        return "Partial — team mapping only"
    return "Odds-only"
