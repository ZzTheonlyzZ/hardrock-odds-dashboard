"""Safe API capability audit helpers for Research Lab diagnostics."""

from __future__ import annotations

import json
from typing import Any, Mapping


MARKET_CELLS = [
    "Hard Rock FL exact odds",
    "Generic Hard Rock odds",
    "Consensus odds",
    "Implied probability",
    "No-vig probability",
    "Edge",
    "EV",
    "Kelly",
    "Manual confirmation requirement",
]

TEAM_CELLS = [
    "Last 5",
    "Last 10",
    "Wins/draws/losses",
    "Goals scored/conceded",
    "Goal differential",
    "BTTS rate",
    "Over 2.5 rate",
    "Clean sheets",
    "Failed to score",
    "Home/away split",
    "Rest/fatigue",
    "Standings/group context",
]

PLAYER_CELLS = [
    "Player names",
    "Position",
    "Expected starter",
    "Confirmed lineup",
    "Minutes per match",
    "Goals per 90",
    "Assists per 90",
    "Shots per 90",
    "Shots on target",
    "Anytime scorer relevance",
    "Injury status",
    "Rotation risk",
    "Penalty taker",
    "Set-piece taker",
]

CONTEXT_CELLS = [
    "Venue",
    "Referee",
    "Weather",
    "Travel",
    "Rest",
    "Motivation",
    "Group incentives",
]


def build_api_capability_audit(
    *,
    selected_event: Mapping[str, Any],
    scanner_data: Mapping[str, Any] | None,
    context_data: Mapping[str, Any],
    odds_key_found: bool,
    api_football_key_found: bool,
    football_data_key_found: bool,
    manual_coordinates_available: bool,
) -> dict[str, Any]:
    found_lines = list(scanner_data.get("found_lines", [])) if scanner_data else []
    diagnostics = dict(context_data.get("integration_diagnostics", {}))
    compatibility = list(context_data.get("compatibility_summary", []))
    raw_log = list(context_data.get("api_request_log", []))
    team_form_live = any(
        row.get("Status")
        in {"Live API-Football", "Live football-data.org team-match history"}
        for row in context_data.get("team_form", [])
    )
    football_data_live = any(
        row.get("Status") == "Live football-data.org team-match history"
        for row in context_data.get("team_form", [])
    )
    football_data_partial = any(
        row.get("Status") == "Partial football-data.org sample — Last 5 threshold met, Last 10 not met."
        for row in context_data.get("team_form", [])
    )
    football_data_limited = any(
        row.get("Status") == "Limited football-data.org sample — not enough rows for Last 5 / Last 10."
        for row in context_data.get("team_form", [])
    )
    football_data_historical = any(
        row.get("Status") == "Historical football-data.org data only — context only"
        for row in context_data.get("team_form", [])
    )
    squad_loaded = int(context_data.get("player_summary", {}).get("Squad players loaded") or 0) > 0
    weather_loaded = any(
        row.get("Factor") == "Weather" and "Unavailable" not in str(row.get("Value", ""))
        for row in context_data.get("context", [])
    )
    current_season_blocked = _contains_plan_block(diagnostics)
    historical_only = _historical_only(diagnostics)

    endpoints_tested = _endpoint_rows(
        selected_event=selected_event,
        scanner_data=scanner_data,
        diagnostics=diagnostics,
        raw_log=raw_log,
        odds_key_found=odds_key_found,
        api_football_key_found=api_football_key_found,
        football_data_key_found=football_data_key_found,
        manual_coordinates_available=manual_coordinates_available,
        found_lines=found_lines,
        squad_loaded=squad_loaded,
        weather_loaded=weather_loaded,
        football_data_live=football_data_live,
        football_data_partial=football_data_partial,
        football_data_limited=football_data_limited,
        football_data_historical=football_data_historical,
    )
    compatibility_matrix = _compatibility_matrix(
        found_lines=found_lines,
        team_form_live=team_form_live,
        squad_loaded=squad_loaded,
        weather_loaded=weather_loaded,
        current_season_blocked=current_season_blocked,
        historical_only=historical_only,
        football_data_key_found=football_data_key_found,
        football_data_live=football_data_live,
        football_data_partial=football_data_partial,
        football_data_limited=football_data_limited,
        football_data_historical=football_data_historical,
        manual_coordinates_available=manual_coordinates_available,
    )
    bet_type_matrix = _bet_type_matrix(
        team_form_live,
        squad_loaded,
        football_data_partial or football_data_limited,
    )
    summary = _summary_rows(compatibility_matrix, bet_type_matrix)
    missing_data = _missing_data(compatibility_matrix)
    manual_checklist = [
        "Confirm every Hard Rock FL line manually before betting.",
        "Use manual venue coordinates before trusting weather context.",
        "Confirm lineups, injuries, penalty takers, and set-piece takers manually.",
        "Treat player props, corners, cards, and SGPs as manual-only until supporting endpoints return rows.",
    ]
    improvements = [
        "Add reliable fixture/team mapping for football-data.org as team-form fallback.",
        "Add lineup, injury, and player-stat endpoint coverage before upgrading player props.",
        "Add venue coordinate source or manual venue coordinate library for weather automation.",
        "Consider paid/better API source if current season fixtures are blocked by plan.",
    ]
    return {
        "selected_event": {
            "event": selected_event.get("event") or selected_event.get("label", ""),
            "home_team": selected_event.get("home_team", ""),
            "away_team": selected_event.get("away_team", ""),
            "commence_time": selected_event.get("commence_time", ""),
        },
        "apis_configured": [
            {"API": "The Odds API", "Connected": "Yes" if odds_key_found else "No"},
            {"API": "API-Football", "Connected": "Yes" if api_football_key_found else "No"},
            {"API": "football-data.org", "Connected": "Yes" if football_data_key_found else "No"},
            {"API": "Open-Meteo", "Connected": "Yes - no API key required"},
            {"API": "Manual Hard Rock FL entry/screenshots", "Connected": "Manual"},
        ],
        "endpoints_tested": endpoints_tested,
        "compatibility_matrix": compatibility_matrix,
        "bet_type_support_matrix": bet_type_matrix,
        "existing_compatibility_inspector": compatibility,
        "summary": summary,
        "missing_data": missing_data,
        "manual_research_checklist": manual_checklist,
        "recommended_next_data_source_improvements": improvements,
    }


