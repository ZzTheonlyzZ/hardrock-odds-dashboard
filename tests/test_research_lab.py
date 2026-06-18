from __future__ import annotations

import unittest
import src.api_football as api_football
import src.football_data as football_data
import src.odds_api as odds_api
import src.open_meteo as open_meteo
import src.research_integrations as research_integrations

from src.advanced_markets import create_market_template
from src.api_football import build_api_football_snapshot, summarize_team_form
from src.api_football import fetch_fixture_history_with_fallbacks
from src.open_meteo import build_weather_snapshot, parse_open_meteo_weather
from src.research_lab import (
    OpenMeteoQuotaTracker,
    aggregate_api_usage_rows,
    build_betting_signals,
    normalize_research_snapshot_for_event,
    parse_api_football_headers,
    parse_football_data_headers,
    parse_the_odds_api_headers,
    quota_status,
    request_budget_preview,
    unavailable_research_snapshot,
)


def _fd_match(
    match_id,
    utc_date,
    home_id,
    home_name,
    home_goals,
    away_id,
    away_name,
    away_goals,
):
    return {
        "id": match_id,
        "utcDate": utc_date,
        "status": "FINISHED",
        "homeTeam": {"id": home_id, "name": home_name},
        "awayTeam": {"id": away_id, "name": away_name},
        "score": {"fullTime": {"home": home_goals, "away": away_goals}},
    }


def _fd_team_matches(team_id, team_name, count):
    rows = []
    for index in range(count):
        rows.append(
            _fd_match(
                1000 + team_id * 100 + index,
                f"2026-05-{28 - index:02d}T00:00:00Z",
                team_id,
                team_name,
                1 + (index % 3),
                900 + index,
                f"Opponent {index}",
                index % 2,
            )
        )
    return rows


