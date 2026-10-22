"""
Per-trade journal: what the tape looked like at the entry of every trade, and
what separates the trades that worked from the ones that did not.

The sweep scores bars and the backtest scores an equity curve; neither can
answer "what do the losers have in common". This can. For each round trip it
records the nine readings below, taken at the entry bar from data available
at that bar, then compares winners against losers.

The obvious way to use that is to find whatever marks the losers and refuse
those entries. That is also the single most reliable way to overfit, because
with enough features some split always separates them. So every separation
here is measured twice: on the first two thirds of the trades, and again on
the last third, which the first measurement never saw. A feature that
separates in both is worth testing as a filter through the usual gates --
cost scan, SPA and Reality Check, holdout. A feature that separates only
in-sample is the search talking to itself, and the point of printing both
columns is to make that visible rather than inferable.

One caveat the output cannot express on its own: the nine are not
independent. Trailing return, RSI, z-score and range location all partly
restate recent price, so a real effect in one tends to light up the others
and a count of how many "hold" is not a count of independent confirmations.
Read the table for which dimension separates, not for how many did.
"""

import math

from fitzz.trading import (
    bollinger_bandwidth,
    chaikin_money_flow,
    money_flow_volume,
    percentile_rank,
    rolling_max,
    rolling_min,
    rsi,
    sma,
    zscore,
)

# Each reads a different dimension, for the same reason confluence_flags does:
# nine restatements of "is price going up" would separate winners from losers
# nine times over and mean it once.
FEATURES = (
    ("trend_dist", "close vs 200-bar mean, as a fraction"),
    ("trend_slope", "200-bar mean vs itself 20 bars back"),
    ("rsi14", "Wilder RSI"),
    ("vol_regime", "Bollinger bandwidth percentile over 100 bars, 0-1"),
    ("vol_ratio", "bar volume over its own 20-bar mean"),
    ("cmf20", "Chaikin money flow"),
    ("location", "position in the 20-bar range, 0 low 1 high"),
    ("z20", "close z-score over 20 bars"),
    ("ret5", "trailing 5-bar return, as a fraction"),
)


def entry_features(bars):
    """
    The nine readings, as parallel lists indexed by bar.

    Computed once per symbol rather than per trade: every indicator here is a
    rolling function of the whole series, so doing it inside the trade loop
    would recompute the same 1,500-bar pass for each of 170 trades.

    Every value at index i depends only on bars 0..i, which is what makes it
    legitimate to read at an entry. Leading positions are None until their
    window fills; callers drop trades whose entry falls there.
    """
    closes = [float(b["close"]) for b in bars]
    volumes = [float(b.get("volume") or 0.0) for b in bars]
    n = len(closes)

    trend = sma(closes, 200)
    bw_rank = percentile_rank(bollinger_bandwidth(closes, 20), 100)
    vol_ma = sma(volumes, 20)
    cmf = chaikin_money_flow(money_flow_volume(bars), volumes, 20)
    hi = rolling_max(closes, 20)
    lo = rolling_min(closes, 20)
    r = rsi(closes, 14)
    z = zscore(closes, 20)

    out = {name: [None] * n for name, _ in FEATURES}
    for i in range(n):
        t = trend[i]
        if t:
            out["trend_dist"][i] = closes[i] / t - 1.0
            back = trend[i - 20] if i >= 20 else None
            if back:
                out["trend_slope"][i] = t / back - 1.0
        out["rsi14"][i] = r[i]
        out["vol_regime"][i] = bw_rank[i]
        if vol_ma[i]:
            out["vol_ratio"][i] = volumes[i] / vol_ma[i]
        out["cmf20"][i] = cmf[i]
        if hi[i] is not None and lo[i] is not None and hi[i] > lo[i]:
            out["location"][i] = (closes[i] - lo[i]) / (hi[i] - lo[i])
        out["z20"][i] = z[i]
        if i >= 5 and closes[i - 5]:
            out["ret5"][i] = closes[i] / closes[i - 5] - 1.0
    return out