def api_capability_audit_to_markdown(audit: Mapping[str, Any]) -> str:
    lines = [
        "# API Capability Audit Package",
        "",
        "Safe audit only. No API keys, sportsbook login, scraping, proxies, hidden endpoints, or automated betting.",
        "",
        "## Selected Event",
        _markdown_table([audit["selected_event"]]),
        "",
        "## APIs Configured",
        _markdown_table(audit["apis_configured"]),
        "",
        "## Endpoints Tested",
        _markdown_table(audit["endpoints_tested"]),
        "",
        "## Master Data Compatibility Matrix",
        _markdown_table(audit["compatibility_matrix"]),
        "",
        "## Bet-Type Support Matrix",
        _markdown_table(audit["bet_type_support_matrix"]),
        "",
        "## Existing Compatibility Inspector",
        _markdown_table(audit["existing_compatibility_inspector"])
        if audit["existing_compatibility_inspector"]
        else "No compatibility inspector rows captured.",
        "",
        "## Final Summary",
        _markdown_table(audit["summary"]),
        "",
        "## Missing Data List",
        _markdown_table([{"Missing data": item} for item in audit["missing_data"]])
        if audit["missing_data"]
        else "None.",
        "",
        "## Manual Research Checklist",
    ]
    lines.extend(f"- {item}" for item in audit["manual_research_checklist"])
    lines.extend(["", "## Recommended Next Data Source Improvements"])
    lines.extend(f"- {item}" for item in audit["recommended_next_data_source_improvements"])
    return "\n".join(lines)


def api_capability_audit_to_json(audit: Mapping[str, Any]) -> str:
    return json.dumps(audit, indent=2, sort_keys=True)


