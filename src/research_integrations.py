"""Stage 4B orchestration for safe live soccer research integrations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from src.api_football import build_api_football_snapshot, read_api_football_key
from src.football_data import (
    LIMITED_FOOTBALL_DATA_STATUS,
    LIVE_FOOTBALL_DATA_STATUS,
    PARTIAL_FOOTBALL_DATA_STATUS,
    STALE_FOOTBALL_DATA_STATUS,
    backup_context_row,
    build_football_data_snapshot,
    read_football_data_key,
)
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
    football_data_key = read_football_data_key(secrets)
    football_data = build_football_data_snapshot(
        api_key=football_data_key,
        home_team=home_team,
        away_team=away_team,
        event_date=event_date,
        competition_code="WC",
    )
    backup_context, backup_usage, backup_missing = backup_context_row(football_data_key)
    team_form = _preferred_team_form(api_football, football_data)

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
            "Value": "Needs fixture history and schedule review",
            "Betting note": f"Match date {event_date}; review fixture congestion manually before upgrading confidence.",
        }
    )
    context.extend(football_data.get("context", []) or [backup_context])
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
    raw_usage.extend(football_data["usage"])
    raw_usage.extend(weather["usage"])
    if not football_data_key:
        raw_usage.append(backup_usage)

    missing = []
    missing.extend(api_football.get("missing", []))
    missing.extend(football_data.get("missing", []))
    missing.extend(weather.get("missing", []))
    if not football_data_key:
        missing.extend(backup_missing)

    diagnostics = dict(api_football.get("diagnostics", {}))
    diagnostics.update(football_data.get("diagnostics", {}))
    diagnostics.update(weather.get("diagnostics", {}))
    diagnostics["API diagnostics summary"] = "; ".join(missing) if missing else "No safe API errors captured"
    diagnostics["Research snapshot source used by Research Data"] = _snapshot_source(
        api_football,
        football_data,
    )
    diagnostics["Selected home team used by Research Data"] = home_team
    diagnostics["Selected away team used by Research Data"] = away_team
    diagnostics["Fixture rows used by Research Data"] = api_football.get("fixture_rows_used", 0)
    diagnostics["football-data.org rows used by Research Data"] = football_data.get("match_rows_used", 0)
    diagnostics["Squad rows used by Research Data"] = api_football.get("squad_rows_used", 0)
    compatibility_summary = build_api_compatibility_summary(
        team_form=team_form,
        player_summary=api_football.get("player_summary", {}),
        weather=weather,
    )

    return {
        "team_form": team_form,
        "players": api_football["players"],
        "context": context,
        "api_usage": aggregate_api_usage_rows(raw_usage),
        "api_request_log": raw_usage,
        "missing_data": missing,
        "data_quality": _data_quality(api_football, football_data, weather),
        "integration_diagnostics": diagnostics,
        "compatibility_summary": compatibility_summary,
        "team_mappings": {
            "API-Football": api_football.get("team_mappings", {}),
            "football-data.org": football_data.get("team_mappings", {}),
        },
        "player_summary": api_football.get("player_summary", {}),
        "research_snapshot_source": diagnostics["Research snapshot source used by Research Data"],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def _date_part(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).date().isoformat()
    return value.split("T", 1)[0]


def _data_quality(
    api_football: dict[str, Any],
    football_data: dict[str, Any],
    weather: dict[str, Any],
) -> str:
    has_team = any(
        row.get("Status") in {"Live API-Football", LIVE_FOOTBALL_DATA_STATUS}
        for row in (
            list(api_football.get("team_form", []))
            + list(football_data.get("team_form", []))
        )
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


def _preferred_team_form(
    api_football: dict[str, Any],
    football_data: dict[str, Any],
) -> list[dict[str, Any]]:
    api_rows = list(api_football.get("team_form", []))
    if any(row.get("Status") == "Live API-Football" for row in api_rows):
        return api_rows
    fd_rows = list(football_data.get("team_form", []))
    if any(
        row.get("Status")
        in {
            LIVE_FOOTBALL_DATA_STATUS,
            PARTIAL_FOOTBALL_DATA_STATUS,
            LIMITED_FOOTBALL_DATA_STATUS,
            STALE_FOOTBALL_DATA_STATUS,
        }
        for row in fd_rows
    ):
        return fd_rows
    return api_rows if api_rows else fd_rows


def _snapshot_source(api_football: dict[str, Any], football_data: dict[str, Any]) -> str:
    api_rows = list(api_football.get("team_form", []))
    fd_rows = list(football_data.get("team_form", []))
    if any(row.get("Status") == "Live API-Football" for row in api_rows):
        return api_football.get("research_snapshot_source", "API-Football live research snapshot")
    if any(row.get("Status") == LIVE_FOOTBALL_DATA_STATUS for row in fd_rows):
        return "football-data.org live team-match fallback snapshot"
    if any(row.get("Status") == PARTIAL_FOOTBALL_DATA_STATUS for row in fd_rows):
        return "football-data.org partial team-match fallback snapshot"
    if any(row.get("Status") == LIMITED_FOOTBALL_DATA_STATUS for row in fd_rows):
        return "football-data.org limited-sample fallback snapshot"
    if any(row.get("Status") == STALE_FOOTBALL_DATA_STATUS for row in fd_rows):
        return "football-data.org historical fallback snapshot"
    return api_football.get("research_snapshot_source", "Unavailable research snapshot")


def build_api_compatibility_summary(
    *,
    team_form: list[dict[str, Any]],
    player_summary: dict[str, Any],
    weather: dict[str, Any],
) -> list[dict[str, Any]]:
    has_fixture_history = any(
        row.get("Status") in {"Live API-Football", LIVE_FOOTBALL_DATA_STATUS}
        for row in team_form
    )
    has_partial_football_data = any(row.get("Status") == PARTIAL_FOOTBALL_DATA_STATUS for row in team_form)
    has_limited_football_data = any(row.get("Status") == LIMITED_FOOTBALL_DATA_STATUS for row in team_form)
    has_stale_football_data = any(row.get("Status") == STALE_FOOTBALL_DATA_STATUS for row in team_form)
    squad_loaded = int(player_summary.get("Squad players loaded") or 0) > 0
    weather_fillable = not weather.get("missing")
    rows = []
    for cell in [
        "Last 5",
        "Last 10",
        "Wins/draws/losses",
        "Goals scored/conceded",
        "BTTS rate",
        "Over 2.5 rate",
        "Clean sheets",
        "Failed to score",
        "Home/away split",
    ]:
        rows.append(
            {
                "Dashboard cell": cell,
                "Needed endpoint": "/fixtures",
                "Required params": "team, season, from, to",
                "Current params available": "team_id, event year, previous year, date range",
                "API returned data": (
                    "Yes"
                    if has_fixture_history
                    or has_partial_football_data
                    or has_limited_football_data
                    or has_stale_football_data
                    else "No"
                ),
                "Status": (
                    "Fillable now"
                    if has_fixture_history
                    else "Partial Last 5 only"
                    if has_partial_football_data
                    else "Limited sample only"
                    if has_limited_football_data
                    else "Historical/stale only"
                    if has_stale_football_data
                    else "Not returned by current API request"
                ),
                "Notes": "Uses completed fixtures sorted by fixture date descending.",
            }
        )
    for cell in ["Player names", "Position"]:
        rows.append(
            {
                "Dashboard cell": cell,
                "Needed endpoint": "/players/squads",
                "Required params": "team",
                "Current params available": "team_id",
                "API returned data": "Yes" if squad_loaded else "No",
                "Status": "Fillable now" if squad_loaded else "Not returned by current API request",
                "Notes": "Squad endpoint only; confirm lineup manually.",
            }
        )
    for cell, status, endpoint in [
        ("Expected starter", "Fillable with lineup endpoint", "/fixtures/lineups"),
        ("Minutes per match", "Fillable with another endpoint", "/players"),
        ("Goals per 90", "Fillable with another endpoint", "/players"),
        ("Assists per 90", "Fillable with another endpoint", "/players"),
        ("Shots per 90", "Fillable with another endpoint", "/players"),
        ("Injury status", "Fillable with injuries endpoint if available", "/injuries"),
        ("Rotation risk", "Needs manual input", "Manual review"),
    ]:
        rows.append(
            {
                "Dashboard cell": cell,
                "Needed endpoint": endpoint,
                "Required params": "team, fixture, player, season as applicable",
                "Current params available": "team_id only" if squad_loaded else "Unavailable",
                "API returned data": "No",
                "Status": status,
                "Notes": "Do not infer from squad list alone.",
            }
        )
    for cell, status, endpoint, notes in [
        ("Venue", "Fillable with another endpoint", "/fixtures", "Requires fixture-level venue response."),
        ("Referee", "Fillable with another endpoint", "/fixtures", "Requires fixture-level referee response."),
        ("Weather", "Fillable now" if weather_fillable else "Needs manual input", "Open-Meteo", "Open-Meteo needs manual latitude/longitude."),
        ("Travel", "Needs manual input", "Manual review", "Travel is not inferred without reliable venue coordinates."),
        ("Rest/fatigue", "Fillable now" if has_fixture_history else "Needs manual input", "/fixtures", "Needs fixture history and schedule review."),
    ]:
        rows.append(
            {
                "Dashboard cell": cell,
                "Needed endpoint": endpoint,
                "Required params": "varies",
                "Current params available": "manual coordinates" if cell == "Weather" and weather_fillable else "partial",
                "API returned data": "Yes" if (cell == "Weather" and weather_fillable) else "No",
                "Status": status,
                "Notes": notes,
            }
        )
    return rows
