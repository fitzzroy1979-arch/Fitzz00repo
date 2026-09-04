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
