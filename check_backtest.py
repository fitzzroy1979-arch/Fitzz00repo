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

   "Agree" is relative, not absolute. Buy-and-hold runs to the last bar and
   the last bar is the one still forming, so the same symbol over the same
   labelled window drifts between runs made hours apart -- and an absolute
   tolerance is the wrong shape for it, being loose against a -35% hold and
   tight against a +169% one. An earlier TOL of 1.0 percentage points
   reported CC (2.5% drift) and QNT (0.6% drift) as contaminated alongside
   the one genuine case. The comparison is therefore on the gross multiple,
   1 + bh/100, with a relative tolerance.

   What this cannot do: distinguish contamination between two symbols whose
   returns over the window happen to be within REL_TOL of each other. The
   genuine ZBCN case was an 18% spread against a 2.5% worst drift, which is
   a comfortable margin, but it is a margin and not a proof. Check 1 is the
   exact one; this is the sensitive one.

Exit 1 if either check finds something.
"""
import glob
import json
import sys
from collections import defaultdict

REL_TOL = 0.05     # relative, on the gross multiple -- see check 2 above.
                   # Covers a day of crypto drift in the still-forming last
                   # bar; the worst drift measured so far is 2.5%.


def load(pattern):
    rows, errors, unreadable = [], [], []
    for path in sorted(glob.glob(pattern)):
        name = path.rsplit("/", 1)[-1]
        tag = name[3:] if name.startswith("bt_") else name
        tag = tag.replace(".json", "")
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
        # Exit 1, not 0. This said "this is not a pass" and then exited 0,
        # which is the fail-open shape of bugs 9, 12 and 13 reappearing in
        # the tool written to catch them: a verifier that verified nothing
        # must not report success to whatever is reading its status.
        print("No usable rows: nothing was checked, so nothing is verified.")
        return 1

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
        if len(d) < 2:
            continue
        gross = [1.0 + v / 100.0 for v in d.values()]
        lo, hi = min(gross), max(gross)
        if lo <= 0:
            bad += 1
            print(f"  IMPOSSIBLE {sym}: a buy-and-hold of {min(d.values()):.2f} "
                  f"means the price reached zero.")
            continue
        spread = hi / lo - 1.0
        detail = "  ".join(f"{k}={v:.2f}" for k, v in sorted(d.items()))
        if spread > REL_TOL:
            bad += 1
            print(f"  DISAGREES {sym}: buy-and-hold spans {spread:.1%} across "
                  f"runs, over the {REL_TOL:.0%} drift allowance -- {detail}")
        elif spread > REL_TOL / 5:
            print(f"  drift     {sym:<18} {spread:.1%}, within allowance -- "
                  f"{detail}")

    print(f"\n{bad} problem(s) found." if bad else "\nBoth checks clean.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "bt_*.json"))
