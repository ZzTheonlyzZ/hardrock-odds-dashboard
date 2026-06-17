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
    parse_api_football_headers,
    parse_football_data_headers,
    parse_the_odds_api_headers,
    quota_status,
    request_budget_preview,
    unavailable_research_snapshot,
)


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
        self.assertEqual(row["Last 5"], "No fixture history returned")
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

    def test_fixture_fallback_prefers_date_range_before_last(self):
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
                diagnostics=diagnostics,
                side="Home",
            )
        finally:
            api_football.fetch_api_football_json = original

        self.assertEqual(rows, [])
        self.assertIn("from", calls[0])
        self.assertNotIn("last", calls[0])
        self.assertEqual(calls[1], {"team": 10, "last": 10})

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