def _endpoint_rows(
    *,
    selected_event: Mapping[str, Any],
    scanner_data: Mapping[str, Any] | None,
    diagnostics: Mapping[str, Any],
    raw_log: list[dict[str, Any]],
    odds_key_found: bool,
    api_football_key_found: bool,
    football_data_key_found: bool,
    manual_coordinates_available: bool,
    found_lines: list[dict[str, Any]],
    squad_loaded: bool,
    weather_loaded: bool,
    football_data_live: bool,
    football_data_partial: bool,
    football_data_limited: bool,
    football_data_historical: bool,
) -> list[dict[str, Any]]:
    market_keys = sorted(
        {
            str(row.get("api_market_key"))
            for row in found_lines
            if row.get("api_market_key")
        }
    )
    bookmaker_keys = sorted(
        {
            str(row.get("bookmaker_key"))
            for row in found_lines
            if row.get("bookmaker_key")
        }
    )
    return [
        {
            "API/source": "The Odds API",
            "Endpoint tested": "/v4/sports/{sport}/odds",
            "Safe params used": f"sport={scanner_data.get('sport_key', '') if scanner_data else ''}; markets={','.join(market_keys)}",
            "Status": "Connected" if odds_key_found else "API key missing",
            "Rows returned": len(found_lines),
            "Errors": "; ".join(scanner_data.get("errors", [])) if scanner_data else "",
            "Sample field names": "bookmaker_key, market_key, selection, price, point",
            "Notes": f"Bookmakers returned: {', '.join(bookmaker_keys)}",
        },
        {
            "API/source": "API-Football",
            "Endpoint tested": "/teams",
            "Safe params used": f"search={selected_event.get('home_team', '')}; search={selected_event.get('away_team', '')}",
            "Status": "Connected" if api_football_key_found else "API key missing",
            "Rows returned": _sum_diag(diagnostics, "team API-Football team ID"),
            "Errors": diagnostics.get("Last safe API error message", ""),
            "Sample field names": "team.id, team.name, team.country, team.national",
            "Notes": "Prefer national team results for international matches.",
        },
        {
            "API/source": "API-Football",
            "Endpoint tested": "/fixtures",
            "Safe params used": _safe_diag(diagnostics, "fixture endpoint params used"),
            "Status": _fixture_status(diagnostics),
            "Rows returned": diagnostics.get("Fixture rows used by Research Data", 0),
            "Errors": diagnostics.get("Last safe API error message", ""),
            "Sample field names": "fixture.id, fixture.date, teams, goals, fixture.status",
            "Notes": "Season/date-range fixture history; stale/historical rows do not upgrade confidence.",
        },
        {
            "API/source": "API-Football",
            "Endpoint tested": "/players/squads",
            "Safe params used": "team=<team_id>",
            "Status": "Connected" if api_football_key_found else "API key missing",
            "Rows returned": diagnostics.get("Squad rows used by Research Data", 0),
            "Errors": diagnostics.get("Last safe API error message", ""),
            "Sample field names": "players.name, players.position",
            "Notes": "Squad-only data. No minutes/per-90/lineup inference.",
        },
        {
            "API/source": "API-Football",
            "Endpoint tested": "/players, /fixtures/lineups, /fixtures/statistics, /injuries",
            "Safe params used": "Not tested unless fixture/player params are available",
            "Status": "Needs another endpoint/source",
            "Rows returned": 0,
            "Errors": "",
            "Sample field names": "not returned",
            "Notes": "Required for player props, lineups, shots, corners, cards, injuries.",
        },
        {
            "API/source": "football-data.org",
            "Endpoint tested": "/v4/competitions/WC/teams; /v4/teams/{team_id}/matches; /v4/competitions/WC/matches",
            "Safe params used": _safe_diag(diagnostics, "football-data.org endpoints tested"),
            "Status": (
                "Rows returned"
                if football_data_live
                else "Partial Last 5 only"
                if football_data_partial
                else "Limited sample only"
                if football_data_limited
                else "Historical/stale only"
                if football_data_historical
                else "No rows returned"
                if football_data_key_found
                else "API key missing"
            ),
            "Rows returned": diagnostics.get("football-data.org match rows used", 0),
            "Errors": diagnostics.get("football-data.org errors", ""),
            "Sample field names": "matches, score, homeTeam, awayTeam",
            "Notes": _football_data_notes(diagnostics),
        },
        {
            "API/source": "Open-Meteo",
            "Endpoint tested": "/v1/forecast",
            "Safe params used": "latitude/longitude manual inputs" if manual_coordinates_available else "coordinates missing",
            "Status": "Connected" if weather_loaded else "Needs manual venue coordinates",
            "Rows returned": 1 if weather_loaded else 0,
            "Errors": "",
            "Sample field names": "temperature_2m, wind_speed_10m, relative_humidity_2m, precipitation_probability",
            "Notes": "No API key required.",
        },
        {
            "API/source": "Manual Hard Rock FL entry/screenshots",
            "Endpoint tested": "manual",
            "Safe params used": "user-entered line/odds",
            "Status": "Manual fallback available",
            "Rows returned": 0,
            "Errors": "",
            "Sample field names": "selection, line, odds, notes",
            "Notes": "Highest confidence only when copied by user from Hard Rock FL app.",
        },
    ]


