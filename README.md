# Hard Rock FL Odds Intelligence Dashboard

Personal sports betting research dashboard built with Python and Streamlit.

## Primary workflow

Use **Research Board** for the unified workflow:

- Select sport, event, market category, and specific market
- See exact Florida, generic Hard Rock, other-book, and manual sources separately
- Review market averages and no-vig probabilities
- Create source-labeled value research cards

The older Live Odds, Market Comparison, and Advanced Markets pages remain
available as secondary diagnostic tools.

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
