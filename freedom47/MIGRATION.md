# Migrating Freedom 47 to the 3-layer architecture

## What changes
- **Before:** `00fitzz.py` — one file holding research, backtest, paper-trading, simulation, discovery,
  scheduler, and dashboard, with the LLM steering all of it.
- **After:** the LLM (orchestration) reads `directives/*.md` and runs single-purpose scripts in `execution/`.
  The only Claude API call left is `synthesize_brief.py`. Everything else is deterministic.

## What does not change
- Agent 47 name, Freedom 47 project name, watchlist, credibility rules, fact-check flags,
  7 backtest strategies + metrics, 8 intervals, $3,000 starting cash, fees/slippage, approval-before-trade.
- Your existing `00fitzz.py` keeps working until every row in `execution/README.md` is extracted.

## Order of work
1. `pip install -r requirements.txt` (same deps as before); copy `.env.example` → `.env`, set `ANTHROPIC_MODEL=claude-fable-5-1`
2. Extract `_common.py` and `fetch_prices.py` first — everything else depends on them. Test with
   `python execution/fetch_prices.py --symbol XRP-USD --interval 4h --out .tmp/t.json`
3. Extract the backtest scripts → run `python execution/run_directive.py backtest --symbol XRP-USD --interval 1d`
4. Extract the paper-trading scripts (portfolio JSON moves to `state/portfolio.json`)
5. Extract the research-brief scripts; `synthesize_brief.py` last, since it costs tokens to test
6. Extract discovery, simulation, then `dashboard.py` (remove any compute — it reads files only)
7. Retire `00fitzz.py` (keep a copy in `legacy/`)

## Webhooks
`execution/webhook_server.py` is provider-agnostic. The Modal example in the original instructions is just
one deployment target; the slug → directive contract in `webhooks.json` is what matters.
