from __future__ import annotations

import unittest

from src.research_board import (
    build_research_card,
    classify_source,
    enrich_odds_rows,
    market_availability_row,
    source_summary,
)


class ResearchBoardTests(unittest.TestCase):
    def test_source_classification(self):
        self.assertEqual(
            classify_source("hardrockbet_fl"),
            ("Exact Hard Rock Florida API", "High confidence"),
        )
        self.assertEqual(
            classify_source("hardrockbet"),
            ("Generic Hard Rock API", "Medium confidence, may differ from Florida"),
        )
        self.assertEqual(
            classify_source(None, manual=True),
            ("Manual Hard Rock Florida Entry", "Highest confidence"),
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
        self.assertEqual(card.source_type, "Manual Hard Rock Florida Entry")
        self.assertEqual(card.confidence, "Highest confidence")
        self.assertAlmostEqual(card.edge, 0.55 - 100 / 220)


if __name__ == "__main__":
    unittest.main()