def extract_trades(bars, positions, cost_bps=10.0):
    """
    One dict per round trip, annotated with the entry-bar features.

    A trade is a run of identical non-zero exposure. The sweep's convention is
    that pos[t] earns the t -> t+1 return, so a run occupying bars t0..t1
    exits at the close of t1+1, and a run still open on the last bar exits
    there. A long-to-short flip is two trades, not one.

    `ret` is net: the raw move times the side, less a round turn of
    2 * cost_bps. Trades whose entry bar predates a full indicator window are
    kept -- dropping them would quietly change which trades are being judged
    -- but their missing features are None and the comparison skips those.
    """
    closes = [float(b["close"]) for b in bars]
    n = len(closes)
    fee = cost_bps * 1e-4
    feats = entry_features(bars)

    trades = []
    i = 0
    while i < n:
        side = positions[i]
        if side == 0:
            i += 1
            continue
        t0 = i
        while i + 1 < n and positions[i + 1] == side:
            i += 1
        exit_i = min(i + 1, n - 1)
        if exit_i > t0 and closes[t0]:
            raw = closes[exit_i] / closes[t0] - 1.0
            trades.append({
                "entry_i": t0,
                "exit_i": exit_i,
                "side": int(side),
                "bars_held": exit_i - t0,
                "entry_px": closes[t0],
                "exit_px": closes[exit_i],
                "entry_time": bars[t0].get("time"),
                "ret": side * raw - 2 * fee,
                "features": {k: feats[k][t0] for k, _ in FEATURES},
            })
        i += 1
    return trades


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _cohens_d(a, b):
    """
    Separation in pooled standard deviations: how far apart two groups sit
    relative to how wide they are.

    Plain difference of means is unreadable across features measured in
    different units -- an RSI gap of 3 and a CMF gap of 0.03 are not
    comparable. This is. As a rule of thumb 0.2 is slight, 0.5 moderate, 0.8
    large; anything under about 0.2 on this data is not worth chasing.
    """
    if len(a) < 2 or len(b) < 2:
        return None
    ma, mb = _mean(a), _mean(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    pooled = ((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2)
    if pooled <= 0:
        return None
    return (ma - mb) / math.sqrt(pooled)


def separation(trades, holdout=0.33):
    """
    Winner-vs-loser separation per feature, in-sample and then held out.

    Trades are split by entry order, not shuffled: the holdout is the last
    third of the timeline, so a feature has to keep working on later trades
    rather than merely on a random subset of the same period. Shuffling would
    let a regime that spans the whole window leak across the split and make
    every feature look stable.

    Returns a list of rows sorted by in-sample |d|, each carrying both d's and
    the group means, plus the split sizes.
    """
    ordered = sorted(trades, key=lambda t: t["entry_i"])
    cut = int(len(ordered) * (1.0 - holdout))
    insample, held = ordered[:cut], ordered[cut:]

    rows = []
    for name, desc in FEATURES:
        def groups(ts):
            w = [t["features"][name] for t in ts
                 if t["ret"] > 0 and t["features"][name] is not None]
            l = [t["features"][name] for t in ts
                 if t["ret"] <= 0 and t["features"][name] is not None]
            return w, l

        wi, li = groups(insample)
        wh, lh = groups(held)
        rows.append({
            "feature": name,
            "desc": desc,
            "d_in": _cohens_d(wi, li),
            "d_out": _cohens_d(wh, lh),
            "win_mean": _mean(wi),
            "loss_mean": _mean(li),
            "n_win": len(wi),
            "n_loss": len(li),
        })
    rows.sort(key=lambda r: abs(r["d_in"]) if r["d_in"] is not None else -1,
              reverse=True)
    return {"rows": rows, "n_in": len(insample), "n_out": len(held)}


def quintiles(trades, feature, buckets=5):
    """
    Win rate and mean return by feature value, lowest bucket first.

    The d statistic assumes the relationship is monotone and roughly normal.
    Plenty are not -- "losers cluster at both extremes" shows up as d near
    zero. Bucketing shows the shape, so a U is not read as an absence.
    """
    vals = [t for t in trades if t["features"][feature] is not None]
    if len(vals) < buckets * 2:
        return []
    vals.sort(key=lambda t: t["features"][feature])
    size = len(vals) / buckets
    out = []
    for b in range(buckets):
        chunk = vals[int(b * size):int((b + 1) * size)]
        if not chunk:
            continue
        rets = [t["ret"] for t in chunk]
        out.append({
            "lo": chunk[0]["features"][feature],
            "hi": chunk[-1]["features"][feature],
            "n": len(chunk),
            "win_pct": 100.0 * sum(1 for r in rets if r > 0) / len(rets),
            "mean_ret_pct": 100.0 * _mean(rets),
        })
    return out


def _fmt(v, places=4):
    if v is None:
        return "n/a"
    # CMF and trend slopes live near 1e-4; fixed places would print them all
    # as +0.0000 and hide the very difference the column exists to show.
    if v != 0 and abs(v) < 10 ** -places:
        return f"{v:+.2e}"
    return f"{v:+.{places}f}"


def render(trades, title, holdout=0.33, show_quintiles=2):
    """The journal as text: the split, the feature table, then the shapes."""
    if not trades:
        return f"{title}: no trades\n"

    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    lines = [
        f"{title}",
        f"  {len(trades)} trades  "
        f"win {100.0 * len(wins) / len(trades):.1f}%  "
        f"avg win {100 * (_mean(wins) or 0):+.2f}%  "
        f"avg loss {100 * (_mean(losses) or 0):+.2f}%  "
        f"total {100 * sum(rets):+.1f}%",
    ]

    sep = separation(trades, holdout)
    lines.append(f"  separation (d), {sep['n_in']} in-sample / "
                 f"{sep['n_out']} held out:")
    lines.append(f"    {'feature':<12} {'d in':>8} {'d out':>8} "
                 f"{'win mean':>11} {'loss mean':>11}  holds?")
    for r in sep["rows"]:
        di, do = r["d_in"], r["d_out"]
        # "holds" means it separated meaningfully in-sample AND kept both the
        # direction and at least half the size out of sample. Sign agreement
        # alone is a coin flip, and a d that collapses is not a filter.
        holds = (di is not None and do is not None
                 and abs(di) >= 0.2 and di * do > 0 and abs(do) >= abs(di) / 2)
        lines.append(
            f"    {r['feature']:<12} {_fmt(di, 3):>8} {_fmt(do, 3):>8} "
            f"{_fmt(r['win_mean']):>11} {_fmt(r['loss_mean']):>11}  "
            f"{'yes' if holds else 'no'}")

    for r in sep["rows"][:show_quintiles]:
        qs = quintiles(trades, r["feature"])
        if not qs:
            continue
        lines.append(f"  {r['feature']} by quintile ({r['desc']}):")
        for q in qs:
            lines.append(
                f"    {q['lo']:+.4f} .. {q['hi']:+.4f}  n={q['n']:<4} "
                f"win {q['win_pct']:5.1f}%  mean {q['mean_ret_pct']:+.3f}%")
    return "\n".join(lines) + "\n"