def _compatibility_matrix(
    *,
    found_lines: list[dict[str, Any]],
    team_form_live: bool,
    squad_loaded: bool,
    weather_loaded: bool,
    current_season_blocked: bool,
    historical_only: bool,
    football_data_key_found: bool,
    football_data_live: bool,
    football_data_partial: bool,
    football_data_limited: bool,
    football_data_historical: bool,
    manual_coordinates_available: bool,
) -> list[dict[str, Any]]:
    rows = []
    odds_available = bool(found_lines)
    for cell in TEAM_CELLS:
        status = "Fillable now" if team_form_live else "Fillable if endpoint returns rows"
        limitation = "No fixture history rows returned"
        impact = "Can support model" if team_form_live else "Do not upgrade confidence"
        if football_data_live:
            status = "Fillable now via football-data.org"
            limitation = "None captured"
            impact = "Can support model"
        elif football_data_partial:
            status = "Partial Last 5 only"
            limitation = "5-9 completed football-data.org rows per team; Last 10 threshold not met"
            impact = "Limited support — do not fully upgrade confidence"
        elif football_data_limited:
            status = "Limited sample only"
            limitation = "2-4 completed football-data.org rows per team; Last 5 / Last 10 thresholds not met"
            impact = "Context only — do not upgrade confidence"
        elif football_data_historical:
            status = "Historical/stale only"
            limitation = "Historical/stale football-data.org data only"
            impact = "Context only — do not upgrade confidence"
        elif current_season_blocked:
            status = "Blocked by current API plan"
            limitation = "API-Football current season blocked by plan"
        elif historical_only:
            status = "Historical/stale only"
            limitation = "Only historical seasons returned"
        elif football_data_key_found and not team_form_live:
            status = "Fillable through backup API only after team/match mapping is implemented"
            limitation = "Needs football-data.org team/match mapping"
        rows.append(_matrix_row(cell, "team fixture history", "API-Football /fixtures", "football-data.org", team_form_live, limitation, status, impact, "Manual team research notes"))
    for cell in PLAYER_CELLS:
        if cell in {"Player names", "Position"}:
            status = "Fillable now" if squad_loaded else "Fillable if endpoint returns rows"
            returned = squad_loaded
            limitation = "Squad endpoint only"
            impact = "Context only"
        elif cell in {"Expected starter", "Confirmed lineup"}:
            status = "Needs another endpoint/source"
            returned = False
            limitation = "Lineup endpoint not returning confirmed starters yet"
            impact = "No Bet if missing"
        elif cell in {"Injury status"}:
            status = "Needs another endpoint/source"
            returned = False
            limitation = "Injury endpoint not integrated with safe params"
            impact = "No Bet if missing"
        else:
            status = "Needs paid/better source"
            returned = False
            limitation = "Not returned by squad endpoint"
            impact = "Do not upgrade confidence"
        rows.append(_matrix_row(cell, "player/team endpoint rows", "API-Football", "manual research", returned, limitation, status, impact, "Manual player research / screenshots"))
    for cell in CONTEXT_CELLS:
        if cell == "Weather":
            status = "Fillable now" if weather_loaded else "Needs manual input"
            returned = weather_loaded
            limitation = "" if weather_loaded else "Needs manual venue coordinates"
            impact = "Context only"
            backup = "manual coordinates"
        elif cell in {"Venue", "Referee"}:
            status = "Fillable if endpoint returns rows"
            returned = False
            limitation = "Fixture context not returned consistently"
            impact = "Context only"
            backup = "manual lookup"
        else:
            status = "Needs manual input"
            returned = False
            limitation = "Not supported by current API result"
            impact = "Context only"
            backup = "manual research"
        rows.append(_matrix_row(cell, "context data", "API-Football/Open-Meteo", backup, returned, limitation, status, impact, "Manual context notes"))
    for cell in MARKET_CELLS:
        rows.append(_matrix_row(cell, "odds market rows", "The Odds API", "Manual Hard Rock FL entry", odds_available, "" if odds_available else "No odds rows returned", "Fillable now" if odds_available else "Needs manual input", "Manual confirmation required", "Manual Hard Rock FL confirmation"))
    return rows


