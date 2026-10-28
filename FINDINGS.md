# Strategy search: results

What was tested, what was found, and what to not repeat. First written
2026-10-17; p-values re-measured on freshly fetched bars on 2026-10-20 and
again on 2026-10-26, so three independent pulls now stand behind the
candidate table.

## The result

Nothing tested here has a detectable edge on these symbols.

Five strategy families, long and short, eleven symbols, three timeframes,
four cost levels — roughly 140 significance sweeps over ~20,000 parameter
configurations each. Five results ever cleared p ≤ 0.05, and none of them
survived a second look:

| candidate | 10-17 | 10-20 | 10-26 | status |
|---|---|---|---|---|
| ZBCN mean_revert, 4h long | 0.021 | 0.018 | **0.016** | the one survivor; RC never clears (0.124 at best) |
| QNT mean_revert, 4h long | 0.031 | 0.046 | **0.019** | 0.103 once a third is held out; RC never clears |
| FLR confluence, 4h short | 0.033 | 0.030 | not re-run | RC 0.154; holdout 82% decayed; absent on unseen symbols |
| CC mean_revert, 4h short | 0.038 | 0.024 | **0.473** | holdout -0.000884; gone by 50 bps |
| ZBCN mean_revert, 1h short | 0.037 | not re-run | 0.018 gated | costs: gone by 25 bps |

Chance alone puts 5% of sweeps under p = 0.05 — about 7 of the ~140 run
here. Five hits is *below* what noise predicts, not above it. Finding a
handful of sub-5% results in a search this wide is the expected outcome of
searching, and the only honest reading of the table.

### The p-values are not stable

Three extra days of bars — about 18 of 1,500 at 4h, roughly 1% more data —
moved every candidate: QNT 0.031 → 0.046, CC 0.038 → 0.024, ZBCN 0.021 →
0.018, FLR 0.033 → 0.030. QNT nearly crossed out of significance and CC
nearly halved on a sample change too small to carry real information.

The third pull on 2026-10-26 says the same thing more loudly. QNT went
0.046 → **0.019**, a halving in the other direction on six days of data, and
CC collapsed from 0.024 to **0.473** — from apparently significant to
nothing, on a window that grew by 2%. Only ZBCN sat still, 0.021 → 0.018 →
0.016 across all three.

That instability is itself a result, and it argues the same way the holdouts
do. A p-value that swings 50% on 1% more data is measuring the particular
bars it was handed, not a property of the instrument. It also means any
single number in this document should be read as "about this, on that pull",
and a candidate that only ever sits near 0.05 is indistinguishable from one
sitting at 0.5.

### Three pulls in, only one candidate is reproducible

Of the five that ever cleared 5%, four move far enough between pulls to be
unreadable. ZBCN mean_revert at 4h long is the exception, and on 2026-10-26
it did something no other result here has managed — survived the cost scan at
**every** level with a positive holdout at each:

| bps | in-sample | holdout | p(SPA) | p(RC) |
|---|---|---|---|---|
| 10 | +0.000517 | +0.000051 | **0.014** | 0.124 |
| 25 | +0.000502 | +0.000193 | 0.016 | 0.137 |
| 50 | +0.000480 | +0.000166 | 0.019 | 0.155 |
| 100 | +0.000435 | +0.000111 | 0.023 | 0.191 |

The tool's own verdict is "survives every cost level tested". The other six
mean_revert pairs in the same run all lose significance by 10 bps, QNT among
them.

That is a real distinction and it should not be rounded down. Three
independent pulls, four cost levels, positive holdouts throughout, p(SPA)
never above 0.023. Nothing else in ~245 sweeps has that profile.

It is still not tradable, on the same two grounds as ever. **Reality Check
never clears it** — 0.124 at best, and when the two tests have split, the
conservative one has been right every time, including on candidates whose
holdouts looked better than this one's. And ZBCN is the least liquid
instrument in the set, so a modelled 10 bps round-turn is least believable
precisely where the edge appears. The honest summary is that the one result
that will not die is also the one whose cost assumption cannot be trusted.

### The one result costs do not kill

A cost scan across all five families on the six symbols at 4h — 30 pairs —
reports "significance is gone by 10 bps" for 29 of them. The exception is
ZBCN mean_revert, which holds SPA 0.011 at 10 bps and only reaches 0.021 at
100. Nothing else found here is cost-robust at all, so it deserves recording
rather than rounding down to "nothing worked".

It is still not tradable evidence:

* Reality Check never clears it — 0.093 at best on the fresh pull (0.117 on
  the first), at every cost level. The two tests have split on every candidate
  and the conservative one has been right each time.
