#!/usr/bin/env python3
"""
conf_family.py — the confluence parameter grid, as a sweep strategy family.

    python3 -m fitzz sweep --json bars.json \\
        --strategy fitzz/conf_family.py:build --objective return --cost-bps 10

Takes (close, bars): two of the five conditions read volume, so this needs
--json bars rather than a bare price series.

The grid sweeps `require` alongside the condition thresholds, because how
many votes to demand is the actual question. Insisting on all five is a
stricter filter, not a better one, and only a sweep can say whether the
strictness buys anything or merely starves the strategy of trades.
"""

import numpy as np

from fitzz.trading import confluence_flags

REQUIRE = (3, 4, 5)
EXIT_BELOW = (1, 2, 3)
SQUEEZE = (0.35, 0.6)
LOCATION = (0.5, 0.8)
RSI_BANDS = ((45.0, 70.0), (40.0, 80.0))


def build(close, bars):
    """Return (positions (T, K), labels) over the confluence grid."""
    n = len(bars)
    cache = {}
    for sq in SQUEEZE:
        for loc in LOCATION:
            for lo, hi in RSI_BANDS:
                cache[(sq, loc, lo, hi)] = confluence_flags(
                    bars, squeeze_pct=sq, location_max=loc,
                    rsi_lo=lo, rsi_hi=hi)[0]

    cols, labels = [], []
    for (sq, loc, lo, hi), counts in cache.items():
        for req in REQUIRE:
            for xb in EXIT_BELOW:
                if xb >= req:
                    continue          # would exit the bar it entered
                p = np.zeros(n, dtype=np.float32)
                state = 0.0
                for i in range(n):
                    if state > 0 and counts[i] < xb:
                        state = 0.0
                    if state <= 0 and counts[i] >= req:
                        state = 1.0
                    p[i] = state
                cols.append(p)
                labels.append(f"confluence req={req} exit<{xb} sq={sq:g} "
                              f"loc={loc:g} rsi={lo:g}-{hi:g}")
    return np.column_stack(cols), labels