def _bet_type_matrix(
    team_form_live: bool,
    squad_loaded: bool,
    team_form_limited: bool = False,
) -> list[dict[str, Any]]:
    if team_form_live:
        core_team_support = "Supported with odds + team form"
        total_support = "Partial with team goals form"
        btts_support = "Partial with BTTS/team goals form"
        spread_support = "Partial with goal differential"
        team_probability = "Yes"
        partial_probability = "Partial"
    elif team_form_limited:
        core_team_support = "Partial with limited team form"
        total_support = "Partial with limited team form"
        btts_support = "Partial with limited team form"
        spread_support = "Partial with limited team form"
        team_probability = "Partial / Low confidence"
        partial_probability = "Partial / Low confidence"
    else:
        core_team_support = "Partial only"
        total_support = "Partial only"
        btts_support = "Partial only"
        spread_support = "Partial only"
        team_probability = "No"
        partial_probability = "No"
    player_status = "Manual research required" if squad_loaded else "Not reliable yet"
    rows = [
        ("Moneyline / 1X2", "odds, consensus, team form", core_team_support, "team-form rows if unavailable", "Medium", team_probability, core_team_support if team_form_live else "Partial only"),
        ("Draw No Bet", "odds, team form", core_team_support, "team-form rows if unavailable", "Medium", partial_probability, core_team_support if team_form_live else "Partial only"),
        ("Double Chance", "odds, team form", core_team_support, "team-form rows if unavailable", "Medium", partial_probability, core_team_support if team_form_live else "Partial only"),
        ("Total Goals", "odds, goals for/against, BTTS, over rate", total_support, "team fixture history", "Medium", partial_probability, total_support if team_form_live else "Partial only"),
        ("Team Total Goals", "odds, team scoring/conceding form", total_support, "team fixture history", "Medium", partial_probability, total_support if team_form_live else "Partial only"),
        ("BTTS", "odds, BTTS rate, goals for/against", btts_support, "team fixture history", "Medium", partial_probability, btts_support if team_form_live else "Partial only"),
        ("Spread / Handicap", "odds, team form, goal differential", spread_support, "goal differential", "Medium", partial_probability, spread_support if team_form_live else "Partial only"),
        ("Corners", "corner stats, odds, matchup context", "Not reliable yet", "fixture statistics/corner data", "High", "No", "No Bet unless manually confirmed"),
        ("Cards", "referee, cards, fouls, odds", "Not reliable yet", "referee/cards endpoint", "High", "No", "No Bet unless manually confirmed"),
        ("Anytime Goalscorer", "lineups, minutes, player scoring stats", player_status, "lineups/player stats", "High", "No", "Manual research required"),
        ("Player Shots", "lineups, minutes, shots per 90", player_status, "player shots/starter data", "High", "No", "Manual research required"),
        ("Player Shots on Target", "lineups, SOT per 90", player_status, "player SOT/starter data", "High", "No", "Manual research required"),
        ("Assists", "lineups, assists per 90, set pieces", player_status, "player assist/set-piece data", "High", "No", "Manual research required"),
        ("SGP / Parlay", "leg probabilities, correlation, confirmed lines", "Manual research required", "correlation and player/team inputs", "Very high", "No", "No Bet unless manually confirmed"),
    ]
    return [
        {
            "Bet type": row[0],
            "Required data": row[1],
            "Current automated support": row[2],
            "Missing data": row[3],
            "Risk level": row[4],
            "Can app estimate true probability now?": row[5],
            "Recommendation status": row[6],
        }
        for row in rows
    ]


