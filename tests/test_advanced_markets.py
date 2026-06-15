from __future__ import annotations

import unittest

from src.advanced_markets import (
    build_advanced_market_card,
    create_market_template,
    determine_api_availability,
    market_support_matrix,
    source_details,
)


class AdvancedMarketsTests(unittest.TestCase):
    def test_market_template_creation(self):
        template = create_market_template("BTTS")
        self.assertEqual(template.api_market_keys, ("btts",))
        self.assertFalse(template.manual_only)

    def test_api_availability_labeling(self):
        template = create_market_template("BTTS")
        availability = determine_api_availability(
            template,
            [
                {
                    "market_key": "btts",
                    "selection": "Yes",
                    "price": -110,
                }
            ],
        )
        self.assertTrue(availability["available"])
        self.assertEqual(availability["label"], "API-backed")
        self.assertEqual(len(availability["outcomes"]), 1)

    def test_manual_only_bet_card_creation(self):
        card = build_advanced_market_card(
            sport="Soccer",
            event="Inter Miami at Orlando City",
            market_category="Other Manual Market",
            selection="First half draw",
            point=None,
            american_odds=150,
            estimated_probability=0.45,
            stake=1.0,
            bankroll=100.0,
            kelly_multiplier=0.25,
        )
        self.assertEqual(card.source_label, "Manual-only")
        self.assertAlmostEqual(card.potential_payout, 2.5)
        self.assertAlmostEqual(card.ev_per_1_dollar, 0.125)

    def test_unsupported_market_handling(self):
        with self.assertRaisesRegex(ValueError, "Unsupported market category"):
            create_market_template("Martian Goal Bonus")

    def test_dynamic_player_template_and_support_matrix(self):
        template = create_market_template("Anytime Goalscorer")
        self.assertTrue(template.dynamic_player)
        self.assertEqual(template.tier, "Tier 2")

        matrix = market_support_matrix()
        row = next(item for item in matrix if item["Market"] == "Anytime Goalscorer")
        self.assertEqual(row["Manual"], "Yes")
        self.assertEqual(row["Other APIs"], "Mapped")

    def test_source_confidence_taxonomy(self):
        self.assertEqual(
            source_details("hardrockbet_fl"),
            ("Hard Rock Florida confirmed", "High"),
        )
        self.assertEqual(
            source_details("hardrockbet"),
            ("Hard Rock generic feed", "Medium"),
        )


if __name__ == "__main__":
    unittest.main()
