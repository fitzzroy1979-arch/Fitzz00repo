#!/usr/bin/env python3
"""Show open simulated futures positions with margin, PnL and liquidation.

Read-only: opens nothing, closes nothing, writes no state. No approval needed
because nothing changes.

    python execution/futures_portfolio.py
    python execution/futures_portfolio.py --json --out .tmp/futures.json

Marks come from the TradingView bridge. When it is unreachable the position
still prints with its entry and liquidation price and the mark shown as n/a —
the total is then reported as unavailable rather than silently understated.
"""

import argparse
import json
import sys

import _common as C
import _futures_state as F


def collect(bridge):
    """[(position, mark, unrealised_pnl)], plus totals. mark/pnl may be None."""
    positions = F._load_futures()["positions"]
    rows, total_margin, total_pnl, pnl_complete = [], 0.0, 0.0, True
    for p in positions:
        mark = F._mark_price(bridge, p["symbol"]) if bridge else None
        upnl = F.unrealized(p, mark)
        if upnl is None:
            pnl_complete = False
        else:
            total_pnl += upnl
        total_margin += p["margin"]
        rows.append((p, mark, upnl))
    return rows, total_margin, total_pnl, pnl_complete


def print_table(rows, total_margin, total_pnl, pnl_complete):
    """Terminal output -- from cmd_futures_portfolio (L1500-1517)."""
    print("Open paper futures positions:")
    for p, mark, upnl in rows:
        head = (f"  {p['id']}  {p['direction'].upper():<5} {p['symbol']:<10} "
                f"{p['leverage']:g}x  margin ${p['margin']:g}")
        if mark is None:
            print(head + f"  entry ${p['entry_price']:g}  "
                         f"liq ${p['liq_price']:g}  (mark n/a)")
            continue
        pnl_pct = upnl / p["margin"] * 100 if p["margin"] else 0.0
        warn = "  ⚠ PAST LIQ" if F.past_liquidation(p, mark) else ""
        print(head + f"  mark ${mark:g}  uPnL ${upnl:+.2f} "
                     f"({pnl_pct:+.1f}% on margin)  liq ${p['liq_price']:g}{warn}")
    tail = f"${total_pnl:+.2f}" if pnl_complete else "n/a (some marks unavailable)"
    print(f"  ── total margin ${total_margin:.2f}   total uPnL {tail}")


def build_parser():
    p = argparse.ArgumentParser(
        description="Show open simulated futures positions. Read-only.")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    p.add_argument("--out", help="Also write the JSON here.")
    p.add_argument("--offline", action="store_true",
                   help="Skip the bridge entirely; show entries and liquidation "
                        "prices with no marks.")
    p.add_argument("--tv-repo", help="Path to the tradingview-mcp checkout.")
    p.add_argument("--settle", type=float, default=1.5, help="Chart settle seconds.")
    p.add_argument("-v", "--verbose", action="store_true", help="Echo bridge commands.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not F._load_futures()["positions"]:
        print("No open (paper) futures positions.")
        return 0

    bridge = None
    if not args.offline:
        try:
            bridge = C.get_bridge(tv_repo=args.tv_repo, settle=args.settle,
                                  verbose=args.verbose)
        except SystemExit:
            raise
        except Exception as e:  # bridge construction should never sink the report
            print(f"! bridge unavailable ({e}); showing positions without marks.",
                  file=sys.stderr)

    rows, total_margin, total_pnl, pnl_complete = collect(bridge)

    payload = {
        "positions": [
            {**p, "mark": mk, "unrealized_pnl": round(u, 2) if u is not None else None,
             "past_liquidation": F.past_liquidation(p, mk)}
            for (p, mk, u) in rows
        ],
        "total_margin": round(total_margin, 2),
        "total_unrealized_pnl": round(total_pnl, 2) if pnl_complete else None,
        "marks_complete": pnl_complete,
    }

    if args.out:
        path = C.write_json(args.out, payload)
        print(f"portfolio -> {path}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print_table(rows, total_margin, total_pnl, pnl_complete)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
