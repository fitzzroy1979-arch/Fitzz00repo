---
name: fitzz-strategy-search-result
description: The fitzz strategy search is measured out — five families x eleven symbols x three timeframes found no edge. Don't re-run it.
metadata:
  type: project
---

As of 2026-10-28, the fitzz strategy search at `~/Desktop/AI` has run ~385 symbol/family significance sweeps: five families (`sma_cross`, `follow_money`, `breakout`, `mean_revert`, `confluence`), long and short, eleven symbols, timeframes 1d/4h/1h, costs 10/25/50/100 bps, plus a swept volatility-regime entry gate in all four timeframe/direction corners. **Result: no detectable edge anywhere.**

Watchlist / main focus: BTC, XRP, FLR, ZBCN, CC (Canton Network), HBAR, QNT. Out-of-sample set: SOL, ADA, LINK, DOT. Account specifics are in [[local-workspace]], which is not tracked.

**ZBCN mean_revert 4h long is the one reproducible result** — SPA 0.021 / 0.018 / 0.016 across three independent data pulls (10-17, 10-20, 10-26), and on the third it survived the cost scan at all four levels with a positive holdout at each, p(SPA) never above 0.023. Nothing else has that profile. It is still not tradable: Reality Check never clears it (0.124 at best, and when the two tests split RC has been right every time), and ZBCN is the least liquid instrument in the set, so the modelled 10 bps round-turn is least believable exactly where the edge appears. Do not round this down to "nothing worked", and do not promote it either.

Everything else died, and four of five candidates are unreadable across pulls — QNT 0.031 → 0.046 → 0.019, CC 0.024 → 0.473 (significant to nothing on 2% more data). The volatility gate the trade journal pointed at was swept properly and closed in all four corners; see FINDINGS.md.

The dominant pattern, across ~30 independent symbol/family pairs: healthy in-sample edge (+0.0001 to +0.0006 per bar) with a **negative holdout**. That is a picture of what a parameter search does to this data, not of a strategy.

**Why:** Re-running these sweeps produces the same answer at a cost of hours. The data is measured out; the full write-up with methodology is in `FINDINGS.md` in the repo.

**The flows are tested too, as of 2026-10-28, and both are null.** CFTC CME-Bitcoin positioning over 444 aligned weeks (release-date alignment, not as-of): every forward correlation inside noise, three of four *backward* ones significant — it describes the week just past and not the week ahead. SEC EDGAR weekly filing counts over three queries, 1,377 requests: nothing reaches |t| = 1.5 in either direction, a stronger null still, since filing counts do not even describe the past. So "a signal that is not a function of price and volume" has been tried, not just contemplated.

**How to apply:** If asked to "run the sweep" again, run it — but say up front what it has already returned, and read any sub-5% result against [[backtest-evidence-order]] rather than as news. Do not offer the CFTC/SEC feeds as the promising untried direction; they are tried. What is actually left is outside this repo: a different market (all of this is crypto through one 2024–2026 regime), a faster clock where 10 bps can be cleared, or reading *what filings say* rather than counting them. Each is a new project, not a refinement of this one.
