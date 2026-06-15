"""The Odds API client and Hard Rock Bet Florida normalization helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

API_BASE_URL = "https://api.the-odds-api.com/v4"
HARD_ROCK_FL_BOOKMAKER = "hardrockbet_fl"
HARD_ROCK_GENERIC_BOOKMAKER = "hardrockbet"
HARD_ROCK_BOOKMAKERS = (
    HARD_ROCK_FL_BOOKMAKER,
    HARD_ROCK_GENERIC_BOOKMAKER,
)
DEFAULT_MARKETS = ("h2h", "spreads", "totals")
DIAGNOSTIC_REGIONS = ("us", "us2")


class OddsApiError(RuntimeError):
    """Raised when The Odds API cannot return a usable response."""


class MissingApiKeyError(OddsApiError):
    """Raised when the API key has not been configured."""


@dataclass(frozen=True)
class HardRockOddsRow:
    sport: str
    event: str
    commence_time: str
    market: str
    selection: str
    price: int | float
    point: int | float | None
    last_update: str
    bookmaker: str
    bookmaker_key: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_api_key(secrets: Mapping[str, Any] | None) -> str:
    """Read and validate the Stage 2 key without exposing its value."""
    if secrets is None:
        raise MissingApiKeyError(
            "The Odds API key is missing. Add THE_ODDS_API_KEY to "
            ".streamlit/secrets.toml and restart Streamlit."
        )

    try:
        api_key = str(secrets.get("THE_ODDS_API_KEY", "")).strip()
    except (AttributeError, FileNotFoundError):
        api_key = ""

    if not api_key:
        raise MissingApiKeyError(
            "The Odds API key is missing. Add THE_ODDS_API_KEY to "
            ".streamlit/secrets.toml and restart Streamlit."
        )
    return api_key


def _request_json(
    path: str,
    params: Mapping[str, str],
    *,
    timeout: float = 15.0,
) -> Any:
    url = f"{API_BASE_URL}{path}?{urlencode(params)}"

    try:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        messages = {
            401: "The Odds API rejected the key. Check THE_ODDS_API_KEY.",
            403: "This API plan does not allow the requested data.",
            422: "The Odds API rejected the sport or market request.",
            429: "The Odds API rate or usage limit has been reached.",
        }
        raise OddsApiError(
            messages.get(exc.code, f"The Odds API returned HTTP {exc.code}.")
        ) from exc
    except URLError as exc:
        raise OddsApiError(
            "Could not connect to The Odds API. Check the network and try again."
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OddsApiError("The Odds API returned an unreadable response.") from exc


def get_sports(api_key: str, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    """Return sports sorted by group and title. This endpoint is quota-free."""
    if not api_key.strip():
        raise MissingApiKeyError("The Odds API key is missing.")

    params = {"apiKey": api_key}
    if include_inactive:
        params["all"] = "true"

    payload = _request_json("/sports/", params)
    if not isinstance(payload, list):
        raise OddsApiError("The Odds API returned an unexpected sports response.")

    sports = [
        sport
        for sport in payload
        if isinstance(sport, dict)
        and sport.get("key")
        and sport.get("title")
        and (include_inactive or sport.get("active", True))
    ]
    return sorted(sports, key=lambda sport: (sport.get("group", ""), sport["title"]))


def select_hardrock_bookmaker(
    bookmaker_keys: list[str] | set[str] | tuple[str, ...],
    *,
    allow_generic: bool,
) -> str | None:
    """Choose the Florida feed first, with an optional generic fallback."""
    available = set(bookmaker_keys)
    if HARD_ROCK_FL_BOOKMAKER in available:
        return HARD_ROCK_FL_BOOKMAKER
    if allow_generic and HARD_ROCK_GENERIC_BOOKMAKER in available:
        return HARD_ROCK_GENERIC_BOOKMAKER
    return None


def extract_market_outcomes(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten every bookmaker market outcome for one event."""
    rows = []
    for bookmaker in event.get("bookmakers", []):
        if not isinstance(bookmaker, dict) or not bookmaker.get("key"):
            continue
        bookmaker_key = str(bookmaker["key"])
        bookmaker_title = str(bookmaker.get("title") or bookmaker_key)
        for market in bookmaker.get("markets", []):
            if not isinstance(market, dict) or not market.get("key"):
                continue
            market_key = str(market["key"])
            for outcome in market.get("outcomes", []):
                if not isinstance(outcome, dict):
                    continue
                price = outcome.get("price")
                if not isinstance(price, (int, float)):
                    continue
                rows.append(
                    {
                        "bookmaker": bookmaker_title,
                        "bookmaker_key": bookmaker_key,
                        "market_key": market_key,
                        "selection": str(outcome.get("name") or ""),
                        "price": price,
                        "point": outcome.get("point"),
                        "is_hardrock": bookmaker_key in HARD_ROCK_BOOKMAKERS,
                        "is_florida": bookmaker_key == HARD_ROCK_FL_BOOKMAKER,
                    }
                )
    return rows


