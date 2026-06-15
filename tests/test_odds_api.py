from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from src.odds_api import (
    HARD_ROCK_FL_BOOKMAKER,
    HARD_ROCK_GENERIC_BOOKMAKER,
    MissingApiKeyError,
    OddsApiError,
    extract_event_rows,
    extract_market_outcomes,
    get_bookmaker_diagnostics,
    get_hardrock_fl_odds,
    get_sports,
    read_api_key,
    select_hardrock_bookmaker,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class OddsApiTests(unittest.TestCase):
    def test_event_table_extraction(self):
        events = extract_event_rows(
            [
                {
                    "id": "event-1",
                    "commence_time": "2026-06-16T12:00:00Z",
                    "home_team": "Marlins",
                    "away_team": "Braves",
                    "bookmakers": [
                        {"key": "fanduel", "title": "FanDuel"},
                        {
                            "key": HARD_ROCK_GENERIC_BOOKMAKER,
                            "title": "Hard Rock Bet",
                        },
                    ],
                }
            ],
            "baseball_mlb",
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["event"], "Braves at Marlins")
        self.assertEqual(event["home_team"], "Marlins")
        self.assertEqual(event["away_team"], "Braves")
        self.assertEqual(
            event["bookmaker_keys"],
            ["fanduel", HARD_ROCK_GENERIC_BOOKMAKER],
        )
        self.assertFalse(event["hardrockbet_fl_present"])
        self.assertTrue(event["hardrockbet_present"])

    def test_market_outcome_extraction(self):
        rows = extract_market_outcomes(
            {
                "bookmakers": [
                    {
                        "key": HARD_ROCK_FL_BOOKMAKER,
                        "title": "Hard Rock Bet (FL)",
                        "markets": [
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {
                                        "name": "Braves",
                                        "price": -110,
                                        "point": -1.5,
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "key": "fanduel",
                        "title": "FanDuel",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Marlins", "price": 120}
                                ],
                            }
                        ],
                    },
                ]
            }
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[0],
            {
                "bookmaker": "Hard Rock Bet (FL)",
                "bookmaker_key": HARD_ROCK_FL_BOOKMAKER,
                "market_key": "spreads",
                "selection": "Braves",
                "price": -110,
                "point": -1.5,
                "is_hardrock": True,
                "is_florida": True,
            },
        )
        self.assertEqual(rows[1]["market_key"], "h2h")
        self.assertEqual(rows[1]["point"], None)

    def test_selects_florida_key_when_only_florida_is_present(self):
        self.assertEqual(
            select_hardrock_bookmaker(
                [HARD_ROCK_FL_BOOKMAKER],
                allow_generic=False,
            ),
            HARD_ROCK_FL_BOOKMAKER,
        )

    def test_selects_generic_key_when_only_generic_is_present_and_allowed(self):
        self.assertEqual(
            select_hardrock_bookmaker(
                [HARD_ROCK_GENERIC_BOOKMAKER],
                allow_generic=True,
            ),
            HARD_ROCK_GENERIC_BOOKMAKER,
        )

    def test_prioritizes_florida_key_when_both_are_present(self):
        self.assertEqual(
            select_hardrock_bookmaker(
                [HARD_ROCK_GENERIC_BOOKMAKER, HARD_ROCK_FL_BOOKMAKER],
                allow_generic=True,
            ),
            HARD_ROCK_FL_BOOKMAKER,
        )

    def test_returns_none_when_neither_key_is_present(self):
        self.assertIsNone(
            select_hardrock_bookmaker(
                ["fanduel", "draftkings"],
                allow_generic=True,
            )
        )

    def test_generic_key_is_not_used_in_florida_only_mode(self):
        self.assertIsNone(
            select_hardrock_bookmaker(
                [HARD_ROCK_GENERIC_BOOKMAKER],
                allow_generic=False,
            )
        )

    def test_read_api_key_requires_nonempty_value(self):
        with self.assertRaises(MissingApiKeyError):
            read_api_key({})
        self.assertEqual(read_api_key({"THE_ODDS_API_KEY": " test-key "}), "test-key")

    @patch("src.odds_api.urlopen")
    def test_get_sports_sorts_and_filters_invalid_rows(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(
            [
                {
                    "key": "basketball_nba",
                    "group": "Basketball",
                    "title": "NBA",
                    "active": True,
                },
                {"group": "Broken", "title": "Missing key"},
                {
                    "key": "baseball_mlb",
                    "group": "Baseball",
                    "title": "MLB",
                    "active": True,
                },
            ]
        )

        sports = get_sports("test-key")

        self.assertEqual([sport["key"] for sport in sports], ["baseball_mlb", "basketball_nba"])
        requested_url = mock_urlopen.call_args.args[0]
        self.assertIn("/sports/", requested_url)
        self.assertIn("apiKey=test-key", requested_url)

    @patch("src.odds_api.urlopen")
    def test_hardrock_odds_only_returns_florida_bookmaker(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(
            [
                {
                    "sport_title": "MLB",
                    "commence_time": "2026-06-16T00:00:00Z",
                    "home_team": "Miami Marlins",
                    "away_team": "Atlanta Braves",
                    "bookmakers": [
                        {
                            "key": "fanduel",
                            "title": "FanDuel",
                            "markets": [
                                {
                                    "key": "h2h",
                                    "outcomes": [{"name": "Atlanta Braves", "price": -120}],
                                }
                            ],
                        },
                        {
                            "key": HARD_ROCK_FL_BOOKMAKER,
                            "title": "Hard Rock Bet (FL)",
                            "last_update": "2026-06-15T19:00:00Z",
                            "markets": [
                                {
                                    "key": "h2h",
                                    "outcomes": [
                                        {"name": "Atlanta Braves", "price": -115},
                                        {"name": "Miami Marlins", "price": 105},
                                    ],
                                },
                                {
                                    "key": "spreads",
                                    "outcomes": [
                                        {
                                            "name": "Atlanta Braves",
                                            "price": 100,
                                            "point": -1.5,
                                        }
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ]
        )

        rows = get_hardrock_fl_odds("test-key", "baseball_mlb")

        self.assertEqual(len(rows), 3)
        self.assertTrue(
            all(row["bookmaker_key"] == HARD_ROCK_FL_BOOKMAKER for row in rows)
        )
        self.assertNotIn(-120, [row["price"] for row in rows])
        requested_url = mock_urlopen.call_args.args[0]
        self.assertIn("bookmakers=hardrockbet_fl%2Chardrockbet", requested_url)
        self.assertIn("oddsFormat=american", requested_url)

    @patch("src.odds_api.urlopen")
    def test_diagnostics_are_unfiltered_and_deduplicate_bookmakers(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(
            [
                {
                    "id": "later-event",
                    "away_team": "Yankees",
                    "home_team": "Red Sox",
                    "commence_time": "2026-06-17T00:00:00Z",
                    "bookmakers": [
                        {"key": "fanduel"},
                        {"key": "draftkings"},
                    ]
                },
                {
                    "id": "earlier-event",
                    "away_team": "Braves",
                    "home_team": "Marlins",
                    "commence_time": "2026-06-16T00:00:00Z",
                    "bookmakers": [
                        {"key": "fanduel"},
                        {
                            "key": HARD_ROCK_FL_BOOKMAKER,
                            "title": "Hard Rock Bet (FL)",
                        },
                    ]
                },
            ]
        )

        diagnostic = get_bookmaker_diagnostics(
            "test-key",
            "baseball_mlb",
            market="h2h",
        )

        self.assertEqual(diagnostic["event_count"], 2)
        self.assertEqual(diagnostic["bookmaker_count"], 3)
        self.assertEqual(
            diagnostic["bookmaker_keys"],
            ["draftkings", "fanduel", HARD_ROCK_FL_BOOKMAKER],
        )
        self.assertTrue(diagnostic["hardrockbet_fl_present"])
        self.assertEqual(
            [event["id"] for event in diagnostic["events"]],
            ["earlier-event", "later-event"],
        )
        self.assertEqual(
            diagnostic["events"][0]["label"],
            "Braves at Marlins",
        )
        florida_bookmaker = next(
            bookmaker
            for bookmaker in diagnostic["events"][0]["bookmakers"]
            if bookmaker["key"] == HARD_ROCK_FL_BOOKMAKER
        )
        self.assertTrue(florida_bookmaker["is_hardrock"])
        self.assertTrue(florida_bookmaker["is_florida"])

        requested_url = mock_urlopen.call_args.args[0]
        self.assertIn("regions=us%2Cus2", requested_url)
        self.assertNotIn("bookmakers=", requested_url)

    @patch("src.odds_api.urlopen")
    def test_diagnostics_report_absent_hardrock(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(
            [{"bookmakers": [{"key": "fanduel"}, {"key": "draftkings"}]}]
        )

        diagnostic = get_bookmaker_diagnostics("test-key", "basketball_wnba")

        self.assertFalse(diagnostic["hardrockbet_fl_present"])
        self.assertEqual(diagnostic["event_count"], 1)

    @patch("src.odds_api.urlopen")
    def test_event_explorer_deduplicates_event_bookmakers(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(
            [
                {
                    "id": "event-1",
                    "away_team": "A",
                    "home_team": "B",
                    "commence_time": "2026-06-16T12:00:00Z",
                    "bookmakers": [
                        {"key": "fanduel", "title": "FanDuel"},
                        {"key": "fanduel", "title": "FanDuel"},
                        {
                            "key": HARD_ROCK_GENERIC_BOOKMAKER,
                            "title": "Hard Rock Bet",
                        },
                    ],
                }
            ]
        )

        diagnostic = get_bookmaker_diagnostics("test-key", "baseball_mlb")
        event = diagnostic["events"][0]

        self.assertEqual(event["id"], "event-1")
        self.assertEqual(event["commence_time"], "2026-06-16T12:00:00Z")
        self.assertEqual(
            [bookmaker["key"] for bookmaker in event["bookmakers"]],
            ["fanduel", HARD_ROCK_GENERIC_BOOKMAKER],
        )
        generic = event["bookmakers"][1]
        self.assertTrue(generic["is_hardrock"])
        self.assertFalse(generic["is_florida"])

    @patch("src.odds_api.urlopen")
    def test_http_errors_become_safe_messages(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="https://example.invalid",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

        with self.assertRaisesRegex(OddsApiError, "rejected the key"):
            get_sports("bad-key")


if __name__ == "__main__":
    unittest.main()