* At the 10 bps winner specifically the holdout is -0.000002: nothing. The
  positive holdouts at 25–100 bps belong to a different, stricter config.
* One result from 30 sweeps is below the ~1.5 chance predicts.
* It appears on no other symbol, in either direction, at either timeframe.
* ZBCN is the thinnest instrument in the set. That is simultaneously why mean
  reversion is most plausible there — illiquid tokens overshoot and snap back
  — and why a modelled cost is least believable there.

### mean_revert across eleven symbols

Adding QNT gave mean reversion a second symbol under 5%, which is worth more
attention than one. The tally:

| | |
|---|---|
| clears 5% on SPA, full window | **2** — ZBCN 0.018, QNT 0.046 |
| clears Reality Check | **0** — best is 0.093 |
| fails | 9 — BTC, XRP, FLR, CC, HBAR, SOL, ADA, LINK, DOT |

Two of eleven, against ~1.8 expected by chance across 35 sweeps. Both are
thin, low-liquidity tokens, which cuts both ways: mean reversion is most
plausible where price overshoots and snaps back for want of a tight market,
and that is exactly where a modelled 10 bps round-turn is least believable.

QNT's holdout is better behaved than most — positive at every cost level,
reaching roughly zero only at 100 bps — but its p-value falls from 0.031 to
0.127 as soon as a third of the data is reserved, so the significance was
coming from the full window rather than from the signal. On the fresh pull it
starts from 0.046 instead, which is the kind of movement described above.

### What the scan shows about everything else

Nearly every one of the 30 pairs posts a healthy in-sample edge, +0.0001 to
+0.0006 per bar, with a **negative holdout**. In-sample positive and
out-of-sample negative, repeated across 30 independent symbol/family pairs,
is the clearest single picture of what a parameter search does to this data.

### The same scan with shorts enabled

Re-run 2026-10-20 on fresh bars, all five families across the seven-symbol
watchlist — 35 pairs. **34 lose significance by 10 bps.** The one exception is
CC mean_revert, clearing at 10 bps (0.024) and 25 bps (0.048) and gone by 50,
with a holdout of **-0.000884** — it fails on untouched data before cost is
even the question.

So enabling shorts removes the single cost-robust result the long-only scan
had. The largest in-sample edges in the whole shorts run, with their holdouts:

| pair | in-sample @ 10 bps | holdout |
|---|---|---|
| HBAR ma_cross | +0.000840 | -0.000191 |
| ZBCN ma_cross | +0.000654 | -0.000225 |
| FLR ma_cross | +0.000653 | +0.000136 |
| HBAR breakout | +0.000638 | -0.000040 |
| XRP ma_cross | +0.000624 | +0.000367 |

Every one is noise by p-value (0.273–0.809) and most flip negative out of
sample. QNT breakout is the inverse case — +0.000200 in sample against
+0.000641 held out, at p 0.642–0.706 — which is the same luck read from the
other end.

## What was tested

| family | idea | long-only result |
|---|---|---|
| `sma_cross` | fast MA crosses slow | beats hold on 4/6 |
| `follow_money` | big buy-side volume + sustained accumulation | beats hold on 5/6 |
| `breakout` | Donchian channel | beats hold on 5/6 |
| `mean_revert` | buy statistically depressed prices | beats hold on 5/6 |
| `confluence` | N of five independent conditions agree | beats hold on 1/6 |

Every one of those backtest headlines is noise. The sweep says so for all
five, which is the point of having it.

Symbols: BTC, XRP, FLR, ZBCN, CC (Canton), HBAR, QNT, plus SOL, ADA, LINK,
DOT as out-of-sample. Timeframes: 1d, 4h, 1h. Costs: 10, 25, 50, 100 bps.

QNT is worth keeping in the set as a counterexample: over eight years it rose
155% while sma_cross finished at -1.97% with a 79% drawdown. Every other
symbol either trends enough for a trend follower to beat holding, or falls
far enough that sitting in cash looks like skill. QNT does neither.

## Things worth remembering

**Win rate says nothing.** `mean_revert` wins 64–74% of trades and loses
money; the trend followers win ~40% at a 3.9x payoff and also lose money.
Opposite shapes, same verdict. Two strategies failing for opposite reasons is
stronger evidence than three trend followers failing together.

**Confluence is a filter, not a generator.** Requiring more conditions to
agree reduces trade count and leaves expectancy flat. Going from 3-of-5 to
5-of-5 cut trades from 172 to 12 across six symbols and changed nothing else.
A filter can remove false signals from a signal that has edge; it cannot
manufacture edge.

