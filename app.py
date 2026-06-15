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
from src.odds_api import (
    HARD_ROCK_GENERIC_BOOKMAKER,
    MissingApiKeyError,
    OddsApiError,
    get_bookmaker_diagnostics,
    get_sports,
    read_api_key,
    select_hardrock_bookmaker,
)
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
    if "hardrock_feed_mode" not in st.session_state:
        st.session_state.hardrock_feed_mode = "Florida only"
    if "navigation_page" not in st.session_state:
        st.session_state.navigation_page = "Home"
    if "odds_board_data" not in st.session_state:
        st.session_state.odds_board_data = None
    manual_defaults = {
        "manual_sport": SUPPORTED_STAGE_1_SPORTS[0],
        "manual_event": "",
        "manual_market": SUPPORTED_STAGE_1_MARKETS[0],
        "manual_selection": "",
        "manual_american_odds": -110,
    }
    for key, value in manual_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_bets() -> None:
    st.session_state.bets = []


def prefill_manual_bet(
    *,
    sport: str,
    event: str,
    market: str,
    selection: str,
    american_odds: int | float,
) -> None:
    st.session_state.manual_sport = (
        sport if sport in SUPPORTED_STAGE_1_SPORTS else "Other"
    )
    st.session_state.manual_event = event
    st.session_state.manual_market = (
        market if market in SUPPORTED_STAGE_1_MARKETS else "Other"
    )
    st.session_state.manual_selection = selection
    st.session_state.manual_american_odds = int(american_odds)
    st.session_state.navigation_page = "Manual Entry"


def get_configured_api_key() -> str:
    try:
        return read_api_key(st.secrets)
    except FileNotFoundError as exc:
        raise MissingApiKeyError(
            "The Odds API key is missing. Add THE_ODDS_API_KEY to "
            ".streamlit/secrets.toml and restart Streamlit."
        ) from exc


@st.cache_data(ttl=3600, show_spinner=False)
def load_sports(api_key: str) -> list[dict]:
    return get_sports(api_key)


@st.cache_data(ttl=300, show_spinner=False)
def load_bookmaker_diagnostics(
    api_key: str,
    sport_key: str,
    market: str,
) -> dict:
    return get_bookmaker_diagnostics(api_key, sport_key, market=market)