class ResearchLabTests(unittest.TestCase):
    def test_quota_thresholds(self):
        self.assertEqual(quota_status(60, 100), "Healthy")
        self.assertEqual(quota_status(40, 100), "Watch")
        self.assertEqual(quota_status(20, 100), "Warning")
        self.assertEqual(quota_status(10, 100), "Critical")
        self.assertEqual(quota_status(4, 100), "Limit reached")
        self.assertEqual(quota_status(50, 100, status_code=429), "Limit reached")

    def test_the_odds_api_headers_parse(self):
        row = parse_the_odds_api_headers(
            {
                "x-requests-remaining": "20",
                "x-requests-used": "80",
                "x-requests-last": "3",
            }
        )
        self.assertEqual(row["API name"], "The Odds API")
        self.assertEqual(row["Requests remaining"], 20)
        self.assertEqual(row["Last request cost"], 3)
        self.assertEqual(row["Status"], "Warning")

    def test_api_football_headers_parse(self):
        row = parse_api_football_headers(
            {
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "12",
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Remaining": "1",
            }
        )
        self.assertEqual(row["API name"], "API-Football")
        self.assertEqual(row["Daily remaining"], 12)
        self.assertEqual(row["Minute remaining"], 1)
        self.assertEqual(row["Status"], "Critical")

    def test_football_data_headers_parse(self):
        row = parse_football_data_headers(
            {
                "X-Requests-Available-Minute": "2",
                "X-RequestCounter-Reset": "30",
            }
        )
        self.assertEqual(row["API name"], "football-data.org")
        self.assertEqual(row["Minute remaining"], 2)
        self.assertEqual(row["Reset time"], "30")
        self.assertEqual(row["Status"], "Warning")

    def test_football_data_maps_teams_and_marks_two_rows_limited(self):
        def fake_fetch(path, params, api_key):
            if path == "/competitions/WC/teams":
                return {
                    "teams": [
                        {"id": 1, "name": "Canada", "tla": "CAN"},
                        {"id": 2, "name": "Qatar", "tla": "QAT"},
                    ]
                }, {"API name": "football-data.org"}
            if path == "/teams/1/matches":
                return {
                    "matches": [
                        _fd_match(11, "2026-06-01T00:00:00Z", 1, "Canada", 3, 2, "Opponent", 1),
                        _fd_match(12, "2026-05-20T00:00:00Z", 3, "Opponent", 0, 1, "Canada", 0),
                    ]
                }, {"API name": "football-data.org"}
            if path == "/teams/2/matches":
                return {
                    "matches": [
                        _fd_match(21, "2026-06-02T00:00:00Z", 2, "Qatar", 1, 4, "Opponent", 1),
                        _fd_match(22, "2026-05-22T00:00:00Z", 4, "Opponent", 0, 2, "Qatar", 0),
                    ]
                }, {"API name": "football-data.org"}
            if path == "/competitions/WC/matches":
                return {"matches": []}, {"API name": "football-data.org"}
            return {}, {"API name": "football-data.org"}

        original = football_data.fetch_football_data_json
        football_data.fetch_football_data_json = fake_fetch
        try:
            snapshot = football_data.build_football_data_snapshot(
                api_key="safe-football-data-key",
                home_team="Canada",
                away_team="Qatar",
                event_date="2026-06-18",
            )
        finally:
            football_data.fetch_football_data_json = original

        self.assertEqual(
            snapshot["team_form"][0]["Status"],
            football_data.LIMITED_FOOTBALL_DATA_STATUS,
        )
        self.assertEqual(
            snapshot["team_form"][0]["Last 5"],
            football_data.LIMITED_FOOTBALL_DATA_STATUS,
        )
        self.assertEqual(snapshot["team_form"][0]["Last 5 threshold met"], "No")
        self.assertEqual(snapshot["team_form"][0]["Last 10 threshold met"], "No")
        self.assertEqual(snapshot["team_form"][0]["Wins"], 1)
        self.assertEqual(snapshot["team_form"][0]["Goals scored"], 3)
        self.assertEqual(
            snapshot["diagnostics"]["Home football-data.org mapped team id"],
            1,
        )
        self.assertEqual(
            snapshot["diagnostics"]["Home football-data.org mapping method"],
            "exact team name",
        )
        self.assertGreater(snapshot["match_rows_used"], 0)
        self.assertEqual(
            snapshot["diagnostics"]["football-data.org team-form sample quality"],
            "Limited sample only",
        )

    def test_football_data_thresholds_last5_and_last10(self):
        partial = football_data.summarize_football_data_team_form(
            "Canada",
            _fd_team_matches(1, "Canada", 5),
            team_id=1,
            event_date="2026-06-18",
        )
        self.assertEqual(partial["Status"], football_data.PARTIAL_FOOTBALL_DATA_STATUS)
        self.assertEqual(partial["Last 5 threshold met"], "Yes")
        self.assertEqual(partial["Last 10 threshold met"], "No")
        self.assertEqual(partial["Team-form sample quality"], "Last 5 threshold met only — limited support")

        full = football_data.summarize_football_data_team_form(
            "Canada",
            _fd_team_matches(1, "Canada", 10),
            team_id=1,
            event_date="2026-06-18",
        )
        self.assertEqual(full["Status"], football_data.LIVE_FOOTBALL_DATA_STATUS)
        self.assertEqual(full["Last 5 threshold met"], "Yes")
        self.assertEqual(full["Last 10 threshold met"], "Yes")
        self.assertEqual(full["Model support"], "Can support model")

    def test_live_snapshot_uses_football_data_when_api_football_missing(self):
        def fake_fetch(path, params, api_key):
            if path == "/competitions/WC/teams":
                return {
                    "teams": [
                        {"id": 1, "name": "Canada", "tla": "CAN"},
                        {"id": 2, "name": "Qatar", "tla": "QAT"},
                    ]
                }, {"API name": "football-data.org"}
            if path == "/teams/1/matches":
                return {"matches": _fd_team_matches(1, "Canada", 10)}, {"API name": "football-data.org"}
            if path == "/teams/2/matches":
                return {"matches": _fd_team_matches(2, "Qatar", 10)}, {"API name": "football-data.org"}
            if path == "/competitions/WC/matches":
                return {"matches": []}, {"API name": "football-data.org"}
            return {}, {"API name": "football-data.org"}

        original = football_data.fetch_football_data_json
        football_data.fetch_football_data_json = fake_fetch
        try:
            snapshot = research_integrations.build_live_soccer_research_snapshot(
                secrets={"FOOTBALL_DATA_KEY": "safe-football-data-key"},
                home_team="Canada",
                away_team="Qatar",
                commence_time="2026-06-18T20:00:00Z",
            )
        finally:
            football_data.fetch_football_data_json = original

        self.assertEqual(
            snapshot["team_form"][0]["Status"],
            football_data.LIVE_FOOTBALL_DATA_STATUS,
        )
        self.assertEqual(snapshot["data_quality"], "Odds + team form")
        self.assertEqual(
            snapshot["integration_diagnostics"]["football-data.org rows used by Research Data"],
            20,
        )
        self.assertEqual(
            snapshot["integration_diagnostics"]["Research snapshot source used by Research Data"],
            "football-data.org live team-match fallback snapshot",
        )

    def test_open_meteo_local_quota_tracking(self):
        tracker = OpenMeteoQuotaTracker(day_calls=9600)
        tracker.record_call()
        row = tracker.status_row()
        self.assertEqual(row["API name"], "Open-Meteo")
        self.assertEqual(row["Requests used"], 9601)
        self.assertEqual(row["Status"], "Limit reached")

    def test_unsupported_market_falls_back_to_manual_entry(self):
        template = create_market_template("Quarter Specials")
        self.assertTrue(template.manual_only)
        self.assertEqual(template.api_market_keys, ())

    def test_request_budget_and_unavailable_snapshot(self):
        budget = request_budget_preview("full")
        self.assertEqual(budget[-1]["Research area"], "Total")
        self.assertGreater(budget[-1]["Estimated calls"], 0)
        snapshot = unavailable_research_snapshot()
        self.assertIn("team_form", snapshot)
        self.assertIn("players", snapshot)
        self.assertIn("context", snapshot)
        self.assertIn("api_request_log", snapshot)

    def test_betting_signal_no_bet_when_edge_unclear(self):
        signals = build_betting_signals(
            [
                {
                    "Selection": "A",
                    "Odds": -110,
                    "Consensus implied probability": None,
                    "Confidence Label": "Comparison only",
                    "Source Label": "Consensus only",
                    "Hard Rock FL Available": "No",
                    "Market Category": "Match",
                }
            ],
            bankroll=100.0,
            kelly_multiplier=0.25,
        )
        self.assertEqual(signals[0]["Classification"], "No Bet")
        self.assertEqual(signals[0]["Data Status"], "Odds-only")
        self.assertIn("No bet if edge is unclear", signals[0]["Contradiction flags"])

    def test_betting_signal_deduplicates_repeated_rows(self):
        line = {
            "Market Category": "Match",
            "Specific Market": "Moneyline / 1X2",
            "Selection": "A",
            "Point / Line": None,
            "Odds": -110,
            "Consensus implied probability": None,
            "Confidence Label": "High confidence",
            "Source Label": "Hard Rock FL",
            "Hard Rock FL Available": "Yes",
        }
        signals = build_betting_signals(
            [line, dict(line)],
            bankroll=100.0,
            kelly_multiplier=0.25,
        )
        self.assertEqual(len(signals), 1)

    def test_missing_api_key_fallback(self):
        snapshot = build_api_football_snapshot(
            api_key=None,
            home_team="Inter Miami",
            away_team="Orlando City",
            event_date="2026-06-17",
        )
        self.assertEqual(snapshot["team_form"][0]["Status"], "Unavailable - API key missing")
        self.assertIn("API_FOOTBALL_KEY", snapshot["missing"])

    def test_api_client_parses_mock_team_form(self):
        fixtures = [
            {
                "teams": {
                    "home": {"name": "Inter Miami"},
                    "away": {"name": "Orlando City"},
                },
                "goals": {"home": 2, "away": 1},
            },
            {
                "teams": {
                    "home": {"name": "Atlanta United"},
                    "away": {"name": "Inter Miami"},
                },
                "goals": {"home": 0, "away": 0},
            },
            {
                "teams": {
                    "home": {"name": "Inter Miami"},
                    "away": {"name": "NYCFC"},
                },
                "goals": {"home": 1, "away": 3},
            },
        ]
        row = summarize_team_form("Inter Miami", fixtures)
        self.assertEqual(row["Status"], "Live API-Football")
        self.assertEqual(row["Last 5"], "W-D-L")
        self.assertEqual(row["Wins"], 1)
        self.assertEqual(row["Draws"], 1)
        self.assertEqual(row["Losses"], 1)
        self.assertEqual(row["Goals scored"], 3)
        self.assertEqual(row["Goals conceded"], 4)
        self.assertEqual(row["Home/away split"], "Home: 1-0-1 | Away: 0-1-0")

    def test_api_client_no_fixtures_does_not_show_zero_stats(self):
        row = summarize_team_form("Inter Miami", [])
        self.assertEqual(row["Last 5"], "No fixture history returned by season/date range")
        self.assertEqual(row["Wins"], "")
        self.assertEqual(row["Goals scored"], "")

    def test_squad_only_player_labeling(self):
        from src.api_football import parse_squad_players

        rows = parse_squad_players(
            "Inter Miami",
            {
                "response": [
                    {
                        "players": [
                            {"name": "Player One", "position": "Attacker"}
                        ]
                    }
                ]
            },
        )
        self.assertEqual(rows[0]["Expected starter"], "Unknown until lineup confirmed")
        self.assertEqual(rows[0]["Rotation risk"], "Manual review required")
        self.assertEqual(rows[0]["Notes"], "Squad only — detailed player stats unavailable")

    def test_open_meteo_parses_mock_weather(self):
        row = parse_open_meteo_weather(
            {
                "current": {
                    "temperature_2m": 29,
                    "relative_humidity_2m": 72,
                    "precipitation": 0.4,
                    "wind_speed_10m": 14,
                },
                "current_units": {
                    "temperature_2m": "C",
                    "relative_humidity_2m": "%",
                    "precipitation": "mm",
                    "wind_speed_10m": "km/h",
                },
                "hourly": {"precipitation_probability": [35]},
            }
        )
        self.assertEqual(row["Factor"], "Weather")
        self.assertIn("Temp 29C", row["Value"])
        self.assertIn("humidity 72%", row["Value"])

    def test_open_meteo_missing_coordinates_is_not_key_error(self):
        snapshot = build_weather_snapshot(latitude=None, longitude=None)
        value = snapshot["context"][0]["Value"]
        self.assertEqual(value, "Unavailable — venue coordinates missing")
        self.assertNotIn("API key missing", value)

    def test_manual_coordinates_trigger_weather_snapshot_parsing(self):
        row = parse_open_meteo_weather(
            {
                "current": {
                    "temperature_2m": 80,
                    "relative_humidity_2m": 60,
                    "precipitation": 0,
                    "wind_speed_10m": 8,
                },
                "current_units": {
                    "temperature_2m": "F",
                    "relative_humidity_2m": "%",
                    "precipitation": "in",
                    "wind_speed_10m": "mph",
                },
                "hourly": {"precipitation_probability": [10]},
            }
        )
        self.assertIn("severity Low", row["Value"])

    def test_api_usage_aggregates_duplicate_provider_rows(self):
        rows = aggregate_api_usage_rows(
            [
                {"API name": "API-Football", "Requests remaining": 95, "Status": "Healthy"},
                {"API name": "API-Football", "Requests remaining": 88, "Status": "Watch"},
                {"API name": "Open-Meteo", "Requests remaining": 9999, "Status": "Healthy"},
            ]
        )
        self.assertEqual(len(rows), 2)
        api_football_row = next(row for row in rows if row["API name"] == "API-Football")
        self.assertEqual(api_football_row["Requests remaining"], 88)
        self.assertEqual(api_football_row["Status"], "Watch")

    def test_fixture_fallback_tries_event_year_and_previous_year(self):
        diagnostics = {}
        calls = []

        def fake_fetch(path, params, api_key):
            calls.append(dict(params))
            return {"response": []}, {"API name": "API-Football"}

        original = api_football.fetch_api_football_json
        api_football.fetch_api_football_json = fake_fetch
        try:
            rows, _usage = fetch_fixture_history_with_fallbacks(
                api_key="safe-test-key",
                team_id=10,
                team_name="England",
                event_date="2026-06-18",
                diagnostics=diagnostics,
                side="Home",
            )
        finally:
            api_football.fetch_api_football_json = original

        self.assertEqual(rows, [])
        self.assertEqual(calls[0]["season"], 2026)
        self.assertEqual(calls[1]["season"], 2025)
        self.assertIn("from", calls[0])
        self.assertIn("to", calls[0])
        self.assertNotIn("last", calls[0])

    def test_fixture_fallback_deduplicates_and_keeps_completed_latest(self):
        diagnostics = {}

        def fixture(fixture_id, date, home_goals, away_goals):
            return {
                "fixture": {
                    "id": fixture_id,
                    "date": date,
                    "status": {"short": "FT"},
                },
                "teams": {
                    "home": {"id": 10, "name": "England"},
                    "away": {"id": 20, "name": "Opponent"},
                },
                "goals": {"home": home_goals, "away": away_goals},
            }

        def fake_fetch(path, params, api_key):
            if params["season"] == 2026:
                return {
                    "response": [
                        fixture(1, "2026-06-01T00:00:00Z", 2, 0),
                        fixture(2, "2026-03-01T00:00:00Z", 1, 1),
                    ]
                }, {"API name": "API-Football"}
            return {
                "response": [
                    fixture(2, "2026-03-01T00:00:00Z", 1, 1),
                    fixture(3, "2025-11-01T00:00:00Z", 0, 1),
                ]
            }, {"API name": "API-Football"}

        original = api_football.fetch_api_football_json
        api_football.fetch_api_football_json = fake_fetch
        try:
            rows, _usage = fetch_fixture_history_with_fallbacks(
                api_key="safe-test-key",
                team_id=10,
                team_name="England",
                event_date="2026-06-18",
                diagnostics=diagnostics,
                side="Home",
            )
        finally:
            api_football.fetch_api_football_json = original

        self.assertEqual([row["fixture"]["id"] for row in rows], [1, 2, 3])
        form = summarize_team_form("England", rows, team_id=10)
        self.assertEqual(form["Wins"], 1)
        self.assertEqual(form["Draws"], 1)
        self.assertEqual(form["Losses"], 1)
        self.assertEqual(form["Goals scored"], 3)
        self.assertEqual(form["Goals conceded"], 2)
        self.assertEqual(form["BTTS rate"], "33.3%")
        self.assertEqual(form["Over 2.5 rate"], "0.0%")
        self.assertEqual(form["Clean sheets"], 1)
        self.assertEqual(form["Failed to score"], 1)

    def test_compatibility_summary_marks_fixture_and_squad_cells(self):
        summary = research_integrations.build_api_compatibility_summary(
            team_form=[
                {
                    "Team": "England",
                    "Status": "No fixture history returned by season/date range",
                }
            ],
            player_summary={"Squad players loaded": 11},
            weather={"missing": ["Venue latitude/longitude"]},
        )
        by_cell = {row["Dashboard cell"]: row for row in summary}
        self.assertEqual(
            by_cell["Last 5"]["Status"],
            "Not returned by current API request",
        )
        self.assertEqual(by_cell["Player names"]["Status"], "Fillable now")
        self.assertEqual(by_cell["Position"]["Status"], "Fillable now")
        self.assertEqual(
            by_cell["Goals per 90"]["Status"],
            "Fillable with another endpoint",
        )
        self.assertEqual(by_cell["Weather"]["Status"], "Needs manual input")

        ready_summary = research_integrations.build_api_compatibility_summary(
            team_form=[{"Team": "England", "Status": "Live API-Football"}],
            player_summary={"Squad players loaded": 0},
            weather={"missing": []},
        )
        ready_by_cell = {row["Dashboard cell"]: row for row in ready_summary}
        self.assertEqual(ready_by_cell["Last 5"]["Status"], "Fillable now")
        self.assertEqual(ready_by_cell["Weather"]["Status"], "Fillable now")

    def test_live_snapshot_zero_squad_uses_api_fallback_message(self):
        def fake_fetch(path, params, api_key):
            if path == "/teams":
                name = params["search"]
                return {
                    "response": [
                        {"team": {"id": 1 if name == "Qatar" else 2, "name": name}}
                    ]
                }, {"API name": "API-Football"}
            if path == "/players/squads":
                return {"response": [{"players": []}]}, {"API name": "API-Football"}
            if path == "/fixtures":
                return {"response": []}, {"API name": "API-Football"}
            return {"response": []}, {"API name": "API-Football"}

        original = api_football.fetch_api_football_json
        api_football.fetch_api_football_json = fake_fetch
        try:
            snapshot = build_api_football_snapshot(
                api_key="safe-test-key",
                home_team="Qatar",
                away_team="Canada",
                event_date="2026-06-18",
            )
        finally:
            api_football.fetch_api_football_json = original

        self.assertEqual(snapshot["team_form"][0]["Team"], "Qatar")
        self.assertNotIn("API key missing", snapshot["team_form"][0]["Status"])
        self.assertEqual(snapshot["players"][0]["Name"], "Squad endpoint returned no players")
        self.assertNotEqual(snapshot["players"][0]["Name"], "Manual input available")
        self.assertNotIn("API key missing", snapshot["context"][0]["Value"])
        self.assertEqual(snapshot["fixture_rows_used"], 0)
        self.assertEqual(snapshot["squad_rows_used"], 0)

    def test_normalized_snapshot_uses_selected_teams_when_key_exists(self):
        snapshot = normalize_research_snapshot_for_event(
            unavailable_research_snapshot(),
            home_team="Canada",
            away_team="Qatar",
            api_football_key_found=True,
        )
        self.assertEqual(snapshot["team_form"][0]["Team"], "Canada")
        self.assertEqual(snapshot["team_form"][1]["Team"], "Qatar")
        self.assertNotIn("API key missing", snapshot["team_form"][0]["Status"])
        self.assertEqual(
            snapshot["integration_diagnostics"]["API-Football key found"],
            "Yes",
        )
        self.assertEqual(snapshot["players"][0]["Name"], "Squad endpoint returned no players")

    def test_no_sportsbook_scraping_or_login_helpers_exist(self):
        forbidden_names = [
            "scrape_hardrock",
            "login_hardrock",
            "automate_bet",
            "bypass_captcha",
            "proxy_sportsbook",
        ]
        modules = [
            api_football,
            football_data,
            odds_api,
            open_meteo,
            research_integrations,
        ]
        exported = {name for module in modules for name in dir(module)}
        for name in forbidden_names:
            self.assertNotIn(name, exported)


if __name__ == "__main__":
    unittest.main()
