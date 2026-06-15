from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import (
    APP_NAME,
    DEFAULT_BANKROLL,
    DEFAULT_KELLY_MULTIPLIER,
    DEFAULT_STAKE,
    SUPPORTED_STAGE_1_MARKETS,
    SUPPORTED_STAGE_1_SPORTS,
)
from src.ev import build_bet_result
from src.models import manual_probability_model
from src.parlay import calculate_parlay, decimal_to_american
from src.ui_components import (
    bets_to_dataframe,
    format_currency,
    format_percent,
    render_bet_card,
    render_warning_box,
)

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🏈",
    layout="wide",
)


def initialize_session_state() -> None:
    if "bets" not in st.session_state:
        st.session_state.bets = []
    if "bankroll" not in st.session_state:
        st.session_state.bankroll = DEFAULT_BANKROLL
    if "default_stake" not in st.session_state:
        st.session_state.default_stake = DEFAULT_STAKE
    if "kelly_multiplier" not in st.session_state:
        st.session_state.kelly_multiplier = DEFAULT_KELLY_MULTIPLIER


def reset_bets() -> None:
    st.session_state.bets = []


def render_home_page() -> None:
    st.title(APP_NAME)
    st.caption("Stage 1: Manual odds entry + EV + Kelly + bet cards + simple parlay builder")
    render_warning_box()

    st.markdown(
        """
        ### What this Stage 1 app does

        This first version does **not** use APIs yet. You manually enter a line from Hard Rock FL or any book, add your estimated probability, and the app calculates:

        - American odds to implied probability
        - Decimal odds
        - Expected value per $1
        - Expected value for your chosen stake
        - Edge
        - Full Kelly and fractional Kelly
        - Potential payout
        - Risk category
        - Bet card
        - Simple parlay math

        ### What this app does not do

        - It does not place bets.
        - It does not log into Hard Rock.
        - It does not scrape Hard Rock.
        - It does not guarantee winners.

        All results are research labels for **potential value bets** only.
        """
    )


def render_settings_page() -> None:
    st.title("Settings")
    render_warning_box()

    st.session_state.bankroll = st.number_input(
        "Bankroll size",
        min_value=1.0,
        value=float(st.session_state.bankroll),
        step=1.0,
        help="Used only for Kelly stake sizing. This does not connect to any betting account.",
    )
    st.session_state.default_stake = st.number_input(
        "Default stake",
        min_value=0.1,
        value=float(st.session_state.default_stake),
        step=0.5,
        help="Stage 1 is optimized for small-stake testing. $1 is the default mode.",
    )
    st.session_state.kelly_multiplier = st.slider(
        "Fractional Kelly multiplier",
        min_value=0.0,
        max_value=1.0,
        value=float(st.session_state.kelly_multiplier),
        step=0.05,
        help="0.25 means quarter Kelly. Conservative sizing is safer for high-variance betting.",
    )

    st.info(
        "For small bankrolls and longshots, treat Kelly as a guide, not a command. "
        "You can keep using flat $1 stakes instead."
    )


def render_manual_entry_page() -> None:
    st.title("Manual Entry + EV Calculator")
    render_warning_box()

    with st.form("manual_bet_form", clear_on_submit=False):
        col1, col2 = st.columns(2)

        with col1:
            sport = st.selectbox("Sport", SUPPORTED_STAGE_1_SPORTS)
            event = st.text_input("Game / Event", placeholder="Example: Celtics vs Lakers")
            market = st.selectbox("Market", SUPPORTED_STAGE_1_MARKETS)
            selection = st.text_input("Selection", placeholder="Example: Celtics ML")

        with col2:
            american_odds = st.number_input(
                "Hard Rock FL American Odds",
                value=-110,
                step=5,
                help="Use American odds like -110, +125, +350.",
            )
            model_probability_percent = st.number_input(
                "Your estimated probability (%)",
                min_value=0.1,
                max_value=99.9,
                value=52.4,
                step=0.1,
                help="Stage 1 uses your manual probability estimate. Later stages will add models.",
            )
            stake = st.number_input(
                "Stake",
                min_value=0.1,
                value=float(st.session_state.default_stake),
                step=0.5,
            )
            data_quality = st.selectbox(
                "Data quality",
                ["normal", "poor"],
                help="Use poor if this is only a guess, screenshot is unclear, or the line may have moved.",
            )

        submitted = st.form_submit_button("Calculate bet card")

    if submitted:
        if not event.strip() or not selection.strip():
            st.error("Please enter both the event and selection.")
            return

        try:
            model_probability = manual_probability_model(model_probability_percent)
            bet = build_bet_result(
                sport=sport,
                event=event.strip(),
                market=market,
                selection=selection.strip(),
                american_odds=int(american_odds),
                model_probability=model_probability,
                stake=float(stake),
                bankroll=float(st.session_state.bankroll),
                kelly_multiplier=float(st.session_state.kelly_multiplier),
                data_quality=data_quality,
            )
            bet_dict = bet.to_dict()
            st.session_state.bets.append(bet_dict)
            st.success("Bet card created and added to your Stage 1 bet list.")
            render_bet_card(bet_dict)
        except ValueError as exc:
            st.error(str(exc))


