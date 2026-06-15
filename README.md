# Hard Rock FL Odds Intelligence Dashboard

Stage 1 personal sports betting research dashboard built with Python and Streamlit.

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

- Stage 2: The Odds API integration
- Stage 3: comparison books, market average, and no-vig fair probability
- Stage 4: basic models
- Stage 5: improved parlay builder
- Stage 6: sport-specific models
- Stage 7: exports to CSV/Google Sheets
