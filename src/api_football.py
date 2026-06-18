"""Safe API-Football client helpers for soccer research context."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.research_lab import parse_api_football_headers

API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
NO_FIXTURE_HISTORY = "No fixture history returned by season/date range"
SQUAD_ONLY_NOTE = "Squad only — detailed player stats unavailable"
TEAM_ALIASES = {
    "USA": ["United States"],
    "United States": ["USA"],
    "DR Congo": ["Congo DR"],
    "DRC": ["Congo DR"],
    "Curacao": ["Curaçao"],
    "Curaçao": ["Curacao"],
    "Ivory Coast": ["Côte d'Ivoire"],
    "Côte d'Ivoire": ["Ivory Coast"],
    "England": ["England"],
    "Croatia": ["Croatia"],
    "Portugal": ["Portugal"],
}


class ApiFootballError(RuntimeError):
    """Raised when API-Football cannot return a usable response."""


def read_api_football_key(secrets: Mapping[str, Any] | None) -> str | None:
    try:
        value = str(secrets.get("API_FOOTBALL_KEY", "")).strip() if secrets else ""
    except (AttributeError, FileNotFoundError, RuntimeError):
        value = ""
    return value or None


def fetch_api_football_json(
    path: str,
    params: Mapping[str, Any],
    api_key: str,
    *,
    timeout: float = 15.0,
) -> tuple[Any, dict[str, Any]]:
    url = f"{API_FOOTBALL_BASE_URL}{path}?{urlencode(params)}"
    request = Request(url, headers={"x-apisports-key": api_key})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = dict(response.headers.items()) if hasattr(response, "headers") else {}
            status = getattr(response, "status", None)
            return payload, parse_api_football_headers(headers, status_code=status)
    except HTTPError as exc:
        raise ApiFootballError(f"API-Football returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ApiFootballError("Could not connect to API-Football.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ApiFootballError("API-Football returned an unreadable response.") from exc


def summarize_team_form(
    team_name: str,
    fixtures: list[Mapping[str, Any]],
    *,
    team_id: int | str | None = None,
) -> dict[str, Any]:
    rows = []
    for fixture in fixtures:
        teams = fixture.get("teams", {})
        goals = fixture.get("goals", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        home_id = home.get("id")
        away_id = away.get("id")
        is_home = (
            str(home.get("name", "")).lower() == team_name.lower()
            or (team_id is not None and str(home_id) == str(team_id))
        )
        is_away = (
            str(away.get("name", "")).lower() == team_name.lower()
            or (team_id is not None and str(away_id) == str(team_id))
        )
        if not is_home and not is_away:
            continue
        goals_for = goals.get("home") if is_home else goals.get("away")
        goals_against = goals.get("away") if is_home else goals.get("home")
        if not isinstance(goals_for, int) or not isinstance(goals_against, int):
            continue
        if goals_for > goals_against:
            result = "W"
        elif goals_for == goals_against:
            result = "D"
        else:
            result = "L"
        rows.append(
            {
                "result": result,
                "goals_for": goals_for,
                "goals_against": goals_against,
                "home_away": "Home" if is_home else "Away",
            }
        )

    if not rows:
        return unavailable_team_row(team_name, NO_FIXTURE_HISTORY)

    recent_10 = rows[:10]
    recent_5 = rows[:5]
    games = len(recent_10)
    wins = sum(row["result"] == "W" for row in recent_10)
    draws = sum(row["result"] == "D" for row in recent_10)
    losses = sum(row["result"] == "L" for row in recent_10)
    scored = sum(row["goals_for"] for row in recent_10)
    conceded = sum(row["goals_against"] for row in recent_10)
    btts = sum(row["goals_for"] > 0 and row["goals_against"] > 0 for row in recent_10)
    over_25 = sum(row["goals_for"] + row["goals_against"] > 2.5 for row in recent_10)
    clean_sheets = sum(row["goals_against"] == 0 for row in recent_10)
    failed_to_score = sum(row["goals_for"] == 0 for row in recent_10)
    split = _home_away_split(recent_10)

    return {
        "Team": team_name,
        "Status": "Live API-Football",
        "Last 5": "-".join(row["result"] for row in recent_5),
        "Last 10": "-".join(row["result"] for row in recent_10),
        "Wins": wins,
        "Draws": draws,
        "Losses": losses,
        "Goals scored": scored,
        "Goals conceded": conceded,
        "Goal differential": scored - conceded,
        "BTTS rate": _rate(btts, games),
        "Over 2.5 rate": _rate(over_25, games),
        "Clean sheets": clean_sheets,
        "Failed to score": failed_to_score,
        "Home/away split": split,
    }


def parse_squad_players(team_name: str, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response") or []
    if not response:
        return []
    players = response[0].get("players", []) if isinstance(response[0], dict) else []
    rows = []
    for player in players:
        if not isinstance(player, dict):
            continue
        rows.append(
            {
                "Name": player.get("name", "Unknown"),
                "Team": team_name,
                "Position": player.get("position", "Unknown"),
                "Expected starter": "Unknown until lineup confirmed",
                "Minutes per match": SQUAD_ONLY_NOTE,
                "Goals per 90": SQUAD_ONLY_NOTE,
                "Assists per 90": SQUAD_ONLY_NOTE,
                "Shots per 90": SQUAD_ONLY_NOTE,
                "Injury status": "Unavailable from squad endpoint",
                "Rotation risk": "Manual review required",
                "Notes": SQUAD_ONLY_NOTE,
            }
        )
    return rows


def parse_fixture_context(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response") or []
    if not response:
        return unavailable_fixture_context_rows()
    fixture = response[0].get("fixture", {}) if isinstance(response[0], dict) else {}
    venue = fixture.get("venue") or {}
    referee = fixture.get("referee") or "Unavailable — referee not returned by fixture endpoint"
    return [
        {
            "Factor": "Venue",
            "Value": venue.get("name") or "Unavailable — fixture context not returned",
            "Betting note": "Confirm venue manually before using travel/weather assumptions.",
        },
        {
            "Factor": "Referee",
            "Value": referee,
            "Betting note": "Cards and fouls markets need referee confirmation.",
        },
    ]


def unavailable_fixture_context_rows() -> list[dict[str, Any]]:
    return [
        {
            "Factor": "Venue",
            "Value": "Unavailable — fixture context not returned",
            "Betting note": "Manual venue confirmation required.",
        },
        {
            "Factor": "Referee",
            "Value": "Unavailable — referee not returned by fixture endpoint",
            "Betting note": "Cards and fouls markets need referee confirmation.",
        },
    ]


def unavailable_team_row(team_name: str, reason: str) -> dict[str, Any]:
    return {
        "Team": team_name,
        "Status": reason,
        "Last 5": reason,
        "Last 10": reason,
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
        "Home/away split": "",
    }


def build_api_football_snapshot(
    *,
    api_key: str | None,
    home_team: str,
    away_team: str,
    event_date: str,
) -> dict[str, Any]:
    diagnostics = _default_diagnostics(api_key, home_team, away_team)
    if not api_key:
        reason = "Unavailable - API key missing"
        diagnostics["Last safe API error message"] = reason
        return {
            "team_form": [
                unavailable_team_row(home_team, reason),
                unavailable_team_row(away_team, reason),
            ],
            "players": [_unavailable_player_row(reason)],
            "context": [
                {"Factor": "Venue", "Value": reason, "Betting note": "Manual venue confirmation required."},
                {"Factor": "Referee", "Value": reason, "Betting note": "Manual referee confirmation required."},
            ],
            "usage": [parse_api_football_headers({})],
            "missing": ["API_FOOTBALL_KEY"],
            "diagnostics": diagnostics,
        }

    usage_rows = []
    missing = []
    team_rows = []
    player_rows = []
    context_rows = []
    team_lookup = {}
    total_fixture_rows_used = 0
    for team_name in [home_team, away_team]:
        team_id = None
        matched_name = ""
        side = "Home" if team_name == home_team else "Away"
        try:
            diagnostics["API-Football team search status"] = "Attempted"
            for candidate in team_search_candidates(team_name):
                team_payload, usage = fetch_api_football_json("/teams", {"search": candidate}, api_key)
                usage_rows.append(usage)
                response = team_payload.get("response") or []
                if response:
                    team = response[0].get("team", {})
                    team_id = team.get("id")
                    matched_name = str(team.get("name") or candidate)
                    break
        except ApiFootballError as exc:
            message = f"{team_name}: {exc}"
            missing.append(message)
            diagnostics["Last safe API error message"] = message

        if team_id is None:
            team_rows.append(unavailable_team_row(team_name, "Unavailable - team not found"))
            continue

        team_lookup[team_name] = {"id": team_id, "matched_name": matched_name}
        diagnostics[f"{side} team API-Football team ID"] = team_id
        diagnostics[f"{side} team matched name"] = matched_name

        fixture_rows = []
        try:
            fixture_rows, fixture_usage = fetch_fixture_history_with_fallbacks(
                api_key=api_key,
                team_id=team_id,
                team_name=matched_name or team_name,
                event_date=event_date,
                diagnostics=diagnostics,
                side=side,
            )
            usage_rows.extend(fixture_usage)
        except ApiFootballError as exc:
            message = f"{team_name} fixtures: {exc}"
            missing.append(message)
            diagnostics["Last safe API error message"] = message
            team_rows.append(unavailable_team_row(team_name, "Unavailable - fixture request failed"))
        else:
            diagnostics[f"Fixture history rows returned for {side.lower()} team"] = len(fixture_rows)
            total_fixture_rows_used += len(fixture_rows)
            team_rows.append(
                summarize_team_form(
                    matched_name or team_name,
                    fixture_rows,
                    team_id=team_id,
                )
            )

        try:
            diagnostics["Squad request attempted"] = "Yes"
            squad_payload, usage = fetch_api_football_json(
                "/players/squads",
                {"team": team_id},
                api_key,
            )
            usage_rows.append(usage)
            squad_rows = parse_squad_players(matched_name or team_name, squad_payload)
            diagnostics[f"Squad rows returned for {side.lower()} team"] = len(squad_rows)
            player_rows.extend(squad_rows[:15])
        except ApiFootballError as exc:
            message = f"{team_name} squad: {exc}"
            missing.append(message)
            diagnostics["Last safe API error message"] = message

    try:
        fixture_payload, usage = fetch_api_football_json(
            "/fixtures",
            {"date": event_date, "team": ""},
            api_key,
        )
        usage_rows.append(usage)
        context_rows.extend(parse_fixture_context(fixture_payload))
    except ApiFootballError as exc:
        diagnostics["Last safe API error message"] = str(exc)
        context_rows.extend(unavailable_fixture_context_rows())

    if not context_rows:
        context_rows.extend(unavailable_fixture_context_rows())

    if not player_rows:
        diagnostics["Last safe API error message"] = (
            diagnostics.get("Last safe API error message")
            or "Squad endpoint returned no players"
        )

    return {
        "team_form": team_rows,
        "players": player_rows or [_unavailable_player_row("Squad endpoint returned no players")],
        "context": context_rows,
        "usage": usage_rows or [parse_api_football_headers({})],
        "missing": missing,
        "diagnostics": diagnostics,
        "team_mappings": team_lookup,
        "player_summary": {
            "Squad players loaded": len(player_rows),
            "Detailed player stats loaded": 0,
            "Confirmed lineup loaded": "No",
            "Player prop confidence": "Reduced until lineup confirmed",
        },
        "research_snapshot_source": "API-Football live research snapshot",
        "fixture_rows_used": total_fixture_rows_used,
        "squad_rows_used": len(player_rows),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def team_search_candidates(team_name: str) -> list[str]:
    normalized = " ".join(team_name.strip().split())
    candidates = [normalized]
    aliases = TEAM_ALIASES.get(normalized, [])
    candidates.extend(aliases)
    for key, values in TEAM_ALIASES.items():
        if normalized in values:
            candidates.append(key)
    deduped = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def fetch_fixture_history_with_fallbacks(
    *,
    api_key: str,
    team_id: int | str,
    team_name: str,
    event_date: str,
    diagnostics: dict[str, Any],
    side: str,
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]]]:
    diagnostics["Fixture history request attempted"] = "Yes"
    start_date, end_date, seasons = _fixture_date_window(event_date)
    diagnostics[f"{side} fixture method used"] = "season/date-range"
    diagnostics[f"{side} seasons tried"] = ", ".join(str(season) for season in seasons)
    diagnostics[f"{side} date range used"] = f"{start_date} to {end_date}"
    params_list = [
        {
            "team": team_id,
            "season": season,
            "from": start_date,
            "to": end_date,
        }
        for season in seasons
    ]
    usage_rows = []
    safe_attempts = []
    last_payload: Mapping[str, Any] | None = None
    last_error = ""
    combined_rows: list[Mapping[str, Any]] = []
    rows_by_season = {}
    for params in params_list:
        safe_attempts.append({"path": "/fixtures", "params": params})
        try:
            payload, usage = fetch_api_football_json("/fixtures", params, api_key)
        except ApiFootballError as exc:
            last_error = str(exc)
            diagnostics["Last safe API error message"] = last_error
            continue
        usage_rows.append(usage)
        last_payload = payload if isinstance(payload, Mapping) else {}
        payload_errors = last_payload.get("errors") or {}
        if payload_errors:
            diagnostics["Last safe API error message"] = json.dumps(
                payload_errors,
                ensure_ascii=True,
            )
        response = last_payload.get("response") or []
        rows_by_season[str(params["season"])] = len(response)
        combined_rows.extend(response)

    diagnostics[f"{side} fixture endpoint used"] = "/fixtures"
    diagnostics[f"{side} fixture endpoint params used"] = json.dumps(
        [_safe_params(params) for params in params_list],
        ensure_ascii=True,
    )
    diagnostics[f"{side} rows returned by season"] = json.dumps(
        rows_by_season,
        ensure_ascii=True,
    )
    final_rows = _latest_completed_fixtures(combined_rows)
    diagnostics[f"{side} completed fixtures used"] = len(
        [row for row in final_rows if _is_completed_fixture(row)]
    )
    diagnostics[f"{side} final fixtures used for Last 10"] = len(final_rows[:10])
    if final_rows:
        diagnostics[f"{side} fixture response body summary"] = (
            f"Combined {len(combined_rows)} rows; using {len(final_rows[:10])} latest fixtures."
        )
        return final_rows[:10], usage_rows

    diagnostics[f"{side} fixture endpoint attempts"] = json.dumps(
        [{"path": item["path"], "params": _safe_params(item["params"])} for item in safe_attempts]
    )
    diagnostics[f"{side} fixture response body summary"] = (
        _payload_summary(last_payload or {}) if last_payload is not None else last_error
    )
    return [], usage_rows


def _fixture_date_window(event_date: str) -> tuple[str, str, list[int]]:
    try:
        end = datetime.fromisoformat(event_date.split("T", 1)[0]).date()
    except (TypeError, ValueError, AttributeError):
        end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=548)
    seasons = [end.year, end.year - 1]
    return start.isoformat(), end.isoformat(), seasons


def _latest_completed_fixtures(rows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    deduped = {}
    for row in rows:
        fixture = row.get("fixture", {}) if isinstance(row, Mapping) else {}
        fixture_id = fixture.get("id")
        key = fixture_id if fixture_id is not None else json.dumps(row, sort_keys=True, default=str)
        deduped[key] = row
    all_rows = list(deduped.values())
    completed = [row for row in all_rows if _is_completed_fixture(row)]
    usable = completed if completed else all_rows
    return sorted(
        usable,
        key=lambda row: str(row.get("fixture", {}).get("date", "")),
        reverse=True,
    )


def _is_completed_fixture(row: Mapping[str, Any]) -> bool:
    status = row.get("fixture", {}).get("status", {})
    short = str(status.get("short", "")).upper()
    return short in {"FT", "AET", "PEN"}


def _safe_params(params: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in params.items()}


def _payload_summary(payload: Mapping[str, Any]) -> str:
    errors = payload.get("errors")
    message = payload.get("message")
    results = payload.get("results")
    response = payload.get("response") or []
    summary = {
        "results": results if results is not None else len(response),
        "errors": errors or {},
    }
    if message:
        summary["message"] = message
    return json.dumps(summary, ensure_ascii=True)


def _default_diagnostics(
    api_key: str | None,
    home_team: str,
    away_team: str,
) -> dict[str, Any]:
    return {
        "API-Football key found": "Yes" if api_key else "No",
        "API-Football team search status": "Not attempted",
        "Home team API-Football team ID": "",
        "Away team API-Football team ID": "",
        "Home team matched name": home_team,
        "Away team matched name": away_team,
        "Fixture history request attempted": "No",
        "Fixture history rows returned for home team": 0,
        "Fixture history rows returned for away team": 0,
        "Squad request attempted": "No",
        "Squad rows returned for home team": 0,
        "Squad rows returned for away team": 0,
        "Player stats request attempted": "No",
        "Player stats rows returned": 0,
        "Weather request attempted": "No",
        "Weather coordinates available": "No",
        "Last safe API error message": "",
    }


def _home_away_split(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Unavailable"
    parts = []
    for side in ["Home", "Away"]:
        side_rows = [row for row in rows if row["home_away"] == side]
        if side_rows:
            wins = sum(row["result"] == "W" for row in side_rows)
            draws = sum(row["result"] == "D" for row in side_rows)
            losses = sum(row["result"] == "L" for row in side_rows)
            parts.append(f"{side}: {wins}-{draws}-{losses}")
    return " | ".join(parts) if parts else "Unavailable"


def _rate(count: int, total: int) -> str:
    return "Unavailable" if total == 0 else f"{count / total:.1%}"


def _unavailable_player_row(reason: str) -> dict[str, Any]:
    return {
        "Name": reason,
        "Team": "",
        "Position": "",
        "Expected starter": reason,
        "Minutes per match": "",
        "Goals per 90": "",
        "Assists per 90": "",
        "Shots per 90": "",
        "Injury status": reason,
        "Rotation risk": "Manual review required",
        "Notes": "Manual player confirmation required.",
    }
