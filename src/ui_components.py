"""Reusable Streamlit UI components for Stage 1."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def format_currency(value: float) -> str:
    return f"${value:,.2f}"


def format_percent(value: float) -> str:
    return f"{value:.2%}"


def render_warning_box() -> None:
    st.warning(
        "Manual confirmation required in the Hard Rock app before betting. "
        "These are potential value bet research cards, not guaranteed winners. "
        "Betting is high variance. Only risk money you can afford to lose."
    )


def render_bet_card(bet: dict, index: int | None = None) -> None:
    title_prefix = f"BET CARD #{index}" if index is not None else "BET CARD"

    with st.container(border=True):
        st.subheader(title_prefix)
        st.markdown(f"**Game:** {bet['event']}")
        st.markdown(f"**Sport:** {bet['sport']}")
        st.markdown(f"**Market:** {bet['market']}")
        st.markdown(f"**Selection:** {bet['selection']}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Hard Rock FL Odds", f"{bet['hardrock_odds']:+d}")
        col2.metric("Potential Payout", format_currency(bet["potential_payout"]))
        col3.metric("EV per $1", format_currency(bet["ev_per_1_dollar"]))

        col4, col5, col6 = st.columns(3)
        col4.metric("Implied Probability", format_percent(bet["implied_probability"]))
        col5.metric("Model Probability", format_percent(bet["model_probability"]))
        col6.metric("Edge", format_percent(bet["edge"]))

        st.markdown(f"**Confidence:** {bet['confidence']}")
        st.markdown(f"**Risk:** {bet['risk_level']}")
        st.markdown(f"**Category:** {bet['category']}")
        st.markdown(f"**Recommendation:** {bet['recommendation']}")

        with st.expander("Reasoning"):
            for reason in bet["reasoning"]:
                st.write(f"- {reason}")

        st.info("Manual Confirmation: Check the Hard Rock app before betting. Do not bet if the line moved.")


def bets_to_dataframe(bets: list[dict]) -> pd.DataFrame:
    if not bets:
        return pd.DataFrame()

    df = pd.DataFrame(bets)
    display_columns = [
        "sport",
        "event",
        "market",
        "selection",
        "hardrock_odds",
        "stake",
        "implied_probability",
        "model_probability",
        "edge",
        "ev_per_1_dollar",
        "potential_payout",
        "kelly_fraction",
        "fractional_kelly",
        "recommended_stake",
        "confidence",
        "risk_level",
        "category",
    ]
    existing = [col for col in display_columns if col in df.columns]
    return df[existing]
