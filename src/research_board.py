"""Unified Research Board source classification and value-card helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import io
import json
import math
from typing import Any

from src.advanced_markets import MarketTemplate
from src.ev import calculate_expected_value, calculate_kelly_fraction
from src.market_comparison import (
    calculate_market_comparison,
    decimal_to_american,
    selection_label,
)
from src.odds_api import (
    HARD_ROCK_FL_BOOKMAKER,
    HARD_ROCK_GENERIC_BOOKMAKER,
)
from src.probabilities import (
    american_to_decimal,
    american_to_implied_probability,
    clamp_probability,
)


SOURCE_RULES = {
    HARD_ROCK_FL_BOOKMAKER: ("Exact Hard Rock FL API", "High confidence"),
    HARD_ROCK_GENERIC_BOOKMAKER: (
        "Generic Hard Rock API",
        "Medium confidence, may differ from Florida",
    ),
}

SCANNER_FL_CONFIDENCE = "High confidence"
SCANNER_GENERIC_CONFIDENCE = "Medium confidence, may differ from Florida"
SCANNER_CONSENSUS_CONFIDENCE = "Comparison only"
SAFETY_WARNINGS = [
    "These are potential value bets only.",
    "Sports betting is high variance.",
    "Past performance does not guarantee future results.",
    "Only risk money you can afford to lose.",
    "This dashboard does not place bets.",
    "This dashboard does not log into Hard Rock.",
    "All wagers must be confirmed manually by the user.",
]


@dataclass(frozen=True)
class ResearchBetCard:
    sport: str
    event: str
    market: str
    selection: str
    point: int | float | None
    american_odds: int
    source_type: str
    confidence: str
    implied_probability: float
    no_vig_probability: float | None
    edge: float
    ev_per_1_dollar: float
    fractional_kelly: float
    kelly_stake: float
    stake: float
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_source(
    bookmaker_key: str | None,
    *,
    manual: bool = False,
) -> tuple[str, str]:
    if manual:
        return (
            "Manual Hard Rock FL Entry",
            "User-confirmed, highest confidence if copied from app",
        )
    if bookmaker_key in SOURCE_RULES:
        return SOURCE_RULES[bookmaker_key]
    return ("Market Consensus / Other Books", "Comparison only")


def enrich_odds_rows(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for outcome in outcomes:
        price = outcome.get("price")
        if not isinstance(price, (int, float)):
            continue
        source_type, confidence = classify_source(outcome.get("bookmaker_key"))
        rows.append(
            {
                "bookmaker": outcome.get("bookmaker", ""),
                "bookmaker_key": outcome.get("bookmaker_key", ""),
                "source_type": source_type,
                "confidence": confidence,
                "market": outcome.get("market_key", ""),
                "selection": outcome.get("selection", ""),
                "point": outcome.get("point"),
                "american_odds": int(price),
                "implied_probability": american_to_implied_probability(price),
            }
        )
    return rows


def _line_key(row: dict[str, Any]) -> tuple[str, Any]:
    return (str(row.get("selection") or ""), row.get("point"))


def _consensus_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    prices = [
        int(row["price"])
        for row in rows
        if isinstance(row.get("price"), (int, float))
    ]
    if not prices:
        return None

    decimals = [american_to_decimal(price) for price in prices]
    average_decimal = sum(decimals) / len(decimals)
    best_price = prices[decimals.index(max(decimals))]
    worst_price = prices[decimals.index(min(decimals))]
    implied = [
        american_to_implied_probability(price)
        for price in prices
    ]
    return {
        "Consensus Odds": decimal_to_american(average_decimal),
        "Average odds": decimal_to_american(average_decimal),
        "Best odds": best_price,
        "Worst odds": worst_price,
        "Number of books": len(prices),
        "Consensus implied probability": sum(implied) / len(implied),
    }


def build_hardrock_coverage_scan(
    templates: list[MarketTemplate],
    outcomes_by_market: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    found_rows = []
    missing_rows = []

    for template in templates:
        template_found = False
        grouped: dict[tuple[str, Any], dict[str, Any]] = {}
        for api_market_key in template.api_market_keys:
            for outcome in outcomes_by_market.get(api_market_key, []):
                bookmaker_key = outcome.get("bookmaker_key")
                if bookmaker_key == HARD_ROCK_FL_BOOKMAKER:
                    grouped.setdefault(_line_key(outcome), {})["fl"] = outcome
                elif bookmaker_key == HARD_ROCK_GENERIC_BOOKMAKER:
                    grouped.setdefault(_line_key(outcome), {})["generic"] = outcome
                elif bookmaker_key:
                    grouped.setdefault(_line_key(outcome), {}).setdefault(
                        "consensus",
                        [],
                    ).append(outcome)
                else:
                    continue

        for (selection, point), source_rows in sorted(
            grouped.items(),
            key=lambda item: (
                str(item[0][0]),
                "" if item[0][1] is None else str(item[0][1]),
            ),
        ):
            fl_row = source_rows.get("fl")
            generic_row = source_rows.get("generic")
            consensus = _consensus_summary(source_rows.get("consensus", []))
            source_row = fl_row or generic_row
            if source_row is None and consensus is None:
                continue

            template_found = True
            if fl_row:
                source_used = "Exact Hard Rock FL API"
                confidence = SCANNER_FL_CONFIDENCE
                source_label = "Hard Rock FL"
            elif generic_row:
                source_used = "Generic Hard Rock API"
                confidence = SCANNER_GENERIC_CONFIDENCE
                source_label = "Generic Hard Rock"
            else:
                source_used = "Market Consensus / Other Books"
                confidence = SCANNER_CONSENSUS_CONFIDENCE
                source_label = "Consensus only"

            fl_odds = int(fl_row["price"]) if fl_row else None
            generic_odds = int(generic_row["price"]) if generic_row else None
            odds = int(source_row["price"]) if source_row else consensus["Consensus Odds"]
            consensus_odds = consensus["Consensus Odds"] if consensus else None
            consensus_probability = (
                consensus["Consensus implied probability"] if consensus else None
            )
            found_rows.append(
                {
                    "Market Category": template.group,
                    "Specific Market": template.name,
                    "Selection": selection,
                    "Point / Line": point,
                    "Odds": odds,
                    "Hard Rock FL Odds": fl_odds,
                    "Generic Hard Rock Odds": generic_odds,
                    "Consensus Odds": consensus_odds,
                    "Hard Rock FL Available": "Yes" if fl_row else "No",
                    "Generic Hard Rock Available": "Yes" if generic_row else "No",
                    "Consensus Available": "Yes" if consensus else "No",
                    "Confidence Label": confidence,
                    "Source Label": source_label,
                    "Source used": source_used,
                    "Difference": (
                        fl_odds - generic_odds
                        if fl_odds is not None and generic_odds is not None
                        else None
                    ),
                    "Average odds": (
                        consensus["Average odds"] if consensus else None
                    ),
                    "Best odds": consensus["Best odds"] if consensus else None,
                    "Worst odds": consensus["Worst odds"] if consensus else None,
                    "Number of books": (
                        consensus["Number of books"] if consensus else 0
                    ),
                    "Consensus implied probability": consensus_probability,
                    "bookmaker_key": (
                        HARD_ROCK_FL_BOOKMAKER
                        if fl_row
                        else HARD_ROCK_GENERIC_BOOKMAKER
                        if generic_row
                        else None
                    ),
                    "api_market_key": (
                        source_row.get("market_key")
                        if source_row
                        else None
                    ),
                    "source_type": source_used,
                    "source_name": source_label,
                    "confidence": confidence,
                    "last_updated": "",
                    "is_manual": False,
                    "is_hardrock_fl": bool(fl_row),
                    "is_generic_hardrock": bool(generic_row),
                    "is_consensus": bool(consensus),
                    "needs_manual_confirmation": True,
                }
            )

        if not template_found:
            missing_rows.append(
                {
                    "Market Category": template.group,
                    "Specific Market": template.name,
                    "Manual entry": "Use Manual Hard Rock FL Entry",
                }
            )

    return found_rows, missing_rows


def markets_missing_from_hardrock_fl(
    found_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "Market Category": row["Market Category"],
            "Specific Market": row["Specific Market"],
            "Selection": row["Selection"],
            "Point / Line": row["Point / Line"],
            "Generic Hard Rock Available": row["Generic Hard Rock Available"],
            "Consensus Available": row["Consensus Available"],
            "Warning": "Verify manually inside Hard Rock Florida before using this market.",
        }
        for row in found_rows
        if row["Hard Rock FL Available"] == "No"
        and (
            row["Generic Hard Rock Available"] == "Yes"
            or row["Consensus Available"] == "Yes"
        )
    ]


def build_ai_research_package(
    *,
    game_info: dict[str, Any],
    found_lines: list[dict[str, Any]],
    missing_markets: list[dict[str, Any]],
    manual_entries: list[dict[str, Any]],
    bankroll: float,
    kelly_multiplier: float,
    api_usage: list[dict[str, Any]] | None = None,
    team_research: list[dict[str, Any]] | None = None,
    player_research: list[dict[str, Any]] | None = None,
    contextual_factors: list[dict[str, Any]] | None = None,
    betting_signals: list[dict[str, Any]] | None = None,
    integration_diagnostics: dict[str, Any] | None = None,
    compatibility_summary: list[dict[str, Any]] | None = None,
    api_capability_audit: dict[str, Any] | None = None,
    team_mappings: dict[str, Any] | None = None,
    missing_data: list[Any] | None = None,
) -> dict[str, Any]:
    hardrock_fl = [
        row for row in found_lines if row["Hard Rock FL Available"] == "Yes"
    ]
    generic = [
        row for row in found_lines if row["Generic Hard Rock Available"] == "Yes"
    ]
    consensus = [
        row for row in found_lines if row["Consensus Available"] == "Yes"
    ]
    missing_fl = markets_missing_from_hardrock_fl(found_lines)

    quantitative = []
    for row in found_lines:
        odds = row["Odds"]
        implied = american_to_implied_probability(odds)
        no_vig = row.get("Consensus implied probability")
        probability = clamp_probability(no_vig if no_vig is not None else implied)
        full_kelly = calculate_kelly_fraction(odds, probability)
        fractional_kelly = max(0.0, full_kelly * kelly_multiplier)
        edge = probability - implied
        ev = calculate_expected_value(odds, probability, 1.0)
        label = _analysis_label(ev, fractional_kelly)
        quantitative.append(
            {
                "Market Category": row["Market Category"],
                "Specific Market": row["Specific Market"],
                "Selection": row["Selection"],
                "Point / Line": row["Point / Line"],
                "Source": row["Source Label"],
                "American Odds": odds,
                "Decimal Odds": american_to_decimal(odds),
                "Implied Probability": implied,
                "Consensus Probability": row.get("Consensus implied probability"),
                "No Vig Probability": no_vig,
                "Edge": edge,
                "Expected Value": ev,
                "Kelly Criterion": full_kelly,
                "Fractional Kelly (25%)": fractional_kelly,
                "Suggested Stake": max(0.0, bankroll * fractional_kelly),
                "Market Discrepancy": _market_discrepancy(row),
                "Best Price Relative To Consensus": _best_price_delta(row),
                "Label": label,
                "Potential Value Bet Only": True,
            }
        )

    for entry in manual_entries:
        odds = int(entry["Odds"])
        implied = american_to_implied_probability(odds)
        quantitative.append(
            {
                "Market Category": "Manual",
                "Specific Market": entry["Market"],
                "Selection": entry["Selection"],
                "Point / Line": entry.get("Point"),
                "Source": "Manual Hard Rock FL Entry",
                "American Odds": odds,
                "Decimal Odds": american_to_decimal(odds),
                "Implied Probability": implied,
                "Consensus Probability": None,
                "No Vig Probability": None,
                "Edge": 0.0,
                "Expected Value": 0.0,
                "Kelly Criterion": 0.0,
                "Fractional Kelly (25%)": 0.0,
                "Suggested Stake": 0.0,
                "Market Discrepancy": None,
                "Best Price Relative To Consensus": None,
                "Label": "Manual verification required",
                "Potential Value Bet Only": True,
            }
        )

    rankings = _rank_value_bets(quantitative)
    no_bets = _build_no_bet_list(quantitative, found_lines)
    source_coverage = [
        {"Source": "Hard Rock FL", "Available": "Yes" if hardrock_fl else "No"},
        {"Source": "Generic Hard Rock", "Available": "Yes" if generic else "No"},
        {"Source": "Market Consensus", "Available": "Yes" if consensus else "No"},
        {"Source": "Manual Entry", "Available": "Yes" if manual_entries else "No"},
    ]

    return {
        "safety": SAFETY_WARNINGS,
        "settings": {
            "bankroll": bankroll,
            "kelly_multiplier": kelly_multiplier,
        },
        "game_information": game_info,
        "source_coverage": source_coverage,
        "api_usage": api_usage or [],
        "team_research": team_research or [],
        "player_research": player_research or [],
        "contextual_factors": contextual_factors or [],
        "betting_signals": betting_signals or [],
        "integration_diagnostics": integration_diagnostics or {},
        "compatibility_summary": compatibility_summary or [],
        "api_capability_audit": api_capability_audit or {},
        "team_mappings": team_mappings or {},
        "missing_data": missing_data or [],
        "hard_rock_fl_markets": hardrock_fl,
        "generic_hard_rock_markets": generic,
        "market_consensus": consensus,
        "manual_hard_rock_entry": manual_entries,
        "quantitative_analysis": quantitative,
        "top_value_bets": rankings,
        "no_bet_list": no_bets,
        "source_summary": {
            "Number of Hard Rock FL lines": len(hardrock_fl),
            "Number of Generic Hard Rock lines": len(generic),
            "Number of Consensus lines": len(consensus),
            "Number of Manual entries": len(manual_entries),
        },
        "data_gaps": {
            "Markets unavailable in Hard Rock FL": missing_fl,
            "Markets unavailable in Generic Hard Rock": [
                row
                for row in found_lines
                if row["Generic Hard Rock Available"] == "No"
            ],
            "Markets requiring manual verification": missing_fl + missing_markets,
            "Missing players": [] if player_research else [{"Status": "Unavailable - API key missing"}],
            "Missing lineups": [{"Status": "Player prop requires confirmed lineup."}],
            "Missing injuries": [] if player_research else [{"Status": "Unavailable - API key missing"}],
            "Missing weather": [] if contextual_factors else [{"Status": "Unavailable - venue coordinates/API missing"}],
            "Missing referee": [{"Status": "Unavailable - API key missing"}],
            "Unsupported markets": missing_markets,
            "API quota limits": api_usage or [],
            "Live integration diagnostics": [
                {"Diagnostic": key, "Value": value}
                for key, value in (integration_diagnostics or {}).items()
            ],
            "API compatibility summary": compatibility_summary or [],
            "Missing live research data": [
                {"Status": value}
                for value in (missing_data or [])
            ],
        },
        "chatgpt_analysis_template": [
            "Potential value bets.",
            "Market inefficiencies.",
            "No-bet situations.",
            "Tactical mismatches.",
            "Injury and rotation impact.",
            "Scheduling and travel effects.",
            "Public bias and market overreactions.",
            "Parlay opportunities.",
            "Risk-adjusted ranking of bets.",
            "Alternative markets offering better value.",
        ],
    }


def _analysis_label(ev: float, fractional_kelly: float) -> str:
    if ev > 0.02 and fractional_kelly > 0:
        return "Positive EV - Potential Value Bet Only"
    if abs(ev) <= 0.02:
        return "Neutral - Potential Value Bet Only"
    return "Negative EV - Potential Value Bet Only"


def _market_discrepancy(row: dict[str, Any]) -> float | None:
    fl = row.get("Hard Rock FL Odds")
    generic = row.get("Generic Hard Rock Odds")
    consensus = row.get("Consensus Odds")
    available = [
        value
        for value in [fl, generic, consensus]
        if isinstance(value, (int, float))
    ]
    if len(available) < 2:
        return None
    return float(max(available) - min(available))


def _best_price_delta(row: dict[str, Any]) -> float | None:
    consensus = row.get("Consensus Odds")
    odds = row.get("Odds")
    if not isinstance(consensus, (int, float)) or not isinstance(odds, (int, float)):
        return None
    return float(odds - consensus)


def _rank_value_bets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            row.get("Expected Value") or 0,
            row.get("Fractional Kelly (25%)") or 0,
            row.get("Market Discrepancy") or 0,
            row.get("Best Price Relative To Consensus") or 0,
        ),
        reverse=True,
    )
    top_rows = []
    for row in ranked[:5]:
        implied = row.get("Implied Probability")
        consensus = row.get("Consensus Probability") or row.get("No Vig Probability")
        if consensus is not None:
            reasoning = (
                f"Consensus implies {_format_percent(consensus)} while market price "
                f"implies {_format_percent(implied)}."
            )
        else:
            reasoning = (
                "No consensus probability was available, so this requires manual "
                "context review before any action."
            )
        top_rows.append(
            {
                "Market": row["Specific Market"],
                "Selection": row["Selection"],
                "Source": row["Source"],
                "Odds": row["American Odds"],
                "EV": row["Expected Value"],
                "Kelly": row["Fractional Kelly (25%)"],
                "Stake": row["Suggested Stake"],
                "Label": row["Label"],
                "Reasoning": reasoning,
            }
        )
    return top_rows


def _build_no_bet_list(
    quantitative_rows: list[dict[str, Any]],
    found_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    no_bets = []
    line_lookup = {
        (
            row["Specific Market"],
            row["Selection"],
            row["Point / Line"],
        ): row
        for row in found_lines
    }
    for row in quantitative_rows:
        reasons = []
        if row.get("Expected Value", 0) < 0:
            reasons.append("Negative EV")
        if row.get("Fractional Kelly (25%)", 0) <= 0:
            reasons.append("Zero Kelly")
        if row.get("Consensus Probability") is None and row["Source"] != "Manual Hard Rock FL Entry":
            reasons.append("High uncertainty")
        scanner_row = line_lookup.get(
            (
                row["Specific Market"],
                row["Selection"],
                row["Point / Line"],
            )
        )
        if scanner_row and (_market_discrepancy(scanner_row) or 0) >= 25:
            reasons.append("Large disagreement between books")
        if scanner_row and scanner_row.get("Hard Rock FL Available") == "No":
            reasons.append("Manual verification missing")
        if row["Source"] == "Manual Hard Rock FL Entry":
            reasons.append("Manual entry must be re-confirmed before betting")
        if reasons:
            no_bets.append(
                {
                    "Market": row["Specific Market"],
                    "Selection": row["Selection"],
                    "Source": row["Source"],
                    "Odds": row["American Odds"],
                    "Why": "; ".join(dict.fromkeys(reasons)),
                }
            )
    return no_bets


def ai_package_to_json(package: dict[str, Any]) -> str:
    return json.dumps(package, indent=2, sort_keys=True)


def ai_package_to_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# Hard Rock FL Odds Intelligence Report",
        "",
        "These are potential value bets only. This dashboard does not place bets, "
        "log into Hard Rock, scrape Hard Rock, or automate sportsbook actions.",
        "",
        "## Safety Warnings",
    ]
    lines.extend(f"- {warning}" for warning in package["safety"])
    lines.extend(["", "## Section 1 - Game Information"])
    lines.append(_markdown_table(_game_info_rows(package["game_information"])))

    lines.extend(["", "## Section 2 - Source Coverage Summary"])
    lines.append(_markdown_table(package["source_coverage"]))
    lines.append("")
    for key, value in package["source_summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "### API Usage / Quota Status"])
    lines.append(_markdown_table(package["api_usage"]) if package["api_usage"] else "No API usage headers captured.")

    lines.extend(["", "## Section 3 - Hard Rock FL Markets"])
    lines.append(
        _markdown_table(
            _hardrock_fl_report_rows(
                package["hard_rock_fl_markets"],
                package["settings"],
            )
        )
        if package["hard_rock_fl_markets"]
        else "No Hard Rock Florida API markets returned."
    )

    lines.extend(["", "## Section 4 - Generic Hard Rock Markets"])
    lines.append("Medium confidence. May differ from Florida.")
    lines.append(
        _markdown_table(
            _generic_report_rows(
                package["generic_hard_rock_markets"],
                package["settings"],
            )
        )
        if package["generic_hard_rock_markets"]
        else "No Generic Hard Rock API markets returned."
    )

    lines.extend(["", "## Section 5 - Market Consensus"])
    if package["market_consensus"]:
        for category, rows in _group_by_category(package["market_consensus"]).items():
            lines.extend(["", f"### {category}"])
            lines.append(_markdown_table(_consensus_report_rows(rows)))
    else:
        lines.append("No market consensus lines returned.")

    lines.extend(["", "## Section 6 - Manual Hard Rock Entry"])
    if package["manual_hard_rock_entry"]:
        lines.append("HIGHEST CONFIDENCE - USER VERIFIED")
        lines.append(_markdown_table(package["manual_hard_rock_entry"]))
    else:
        lines.append("No manual Hard Rock FL entries recorded.")

    lines.extend(["", "## Section 7 - Quantitative Analysis"])
    lines.append(_markdown_table(_quant_report_rows(package["quantitative_analysis"])))

    lines.extend(["", "## Team Research"])
    if package.get("team_mappings"):
        lines.append("### API-Football Team ID Mappings")
        lines.append(
            _markdown_table(
                [
                    {
                        "Team": team,
                        "API-Football team ID": values.get("id"),
                        "Matched name": values.get("matched_name"),
                    }
                    for team, values in package["team_mappings"].items()
                ]
            )
        )
    lines.append(_markdown_table(package["team_research"]) if package["team_research"] else "Unavailable - API key missing.")

    lines.extend(["", "## Player Research"])
    lines.append(_markdown_table(package["player_research"]) if package["player_research"] else "Unavailable - API key missing.")

    lines.extend(["", "## Contextual Factors"])
    lines.append(_markdown_table(package["contextual_factors"]) if package["contextual_factors"] else "Unavailable - API key missing.")

    lines.extend(["", "## Live Integration Diagnostics"])
    diagnostics = package.get("integration_diagnostics") or {}
    lines.append(
        _markdown_table(
            [{"Diagnostic": key, "Value": value} for key, value in diagnostics.items()]
        )
        if diagnostics
        else "No live integration diagnostics captured."
    )
    missing_data = package.get("missing_data") or []
    lines.extend(["", "### Missing Data List"])
    lines.append(
        _markdown_table([{"Status": item} for item in missing_data])
        if missing_data
        else "None."
    )

    lines.extend(["", "## API Compatibility Summary"])
    compatibility = package.get("compatibility_summary") or []
    lines.append(
        _markdown_table(compatibility)
        if compatibility
        else "No API compatibility summary captured."
    )

    audit = package.get("api_capability_audit") or {}
    if audit:
        lines.extend(["", "## API Capability Audit"])
        lines.append("### APIs Configured")
        lines.append(_markdown_table(audit.get("apis_configured", [])))
        lines.append("### Master Data Compatibility Matrix")
        lines.append(_markdown_table(audit.get("compatibility_matrix", [])))
        lines.append("### Bet-Type Support Matrix")
        lines.append(_markdown_table(audit.get("bet_type_support_matrix", [])))
        lines.append("### API Limitations / Missing Data")
        lines.append(
            _markdown_table(
                [{"Missing data": item} for item in audit.get("missing_data", [])]
            )
            if audit.get("missing_data")
            else "None."
        )
        lines.append("### Manual Fallback List")
        for item in audit.get("manual_research_checklist", []):
            lines.append(f"- {item}")

    lines.extend(["", "## Betting Signals"])
    lines.append(_markdown_table(package["betting_signals"]) if package["betting_signals"] else "No betting signals generated.")

    lines.extend(["", "## Section 8 - Bet Rankings"])
    lines.append("### TOP 5 POTENTIAL VALUE BETS")
    lines.append(
        _markdown_table(package["top_value_bets"])
        if package["top_value_bets"]
        else "No ranked lines available."
    )

    lines.extend(["", "## Section 9 - No Bet List"])
    lines.append(
        _markdown_table(package["no_bet_list"])
        if package["no_bet_list"]
        else "No no-bet flags generated."
    )

    lines.extend(["", "## Section 10 - Data Gaps"])
    for key, rows in package["data_gaps"].items():
        lines.extend(["", f"### {key}"])
        lines.append(_markdown_table(rows) if rows else "None.")

    lines.extend(["", "## Section 12 - ChatGPT Analysis Mode Prompt"])
    lines.append("Use this package to analyze:")
    for index, item in enumerate(package["chatgpt_analysis_template"], start=1):
        lines.append(f"{index}. {item}")
    return "\n".join(lines)


def ai_package_to_txt(package: dict[str, Any]) -> str:
    return ai_package_to_markdown(package)


def ai_package_to_csv(package: dict[str, Any]) -> str:
    rows = []
    for section_name in [
        "hard_rock_fl_markets",
        "generic_hard_rock_markets",
        "market_consensus",
        "manual_hard_rock_entry",
        "quantitative_analysis",
    ]:
        for row in package[section_name]:
            flat_row = {"section": section_name}
            flat_row.update(row)
            rows.append(flat_row)
    if not rows:
        return "section\n"

    fieldnames = sorted({key for row in rows for key in row})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def chatgpt_analysis_package_to_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# ChatGPT Analysis Package",
        "",
        "Analyze these as potential value bets only. Do not treat any output as a guaranteed winner.",
        "",
        "## Game Information",
        _markdown_table(_game_info_rows(package["game_information"])),
        "",
        "## Hard Rock FL Lines",
        (
            _markdown_table(_simple_line_rows(package["hard_rock_fl_markets"]))
            if package["hard_rock_fl_markets"]
            else "No Hard Rock Florida API markets returned."
        ),
        "",
        "## Generic Hard Rock Lines",
        (
            _markdown_table(_simple_line_rows(package["generic_hard_rock_markets"]))
            if package["generic_hard_rock_markets"]
            else "No Generic Hard Rock API markets returned."
        ),
        "",
        "## Consensus Lines",
        (
            _markdown_table(_consensus_report_rows(package["market_consensus"]))
            if package["market_consensus"]
            else "No consensus lines returned."
        ),
        "",
        "## Manual Entries",
        (
            _markdown_table(package["manual_hard_rock_entry"])
            if package["manual_hard_rock_entry"]
            else "No manual entries recorded."
        ),
        "",
        "## Top Value Bets",
        (
            _markdown_table(package["top_value_bets"])
            if package["top_value_bets"]
            else "No ranked lines available."
        ),
        "",
        "## No Bet List",
        (
            _markdown_table(package["no_bet_list"])
            if package["no_bet_list"]
            else "No no-bet flags generated."
        ),
        "",
        "## Data Gaps",
    ]
    for key, rows in package["data_gaps"].items():
        lines.extend([f"### {key}", _markdown_table(rows) if rows else "None."])
    audit = package.get("api_capability_audit") or {}
    if audit:
        lines.extend(["", "## API Capability Audit Summary"])
        if audit.get("apis_configured"):
            lines.extend(["### APIs Configured", _markdown_table(audit["apis_configured"])])
        if audit.get("compatibility_matrix"):
            lines.extend(
                [
                    "### Master Data Compatibility Matrix",
                    _markdown_table(audit["compatibility_matrix"]),
                ]
            )
        if audit.get("bet_type_support_matrix"):
            lines.extend(
                [
                    "### Bet-Type Support Matrix",
                    _markdown_table(audit["bet_type_support_matrix"]),
                ]
            )
        if audit.get("missing_data"):
            lines.extend(["### API Limitations"])
            lines.extend(f"- {item}" for item in audit["missing_data"])
        if audit.get("manual_research_checklist"):
            lines.extend(["### Manual Fallback List"])
            lines.extend(f"- {item}" for item in audit["manual_research_checklist"])
    return "\n".join(lines)


def _game_info_rows(game_info: dict[str, Any]) -> list[dict[str, Any]]:
    keys = [
        "Sport",
        "League",
        "Competition stage",
        "Date",
        "Time",
        "Home team",
        "Away team",
        "Venue",
        "Timezone",
    ]
    return [{"Field": key, "Value": game_info.get(key) or "Unavailable"} for key in keys]


def _hardrock_fl_report_rows(
    rows: list[dict[str, Any]],
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    report_rows = []
    for row in rows:
        metrics = _report_metrics(row, row["Hard Rock FL Odds"], settings)
        report_rows.append(
            {
            "Market Category": row["Market Category"],
            "Specific Market": row["Specific Market"],
            "Selection": row["Selection"],
            "Point / Line": _format_value(row["Point / Line"]),
            "Odds": _format_odds(row["Hard Rock FL Odds"]),
            "Implied Probability": _format_percent(metrics["implied"]),
            "No Vig Probability": _format_percent(row.get("Consensus implied probability")),
            "EV": f"{metrics['ev']:.3f}",
            "Kelly %": _format_percent(metrics["fractional_kelly"]),
            "Stake Recommendation": f"${metrics['stake']:.2f}",
            "Source Confidence": "High confidence",
        }
        )
    return report_rows


def _generic_report_rows(
    rows: list[dict[str, Any]],
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    report_rows = []
    for row in rows:
        metrics = _report_metrics(row, row["Generic Hard Rock Odds"], settings)
        report_rows.append(
            {
            "Market Category": row["Market Category"],
            "Specific Market": row["Specific Market"],
            "Selection": row["Selection"],
            "Point": _format_value(row["Point / Line"]),
            "Odds": _format_odds(row["Generic Hard Rock Odds"]),
            "Consensus Odds": _format_odds(row.get("Consensus Odds")),
            "Difference": _format_value(row.get("Difference")),
            "Consensus Probability": _format_percent(row.get("Consensus implied probability")),
            "EV": f"{metrics['ev']:.3f}",
            "Kelly": _format_percent(metrics["fractional_kelly"]),
            "Stake": f"${metrics['stake']:.2f}",
        }
        )
    return report_rows


def _report_metrics(
    row: dict[str, Any],
    odds: int | float | None,
    settings: dict[str, Any],
) -> dict[str, float]:
    if odds is None:
        return {"implied": 0.0, "ev": 0.0, "fractional_kelly": 0.0, "stake": 0.0}
    implied = american_to_implied_probability(odds)
    probability = clamp_probability(row.get("Consensus implied probability") or implied)
    full_kelly = calculate_kelly_fraction(int(odds), probability)
    fractional_kelly = max(0.0, full_kelly * float(settings["kelly_multiplier"]))
    return {
        "implied": implied,
        "ev": calculate_expected_value(int(odds), probability, 1.0),
        "fractional_kelly": fractional_kelly,
        "stake": float(settings["bankroll"]) * fractional_kelly,
    }


def _consensus_report_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Market Category": row["Market Category"],
            "Specific Market": row["Specific Market"],
            "Selection": row["Selection"],
            "Average Odds": _format_odds(row.get("Average odds")),
            "Best Odds": _format_odds(row.get("Best odds")),
            "Worst Odds": _format_odds(row.get("Worst odds")),
            "Number of Books": row.get("Number of books", 0),
            "Implied Probability": _format_percent(
                american_to_implied_probability(row["Consensus Odds"])
                if row.get("Consensus Odds") is not None
                else None
            ),
            "No Vig Probability": _format_percent(row.get("Consensus implied probability")),
        }
        for row in rows
    ]


def _quant_report_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Market": row["Specific Market"],
            "Selection": row["Selection"],
            "American Odds": _format_odds(row["American Odds"]),
            "Decimal Odds": f"{row['Decimal Odds']:.2f}",
            "Implied Probability": _format_percent(row["Implied Probability"]),
            "Consensus Probability": _format_percent(row.get("Consensus Probability")),
            "No Vig Probability": _format_percent(row.get("No Vig Probability")),
            "Edge": _format_percent(row["Edge"]),
            "Expected Value": f"{row['Expected Value']:.3f}",
            "Kelly Criterion": _format_percent(row["Kelly Criterion"]),
            "Fractional Kelly (25%)": _format_percent(row["Fractional Kelly (25%)"]),
            "Suggested Stake": f"${row['Suggested Stake']:.2f}",
            "Label": row["Label"],
        }
        for row in rows
    ]


def _simple_line_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Market Category": row["Market Category"],
            "Specific Market": row["Specific Market"],
            "Selection": row["Selection"],
            "Point / Line": _format_value(row["Point / Line"]),
            "Odds": _format_odds(row["Odds"]),
            "Source": row["Source Label"],
            "Confidence": row["Confidence Label"],
        }
        for row in rows
    ]


def _group_by_category(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["Market Category"], []).append(row)
    ordered = {}
    for category in ["Match", "Goals", "Spread", "Corners", "Cards", "Player Prop", "Special"]:
        if category in grouped:
            ordered[category] = grouped.pop(category)
    ordered.update(dict(sorted(grouped.items())))
    return ordered


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "None."
    headers = list(dict.fromkeys(key for row in rows for key in row.keys()))
    table = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        table.append(
            "| "
            + " | ".join(_escape_markdown(_format_value(row.get(header))) for header in headers)
            + " |"
        )
    return "\n".join(table)


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _format_percent(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}%"


def _format_odds(value: Any) -> str:
    if value is None:
        return ""
    return f"{int(value):+d}"




def source_summary(rows: list[dict[str, Any]]) -> dict[str, bool]:
    keys = {row.get("bookmaker_key") for row in rows}
    hardrock_fl = HARD_ROCK_FL_BOOKMAKER in keys
    generic = HARD_ROCK_GENERIC_BOOKMAKER in keys
    other = any(key and key not in SOURCE_RULES for key in keys)
    return {
        "hardrock_fl_available": hardrock_fl,
        "generic_hardrock_available": generic,
        "other_books_available": other,
        "manual_entry_required": not (hardrock_fl or generic),
    }


def market_availability_row(
    market_name: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = source_summary(rows)
    return {
        "market": market_name,
        "hardrockbet_fl available": summary["hardrock_fl_available"],
        "hardrockbet available": summary["generic_hardrock_available"],
        "other books available": summary["other_books_available"],
        "manual entry available": True,
    }


def market_consensus(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return calculate_market_comparison(outcomes)


def find_no_vig_probability(
    comparison: list[dict[str, Any]],
    selection: str,
    point: int | float | None,
) -> tuple[float | None, int]:
    label = selection_label(selection, point)
    row = next(
        (item for item in comparison if item["selection"] == label),
        None,
    )
    if not row:
        return None, 0
    return row["market_no_vig_probability"], row["bookmaker_count"]


def build_research_card(
    *,
    sport: str,
    event: str,
    market: str,
    selection: str,
    point: int | float | None,
    american_odds: int,
    estimated_probability: float,
    no_vig_probability: float | None,
    stake: float,
    bankroll: float,
    kelly_multiplier: float,
    bookmaker_key: str | None = None,
    manual: bool = False,
    notes: str = "",
) -> ResearchBetCard:
    if not selection.strip():
        raise ValueError("Selection is required.")
    probability = clamp_probability(
        no_vig_probability
        if no_vig_probability is not None
        else estimated_probability
    )
    if probability <= 0 or probability >= 1:
        raise ValueError("Probability must be between 0 and 1.")
    implied = american_to_implied_probability(american_odds)
    full_kelly = calculate_kelly_fraction(american_odds, probability)
    fractional_kelly = max(0.0, full_kelly * kelly_multiplier)
    source_type, confidence = classify_source(bookmaker_key, manual=manual)
    return ResearchBetCard(
        sport=sport,
        event=event,
        market=market,
        selection=selection,
        point=point,
        american_odds=american_odds,
        source_type=source_type,
        confidence=confidence,
        implied_probability=implied,
        no_vig_probability=no_vig_probability,
        edge=probability - implied,
        ev_per_1_dollar=calculate_expected_value(
            american_odds,
            probability,
            1.0,
        ),
        fractional_kelly=fractional_kelly,
        kelly_stake=max(0.0, bankroll * fractional_kelly),
        stake=stake,
        notes=notes,
    )
