# execution/ — migration map from `fitzz/trading.py`

Each script: one job, CLI args in, JSON/Markdown out, exit non-zero on failure, no LLM calls
(except the two marked **spends tokens**). Shared helpers go in `_common.py`.

## Read this before using the table

This map was rewritten on 2026-09-04 against the actual source. The first version was written
without access to it and described a **different tool** — yfinance price fetching, seven backtest
strategies, a spot portfolio, YouTube and analyst scraping, a Streamlit dashboard. None of that
exists in this repo. What exists is a TradingView-bridge tool with one strategy, a futures paper
portfolio, and Perplexity-backed research. Rows below cite real line numbers in `fitzz/trading.py`.

Three things the architecture docs get wrong about the real source, unresolved:

1. **`CLAUDE.md` says one LLM call remains, in brief synthesis.** There are two LLM paths:
   `--research` (Perplexity Sonar) and `--learn` (four providers — Claude, Hermes/Together,
   Gemini, Perplexity). `--learn` has no counterpart in the architecture at all.
2. **The watchlist has two sources of truth.** `WATCHLIST` in `.env` (Yahoo form, `XRP-USD`) and
   `bridge.get_watchlist()`, which reads TradingView's own watchlist panel. `--watchlist` uses the
   latter; `_common.watchlist()` reads the former.
3. **Paper state does not live in `state/`.** The futures portfolio is at
   `.00fitzz/futures.json` and the order log at `.00fitzz/orders.log`, both at the repo root.

## Extracted

| Script | Pulls from `fitzz/trading.py` | Status |
|---|---|---|
| `_common.py` | `fmt_time` (L535); `MAX_BARS`, `DEFAULT_STARTING_CASH`, `INTERVAL_TO_TV`, `INTERVAL_MINUTES` (L85–133); `resolve_interval`, `period_to_bars`, `days_to_bars` (L377–414). Plus new: `.env` loader, workspace paths, Yahoo→TradingView symbol normalisation, `get_bridge()` | **done** |
| `fetch_prices.py` | `TradingViewBridge.load_bars` / `ensure_history` / `get_ohlcv` (L142–376), via `_common.get_bridge()` | **done** |
| `run_backtest.py` | `sma` (L416), `backtest_sma_cross` (L431), `_strategy_label` (L523), the symbol loop and `_is_proven` filter in `cmd_backtest` (L565–620). Verified bit-identical to the monolith across 5 parameter sets | **done** |
| `render_backtest_report.py` | `print_result_row` (L621), `print_backtest_summary` (L633) kept verbatim as `--format text`; Markdown deliverable into `output/` is new. Computes nothing | **done** |

## To extract

| Script | Pulls from `fitzz/trading.py` | Status |
|---|---|---|
| `run_simulation.py` | `simulate_strategy` (L1179–1311), `_sim_label` (L1160), the loop in `cmd_simulate` (L1312). Adds trailing stop, risk %, max-drawdown halt, blotter | TODO |
| `render_simulation_report.py` | `_print_sim` (L1351), `_print_sim_summary` (L1368) | TODO |
| `llm_client.py` | `_call_claude` (L757), `_call_hermes` (L785), `_call_gemini` (L818), `_call_perplexity` (L851), `_extract_json` (L741). Shared by the two scripts below; reads `ANTHROPIC_MODEL` from `.env` | TODO |
| `research_brief.py` | `RESEARCH_SYSTEM` (L1044), `_price_context` (L1064), `_research_user_prompt` (L1089), `_research_symbol` (L1101), `cmd_research` (L1109). **Spends tokens** (Perplexity Sonar) | TODO |
| `render_brief.py` | `_print_research` (L1139) — Markdown + sources list into `output/` | TODO |
| `tune_parameters.py` | `cmd_learn` (L967), `LEARN_SYSTEM` (L703), `_learn_user_prompt` (L721), `llm_propose` (L917), `_clamp_params` (L895), `_tune_symbol` (L936), `_print_best` (L1015), `_print_learn_row` (L1022). **Spends tokens.** Not in the old map at all | TODO |
| `propose_trade.py` | `check_trade_window` (L551) + `bridge.get_quote` price lookup from `cmd_trade` (L649) — compute only, write nothing | TODO |
| `log_trade.py` | the `ORDER_LOG` append from `cmd_trade` (L649–698). Currently a **stub** that never places an order; keep it that way | TODO |
| `futures_trade.py` | `cmd_futures_trade` (L1420), `_mark_price` (L1403) | TODO |
| `futures_portfolio.py` | `cmd_futures_portfolio` (L1475) | TODO |
| `futures_close.py` | `cmd_futures_close` (L1519) | TODO |
| `_futures_state.py` | `_load_futures` / `_save_futures` (L1389–1402). Decide first whether state moves from `.00fitzz/futures.json` to `state/` | TODO |
| `get_watchlist.py` | `TradingViewBridge.get_watchlist` (L197). Resolve the two-sources problem above first | TODO |
| `notify.py` | — | NEW, no source |
| `run_directive.py` | — | provided (skeleton) |
| `webhook_server.py` | — | provided (skeleton) |
| `webhooks.json` | — | provided |

## Backlog — described in the old map, no source to extract from

These were never in `fitzz/trading.py`. Building them is a feature project, not a migration, and
each needs its own decision about scope and data source:

- `fetch_analyst_views.py` — TradingView / FXStreet / DailyFX / ForexLive / Forex Factory sourcing
  with the credibility filter in `directives/source_credibility.md`
- `fetch_youtube_metadata.py` — YouTube search + priority channels (`@AlexanderELorenzo`,
  `@24hrsCrypto`), metadata only
- `fact_check_claims.py` — claim verification → confirmed / uncertain / contradicted
- `synthesize_brief.py` — a Claude call with a fixed prompt and output schema. Note `--research`
  already produces a cited brief via Perplexity; decide whether this replaces it or wraps it
- `scan_launch_platforms.py`, `score_project_credibility.py` — the `--discover` mode
- `dashboard.py` — Streamlit UI, SVG badge, TTS button, reading `output/` and `state/` only
- Spot paper portfolio (`state/portfolio.json`, `--portfolio` / `--reset-portfolio`) — only a
  futures portfolio exists
- The other six backtest strategies — only `backtest_sma_cross` exists

## Extraction rules

**Move code, don't rewrite it.** Every function that worked should land unchanged inside its
script; only the CLI wrapper and file I/O are new. Test each script standalone before wiring the
directive that uses it.

**One exception, ratified 2026-09-04: the TradingView bridge is imported, not copied.**
`_common.get_bridge()` imports `TradingViewBridge` from the `fitzz` package. It is 243 lines that
`fitzz trade` still uses and that were being actively fixed as of commit `b872deb`; a second copy
would fork a file still under repair. Any script needing price data or a quote goes through
`_common.get_bridge()` — do not paste the bridge into a script.

**Anything that spends tokens gets checked with the user before it runs.** That is
`research_brief.py` and `tune_parameters.py`.

**Paper trades need explicit approval on every invocation** — never stored, never defaulted, never
reachable from a webhook.
