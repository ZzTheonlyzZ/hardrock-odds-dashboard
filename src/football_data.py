"""Optional football-data.org backup client for Research Lab context."""

from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.research_lab import parse_football_data_headers

FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"


class FootballDataError(RuntimeError):
    """Raised when football-data.org cannot return a usable response."""


def read_football_data_key(secrets: Mapping[str, Any] | None) -> str | None:
    try:
        value = str(secrets.get("FOOTBALL_DATA_KEY", "")).strip() if secrets else ""
    except (AttributeError, FileNotFoundError, RuntimeError):
        value = ""
    return value or None


def fetch_football_data_json(
    path: str,
    params: Mapping[str, Any],
    api_key: str,
    *,
    timeout: float = 15.0,
) -> tuple[Any, dict[str, Any]]:
    url = f"{FOOTBALL_DATA_BASE_URL}{path}?{urlencode(params)}"
    request = Request(url, headers={"X-Auth-Token": api_key})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = dict(response.headers.items()) if hasattr(response, "headers") else {}
            status = getattr(response, "status", None)
            return payload, parse_football_data_headers(headers, status_code=status)
    except HTTPError as exc:
        raise FootballDataError(f"football-data.org returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise FootballDataError("Could not connect to football-data.org.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FootballDataError("football-data.org returned an unreadable response.") from exc


def backup_context_row(api_key: str | None) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    if not api_key:
        return (
            {
                "Factor": "football-data.org backup",
                "Value": "Unavailable - API key missing",
                "Betting note": "Optional backup not connected; use API-Football/manual context.",
            },
            parse_football_data_headers({}),
            ["FOOTBALL_DATA_KEY"],
        )
    return (
        {
            "Factor": "football-data.org backup",
            "Value": "Configured",
            "Betting note": "Optional backup key available if API-Football data is incomplete.",
        },
        parse_football_data_headers({}),
        [],
    )
