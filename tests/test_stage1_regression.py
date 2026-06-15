from __future__ import annotations

import unittest

from src.ev import build_bet_result
from src.parlay import calculate_parlay
from src.probabilities import american_to_decimal, american_to_implied_probability


class Stage1RegressionTests(unittest.TestCase):
    def test_probability_and_ev_calculations(self):
        self.assertAlmostEqual(american_to_decimal(-110), 1 + 100 / 110)
        self.assertAlmostEqual(american_to_implied_probability(-110), 110 / 210)

        bet = build_bet_result(
            sport="NFL",
            event="A vs B",
            market="Moneyline",
            selection="A",
            american_odds=150,
            model_probability=0.50,
            stake=1.0,
            bankroll=100.0,
            kelly_multiplier=0.25,
            data_quality="normal",
        )

        self.assertAlmostEqual(bet.ev_per_1_dollar, 0.25)
        self.assertAlmostEqual(bet.potential_payout, 2.50)

    def test_two_leg_parlay(self):
        legs = [
            {
                "event": "A vs B",
                "market": "Moneyline",
                "selection": "A",
                "hardrock_odds": 100,
                "model_probability": 0.5,
            },
            {
                "event": "C vs D",
                "market": "Moneyline",
                "selection": "C",
                "hardrock_odds": 100,
                "model_probability": 0.5,
            },
        ]

        result = calculate_parlay(legs=legs, stake=1.0)

        self.assertEqual(result.combined_decimal_odds, 4.0)
        self.assertEqual(result.estimated_probability, 0.25)
        self.assertEqual(result.potential_payout, 4.0)


if __name__ == "__main__":
    unittest.main()