def render_home_page() -> None:
    st.title(APP_NAME)
    st.caption("Stage 2: Live Hard Rock Bet Florida odds plus all Stage 1 research tools")
    render_warning_box()

    st.markdown(
        """
        ### What this app does

        Stage 2 can load current Hard Rock Bet Florida odds from The Odds API. You can
        also manually enter a line from any book, add your estimated probability, and
        use the original Stage 1 calculations:

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


def render_live_odds_page() -> None:
    st.title("Stage 2 Odds Diagnostics")
    render_warning_box()
    st.caption(
        "Diagnostic mode requests all bookmakers in The Odds API us and us2 regions. "
        "No Hard Rock bookmaker filter is sent."
    )

    try:
        api_key = get_configured_api_key()
    except MissingApiKeyError as exc:
        st.error(str(exc))
        st.info("Stage 1 pages remain available from the sidebar.")
        return

    try:
        with st.spinner("Loading in-season sports..."):
            sports = load_sports(api_key)
    except OddsApiError as exc:
        st.error(str(exc))
        return

    if not sports:
        st.info("The Odds API returned no in-season sports.")
        return

    sport_by_label = {
        f"{sport.get('group', 'Other')} | {sport['title']}": sport["key"]
        for sport in sports
    }
    selected_label = st.selectbox("Sport", options=list(sport_by_label))
    market_label = st.selectbox(
        "Market",
        options=["Moneyline", "Spread", "Total"],
        help="Loading one market at a time conserves API credits.",
    )
    market_keys = {
        "Moneyline": "h2h",
        "Spread": "spreads",
        "Total": "totals",
    }
    st.success(f"Sports list loaded: {len(sports)} available.")

    if st.button("Run bookmaker diagnostic", type="primary"):
        try:
            with st.spinner("Loading unfiltered bookmaker diagnostics..."):
                diagnostic = load_bookmaker_diagnostics(
                    api_key,
                    sport_by_label[selected_label],
                    market_keys[market_label],
                )
        except (OddsApiError, ValueError) as exc:
            st.error(str(exc))
            return

        diagnostic["sport_title"] = next(
            sport["title"]
            for sport in sports
            if sport["key"] == sport_by_label[selected_label]
        )
        diagnostic["market_label"] = market_label
        st.session_state.odds_board_data = diagnostic

    diagnostic = st.session_state.odds_board_data
    if diagnostic:
        allow_generic = st.session_state.hardrock_feed_mode == "Allow generic Hard Rock"
        matched_key = select_hardrock_bookmaker(
            diagnostic["bookmaker_keys"],
            allow_generic=allow_generic,
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Events returned", diagnostic["event_count"])
        col2.metric("Unique bookmakers", diagnostic["bookmaker_count"])
        col3.metric(
            "hardrockbet_fl present",
            "Yes" if diagnostic["hardrockbet_fl_present"] else "No",
        )
        col4.metric("Matched Hard Rock key", matched_key or "None")

        st.subheader("Unique bookmaker keys")
        if diagnostic["bookmaker_keys"]:
            st.dataframe(
                pd.DataFrame(
                    {"bookmaker_key": diagnostic["bookmaker_keys"]}
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("The API returned no bookmaker keys for this sport and market.")

        if matched_key == "hardrockbet_fl":
            st.success(
                "Matched Hard Rock key: hardrockbet_fl. Florida-specific feed selected."
            )
        elif matched_key == HARD_ROCK_GENERIC_BOOKMAKER:
            st.warning(
                "Using generic Hard Rock feed. This may differ from Florida-specific pricing."
            )
        elif diagnostic["hardrockbet_present"] and not allow_generic:
            st.warning(
                "hardrockbet is present, but Settings is configured for Florida only. "
                "Enable Allow generic Hard Rock to use the fallback feed."
            )
        else:
            st.warning(
                "Neither hardrockbet_fl nor hardrockbet is present in the unfiltered "
                "The Odds API response. This is upstream data availability, not a "
                "Hard Rock filtering bug in this app."
            )

        st.divider()
        st.subheader("Full Events Board")
        if not diagnostic["events"]:
            st.info("No events were returned for this sport and market.")
            return

        event_table = pd.DataFrame(
            [
                {
                    "commence_time": event["commence_time"],
                    "home_team": event["home_team"],
                    "away_team": event["away_team"],
                    "event": event["event"],
                    "bookmaker_keys": ", ".join(event["bookmaker_keys"]),
                    "hardrockbet_fl_present": event["hardrockbet_fl_present"],
                    "hardrockbet_present": event["hardrockbet_present"],
                }
                for event in diagnostic["events"]
            ]
        )
        st.dataframe(event_table, use_container_width=True, hide_index=True)

        st.subheader("Selected Event Odds")
        event_by_label = {
            f"{event['commence_time']} | {event['event']}": event
            for event in diagnostic["events"]
        }
        selected_event_label = st.selectbox(
            "Game",
            options=list(event_by_label),
        )
        selected_event = event_by_label[selected_event_label]

        st.markdown(f"**Event:** {selected_event['event']}")
        st.markdown(
            f"**Date/time:** {selected_event['commence_time'] or 'Not provided'}"
        )
        st.markdown(f"**Event ID:** `{selected_event['id']}`")

        show_only_hardrock = st.checkbox(
            "Show only Hard Rock odds",
            value=False,
            help="Uncheck to show all bookmaker odds.",
        )

        eligible_hardrock_keys = {"hardrockbet_fl"}
        if allow_generic:
            eligible_hardrock_keys.add(HARD_ROCK_GENERIC_BOOKMAKER)

        outcomes = list(selected_event["outcomes"])
        if show_only_hardrock:
            outcomes = [
                row
                for row in outcomes
                if row["bookmaker_key"] in eligible_hardrock_keys
            ]

        outcomes.sort(
            key=lambda row: (
                0
                if row["bookmaker_key"] == "hardrockbet_fl"
                else 1
                if (
                    allow_generic
                    and row["bookmaker_key"] == HARD_ROCK_GENERIC_BOOKMAKER
                )
                else 2,
                row["bookmaker_key"],
                row["selection"],
            )
        )

        hardrock_outcomes = [
            row
            for row in selected_event["outcomes"]
            if row["bookmaker_key"] in eligible_hardrock_keys
        ]
        if (
            allow_generic
            and any(
                row["bookmaker_key"] == HARD_ROCK_GENERIC_BOOKMAKER
                for row in hardrock_outcomes
            )
            and not selected_event["hardrockbet_fl_present"]
        ):
            st.warning(
                "Using generic Hard Rock feed. Confirm manually in the Hard Rock Florida app."
            )
        if not hardrock_outcomes:
            st.warning(
                "No Hard Rock odds available from the API for this event. "
                "Use this only as market reference."
            )

        if not outcomes:
            st.info("No odds match the current filter.")
            return

        st.dataframe(
            pd.DataFrame(outcomes)[
                [
                    "bookmaker",
                    "bookmaker_key",
                    "market_key",
                    "selection",
                    "price",
                    "point",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("**Create a Stage 1 manual bet card:**")
        for index, row in enumerate(outcomes):
            with st.container(border=True):
                details_col, action_col = st.columns([4, 1])
                with details_col:
                    point_text = (
                        f" | Line: {row['point']}"
                        if row["point"] is not None
                        else ""
                    )
                    st.write(
                        f"**{row['bookmaker']}** (`{row['bookmaker_key']}`) | "
                        f"{row['market_key']} | {row['selection']} | "
                        f"{row['price']:+g}{point_text}"
                    )
                with action_col:
                    st.button(
                        "Create manual bet card from this line",
                        key=(
                            f"prefill-{selected_event['id']}-"
                            f"{row['bookmaker_key']}-{row['market_key']}-{index}"
                        ),
                        on_click=prefill_manual_bet,
                        kwargs={
                            "sport": diagnostic["sport_title"],
                            "event": selected_event["event"],
                            "market": diagnostic["market_label"],
                            "selection": row["selection"],
                            "american_odds": row["price"],
                        },
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

    st.subheader("Hard Rock feed preference")
    st.session_state.hardrock_feed_mode = st.radio(
        "Hard Rock bookmaker matching",
        options=["Florida only", "Allow generic Hard Rock"],
        index=(
            1
            if st.session_state.hardrock_feed_mode == "Allow generic Hard Rock"
            else 0
        ),
        help=(
            "Florida only accepts hardrockbet_fl. Allow generic Hard Rock falls back "
            "to hardrockbet only when the Florida-specific key is unavailable."
        ),
    )


def render_manual_entry_page() -> None:
    st.title("Manual Entry + EV Calculator")
    render_warning_box()

    with st.form("manual_bet_form", clear_on_submit=False):
        col1, col2 = st.columns(2)

        with col1:
            sport = st.selectbox(
                "Sport",
                SUPPORTED_STAGE_1_SPORTS,
                key="manual_sport",
            )
            event = st.text_input(
                "Game / Event",
                placeholder="Example: Celtics vs Lakers",
                key="manual_event",
            )
            market = st.selectbox(
                "Market",
                SUPPORTED_STAGE_1_MARKETS,
                key="manual_market",
            )
            selection = st.text_input(
                "Selection",
                placeholder="Example: Celtics ML",
                key="manual_selection",
            )

        with col2:
            american_odds = st.number_input(
                "Hard Rock FL American Odds",
                step=5,
                key="manual_american_odds",
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
            {"Stage": "Stage 2", "Feature": "The Odds API sports list", "Status": "Built now"},
            {"Stage": "Stage 2", "Feature": "Hard Rock Bet Florida odds", "Status": "Built now"},
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
                "Live Odds",
                "Manual Entry",
                "Bet Cards",
                "Parlay Builder",
                "Settings",
                "Stage Status",
            ],
            key="navigation_page",
        )

        st.divider()
        st.metric("Current bet cards", len(st.session_state.bets))
        st.metric("Default stake", format_currency(st.session_state.default_stake))
        st.metric("Bankroll", format_currency(st.session_state.bankroll))
        st.caption("Stage 2 uses The Odds API only on the Live Odds page.")

    if page == "Home":
        render_home_page()
    elif page == "Live Odds":
        render_live_odds_page()
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
