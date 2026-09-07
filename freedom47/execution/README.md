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
   latter; `_common.watchlist()` reads the former. Still unresolved — scripts expose both behind
   `--watchlist` / `--env-watchlist` so neither is chosen silently.

**Resolved 2026-09-04 (user decision):**

3. ~~Paper state does not live in `state/`.~~ **Paper state stays in `.00fitzz/`** —
   `futures.json` and `orders.log` at the repo root, where `fitzz trade` already reads them.
   The architecture's `state/` directory goes unused for now; one portfolio, one location,
   and the monolith and the extracted scripts cannot drift apart.
4. **Paper-trade approval is an interactive `y/N` prompt.** Never stored, never defaulted, never
   reachable from a webhook. A script that writes a trade must refuse to proceed when stdin is not
   a TTY rather than assuming yes.

## Extracted

| Script | Pulls from `fitzz/trading.py` | Status |
|---|---|---|
| `_common.py` | `sma` (L416), `fmt_time` (L535); `MAX_BARS`, `DEFAULT_STARTING_CASH`, `INTERVAL_TO_TV`, `INTERVAL_MINUTES` (L85–133); `resolve_interval`, `period_to_bars`, `days_to_bars` (L377–414). Plus new: `.env` loader, workspace paths, Yahoo→TradingView symbol normalisation, `get_bridge()` | **done** |
| `fetch_prices.py` | `TradingViewBridge.load_bars` / `ensure_history` / `get_ohlcv` (L142–376), via `_common.get_bridge()` | **done** |
| `run_backtest.py` | `sma` (L416), `backtest_sma_cross` (L431), `_strategy_label` (L523), the symbol loop and `_is_proven` filter in `cmd_backtest` (L565–620). Verified bit-identical to the monolith across 5 parameter sets | **done** |
| `render_backtest_report.py` | `print_result_row` (L621), `print_backtest_summary` (L633) kept verbatim as `--format text`; Markdown deliverable into `output/` is new. Computes nothing | **done** |
| `run_simulation.py` | `simulate_strategy` (L1179–1311), `_sim_label` (L1160), the loop in `cmd_simulate` (L1312). Trailing stop, risk sizing, max-drawdown halt, blotter. Verified bit-identical to the monolith across 6 parameter sets | **done** |
| `render_simulation_report.py` | `_print_sim` (L1351), `_print_sim_summary` (L1368) kept verbatim as `--format text`; Markdown deliverable with blotter table and exit-reason breakdown is new. Computes nothing | **done** |
| `llm_client.py` | `_call_claude` (L757), `_call_hermes` (L785), `_call_gemini` (L818), `_call_perplexity` (L851), `_extract_json` (L741), endpoints + model defaults (L95–107). All five verified source-identical via `inspect.getsource`. `--check` reports configuration without calling | **done** |
| `propose_trade.py` | `check_trade_window` (L551, source-identical) + the `get_quote` price lookup and order dict from `cmd_trade` (L649). Computes only; exits 3 when the window is shut | **done** |
| `log_trade.py` | the `ORDER_LOG` append from `cmd_trade` (L678–680). Interactive `y/N`, no `--yes`, refuses when stdin is not a TTY. Still a stub that never places an order | **done** |
| `_futures_state.py` | `_load_futures` / `_save_futures` (L1389–1402), `_mark_price` (L1403). State at `.00fitzz/futures.json` per decision 3. Adds `ensure_unique_id()` / `used_ids()`. Import-only | **done** |
| `futures_trade.py` | position maths from `cmd_futures_trade` (L1444–1458), verified field-identical long and short. `y/N` + TTY refusal; `--entry-price` works offline; id settled against state at write time | **done** |
| `futures_portfolio.py` | `cmd_futures_portfolio` (L1475–1517). Read-only, no approval. Falls back to BTCC's public marks when the bridge gives nothing, skipping `price_suspect` instruments; every mark tagged with its source. `--no-fallback` disables | **done** |
| `futures_close.py` | `cmd_futures_close` (L1519–1563). `y/N` + TTY refusal. Warns loudly when closing at entry price because no mark was available | **done** |
| `fetch_btcc_prices.py` | — NEW, no monolith source. Snapshots BTCC's public `GET /api/futures` (no auth): marks, bid/ask, index, fees, funding. **Snapshot only, no OHLCV.** Flags `price_suspect` instruments | **done (new)** |

