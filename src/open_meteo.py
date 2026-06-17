"""Open-Meteo weather helpers for Research Lab context."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from src.research_lab import OpenMeteoQuotaTracker

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
MISSING_COORDINATES = "Unavailable — venue coordinates missing"


class OpenMeteoError(RuntimeError):
    """Raised when Open-Meteo cannot return a usable response."""


def fetch_open_meteo_weather(
    *,
    latitude: float,
    longitude: float,
    tracker: OpenMeteoQuotaTracker | None = None,
    timeout: float = 15.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,relative_humidity_2m,precipitation,"
            "wind_speed_10m"
        ),
        "hourly": "precipitation_probability",
        "forecast_days": 7,
        "timezone": "UTC",
    }
    url = f"{OPEN_METEO_BASE_URL}?{urlencode(params)}"
    tracker = tracker or OpenMeteoQuotaTracker()
    try:
        with urlopen(url, timeout=timeout) as response:
            tracker.record_call()
            payload = json.loads(response.read().decode("utf-8"))
            return payload, tracker.status_row()
    except HTTPError as exc:
        raise OpenMeteoError(f"Open-Meteo returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise OpenMeteoError("Could not connect to Open-Meteo.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OpenMeteoError("Open-Meteo returned an unreadable response.") from exc


def parse_open_meteo_weather(payload: Mapping[str, Any]) -> dict[str, Any]:
    current = payload.get("current") or {}
    units = payload.get("current_units") or {}
    temperature = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    precipitation = current.get("precipitation")
    wind = current.get("wind_speed_10m")
    hourly = payload.get("hourly") or {}
    probabilities = hourly.get("precipitation_probability") or []
    precipitation_probability = probabilities[0] if probabilities else None
    severity = weather_severity(
        wind_speed=wind,
        precipitation=precipitation,
        precipitation_probability=precipitation_probability,
    )
    return {
        "Factor": "Weather",
        "Value": (
            f"Temp {temperature}{units.get('temperature_2m', 'C')}, "
            f"humidity {humidity}{units.get('relative_humidity_2m', '%')}, "
            f"precip {precipitation}{units.get('precipitation', 'mm')}, "
            f"precip probability {precipitation_probability}%, "
            f"wind {wind}{units.get('wind_speed_10m', 'km/h')}, "
            f"severity {severity}"
        ),
        "Betting note": "Weather is context only; confirm venue and match conditions manually.",
    }


def unavailable_weather_context(reason: str = MISSING_COORDINATES) -> dict[str, Any]:
    return {
        "Factor": "Weather",
        "Value": reason,
        "Betting note": "Weather unavailable; keep model conservative and confirm manually.",
    }


def build_weather_snapshot(
    *,
    latitude: float | None,
    longitude: float | None,
    tracker: OpenMeteoQuotaTracker | None = None,
) -> dict[str, Any]:
    tracker = tracker or OpenMeteoQuotaTracker()
    diagnostics = {
        "Weather request attempted": "No",
        "Weather coordinates available": "Yes" if latitude is not None and longitude is not None else "No",
    }
    if latitude is None or longitude is None:
        return {
            "context": [unavailable_weather_context()],
            "usage": [tracker.status_row()],
            "missing": ["Venue latitude/longitude"],
            "diagnostics": diagnostics,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    try:
        diagnostics["Weather request attempted"] = "Yes"
        payload, usage = fetch_open_meteo_weather(
            latitude=latitude,
            longitude=longitude,
            tracker=tracker,
        )
    except OpenMeteoError as exc:
        return {
            "context": [unavailable_weather_context(str(exc))],
            "usage": [tracker.status_row()],
            "missing": [str(exc)],
            "diagnostics": diagnostics,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "context": [parse_open_meteo_weather(payload)],
        "usage": [usage],
        "missing": [],
        "diagnostics": diagnostics,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def weather_severity(
    *,
    wind_speed: int | float | None,
    precipitation: int | float | None,
    precipitation_probability: int | float | None,
) -> str:
    wind = float(wind_speed or 0)
    precip = float(precipitation or 0)
    probability = float(precipitation_probability or 0)
    if wind >= 35 or precip >= 5 or probability >= 70:
        return "High"
    if wind >= 20 or precip > 0 or probability >= 40:
        return "Medium"
    return "Low"
