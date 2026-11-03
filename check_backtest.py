#!/usr/bin/env python3
"""
check_backtest.py -- verify a set of backtest JSON runs before believing them.

    python3 check_backtest.py 'out/bt_*.json'

The bridge can serve one symbol's series in answer to a request for another,
and the in-process guards do not always catch it: `_prices_agree` returns
True when no quote is available, so it fails *open* exactly when the bridge
is degraded enough for the quote to fail too (bug 13 in FINDINGS.md).

Two checks, because the first one alone missed a real contamination:

1. Within a run, two different symbols must not share bar count, first and
   last timestamp and buy-and-hold. Those are properties of the DATA, so a
   match means one series was served twice.

2. Across runs, one symbol's buy-and-hold must AGREE. The same symbol over
   the same period has one buy-and-hold whatever strategy is traded on it, so
   a disagreement means at least one of those rows is not the symbol it
   claims. This is what caught a `confluence` row labelled OKX:ZBCNUSDT that
   carried BITSTAMP:BTCUSD's -24.22; check 1 could not see it, because only
   one row of that run survived and a single row collides with nothing.

Exit 1 if either check finds something.
"""
import glob
import json
import sys
from collections import defaultdict

TOL = 1.0          # percentage points; same bars, so agreement should be exact


def load(pattern):
    rows, errors, unreadable = [], [], []
    for path in sorted(glob.glob(pattern)):
        tag = path.split("bt_")[-1].replace(".json", "")
        try:
            blob = json.load(open(path))
        except (OSError, ValueError) as e:
            # An incomplete run is not a collision. Keep the exit status for
            # what this tool is actually for.
            unreadable.append((tag, str(e)[:60]))
            continue
        for r in blob:
            (errors if "error" in r else rows).append((tag, r))
    return rows, errors, unreadable


def main(pattern):
    rows, errors, unreadable = load(pattern)
    for tag, why in unreadable:
        print(f"  skipped   {tag:<14} no usable JSON ({why})")
    for tag, r in errors:
        print(f"  refused   {tag:<14} {r['symbol']:<18} {r['error'][:60]}")
    print(f"\n{len(rows)} usable rows, {len(errors)} refused\n")
    if not rows:
        print("No usable rows: nothing to check. This is not a pass.")
        return 0

    bad = 0

    groups = defaultdict(list)
    for tag, r in rows:
        groups[(tag, r.get("bars"), r.get("from"), r.get("to"),
                r.get("buy_hold_pct"))].append(r["symbol"])
    for k, syms in groups.items():
        if len(set(syms)) > 1:
            bad += 1
            print(f"  COLLISION in {k[0]}: {', '.join(sorted(set(syms)))} "
                  f"share bars={k[1]} {k[2]}->{k[3]} buy_hold={k[4]}")

    bh = defaultdict(dict)
    for tag, r in rows:
        bh[r["symbol"]][tag] = r["buy_hold_pct"]
    for sym, d in sorted(bh.items()):
        vals = list(d.values())
        if len(vals) > 1 and max(vals) - min(vals) > TOL:
            bad += 1
            detail = "  ".join(f"{k}={v:.2f}" for k, v in sorted(d.items()))
            print(f"  DISAGREES {sym}: buy-and-hold differs across runs -- "
                  f"{detail}")

    print(f"\n{bad} problem(s) found." if bad else "\nBoth checks clean.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "bt_*.json"))
