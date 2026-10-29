---
name: pooled-comparison-composition
description: A holdout does not catch a composition artifact — pooling groups that differ in both the feature and the outcome separates them every time, stably.
metadata:
  type: feedback
---

When comparing two outcome groups (winners vs losers, converted vs not) across a pooled set that mixes **kinds**, check composition before believing the result — and know that a holdout will not catch it.

The 2026-10-22 trade journal on the fitzz toolkit pooled 1,243 backtest trades across five strategy families. Five features separated winners from losers cleanly and **held out of sample**: entry z-score d = -0.351 in / -0.282 out, range location -0.339 / -0.329, trailing return, RSI, CMF, all negative — "winners entered after weakness". It looked like the only real finding of a long search.

It was composition. `mean_revert` enters at mean z = -2.56 and wins 71.5%; `breakout` enters at +2.32 and wins 43.7%. The pooled effect was "mean_revert trades win more often" restated in five correlated features. Two controls killed it: dropping `mean_revert` pushed z-score out of the top five entirely (best remaining d_in 0.171, holding at 0.018), and z-scoring each feature within its own family collapsed everything below 0.19.

**Why:** The out-of-sample check — my usual defence — passed cleanly, because group composition is stable across time. A holdout tests whether an effect persists, not whether it is the effect you think it is. Nothing in the standard gate sequence catches this.

**How to apply:** Before reading a pooled winner/loser comparison, tabulate the groups: n, outcome rate, and mean feature value per group. If the groups differ in both, the pooled number is measuring membership. Then run the two controls — drop the dominant group, and standardise within group — and report what survives both. See [[backtest-evidence-order]], [[backtest-signal-design]].
