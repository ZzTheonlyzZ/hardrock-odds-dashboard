"""Optional football-data.org backup client for Research Lab context."""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.research_lab import parse_football_data_headers

FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"
NO_FOOTBALL_DATA_HISTORY = "No team match history returned by football-data.org mapping."
LIVE_FOOTBALL_DATA_STATUS = "Live football-data.org team-match history"
PARTIAL_FOOTBALL_DATA_STATUS = "Partial football-data.org sample — Last 5 threshold met, Last 10 not met."
LIMITED_FOOTBALL_DATA_STATUS = "Limited football-data.org sample — not enough rows for Last 5 / Last 10."
STALE_FOOTBALL_DATA_STATUS = "Historical football-data.org data only — context only"
FOOTBALL_DATA_ALIASES = {
    "Canada": ["Canada", "CAN"],
    "Qatar": ["Qatar", "QAT"],
    "USA": ["United States", "USA"],
    "United States": ["United States", "USA"],
    "England": ["England", "ENG"],
    "Croatia": ["Croatia", "CRO"],
    "Curacao": ["Curaçao", "CUW"],
    "Curaçao": ["Curacao", "CUW"],
    "Ivory Coast": ["Côte d’Ivoire", "Côte d'Ivoire", "CIV"],
    "Côte d’Ivoire": ["Ivory Coast", "CIV"],
    "DR Congo": ["Congo DR", "COD"],
    "Congo DR": ["DR Congo", "COD"],
}


class FootballDataError(RuntimeError):
    """Raised when football-data.org cannot return a usable response."""


def read_football_data_key(secrets: Mapping[str, Any] | None) -> str | None:
    try:
        value = str(secrets.get("FOOTBALL_DATA_KEY", "")).strip() if secrets else ""
    except (AttributeError, FileNotFoundError, RuntimeError):
        value = ""
    return value or None


