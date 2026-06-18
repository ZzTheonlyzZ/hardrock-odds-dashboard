from __future__ import annotations

import json
import unittest

from src.api_capability_audit import (
    api_capability_audit_to_json,
    api_capability_audit_to_markdown,
    build_api_capability_audit,
)


class ApiCapabilityAuditTests(unittest.TestCase):
    def _audit(self, *, context_data=None, found_lines=None):
        scanner_data = {
            "sport_key": "soccer_fifa_world_cup",
            "event": "Canada at Qatar",
            "found_lines": found_lines or [
                {
                    "Market Category": "Match",
                    "Specific Market": "Moneyline / 1X2",
                    "Selection": "Canada",
                    "Odds": 120,
                    "Hard Rock FL Available": "No",
                    "Generic Hard Rock Available": "Yes",
                    "Consensus Available": "Yes",
                    "bookmaker_key": "hardrockbet",
                    "api_market_key": "h2h",
                }
            ],
            "errors": [],
        }
        return build_api_capability_audit(
            selected_event={
                "event": "Qatar at Canada",
                "home_team": "Canada",
                "away_team": "Qatar",
                "commence_time": "2026-06-18T20:00:00Z",
            },
            scanner_data=scanner_data,
            context_data=context_data
            or {
                "team_form": [],
                "players": [],
                "context": [],
                "integration_diagnostics": {},
                "player_summary": {"Squad players loaded": 0},
                "api_request_log": [],
                "compatibility_summary": [],
            },
            odds_key_found=True,
            api_football_key_found=True,
            football_data_key_found=True,
            manual_coordinates_available=False,
        )

    def test_audit_maps_odds_api_to_market_cells_only(self):
        audit = self._audit()
        matrix = {row["Dashboard cell"]: row for row in audit["compatibility_matrix"]}
        self.assertEqual(matrix["Implied probability"]["Best source"], "The Odds API")
        self.assertEqual(matrix["Implied probability"]["Fillability status"], "Fillable now")
        self.assertNotEqual(matrix["Last 5"]["Best source"], "The Odds API")
        self.assertNotEqual(matrix["Player names"]["Best source"], "The Odds API")

    def test_squad_maps_names_positions_not_per_90_stats(self):
        audit = self._audit(
            context_data={
                "team_form": [],
                "players": [{"Name": "Player", "Position": "Forward"}],
                "context": [],
                "integration_diagnostics": {},
                "player_summary": {"Squad players loaded": 1},
                "api_request_log": [],
                "compatibility_summary": [],
            }
        )
        matrix = {row["Dashboard cell"]: row for row in audit["compatibility_matrix"]}
        self.assertEqual(matrix["Player names"]["Fillability status"], "Fillable now")
        self.assertEqual(matrix["Position"]["Fillability status"], "Fillable now")
        self.assertEqual(matrix["Goals per 90"]["Fillability status"], "Needs paid/better source")

    def test_plan_block_and_historical_statuses_are_marked(self):
        blocked = self._audit(
            context_data={
                "team_form": [],
                "players": [],
                "context": [],
                "integration_diagnostics": {
                    "Last safe API error message": "Free plans do not have access to this season",
                },
                "player_summary": {"Squad players loaded": 0},
                "api_request_log": [],
                "compatibility_summary": [],
            }
        )
        blocked_matrix = {row["Dashboard cell"]: row for row in blocked["compatibility_matrix"]}
        self.assertEqual(blocked_matrix["Last 5"]["Fillability status"], "Blocked by current API plan")

        historical = self._audit(
            context_data={
                "team_form": [],
                "players": [],
                "context": [],
                "integration_diagnostics": {"Home rows returned by season": '{"2022": 3, "2023": 4}'},
                "player_summary": {"Squad players loaded": 0},
                "api_request_log": [],
                "compatibility_summary": [],
            }
        )
        historical_matrix = {row["Dashboard cell"]: row for row in historical["compatibility_matrix"]}
        self.assertEqual(historical_matrix["Last 5"]["Fillability status"], "Historical/stale only")

    def test_football_data_backup_and_open_meteo_wording(self):
        audit = self._audit()
        api_football = next(row for row in audit["apis_configured"] if row["API"] == "API-Football")
        self.assertEqual(api_football["Connected"], "Yes")
        matrix = {row["Dashboard cell"]: row for row in audit["compatibility_matrix"]}
        self.assertEqual(
            matrix["Last 5"]["Fillability status"],
            "Fillable through backup API only after team/match mapping is implemented",
        )
        self.assertNotEqual(matrix["Last 5"]["Fillability status"], "Fillable now")
        weather = next(row for row in audit["endpoints_tested"] if row["API/source"] == "Open-Meteo")
        self.assertEqual(weather["Status"], "Needs manual venue coordinates")
        self.assertNotIn("API key missing", json.dumps(weather))

    def test_football_data_rows_upgrade_team_form_only(self):
        audit = self._audit(
            context_data={
                "team_form": [
                    {
                        "Team": "Canada",
                        "Status": "Live football-data.org team-match history",
                    },
                    {
                        "Team": "Qatar",
                        "Status": "Live football-data.org team-match history",
                    },
                ],
                "players": [],
                "context": [],
                "integration_diagnostics": {
                    "football-data.org key found": "Yes",
                    "football-data.org competition code used": "WC",
                    "football-data.org seasons tried": "2026, 2025, 2024, 2023, 2022",
                    "football-data.org match rows used": 12,
                    "Home football-data.org mapped team id": 1,
                    "Away football-data.org mapped team id": 2,
                    "Home football-data.org mapped team name": "Canada",
                    "Away football-data.org mapped team name": "Qatar",
                },
                "player_summary": {"Squad players loaded": 0},
                "api_request_log": [],
                "compatibility_summary": [],
            }
        )
        matrix = {row["Dashboard cell"]: row for row in audit["compatibility_matrix"]}
        self.assertEqual(matrix["Last 5"]["Fillability status"], "Fillable now via football-data.org")
        self.assertEqual(matrix["Last 5"]["Betting confidence impact"], "Can support model")
        endpoint = next(row for row in audit["endpoints_tested"] if row["API/source"] == "football-data.org")
        self.assertEqual(endpoint["Rows returned"], 12)
        by_bet = {row["Bet type"]: row for row in audit["bet_type_support_matrix"]}
        self.assertEqual(
            by_bet["Moneyline / 1X2"]["Recommendation status"],
            "Supported with odds + team form",
        )
        self.assertEqual(
            by_bet["BTTS"]["Recommendation status"],
            "Partial with BTTS/team goals form",
        )
        self.assertEqual(
            by_bet["Player Shots"]["Recommendation status"],
            "Manual research required",
        )

    def test_limited_football_data_sample_does_not_upgrade_moneyline(self):
        audit = self._audit(
            context_data={
                "team_form": [
                    {
                        "Team": "Canada",
                        "Status": "Limited football-data.org sample — not enough rows for Last 5 / Last 10.",
                    },
                    {
                        "Team": "Qatar",
                        "Status": "Limited football-data.org sample — not enough rows for Last 5 / Last 10.",
                    },
                ],
                "players": [],
                "context": [],
                "integration_diagnostics": {
                    "football-data.org match rows used": 4,
                    "football-data.org rows per team": '{"Canada": 2, "Qatar": 2}',
                    "football-data.org minimum rows per team": 2,
                    "football-data.org team-form sample quality": "Limited sample only",
                    "football-data.org Last 5 threshold met": "No",
                    "football-data.org Last 10 threshold met": "No",
                },
                "player_summary": {"Squad players loaded": 0},
                "api_request_log": [],
                "compatibility_summary": [],
            }
        )
        matrix = {row["Dashboard cell"]: row for row in audit["compatibility_matrix"]}
        self.assertEqual(matrix["Last 5"]["Fillability status"], "Limited sample only")
        self.assertEqual(matrix["Last 10"]["Fillability status"], "Limited sample only")
        self.assertEqual(
            matrix["Last 5"]["Betting confidence impact"],
            "Context only — do not upgrade confidence",
        )
        by_bet = {row["Bet type"]: row for row in audit["bet_type_support_matrix"]}
        self.assertEqual(
            by_bet["Moneyline / 1X2"]["Current automated support"],
            "Partial with limited team form",
        )
        self.assertEqual(
            by_bet["Moneyline / 1X2"]["Can app estimate true probability now?"],
            "Partial / Low confidence",
        )
        self.assertEqual(
            by_bet["Moneyline / 1X2"]["Recommendation status"],
            "Partial only",
        )
        self.assertEqual(
            by_bet["Corners"]["Recommendation status"],
            "No Bet unless manually confirmed",
        )
        self.assertEqual(
            by_bet["SGP / Parlay"]["Recommendation status"],
            "No Bet unless manually confirmed",
        )

    def test_partial_football_data_sample_allows_last5_only(self):
        audit = self._audit(
            context_data={
                "team_form": [
                    {
                        "Team": "Canada",
                        "Status": "Partial football-data.org sample — Last 5 threshold met, Last 10 not met.",
                    },
                    {
                        "Team": "Qatar",
                        "Status": "Partial football-data.org sample — Last 5 threshold met, Last 10 not met.",
                    },
                ],
                "players": [],
                "context": [],
                "integration_diagnostics": {
                    "football-data.org match rows used": 12,
                    "football-data.org rows per team": '{"Canada": 6, "Qatar": 6}',
                    "football-data.org minimum rows per team": 6,
                    "football-data.org team-form sample quality": "Last 5 threshold met only — limited support",
                    "football-data.org Last 5 threshold met": "Yes",
                    "football-data.org Last 10 threshold met": "No",
                },
                "player_summary": {"Squad players loaded": 0},
                "api_request_log": [],
                "compatibility_summary": [],
            }
        )
        matrix = {row["Dashboard cell"]: row for row in audit["compatibility_matrix"]}
        self.assertEqual(matrix["Last 5"]["Fillability status"], "Partial Last 5 only")
        self.assertEqual(
            matrix["Last 5"]["Betting confidence impact"],
            "Limited support — do not fully upgrade confidence",
        )

    def test_bet_type_matrix_keeps_player_props_restricted(self):
        audit = self._audit(context_data={"team_form": [], "players": [], "context": [], "integration_diagnostics": {}, "player_summary": {"Squad players loaded": 1}, "api_request_log": [], "compatibility_summary": []})
        by_bet = {row["Bet type"]: row for row in audit["bet_type_support_matrix"]}
        self.assertEqual(by_bet["Player Shots"]["Recommendation status"], "Manual research required")
        self.assertEqual(by_bet["SGP / Parlay"]["Recommendation status"], "No Bet unless manually confirmed")

    def test_export_includes_audit_and_redacts_secrets(self):
        audit = self._audit()
        markdown = api_capability_audit_to_markdown(audit)
        parsed = json.loads(api_capability_audit_to_json(audit))
        self.assertIn("API Capability Audit Package", markdown)
        self.assertIn("Master Data Compatibility Matrix", markdown)
        self.assertIn("bet_type_support_matrix", parsed)
        self.assertNotIn("safe-test-key", markdown)
        self.assertNotIn("THE_ODDS_API_KEY", markdown)


if __name__ == "__main__":
    unittest.main()
