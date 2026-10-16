#!/usr/bin/env python3
"""
fm_family.py — the follow_money parameter grid, as a sweep strategy family.

Lets `fitzz sweep` price the selection bias in follow_money's parameters the
same way it does for ma_cross:

    python3 -m fitzz sweep --json bars.json \\
        --strategy fitzz/fm_family.py:build --objective return --cost-bps 10

`build` takes (close, bars) rather than just close, because the signal reads
high/low/volume -- so this family needs --json input, not --csv.

What is swept is the *signal*, not the risk overlay: no stop-loss or
take-profit. Those change the return distribution without telling you whether
the entry rule knows anything, which is the question a significance test is
for. Positions are 1 while long and 0 while flat, decided from data through
bar t, which is the convention sweep scores against (pos[t] earns t -> t+1).
"""

import numpy as np

from fitzz.trading import chaikin_money_flow, money_flow_volume, sma

# The grid. Kept deliberately small: every extra config is another draw on the
# same data, which the Reality Check then has to charge for.
SURGES = (1.5, 2.0, 2.5, 3.0)
CMF_WINDOWS = (10, 20, 30)
CMF_ENTERS = (0.0, 0.05, 0.10)
CONFIRMS = (1, 3, 5)
VOL_WINDOW = 20
CMF_EXIT = -0.05


def build(close, bars):
    """Return (positions (T, K), labels) over the follow_money grid."""
    n = len(close)
    volumes = [float(b.get("volume") or 0.0) for b in bars]
    if sum(volumes) <= 0:
        raise SystemExit("these bars carry no volume; follow_money cannot be swept "
                         "on them (an INDEX: feed rather than an exchange symbol?)")

    mfv = money_flow_volume(bars)
    vol_ma = sma(volumes, VOL_WINDOW)
    big = {}
    for surge in SURGES:
        big[surge] = [
            vol_ma[i] is not None and vol_ma[i] > 0
            and volumes[i] >= surge * vol_ma[i] and mfv[i] > 0
            for i in range(n)
        ]
    cmfs = {w: chaikin_money_flow(mfv, volumes, w) for w in CMF_WINDOWS}

    cols, labels = [], []
    for surge in SURGES:
        bb = big[surge]
        for w in CMF_WINDOWS:
            cmf = cmfs[w]
            for enter in CMF_ENTERS:
                for confirm in CONFIRMS:
                    p = np.zeros(n, dtype=np.float32)
                    state = 0.0
                    for i in range(n):
                        c = cmf[i]
                        if state > 0:
                            if c is not None and c <= CMF_EXIT:
                                state = 0.0
                        elif c is not None and c >= enter:
                            if any(bb[max(0, i - confirm + 1):i + 1]):
                                state = 1.0
                        p[i] = state
                    cols.append(p)
                    labels.append(f"follow_money surge={surge:g} cmf={w} "
                                  f"enter={enter:g} confirm={confirm}")
    return np.column_stack(cols), labels
