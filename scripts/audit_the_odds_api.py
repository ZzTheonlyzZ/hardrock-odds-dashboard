# scripts/audit_the_odds_api.py

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
BASE_URL = "https://api.the-odds-api.com/v4"



def get_api_key() -> str:
    import streamlit as st
    from src.odds_api import read_api_key

    return read_api_key(st.secrets)


def print_headers(response: requests.Response) -> None:
    print("\n=== QUOTA HEADERS ===")
    for key in ["x-requests-remaining", "x-requests-used", "x-requests-last"]:
        print(f"{key}: {response.headers.get(key)}")


def print_json_shape(data: Any, prefix: str = "") -> None:
    if isinstance(data, list):
        print(f"{prefix}list[{len(data)}]")
        if data:
            print_json_shape(data[0], prefix + "  [0].")
        return

    if isinstance(data, dict):
        print(f"{prefix}dict keys: {list(data.keys())}")
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                print_json_shape(value, prefix + f"{key}.")
            else:
                print(f"{prefix}{key}: {type(value).__name__}")
        return

    print(f"{prefix}{type(data).__name__}")


def safe_get(path: str, params: Mapping[str, Any]) -> Any:
    api_key = get_api_key()
    url = f"{BASE_URL}{path}"

    request_params = dict(params)
    request_params["apiKey"] = api_key

    print("\n=== REQUEST ===")
    print(f"GET {path}")
    print("Params used, key hidden:")
    for key, value in params.items():
        print(f"- {key}: {value}")

    response = requests.get(url, params=request_params, timeout=20)

    print(f"\nHTTP status: {response.status_code}")
    print_headers(response)

    try:
        data = response.json()
    except Exception:
        print(response.text[:1000])
        raise

    if response.status_code >= 400:
        print("\n=== ERROR BODY ===")
        print(json.dumps(data, indent=2))
        return data

    print("\n=== JSON SHAPE ===")
    print_json_shape(data)

    print("\n=== SAMPLE RESPONSE, FIRST ITEM ONLY ===")
    if isinstance(data, list) and data:
        print(json.dumps(data[0], indent=2)[:5000])
    else:
        print(json.dumps(data, indent=2)[:5000])

    return data


def audit_sports() -> None: #This function audits the available sports from the API and prints their details.
    data = safe_get("/sports", params={})

    if not isinstance(data, list):
        return

    print("\n=== AVAILABLE SPORTS ===")
    for row in data:
        print(
            f"{row.get('key')} | "
            f"{row.get('group')} | "
            f"{row.get('title')} | "
            f"active={row.get('active')} | "
            f"outrights={row.get('has_outrights')}"
        )

def audit_odds() -> None:
    safe_get(
        "/sports/soccer_fifa_world_cup/odds",
        params={
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "american",
        },
    )


def audit_events() -> None:
    safe_get(
        "/sports/soccer_fifa_world_cup/events",
        params={},
    )


if __name__ == "__main__":
    print("THE ODDS API AUDIT")
    print("1 = /sports")
    print("2 = /odds")
    print("3 = /events")

    choice = input("Choose audit: ").strip()

    if choice == "1":
        audit_sports()
    elif choice == "2":
        audit_odds()
    elif choice == "3":
        audit_events()
    else:
        print("Invalid choice.")
