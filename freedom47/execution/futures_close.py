#!/usr/bin/env python3
"""Close simulated futures positions and realise their PnL. Requires y/N.

Paper only — no exchange is contacted and no funds move. Closed positions are
removed from `.00fitzz/futures.json` and appended to
`.00fitzz/futures_closed.log`.

    python execution/futures_close.py --target F0904203347123
    python execution/futures_close.py --target XRPUSD
    python execution/futures_close.py --all

Approval rule (CLAUDE.md): closing changes the paper portfolio and realises a
number, so it needs an explicit y/N on that invocation — no --yes flag, no
stored consent, and refused when stdin is not a TTY.

When the bridge is unreachable the close price falls back to the entry price,
which realises exactly zero PnL. That is the monolith's behaviour; it is
flagged loudly rather than silently booked, because a zero is a real number in
the log and it is not the one the market would have given you.
"""

import argparse
import datetime as dt
import json
import sys

import _common as C
import _futures_state as F


def select(positions, target, close_all):
    """Positions matching `target` (id or symbol), or all of them."""
    if close_all:
        return list(positions)
    return [p for p in positions if target in (p["symbol"], p["id"])]


def realise(positions, bridge):
    """Build the realised records. Returns (records, used_fallback_symbols)."""
    records, fallback = [], []
    for p in positions:
        mark = F._mark_price(bridge, p["symbol"]) if bridge else None
        if not mark:
            mark = p["entry_price"]
            fallback.append(p["id"])
        sign = 1 if p["direction"] == "long" else -1
        pnl = sign * (mark - p["entry_price"]) * p["quantity"]
        records.append({**p, "close_price": mark, "realized_pnl": round(pnl, 2),
                        "closed_at": dt.datetime.now().isoformat(timespec="seconds")})
    return records, fallback


def summarise(records, fallback):
    lines = ["┌─ CLOSING SIMULATED POSITIONS (paper — no real order) ────────"]
    for r in records:
        lines.append(f"│  {r['id']}  {r['direction'].upper():<5} {r['symbol']:<10} "
                     f"entry ${r['entry_price']:g} → close ${r['close_price']:g}  "
                     f"realized ${r['realized_pnl']:+.2f}")
    total = sum(r["realized_pnl"] for r in records)
    lines.append(f"│  total realized ${total:+.2f}")
    if fallback:
        lines.append("│")
        lines.append(f"│  ! no live mark for {len(fallback)} position(s) — closing at "
                     f"ENTRY price,")
        lines.append("│    which realises exactly $0.00 for them. Start TradingView "
                     "for a real mark.")
    lines.append("└──────────────────────────────────────────────────────────────")
    return lines


def approve(records, fallback):
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("! refusing to close a paper position without an interactive approval "
              "prompt (stdin is not a TTY).\n"
              "  Closing realises PnL and rewrites the portfolio, so it needs an "
              "explicit y/N on that invocation — no --yes flag, no stored consent.\n"
              "  Run it yourself in a terminal to approve.", file=sys.stderr)
        return False
    for line in summarise(records, fallback):
        print(line)
    try:
        answer = input(f"Close {len(records)} position(s)? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\naborted.", file=sys.stderr)
        return False
    return answer in ("y", "yes")


def build_parser():
    p = argparse.ArgumentParser(
        description="Close simulated futures positions. Interactive y/N required.")
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--target", help="Position id or symbol to close.")
    sel.add_argument("--all", action="store_true", dest="close_all",
                     help="Close every open position.")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would close and exit without prompting or writing.")
    p.add_argument("--offline", action="store_true",
                   help="Skip the bridge; close at entry price (realises $0).")
    p.add_argument("--tv-repo", help="Path to the tradingview-mcp checkout.")
    p.add_argument("--settle", type=float, default=1.5, help="Chart settle seconds.")
    p.add_argument("-v", "--verbose", action="store_true", help="Echo bridge commands.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    state = F._load_futures()
    positions = state["positions"]
    if not positions:
        print("No open positions to close.")
        return 0

    to_close = select(positions, args.target, args.close_all)
    if not to_close:
        print(f"Nothing to close (no open position matching {args.target!r}).")
        return 1

    bridge = None
    if not args.offline:
        try:
            bridge = C.get_bridge(tv_repo=args.tv_repo, settle=args.settle,
                                  verbose=args.verbose)
        except SystemExit:
            raise
        except Exception as e:
            print(f"! bridge unavailable ({e}); will close at entry price.",
                  file=sys.stderr)

    records, fallback = realise(to_close, bridge)

    if args.dry_run:
        for line in summarise(records, fallback):
            print(line)
        print("\ndry run — nothing was closed.")
        return 0

    if not approve(records, fallback):
        print("not closed.", file=sys.stderr)
        return 1

    closed_ids = {r["id"] for r in records}
    state["positions"] = [p for p in positions if p["id"] not in closed_ids]
    F._save_futures(state)
    log = F.log_closed(records)

    total = sum(r["realized_pnl"] for r in records)
    print(f"closed {len(records)} position(s), total realized ${total:+.2f}")
    print(f"logged to {log}")
    print("No real order was placed and no funds were touched.")
    print(json.dumps(records, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
