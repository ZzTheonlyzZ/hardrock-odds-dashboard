from __future__ import annotations

import unittest

from src.market_comparison import (
    build_stage3_bet_card,
    calculate_market_comparison,
)
from src.probabilities import american_to_implied_probability


class MarketComparisonTests(unittest.TestCase):
    def setUp(self):
        self.outcomes = [
            {
                "bookmaker_key": "book_a",
                "selection": "Team A",
                "price": -110,
                "point": None,
            },
            {
                "bookmaker_key": "book_a",
                "selection": "Team B",
                "price": -110,
                "point": None,
            },
            {
                "bookmaker_key": "book_b",
                "selection": "Team A",
                "price": 100,
                "point": None,
            },
            {
                "bookmaker_key": "book_b",
                "selection": "Team B",
                "price": -120,
                "point": None,
            },
        ]

    def test_implied_probability(self):
        self.assertAlmostEqual(
            american_to_implied_probability(-110),
            110 / 210,
        )

    def test_no_vig_calculation(self):
        comparison = calculate_market_comparison(self.outcomes)
        team_a = next(row for row in comparison if row["selection"] == "Team A")

        book_a_fair = 0.5
        book_b_fair = 0.5 / (0.5 + 120 / 220)
        self.assertAlmostEqual(
            team_a["market_no_vig_probability"],
            (book_a_fair + book_b_fair) / 2,
        )

    def test_market_average_calculation(self):
        comparison = calculate_market_comparison(self.outcomes)
        team_a = next(row for row in comparison if row["selection"] == "Team A")

        expected_decimal = ((1 + 100 / 110) + 2.0) / 2
        self.assertAlmostEqual(
            team_a["market_average_decimal_odds"],
            expected_decimal,
        )
        self.assertEqual(team_a["bookmaker_count"], 2)

    def test_ev_using_manual_hardrock_override(self):
        comparison = calculate_market_comparison(self.outcomes)
        team_a = next(row for row in comparison if row["selection"] == "Team A")

        card = build_stage3_bet_card(
            sport="MLB",
            event="Team B at Team A",
            market="Moneyline",
            selection="Team A",
            hardrock_odds=120,
            market_no_vig_probability=team_a["market_no_vig_probability"],
            market_average_american_odds=team_a[
                "market_average_american_odds"
            ],
            bookmaker_count=team_a["bookmaker_count"],
            stake=1.0,
            bankroll=100.0,
            kelly_multiplier=0.25,
        )

        expected_ev = (
            team_a["market_no_vig_probability"] * 1.2
            - (1 - team_a["market_no_vig_probability"])
        )
        self.assertAlmostEqual(card.ev_per_1_dollar, expected_ev)
        self.assertEqual(card.potential_payout, 2.2)


if __name__ == "__main__":
    unittest.main()