def fetch_football_data_json(
    path: str,
    params: Mapping[str, Any],
    api_key: str,
    *,
    timeout: float = 15.0,
) -> tuple[Any, dict[str, Any]]:
    url = f"{FOOTBALL_DATA_BASE_URL}{path}?{urlencode(params)}"
    request = Request(url, headers={"X-Auth-Token": api_key})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = dict(response.headers.items()) if hasattr(response, "headers") else {}
            status = getattr(response, "status", None)
            return payload, parse_football_data_headers(headers, status_code=status)
    except HTTPError as exc:
        raise FootballDataError(f"football-data.org returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise FootballDataError("Could not connect to football-data.org.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FootballDataError("football-data.org returned an unreadable response.") from exc


def backup_context_row(api_key: str | None) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    if not api_key:
        return (
            {
                "Factor": "football-data.org backup",
                "Value": "Unavailable - API key missing",
                "Betting note": "Optional backup not connected; use API-Football/manual context.",
            },
            parse_football_data_headers({}),
            ["FOOTBALL_DATA_KEY"],
        )
    return (
        {
            "Factor": "football-data.org backup",
            "Value": "Configured",
            "Betting note": "Optional backup key available if API-Football data is incomplete.",
        },
        parse_football_data_headers({}),
        [],
    )


def build_football_data_snapshot(
    *,
    api_key: str | None,
    home_team: str,
    away_team: str,
    event_date: str,
    competition_code: str = "WC",
) -> dict[str, Any]:
    diagnostics = _default_diagnostics(api_key, home_team, away_team, competition_code)
    if not api_key:
        diagnostics["football-data.org last safe error"] = "Unavailable - API key missing"
        return {
            "team_form": [
                unavailable_football_data_team_row(home_team),
                unavailable_football_data_team_row(away_team),
            ],
            "context": [_context_row("Unavailable - API key missing")],
            "usage": [parse_football_data_headers({})],
            "missing": ["FOOTBALL_DATA_KEY"],
            "diagnostics": diagnostics,
            "team_mappings": {},
            "match_rows_used": 0,
            "data_freshness": "unavailable",
        }

    event_year = _event_year(event_date)
    seasons = _seasons_to_try(event_year)
    diagnostics["football-data.org seasons tried"] = ", ".join(str(season) for season in seasons)
    usage_rows: list[dict[str, Any]] = []
    missing: list[str] = []
    team_catalog: list[Mapping[str, Any]] = []
    endpoint_attempts: list[dict[str, Any]] = []
    errors: list[str] = []

    for season in seasons:
        params = {"season": season}
        endpoint_attempts.append({"path": f"/competitions/{competition_code}/teams", "params": params})
        try:
            payload, usage = fetch_football_data_json(
                f"/competitions/{competition_code}/teams",
                params,
                api_key,
            )
        except FootballDataError as exc:
            errors.append(f"teams season {season}: {exc}")
            continue
        usage_rows.append(usage)
        teams = payload.get("teams") or []
        diagnostics[f"football-data.org teams rows season {season}"] = len(teams)
        if teams:
            team_catalog = teams
            diagnostics["football-data.org team season used"] = season
            break
        message = payload.get("message") or payload.get("error") or ""
        if message:
            errors.append(f"teams season {season}: {message}")

    team_form_rows: list[dict[str, Any]] = []
    team_mappings: dict[str, Any] = {}
    all_match_rows: list[Mapping[str, Any]] = []
    for side, selected_team in [("Home", home_team), ("Away", away_team)]:
        mapping = match_football_data_team(selected_team, team_catalog)
        team_mappings[selected_team] = mapping
        diagnostics[f"{side} football-data.org selected team"] = selected_team
        diagnostics[f"{side} football-data.org mapped team name"] = mapping.get("mapped_name", "")
        diagnostics[f"{side} football-data.org mapped team id"] = mapping.get("team_id", "")
        diagnostics[f"{side} football-data.org mapping method"] = mapping.get("method", "not mapped")
        if not mapping.get("team_id"):
            team_form_rows.append(unavailable_football_data_team_row(selected_team))
            missing.append(f"{selected_team}: football-data.org team not mapped")
            continue

        matches, team_usage, team_errors, team_attempts = fetch_team_matches_with_fallbacks(
            api_key=api_key,
            team_id=mapping["team_id"],
            event_date=event_date,
        )
        usage_rows.extend(team_usage)
        errors.extend(team_errors)
        endpoint_attempts.extend(team_attempts)
        diagnostics[f"{side} football-data.org match rows returned"] = len(matches)
        all_match_rows.extend(matches)
        team_form_rows.append(
            summarize_football_data_team_form(
                selected_team,
                matches,
                team_id=mapping["team_id"],
                event_date=event_date,
            )
        )

    comp_matches, comp_usage, comp_errors, comp_attempts = fetch_competition_matches_with_fallbacks(
        api_key=api_key,
        competition_code=competition_code,
        event_date=event_date,
        seasons=seasons,
    )
    usage_rows.extend(comp_usage)
    errors.extend(comp_errors)
    endpoint_attempts.extend(comp_attempts)
    diagnostics["football-data.org competition match rows returned"] = len(comp_matches)

    used_rows = sum(
        1
        for row in team_form_rows
        if row.get("Status")
        in {
            LIVE_FOOTBALL_DATA_STATUS,
            PARTIAL_FOOTBALL_DATA_STATUS,
            LIMITED_FOOTBALL_DATA_STATUS,
            STALE_FOOTBALL_DATA_STATUS,
        }
    )
    match_rows_used = len(_dedupe_matches(all_match_rows))
    per_team_counts = [
        int(row.get("football-data.org rows used") or 0)
        for row in team_form_rows
    ]
    min_rows = min(per_team_counts) if per_team_counts else 0
    diagnostics["football-data.org match rows used"] = match_rows_used
    diagnostics["football-data.org rows per team"] = json.dumps(
        {
            row.get("Team", ""): int(row.get("football-data.org rows used") or 0)
            for row in team_form_rows
        },
        ensure_ascii=True,
    )
    diagnostics["football-data.org minimum rows per team"] = min_rows
    diagnostics["football-data.org Last 5 threshold met"] = "Yes" if min_rows >= 5 else "No"
    diagnostics["football-data.org Last 10 threshold met"] = "Yes" if min_rows >= 10 else "No"
    diagnostics["football-data.org team-form sample quality"] = _sample_quality_label(min_rows)
    diagnostics["football-data.org endpoints tested"] = json.dumps(endpoint_attempts, ensure_ascii=True)
    diagnostics["football-data.org errors"] = "; ".join(errors[:5])
    diagnostics["football-data.org fields returned"] = (
        "id, utcDate, status, homeTeam, awayTeam, score"
        if match_rows_used
        else ""
    )
    if errors:
        diagnostics["football-data.org last safe error"] = errors[-1]

    freshness = "unavailable"
    if any(row.get("Status") == LIVE_FOOTBALL_DATA_STATUS for row in team_form_rows):
        freshness = "current"
    elif any(row.get("Status") == PARTIAL_FOOTBALL_DATA_STATUS for row in team_form_rows):
        freshness = "partial"
    elif any(row.get("Status") == LIMITED_FOOTBALL_DATA_STATUS for row in team_form_rows):
        freshness = "limited"
    elif any(row.get("Status") == STALE_FOOTBALL_DATA_STATUS for row in team_form_rows):
        freshness = "historical"
    if not used_rows:
        missing.append(NO_FOOTBALL_DATA_HISTORY)

    return {
        "team_form": team_form_rows,
        "context": [
            _context_row(
                "Team-match history returned"
                if used_rows
                else NO_FOOTBALL_DATA_HISTORY
            )
        ],
        "usage": usage_rows or [parse_football_data_headers({})],
        "missing": missing,
        "diagnostics": diagnostics,
        "team_mappings": team_mappings,
        "match_rows_used": match_rows_used,
        "data_freshness": freshness,
    }


def fetch_team_matches_with_fallbacks(
    *,
    api_key: str,
    team_id: int | str,
    event_date: str,
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    date_from, date_to = _match_window(event_date)
    params_list = [
        {"dateFrom": date_from, "dateTo": date_to, "status": "FINISHED", "limit": 20},
        {"status": "FINISHED", "limit": 20},
    ]
    rows: list[Mapping[str, Any]] = []
    usage_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    attempts: list[dict[str, Any]] = []
    for params in params_list:
        attempts.append({"path": f"/teams/{team_id}/matches", "params": dict(params)})
        try:
            payload, usage = fetch_football_data_json(
                f"/teams/{team_id}/matches",
                params,
                api_key,
            )
        except FootballDataError as exc:
            errors.append(f"team matches {team_id}: {exc}")
            continue
        usage_rows.append(usage)
        matches = payload.get("matches") or []
        rows.extend(matches)
        message = payload.get("message") or payload.get("error") or ""
        if message and not matches:
            errors.append(f"team matches {team_id}: {message}")
    return _dedupe_matches(rows), usage_rows, errors, attempts


def fetch_competition_matches_with_fallbacks(
    *,
    api_key: str,
    competition_code: str,
    event_date: str,
    seasons: list[int],
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    date_from, date_to = _match_window(event_date)
    rows: list[Mapping[str, Any]] = []
    usage_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    attempts: list[dict[str, Any]] = []
    for season in seasons:
        params = {
            "season": season,
            "dateFrom": date_from,
            "dateTo": date_to,
            "status": "FINISHED",
        }
        attempts.append({"path": f"/competitions/{competition_code}/matches", "params": params})
        try:
            payload, usage = fetch_football_data_json(
                f"/competitions/{competition_code}/matches",
                params,
                api_key,
            )
        except FootballDataError as exc:
            errors.append(f"competition matches season {season}: {exc}")
            continue
        usage_rows.append(usage)
        matches = payload.get("matches") or []
        rows.extend(matches)
        message = payload.get("message") or payload.get("error") or ""
        if message and not matches:
            errors.append(f"competition matches season {season}: {message}")
    return _dedupe_matches(rows), usage_rows, errors, attempts


def match_football_data_team(selected_team: str, teams: list[Mapping[str, Any]]) -> dict[str, Any]:
    aliases = _aliases_for(selected_team)
    exact = _match_team_by(lambda team, candidate: str(team.get("name", "")) == candidate, teams, aliases)
    if exact:
        return _mapping(selected_team, exact, "exact team name")
    code = _match_team_by(
        lambda team, candidate: str(team.get("tla", "")).upper() == candidate.upper(),
        teams,
        aliases,
    )
    if code:
        return _mapping(selected_team, code, "country code alias")
    normalized = _match_team_by(
        lambda team, candidate: _normalize(team.get("name", "")) == _normalize(candidate),
        teams,
        aliases,
    )
    if normalized:
        return _mapping(selected_team, normalized, "normalized name")
    return {"selected_team": selected_team, "mapped_name": "", "team_id": "", "method": "not mapped"}


def summarize_football_data_team_form(
    team_name: str,
    matches: list[Mapping[str, Any]],
    *,
    team_id: int | str,
    event_date: str,
) -> dict[str, Any]:
    rows = []
    for match in sorted(matches, key=lambda row: str(row.get("utcDate", "")), reverse=True):
        if str(match.get("status", "")).upper() != "FINISHED":
            continue
        home = match.get("homeTeam", {})
        away = match.get("awayTeam", {})
        score = (match.get("score", {}) or {}).get("fullTime", {})
        is_home = str(home.get("id")) == str(team_id)
        is_away = str(away.get("id")) == str(team_id)
        if not is_home and not is_away:
            continue
        home_goals = score.get("home")
        away_goals = score.get("away")
        if not isinstance(home_goals, int) or not isinstance(away_goals, int):
            continue
        goals_for = home_goals if is_home else away_goals
        goals_against = away_goals if is_home else home_goals
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
                "date": str(match.get("utcDate", "")),
            }
        )

    if not rows:
        return unavailable_football_data_team_row(team_name)

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
    latest_date = _parse_date(rows[0]["date"])
    event = _parse_date(event_date)
    days_since = (event - latest_date).days if event and latest_date else None
    if not _is_current_or_recent(rows, event_date):
        status = STALE_FOOTBALL_DATA_STATUS
    elif games >= 10:
        status = LIVE_FOOTBALL_DATA_STATUS
    elif games >= 5:
        status = PARTIAL_FOOTBALL_DATA_STATUS
    elif games >= 2:
        status = LIMITED_FOOTBALL_DATA_STATUS
    else:
        return unavailable_football_data_team_row(team_name)
    return {
        "Team": team_name,
        "Status": status,
        "Last 5": (
            "-".join(row["result"] for row in recent_5)
            if games >= 5
            else LIMITED_FOOTBALL_DATA_STATUS
        ),
        "Last 10": (
            "-".join(row["result"] for row in recent_10)
            if games >= 10
            else "Limited football-data.org sample — Last 10 threshold not met."
        ),
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
        "Home/away split": _home_away_split(recent_10),
        "Rest/fatigue": f"{days_since} days since last match" if days_since is not None else "Needs schedule review",
        "football-data.org rows used": games,
        "Team-form sample quality": _sample_quality_label(games),
        "Last 5 threshold met": "Yes" if games >= 5 else "No",
        "Last 10 threshold met": "Yes" if games >= 10 else "No",
        "Model support": "Can support model" if games >= 10 else "Context only — do not upgrade confidence",
    }


def unavailable_football_data_team_row(team_name: str) -> dict[str, Any]:
    return {
        "Team": team_name,
        "Status": NO_FOOTBALL_DATA_HISTORY,
        "Last 5": NO_FOOTBALL_DATA_HISTORY,
        "Last 10": NO_FOOTBALL_DATA_HISTORY,
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
        "Rest/fatigue": "",
        "football-data.org rows used": 0,
        "Team-form sample quality": "Unavailable",
        "Last 5 threshold met": "No",
        "Last 10 threshold met": "No",
        "Model support": "Do not upgrade confidence",
    }


def _default_diagnostics(api_key: str | None, home_team: str, away_team: str, competition_code: str) -> dict[str, Any]:
    return {
        "football-data.org key found": "Yes" if api_key else "No",
        "football-data.org competition code used": competition_code,
        "Home football-data.org selected team": home_team,
        "Away football-data.org selected team": away_team,
        "football-data.org seasons tried": "",
        "football-data.org match rows used": 0,
        "football-data.org data freshness": "unavailable",
        "football-data.org endpoints tested": "",
        "football-data.org errors": "",
    }


def _event_year(event_date: str) -> int:
    parsed = _parse_date(event_date)
    return parsed.year if parsed else datetime.now(timezone.utc).year


def _seasons_to_try(event_year: int) -> list[int]:
    seasons = [event_year, event_year - 1, 2024, 2023, 2022]
    deduped = []
    for season in seasons:
        if season not in deduped:
            deduped.append(season)
    return deduped


def _match_window(event_date: str) -> tuple[str, str]:
    end = _parse_date(event_date) or datetime.now(timezone.utc).date()
    start = end - timedelta(days=730)
    return start.isoformat(), end.isoformat()


def _parse_date(value: str):
    try:
        return datetime.fromisoformat(str(value).split("T", 1)[0]).date()
    except (TypeError, ValueError):
        return None


def _aliases_for(team_name: str) -> list[str]:
    aliases = [team_name]
    aliases.extend(FOOTBALL_DATA_ALIASES.get(team_name, []))
    normalized = _normalize(team_name)
    for key, values in FOOTBALL_DATA_ALIASES.items():
        candidates = [key] + values
        if any(_normalize(candidate) == normalized for candidate in candidates):
            aliases.extend(candidates)
    deduped = []
    for alias in aliases:
        if alias and alias not in deduped:
            deduped.append(alias)
    return deduped


def _match_team_by(predicate, teams: list[Mapping[str, Any]], candidates: list[str]):
    for candidate in candidates:
        for team in teams:
            if predicate(team, candidate):
                return team
    return None


def _mapping(selected_team: str, team: Mapping[str, Any], method: str) -> dict[str, Any]:
    return {
        "selected_team": selected_team,
        "mapped_name": team.get("name", ""),
        "team_id": team.get("id", ""),
        "method": method,
        "tla": team.get("tla", ""),
    }


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    ascii_text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch.lower() for ch in ascii_text if ch.isalnum())


def _dedupe_matches(rows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    deduped = {}
    for row in rows:
        match_id = row.get("id")
        key = match_id if match_id is not None else json.dumps(row, sort_keys=True, default=str)
        deduped[key] = row
    return sorted(deduped.values(), key=lambda row: str(row.get("utcDate", "")), reverse=True)


def _is_current_or_recent(rows: list[dict[str, Any]], event_date: str) -> bool:
    event_year = _event_year(event_date)
    years = [(_parse_date(row["date"]) or datetime.min.date()).year for row in rows]
    return any(year >= event_year - 1 for year in years)


def _home_away_split(rows: list[dict[str, Any]]) -> str:
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


def _sample_quality_label(row_count: int) -> str:
    if row_count >= 10:
        return "Last 10 threshold met — team form can support model"
    if row_count >= 5:
        return "Last 5 threshold met only — limited support"
    if row_count >= 2:
        return "Limited sample only"
    return "Team form unavailable"


def _context_row(value: str) -> dict[str, Any]:
    return {
        "Factor": "football-data.org team form",
        "Value": value,
        "Betting note": "Use as backup context only; final Hard Rock FL wager must be manually confirmed.",
    }
