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

    print(f"{'symbol':<20}{'family':<14}{'bars':>6}{'cfgs':>7}{'trades':>8}"
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
            print(f"{sym:<20}{fam:<14}{res.get('n_bars', n):>6}"
                  f"{res.get('n_configs', 0):>7}{d.get('trades', 0):>8}"
                  f"{res.get('p_rc', float('nan')):>8.3f}"
                  f"{res.get('p_spa', float('nan')):>8.3f}  {ok}")
            rows.append((sym, fam, res.get("p_spa")))

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
