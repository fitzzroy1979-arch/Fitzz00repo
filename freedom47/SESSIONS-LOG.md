# SESSIONS-LOG.md — Freedom 47

**Read this file in full before doing anything else in a session. Append an entry before you finish.**
This log is the continuous memory of the project across sessions and across AI environments (Claude, Codex, Gemini, etc.). If it isn't in here, the next agent won't know it happened.

## How to write an entry
- One entry per session, newest at the bottom. Never edit or delete previous entries — add a correction in your own entry instead.
- Use the template. Keep it factual: what was done, what was decided, what broke, what's next.
- "Open items" carries forward: copy anything still open from the previous entry into yours, mark it resolved or still open.
- If you changed a directive or script, name the file. If you spent API tokens, say so.

```
## YYYY-MM-DD — <agent/environment> — <one-line title>
**Context going in:** ...
**Done:** ...
**Decisions:** ...
**Broke / learned:** ...
**Files touched:** ...
**Open items:** ...
**Next session should start by:** ...
```

---

## Standing facts (update in place — the only section that is edited, not appended)
- Project: **Freedom 47**. Agent persona: **Agent 47** (was "00Fitzz"; legacy file is still named `00fitzz.py`).
- Purpose: cited market-research briefs + local paper trading for the user's *manual* decisions. No live exchange connection exists or is authorized.
- Watchlist: XRP, XLM, HBAR, ZAMA (`WATCHLIST` in `.env`, Yahoo `-USD` tickers).
- Model: Claude Fable 5.1 (`claude-fable-5-1`) for everything.
- Paper trading: crypto only, $3,000 starting cash, fee 0.10%, slippage 5 bps, **explicit approval required on every trade** — never stored, never via webhook/scheduler.
- User preferences: when tests reveal problems, surface them and let the user decide — don't auto-fix silently. Don't create/overwrite directives without asking. Check with the user before re-running anything that costs tokens.
- Source rules live in `directives/source_credibility.md`; priority YouTube channels `@AlexanderELorenzo`, `@24hrsCrypto`; Investopedia is reference-only.

---

## 2026-09-03 — Claude (claude.ai chat) — Migrated framework to 3-layer architecture
**Context going in:** Freedom 47 existed as one file, `00fitzz.py` (CLI modes: single-symbol/watchlist brief, `--backtest` w/ 7 strategies & 8 intervals, `--trade`/`--portfolio`/`--reset-portfolio`, `--simulate`, `--discover`, scheduler; `streamlit run` for dashboard). User supplied new agent instructions defining a Directive → Orchestration → Execution architecture and asked for the workspace to be re-framed around it. The Modal webhook example in those instructions is illustrative only (fictitious endpoints); any webhook provider is acceptable.

**Done:**
- Created repo scaffold: `CLAUDE.md` = `AGENTS.md` = `GEMINI.md` (adapted instructions), `.env.example`, `.gitignore`, `.tmp/`, `output/`, `state/`, `legacy/`, `MIGRATION.md`.
- Wrote 9 directives in `directives/` mapping 1:1 to existing 00fitzz.py modes, plus shared `source_credibility.md` and `directives/README.md` index.
- Wrote `execution/run_directive.py` (chain runner for research_brief / backtest / discover / simulate; paper_trade deliberately excluded because it needs an interactive approval prompt), `execution/webhook_server.py` (provider-agnostic; hard-blocks `execute_paper_trade`), `execution/webhooks.json`, `execution/README.md` (function → script migration map).
- Syntax-checked the two Python files and the JSON. No API tokens spent.

**Decisions:**
- Only one LLM call remains inside a run: `execution/synthesize_brief.py`. Everything else deterministic.
- Portfolio state moves from wherever 00fitzz.py kept it to `state/portfolio.json`.
- Dashboard becomes read-only over `output/` and `state/`; no compute in it.
- 4h bars remain a 1h resample (Yahoo has no native 4h); per-interval period clamps recorded in `directives/backtest.md`.

**Broke / learned:**
- Sandbox shell had no brace expansion (`mkdir {a,b}` made a literal dir) — irrelevant to the user's machine, noted only so nobody chases it.
- **Actual code extraction was NOT done**: `00fitzz.py` was not available in the session. All rows in `execution/README.md` are `TODO — extract` except the two framework scripts.

**Files touched:** everything in the delivered `freedom47-3layer.zip` (new).

**Open items:**
- [ ] Extract `00fitzz.py` into the scripts listed in `execution/README.md` (order in `MIGRATION.md`: `_common.py` + `fetch_prices.py` first, `synthesize_brief.py` last).
- [ ] Write `requirements.txt` (carry over from existing project).
- [ ] Write `execution/notify.py` (new — email/sheet delivery).
- [ ] Deploy a webhook to a real provider once `run_directive.py` chains work end to end.
- [ ] Live/real exchange connection — still a separate future step, needs explicit user sign-off before any work starts.

**Next session should start by:** asking the user for `00fitzz.py` (or locating it in the repo), then extracting `_common.py` and `fetch_prices.py` and testing `fetch_prices.py --symbol XRP-USD --interval 4h` before touching anything else. Surface test failures; don't auto-fix.

