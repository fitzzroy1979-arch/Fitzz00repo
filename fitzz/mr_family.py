#!/usr/bin/env python3
"""
mr_family.py — the mean_revert parameter grid, as a sweep strategy family.

    python3 -m fitzz sweep --json bars.json \\
        --strategy fitzz/mr_family.py:build --objective return --cost-bps 10

`build` is long-only; `build_shorts` also sells the overbought stretch.
Both delegate to mean_revert_positions, the same function the backtest
uses, so the grid cannot drift from the strategy it claims to be testing.

Mean reversion is the one family here that is not a trend follower. If the
trend followers all fail on the same symbols, a shared reason is likelier
than several separate ones -- they are the same bet in different clothes.
This grid asks whether the opposite bet does any better on the same data.
"""

import numpy as np

from fitzz.trading import mean_revert_positions

WINDOWS = (10, 20, 50)
ENTRY_Z = (-1.5, -2.0, -2.5, -3.0)
EXIT_Z = (-0.5, 0.0, 0.5)
MAX_HOLDS = (0, 10, 20)          # 0 = no time limit


def _grid(close, allow_shorts):
    bars = [{"close": float(c)} for c in close]
    cols, labels = [], []
    for w in WINDOWS:
        for ez in ENTRY_Z:
            for xz in EXIT_Z:
                if xz < ez:
                    continue      # an exit below the entry never reverts
                for mh in MAX_HOLDS:
                    pos = mean_revert_positions(bars, window=w, entry_z=ez,
                                                exit_z=xz, max_hold=mh,
                                                allow_shorts=allow_shorts)
                    cols.append(np.asarray(pos, dtype=np.float32))
                    labels.append(f"mean_revert w={w} entry={ez:g} "
                                  f"exit={xz:g} hold={mh}"
                                  + (" short" if allow_shorts else ""))
    return np.column_stack(cols), labels


def build(close):
    return _grid(close, False)


def build_shorts(close):
    return _grid(close, True)
