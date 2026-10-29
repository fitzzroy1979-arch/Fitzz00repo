---
name: backtest-evidence-order
description: Order to test a backtest result in — cost scan, then both p-value tests, then holdout. A headline return is not evidence.
metadata:
  type: feedback
---

A backtest headline ("beats hold on 5 of 6 symbols") is **never** a finding. Before reporting a candidate as real, run these gates in this order, cheapest and most decisive first:

1. **Cost scan first.** `fitzz`'s `--cost-scan` (10/25/50/100 bps) disqualifies most candidates in one step and costs far less than a sweep. "What round-turn cost does this need?" is a fact about the instrument — an edge that needs 10 bps on a thin small-cap is dead on the spread it will actually pay, whatever its p-value.
2. **Both SPA and Reality Check — but their agreement is not a second opinion.** They split on most candidates in the 2026-10 search (SPA 0.021 vs RC 0.113; 0.035 vs 0.154) and the conservative one — RC — was right every time, so clearing SPA alone is not clearing. When they *agree*, that is still one piece of evidence, not two: both correct the same in-sample quantity for the same grid search, and neither can see data that was never searched. On 2026-10-27 QNT mean_revert 1h short cleared both (SPA 0.009, RC 0.047) with a holdout of **-0.000673** — negative at every cost level, three times the in-sample edge with the sign reversed. Both were wrong; only the holdout caught it.
3. **Chance expectation.** ~0.05 x N sweeps clear 5% by luck. 2 hits out of 35 sweeps is *below* chance. Always state the count alongside the p-value.
4. **Holdout last, and only for a candidate whose p-value was already low.** A positive holdout on its own is worthless: HBAR/breakout held +0.000241 out of sample with a *negative* in-sample edge and p = 1.000 — 1,650 bars of luck.

**A filter or extra parameter must be swept, never chosen.** If a feature looks like it separates good trades from bad, put its threshold *into the grid* with the no-op value (0, off, unfiltered) alongside it, and re-sweep. Then the correction pays for having chosen it, and the filter has to beat the unfiltered version of itself inside the same test. Choosing a threshold by looking at the answer and then testing only that threshold is not a test. On 2026-10-22 a volatility gate that improved in-sample return in 30 of 35 fits made every p-value *worse* once swept — the sixfold grid cost more in correction than the gate returned.

**Know the price of a wider grid before you widen it.** On 2026-10-26 the gated and ungated sweeps ran against the same cached bars, and on the best candidate the sweep chose `volgate=0` — no gate — at every cost level. The winning strategy was therefore identical and the returns bit-identical, while p(SPA) went 0.014 → 0.035 and the result fell from "survives every cost level tested" to "gone by 50 bps". A 6x grid cost the most durable result in ~385 sweeps its cost robustness *without changing a single trade*. That is the multiple-comparisons correction measured in isolation, with nothing found to confound it — a rare clean number, and the one to weigh any grid-widening idea against.

**An unstable best-parameter is itself the verdict.** Across those 35 fits the winning gate threshold was near-uniform over the grid (5/9/4/2/7/8), and the value that motivated the whole test won least often. A parameter whose optimum scatters across independent fits is not measuring the market. That signal is cheaper and more convincing than the p-value.

**Why:** Across ~385 sweeps on the fitzz toolkit every single candidate died at one of these gates, and the expensive gates were the ones that found nothing new. Running them out of order wastes hours and, worse, builds confidence in an artifact.

**How to apply:** When a sweep returns something under 5%, do not report it as promising. Run the cost scan, then quote SPA *and* RC, the sweep count, and the holdout together, in that order. If a gate fails, say the candidate is dead — do not soften it. See [[fitzz-strategy-search-result]] and [[backtest-signal-design]].
