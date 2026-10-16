#!/usr/bin/env python3
"""
run_sweep_4h.py — reproduce the intraday significance sweep.

Pulls 4h bars for a set of symbols off the TradingView bridge, runs every
strategy family over each, and prints the corrected p-values side by side.

    python3 run_sweep_4h.py                    # the six focus symbols
    python3 run_sweep_4h.py --symbols BITSTAMP:BTCUSD,COINBASE:XRPUSD
    python3 run_sweep_4h.py --interval 1d --bars 3000
    python3 run_sweep_4h.py --family ma_cross  # just one family

Why 4h rather than daily: a sweep can only score a config that trades enough
to clear --min-trades. On daily bars follow_money fires 2-4 times a year, so
98+ of its 108 configs were dropped and the grid was never really tested. At
4h the same configs make 90-130 trades and the whole grid is scored. That is
a statement about statistical power, not about 4h being a better timeframe to
trade.

Bars are cached under --cache so repeat runs do not re-hit the bridge; delete
that directory to refetch.

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
    "follow_money": ["--strategy", "fitzz/fm_family.py:build"],
}
REPO = os.path.dirname(os.path.abspath(__file__))

# Mirrors fitzz.sweep's own argparse defaults; rebuilding the winning config
# means reusing the same grid the sweep searched.
MA_DEFAULTS = ("2:40:2", "10:200:5", "0,0.001,0.0025,0.005,0.01")


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
    with open(bars_path) as fh:
        bars = json.load(fh)
    close = np.asarray([float(b["close"]) for b in bars], dtype=float)

    if family == "ma_cross":
        from fitzz.sweep import ma_cross_family, parse_range
        # sweep's main casts the window grids to int and the deadband to
        # float before building; match that or rolling_mean gets float windows.
        f = [int(v) for v in parse_range(MA_DEFAULTS[0])]
        s = [int(v) for v in parse_range(MA_DEFAULTS[1])]
        th = [float(v) for v in parse_range(MA_DEFAULTS[2])]
        pos, labels, _ = ma_cross_family(close, f, s, th, True)
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


def fetch(symbol, interval, bars, cache):
    """Bars for one symbol, from the cache if it is already there."""
    path = os.path.join(cache, f"{symbol.replace(':', '_')}_{interval}_{bars}.json")
    if os.path.exists(path):
        with open(path) as fh:
            return path, len(json.load(fh))
    from fitzz.trading import TradingViewBridge, resolve_interval
    data = TradingViewBridge().load_bars(symbol, resolve_interval(interval), bars)
    os.makedirs(cache, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh)
    return path, len(data)


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
