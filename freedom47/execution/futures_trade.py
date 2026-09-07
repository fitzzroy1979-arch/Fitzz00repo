#!/usr/bin/env python3
"""Open a simulated leveraged futures position. Requires a y/N approval.

Paper only. No exchange is contacted, no real leveraged order is placed, and no
funds move — this build is TradingView-data-only. The position is tracked in
`.00fitzz/futures.json` so you can watch margin, PnL and liquidation behave.

    python execution/futures_trade.py --symbol XRPUSD --direction long \\
        --leverage 5 --margin 100

    # offline, when TradingView is not running:
    python execution/futures_trade.py --symbol XRPUSD --direction long \\
        --leverage 5 --margin 100 --entry-price 1.40

Approval rule (CLAUDE.md): opening a position changes the paper portfolio, so
it needs an explicit y/N on that invocation. There is no --yes flag, nothing is
remembered between runs, and the script refuses when stdin is not a TTY — which
is what keeps it unreachable from webhooks, cron and directive chains.
"""

import argparse
import datetime as dt
import json
import sys

import _common as C
import _futures_state as F


def build_position(symbol, direction, leverage, margin, entry):
    """The position dict cmd_futures_trade builds (L1444-1458), verbatim maths."""
    sign = 1 if direction == "long" else -1
    notional = margin * leverage
    quantity = notional / entry
    # Approximate isolated-margin liquidation: a 1/leverage adverse move wipes
    # the margin. Ignores fees and maintenance margin.
    liq = entry * (1 - sign * (1 / leverage))

    now = dt.datetime.now()
    return {
        "id": "F" + now.strftime("%m%d%H%M%S") + f"{now.microsecond // 1000:03d}",
        "symbol": symbol,
        "direction": direction,
        "leverage": leverage,
        "margin": round(margin, 2),
        "notional": round(notional, 2),
        "quantity": quantity,
        "entry_price": entry,
        "liq_price": round(liq, 6),
        "opened_at": now.isoformat(timespec="seconds"),
        "mode": "SIMULATED",
    }


def summarise(pos):
    return [
        "┌─ SIMULATED FUTURES POSITION (paper — no real order placed) ──",
        f"│  {pos['direction'].upper()} {pos['symbol']}  {pos['leverage']:g}x  "
        f"margin ${pos['margin']:g}",
        f"│  entry ${pos['entry_price']:g}   notional ${pos['notional']:g}   "
        f"qty {pos['quantity']:.6g}",
        f"│  est. liquidation ${pos['liq_price']:.6g}  "
        f"(approx; no fees/maintenance margin)",
        f"│  state: {F.FUTURES_STATE}",
        "└──────────────────────────────────────────────────────────────",
    ]


def approve(pos):
    """Interactive y/N. True only on an explicit yes typed at a TTY."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("! refusing to open a paper futures position without an interactive "
              "approval prompt (stdin is not a TTY).\n"
              "  Every paper trade needs an explicit y/N on that invocation — no "
              "--yes flag, no stored consent — which is what keeps this "
              "unreachable from webhooks, cron and directive chains.\n"
              "  Run it yourself in a terminal to approve.", file=sys.stderr)
        return False
    for line in summarise(pos):
        print(line)
    try:
        answer = input("Open this simulated position? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\naborted.", file=sys.stderr)
        return False
    return answer in ("y", "yes")


def build_parser():
    p = argparse.ArgumentParser(
        description="Open a simulated leveraged position. Interactive y/N required.")
    p.add_argument("--symbol", required=True, help="Symbol to trade.")
    p.add_argument("--direction", required=True, choices=["long", "short"])
    p.add_argument("--leverage", required=True, type=float, help="Leverage multiple, e.g. 5.")
    p.add_argument("--margin", required=True, type=float,
                   help="Margin in quote currency.")
    p.add_argument("--entry-price", type=float, default=None,
                   help="Override the mark price (use when TradingView is offline).")
    p.add_argument("--dry-run", action="store_true",
                   help="Show the position and exit without prompting or writing.")
    p.add_argument("--tv-repo", help="Path to the tradingview-mcp checkout.")
    p.add_argument("--settle", type=float, default=1.5, help="Chart settle seconds.")
    p.add_argument("-v", "--verbose", action="store_true", help="Echo bridge commands.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.leverage < 1:
        print("! --leverage must be >= 1.", file=sys.stderr)
        return 2
    if args.margin <= 0:
        print("! --margin must be positive.", file=sys.stderr)
        return 2

    symbol = C.normalize_symbol(args.symbol)

    entry = args.entry_price
    if entry is None:
        bridge = C.get_bridge(tv_repo=args.tv_repo, settle=args.settle,
                              verbose=args.verbose)
        entry = F._mark_price(bridge, symbol)
    if not entry:
        print(f"! no mark price for {symbol} (is TradingView running?). "
              f"Pass --entry-price P to open a paper position offline.",
              file=sys.stderr)
        return 1

    pos = build_position(symbol, args.direction, args.leverage, args.margin, entry)

    if args.dry_run:
        for line in summarise(pos):
            print(line)
        print("\ndry run — nothing was opened.")
        return 0

    if not approve(pos):
        print("not opened.", file=sys.stderr)
        return 1

    # Re-read state at write time and settle the id against it. Ids are
    # timestamp-derived to the millisecond, so anything opening positions in a
    # loop can collide -- and futures_close.py selects by id.
    state = F._load_futures()
    asked = pos["id"]
    F.ensure_unique_id(pos, state)
    if pos["id"] != asked:
        print(f"! id {asked} was already taken; using {pos['id']}.", file=sys.stderr)
    state["positions"].append(pos)
    F._save_futures(state)

    print(f"opened {pos['id']} — tracked in {F.FUTURES_STATE}")
    print("No real order was placed and no funds were touched.")
    print(json.dumps(pos, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
