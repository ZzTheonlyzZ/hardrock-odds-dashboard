from __future__ import annotations

import json
import unittest
import app as dashboard_app
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from src.odds_api import MissingApiKeyError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def fake_api_response(url, timeout):
    if "/sports/?" in url:
        return FakeResponse(
            [
                {
                    "key": "baseball_mlb",
                    "group": "Baseball",
                    "title": "MLB",
                    "active": True,
                }
            ]
        )

    return FakeResponse(
        [
            {
                "id": "mlb-1",
                "sport_title": "MLB",
                "commence_time": "2026-06-16T00:00:00Z",
                "home_team": "Miami Marlins",
                "away_team": "Atlanta Braves",
                "bookmakers": [
                    {
                        "key": "fanduel",
                        "title": "FanDuel",
                        "last_update": "2026-06-15T19:00:00Z",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Atlanta Braves", "price": -115},
                                    {"name": "Miami Marlins", "price": 105},
                                ],
                            }
                        ],
                    },
                    {
                        "key": "hardrockbet",
                        "title": "Hard Rock Bet",
                        "markets": [],
                    }
                ],
            }
        ]
    )


def fake_generic_hardrock_response(url, timeout):
    if "/sports/?" in url:
        return FakeResponse(
            [
                {
                    "key": "baseball_mlb",
                    "group": "Baseball",
                    "title": "MLB",
                    "active": True,
                }
            ]
        )

    return FakeResponse(
        [
            {
                "id": "generic-event",
                "commence_time": "2026-06-16T00:00:00Z",
                "home_team": "Marlins",
                "away_team": "Braves",
                "bookmakers": [
                    {
                        "key": "hardrockbet",
                        "title": "Hard Rock Bet",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Braves", "price": -105}
                                ],
                            }
                        ],
                    }
                ]
            }
        ]
    )


class AppTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()

    def test_stage1_navigation_still_renders(self):
        app = AppTest.from_file("app.py", default_timeout=10).run()

        self.assertFalse(app.exception)
        self.assertEqual(
            app.radio[0].options,
            [
                "Home",
                "Research Board",
                "Manual Entry",
                "Bet Cards",
                "Parlay Builder",
                "Settings",
                "Stage Status",
            ],
        )
        self.assertNotIn("Live Odds", app.radio[0].options)
        self.assertNotIn("Market Comparison", app.radio[0].options)
        self.assertNotIn("Advanced Markets", app.radio[0].options)
        self.assertEqual(app.session_state["navigation_page"], "Research Board")

        app.radio[0].set_value("Manual Entry").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Manual Entry + EV Calculator")

    def test_legacy_pages_are_internal_debug_renderers(self):
        self.assertFalse(dashboard_app.DEBUG_MODE)
        self.assertTrue(callable(dashboard_app.render_live_odds_page))
        self.assertTrue(callable(dashboard_app.render_market_comparison_page))
        self.assertTrue(callable(dashboard_app.render_advanced_markets_page))

    @patch(
        "src.odds_api.read_api_key",
        side_effect=MissingApiKeyError("The Odds API key is missing."),
    )
    def test_missing_key_is_safe(self, _mock_read_api_key):
        app = AppTest.from_file("app.py", default_timeout=10).run()

        self.assertFalse(app.exception)
        self.assertTrue(any("key is missing" in error.value for error in app.error))
        self.assertEqual(app.title[0].value, "Research Board")

    @patch("src.odds_api.urlopen", side_effect=fake_api_response)
    def test_research_board_shows_missing_hardrock_api_warning(self, _mock_urlopen):
        app = AppTest.from_file("app.py", default_timeout=10).run()

        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].value, "Baseball | MLB")

        app.button[0].click().run()
        load_market = next(
            button
            for button in app.button
            if button.label == "Load odds / source availability"
        )
        load_market.click().run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                warning.value
                == (
                    "No Hard Rock API line found for this market. Use Manual Hard "
                    "Rock FL Entry and compare against market consensus."
                )
                for warning in app.warning
            )
        )
        self.assertTrue(
            any(tab.label == "Market Consensus" for tab in app.tabs)
        )
        self.assertTrue(
            any(
                "Market Consensus / Other Books: Comparison only" in markdown.value
                for markdown in app.markdown
            )
        )

    @patch("src.odds_api.urlopen", side_effect=fake_generic_hardrock_response)
    def test_generic_feed_setting_shows_required_warning(self, _mock_urlopen):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        app.radio[0].set_value("Settings").run()

        feed_radio = next(
            radio
            for radio in app.radio
            if radio.label == "Hard Rock bookmaker matching"
        )
        feed_radio.set_value("Allow generic Hard Rock").run()
        self.assertEqual(
            app.session_state["hardrock_feed_mode"],
            "Allow generic Hard Rock",
        )

        navigation = next(radio for radio in app.radio if radio.label == "Go to")
        navigation.set_value("Research Board").run()
        app.button[0].click().run()
        load_market = next(
            button
            for button in app.button
            if button.label == "Load odds / source availability"
        )
        load_market.click().run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                warning.value
                == "Generic Hard Rock API | Medium confidence, may differ from Florida"
                for warning in app.warning
            )
        )
        self.assertTrue(
            any(
                tab.label == "Generic Hard Rock"
                for tab in app.tabs
            )
        )

    @patch("src.odds_api.urlopen", side_effect=fake_api_response)
    def test_research_board_preserves_stage3_market_consensus(self, _mock_urlopen):
        app = AppTest.from_file("app.py", default_timeout=10).run()

        load_button = next(
            button
            for button in app.button
            if button.label == "Load games"
        )
        load_button.click().run()
        load_market = next(
            button
            for button in app.button
            if button.label == "Load odds / source availability"
        )
        load_market.click().run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(tab.label == "Market Consensus" for tab in app.tabs)
        )
        self.assertTrue(
            any("Market average and no-vig consensus" in markdown.value for markdown in app.markdown)
        )

    @patch("src.odds_api.urlopen", side_effect=fake_api_response)
    def test_research_board_preserves_advanced_manual_market_card(self, _mock_urlopen):
        app = AppTest.from_file("app.py", default_timeout=10).run()

        load_button = next(
            button
            for button in app.button
            if button.label == "Load games"
        )
        load_button.click().run()

        category = next(
            selectbox
            for selectbox in app.selectbox
            if selectbox.label == "Market category"
        )
        category.set_value("Other").run()

        load_market = next(
            button
            for button in app.button
            if button.label == "Load odds / source availability"
        )
        load_market.click().run()

        selection = next(
            text_input
            for text_input in app.text_input
            if text_input.label == "Research selection"
        )
        selection.set_value("First half draw")
        create_button = next(
            button
            for button in app.button
            if button.label == "Create Research Board bet card"
        )
        create_button.click().run()

        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state["research_cards"]), 1)
        self.assertEqual(
            app.session_state["research_cards"][0]["source_type"],
            "Manual Hard Rock FL Entry",
        )
        self.assertTrue(
            any(
                "Research Board bet card created" in success.value
                for success in app.success
            )
        )

    @patch("src.odds_api.urlopen", side_effect=fake_api_response)
    def test_research_board_unifies_sources_and_creates_manual_card(
        self,
        _mock_urlopen,
    ):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        self.assertEqual(app.title[0].value, "Research Board")

        load_games = next(
            button for button in app.button if button.label == "Load games"
        )
        load_games.click().run()

        load_market = next(
            button
            for button in app.button
            if button.label == "Load odds / source availability"
        )
        load_market.click().run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                warning.value
                == (
                    "No Hard Rock API line found for this market. Use Manual Hard "
                    "Rock FL Entry and compare against market consensus."
                )
                for warning in app.warning
            )
        )
        self.assertTrue(
            any(tab.label == "Manual Hard Rock FL Entry" for tab in app.tabs)
        )

        selection = next(
            text_input
            for text_input in app.text_input
            if text_input.label == "Research selection"
        )
        selection.set_value("Atlanta Braves")
        create = next(
            button
            for button in app.button
            if button.label == "Create Research Board bet card"
        )
        create.click().run()

        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state["research_cards"]), 1)
        card = app.session_state["research_cards"][0]
        self.assertEqual(card["source_type"], "Manual Hard Rock FL Entry")
        self.assertEqual(
            card["confidence"],
            "User-confirmed, highest confidence if copied from app",
        )


if __name__ == "__main__":
    unittest.main()
