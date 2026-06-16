from __future__ import annotations

import pandas as pd
import streamlit as st

from src.advanced_markets import (
    SOCCER_MARKET_TEMPLATES,
    build_advanced_market_card,
    create_market_template,
    determine_api_availability,
    market_support_matrix,
)
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
from src.market_comparison import (
    build_stage3_bet_card,
    calculate_market_comparison,
)
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
from src.probabilities import american_to_implied_probability
from src.research_board import (
    build_research_card,
    enrich_odds_rows,
    find_no_vig_probability,
    market_availability_row,
    market_consensus,
    source_summary,
)
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

DEBUG_MODE = False

MAIN_NAVIGATION = [
    "Home",
    "Research Board",
    "Manual Entry",
    "Bet Cards",
    "Parlay Builder",
    "Settings",
    "Stage Status",
]

DEBUG_NAVIGATION = [
    "Live Odds",
    "Market Comparison",
    "Advanced Markets",
]


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
        st.session_state.navigation_page = "Research Board"
    if st.session_state.navigation_page not in MAIN_NAVIGATION + DEBUG_NAVIGATION:
        st.session_state.navigation_page = "Research Board"
    if not DEBUG_MODE and st.session_state.navigation_page in DEBUG_NAVIGATION:
        st.session_state.navigation_page = "Research Board"
    if "odds_board_data" not in st.session_state:
        st.session_state.odds_board_data = None
    if "stage3_market_data" not in st.session_state:
        st.session_state.stage3_market_data = None
    if "stage3_cards" not in st.session_state:
        st.session_state.stage3_cards = []
    if "advanced_events_data" not in st.session_state:
        st.session_state.advanced_events_data = None
    if "advanced_market_result" not in st.session_state:
        st.session_state.advanced_market_result = None
    if "advanced_cards" not in st.session_state:
        st.session_state.advanced_cards = []
    if "research_events_data" not in st.session_state:
        st.session_state.research_events_data = None
    if "research_market_data" not in st.session_state:
        st.session_state.research_market_data = None
    if "research_cards" not in st.session_state:
        st.session_state.research_cards = []
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
    st.caption("Research Board first, with Stage 1 through Stage 3 calculations preserved")
    render_warning_box()

    st.markdown(
        """
        ### What this app does

        Use the Research Board as the main workflow:
        Sport → Game → Market Category → Specific Market → Source Summary → Lines →
        Manual Entry → EV/Kelly → Bet Card.

        It combines Hard Rock source availability, market consensus, manual line entry,
        and the original Stage 1 calculations:

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


def render_research_card(card: dict, index: int) -> None:
    with st.container(border=True):
        st.subheader(f"RESEARCH CARD #{index}")
        st.markdown(f"**Game:** {card['event']}")
        st.markdown(f"**Market:** {card['market']}")
        st.markdown(f"**Selection:** {card['selection']}")
        if card["point"] is not None:
            st.markdown(f"**Line / point:** {card['point']:+g}")
        st.markdown(f"**Source type:** {card['source_type']}")
        st.markdown(f"**Confidence:** {card['confidence']}")

        col1, col2, col3 = st.columns(3)
        col1.metric("American Odds", f"{card['american_odds']:+d}")
        col2.metric("Implied Probability", format_percent(card["implied_probability"]))
        col3.metric(
            "No-Vig Probability",
            (
                format_percent(card["no_vig_probability"])
                if card["no_vig_probability"] is not None
                else "Unavailable"
            ),
        )

        col4, col5, col6 = st.columns(3)
        col4.metric("Edge", format_percent(card["edge"]))
        col5.metric("EV per $1", format_currency(card["ev_per_1_dollar"]))
        col6.metric("Kelly Stake", format_currency(card["kelly_stake"]))
        st.warning(
            "Manual confirmation required. Confirm the exact line and odds inside "
            "the Hard Rock Florida app before betting."
        )


def render_research_board_page() -> None:
    st.title("Research Board")
    render_warning_box()
    st.info(
        "Sport -> Game -> Market Category -> Specific Market -> Source Summary -> "
        "Lines -> Manual Entry -> EV/Kelly -> Bet Card. This app does not auto-bet, "
        "scrape Hard Rock, or log into any sportsbook."
    )

    try:
        api_key = get_configured_api_key()
        sports = load_sports(api_key)
    except (MissingApiKeyError, OddsApiError) as exc:
        st.error(str(exc))
        return

    sport_by_label = {
        f"{sport.get('group', 'Other')} | {sport['title']}": sport
        for sport in sports
    }
    sport_label = st.selectbox(
        "Research sport",
        options=list(sport_by_label),
    )
    selected_sport = sport_by_label[sport_label]

    if st.button("Load games", type="primary"):
        try:
            data = load_bookmaker_diagnostics(
                api_key,
                selected_sport["key"],
                "h2h",
            )
        except (OddsApiError, ValueError) as exc:
            st.error(str(exc))
            return
        data["sport_title"] = selected_sport["title"]
        data["sport_key"] = selected_sport["key"]
        st.session_state.research_events_data = data
        st.session_state.research_market_data = None

    events_data = st.session_state.research_events_data
    if not events_data:
        st.info("Select a sport and load games.")
        return
    if not events_data["events"]:
        st.info("No games were returned for this sport.")
        return

    event_by_label = {
        f"{event['commence_time']} | {event['event']}": event
        for event in events_data["events"]
    }
    event_label = st.selectbox("Research event / game", options=list(event_by_label))
    selected_event = event_by_label[event_label]

    groups = list(dict.fromkeys(template.group for template in SOCCER_MARKET_TEMPLATES))
    market_group = st.selectbox("Market category", options=groups)
    templates = [
        template
        for template in SOCCER_MARKET_TEMPLATES
        if template.group == market_group
    ]
    specific_market = st.selectbox(
        "Specific market",
        options=[template.name for template in templates],
    )
    template = create_market_template(specific_market)

    if st.button("Load odds / source availability"):
        outcomes = []
        errors = []
        for api_market_key in template.api_market_keys:
            try:
                market_data = load_bookmaker_diagnostics(
                    api_key,
                    events_data["sport_key"],
                    api_market_key,
                )
            except OddsApiError as exc:
                errors.append(str(exc))
                continue
            matching_event = next(
                (
                    event
                    for event in market_data["events"]
                    if event["id"] == selected_event["id"]
                ),
                None,
            )
            if matching_event:
                outcomes.extend(matching_event["outcomes"])

        rows = enrich_odds_rows(outcomes)
        st.session_state.research_market_data = {
            "event_id": selected_event["id"],
            "event": selected_event["event"],
            "sport": events_data["sport_title"],
            "market": specific_market,
            "rows": rows,
            "outcomes": outcomes,
            "errors": errors,
        }

    board = st.session_state.research_market_data
    if (
        not board
        or board["event_id"] != selected_event["id"]
        or board["market"] != specific_market
    ):
        st.info("Select a game and market, then load odds/source availability.")
        return

    rows = board["rows"]
    summary = source_summary(rows)

    st.subheader("Source Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Exact Hard Rock FL available",
        "Yes" if summary["hardrock_fl_available"] else "No",
    )
    col2.metric(
        "Generic Hard Rock available",
        "Yes" if summary["generic_hardrock_available"] else "No",
    )
    col3.metric(
        "Market consensus available",
        "Yes" if summary["other_books_available"] else "No",
    )
    col4.metric(
        "Manual entry required",
        "Yes" if summary["manual_entry_required"] else "No",
    )

    st.markdown(
        """
        **Coverage badges**
        - Exact Hard Rock FL API: High confidence
        - Generic Hard Rock API: Medium confidence, may differ from Florida
        - Market Consensus / Other Books: Comparison only
        - Manual Hard Rock FL Entry: User-confirmed, highest confidence if copied from app
        """
    )

    if not summary["hardrock_fl_available"] and not summary["generic_hardrock_available"]:
        st.warning(
            "No Hard Rock API line found for this market. Use Manual Hard Rock FL "
            "Entry and compare against market consensus."
        )

    st.subheader("Market Availability")
    st.dataframe(
        pd.DataFrame([market_availability_row(specific_market, rows)]),
        use_container_width=True,
        hide_index=True,
    )

    hardrock_fl_rows = [
        row for row in rows if row["bookmaker_key"] == "hardrockbet_fl"
    ]
    generic_rows = [
        row for row in rows if row["bookmaker_key"] == "hardrockbet"
    ]
    other_rows = [
        row
        for row in rows
        if row["bookmaker_key"] not in {"hardrockbet_fl", "hardrockbet"}
    ]
    comparison = market_consensus(board["outcomes"])

    fl_tab, generic_tab, comparison_tab, manual_tab = st.tabs(
        [
            "Exact Hard Rock FL",
            "Generic Hard Rock",
            "Market Consensus",
            "Manual Hard Rock FL Entry",
        ]
    )

    display_columns = [
        "bookmaker",
        "bookmaker_key",
        "source_type",
        "confidence",
        "market",
        "selection",
        "point",
        "american_odds",
        "implied_probability",
    ]
    with fl_tab:
        if hardrock_fl_rows:
            st.success("Exact Hard Rock FL API | High confidence")
            st.dataframe(
                pd.DataFrame(hardrock_fl_rows)[display_columns],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No exact Hard Rock Florida API lines returned.")

    with generic_tab:
        if generic_rows:
            st.warning(
                "Generic Hard Rock API | Medium confidence, may differ from Florida"
            )
            st.dataframe(
                pd.DataFrame(generic_rows)[display_columns],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No generic Hard Rock API lines returned.")

    with comparison_tab:
        if rows:
            st.caption("Market Consensus / Other Books | Comparison only")
            st.dataframe(
                pd.DataFrame(rows)[display_columns],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No API bookmaker lines returned for this market.")
        if comparison:
            st.markdown("**Market average and no-vig consensus:**")
            st.dataframe(
                pd.DataFrame(comparison),
                use_container_width=True,
                hide_index=True,
            )

    with manual_tab:
        st.success(
            "Manual Hard Rock FL Entry | User-confirmed, highest confidence if copied from app"
        )
        st.caption(
            "Manual entry is always available. Enter the exact line currently shown "
            "inside the Hard Rock Florida app."
        )

        with st.form("research_manual_form"):
            selection = st.text_input("Research selection")
            use_point = st.checkbox("Research market has a line / point")
            point = st.number_input("Research line / point", value=0.0, step=0.5)
            american_odds = st.number_input(
                "Research American odds",
                value=-110,
                step=5,
            )
            estimated_probability = st.number_input(
                "Estimated probability or market fair probability (%)",
                min_value=0.1,
                max_value=99.9,
                value=50.0,
                step=0.1,
            )
            stake = st.number_input(
                "Research stake",
                min_value=0.1,
                value=float(st.session_state.default_stake),
                step=0.5,
            )
            submitted = st.form_submit_button("Create Research Board bet card")

        if submitted:
            no_vig_probability, _bookmaker_count = find_no_vig_probability(
                comparison,
                selection,
                float(point) if use_point else None,
            )
            try:
                card = build_research_card(
                    sport=board["sport"],
                    event=board["event"],
                    market=specific_market,
                    selection=selection,
                    point=float(point) if use_point else None,
                    american_odds=int(american_odds),
                    estimated_probability=float(estimated_probability) / 100,
                    no_vig_probability=no_vig_probability,
                    stake=float(stake),
                    bankroll=float(st.session_state.bankroll),
                    kelly_multiplier=float(st.session_state.kelly_multiplier),
                    manual=True,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.research_cards.append(card.to_dict())
                st.success("Research Board bet card created.")

    if rows:
        st.subheader("Create Card From API Line")
        api_line_by_label = {
            (
                f"{row['source_type']} | {row['bookmaker']} | "
                f"{row['selection']} | {row['american_odds']:+d}"
                + (
                    f" | {row['point']:+g}"
                    if row["point"] is not None
                    else ""
                )
            ): row
            for row in rows
        }
        api_line_label = st.selectbox(
            "API line for research card",
            options=list(api_line_by_label),
        )
        api_line = api_line_by_label[api_line_label]
        no_vig_probability, _bookmaker_count = find_no_vig_probability(
            comparison,
            api_line["selection"],
            api_line["point"],
        )
        api_estimated_probability = st.number_input(
            "API line estimated probability (%)",
            min_value=0.1,
            max_value=99.9,
            value=float(
                (
                    no_vig_probability
                    if no_vig_probability is not None
                    else api_line["implied_probability"]
                )
                * 100
            ),
            step=0.1,
        )
        api_stake = st.number_input(
            "API line stake",
            min_value=0.1,
            value=float(st.session_state.default_stake),
            step=0.5,
        )
        if st.button("Create card from selected API line"):
            card = build_research_card(
                sport=board["sport"],
                event=board["event"],
                market=specific_market,
                selection=api_line["selection"],
                point=api_line["point"],
                american_odds=api_line["american_odds"],
                estimated_probability=float(api_estimated_probability) / 100,
                no_vig_probability=no_vig_probability,
                stake=float(api_stake),
                bankroll=float(st.session_state.bankroll),
                kelly_multiplier=float(st.session_state.kelly_multiplier),
                bookmaker_key=api_line["bookmaker_key"],
            )
            st.session_state.research_cards.append(card.to_dict())
            st.success("API-sourced Research Board card created.")

    if st.session_state.research_cards:
        st.subheader("Research Board Bet Cards")
        for index, card in enumerate(
            reversed(st.session_state.research_cards),
            start=1,
        ):
            render_research_card(card, index)


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

    st.subheader("Kelly sizing preset")
    kelly_preset = st.radio(
        "Kelly preset",
        options=["Full Kelly", "Half Kelly", "Quarter Kelly", "Custom"],
        index=2,
        horizontal=True,
    )
    preset_values = {
        "Full Kelly": 1.0,
        "Half Kelly": 0.5,
        "Quarter Kelly": 0.25,
    }
    if kelly_preset in preset_values:
        st.session_state.kelly_multiplier = preset_values[kelly_preset]
        st.caption(
            f"Active Kelly multiplier: {st.session_state.kelly_multiplier:.2f}"
        )
    else:
        st.caption(
            "Use the fractional Kelly slider above for a custom multiplier."
        )


def render_stage3_card(card: dict, index: int) -> None:
    with st.container(border=True):
        st.subheader(f"STAGE 3 BET CARD #{index}")
        st.markdown(f"**Event:** {card['event']}")
        st.markdown(f"**Sport / Market:** {card['sport']} | {card['market']}")
        st.markdown(f"**Selection:** {card['selection']}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Manual Hard Rock FL Odds", f"{card['hardrock_odds']:+d}")
        col2.metric(
            "Hard Rock Implied",
            format_percent(card["hardrock_implied_probability"]),
        )
        col3.metric(
            "Market No-Vig",
            format_percent(card["market_no_vig_probability"]),
        )

        col4, col5, col6 = st.columns(3)
        col4.metric("Edge", format_percent(card["edge"]))
        col5.metric("EV per $1", format_currency(card["ev_per_1_dollar"]))
        col6.metric("Potential Payout", format_currency(card["potential_payout"]))

        st.markdown(
            f"**Market average odds:** {card['market_average_american_odds']:+d} "
            f"across {card['bookmaker_count']} books"
        )
        st.markdown(
            f"**Fractional Kelly:** {format_percent(card['fractional_kelly'])}"
        )
        st.markdown(
            f"**Suggested stake from bankroll:** "
            f"{format_currency(card['recommended_stake'])}"
        )
        st.markdown(f"**Label:** {card['category']}")
        st.markdown(f"**Recommendation:** {card['recommendation']}")
        st.warning(
            "Manual confirmation required: verify the exact selection and price "
            "in the Hard Rock Florida app. Do not bet if the line moved."
        )


def render_market_comparison_page() -> None:
    st.title("Market Comparison")
    render_warning_box()
    st.info(
        "Stage 3 compares a manually entered Hard Rock Florida price with a "
        "multi-book no-vig market estimate. It does not place bets, log into "
        "Hard Rock, or scrape any sportsbook."
    )

    try:
        api_key = get_configured_api_key()
        sports = load_sports(api_key)
    except (MissingApiKeyError, OddsApiError) as exc:
        st.error(str(exc))
        return

    sport_by_label = {
        f"{sport.get('group', 'Other')} | {sport['title']}": sport
        for sport in sports
    }
    selected_sport_label = st.selectbox(
        "Stage 3 sport",
        options=list(sport_by_label),
    )
    market_label = st.selectbox(
        "Stage 3 market",
        options=["Moneyline", "Spread", "Total"],
    )
    market_keys = {
        "Moneyline": "h2h",
        "Spread": "spreads",
        "Total": "totals",
    }

    if st.button("Load market comparison", type="primary"):
        selected_sport = sport_by_label[selected_sport_label]
        try:
            data = load_bookmaker_diagnostics(
                api_key,
                selected_sport["key"],
                market_keys[market_label],
            )
        except (OddsApiError, ValueError) as exc:
            st.error(str(exc))
            return
        data["sport_title"] = selected_sport["title"]
        data["market_label"] = market_label
        st.session_state.stage3_market_data = data

    data = st.session_state.stage3_market_data
    if not data:
        st.info("Select a sport and market, then load comparison data.")
        return
    if not data["events"]:
        st.info("No events were returned for this sport and market.")
        return

    event_by_label = {
        f"{event['commence_time']} | {event['event']}": event
        for event in data["events"]
    }
    selected_event_label = st.selectbox(
        "Stage 3 event",
        options=list(event_by_label),
    )
    event = event_by_label[selected_event_label]

    st.subheader("All Bookmaker Odds")
    odds_rows = []
    for row in event["outcomes"]:
        odds_rows.append(
            {
                "bookmaker": row["bookmaker"],
                "bookmaker_key": row["bookmaker_key"],
                "market_key": row["market_key"],
                "selection": row["selection"],
                "point": row["point"],
                "american_odds": row["price"],
                "implied_probability": american_to_implied_probability(
                    row["price"]
                ),
            }
        )
    if not odds_rows:
        st.info("No bookmaker outcomes were returned for this event.")
        return
    st.dataframe(pd.DataFrame(odds_rows), use_container_width=True, hide_index=True)

    comparison = calculate_market_comparison(event["outcomes"])
    if not comparison:
        st.warning(
            "Not enough complete bookmaker markets are available for a no-vig comparison."
        )
        return

    st.subheader("Market Consensus")
    st.dataframe(
        pd.DataFrame(comparison),
        use_container_width=True,
        hide_index=True,
    )

    comparison_by_selection = {
        row["selection"]: row for row in comparison
    }
    with st.form("stage3_manual_override"):
        st.subheader("Manual Hard Rock FL Override")
        selection = st.selectbox(
            "Selection",
            options=list(comparison_by_selection),
        )
        hardrock_odds = st.number_input(
            "Exact American odds from Hard Rock Florida app",
            value=-110,
            step=5,
        )
        stake = st.number_input(
            "Stage 3 stake",
            min_value=0.1,
            value=float(st.session_state.default_stake),
            step=0.5,
        )
        data_quality = st.selectbox(
            "Manual line quality",
            options=["normal", "poor"],
        )
        submitted = st.form_submit_button("Generate Stage 3 bet card")

    if submitted:
        consensus = comparison_by_selection[selection]
        try:
            card = build_stage3_bet_card(
                sport=data["sport_title"],
                event=event["event"],
                market=data["market_label"],
                selection=selection,
                hardrock_odds=int(hardrock_odds),
                market_no_vig_probability=consensus[
                    "market_no_vig_probability"
                ],
                market_average_american_odds=consensus[
                    "market_average_american_odds"
                ],
                bookmaker_count=consensus["bookmaker_count"],
                stake=float(stake),
                bankroll=float(st.session_state.bankroll),
                kelly_multiplier=float(st.session_state.kelly_multiplier),
                data_quality=data_quality,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.stage3_cards.append(card.to_dict())
            st.success("Stage 3 bet card created.")

    if st.session_state.stage3_cards:
        st.subheader("Stage 3 Bet Cards")
        for index, card in enumerate(
            reversed(st.session_state.stage3_cards),
            start=1,
        ):
            render_stage3_card(card, index)


def render_advanced_card(card: dict, index: int) -> None:
    with st.container(border=True):
        st.subheader(f"ADVANCED MARKET CARD #{index}")
        st.markdown(f"**Event:** {card['event']}")
        st.markdown(
            f"**Sport / League / Market:** {card['sport']} | "
            f"{card['league']} | {card['market_category']}"
        )
        st.markdown(f"**Selection:** {card['selection']}")
        if card["point"] is not None:
            st.markdown(f"**Line / point:** {card['point']:+g}")
        st.markdown(f"**Source:** {card['source_label']}")
        st.markdown(f"**Market source:** {card['market_source']}")
        st.markdown(f"**Confidence:** {card['confidence']}")
        st.markdown(f"**Analysis label:** {card['analysis_label']}")
        st.markdown("**Not Guaranteed**")
        if card["bookmaker_key"]:
            st.markdown(f"**Bookmaker key:** `{card['bookmaker_key']}`")

        col1, col2, col3 = st.columns(3)
        col1.metric("American Odds", f"{card['american_odds']:+d}")
        col2.metric("Estimated Probability", format_percent(card["estimated_probability"]))
        col3.metric("Implied Probability", format_percent(card["implied_probability"]))

        col4, col5, col6 = st.columns(3)
        col4.metric("Edge", format_percent(card["edge"]))
        col5.metric("EV per $1", format_currency(card["ev_per_1_dollar"]))
        col6.metric("Potential Payout", format_currency(card["potential_payout"]))

        st.markdown(
            f"**Fractional Kelly:** {format_percent(card['fractional_kelly'])}"
        )
        st.markdown(
            f"**Suggested stake from bankroll:** "
            f"{format_currency(card['recommended_stake'])}"
        )
        st.warning(
            "Confirm the exact line and odds inside the Hard Rock Florida app before betting."
        )


def render_advanced_markets_page() -> None:
    st.title("Advanced Markets")
    render_warning_box()
    st.info(
        "Stage 3.5 checks The Odds API for advanced market availability and "
        "provides a manual fallback. It does not auto-bet, scrape, or log into Hard Rock."
    )
    st.warning(
        "Confirm the exact line and odds inside the Hard Rock Florida app before betting."
    )

    with st.expander("Market Support Matrix / Roadmap"):
        st.dataframe(
            pd.DataFrame(market_support_matrix()),
            use_container_width=True,
            hide_index=True,
        )

    try:
        api_key = get_configured_api_key()
        sports = load_sports(api_key)
    except (MissingApiKeyError, OddsApiError) as exc:
        st.error(str(exc))
        return

    sport_by_label = {
        f"{sport.get('group', 'Other')} | {sport['title']}": sport
        for sport in sports
    }
    selected_sport_label = st.selectbox(
        "Advanced sport",
        options=list(sport_by_label),
    )

    if st.button("Load advanced market events", type="primary"):
        selected_sport = sport_by_label[selected_sport_label]
        try:
            data = load_bookmaker_diagnostics(
                api_key,
                selected_sport["key"],
                "h2h",
            )
        except (OddsApiError, ValueError) as exc:
            st.error(str(exc))
            return
        data["sport_title"] = selected_sport["title"]
        data["sport_key"] = selected_sport["key"]
        st.session_state.advanced_events_data = data
        st.session_state.advanced_market_result = None

    data = st.session_state.advanced_events_data
    if not data:
        st.info("Load events to begin the advanced market availability check.")
        return
    if not data["events"]:
        st.info("No events were returned for the selected sport.")
        return

    event_by_label = {
        f"{event['commence_time']} | {event['event']}": event
        for event in data["events"]
    }
    selected_event_label = st.selectbox(
        "Advanced event",
        options=list(event_by_label),
    )
    selected_event = event_by_label[selected_event_label]
    category = st.selectbox(
        "Market category",
        options=[template.name for template in SOCCER_MARKET_TEMPLATES],
        format_func=lambda name: (
            f"{create_market_template(name).tier} | "
            f"{create_market_template(name).group} | {name}"
        ),
    )
    template = create_market_template(category)

    if st.button("Check API availability"):
        if template.manual_only:
            availability = determine_api_availability(template, [])
        else:
            candidate_outcomes = []
            api_errors = []
            for api_market_key in template.api_market_keys:
                try:
                    market_data = load_bookmaker_diagnostics(
                        api_key,
                        data["sport_key"],
                        api_market_key,
                    )
                except OddsApiError as exc:
                    api_errors.append(str(exc))
                    continue
                matching_event = next(
                    (
                        event
                        for event in market_data["events"]
                        if event["id"] == selected_event["id"]
                    ),
                    None,
                )
                if matching_event:
                    candidate_outcomes.extend(matching_event["outcomes"])

            availability = determine_api_availability(
                template,
                candidate_outcomes,
            )
            if not availability["available"] and api_errors:
                st.warning(
                    f"The API could not provide this market ({api_errors[0]}). "
                    "Manual entry is available below."
                )
        st.session_state.advanced_market_result = {
            "availability": availability,
            "category": category,
            "event_id": selected_event["id"],
        }

    result = st.session_state.advanced_market_result
    if (
        not result
        or result["category"] != category
        or result["event_id"] != selected_event["id"]
    ):
        st.info("Choose a category and check its current API availability.")
        return

    availability = result["availability"]
    if availability["available"]:
        st.success(f"Availability: {availability['label']}")
        st.dataframe(
            pd.DataFrame(availability["outcomes"])[
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
        line_by_label = {
            (
                f"{row['bookmaker']} | {row['selection']} | "
                f"{row['price']:+g}"
                + (f" | {row['point']:+g}" if row["point"] is not None else "")
            ): row
            for row in availability["outcomes"]
        }
        selected_line_label = st.selectbox(
            "API-filled line",
            options=list(line_by_label),
        )
        selected_line = line_by_label[selected_line_label]
    else:
        st.warning(
            "No matching API data is currently available. "
            "This market will use manual entry."
        )
        selected_line = None

    default_selection = selected_line["selection"] if selected_line else ""
    default_point = (
        float(selected_line["point"])
        if selected_line and selected_line["point"] is not None
        else 0.0
    )
    default_odds = int(selected_line["price"]) if selected_line else -110
    default_probability = (
        american_to_implied_probability(default_odds) * 100
        if selected_line
        else 50.0
    )

    with st.form("advanced_market_card_form"):
        player_name = ""
        if template.dynamic_player:
            player_name = st.text_input(
                "Player name",
                help="Player names are entered dynamically and are never hardcoded.",
            )
        selection = st.text_input("Advanced selection", value=default_selection)
        use_point = st.checkbox(
            "This market has a line / point",
            value=bool(selected_line and selected_line["point"] is not None),
        )
        point = st.number_input("Line / point", value=default_point, step=0.5)
        american_odds = st.number_input(
            "American odds from Hard Rock Florida",
            value=default_odds,
            step=5,
        )
        estimated_probability = st.number_input(
            "Estimated probability or market fair probability (%)",
            min_value=0.1,
            max_value=99.9,
            value=float(default_probability),
            step=0.1,
        )
        stake = st.number_input(
            "Advanced market stake",
            min_value=0.1,
            value=float(st.session_state.default_stake),
            step=0.5,
        )
        submitted = st.form_submit_button("Create advanced market bet card")

    if submitted:
        card_selection = (
            f"{player_name.strip()} | {selection.strip()}"
            if player_name.strip()
            else selection
        )
        try:
            card = build_advanced_market_card(
                sport=data["sport_title"],
                event=selected_event["event"],
                market_category=category,
                selection=card_selection,
                point=float(point) if use_point else None,
                american_odds=int(american_odds),
                estimated_probability=float(estimated_probability) / 100,
                stake=float(stake),
                bankroll=float(st.session_state.bankroll),
                kelly_multiplier=float(st.session_state.kelly_multiplier),
                bookmaker_key=(
                    selected_line["bookmaker_key"] if selected_line else None
                ),
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.advanced_cards.append(card.to_dict())
            st.success("Advanced market bet card created.")

    if st.session_state.advanced_cards:
        st.subheader("Advanced Market Bet Cards")
        for index, card in enumerate(
            reversed(st.session_state.advanced_cards),
            start=1,
        ):
            render_advanced_card(card, index)


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
            {"Stage": "Stage 3", "Feature": "Market average + no-vig", "Status": "Built now"},
            {"Stage": "Stage 3", "Feature": "Manual Hard Rock value scanner", "Status": "Built now"},
            {"Stage": "Stage 3.5", "Feature": "Advanced market templates", "Status": "Built now"},
            {"Stage": "Stage 4", "Feature": "Basic models", "Status": "Not active yet"},
        ]
    )
    st.dataframe(status, use_container_width=True, hide_index=True)


def main() -> None:
    initialize_session_state()

    with st.sidebar:
        st.header("Navigation")
        st.caption("Primary workflow")
        navigation_options = list(MAIN_NAVIGATION)
        if DEBUG_MODE:
            navigation_options.extend(DEBUG_NAVIGATION)
        page = st.radio(
            "Go to",
            navigation_options,
            key="navigation_page",
        )
        if DEBUG_MODE:
            st.caption(
                "Debug pages are visible: Live Odds, Market Comparison, and Advanced Markets."
            )

        st.divider()
        st.metric("Current bet cards", len(st.session_state.bets))
        st.metric("Default stake", format_currency(st.session_state.default_stake))
        st.metric("Bankroll", format_currency(st.session_state.bankroll))
        st.caption("Use Research Board as the main odds and value workflow.")

    if page == "Research Board":
        render_research_board_page()
    elif page == "Home":
        render_home_page()
    elif DEBUG_MODE and page == "Live Odds":
        render_live_odds_page()
    elif DEBUG_MODE and page == "Market Comparison":
        render_market_comparison_page()
    elif DEBUG_MODE and page == "Advanced Markets":
        render_advanced_markets_page()
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