---

## 2026-09-04 — Claude (Claude Code, desktop) — Extracted `_common.py` + `fetch_prices.py`; found the migration map describes a different tool
**Context going in:** Previous session built the 3-layer scaffold without access to the source file. This session unzipped `freedom47-3layer.zip` into the repo (`~/Desktop/AI`), symlinked `freedom47/fitzz -> ../fitzz` so the `00fitzz.py` shim runs in place, and committed/merged that to `main` (`0e49100`). Then started the extraction at the order given in `MIGRATION.md`.

**Done:**
- `.env` created from `.env.example`, `ANTHROPIC_MODEL=claude-fable-5-1` (gitignored, all key fields blank).
- `execution/_common.py` — .env loader, workspace paths, `MAX_BARS` / `DEFAULT_STARTING_CASH` / `INTERVAL_TO_TV` / `INTERVAL_MINUTES` / `BARS_PER_YEAR`, `resolve_interval` / `period_to_bars` / `days_to_bars` (verbatim from `fitzz/trading.py`), `normalize_symbol`, `get_bridge`, `write_json` / `read_json`.
- `execution/fetch_prices.py` — one symbol in, JSON bars out; `--period` / `--days` / `--bars` windows, `--out`, `--stdout`, non-zero exit on failure.
- Tested: both compile; `--help` clean; helpers return correct values (4h→240, 1y@4h→2190 bars, 90d@4h→540, XRP-USD→XRPUSD); bridge-down path exits 1 with the setup message, bad interval exits 2. Then TradingView Desktop was launched with `--remote-debugging-port=9222` and the live fetch **passed**: all four watchlist symbols returned real, distinct data (XRPUSD 1.4502 / HBARUSD 0.07916 / XLMUSD 0.184601 / ZAMAUSD 0.05247 at the same last bar), uniform 14400s spacing, monotonic timestamps, OHLC invariants hold. The documented acceptance command (`--symbol XRP-USD --interval 4h`, defaulting to 1y) returned 2190/2190 bars in 19.7s, so the chart's lazy-load paging via `ensure_history` reaches a full year. No API tokens spent.

**Decisions:**
- `fetch_prices.py` reads TradingView through the `tv` bridge, not yfinance — that is what the code actually does (see below).
- `_common.get_bridge()` **imports** `TradingViewBridge` from the `fitzz` package instead of copying it, deviating from the "move code, don't rewrite it" rule. The bridge is 243 lines and `fitzz trade` still uses it, so a second copy would drift. **Correction to an earlier claim in this entry's first draft:** commit `2b76754` was cited as a bridge fix; it is not — it is the Claude `--learn` max_tokens fix and never touched the bridge. The real and much stronger reason is under Broke/learned. Flagged to the user, not yet ratified.

**Broke / learned:**
- **The migration map in `execution/README.md` describes a tool that does not exist in this repo.** The previous session wrote it from description, without the source. Verified against `fitzz/trading.py` (1700 lines): zero occurrences of yfinance, youtube, fact-check, streamlit, discover, or resample. What actually exists: `TradingViewBridge` (subprocess to the `tv` CLI over Chrome DevTools :9222), **one** strategy `backtest_sma_cross` plus `simulate_strategy` — not seven, a **futures** paper portfolio in `.00fitzz/futures.json` (`cmd_futures_trade` / `_portfolio` / `_close`) — not a spot portfolio, and `cmd_research` on **Perplexity Sonar** — not a Claude call. `cmd_learn` (four LLM providers) has no row in the map at all. So `fetch_analyst_views.py`, `fetch_youtube_metadata.py`, `fact_check_claims.py`, `scan_launch_platforms.py`, `score_project_credibility.py` and `dashboard.py` have no source to extract from — they would be new features, not migrations.
- **The bridge capabilities this all depends on are uncommitted.** `git show HEAD:fitzz/trading.py` has *none* of `get_chart_state`, `wait_for_chart`, `_fingerprint`, `ensure_history`, or the tempfile stdout read — they exist only in the working tree (`git diff HEAD -- fitzz/trading.py` = +170/-18). So the chart-confirmation that made the four symbols return distinct series, and the `ensure_history` paging that reached 2190 bars, are all work-in-progress that is not in git. Committed HEAD would have failed both tests. Anything importing or copying the bridge inherits that exposure until the change is committed.
- The Yahoo-form watchlist (`XRP-USD`) is kept in `.env` and normalised at the edge, so the documented commands still work against a TradingView feed.
- `timeout` is not available on this Mac (no coreutils); use plain invocation.

**Files touched:** `freedom47/.env` (new, gitignored), `freedom47/execution/_common.py` (new), `freedom47/execution/fetch_prices.py` (new), this log. `freedom47/execution/README.md` (rewritten against the real source).

