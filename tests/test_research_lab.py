from __future__ import annotations

import unittest

from src.advanced_markets import create_market_template
from src.research_lab import (
    OpenMeteoQuotaTracker,
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
        self.assertEqual(signals[0]["Data Status"], "Odds only")
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


if __name__ == "__main__":
    unittest.main()
