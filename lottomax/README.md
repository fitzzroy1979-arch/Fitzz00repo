# lottomax

Frequency and fairness testing on Lotto Max draw history. Standalone — not part
of the `fitzz` package, and not exported by `pyproject.toml`.

```bash
python3 lottomax/fetch_draws.py          # refresh draws.json
python3 lottomax/analyze_draws.py        # test the last 3 years
python3 lottomax/analyze_draws.py --cap 49
```

`fetch_draws.py` needs only the stdlib; `analyze_draws.py` needs numpy (already
a `fitzz` dependency).

## The one thing to know before touching this

The number pool is **not** constant across the history. Through the 2026-04-10
draw it was 7 balls from 1–50; from 2026-04-14 it is 7 from 1–52. Pool size is
therefore a lookup table, `MATRIX` in `fetch_draws.py`, and the analysis weights
each era separately. Pool the eras naively and 51/52 read as ice-cold purely
because they did not exist yet.

If the game changes again, add a `(first_draw_date, highest_ball)` row to
`MATRIX`. Until someone does, `fetch_draws.py` hard-errors on any ball outside
the declared range rather than writing a file that would skew the stats.

## Findings as of 2026-10-15 (313 draws)

| Test | Draws | χ² | p | Verdict |
|---|---|---|---|---|
| Main balls, 1–50 era | 260 | 32.5 | 0.89 | fair |
| Main balls, 1–52 era | 53 | 36.7 | 0.83 | fair |
| Main balls, combined | 313 | 29.4 | 0.97 | fair |
| Bonus ball, combined | 313 | 61.5 | 0.15 | fair |

No number deviates meaningfully. The hottest, 6, ran +1.9 SD (55 draws against
43.5 expected) — and a fair machine throws a peak at least that extreme 91% of
the time, because the max of 52 noisy counts is biased upward. All four χ²
values land *below* their null means; the spread is if anything tighter than
chance predicts.

Capping your own picks at 49 costs nothing: `1/C(52,7)` either way. Restricting
to 1–49 forfeits the 36% of draws containing a 50+, but conditional on the draw
landing in 1–49 your set is one of 85,900,584 rather than 133,784,560, and the
two effects cancel exactly. Lower tiers are unchanged too. Number choice only
moves *how many people share* a jackpot, which draw data cannot measure.

## Source

Per-year archive pages on lottomaxnumbers.com — an unofficial mirror. Spot-check
against the operator's own results before acting on anything.