**Open items:**
- [x] **Resolved:** the migration map was rewritten against the real source (`execution/README.md`). 16 rows now cite real line numbers in `fitzz/trading.py`; the six sourceless rows moved to a clearly-marked Backlog section, so they are not lost but are not pretending to be migrations either. Three unresolved contradictions between the architecture docs and the source are recorded at the top of that file: two LLM paths not one, two watchlist sources of truth, and paper state living in `.00fitzz/` rather than `state/`.
- [x] **Resolved:** import-instead-of-copy for the bridge is **ratified**, recorded as a named exception in the map's extraction rules.
- [ ] Decide the three contradictions the rewritten map names (LLM paths, watchlist source, state location) — `get_watchlist.py` and `_futures_state.py` are blocked on the last two.
- [x] Live-fetch test of `fetch_prices.py` — **passed** (see Done). Requires TradingView Desktop running with the debug port; `fetch_prices.py` exits 1 with the setup message when it is not.
- [ ] **Commit the working-tree changes to `fitzz/trading.py`** (+170/-18: chart confirmation, stale-bar fingerprint, `ensure_history` paging, tempfile stdout). Untracked/uncommitted and everything in `execution/` now leans on it. Also uncommitted: `README.md`, `fitzz/__init__.py`, `fitzz/cli.py`, and untracked `fitzz/feed.py`.
- [ ] (carried) `requirements.txt` — still unwritten; nothing extracted so far needs a third-party dep (stdlib only).
- [ ] (carried) `execution/notify.py` — new, email/sheet delivery.
- [ ] (carried) Deploy a webhook to a real provider once `run_directive.py` chains work end to end.
- [ ] (carried) Live/real exchange connection — still a separate future step, needs explicit user sign-off.

**Next session should start by:** getting the two decisions above from the user. Then, if the map is being rewritten, do it before extracting anything else — `run_backtest.py` is the next real row and it depends on which strategy set is authoritative.

---

## 2026-09-04 — Claude (Claude Code, desktop) — Extracted `run_backtest.py`; verified bit-identical to the monolith
**Context going in:** Same session as the entry above, continued after the map rewrite. TradingView Desktop running on :9222 throughout.

**Done:**
- `execution/run_backtest.py` — `sma`, `backtest_sma_cross`, `_strategy_label`, `_is_proven` copied verbatim from `fitzz/trading.py`. Takes prices from `--prices FILE` (repeatable, from `fetch_prices.py`) or fetches for `--symbol` / `--watchlist` / `--env-watchlist`. Writes a JSON payload (`ran_at`, `starting_capital`, `strategy`, `results[]`); no table printing — that is `render_backtest_report.py`'s job.
- `fmt_time` moved into `_common.py` (shared by backtest, simulation and the renderers) and imported by name so the copied function bodies stay byte-identical.
- `execution/README.md` — `run_backtest.py` moved to the Extracted section; `_common.py` row now cites `fmt_time` (L535).

**Decisions:**
- Pure strategy functions are **copied** verbatim, as the extraction rule says. The import exception stays scoped to the bridge alone: `sma`/`backtest_sma_cross` are self-contained and stable, unlike the bridge.
- `run_backtest.py` emits JSON only. Rendering is a separate row, so the same metrics can feed a report, a webhook or the dashboard without re-running the maths.

**Broke / learned:**
- **Equivalence verified, not assumed.** Ran the copied `backtest_sma_cross` and the monolith's side by side on the same 2190 bars across 5 parameter sets (plain 20/50; 5/200 + trend100; 10/30 + sl5 + tp15; 3/5 + sl2.5 + trend200; 50/51) and the short-series error path — all six outputs compared equal as whole dicts. If either copy is edited later, re-run that comparison before trusting it.
- Own bug, found and fixed during testing: the default `--out` name used `--interval` (default `1d`) even when the bars came from a 4h file, so a 4h backtest was landing in `backtest_1d.json`. Now derives the tag from the interval the bars actually carry.
- Error paths: no args exits 2, unreadable price file exits 1, bad interval exits 2.
- Live end-to-end (`--symbol XRP-USD --interval 1d --period 6mo`) fetched and backtested in one command, 180 bars. No API tokens spent — nothing here calls an LLM.

**Files touched:** `freedom47/execution/run_backtest.py` (new), `freedom47/execution/_common.py` (added `fmt_time`, `datetime` import), `freedom47/execution/README.md`, this log.

**Open items:**
- [ ] Decide the three contradictions the rewritten map names (LLM paths, watchlist source, state location) — `get_watchlist.py` and `_futures_state.py` are blocked on the last two.
- [ ] Next rows: `render_backtest_report.py`, then `run_simulation.py`.
- [ ] (carried) `requirements.txt` — still unwritten; everything extracted so far is stdlib only. The un-extracted `--learn` path needs the `anthropic` package.
- [ ] (carried) `execution/notify.py` — new, email/sheet delivery.
- [ ] (carried) Deploy a webhook to a real provider once `run_directive.py` chains work end to end.
- [ ] (carried) Live/real exchange connection — still a separate future step, needs explicit user sign-off.

**Next session should start by:** `render_backtest_report.py` (`print_result_row` L621, `print_backtest_summary` L633) turning a `run_backtest.py` payload into Markdown in `output/`. It needs no bridge and no tokens, so it is testable against the JSON already in `.tmp/`.
