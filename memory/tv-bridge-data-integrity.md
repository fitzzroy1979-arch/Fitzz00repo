---
name: tv-bridge-data-integrity
description: TradingView bridge reads lie silently — verify the bars against price, spacing and depth, never the chart's own description of itself.
metadata:
  type: feedback
---

Six data bugs found in the fitzz/TradingView bridge during the 2026-10 strategy search, all the same shape: **a read that was short, stale, or another symbol's entirely, passing as valid.** None errored; each silently changed results.

1. `ensure_history` stopped paging on the first `requestMoreDataAvailable() == false`, which also reads false mid-fetch. HBAR ran on 1,300 of 1,466 bars and overstated its return by 69 points.
2. `load_bars` reported a truncated read and a genuinely short feed with the same message — indistinguishable to caller or human.
3. The chart reports a new symbol *before* its data repaints: a 4h CC read came back holding BTC's series.
4. Same for timeframes: a daily CC request returned its 1,482-bar 4h series.
5. Two processes driving one chart interleave symbol switches and each gets the other's bars. Now an `flock` at `.00fitzz/chart.lock` (`FITZZ_NO_CHART_LOCK=1` to disable).
6. The sweep cache re-read short series each run and kept the longer — so one cross-symbol read overwrote good CC data with BTC's.

Guards now check **the data**, not the chart's claim about itself: bar count against confirmed depth, last close against a live quote (retry the quote — it fails exactly when the bridge is busy, and treating "unavailable" as "allow" self-disables the check), median bar spacing against the requested interval, and the lock against concurrent readers.

**Why:** Every one of these produced plausible-looking numbers. A backtest cannot be trusted further than its bars, and these bars misreport themselves under load.

**How to apply:** Before trusting any new bridge read path, ask what happens if it returns the previous symbol, half the bars, or the wrong timeframe. If the answer is "wrong number, no error", add a check on the data itself. Never reinstate a guard that treats an unavailable cross-check as a pass. See [[tradingview-mcp-install]].
