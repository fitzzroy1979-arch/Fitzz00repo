# execution/ — migration map from 00fitzz.py

Each script: one job, CLI args in, JSON/Markdown out, exit non-zero on failure, no LLM calls
(except `synthesize_brief.py`). Shared helpers go in `_common.py` (env loading, .tmp paths, Yahoo ticker normalisation).

| Script | Pulls from 00fitzz.py | Status |
|---|---|---|
| `_common.py` | env/constants (DEFAULT_STARTING_CASH, WATCHLIST, interval → period/bars-per-year tables) | TODO — extract |
| `fetch_prices.py` | yfinance fetch + 4h resampling + per-interval period clamp | TODO — extract |
| `fetch_analyst_views.py` | TradingView / FXStreet / DailyFX / ForexLive / Forex Factory / blog sourcing + credibility filter | TODO — extract |
| `fetch_youtube_metadata.py` | YouTube search + priority channels, metadata only | TODO — extract |
| `fact_check_claims.py` | claim verification → confirmed / uncertain / contradicted | TODO — extract |
| `synthesize_brief.py` | the Claude API call (prompt + schema) — reads `ANTHROPIC_MODEL` | TODO — extract |
| `render_brief.py` | Markdown report writer, "Agent 47" header, halving context, sources list | TODO — extract |
| `run_backtest.py` | 7 strategies + metrics | TODO — extract |
| `render_backtest_report.py` | backtest table/report | TODO — extract |
| `propose_trade.py` | price fetch + slippage + fee + cash/holdings checks | TODO — extract |
| `execute_paper_trade.py` | portfolio write (state/portfolio.json) | TODO — extract |
| `show_portfolio.py`, `reset_portfolio.py` | --portfolio / --reset-portfolio | TODO — extract |
| `run_simulation.py` | run_historical_simulation | TODO — extract |
| `scan_launch_platforms.py`, `score_project_credibility.py` | --discover | TODO — extract |
| `dashboard.py` | Streamlit UI, SVG badge, TTS button — reads files only | TODO — extract, strip compute |
| `notify.py` | email / sheet delivery | NEW |
| `run_directive.py` | orchestration entry point used by cron & webhooks | provided (skeleton) |
| `webhook_server.py` | provider-agnostic webhook handler | provided (skeleton) |
| `webhooks.json` | slug → directive mapping | provided |

Extraction rule: move code, don't rewrite it. Every function that worked in 00fitzz.py should land unchanged
inside its script; only the CLI wrapper and file I/O are new. Test each script standalone before wiring the
directive that uses it.