def render_bet_cards_page() -> None:
    st.title("Bet Cards")
    render_warning_box()

    if not st.session_state.bets:
        st.info("No bet cards yet. Go to Manual Entry and create your first bet card.")
        return

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Clear all bet cards", type="secondary"):
            reset_bets()
            st.rerun()

    df = bets_to_dataframe(st.session_state.bets)
    st.subheader("Ranked Table")
    st.dataframe(
        df.sort_values(by=["ev_per_1_dollar", "edge"], ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download current bet cards as CSV",
        data=csv,
        file_name="stage1_bet_cards.csv",
        mime="text/csv",
    )

    st.subheader("Cards")
    ranked_bets = sorted(
        st.session_state.bets,
        key=lambda item: (item["ev_per_1_dollar"], item["edge"]),
        reverse=True,
    )
    for idx, bet in enumerate(ranked_bets, start=1):
        render_bet_card(bet, index=idx)


def render_parlay_page() -> None:
    st.title("Simple Parlay Builder")
    render_warning_box()

    if not st.session_state.bets:
        st.info("Create at least two bet cards first, then come back to build a parlay.")
        return

    options = []
    option_to_bet = {}
    for idx, bet in enumerate(st.session_state.bets):
        label = f"{idx + 1}. {bet['event']} | {bet['market']} | {bet['selection']} ({bet['hardrock_odds']:+d})"
        options.append(label)
        option_to_bet[label] = bet

    selected_labels = st.multiselect(
        "Select parlay legs",
        options=options,
        help="Stage 1 assumes independent legs. Be careful with same-game or correlated legs.",
    )

    col1, col2 = st.columns(2)
    with col1:
        stake = st.number_input(
            "Parlay stake",
            min_value=0.1,
            value=float(st.session_state.default_stake),
            step=0.5,
        )
    with col2:
        correlation_warning = st.checkbox(
            "These legs may be correlated",
            value=False,
            help="Check this for same-game legs or bets connected to the same scoring environment.",
        )

    if st.button("Calculate parlay"):
        if len(selected_labels) < 2:
            st.error("Select at least two legs for a parlay.")
            return

        selected_legs = [option_to_bet[label] for label in selected_labels]
        try:
            result = calculate_parlay(
                legs=selected_legs,
                stake=float(stake),
                correlation_warning=correlation_warning,
            )
        except ValueError as exc:
            st.error(str(exc))
            return

        approx_american = decimal_to_american(result.combined_decimal_odds)

        with st.container(border=True):
            st.subheader("PARLAY CARD")
            st.markdown(f"**Legs:** {result.leg_count}")
            for leg in result.legs_summary:
                st.write(f"- {leg}")

            col1, col2, col3 = st.columns(3)
            col1.metric("Combined Decimal Odds", f"{result.combined_decimal_odds:.2f}")
            col2.metric("Approx American Odds", f"{approx_american:+d}")
            col3.metric("Potential Payout", format_currency(result.potential_payout))

            col4, col5, col6 = st.columns(3)
            col4.metric("Estimated Probability", format_percent(result.estimated_probability))
            col5.metric("Parlay Implied Probability", format_percent(result.implied_probability))
            col6.metric("EV per $1", format_currency(result.ev_per_1_dollar))

            st.markdown(f"**Profit if win:** {format_currency(result.profit_if_win)}")
            st.markdown(f"**Risk:** {result.risk_level}")
            st.markdown(f"**Category:** {result.category}")
            st.warning(result.warning)
            st.info("Manual Confirmation: Check every leg in the Hard Rock app before betting. Do not bet if any line moved.")


def render_stage_status_page() -> None:
    st.title("Stage Status")
    render_warning_box()

    status = pd.DataFrame(
        [
            {"Stage": "Stage 1", "Feature": "Manual odds entry", "Status": "Built now"},
            {"Stage": "Stage 1", "Feature": "Implied probability", "Status": "Built now"},
            {"Stage": "Stage 1", "Feature": "EV calculator", "Status": "Built now"},
            {"Stage": "Stage 1", "Feature": "Kelly calculator", "Status": "Built now"},
            {"Stage": "Stage 1", "Feature": "Bet cards", "Status": "Built now"},
            {"Stage": "Stage 1", "Feature": "Simple parlay builder", "Status": "Built now"},
            {"Stage": "Stage 2", "Feature": "The Odds API", "Status": "Not active yet"},
            {"Stage": "Stage 3", "Feature": "Market average + no-vig", "Status": "Not active yet"},
            {"Stage": "Stage 4", "Feature": "Basic models", "Status": "Not active yet"},
        ]
    )
    st.dataframe(status, use_container_width=True, hide_index=True)


def main() -> None:
    initialize_session_state()

    with st.sidebar:
        st.header("Navigation")
        page = st.radio(
            "Go to",
            [
                "Home",
                "Manual Entry",
                "Bet Cards",
                "Parlay Builder",
                "Settings",
                "Stage Status",
            ],
        )

        st.divider()
        st.metric("Current bet cards", len(st.session_state.bets))
        st.metric("Default stake", format_currency(st.session_state.default_stake))
        st.metric("Bankroll", format_currency(st.session_state.bankroll))
        st.caption("No APIs connected in Stage 1.")

    if page == "Home":
        render_home_page()
    elif page == "Manual Entry":
        render_manual_entry_page()
    elif page == "Bet Cards":
        render_bet_cards_page()
    elif page == "Parlay Builder":
        render_parlay_page()
    elif page == "Settings":
        render_settings_page()
    elif page == "Stage Status":
        render_stage_status_page()


if __name__ == "__main__":
    main()
