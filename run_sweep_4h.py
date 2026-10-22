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
import textwrap
import json
import os
import subprocess
import sys
import tempfile

DEFAULT_SYMBOLS = [
    "BITSTAMP:BTCUSD", "COINBASE:XRPUSD", "COINBASE:FLRUSD",
    "OKX:ZBCNUSDT", "OKX:CCUSDT", "COINBASE:HBARUSD",
    "COINBASE:QNTUSD",
]
# Long-only args, and the same family with shorts enabled. The built-in
# families short by simply dropping --long-only; the custom ones expose a
# second entry point that passes allow_shorts through to the shared builder.
FAMILIES = {
    "ma_cross": ["--family", "ma_cross", "--long-only"],
    "breakout": ["--family", "breakout", "--long-only"],
    "follow_money": ["--strategy", "fitzz/fm_family.py:build"],
    "mean_revert": ["--strategy", "fitzz/mr_family.py:build"],
    "confluence": ["--strategy", "fitzz/conf_family.py:build"],
}
FAMILIES_SHORT = {
    "ma_cross": ["--family", "ma_cross"],
    "breakout": ["--family", "breakout"],
    "follow_money": ["--strategy", "fitzz/fm_family.py:build_shorts"],
    "mean_revert": ["--strategy", "fitzz/mr_family.py:build_shorts"],
    "confluence": ["--strategy", "fitzz/conf_family.py:build_shorts"],
}
# The same five, each crossed with the volatility-regime entry gate. The gate
# threshold is swept rather than chosen, and 0.0 (no gate) is in the grid, so
# a gated winner has beaten the ungated version of itself inside the same
# multiple-comparisons correction.
FAMILIES_GATED = {
    "ma_cross": ["--strategy", "fitzz/gated_family.py:build_ma_cross"],
    "breakout": ["--strategy", "fitzz/gated_family.py:build_breakout"],
    "follow_money": ["--strategy", "fitzz/gated_family.py:build_follow_money"],
    "mean_revert": ["--strategy", "fitzz/gated_family.py:build_mean_revert"],
    "confluence": ["--strategy", "fitzz/gated_family.py:build_confluence"],
}
FAMILIES_GATED_SHORT = {
    k: [v[0], v[1] + "_shorts"] for k, v in FAMILIES_GATED.items()
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
from fitzz.sweep import BREAKOUT_GRID as BREAKOUT_DEFAULTS, MA_GRID as MA_DEFAULTS


def rebuild_positions(bars_path, family, label, shorts=False):
    """
    (bars, position column) for one swept config, or (bars, None).

    Positions are rebuilt by running the same family builder and picking the
    column whose label matches, so nothing downstream can drift from what was
    actually swept. Both the win/loss summary and the trade journal go
    through here for that reason -- two separate reimplementations of "what
    did this config hold" is exactly the kind of quiet disagreement that took
    six data bugs to find the first time.
    """
    import numpy as np
    bars, _ = _read_cache(bars_path)      # same reader: the file carries meta
    if not bars:
        return [], None
    close = np.asarray([float(b["close"]) for b in bars], dtype=float)

    # A gated winner's label carries its threshold, so the gated grid is the
    # only one that can contain it. Dispatching on the label rather than on a
    # flag means a journal or a win/loss summary reproduces whatever config it
    # was handed, without the caller having to remember how it was produced.
    if "volgate=" in label:
        from fitzz import gated_family
        fn = getattr(gated_family,
                     f"build_{family}{'_shorts' if shorts else ''}")
        pos, labels = (fn(close, bars) if family in ("follow_money",
                                                     "confluence")
                       else fn(close))
        if label not in labels:
            return bars, None
        return bars, np.asarray(pos)[:, labels.index(label)]

    if family == "ma_cross":
        from fitzz.sweep import ma_cross_family, parse_range
        # sweep's main casts the window grids to int and the deadband to
        # float before building; match that or rolling_mean gets float windows.
        f = [int(v) for v in parse_range(MA_DEFAULTS[0])]
        s = [int(v) for v in parse_range(MA_DEFAULTS[1])]
        th = [float(v) for v in parse_range(MA_DEFAULTS[2])]
        pos, labels, _ = ma_cross_family(close, f, s, th, not shorts)
    elif family == "breakout":
        from fitzz.sweep import breakout_family, parse_range
        e = [int(v) for v in parse_range(BREAKOUT_DEFAULTS[0])]
        x = [int(v) for v in parse_range(BREAKOUT_DEFAULTS[1])]
        pos, labels, _ = breakout_family(close, e, x, not shorts)
    elif family == "confluence":
        from fitzz import conf_family
        pos, labels = (conf_family.build_shorts if shorts
                       else conf_family.build)(close, bars)
    elif family == "mean_revert":
        from fitzz import mr_family
        pos, labels = (mr_family.build_shorts if shorts
                       else mr_family.build)(close)
    else:
        from fitzz import fm_family
        pos, labels = (fm_family.build_shorts if shorts
                       else fm_family.build)(close, bars)
    if label not in labels:
        return bars, None
    return bars, np.asarray(pos)[:, labels.index(label)]


def trade_stats(bars_path, family, label, cost_bps, shorts=False):
    """
    Per-trade win/loss for the winning config, which the sweep does not
    report -- it scores bars, not round trips.

    Round trips come from fitzz.journal so that the summary and the journal
    cannot disagree about what a trade is. The earlier version walked only
    `col[i] > 0` and so counted nothing but the long legs: under --shorts the
    win rate and payoff described half the strategy while appearing to
    describe all of it.
    """
    from fitzz.journal import extract_trades

    bars, col = rebuild_positions(bars_path, family, label, shorts)
    if col is None:
        return None
    trades = extract_trades(bars, [int(x) for x in col], cost_bps)
    if not trades:
        return None

    gains = [t["ret"] for t in trades if t["ret"] > 0]
    drops = [t["ret"] for t in trades if t["ret"] <= 0]
    return {
        "trades": len(trades),
        "win_pct": 100.0 * len(gains) / len(trades),
        "avg_win": 100.0 * sum(gains) / len(gains) if gains else 0.0,
        "avg_loss": 100.0 * sum(drops) / len(drops) if drops else 0.0,
        "shorts": sum(1 for t in trades if t["side"] < 0),
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


def sweep(bars_path, family, cost_bps, block, seed, shorts=False,
          vol_gate=False):
    """One sweep. Returns the tool's own result dict, or None if it bailed."""
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as out:
        out_path = out.name
    if vol_gate:
        spec = (FAMILIES_GATED_SHORT if shorts else FAMILIES_GATED)[family]
    else:
        spec = (FAMILIES_SHORT if shorts else FAMILIES)[family]
    cmd = [sys.executable, "-m", "fitzz", "sweep", "--json", bars_path,
           *spec,
           "--objective", "return",
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


def cost_scan(bars_path, family, levels, block, seed, shorts, holdout=0.33,
              vol_gate=False):
    """
    Re-run one sweep across a range of transaction costs.

    The question this answers is more useful than a p-value: at what cost
    does the edge stop existing? A winner that needs 10bps round-turn on an
    illiquid pair is disqualified by the spread it will actually pay, and
    that is a fact about the market rather than about the test. It is also
    cheaper to check than anything else here, so it belongs early.

    Each level is run with a holdout, because an edge that survives costs
    in sample and dies out of sample is still nothing.
    """
    import re
    rows = []
    for bps in levels:
        if vol_gate:
            spec = (FAMILIES_GATED_SHORT if shorts else FAMILIES_GATED)[family]
        else:
            spec = (FAMILIES_SHORT if shorts else FAMILIES)[family]
        cmd = [sys.executable, "-m", "fitzz", "sweep", "--json", bars_path,
               *spec,
               "--objective", "return", "--cost-bps", str(bps),
               "--holdout", str(holdout), "--seed", str(seed)]
        if block:
            cmd += ["--block", str(block)]
        out = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO).stdout
        cfg = re.search(r"^\s{4}(\S.*?)\s*$", out, re.M)
        hold = re.search(r"mean ([+-][\d.]+) vs ([+-][\d.]+) in-sample", out)
        spa = re.search(r"SPA, corrected \+ studentized\s+:\s+([\d.]+)", out)
        rc = re.search(r"Reality Check, corrected for the search\s+:\s+([\d.]+)", out)
        lbl = re.search(r"^\s+((?:ma_cross|breakout|follow_money|mean_revert|confluence)[^\n]*)",
                        out, re.M)
        rows.append({
            "bps": bps,
            "config": (lbl.group(1).strip() if lbl else "?"),
            "in_sample": float(hold.group(2)) if hold else None,
            "holdout": float(hold.group(1)) if hold else None,
            "p_spa": float(spa.group(1)) if spa else None,
            "p_rc": float(rc.group(1)) if rc else None,
        })
    return rows


def main(argv=None):
    from fitzz.journal import extract_trades, render, separation


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
    p.add_argument("--cost-scan", default=None, metavar="BPS,BPS,...",
                   help="Instead of one sweep, re-run it at each cost level with a "
                        "holdout, and report where the edge stops surviving.")
    p.add_argument("--shorts", action="store_true",
                   help="Let every family take the mirror-image short as well as "
                        "the long (default long-only).")
    p.add_argument("--journal", action="store_true",
                   help="After each sweep, log every round trip of the winning "
                        "config with the tape readings at its entry, and report "
                        "what separates winners from losers -- measured on the "
                        "first two thirds of trades and re-checked on the last "
                        "third. Also pools trades per family across symbols.")
    p.add_argument("--vol-gate", action="store_true",
                   help="Sweep each family crossed with a volatility-regime "
                        "entry gate, the threshold swept over "
                        "0/0.2/0.3/0.4/0.5/0.6 rather than chosen. 0.0 is the "
                        "ungated family, so the gate has to beat it.")
    p.add_argument("--journal-dump", default=None, metavar="PATH",
                   help="Write every journalled round trip to PATH as JSON, so "
                        "the trades can be re-analysed without re-running the "
                        "sweep. Implies --journal.")
    p.add_argument("--journal-holdout", type=float, default=0.33,
                   help="fraction of trades reserved from the separation "
                        "measurement (default 0.33)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "fitzz_sweep_bars"),
                   help="where fetched bars are cached")
    args = p.parse_args(argv)

    if args.journal_dump:
        args.journal = True

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    families = args.family or sorted(FAMILIES)

    if args.cost_scan:
        levels = [float(x) for x in args.cost_scan.split(",") if x.strip()]
        for sym in symbols:
            try:
                path, n = fetch(sym, args.interval, args.bars, args.cache)
            except Exception as e:
                print(f"{sym}: fetch failed: {str(e)[:60]}")
                continue
            for fam in families:
                print(f"\n{sym}  {fam}{'  (shorts)' if args.shorts else ''}  "
                      f"{args.interval}  {n} bars")
                print(f"  {'bps':>5}{'in-sample':>12}{'holdout':>12}"
                      f"{'p(SPA)':>9}{'p(RC)':>8}  winning config")
                dead = None
                for r in cost_scan(path, fam, levels, args.block, args.seed,
                                   args.shorts, vol_gate=args.vol_gate):
                    ins = f"{r['in_sample']:+.6f}" if r["in_sample"] is not None else "-"
                    hld = f"{r['holdout']:+.6f}" if r["holdout"] is not None else "-"
                    spa = f"{r['p_spa']:.3f}" if r["p_spa"] is not None else "-"
                    rc = f"{r['p_rc']:.3f}" if r["p_rc"] is not None else "-"
                    print(f"  {r['bps']:>5.0f}{ins:>12}{hld:>12}{spa:>9}{rc:>8}  "
                          f"{r['config'][:44]}")
                    if dead is None and r["p_spa"] is not None and r["p_spa"] > 0.05:
                        dead = r["bps"]
                if dead is not None:
                    print(f"\n  significance is gone by {dead:.0f} bps. If the real "
                          f"round-turn cost on this\n  instrument is at or above "
                          f"that, the edge is not tradable whatever the\n  p-value "
                          f"says at a cost you will not get.")
                else:
                    print("\n  survives every cost level tested -- worth raising the "
                          "range.")
        return 0

    print(f"{'symbol':<20}{'family':<14}{'bars':>6}{'cfgs':>7}{'trades':>7}"
          f"{'hit%':>7}{'win%':>7}{'avgW%':>7}{'avgL%':>7}"
          f"{'p(RC)':>8}{'p(SPA)':>8}  block ok")
    rows = []
    journals, by_family = [], {}
    for sym in symbols:
        try:
            path, n = fetch(sym, args.interval, args.bars, args.cache)
        except Exception as e:
            print(f"{sym:<20}{'-':<14}{'':>6}  fetch failed: {str(e)[:40]}")
            continue
        for fam in families:
            res = sweep(path, fam, args.cost_bps, args.block, args.seed,
                        shorts=args.shorts, vol_gate=args.vol_gate)
            if "error" in res:
                print(f"{sym:<20}{fam:<14}{n:>6}  {res['error']}")
                continue
            d = res.get("detail") or {}
            # The tool warns when a winner outlives the block: p is then too
            # small, so a 'no' makes a significant-looking result suspect.
            ok = "yes" if res.get("hold_bars", 0) <= res.get("block", 0) else "NO"
            ts = trade_stats(path, fam, res.get("label", ""), args.cost_bps,
                             shorts=args.shorts)
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

            if args.journal:
                bars, col = rebuild_positions(path, fam, res.get("label", ""),
                                              args.shorts)
                if col is not None:
                    tr = extract_trades(bars, [int(x) for x in col],
                                        args.cost_bps)
                    for t in tr:
                        t["symbol"] = sym
                    journals.append((sym, fam, tr))
                    by_family.setdefault(fam, []).extend(tr)

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

    if args.journal:
        print("\n" + "=" * 72)
        print("TRADE JOURNAL -- what separated the winners from the losers")
        print("=" * 72)
        print(textwrap.fill(
            "d is the gap between winning and losing entries in pooled standard "
            "deviations. 'd in' is measured on the first "
            f"{100 * (1 - args.journal_holdout):.0f}% of trades and 'd out' on "
            "the last "
            f"{100 * args.journal_holdout:.0f}%, which that measurement never "
            "saw. A feature that separates in-sample and collapses out of it "
            "is the search fitting noise, not a property of a bad trade. Only "
            "a 'yes' in the holds column is worth testing as an entry filter, "
            "and even then it has to clear the cost scan and both p-value "
            "tests before it means anything. The nine features are not "
            "independent -- trailing return, RSI, z-score and range location "
            "all partly restate recent price -- so read which dimension "
            "separates, not how many did.", width=72))

        for sym, fam, tr in journals:
            print()
            print(render(tr, f"{sym}  {fam}", args.journal_holdout))

        for fam, tr in sorted(by_family.items()):
            if len(tr) < 30:
                continue
            print()
            print(render(tr, f"ALL SYMBOLS  {fam}  (pooled)",
                         args.journal_holdout))

        if args.journal_dump:
            flat = [dict(t, family=fam) for sym, fam, ts in journals for t in ts]
            with open(args.journal_dump, "w") as fh:
                json.dump({"interval": args.interval,
                           "cost_bps": args.cost_bps,
                           "shorts": bool(args.shorts),
                           "trades": flat}, fh, indent=1)
            print(f"\n  wrote {len(flat)} trades to {args.journal_dump}")

        every = [t for ts in by_family.values() for t in ts]
        if every:
            print()
            print(render(every, "EVERYTHING  (all families, all symbols)",
                         args.journal_holdout))
            holds = 0
            for fam, tr in by_family.items():
                for r in separation(tr, args.journal_holdout)["rows"]:
                    di, do = r["d_in"], r["d_out"]
                    if (di is not None and do is not None and abs(di) >= 0.2
                            and di * do > 0 and abs(do) >= abs(di) / 2):
                        holds += 1
            tested = len(by_family) * 9
            print(f"  {holds} of {tested} family/feature pairs separate "
                  f"in-sample and hold out of sample.")
            if not holds:
                print("  Nothing about the losing entries is stable. There is no "
                      "filter to\n  build here -- the losers are not a kind of "
                      "trade, they are the same\n  trades on the other side of "
                      "a coin.")

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