**Redundant signals flatter a backtest.** The first confluence build used
five conditions of which three answered "is price going up" (trend/momentum
correlated at +0.45). It returned +4,250% on BTC. Rebuilding the five to
measure genuinely different dimensions — direction, momentum, volatility
regime, participation, location — dropped that to +165%. The redundancy was
a trend follower in disguise, and the trend is what paid.

**A positive holdout alone proves nothing.** HBAR/breakout holds +0.000241
out of sample with a *negative* in-sample edge and p = 1.000. When the
in-sample winner is worse than the null's median, the holdout is 1,650 bars
of luck. Only read a holdout for a candidate whose p-value was low first.

**Ask the cost question first.** `--cost-scan` disqualified the best
candidate of the session in one step, and it is cheaper than a significance
sweep. "What does this need to cost to work?" is a fact about the instrument.
An edge needing 10 bps round-turn on a thin small-cap pair is ruled out by
the spread it will actually pay, whatever its p-value says.

**Shorts did not help.** On six symbols only FLR improved. ZBCN also fell
over the window and shorting it took -2.68% to -88.73% at a 96% drawdown — it
declined by chopping rather than trending, so every false signal cost twice.
A falling asset is not a shortable one. Under the cost scan it is worse than
neutral: 34 of 35 pairs lose significance by 10 bps with shorts on, against
29 of 30 long-only, and the one long-only result that survived cost does not
survive the addition.

**SPA and Reality Check usually disagreed, and agreement means nothing
either.** SPA 0.021 against RC 0.113; SPA 0.035 against RC 0.154; SPA 0.037
against RC 0.099. When they split, the conservative one was right every time.

Read that as a fact about RC being stricter, not as a reason to trust
agreement. On 2026-10-27, QNT mean_revert 1h short cleared **both** -- SPA
0.009 and RC 0.047 at 10 bps -- and its holdout was **-0.000673**, negative
at every cost level and three times the in-sample edge with the sign
reversed. Both tests agreed and both were wrong.

They were always going to be. SPA and Reality Check are two corrections of
the *same in-sample quantity* for the *same* grid search; neither can see
data that was never searched. They are not two opinions, and two of them
agreeing is one piece of evidence, not two. Only the holdout is looking
somewhere else, which is why it stays in the sequence after them rather than
being replaced by them.

## What the losing trades have in common