def _summary_rows(
    compatibility_matrix: list[dict[str, Any]],
    bet_type_matrix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fillable = [
        row["Dashboard cell"]
        for row in compatibility_matrix
        if row["Fillability status"] in {"Fillable now", "Fillable now via football-data.org"}
    ]
    endpoint_rows = [row["Dashboard cell"] for row in compatibility_matrix if row["Fillability status"] == "Fillable if endpoint returns rows"]
    manual = [row["Dashboard cell"] for row in compatibility_matrix if "manual" in row["Fillability status"].lower() or "source" in row["Fillability status"].lower()]
    blocked = [row["Dashboard cell"] for row in compatibility_matrix if row["Fillability status"] == "Blocked by current API plan"]
    supported = [row["Bet type"] for row in bet_type_matrix if row["Recommendation status"] == "Supported with odds + team form"]
    manual_bets = [row["Bet type"] for row in bet_type_matrix if row["Recommendation status"] != "Supported with odds + team form"]
    return [
        {"Category": "Fillable now", "Items": _join(fillable)},
        {"Category": "Fillable only if endpoint returns rows", "Items": _join(endpoint_rows)},
        {"Category": "Manual or better-source required", "Items": _join(manual)},
        {"Category": "Blocked by current API plan", "Items": _join(blocked) or "None captured"},
        {"Category": "Betting use - supported", "Items": _join(supported) or "Odds-only/context until team form loads"},
        {"Category": "Betting use - manual/No Bet", "Items": _join(manual_bets)},
    ]


def _missing_data(matrix: list[dict[str, Any]]) -> list[str]:
    return [
        f"{row['Dashboard cell']}: {row['Current limitation']}"
        for row in matrix
        if row["Current API returned data: Yes/No"] == "No"
    ]


def _matrix_row(
    cell: str,
    needed: str,
    best: str,
    backup: str,
    returned: bool,
    limitation: str,
    status: str,
    impact: str,
    manual: str,
) -> dict[str, Any]:
    return {
        "Dashboard cell": cell,
        "Needed data": needed,
        "Best source": best,
        "Backup source": backup,
        "Current API returned data: Yes/No": "Yes" if returned else "No",
        "Current limitation": limitation or "None captured",
        "Fillability status": status,
        "Betting confidence impact": impact,
        "Manual fallback": manual,
    }


def _contains_plan_block(diagnostics: Mapping[str, Any]) -> bool:
    text = json.dumps(diagnostics, ensure_ascii=True).lower()
    return "free plans" in text or "blocked" in text or "plan" in text


def _historical_only(diagnostics: Mapping[str, Any]) -> bool:
    text = json.dumps(diagnostics, ensure_ascii=True)
    return any(year in text for year in ["2022", "2023", "2024"]) and not any(
        year in text for year in ["2025", "2026"]
    )


def _sum_diag(diagnostics: Mapping[str, Any], pattern: str) -> int:
    return sum(1 for key, value in diagnostics.items() if pattern in key and value)


def _safe_diag(diagnostics: Mapping[str, Any], suffix: str) -> str:
    values = [str(value) for key, value in diagnostics.items() if key.endswith(suffix)]
    return "; ".join(values)[:500]


def _football_data_notes(diagnostics: Mapping[str, Any]) -> str:
    parts = []
    for key in [
        "football-data.org competition code used",
        "football-data.org seasons tried",
        "football-data.org rows per team",
        "football-data.org minimum rows per team",
        "football-data.org team-form sample quality",
        "football-data.org Last 5 threshold met",
        "football-data.org Last 10 threshold met",
        "Home football-data.org mapped team id",
        "Away football-data.org mapped team id",
        "Home football-data.org mapped team name",
        "Away football-data.org mapped team name",
    ]:
        value = diagnostics.get(key)
        if value:
            parts.append(f"{key}: {value}")
    return "; ".join(parts)


def _fixture_status(diagnostics: Mapping[str, Any]) -> str:
    if _contains_plan_block(diagnostics):
        return "Blocked by current API plan"
    if _historical_only(diagnostics):
        return "Historical/stale only"
    rows = int(diagnostics.get("Fixture rows used by Research Data") or 0)
    return "Rows returned" if rows else "No rows returned"


def _join(items: list[str]) -> str:
    return ", ".join(items[:12]) + (" ..." if len(items) > 12 else "")


def _markdown_table(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return "None."
    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(_md(row.get(header, "")) for header in headers)
            + " |"
        )
    return "\n".join(lines)


def _md(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text[:500]
