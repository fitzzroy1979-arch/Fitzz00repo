# Directive: Historical simulation

## Goal
Walk real historical daily closes through the actual `propose_trade` / `execute_paper_trade` logic to see how the paper-trading mechanics behave over time. No API key needed.

## Inputs
- `symbols` (default watchlist), `days` (default 90), `starting_cash` (default 3000)

## Steps
1. `execution/fetch_prices.py` per symbol, `--interval 1d --period <days>d`
2. `execution/run_simulation.py --prices .tmp/ --days N --starting-cash C --out output/simulations/<date>.md` — one trade per day, alternating buy/sell, using a throwaway portfolio state (never touches `state/portfolio.json`)

## Constraints
- 1 trade/day only: Yahoo's free intraday history covers ~60 days, so multi-trade-per-day simulation over 90 days needs a paid data source.
- Output must be labeled as a mechanics demonstration, not a strategy result.
