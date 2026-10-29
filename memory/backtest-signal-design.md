---
name: backtest-signal-design
description: What flatters a backtest and means nothing — redundant signals, win rate, confluence counts, adding shorts.
metadata:
  type: feedback
---

Four things that make a strategy look good on the fitzz backtests without adding any edge:

**Redundant signals.** The first five-point confluence build had three conditions all answering "is price going up" (trend/momentum correlated at +0.45). It returned +4,250% on BTC. Rebuilding the five to measure genuinely different dimensions — direction, momentum, volatility regime, participation, location — dropped it to +165%. The redundancy was a trend follower in disguise. **Measure pairwise correlation of the boolean conditions before trusting a multi-signal strategy.**

**Win rate.** Uninformative in both directions: `mean_revert` wins 64–74% of trades and loses money; trend followers win ~40% at a 3.9x payoff and also lose money. Never quote win rate as support.

**More confluence conditions.** Confluence is a filter, not a generator. Going 3-of-5 to 5-of-5 cut trades from 172 to 12 across six symbols and left expectancy flat. A filter can strip false signals off a signal that has edge; it cannot manufacture edge.

**Adding shorts.** Of six symbols only FLR improved. ZBCN went -2.68% to -88.73% at 96% drawdown — it fell by chopping, not trending, so every false signal paid twice. A falling asset is not a shortable one. With shorts on, 34 of 35 pairs lost significance by 10 bps and the long-only cost-robust result disappeared.

**Why:** Each of these produced a result I initially read as encouraging, and each dissolved when measured properly. The user pushed back on the confluence build specifically, and measuring the correlations is what exposed it.

**How to apply:** When a backtest number looks strong, check these four before reporting it. See [[backtest-evidence-order]].

**To ask what the losing trades have in common**, use `fitzz/journal.py` (`--journal` / `--journal-dump` on `run_sweep_4h.py`) rather than eyeballing trades: it logs each round trip with nine tape readings at entry and measures winner-vs-loser separation in-sample and on held-out trades. Verify any such tool against a planted signal first — one that cannot recover a relationship known to be there cannot be trusted reporting one absent. Read its output with [[pooled-comparison-composition]] in hand.