## To extract

| Script | Pulls from `fitzz/trading.py` | Status |
|---|---|---|
| `research_brief.py` | `RESEARCH_SYSTEM` (L1044), `_price_context` (L1064), `_research_user_prompt` (L1089), `_research_symbol` (L1101), `cmd_research` (L1109). **Spends tokens** (Perplexity Sonar) | TODO |
| `render_brief.py` | `_print_research` (L1139) — Markdown + sources list into `output/` | TODO |
| `tune_parameters.py` | `cmd_learn` (L967), `LEARN_SYSTEM` (L703), `_learn_user_prompt` (L721), `llm_propose` (L917), `_clamp_params` (L895), `_tune_symbol` (L936), `_print_best` (L1015), `_print_learn_row` (L1022). **Spends tokens.** Not in the old map at all | TODO |
| `get_watchlist.py` | `TradingViewBridge.get_watchlist` (L197). Resolve the two-sources problem above first | TODO |
| `notify.py` | — | NEW, no source |
| `run_directive.py` | — | provided (skeleton) |
| `webhook_server.py` | — | provided (skeleton) |
| `webhooks.json` | — | provided |

## BTCC market data (public, no account)

`GET https://www.btcc.com/api/futures` — the endpoint BTCC's own trading page calls. No key, no
cookie, no login. 177 perpetuals with `last`/`bid`/`ask`/`index`, `maker_fee`/`taker_fee`,
`funding_rate`, price bounds, open interest and 24h volume. Wrapped by `fetch_btcc_prices.py`.

Two limits that decide what it can be used for:

- **Snapshot only.** No OHLCV, so it cannot feed `run_backtest.py` or `run_simulation.py`.
  TradingView via `fetch_prices.py` remains the only source of bars.
- **Roughly half the instruments quote zero.** 85 of 177 report `last`/`bid`/`ask`/`index` as
  exactly 0 while `enabled` with real open interest and volume — PONSUSDT does it on $153M of
  24h volume. `XRPUSDT`, `XLMUSDT` and `HBARUSDT` quote fine; `ZAMAUSDT` does not.
  `fetch_btcc_prices.py` sets `price_suspect: true` on these and warns; never consume a
  flagged quote.

Fee and funding **units are unconfirmed** — `taker_fee: 0.01` may be 0.01% or 1%. Values are
passed through as received. Confirm against BTCC's published schedule before any PnL use.

There is no evidence of a BTCC *demo* API; demo trading is a logged-in web feature.

`futures_portfolio.py` uses this as a **mark fallback** when TradingView gives nothing. Marks are
tagged `[btcc]` / `mark_source`, never blended silently: BTCC quotes its own perpetual book while
positions were priced at entry from TradingView, so the basis between the feeds lands in
unrealised PnL. Mixed marks are indicative, not exact.

**Position-id collision — fixed 2026-09-07 by a uniqueness check, not a format change.** Ids are
`"F" + %m%d%H%M%S + milliseconds`, so anything opening positions in a loop collided; five built in
a tight loop produced one id, five times, and `futures_close.py --target <id>` would have closed
all of them. `_futures_state.ensure_unique_id()` now settles the id at write time against both the
open positions and `.00fitzz/futures_closed.log`, appending `-2`, `-3`, … on collision. The base
format is untouched, so every id already in the closed log stays valid and no migration is needed.

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
`research_brief.py` and `tune_parameters.py`, both via `llm_client.py`. Importing `llm_client`
costs nothing; only `call()` does. `python execution/llm_client.py --check` reports which
providers are configured without making a request.

**Paper trades need explicit approval on every invocation** — an interactive `y/N` prompt per
decision 4. Never stored, never defaulted, never reachable from a webhook, and refused outright
when stdin is not a TTY.
