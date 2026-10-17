#!/usr/bin/env python3
"""
mr_family.py — the mean_revert parameter grid, as a sweep strategy family.

    python3 -m fitzz sweep --json bars.json \\
        --strategy fitzz/mr_family.py:build --objective return --cost-bps 10

`build` takes only closes: unlike follow_money this signal reads no volume,
so it works from a bare price series and runs against --csv input too.

Mean reversion is the one family here that is not a trend follower. If
sma_cross, breakout and follow_money all fail on the same symbols, a shared
reason is more plausible than three separate ones -- they are the same bet
wearing different clothes. This grid exists to find out whether the opposite
bet fares any better on the same data, which is a question none of the other
three can answer.

Positions are 1 while long and 0 while flat, decided from data through bar t,
matching the convention sweep scores against (pos[t] earns t -> t+1).
"""

import numpy as np

from fitzz.trading import zscore

# Kept small: every extra config is another draw on the same data that the
# Reality Check then has to charge for.
WINDOWS = (10, 20, 50)
ENTRY_Z = (-1.5, -2.0, -2.5, -3.0)
EXIT_Z = (-0.5, 0.0, 0.5)
MAX_HOLDS = (0, 10, 20)          # 0 = no time limit


def build(close):
    """Return (positions (T, K), labels) over the mean_revert grid."""
    closes = [float(c) for c in close]
    n = len(closes)
    zs = {w: zscore(closes, w) for w in WINDOWS}

    cols, labels = [], []
    for w in WINDOWS:
        z = zs[w]
        for ez in ENTRY_Z:
            for xz in EXIT_Z:
                if xz < ez:
                    continue        # exit below entry never reverts; skip
                for mh in MAX_HOLDS:
                    p = np.zeros(n, dtype=np.float32)
                    state = 0.0
                    entry_i = 0
                    for i in range(n):
                        if state > 0:
                            if (z[i] is not None and z[i] >= xz) or \
                               (mh and (i - entry_i) >= mh):
                                state = 0.0
                        if state <= 0 and z[i] is not None and z[i] <= ez:
                            state = 1.0
                            entry_i = i
                        p[i] = state
                    cols.append(p)
                    labels.append(f"mean_revert w={w} entry={ez:g} "
                                  f"exit={xz:g} hold={mh}")
    return np.column_stack(cols), labels
