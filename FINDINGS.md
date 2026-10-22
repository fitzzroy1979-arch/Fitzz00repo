# Strategy search: results

What was tested, what was found, and what to not repeat. First written
2026-10-17; p-values re-measured 2026-10-20 on freshly fetched bars (through
2026-10-20 04:00) after clearing the cache.

## The result

Nothing tested here has a detectable edge on these symbols.

Five strategy families, long and short, eleven symbols, three timeframes,
four cost levels — roughly 140 significance sweeps over ~20,000 parameter
configurations each. Five results ever cleared p ≤ 0.05, and none of them
survived a second look:

| candidate | p(SPA) 10-17 | p(SPA) 10-20 | status |
|---|---|---|---|
| ZBCN mean_revert, 4h long | 0.021 | **0.018** | RC 0.117 → 0.093; holdout at that config +0.000517 → **-0.000002** per bar |
| QNT mean_revert, 4h long | 0.031 | **0.046** | drops to 0.127 once a third is held out; RC never clears |
| FLR confluence, 4h short | 0.033 | **0.030** | RC 0.154; holdout 82% decayed; absent on unseen symbols |
| CC mean_revert, 4h short | 0.038 | **0.024** | holdout **-0.000884**; gone by 50 bps |
| ZBCN mean_revert, 1h short | 0.037 | not re-run | costs: gone by 25 bps, holdout -0.000001 at 100 |

Chance alone puts 5% of sweeps under p = 0.05 — about 7 of the ~140 run
here. Five hits is *below* what noise predicts, not above it. Finding a
handful of sub-5% results in a search this wide is the expected outcome of
searching, and the only honest reading of the table.

### The p-values are not stable

Three extra days of bars — about 18 of 1,500 at 4h, roughly 1% more data —
moved every candidate: QNT 0.031 → 0.046, CC 0.038 → 0.024, ZBCN 0.021 →
0.018, FLR 0.033 → 0.030. QNT nearly crossed out of significance and CC
nearly halved on a sample change too small to carry real information.

That instability is itself a result, and it argues the same way the holdouts
do. A p-value that swings 50% on 1% more data is measuring the particular
bars it was handed, not a property of the instrument. It also means any
single number in this document should be read as "about this, on that pull",
and a candidate that only ever sits near 0.05 is indistinguishable from one
sitting at 0.5.

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

**SPA and Reality Check disagreed on every candidate.** SPA 0.021 against RC
0.113; SPA 0.035 against RC 0.154; SPA 0.037 against RC 0.099. When they
split, the conservative one was right every time.

## Data bugs found along the way

Six, all the same shape: a read that was short, stale or simply another
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

Guards now check the data rather than the chart's description of itself: bar
count against confirmed depth, price against a live quote, bar spacing
against the requested interval, and a lock against concurrent readers.

## What would actually change the answer

Not more sweeps on this data — it is measured out. Either a different market
(everything here is crypto through one 2024–2026 regime), or a signal that is
not a function of price and volume. The CFTC and SEC feeds in `fitzz flows`
are the untested direction, though commercial positioning already measured as
lagging price (-0.009 correlation with next-week returns, +0.205 with the
week just past).
