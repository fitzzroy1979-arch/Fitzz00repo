#!/usr/bin/env python3
"""
analyze_draws.py -- is the Lotto Max draw fair, and are "hot" numbers real?

Reads the JSON written by fetch_draws.py and tests each ball's observed
frequency against the hypothesis that the machine is fair.

Why not just a chi-square table
-------------------------------
Two reasons the textbook test is the wrong tool here.

First, the 7 balls in a draw come out *without replacement*, so the per-number
counts are not independent -- the chi-square asymptotic distribution is close
but not exact. This script instead simulates the real mechanic (draw 7 of N,
repeat for the observed number of draws, 20k times) and reads the p-value off
that null. No approximation.

Second, and more important: with ~50 numbers in play, *something* is always
going to look hot. The maximum of 50 noisy counts is biased upward even when
every ball is equally likely. Reporting the hottest number's z-score on its own
invites exactly the wrong conclusion, so this script also reports how often a
fair machine produces a peak at least that extreme. Over three years of real
draws that figure is ~91%: the hottest number is what fairness looks like.

The pool size is read per-draw from fetch_draws.MATRIX, so eras with different
number ranges are weighted correctly instead of being pooled into nonsense.

Usage
-----
  # default: the 3 years ending today
  python3 lottomax/analyze_draws.py

  # a specific window, more simulations
  python3 lottomax/analyze_draws.py --end 2026-04-10 --window-days 1095 --sims 50000

  # what does capping your own picks at 49 actually cost?
  python3 lottomax/analyze_draws.py --cap 49
"""

import argparse
import datetime as dt
import json
import os
import sys
from math import comb

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_draws import BALLS_PER_DRAW, MATRIX, pool_for  # noqa: E402

K = BALLS_PER_DRAW


def segments(draws):
    """[(pool_size, n_draws)] for the eras present in `draws`."""
    counts = {}
    for d in draws:
        counts[pool_for(d["date"])] = counts.get(pool_for(d["date"]), 0) + 1
    return sorted(counts.items())


def moments(segs, pool_max, k):
    """Expected count and SD per number: a sum of without-replacement draws."""
    exp, var = np.zeros(pool_max), np.zeros(pool_max)
    for pool, n in segs:
        p = k / pool
        exp[:pool] += n * p
        var[:pool] += n * p * (1 - p)
    return exp, np.sqrt(var)


def chisq(obs, exp):
    return float(((obs - exp) ** 2 / exp).sum())


def tally(draws, pool_max, key):
    c = np.zeros(pool_max, dtype=int)
    for d in draws:
        for n in (d["main"] if key == "main" else [d["bonus"]]):
            c[n - 1] += 1
    return c


def test(name, segs, obs, k, sims, rng):
    """Monte-Carlo goodness-of-fit against a fair draw. Returns the p-value."""
    pool_max = max(p for p, _ in segs)
    exp, sd = moments(segs, pool_max, k)
    stat = chisq(obs, exp)

    null = np.empty(sims)
    peak = np.empty(sims)
    for s in range(sims):
        c = np.zeros(pool_max)
        for pool, n in segs:
            for _ in range(n):
                c[rng.choice(pool, size=k, replace=False)] += 1
        null[s] = chisq(c, exp)
        peak[s] = ((c - exp) / sd).max()

    p = float((null >= stat).mean())
    z = (obs - exp) / sd
    order = np.argsort(-z)
    fmt = lambda i: f"{i + 1} ({obs[i]}x, z={z[i]:+.1f})"
    n_tot = sum(n for _, n in segs)

    print(f"\n=== {name} ===")
    print(f"draws {n_tot}   pool 1-{pool_max}   balls/draw {k}   "
          f"expected per number {exp.min():.1f}-{exp.max():.1f}")
    print(f"chi-square {stat:.2f}   Monte-Carlo p {p:.4f}   (null mean {null.mean():.1f})")
    print(f"VERDICT  {'DEVIATES from a fair draw' if p < 0.05 else 'consistent with a fair draw'}")
    print("  most drawn  " + ", ".join(fmt(i) for i in order[:5]))
    print("  least drawn " + ", ".join(fmt(i) for i in order[-5:][::-1]))
    print(f"  peak is {z.max():+.1f} SD; a fair draw peaks that high or higher "
          f"{(peak >= z.max()).mean() * 100:.0f}% of the time")
    return p


def cap_report(cap, pool_max):
    """What restricting your own picks to 1..cap does to the odds. Spoiler: nothing."""
    full, restricted = comb(pool_max, K), comb(cap, K)
    print(f"\n=== capping your picks at {cap} (pool is 1-{pool_max}) ===")
    print(f"any specific 7-set from 1-{pool_max} : 1 in {full:,}")
    print(f"a 7-set drawn only from 1-{cap} : 1 in {full:,}")
    print(f"  P(draw lands entirely in 1-{cap}) = {restricted / full:.4f}")
    print(f"  P(your set | that happens)      = 1 in {restricted:,}")
    print(f"  the two cancel exactly: {restricted / full / restricted:.3e} "
          f"vs {1 / full:.3e}")
    print("  every lower tier is unchanged too -- the match distribution for a fixed")
    print("  7-set is hypergeometric and does not depend on WHICH numbers you pick.")
    print("  Number choice only affects how many others share a jackpot with you.")


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_argument_group("data")
    src.add_argument("--draws", default=os.path.join(here, "draws.json"),
                     help="draw JSON from fetch_draws.py (default: lottomax/draws.json)")
    win = p.add_argument_group("window")
    win.add_argument("--end", help="last draw date to include, YYYY-MM-DD (default: today)")
    win.add_argument("--window-days", type=int, default=3 * 365,
                     help="length of the window in days (default: 1095)")
    tst = p.add_argument_group("test")
    tst.add_argument("--sims", type=int, default=20000, help="Monte-Carlo simulations")
    tst.add_argument("--seed", type=int, default=20261015, help="RNG seed")
    tst.add_argument("--cap", type=int, metavar="N",
                     help="also price capping your own picks at 1..N")
    args = p.parse_args(argv)

    with open(args.draws, encoding="utf-8") as fh:
        all_draws = json.load(fh)

    end = dt.date.fromisoformat(args.end) if args.end else dt.date.today()
    start = end - dt.timedelta(days=args.window_days)
    draws = [d for d in all_draws
             if start <= dt.date.fromisoformat(d["date"]) <= end]
    if not draws:
        raise SystemExit(f"no draws between {start} and {end}")

    segs = segments(draws)
    pool_max = max(p_ for p_, _ in segs)
    rng = np.random.default_rng(args.seed)

    print(f"window {start} .. {end}   {len(draws)} draws")
    for pool, n in segs:
        era = [d for d in draws if pool_for(d["date"]) == pool]
        print(f"  pool 1-{pool}: {n} draws  {era[0]['date']} .. {era[-1]['date']}")

    for pool, n in segs:
        if len(segs) > 1:
            era = [d for d in draws if pool_for(d["date"]) == pool]
            test(f"main balls, 1-{pool} era", [(pool, n)], tally(era, pool, "main"),
                 K, args.sims, rng)

    test("main balls, whole window", segs, tally(draws, pool_max, "main"),
         K, args.sims, rng)
    test("bonus ball, whole window", segs, tally(draws, pool_max, "bonus"),
         1, args.sims, rng)

    if args.cap:
        cap_report(args.cap, pool_max)


if __name__ == "__main__":
    main()
