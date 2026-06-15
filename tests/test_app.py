from __future__ import annotations

import json
import unittest
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
                "Live Odds",
                "Manual Entry",
                "Bet Cards",
                "Parlay Builder",
                "Settings",
                "Stage Status",
            ],
        )

        app.radio[0].set_value("Manual Entry").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Manual Entry + EV Calculator")

    @patch(
        "src.odds_api.read_api_key",
        side_effect=MissingApiKeyError("The Odds API key is missing."),
    )
    def test_missing_key_is_safe(self, _mock_read_api_key):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        navigation = next(radio for radio in app.radio if radio.label == "Go to")
        navigation.set_value("Live Odds").run()

        self.assertFalse(app.exception)
        self.assertTrue(any("key is missing" in error.value for error in app.error))
        self.assertTrue(any("Stage 1 pages remain available" in info.value for info in app.info))

    @patch("src.odds_api.urlopen", side_effect=fake_api_response)
    def test_diagnostic_page_shows_unfiltered_upstream_warning(self, _mock_urlopen):
        app = AppTest.from_file("app.py", default_timeout=10).run()
        app.radio[0].set_value("Live Odds").run()

        self.assertFalse(app.exception)
        self.assertTrue(any("Sports list loaded" in item.value for item in app.success))
        self.assertEqual(app.selectbox[0].value, "Baseball | MLB")

        app.button[0].click().run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any("Florida only" in item.value for item in app.warning)
        )
        self.assertGreaterEqual(len(app.dataframe), 3)
        self.assertEqual(app.selectbox[2].value, "2026-06-16T00:00:00Z | Atlanta Braves at Miami Marlins")
        self.assertTrue(
            any("Date/time:" in markdown.value for markdown in app.markdown)
        )
        self.assertTrue(
            any(
                warning.value
                == "No Hard Rock odds available from the API for this event. Use this only as market reference."
                for warning in app.warning
            )
        )

        prefill_button = next(
            button
            for button in app.button
            if button.label == "Create manual bet card from this line"
        )
        prefill_button.click().run()

        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["navigation_page"], "Manual Entry")
        self.assertEqual(app.session_state["manual_sport"], "MLB")
        self.assertEqual(
            app.session_state["manual_event"],
            "Atlanta Braves at Miami Marlins",
        )
        self.assertEqual(app.session_state["manual_market"], "Moneyline")
        self.assertEqual(app.session_state["manual_selection"], "Atlanta Braves")
        self.assertEqual(app.session_state["manual_american_odds"], -115)

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
        navigation.set_value("Live Odds").run()
        app.button[0].click().run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                warning.value
                == "Using generic Hard Rock feed. This may differ from Florida-specific pricing."
                for warning in app.warning
            )
        )
        self.assertTrue(
            any(
                warning.value
                == "Using generic Hard Rock feed. Confirm manually in the Hard Rock Florida app."
                for warning in app.warning
            )
        )
        self.assertTrue(
            any(
                checkbox.label == "Show only Hard Rock odds"
                for checkbox in app.checkbox
            )
        )


if __name__ == "__main__":
    unittest.main()
