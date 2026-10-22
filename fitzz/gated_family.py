"""
gated_family.py — the five families again, each crossed with a volatility
regime gate on entry.

    python3 -m fitzz sweep --json bars.json \\
        --strategy fitzz/gated_family.py:build_ma_cross --objective return

The trade journal found exactly one entry reading that told winners from
losers in every view it was asked for: Bollinger bandwidth percentile, the
volatility regime at the moment of entry. Winners were entered when the
market was moving. Refusing entries below the 40th percentile raised mean
per-trade return in four of five families, in-sample and out of it.

That measurement chose its threshold by looking at the answer, which is the
whole problem. This module puts the threshold into the grid instead, so the
sweep's own correction pays for having chosen it, and the p-value that comes
out is a p-value for "gating on volatility helps" rather than for "this
particular gate, picked afterwards, helped".

**0.0 is in the grid on purpose.** At that threshold the gate passes
everything and the column is the base family, bar for bar. So the ungated
strategy competes inside the same grid: for a gated config to be the sweep's
winner it has to beat not only the bootstrap null but the version of itself
that never refused a trade. If gating is doing nothing, the sweep will say so
by picking 0.0 -- which is a cleaner answer than any comparison run
separately.
"""

import numpy as np

from fitzz.trading import bollinger_bandwidth, percentile_rank

# Deciles around the 0.4 the journal pointed at, plus 0.0 for "no gate".
GATE_GRID = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6)

BANDWIDTH_WINDOW = 20
RANK_LOOKBACK = 100


def vol_regime(close):
    """
    Bandwidth percentile per bar: where this bar's Bollinger bandwidth sits
    in its own trailing 100-bar distribution, 0 to 1.

    A percentile rather than a level because bandwidth is not comparable
    across instruments or across eras of one instrument -- ZBCN's quiet is
    BTC's storm. Rank against the recent past and "unusually quiet for this
    market, lately" means the same thing everywhere.

    NaN while the lookback fills, which the gate treats as a refusal.
    """
    closes = [float(x) for x in close]
    ranks = percentile_rank(bollinger_bandwidth(closes, BANDWIDTH_WINDOW),
                            RANK_LOOKBACK)
    return np.asarray([np.nan if r is None else float(r) for r in ranks],
                      dtype=np.float64)


def apply_entry_gate(col, regime, threshold):
    """
    Zero out whole trades whose entry bar fails the gate; leave the rest
    untouched.

    The gate is tested once, at entry, and never again -- a trade that opens
    in a live market is seen through even if things go quiet, because that is
    the hypothesis the journal actually measured. Killing exposure mid-trade
    whenever volatility dips is a different strategy with a different risk
    profile, and swapping one for the other here would mean the p-value
    answers a question nobody asked.

    A trade is a run of identical non-zero exposure, matching
    fitzz.journal.extract_trades, so what the sweep scores and what the
    journal reports are the same round trips.
    """
    if threshold <= 0.0:
        return col                      # 0.0 is the ungated column, exactly
    out = col.copy()
    n = len(col)
    i = 0
    while i < n:
        side = col[i]
        if side == 0:
            i += 1
            continue
        start = i
        while i + 1 < n and col[i + 1] == side:
            i += 1
        r = regime[start]
        if not (r >= threshold):        # NaN warm-up fails, as it should
            out[start:i + 1] = 0.0
        i += 1
    return out


def _cross_with_gate(cols, labels, close):
    """Every base column times every threshold, labels carrying the gate."""
    regime = vol_regime(close)
    out_cols, out_labels = [], []
    for k, label in enumerate(labels):
        base = np.asarray(cols[:, k], dtype=np.float32)
        for thr in GATE_GRID:
            gated = apply_entry_gate(base, regime, thr)
            # An all-flat column cannot be a winner and only pads the grid,
            # making the multiple-comparisons correction pay for nothing.
            if thr > 0.0 and not gated.any():
                continue
            out_cols.append(gated.astype(np.float32))
            out_labels.append(f"{label} volgate={thr:g}")
    return np.column_stack(out_cols), out_labels


def _base_ma_cross(close, allow_shorts):
    from fitzz.sweep import MA_GRID, ma_cross_family, parse_range
    f = [int(v) for v in parse_range(MA_GRID[0])]
    s = [int(v) for v in parse_range(MA_GRID[1])]
    th = [float(v) for v in parse_range(MA_GRID[2])]
    cols, labels, _ = ma_cross_family(close, f, s, th, not allow_shorts)
    return cols, labels


def _base_breakout(close, allow_shorts):
    from fitzz.sweep import BREAKOUT_GRID, breakout_family, parse_range
    e = [int(v) for v in parse_range(BREAKOUT_GRID[0])]
    x = [int(v) for v in parse_range(BREAKOUT_GRID[1])]
    cols, labels, _ = breakout_family(close, e, x, not allow_shorts)
    return cols, labels


def _base_follow_money(close, bars, allow_shorts):
    from fitzz import fm_family
    return (fm_family.build_shorts if allow_shorts else fm_family.build)(
        close, bars)


def _base_mean_revert(close, bars, allow_shorts):
    from fitzz import mr_family
    return (mr_family.build_shorts if allow_shorts else mr_family.build)(close)


def _base_confluence(close, bars, allow_shorts):
    from fitzz import conf_family
    return (conf_family.build_shorts if allow_shorts else conf_family.build)(
        close, bars)


# The sweep calls FUNC(close) or FUNC(close, bars) depending on how many
# positional parameters the function declares, so the price-only families
# must not declare a `bars` they do not use.

def build_ma_cross(close):
    return _cross_with_gate(*_base_ma_cross(close, False), close=close)


def build_ma_cross_shorts(close):
    return _cross_with_gate(*_base_ma_cross(close, True), close=close)


def build_breakout(close):
    return _cross_with_gate(*_base_breakout(close, False), close=close)


def build_breakout_shorts(close):
    return _cross_with_gate(*_base_breakout(close, True), close=close)


def build_mean_revert(close):
    return _cross_with_gate(*_base_mean_revert(close, None, False), close=close)


def build_mean_revert_shorts(close):
    return _cross_with_gate(*_base_mean_revert(close, None, True), close=close)


def build_follow_money(close, bars):
    return _cross_with_gate(*_base_follow_money(close, bars, False), close=close)


def build_follow_money_shorts(close, bars):
    return _cross_with_gate(*_base_follow_money(close, bars, True), close=close)


def build_confluence(close, bars):
    return _cross_with_gate(*_base_confluence(close, bars, False), close=close)


def build_confluence_shorts(close, bars):
    return _cross_with_gate(*_base_confluence(close, bars, True), close=close)