def extract_event_rows(
    payload: list[Any],
    sport_key: str,
) -> list[dict[str, Any]]:
    """Normalize API events for the Stage 2 events table and outcome board."""
    events = []
    for index, event in enumerate(payload):
        if not isinstance(event, dict):
            continue

        event_bookmakers = {
            str(bookmaker["key"]): str(
                bookmaker.get("title") or bookmaker["key"]
            )
            for bookmaker in event.get("bookmakers", [])
            if isinstance(bookmaker, dict) and bookmaker.get("key")
        }
        bookmaker_keys = sorted(event_bookmakers)
        away_team = str(event.get("away_team") or "Away")
        home_team = str(event.get("home_team") or "Home")
        events.append(
            {
                "id": str(event.get("id") or f"{sport_key}-{index}"),
                "event": f"{away_team} at {home_team}",
                "label": f"{away_team} at {home_team}",
                "away_team": away_team,
                "home_team": home_team,
                "commence_time": str(event.get("commence_time") or ""),
                "bookmaker_keys": bookmaker_keys,
                "hardrockbet_fl_present": (
                    HARD_ROCK_FL_BOOKMAKER in bookmaker_keys
                ),
                "hardrockbet_present": (
                    HARD_ROCK_GENERIC_BOOKMAKER in bookmaker_keys
                ),
                "bookmakers": [
                    {
                        "key": key,
                        "title": event_bookmakers[key],
                        "is_hardrock": key in HARD_ROCK_BOOKMAKERS,
                        "is_florida": key == HARD_ROCK_FL_BOOKMAKER,
                    }
                    for key in bookmaker_keys
                ],
                "outcomes": extract_market_outcomes(event),
            }
        )
    events.sort(key=lambda event: (event["commence_time"], event["event"]))
    return events


def get_hardrock_odds(
    api_key: str,
    sport_key: str,
    *,
    markets: tuple[str, ...] = DEFAULT_MARKETS,
    allow_generic: bool = False,
) -> list[dict[str, Any]]:
    """Return normalized Hard Rock odds, preferring the Florida feed."""
    if not api_key.strip():
        raise MissingApiKeyError("The Odds API key is missing.")
    if not sport_key.strip():
        raise ValueError("Select a sport before loading odds.")

    payload = _request_json(
        f"/sports/{sport_key}/odds/",
        {
            "apiKey": api_key,
            "bookmakers": ",".join(HARD_ROCK_BOOKMAKERS),
            "markets": ",".join(markets),
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
    )
    if not isinstance(payload, list):
        raise OddsApiError("The Odds API returned an unexpected odds response.")

    available_keys = {
        str(bookmaker["key"])
        for event in payload
        if isinstance(event, dict)
        for bookmaker in event.get("bookmakers", [])
        if isinstance(bookmaker, dict) and bookmaker.get("key")
    }
    matched_key = select_hardrock_bookmaker(
        available_keys,
        allow_generic=allow_generic,
    )
    if matched_key is None:
        return []

    rows: list[HardRockOddsRow] = []
    for event in payload:
        if not isinstance(event, dict):
            continue

        event_name = f"{event.get('away_team', 'Away')} at {event.get('home_team', 'Home')}"
        for bookmaker in event.get("bookmakers", []):
            if bookmaker.get("key") != matched_key:
                continue

            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if not isinstance(price, (int, float)):
                        continue
                    rows.append(
                        HardRockOddsRow(
                            sport=str(event.get("sport_title", sport_key)),
                            event=event_name,
                            commence_time=str(event.get("commence_time", "")),
                            market=str(market.get("key", "")),
                            selection=str(outcome.get("name", "")),
                            price=price,
                            point=outcome.get("point"),
                            last_update=str(
                                market.get("last_update")
                                or bookmaker.get("last_update", "")
                            ),
                            bookmaker=str(
                                bookmaker.get("title")
                                or (
                                    "Hard Rock Bet (FL)"
                                    if matched_key == HARD_ROCK_FL_BOOKMAKER
                                    else "Hard Rock Bet"
                                )
                            ),
                            bookmaker_key=matched_key,
                        )
                    )

    return [row.to_dict() for row in rows]


def get_hardrock_fl_odds(
    api_key: str,
    sport_key: str,
    *,
    markets: tuple[str, ...] = DEFAULT_MARKETS,
) -> list[dict[str, Any]]:
    """Backward-compatible Florida-only helper."""
    return get_hardrock_odds(
        api_key,
        sport_key,
        markets=markets,
        allow_generic=False,
    )


def get_bookmaker_diagnostics(
    api_key: str,
    sport_key: str,
    *,
    market: str = "h2h",
) -> dict[str, Any]:
    """Inspect every bookmaker returned for a sport without a bookmaker filter."""
    if not api_key.strip():
        raise MissingApiKeyError("The Odds API key is missing.")
    if not sport_key.strip():
        raise ValueError("Select a sport before loading diagnostics.")

    payload = _request_json(
        f"/sports/{sport_key}/odds/",
        {
            "apiKey": api_key,
            "regions": ",".join(DIAGNOSTIC_REGIONS),
            "markets": market,
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
    )
    if not isinstance(payload, list):
        raise OddsApiError("The Odds API returned an unexpected odds response.")

    bookmaker_keys = sorted(
        {
            str(bookmaker["key"])
            for event in payload
            if isinstance(event, dict)
            for bookmaker in event.get("bookmakers", [])
            if isinstance(bookmaker, dict) and bookmaker.get("key")
        }
    )
    events = extract_event_rows(payload, sport_key)

    hardrockbet_fl_present = HARD_ROCK_FL_BOOKMAKER in bookmaker_keys
    hardrockbet_present = HARD_ROCK_GENERIC_BOOKMAKER in bookmaker_keys
    return {
        "event_count": len(payload),
        "bookmaker_keys": bookmaker_keys,
        "bookmaker_count": len(bookmaker_keys),
        "events": events,
        "hardrockbet_fl_present": hardrockbet_fl_present,
        "hardrockbet_present": hardrockbet_present,
        "regions": list(DIAGNOSTIC_REGIONS),
        "market": market,
    }


def stage_status() -> str:
    return "Active on the Stage 2 branch."