Added 2026-10-22, after the question was put directly: learn from the bad
trades so the same ones are not taken again. `fitzz/journal.py` logs every
round trip of a winning config with nine readings of the tape at its entry —
trend distance and slope, RSI, bandwidth percentile, volume ratio, CMF, range
location, z-score, trailing 5-bar return — and measures how far apart the
winning and losing entries sit, in pooled standard deviations (Cohen's d).

Mining losers for a pattern is the most reliable way to overfit there is, so
every separation is measured on the first two thirds of trades and re-checked
on the last third. `--journal` on the runner prints both columns;
`--journal-dump` writes the trades to JSON.

Across 1,243 trades, five families, seven symbols at 4h:

**4 of 45 family/feature pairs separate in-sample and hold out of sample**,
and no two families agree on which. breakout/CMF, confluence/RSI,
follow_money/trend-slope, ma_cross/bandwidth — scattered, all d ≈ 0.2–0.4
in-sample, nothing a filter could be built on.

### The pooled result is a composition artifact

Pool all 1,243 trades and five features separate cleanly and hold out of
sample — z-score -0.351/-0.282, range location -0.339/-0.329, trailing
return -0.306/-0.343, RSI -0.293/-0.215, CMF -0.206/-0.171. All negative:
winners entered after weakness. It looks like the session's one real finding.

It is not. The pool mixes families that enter at opposite ends of every one
of those scales:

| family | trades | win rate | mean z-score at entry |
|---|---|---|---|
| mean_revert | 207 | 71.5% | **-2.56** |
| confluence | 211 | 48.3% | -0.12 |
| ma_cross | 361 | 38.8% | +0.85 |
| follow_money | 258 | 42.6% | +1.22 |
| breakout | 206 | 43.7% | **+2.32** |

So "winners entered low" is "mean_revert trades win more often" restated —
and mean_revert loses money at a 71.5% win rate, which is the oldest lesson
in this document. Two controls confirm it: drop mean_revert and z-score
leaves the top five entirely (best remaining d_in 0.171, holding at 0.018);
z-score each feature within its own family before pooling and every effect
collapses below 0.19.

**This is the shape to watch for.** A pooled comparison across groups that
differ in both the feature and the outcome will separate them every time, and
it survives a holdout, because composition is stable across time. The holdout
does not catch this one. Only the control does.

### The one thing left

Bandwidth percentile at entry — the volatility regime — is the only feature
that keeps its sign and rough size in all three views: pooled (+0.188/+0.104),
pooled excluding mean_revert (+0.118/+0.114), and z-scored within family
(+0.182/+0.121). Winners were entered when the market was moving. That is not
a price prediction; it is "these are all breakout and trend strategies and
they need movement to pay".

Refusing entries below the 40th percentile of bandwidth raises mean per-trade
return in four of five families, in-sample **and** out:

| family | holdout mean/trade, unfiltered | at thr 0.4 |
|---|---|---|
| confluence | +3.25% | +7.84% |
| ma_cross | +2.67% | +4.61% |
| follow_money | +3.61% | +5.54% |
| breakout | +2.83% | +4.47% |
| mean_revert | +0.93% | +0.78% |

First thing all session to improve out of sample. Three reasons it is not yet
a result: total return falls at every threshold, because the filter removes
more good trades than bad; the effect is **non-monotone** out of sample —
breakout's holdout mean goes 4.47% at 0.4 to 0.08% at 0.5 and back to 0.61%
at 0.6, and ma_cross 4.90% to 0.31% — which is what noise looks like and not
what a regime effect looks like; and d ≈ 0.15 means the winning and losing
distributions overlap by about 94%.

### Settled: the gate helps only where it is shorting, and not enough

`fitzz/gated_family.py` crosses all five families with the gate, sweeping the
threshold over 0/0.2/0.3/0.4/0.5/0.6 instead of choosing it. The gate is
tested once, at entry, and a trade already open is seen through -- that is the
hypothesis the journal measured. **0.0 is in the grid**, so the ungated family
competes inside the same correction and a gated winner has to beat the version
of itself that never refused a trade. `--vol-gate` on the runner.

#### Long-only: what the gate costs, with the strategy held fixed

Run 2026-10-26, gated and ungated against the *same cached bars*. On ZBCN
mean_revert -- the only reproducible result in this search -- the sweep
examined all six thresholds and chose **`volgate=0`**, no gate, at every cost
level. So the winning strategy is identical in the two runs, bar for bar, and
the only difference between the columns below is that one grid is six times
larger than the other:

| bps | in-sample | holdout | SPA ungated | SPA gated | RC ungated | RC gated |
|---|---|---|---|---|---|---|
| 10 | +0.000517 | +0.000051 | **0.014** | 0.035 | 0.124 | 0.148 |
| 25 | +0.000502 | +0.000193 | 0.016 | 0.045 | 0.137 | 0.162 |
| 50 | +0.000480 | +0.000166 | 0.019 | **0.054** | 0.155 | 0.186 |
| 100 | +0.000435 | +0.000111 | 0.023 | 0.074 | 0.191 | 0.243 |

The returns are bit-identical at all four cost levels. Nothing about the
strategy changed. And that alone moved ZBCN from the tool's *"survives every
cost level tested"* to *"significance is gone by 50 bps"*, with p(SPA) up by a
factor of 2.5. Over the whole run, lowest p(SPA) 0.016 → 0.047, significant
sweeps 2 → 1, QNT mean_revert 0.019 → 0.060.

**This is the price of looking, measured on its own.** Usually a wider search
is entangled with whatever the search found, and the two cannot be separated.
Here the search found nothing -- it rejected the gate outright -- so the entire
p-value movement is the multiple-comparisons correction and nothing else. A
6x grid cost the best result in ~280 sweeps its cost robustness without
changing a single trade. Any future idea that widens a grid should be read
against this number before it is read against its own backtest.

#### With shorts, the gate does help -- and it is still not enough

Run 2026-10-26 on the same bars with `--shorts`. Here the sweep chose
**`volgate=0.5`**, so for once the gate beat the ungated competitor inside its
own grid, and it improved every column it touched:

| bps | SPA ungated | SPA gated | holdout ungated | holdout gated |
|---|---|---|---|---|
| 10 | 0.140 | **0.088** | +0.000104 | **+0.000590** |
| 25 | 0.174 | 0.109 | +0.000059 | +0.000541 |
| 50 | 0.244 | 0.153 | -0.000017 | +0.000459 |
| 100 | 0.381 | 0.320 | -0.000134 | +0.000296 |

Lower p at all four cost levels, in-sample +0.000435 -> +0.000592, and a
holdout 5.7x better that stays positive at 100 bps where the ungated version
has gone negative. **So "the gate never helps" is wrong** -- an earlier draft
of this section said so, and the long-only runs are the reason. It does not
help long. It helps short.

A mechanism fits ZBCN in particular. It fell over this window by chopping
rather than trending, which is why shorting it was so punishing in the first
place; shorting a mean reversion into a dead-volatility regime has no
snap-back to collect, so refusing those entries removes a subset of trades
that is genuinely bad rather than merely unlucky.

And it is still nothing. Full-window SPA was 0.011; with a third reserved it
is **0.088**, and RC is **0.419**. By this document's own rule a holdout is
only readable after a low p-value, and 0.088 is not one. The gate turns a
non-result into a better-looking non-result.

Worth recording what makes it the most seductive row here: in-sample
+0.000592 against a holdout of +0.000590 is **99.7% retention**, the best in
the entire search, decaying gracefully to +0.000296 at 100 bps. That is the
profile a real edge has. It is also what p = 0.088 means when the winner was
picked from ~594 configs, which is exactly why the gate sequence exists and
why the holdout is read last.

#### The earlier runs said the same thing less cleanly

Run 2026-10-22, on that pull's bars, the gate won the grid **30 times out of
35**. It does improve in-sample return, just as the journal said. And it still
made everything worse:

| | ungated | gated |
|---|---|---|
| lowest p(SPA) over 35 sweeps | 0.018 | **0.023** |
| sweeps significant at 5% | 2 | **1** |
| QNT mean_revert | 0.046 | **0.127** |

With a third of the data held out and costs charged, the one survivor goes
the same way — ZBCN mean_revert, which ungated held SPA 0.011 at 10 bps:

| bps | in-sample | holdout | p(SPA) | p(RC) |
|---|---|---|---|---|
| 10 | +0.000517 | -0.000032 | **0.056** | 0.137 |
| 25 | +0.000502 | +0.000111 | 0.058 | 0.150 |
| 50 | +0.000480 | +0.000085 | 0.070 | 0.170 |
| 100 | +0.000435 | +0.000034 | 0.096 | 0.228 |

It no longer clears 5% at any cost level. QNT gated sits at 0.230. The gate
multiplied each grid roughly sixfold -- ma_cross went from 3,339 configs to
about 20,000 -- and the correction for that search costs more than the gate
returns. An improvement that cannot pay for the cost of having looked for it
is not an improvement.

**The tell was in the thresholds.** If a volatility regime genuinely marked
bad entries, the winning threshold would cluster. It does not:

| threshold | times it won |
|---|---|
| 0.0 (no gate) | 5 |
| 0.2 | 9 |
| 0.3 | 4 |
| 0.4 | 2 |
| 0.5 | 7 |
| 0.6 | 8 |

Near-uniform across the grid, and 0.4 -- the value the journal pointed at --
is the *rarest* winner of the five gates. Each symbol and family found
whichever threshold happened to delete its own worst trades. That is what
fitting looks like from the inside, and it is worth more than the p-value:
a parameter whose best value is unstable across 35 independent fits is not
measuring anything about the market.

So the journal's one surviving lead is closed. It was a real in-sample
effect, reproducible, directionally consistent across families and holdouts
-- and still nothing, once made to pay for itself.

### Gated, with shorts

Run 2026-10-22, `--vol-gate --shorts`, same 35 pairs. This produced the
**lowest p(SPA) of the entire search**: ZBCN mean_revert at 0.007, with the
block check passing. Its Reality Check was 0.203.

Reserve a third of the data and it is 0.124:

| bps | in-sample | holdout | p(SPA) | p(RC) |
|---|---|---|---|---|
| 10 | +0.000590 | +0.000552 | **0.124** | 0.422 |
| 25 | +0.000558 | +0.000505 | 0.164 | 0.468 |
| 50 | +0.000505 | +0.000426 | 0.231 | 0.544 |
| 100 | +0.000399 | +0.000268 | 0.436 | 0.700 |

0.007 to 0.124 on the same data, the only difference being that a third of
the window was withheld from the search. The significance was the full
window, not the signal.

Worth noting what is unusual here, because it is the most seductive row in
this document: the holdout is **positive at every cost level** and decays
gracefully rather than collapsing. That is the profile a real edge would
have. It is also what p = 0.124 and RC = 0.422 mean in practice -- out of
~20,000 configs, the best one on a third of the data looking decent on the
rest is roughly what noise produces. This is precisely the case the earlier
rule was written for: a holdout is only readable after a p-value is low, and
this one is not. The second candidate behaves the same way -- FLR confluence
shorts, holdout +0.000246 at 10 bps, SPA 0.139, never clearing.

The threshold scatter repeats, and the no-gate option wins more often with
shorts than it did long-only:

| threshold | long-only | with shorts |
|---|---|---|
| 0.0 (no gate) | 5 | **11** |
| 0.2 | 9 | 8 |
| 0.3 | 4 | 3 |
| 0.4 | 2 | 3 |
| 0.5 | 7 | 6 |
| 0.6 | 8 | 4 |

Given a free choice in the same grid, 11 of 35 fits now prefer no gate at
all. Two independent runs, both scattered, with the mode moving between them.
The gate is closed in both directions.

### Gated, 1h — the only time both tests ever agreed

Run 2026-10-22, `--vol-gate --interval 1h`, long-only, 35 pairs. ZBCN
mean_revert returned **SPA 0.004 and Reality Check 0.034**, block check
passing. That is the one and only occasion in this entire search that RC fell
below 5%. Reality Check is the test that has killed every candidate, and it
had never gone below 0.093 before.

It does not survive a holdout either:

| bps | in-sample | holdout | p(SPA) | p(RC) |
|---|---|---|---|---|
| 10 | +0.000178 | **+0.000184** | 0.040 | 0.107 |
| 25 | +0.000136 | +0.000093 | **0.205** | 0.290 |
| 50 | +0.000111 | +0.000025 | 0.376 | 0.418 |
| 100 | +0.000069 | -0.000005 | 0.650 | 0.786 |

Reserve a third and RC goes from 0.034 to 0.107 — the clearance was the full
window. Give it full credit for what it does do, because nothing else here
has: at 10 bps the holdout is **+0.000184 against an in-sample +0.000178**.
Not merely positive, not merely gracefully decaying — *identical*, no decay at
all, which is what a genuine edge looks like and what no other row in this
document shows.

And it is still dead, on the question that should have been asked first.
Significance is gone by 25 bps, and the trades say why: at 1h the winners
average +1.5% and the losers -1.7%. A 10 bps round turn is 0.2% — 13% of the
average winner. At 25 bps it is a third of it. ZBCN is the least liquid
instrument in the set; its real round-turn cost at 1h is not 10 bps. The edge
exists only at a cost that cannot be obtained on the only instrument that has
it.

Note the shorter calendar window: 5,000 bars at 1h is about 208 days against
833 at 4h, so this is one regime rather than several, which is its own reason
for caution regardless of the p-value.

### Gated, 1h, with shorts, on fresh bars

Re-run 2026-10-27 on newly fetched 1h bars, with an ungated-shorts control on
the same bars. Lowest p(SPA) 0.025 (ZBCN, RC 0.054), 2 of 35 under 5%.

The gate split by symbol, which neither earlier run showed so plainly:

* **ZBCN chose `volgate=0.2`** -- a light gate that barely changes the returns
  (+0.000274 gated against +0.000271 ungated) yet improves the p-value at
  every cost level, most at the costs that matter: 0.085 → 0.072 at 10 bps,
  0.221 → 0.108 at 25, 0.418 → 0.234 at 50. Still gone by 10 bps on the 5%
  line.
* **QNT chose `volgate=0`**, and the search-cost penalty reappears exactly as
  in the long-only case: identical returns, SPA 0.009 → 0.024 from the 6x
  grid alone.

So across five gated runs the gate is chosen roughly half the time, helps
slightly when chosen, and costs a factor of 2-3 in p-value when it is not.
Neither outcome has produced a tradable result.

QNT's row in that control is the one worth keeping, and it is written up
under *Things worth remembering*: ungated it cleared **both** tests at 10 bps
-- SPA 0.009, RC 0.047 -- with a holdout of **-0.000673**. It is the second
time RC has gone below 5% in ~350 sweeps, and the only time both tests have
cleared together. They were both wrong.

### Gated, 1h, with shorts — and the scatter completed

Run 2026-10-22, the fourth corner. ZBCN mean_revert again, SPA 0.018 and RC
0.056, over 426 trades. Adding shorts made it worse than long-only on both
tests (0.004 and 0.034), consistent with everything else here: shorts have
never improved a candidate in this search.

With a third held out it behaves exactly as the long-only version did:

| bps | in-sample | holdout | p(SPA) | p(RC) |
|---|---|---|---|---|
| 10 | +0.000282 | +0.000221 | 0.042 | 0.108 |
| 25 | +0.000244 | +0.000182 | **0.067** | 0.189 |
| 50 | +0.000180 | +0.000117 | 0.172 | 0.422 |
| 100 | +0.000053 | -0.000054 | 0.826 | 0.964 |

SPA clears at 10 bps, RC does not, gone by 25. The full-window RC of 0.056
becomes 0.108 once a third is reserved — the same lesson as the long-only
run: **every RC clearance this search has produced came from the full
window.** Holdout retention is again good, 78% of the in-sample edge.

**All four corners of the gate, and the scatter is complete:**

| threshold | 4h long | 4h shorts | 1h long | 1h shorts |
|---|---|---|---|---|
| 0.0 (no gate) | 5 | **11** | 3 | 7 |
| 0.2 | **9** | 8 | 4 | 4 |
| 0.3 | 4 | 3 | 6 | 4 |
| 0.4 | 2 | 3 | 7 | 3 |
| 0.5 | 7 | 6 | **10** | 5 |
| 0.6 | 8 | 4 | 5 | **12** |

Four independent runs of 35 fits each, four different modes — 0.2, 0.0, 0.5,
0.6 — spanning the whole grid end to end, and 0.4, the value the journal
pointed at, is a mode in none of them. 140 fits chose a threshold and no two
runs agreed on what it should be.

That is the strongest single argument against the gate, and a better one than
any p-value: across 140 fits the parameter has no stable optimum, so there is
mostly nothing there to optimise.

**Mostly** is the honest word, and it is a narrowing of what an earlier draft
claimed. The shorts case above is a real exception -- there the gate was
chosen over no-gate, lowered p at every cost level and improved the holdout
5.7x. The scatter says the threshold is noise *on average across 140 fits*,
not that it is noise everywhere. Where the gate does bite, it still produced
p = 0.088 and RC = 0.419, so the conclusion is unchanged even where the
reasoning for it is.

The journal found a real in-sample pattern, the sweep priced it, and in the
one configuration where the pattern survived pricing it was still not worth
enough to clear.

## Settled: neither flow predicts anything

The two feeds in `fitzz flows` were the last untested direction — the one
place to look that is not a function of price and volume. Both were tested
the same way, against BTC weekly returns, and both came back empty.

### CFTC positioning describes the week that just happened

CME Bitcoin legacy futures-only, 446 weekly reports, 2018-04-10 to
2026-10-20, 444 aligned observations. Positions are as of Tuesday and
published the Friday after, so everything is measured **from the release
close forward**; aligning on the as-of date instead would be reading
Tuesday's positions at Tuesday's price, which no trader could do.

| feature | vs next week | t | vs week just past | t |
|---|---|---|---|---|
| commercial net change (w/w) | +0.013 | +0.275 | **+0.132** | **+2.792** |
| commercial net level | +0.036 | +0.763 | +0.086 | +1.818 |
| commercial net / open interest | +0.046 | +0.964 | **+0.104** | **+2.209** |
| non-commercial net level | −0.085 | −1.791 | **−0.153** | **−3.264** |

Every forward reading is inside noise; three of the four backward readings
are not. The feed carries real information about the week that has already
happened and none about the week ahead. The largest forward number
(speculator net, t = −1.791, p ≈ 0.07) is one of four features tested, which
is where one such reading is expected.

The quintile table says the same thing by not ordering. The best next-week
mean sits in the **fourth** bucket, not an extreme:

| commercial net change | n | mean next week | up |
|---|---|---|---|
| −1943 .. −236 | 88 | +0.88% | 46.6% |
| −232 .. −8 | 89 | +0.32% | 51.7% |
| −8 .. +2 | 89 | −0.16% | 51.7% |
| +3 .. +201 | 89 | **+2.81%** | 61.8% |
| +212 .. +1917 | 89 | +0.59% | 51.7% |

This replaces the earlier −0.009 / +0.205 figures, which came from a smaller
sample. Same conclusion, properly sized.

### SEC filing counts describe nothing at all

Weekly EDGAR full-text hit counts for three queries, 2018–2026, against the
same weekly returns. Filings dated Mon..Sun are all public by Sunday, so the
feature is known at the last close ≤ Sunday and the forward return runs from
there. **Twelve looks were declared before the run** — 3 queries × 2 feature
forms × 2 directions — of which the 6 forward ones are the hypothesis and the
6 backward ones a control. Chance expectation at 0.05 is 0.3 forward hits;
with n ≈ 450 an |r| below about 0.094 cannot clear 2 sigma at all.

| query | feature | vs next week | t | vs week just past | t |
|---|---|---|---|---|---|
| `bitcoin` | count change (log w/w) | +0.008 | +0.181 | −0.006 | −0.119 |
| `bitcoin` | count z-score (26w) | +0.034 | +0.721 | +0.023 | +0.493 |
| `"bitcoin treasury"` | count change (log w/w) | +0.039 | +0.782 | −0.048 | −0.970 |
| `"bitcoin treasury"` | count z-score (26w) | +0.014 | +0.249 | −0.034 | −0.628 |
| `cryptocurrency` | count change (log w/w) | −0.008 | −0.173 | +0.042 | +0.901 |
| `cryptocurrency` | count z-score (26w) | +0.013 | +0.281 | +0.030 | +0.623 |

Nothing reaches |t| = 1.5 in either direction. 1,377 weekly requests, zero
fetch failures.

This is a **stronger null than the CFTC result**, and the difference is the
interesting part. Positioning at least described the week just past; filing
counts do not even do that. Counting how often a word appears in EDGAR
measures filing season and disclosure fashion, not the market.

Three things kept the test honest, each of which would have manufactured a
result on its own:

* **The feature is a change or a z-score, never the raw count.** Crypto
  mentions grew from 6 a week to 1,344 while the price also rose; correlating
  two rising series measures the trend. The raw level is in the output,
  flagged, and not counted among the twelve looks — it reads −0.041 to −0.057
  forward, which is the trend, not a signal.
* **Counts come from EDGAR's `total` for a one-week window, one request per
  week.** Paging the filings and bucketing them locally would be far fewer
  requests and would not work: the endpoint refuses offsets past ~10,000, so
  a locally-bucketed eight-year series would silently be a truncated one.
  That is the bug in the entry below, and designing around it is the only
  reason this series is trustworthy.
* **A phrase is zero before it is coined.** `"bitcoin treasury"` is unused
  until 2019-01-28; 56 leading weeks were dropped rather than fed to a
  log-change over a run of zeros. Even so its median weekly count is 0, so
  its three middle quintiles are all exactly zero and its quintile table
  carries no information — the correlations above are computed over the real
  spread, but that query's bucket view should be ignored.

## Data bugs found along the way

Eight, all the same shape: a read that was short, stale or simply another
symbol's, passing as valid. Each silently changed results rather than
erroring.

1. `ensure_history` stopped paging on the first `requestMoreDataAvailable()
   false`, which also reads false mid-fetch. HBAR ran on 1,300 of 1,466 bars
   and overstated its return by 69 points.
2. `load_bars` reported a truncated read and a genuinely short feed with the
   same message, so neither caller nor human could tell them apart.
3. The chart reports a new symbol before its data repaints; a 4h CC read came
   back holding BTC's series.
4. The same for timeframes: a daily CC request returned its 1,482-bar 4h
   series.
5. Two processes driving one chart interleave their symbol switches and each
   gets the other's bars. Now an flock, so the second one errors.
6. The sweep cache re-read any short series every run and took the longer of
   the two, so one cross-symbol read overwrote good CC data with BTC's.

7. `trade_stats` walked only `col[i] > 0`, so under `--shorts` it counted
   the long legs and reported them as the whole strategy. Every win rate and
   payoff figure from a shorts run before 2026-10-22 describes half the
   trades. It now shares `fitzz.journal`'s extractor with the journal, so the
   two cannot disagree about what a trade is.
8. `fetch_sec_filings` read one EDGAR response and its own docstring asserted
   that response was the complete result set, which made sorting by date
   safe. EDGAR returns 100 hits ranked by *relevance*, so `--sort date
   --limit 20` gave "the 20 newest of the 100 most relevant" while reading
   exactly like "the 20 newest". On `bitcoin treasury` since January it
   called 2026-10-19 the newest filing; paging finds 2026-10-23 and
   2026-10-21 ahead of it. It hid the newest filings behind the word
   "newest". It now pages with `from` until it has every match or
   `--max-rows`, and returns `complete` so a caller can tell a full ordering
   from a partial one. The commit message for 2d7d67d calls this the seventh
   bug of this shape; counting this list, it is the eighth.

Guards now check the data rather than the chart's description of itself: bar
count against confirmed depth, price against a live quote, bar spacing
against the requested interval, and a lock against concurrent readers.

## What would actually change the answer

Not more sweeps on this data — it is measured out. And not the flows either:
both are now tested and neither predicts next week, so the "signal that is not
a function of price and volume" direction has been tried and closed with the
rest.

What is left is genuinely outside what this repo can reach:

* **A different market.** Everything here is crypto through one 2024–2026
  regime, eleven symbols that largely move together. Equities, rates or
  commodities over several decades would be a new test rather than another
  look at the same data.
* **A faster clock.** Every edge found here died at 10 bps of cost. Intraday
  or microstructure work is where costs can be cleared, and it needs
  execution data this project does not have.
* **A non-count use of the filings.** Counting how often a word appears was
  the cheap test and it failed. Reading *what the filings say* — a specific
  disclosure by a specific filer — is a different question, and one that
  eight years of weekly hit totals cannot answer either way.

None of these is a refinement of the current search; each is a new project.
The honest summary of this one is that it measured its space and found
nothing tradable in it.
