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

from fitzz.trading import confluence_positions

REQUIRE = (3, 4, 5)
EXIT_BELOW = (1, 2, 3)
SQUEEZE = (0.35, 0.6)
LOCATION = (0.5, 0.8)
RSI_BANDS = ((45.0, 70.0), (40.0, 80.0))


def _grid(close, bars, allow_shorts):
    cols, labels = [], []
    for sq in SQUEEZE:
        for loc in LOCATION:
            for lo, hi in RSI_BANDS:
                for req in REQUIRE:
                    for xb in EXIT_BELOW:
                        if xb >= req:
                            continue   # would exit the bar it entered
                        pos = confluence_positions(
                            bars, require=req, exit_below=xb,
                            allow_shorts=allow_shorts, squeeze_pct=sq,
                            location_max=loc, rsi_lo=lo, rsi_hi=hi)
                        cols.append(np.asarray(pos, dtype=np.float32))
                        labels.append(f"confluence req={req} exit<{xb} "
                                      f"sq={sq:g} loc={loc:g} rsi={lo:g}-{hi:g}"
                                      + (" short" if allow_shorts else ""))
    return np.column_stack(cols), labels


def build(close, bars):
    return _grid(close, bars, False)


def build_shorts(close, bars):
    return _grid(close, bars, True)
