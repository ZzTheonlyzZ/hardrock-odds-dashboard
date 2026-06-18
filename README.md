# Hard Rock FL Odds Intelligence Dashboard

Personal sports betting research dashboard built with Python and Streamlit.

## Primary workflow

Use **Research Lab** for the unified workflow:

- Select sport, event, market category, and specific market
- See exact Florida, generic Hard Rock, other-book, and manual sources separately
- Review market averages and no-vig probabilities
- Review API usage, request budget, research gaps, team/player/context placeholders, and betting signals
- Create source-labeled value research cards
- Export AI Research Package and ChatGPT Analysis Package

The older Live Odds, Market Comparison, and Advanced Markets pages are hidden from the main sidebar and remain internal diagnostic/debug renderers only.

## Important warnings

This app is for research only. It does not place bets, log into Hard Rock, scrape Hard Rock, bypass protections, or automate betting.

All outputs are potential value bet research labels, not guaranteed winners.

Manual confirmation required in the Hard Rock app before betting. Do not bet if the line moved.

Betting is high variance. Only risk money you can afford to lose.

## Stage 1 features

- Manual odds entry
- American odds to implied probability
- American odds to decimal odds
- Expected value calculator
- Edge calculator
- Full Kelly and fractional Kelly calculator
- $1 default stake mode
- Bet cards
- Ranked bet table
- CSV download of current cards
- Simple parlay builder
- Correlation and high-variance warnings

## Stage 2 features

- In-season sports from The Odds API
- Current `hardrockbet_fl` moneyline, spread, and total odds
- One market per refresh to conserve free-plan API credits
- Diagnostic mode showing all unique `us`/`us2` bookmaker keys and event count
- Explicit upstream warning when `hardrockbet_fl` is absent before filtering
- Support for `hardrockbet_fl` and optional `hardrockbet` fallback
- Florida-specific feed priority when both keys are available
- Event Explorer with matchup, start time, and event-level bookmaker availability
- Full events table and event-level market outcome board
- One-click prefill from an API line into the Stage 1 manual bet form

## Stage 3 features

- Sport, event, and market comparison from The Odds API
- Per-book implied probability
- Average market odds by selection
- Per-book normalized no-vig consensus probability
- Manual Hard Rock Florida price override
- Edge, EV per $1, payout, and fractional Kelly calculations
- Persistent Stage 3 research cards with conservative labels

## Stage 3.5 features

- Tier 1 core, Tier 2 player prop, and Tier 3 special market templates
- Dynamic player names for player props
- Per-event API availability checks
- API-filled or manual fallback entry
- Source labels for API, generic Hard Rock, market reference, and manual data
- Market support matrix and roadmap
- Advanced market EV, payout, edge, and fractional Kelly cards

## Safety model

- No automatic betting
- No sportsbook login
- No direct Hard Rock scraping
- No proxies, hidden endpoints, or protection bypasses
- Every result requires manual confirmation in the Hard Rock Florida app
- American odds format
- Cached sports and odds requests
- Safe missing-key, invalid-key, network, and rate-limit messages

## Research Lab

Research Lab combines odds, source coverage, market mapping, manual Hard Rock FL entry, research context, betting signals, API budget awareness, and exports into one clean workflow.

It does:

- Use The Odds API for odds, market consensus, `hardrockbet_fl`, and `hardrockbet` availability
- Label every line by source and confidence
- Fall back to manual Hard Rock FL entry when an API does not return a market
- Track source coverage and quota status where headers or local counters are available
- Generate AI Research Package exports for deeper external analysis
- Generate a cleaner ChatGPT Analysis Package for copy/paste review

It does not:

- Place bets
- Log into Hard Rock
- Scrape Hard Rock
- Use proxies, hidden endpoints, captcha bypasses, or sportsbook automation
- Guarantee winners

Manual Hard Rock FL confirmation is always required before any wager.

## API keys and quotas

Supported environment/config keys:

- `THE_ODDS_API_KEY`: odds, Hard Rock source detection, and market consensus
- `API_FOOTBALL_KEY`: future fixture/team/player/injury research
- `FOOTBALL_DATA_KEY`: future backup fixture/standings data
- Optional `SPORTMONKS_KEY`: future paid-source integration only

Missing keys must not crash the app. Research Lab marks unavailable sections as `Unavailable - API key missing` and continues with available sources.

Quota behavior:

- The Odds API headers: `x-requests-remaining`, `x-requests-used`, `x-requests-last`
- API-Football headers: `x-ratelimit-requests-limit`, `x-ratelimit-requests-remaining`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`
- football-data.org headers: `X-Requests-Available-Minute`, `X-RequestCounter-Reset`
- Open-Meteo is tracked with local free-use limits: 10,000/day, 5,000/hour, 600/minute

Research Lab shows a request budget preview before optional research loads.

## Source confidence hierarchy

1. Manual Hard Rock FL Entry: user-confirmed, highest confidence if copied from the app
2. Exact Hard Rock FL API / `hardrockbet_fl`: high confidence
3. Generic Hard Rock API / `hardrockbet`: medium confidence, may differ from Florida
4. Market Consensus / Other Books: comparison only
5. Unsupported or missing API markets: manual entry required

## Exports

Research Lab exports:

- Copy text
- TXT
- Markdown
- JSON
- CSV market rows
- ChatGPT Analysis Package markdown

All exports are for potential value bet research only. ChatGPT analysis should separate Serious EV Bets, Small Edge Leans, Lottery Tickets, and No Bets, and should always include what could go wrong.

## The Odds API setup

Create `.streamlit/secrets.toml`:

```toml
THE_ODDS_API_KEY = "your-api-key"
```

The secrets file is ignored by Git and must never be committed.

## Install locally

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

In GitHub Codespaces, run:

```bash
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Keep the forwarded port private.

## Test

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py src tests
```

## Project structure

```text
hardrock-odds-dashboard/
  app.py
  requirements.txt
  README.md
  .gitignore
  src/
    __init__.py
    config.py
    probabilities.py
    ev.py
    models.py
    parlay.py
    ui_components.py
    odds_api.py
    rundown_api.py
    sports_stats.py
    normalize.py
    cache.py
  data/
    manual_entries.csv
    sample_odds.json
```

## Later stages

- Stage 3: comparison books, market average, and no-vig fair probability
- Stage 4: basic models
- Stage 5: improved parlay builder
- Stage 6: sport-specific models
- Stage 7: exports to CSV/Google Sheets
