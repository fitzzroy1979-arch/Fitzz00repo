#!/usr/bin/env python3
"""
run_sweep_4h.py — reproduce the intraday significance sweep.

Pulls 4h bars for a set of symbols off the TradingView bridge, runs every
strategy family over each, and prints the corrected p-values side by side.

    python3 run_sweep_4h.py                    # the six focus symbols
    python3 run_sweep_4h.py --symbols BITSTAMP:BTCUSD,COINBASE:XRPUSD
    python3 run_sweep_4h.py --interval 1d --bars 3000
    python3 run_sweep_4h.py --family ma_cross  # just one family
                                               # (ma_cross, breakout, follow_money)

Why 4h rather than daily: a sweep can only score a config that trades enough
to clear --min-trades. On daily bars follow_money fires 2-4 times a year, so
98+ of its 108 configs were dropped and the grid was never really tested. At
4h the same configs make 90-130 trades and the whole grid is scored. That is
a statement about statistical power, not about 4h being a better timeframe to
trade.

Bars are cached under --cache so repeat runs do not re-hit the bridge; delete
that directory to refetch. A series shorter than requested is re-read once
before being trusted, because a short read can mean a young asset or a chart
that had not finished paging history -- and caching the latter would poison
every run after it.

Two different "win rates" appear, and they are not the same measure:
`hit%` is the share of active BARS the winner got directionally right,
which is what the sweep scores; `win%` is the share of round-trip TRADES
that closed green, which is what the backtest reports. A trend-following
config routinely shows win% near 30 while still making money, because the
few winners are much larger than the many losers -- so a low win% is not
by itself evidence against a config.

Reading the output: p(SPA) is the number to quote. Above 0.05 the winner is a
lucky draw from the search. The `block ok` column reports the test's own
diagnostic -- when a winner holds positions longer than the bootstrap block,
the p-value is optimistically small and the run should be repeated with the
larger --block the tool suggests. A 'no' there only matters for a result that
would otherwise look significant, since the correction always raises p.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

DEFAULT_SYMBOLS = [
    "BITSTAMP:BTCUSD", "COINBASE:XRPUSD", "COINBASE:FLRUSD",
    "OKX:ZBCNUSDT", "OKX:CCUSDT", "COINBASE:HBARUSD",
]
FAMILIES = {
    "ma_cross": ["--family", "ma_cross", "--long-only"],
    "breakout": ["--family", "breakout", "--long-only"],
    "follow_money": ["--strategy", "fitzz/fm_family.py:build"],
    "mean_revert": ["--strategy", "fitzz/mr_family.py:build"],
    "confluence": ["--strategy", "fitzz/conf_family.py:build"],
}
REPO = os.path.dirname(os.path.abspath(__file__))

# One bridge for the whole run, not one per symbol. TradingViewBridge keeps the
# previous read on the instance and refuses a new one whose bars are identical
# to it -- that is the guard against the chart not having repainted yet, and
# constructing a fresh bridge per fetch silently disables it, because the
# fingerprint it compares against is always None. Doing that crossed six
# symbols' caches: a 4h XRP file ended up holding FLR's daily series.
_BRIDGE = None


def _bridge():
    global _BRIDGE
    if _BRIDGE is None:
        from fitzz.trading import TradingViewBridge
        _BRIDGE = TradingViewBridge()
    return _BRIDGE


# Seconds per bar, to check a fetched series is on the interval it claims.
_INTERVAL_SECS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                  "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400,
                  "1w": 604800}


def _spacing_ok(bars, interval):
    """
    Does this series actually step at `interval`?

    Catches a whole class of mix-up that a bar count cannot: a daily series
    written into a 4h cache file looks perfectly healthy until its results
    make no sense. Uses the median gap, so listing halts and feed outages do
    not trip it.
    """
    want = _INTERVAL_SECS.get(interval)
    if not want or len(bars) < 10:
        return True, None
    gaps = sorted(b2["time"] - b1["time"]
                  for b1, b2 in zip(bars, bars[1:])
                  if isinstance(b1.get("time"), (int, float))
                  and isinstance(b2.get("time"), (int, float)))
    if not gaps:
        return True, None
    median = gaps[len(gaps) // 2]
    return abs(median - want) <= want * 0.25, median

# Mirrors fitzz.sweep's own argparse defaults; rebuilding the winning config
# means reusing the same grid the sweep searched.
MA_DEFAULTS = ("2:40:2", "10:200:5", "0,0.001,0.0025,0.005,0.01")
BREAKOUT_DEFAULTS = ("10:120:5", "5:60:5")


def trade_stats(bars_path, family, label, cost_bps):
    """
    Per-trade win/loss for the winning config, which the sweep does not
    report -- it scores bars, not round trips.

    Positions are rebuilt by running the same family builder and picking the
    column whose label matches, so the logic cannot drift from what was
    actually swept. A position held from bar t0 through t1 earns
    close[t1+1]/close[t0], since the sweep's convention is that pos[t] earns
    the t -> t+1 return. Costs are charged once each way.
    """
    import numpy as np
    bars, _ = _read_cache(bars_path)      # same reader: the file carries meta
    if not bars:
        return None
    close = np.asarray([float(b["close"]) for b in bars], dtype=float)

    if family == "ma_cross":
        from fitzz.sweep import ma_cross_family, parse_range
        # sweep's main casts the window grids to int and the deadband to
        # float before building; match that or rolling_mean gets float windows.
        f = [int(v) for v in parse_range(MA_DEFAULTS[0])]
        s = [int(v) for v in parse_range(MA_DEFAULTS[1])]
        th = [float(v) for v in parse_range(MA_DEFAULTS[2])]
        pos, labels, _ = ma_cross_family(close, f, s, th, True)
    elif family == "breakout":
        from fitzz.sweep import breakout_family, parse_range
        e = [int(v) for v in parse_range(BREAKOUT_DEFAULTS[0])]
        x = [int(v) for v in parse_range(BREAKOUT_DEFAULTS[1])]
        pos, labels, _ = breakout_family(close, e, x, True)
    elif family == "confluence":
        from fitzz.conf_family import build
        pos, labels = build(close, bars)
    elif family == "mean_revert":
        from fitzz.mr_family import build
        pos, labels = build(close)
    else:
        from fitzz.fm_family import build
        pos, labels = build(close, bars)
    if label not in labels:
        return None
    col = np.asarray(pos)[:, labels.index(label)]

    fee = cost_bps * 1e-4
    wins = losses = 0
    gains, drops = [], []
    i, n = 0, len(col)
    while i < n:
        if col[i] > 0:
            t0 = i
            while i + 1 < n and col[i + 1] > 0:
                i += 1
            exit_i = min(i + 1, n - 1)
            if exit_i > t0:
                r = (close[exit_i] / close[t0] - 1) - 2 * fee
                (gains if r > 0 else drops).append(r)
                wins += r > 0
                losses += r <= 0
        i += 1
    total = wins + losses
    if not total:
        return None
    return {
        "trades": total,
        "win_pct": 100.0 * wins / total,
        "avg_win": 100.0 * sum(gains) / len(gains) if gains else 0.0,
        "avg_loss": 100.0 * sum(drops) / len(drops) if drops else 0.0,
    }


def _read_cache(path):
    """(bars, meta) from a cache file, tolerating the old bare-list format."""
    try:
        with open(path) as fh:
            blob = json.load(fh)
    except (OSError, ValueError):
        return None, {}
    if isinstance(blob, dict):
        return blob.get("bars") or [], blob.get("meta") or {}
    return blob, {}                      # written before meta existed


def _write_cache(path, bars, meta):
    # sweep's load_json accepts {"bars": [...]}, so the meta rides along in the
    # same file and --json can still be pointed straight at it.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"bars": bars, "meta": meta}, fh)


def fetch(symbol, interval, bars, cache):
    """
    Bars for one symbol, cached.

    A short series means one of two things and the count alone cannot say
    which: the asset is young, or the TradingView chart was still paging
    history back when it was read. Caching the second silently poisons every
    later run, so a series shorter than asked is re-fetched once; if the
    second read agrees it is marked confirmed and trusted from then on, and
    if it comes back longer the longer one wins.
    """
    from fitzz.trading import resolve_interval
    path = os.path.join(cache, f"{symbol.replace(':', '_')}_{interval}_{bars}.json")

    cached, meta = (_read_cache(path) if os.path.exists(path) else (None, {}))
    if cached:
        ok, median = _spacing_ok(cached, interval)
        if not ok:
            print(f"  note: cached {symbol} steps {median}s, not {interval} — "
                  f"discarding and refetching")
            cached, meta = None, {}
    if cached and (len(cached) >= bars or meta.get("confirmed")):
        return path, len(cached)

    fresh = _bridge().load_bars(symbol, resolve_interval(interval), bars)
    ok, median = _spacing_ok(fresh, interval)
    if not ok:
        raise RuntimeError(
            f"{symbol}: fetched series steps {median}s but {interval} was asked "
            f"for — the chart was on another timeframe. Not caching this.")

    # A re-read must trade at roughly the price the cached one did. A short
    # series is re-read every run until two reads agree, and "longer wins"
    # below is only sound for the same instrument — a cross-symbol read is
    # wrong however long it is. CC is 1,482 bars, so it is re-read every time;
    # one of those came back holding BTC's 5,000-bar series and was accepted
    # for being the longer of the two.
    if cached and fresh:
        try:
            a, b = float(fresh[-1]["close"]), float(cached[-1]["close"])
            if a > 0 and b > 0 and not (0.2 <= a / b <= 5.0):
                raise RuntimeError(
                    f"{symbol}: re-read closes at {a}, cached series closes at "
                    f"{b} — different instrument. Keeping the cached series.")
        except (KeyError, TypeError, ValueError):
            pass
    if cached and len(fresh) < len(cached):
        # A worse read than one we already hold: keep the longer series and do
        # not confirm, so the next run checks again.
        _write_cache(path, cached, {**meta, "asked": bars, "got": len(cached)})
        print(f"  note: {symbol} re-read returned {len(fresh)} bars, keeping the "
              f"cached {len(cached)}")
        return path, len(cached)

    confirmed = bool(cached) and len(fresh) == len(cached)
    _write_cache(path, fresh, {"symbol": symbol, "interval": interval,
                               "asked": bars, "got": len(fresh),
                               "confirmed": confirmed})
    return path, len(fresh)


def sweep(bars_path, family, cost_bps, block, seed):
    """One sweep. Returns the tool's own result dict, or None if it bailed."""
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as out:
        out_path = out.name
    cmd = [sys.executable, "-m", "fitzz", "sweep", "--json", bars_path,
           *FAMILIES[family], "--objective", "return",
           "--cost-bps", str(cost_bps), "--seed", str(seed),
           "--json-out", out_path]
    if block:
        cmd += ["--block", str(block)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    try:
        with open(out_path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        # sweep exits early when no config clears --min-trades, or when the
        # grid's longest window outruns the history.
        msg = (proc.stdout or proc.stderr or "").strip().splitlines()
        return {"error": msg[-1][:60] if msg else f"exit {proc.returncode}"}
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                   help="comma-separated TradingView symbols")
    p.add_argument("--interval", default="4h", help="bar interval (default 4h)")
    p.add_argument("--bars", type=int, default=5000,
                   help="bars to request per symbol (default 5000, the bridge cap)")
    p.add_argument("--family", choices=sorted(FAMILIES), action="append",
                   help="limit to one family; repeatable (default: all)")
    p.add_argument("--cost-bps", type=float, default=10.0,
                   help="cost per unit turnover (default 10)")
    p.add_argument("--block", type=int, default=None,
                   help="bootstrap block length; default lets the tool choose")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "fitzz_sweep_bars"),
                   help="where fetched bars are cached")
    args = p.parse_args(argv)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    families = args.family or sorted(FAMILIES)

    print(f"{'symbol':<20}{'family':<14}{'bars':>6}{'cfgs':>7}{'trades':>7}"
          f"{'hit%':>7}{'win%':>7}{'avgW%':>7}{'avgL%':>7}"
          f"{'p(RC)':>8}{'p(SPA)':>8}  block ok")
    rows = []
    for sym in symbols:
        try:
            path, n = fetch(sym, args.interval, args.bars, args.cache)
        except Exception as e:
            print(f"{sym:<20}{'-':<14}{'':>6}  fetch failed: {str(e)[:40]}")
            continue
        for fam in families:
            res = sweep(path, fam, args.cost_bps, args.block, args.seed)
            if "error" in res:
                print(f"{sym:<20}{fam:<14}{n:>6}  {res['error']}")
                continue
            d = res.get("detail") or {}
            # The tool warns when a winner outlives the block: p is then too
            # small, so a 'no' makes a significant-looking result suspect.
            ok = "yes" if res.get("hold_bars", 0) <= res.get("block", 0) else "NO"
            ts = trade_stats(path, fam, res.get("label", ""), args.cost_bps)
            hit = 100.0 * d.get("hit_rate", 0.0)
            w = f"{ts['win_pct']:>7.1f}" if ts else f"{'-':>7}"
            aw = f"{ts['avg_win']:>7.1f}" if ts else f"{'-':>7}"
            al = f"{ts['avg_loss']:>7.1f}" if ts else f"{'-':>7}"
            print(f"{sym:<20}{fam:<14}{res.get('n_bars', n):>6}"
                  f"{res.get('n_configs', 0):>7}{d.get('trades', 0):>7}"
                  f"{hit:>7.1f}{w}{aw}{al}"
                  f"{res.get('p_rc', float('nan')):>8.3f}"
                  f"{res.get('p_spa', float('nan')):>8.3f}  {ok}")
            rows.append((sym, fam, res.get("p_spa"), ts))

    pooled = [r[3] for r in rows if r[3]]
    if pooled:
        tw = sum(s["trades"] * s["win_pct"] / 100.0 for s in pooled)
        tt = sum(s["trades"] for s in pooled)
        aw = sum(s["avg_win"] * s["trades"] for s in pooled) / tt
        al = sum(s["avg_loss"] * s["trades"] for s in pooled) / tt
        print(f"\n  ALL SWEEPS  {int(round(tw))}W / {int(tt - round(tw))}L "
              f"of {tt} trades = {100.0 * tw / tt:.1f}% win")
        print(f"  trade-weighted average winner {aw:+.2f}%, average loser {al:+.2f}%, "
              f"payoff {abs(aw / al) if al else float('nan'):.2f}x")

    live = [r for r in rows if r[2] is not None]
    if live:
        best = min(live, key=lambda r: r[2])
        sig = [r for r in live if r[2] <= 0.05]
        print(f"\n  {len(live)} sweeps; lowest p(SPA) {best[2]:.3f} "
              f"({best[0]} / {best[1]})")
        print(f"  significant at 5%: {len(sig)}")
        if sig:
            print("  NOTE: these p-values correct for searching the grid within a")
            print("  symbol, not for trying several symbols. Across "
                  f"{len(live)} sweeps, expect")
            print(f"  about {0.05 * len(live):.1f} to clear 5% by chance alone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
