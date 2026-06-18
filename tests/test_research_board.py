from __future__ import annotations

import csv
import json
import unittest

from src.research_board import (
    ai_package_to_csv,
    ai_package_to_json,
    ai_package_to_markdown,
    chatgpt_analysis_package_to_markdown,
    build_hardrock_coverage_scan,
    build_ai_research_package,
    build_research_card,
    classify_source,
    enrich_odds_rows,
    markets_missing_from_hardrock_fl,
    market_availability_row,
    source_summary,
)
from src.advanced_markets import MarketTemplate


class ResearchBoardTests(unittest.TestCase):
    def test_source_classification(self):
        self.assertEqual(
            classify_source("hardrockbet_fl"),
            ("Exact Hard Rock FL API", "High confidence"),
        )
        self.assertEqual(
            classify_source("hardrockbet"),
            ("Generic Hard Rock API", "Medium confidence, may differ from Florida"),
        )
        self.assertEqual(
            classify_source(None, manual=True),
            (
                "Manual Hard Rock FL Entry",
                "User-confirmed, highest confidence if copied from app",
            ),
        )

    def test_source_summary_and_availability(self):
        rows = enrich_odds_rows(
            [
                {
                    "bookmaker": "Hard Rock Bet",
                    "bookmaker_key": "hardrockbet",
                    "market_key": "h2h",
                    "selection": "A",
                    "price": 110,
                    "point": None,
                },
                {
                    "bookmaker": "FanDuel",
                    "bookmaker_key": "fanduel",
                    "market_key": "h2h",
                    "selection": "A",
                    "price": 105,
                    "point": None,
                },
            ]
        )
        summary = source_summary(rows)
        self.assertFalse(summary["hardrock_fl_available"])
        self.assertTrue(summary["generic_hardrock_available"])
        self.assertTrue(summary["other_books_available"])
        self.assertFalse(summary["manual_entry_required"])

        availability = market_availability_row("Moneyline / 1X2", rows)
        self.assertTrue(availability["manual entry available"])
        self.assertTrue(availability["hardrockbet available"])

    def test_manual_research_card(self):
        card = build_research_card(
            sport="Soccer",
            event="A at B",
            market="BTTS",
            selection="Yes",
            point=None,
            american_odds=120,
            estimated_probability=0.50,
            no_vig_probability=0.55,
            stake=1.0,
            bankroll=100.0,
            kelly_multiplier=0.25,
            manual=True,
        )
        self.assertEqual(card.source_type, "Manual Hard Rock FL Entry")
        self.assertEqual(
            card.confidence,
            "User-confirmed, highest confidence if copied from app",
        )
        self.assertAlmostEqual(card.edge, 0.55 - 100 / 220)

    def test_hardrock_coverage_scanner_detects_fl_and_generic(self):
        templates = [
            MarketTemplate("Moneyline / 1X2", ("h2h",), "Tier 1", "Match"),
        ]
        found, missing = build_hardrock_coverage_scan(
            templates,
            {
                "h2h": [
                    {
                        "bookmaker_key": "hardrockbet_fl",
                        "market_key": "h2h",
                        "selection": "Braves",
                        "price": -115,
                        "point": None,
                    },
                    {
                        "bookmaker_key": "hardrockbet",
                        "market_key": "h2h",
                        "selection": "Braves",
                        "price": -110,
                        "point": None,
                    },
                ]
            },
        )

        self.assertEqual(missing, [])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["Source used"], "Exact Hard Rock FL API")
        self.assertEqual(found[0]["Confidence Label"], "High confidence")
        self.assertEqual(found[0]["Hard Rock FL Available"], "Yes")
        self.assertEqual(found[0]["Generic Hard Rock Available"], "Yes")
        self.assertEqual(found[0]["Hard Rock FL Odds"], -115)
        self.assertEqual(found[0]["Generic Hard Rock Odds"], -110)
        self.assertEqual(found[0]["Difference"], -5)

    def test_hardrock_coverage_scanner_marks_generic_only_lines(self):
        templates = [
            MarketTemplate("Moneyline / 1X2", ("h2h",), "Tier 1", "Match"),
        ]
        found, missing = build_hardrock_coverage_scan(
            templates,
            {
                "h2h": [
                    {
                        "bookmaker_key": "hardrockbet",
                        "market_key": "h2h",
                        "selection": "Marlins",
                        "price": 105,
                        "point": None,
                    },
                ]
            },
        )

        self.assertEqual(missing, [])
        self.assertEqual(found[0]["Source used"], "Generic Hard Rock API")
        self.assertEqual(
            found[0]["Confidence Label"],
            "Medium confidence, may differ from Florida",
        )
        self.assertEqual(found[0]["Hard Rock FL Available"], "No")
        self.assertEqual(found[0]["Generic Hard Rock Available"], "Yes")

    def test_hardrock_coverage_scanner_detects_consensus_lines(self):
        templates = [
            MarketTemplate("BTTS", ("btts",), "Tier 1", "Goals"),
        ]
        found, missing = build_hardrock_coverage_scan(
            templates,
            {
                "btts": [
                    {
                        "bookmaker_key": "fanduel",
                        "market_key": "btts",
                        "selection": "Yes",
                        "price": -120,
                        "point": None,
                    },
                ]
            },
        )

        self.assertEqual(missing, [])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["Source used"], "Market Consensus / Other Books")
        self.assertEqual(found[0]["Confidence Label"], "Comparison only")
        self.assertEqual(found[0]["Consensus Available"], "Yes")
        self.assertEqual(found[0]["Hard Rock FL Available"], "No")

    def test_hardrock_coverage_scanner_does_not_invent_missing_markets(self):
        templates = [
            MarketTemplate("BTTS", ("btts",), "Tier 1", "Goals"),
        ]
        found, missing = build_hardrock_coverage_scan(
            templates,
            {"btts": []},
        )

        self.assertEqual(found, [])
        self.assertEqual(
            missing,
            [
                {
                    "Market Category": "Goals",
                    "Specific Market": "BTTS",
                    "Manual entry": "Use Manual Hard Rock FL Entry",
                }
            ],
        )

    def test_missing_fl_logic_marks_generic_or_consensus_rows(self):
        rows = [
            {
                "Market Category": "Match",
                "Specific Market": "Moneyline / 1X2",
                "Selection": "Braves",
                "Point / Line": None,
                "Hard Rock FL Available": "No",
                "Generic Hard Rock Available": "Yes",
                "Consensus Available": "No",
            },
            {
                "Market Category": "Goals",
                "Specific Market": "BTTS",
                "Selection": "Yes",
                "Point / Line": None,
                "Hard Rock FL Available": "Yes",
                "Generic Hard Rock Available": "No",
                "Consensus Available": "Yes",
            },
        ]

        missing = markets_missing_from_hardrock_fl(rows)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["Specific Market"], "Moneyline / 1X2")

    def test_ai_package_exports_are_valid(self):
        found_lines = [
            {
                "Market Category": "Match",
                "Specific Market": "Moneyline / 1X2",
                "Selection": "Braves",
                "Point / Line": None,
                "Odds": -115,
                "Hard Rock FL Odds": -115,
                "Generic Hard Rock Odds": -110,
                "Consensus Odds": -108,
                "Hard Rock FL Available": "Yes",
                "Generic Hard Rock Available": "Yes",
                "Consensus Available": "Yes",
                "Confidence Label": "High confidence",
                "Source Label": "Hard Rock FL",
                "Source used": "Exact Hard Rock FL API",
                "Difference": -5,
                "Average odds": -108,
                "Best odds": -105,
                "Worst odds": -112,
                "Number of books": 3,
                "Consensus implied probability": 0.51,
                "bookmaker_key": "hardrockbet_fl",
                "api_market_key": "h2h",
            }
        ]
        package = build_ai_research_package(
            game_info={
                "Sport": "MLB",
                "League": "MLB",
                "Event": "Braves at Marlins",
                "Date": "2026-06-16T00:00:00Z",
                "Venue": "Unavailable",
            },
            found_lines=found_lines,
            missing_markets=[],
            manual_entries=[
                {
                    "Market": "Moneyline / 1X2",
                    "Selection": "Braves",
                    "Odds": -115,
                    "User notes": "Copied from app",
                    "Confidence": "Highest confidence",
                }
            ],
            bankroll=100.0,
            kelly_multiplier=0.25,
            api_usage=[{"API name": "API-Football", "Status": "Healthy"}],
            team_research=[{"Team": "Braves", "Last 5": "W-W-L-W-D"}],
            player_research=[{"Name": "Starter", "Position": "Forward"}],
            contextual_factors=[{"Factor": "Weather", "Value": "Clear"}],
            integration_diagnostics={
                "Home team API-Football team ID": 123,
                "Fixture history request attempted": "Yes",
                "Weather coordinates available": "Yes",
            },
            compatibility_summary=[
                {
                    "Dashboard cell": "Last 5",
                    "Needed endpoint": "/fixtures",
                    "Required params": "team, season, from, to",
                    "Current params available": "team_id",
                    "API returned data": "Yes",
                    "Status": "Fillable now",
                    "Notes": "Season/date range",
                }
            ],
            api_capability_audit={
                "apis_configured": [
                    {"API": "API-Football", "Connected": "Yes"},
                    {"API": "football-data.org", "Connected": "Yes"},
                ],
                "compatibility_matrix": [
                    {
                        "Dashboard cell": "Last 5",
                        "Fillability status": "Fillable through backup API only after team/match mapping is implemented",
                    }
                ],
                "bet_type_support_matrix": [
                    {
                        "Bet type": "Player Shots",
                        "Recommendation status": "Manual research required",
                    }
                ],
                "missing_data": ["Last 5: needs mapping"],
                "manual_research_checklist": ["Confirm Hard Rock FL manually."],
            },
            team_mappings={"Braves": {"id": 123, "matched_name": "Braves"}},
            missing_data=["No fixture history returned by season/date range"],
        )

        parsed_json = json.loads(ai_package_to_json(package))
        self.assertEqual(parsed_json["source_summary"]["Number of Hard Rock FL lines"], 1)
        self.assertEqual(parsed_json["team_research"][0]["Team"], "Braves")
        self.assertEqual(parsed_json["player_research"][0]["Name"], "Starter")
        self.assertEqual(parsed_json["contextual_factors"][0]["Factor"], "Weather")
        self.assertEqual(
            parsed_json["integration_diagnostics"]["Fixture history request attempted"],
            "Yes",
        )
        self.assertEqual(parsed_json["team_mappings"]["Braves"]["id"], 123)
        self.assertEqual(parsed_json["compatibility_summary"][0]["Dashboard cell"], "Last 5")
        self.assertEqual(parsed_json["api_capability_audit"]["apis_configured"][0]["Connected"], "Yes")
        markdown = ai_package_to_markdown(package)
        self.assertIn("## Section 8 - Bet Rankings", markdown)
        self.assertIn("TOP 5 POTENTIAL VALUE BETS", markdown)
        self.assertIn("## Section 10 - Data Gaps", markdown)
        self.assertIn("## Team Research", markdown)
        self.assertIn("## Player Research", markdown)
        self.assertIn("## Contextual Factors", markdown)
        self.assertIn("## Live Integration Diagnostics", markdown)
        self.assertIn("API-Football Team ID Mappings", markdown)
        self.assertIn("## API Compatibility Summary", markdown)
        self.assertIn("## API Capability Audit", markdown)
        self.assertIn("Bet-Type Support Matrix", markdown)
        self.assertNotIn('{"Market Category"', markdown)
        chatgpt_markdown = chatgpt_analysis_package_to_markdown(package)
        self.assertIn("# ChatGPT Analysis Package", chatgpt_markdown)
        self.assertIn("## API Capability Audit Summary", chatgpt_markdown)
        self.assertIn("Bet-Type Support Matrix", chatgpt_markdown)
        self.assertNotIn('{"Market Category"', chatgpt_markdown)
        csv_rows = list(csv.DictReader(ai_package_to_csv(package).splitlines()))
        self.assertTrue(csv_rows)
        self.assertTrue(any(row["section"] == "quantitative_analysis" for row in csv_rows))


if __name__ == "__main__":
    unittest.main()
