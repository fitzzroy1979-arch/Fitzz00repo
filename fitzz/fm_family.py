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

from fitzz.trading import follow_money_positions

# The grid. Kept deliberately small: every extra config is another draw on the
# same data, which the Reality Check then has to charge for.
SURGES = (1.5, 2.0, 2.5, 3.0)
CMF_WINDOWS = (10, 20, 30)
CMF_ENTERS = (0.0, 0.05, 0.10)
CONFIRMS = (1, 3, 5)
VOL_WINDOW = 20
CMF_EXIT = -0.05


def _grid(close, bars, allow_shorts):
    volumes = [float(b.get("volume") or 0.0) for b in bars]
    if sum(volumes) <= 0:
        raise SystemExit("these bars carry no volume; follow_money cannot be swept "
                         "on them (an INDEX: feed rather than an exchange symbol?)")
    cols, labels = [], []
    for surge in SURGES:
        for w in CMF_WINDOWS:
            for enter in CMF_ENTERS:
                for confirm in CONFIRMS:
                    pos = follow_money_positions(
                        bars, vol_window=VOL_WINDOW, surge=surge, cmf_window=w,
                        cmf_enter=enter, cmf_exit=CMF_EXIT, confirm=confirm,
                        allow_shorts=allow_shorts)
                    cols.append(np.asarray(pos, dtype=np.float32))
                    labels.append(f"follow_money surge={surge:g} cmf={w} "
                                  f"enter={enter:g} confirm={confirm}"
                                  + (" short" if allow_shorts else ""))
    return np.column_stack(cols), labels


def build(close, bars):
    """Long-only grid."""
    return _grid(close, bars, False)


def build_shorts(close, bars):
    """Same grid, also selling big volume into distribution."""
    return _grid(close, bars, True)
