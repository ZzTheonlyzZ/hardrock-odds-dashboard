# Hard Rock FL Odds Intelligence Dashboard

Personal sports betting research dashboard built with Python and Streamlit.

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
