#!/usr/bin/env python3
"""Record an approved paper trade in the order log. Requires a y/N approval.

This is the only script in execution/ that writes a trade, and it is a **stub**
by design: it appends the intent to `.00fitzz/orders.log` and stops. No order is
placed, no exchange is contacted, no funds move. This build is
TradingView-data-only.

    python execution/propose_trade.py --symbol XRP-USD --action buy --amount 50
    python execution/log_trade.py --proposal .tmp/proposed_trade.json

Approval rule (non-negotiable, CLAUDE.md): every paper trade needs explicit
approval on that invocation. It is an interactive y/N prompt — there is
deliberately no --yes flag, nothing is remembered between runs, and the script
refuses outright when stdin is not a TTY. That last part is what keeps it
unreachable from a webhook, a cron job or a directive chain: those have no
terminal, so they cannot answer, so nothing is written.
"""

import argparse
import json
import sys

import _common as C


def summarise(order):
    """The confirmation block the user approves, from cmd_trade's printout."""
    price = order.get("ref_price")
    px = f"${price}" if price else "unavailable"
    units = f"{order['est_units']} units" if order.get("est_units") else "n/a"
    return [
        "┌─ SIMULATED ORDER (no real trade placed) ──────────────────────",
        f"│  {str(order.get('action', '?')).upper()} {order.get('amount')} "
        f"of {order.get('symbol')}",
        f"│  reference price: {px}   est. size: {units}",
        f"│  priced at: {order.get('ts')}",
        f"│  will be logged to: {C.ORDER_LOG}",
        "└──────────────────────────────────────────────────────────────",
    ]


def approve(order):
    """Interactive y/N. Returns True only on an explicit yes typed at a TTY."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("! refusing to log a paper trade without an interactive approval "
              "prompt (stdin is not a TTY).\n"
              "  Every paper trade needs an explicit y/N on that invocation — "
              "there is no --yes flag and no stored consent, which is what keeps "
              "this unreachable from webhooks, cron and directive chains.\n"
              "  Run it yourself in a terminal to approve.", file=sys.stderr)
        return False

    for line in summarise(order):
        print(line)
    try:
        answer = input("Log this simulated order? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\naborted.", file=sys.stderr)
        return False
    return answer in ("y", "yes")


def append_to_log(order):
    """Append one JSON line to the order log. Moved from cmd_trade (L678-680)."""
    C.ORDER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with C.ORDER_LOG.open("a") as fh:
        fh.write(json.dumps(order) + "\n")
    return C.ORDER_LOG


def build_parser():
    p = argparse.ArgumentParser(
        description="Record an approved paper trade. Interactive y/N required.")
    p.add_argument("--proposal", required=True, metavar="FILE",
                   help="Proposal JSON written by propose_trade.py.")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be logged and exit without prompting "
                        "or writing.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        order = C.read_json(args.proposal)
    except (OSError, ValueError) as e:
        print(f"! {args.proposal}: {e}", file=sys.stderr)
        return 1

    missing = [k for k in ("symbol", "action", "amount") if not order.get(k)]
    if missing:
        print(f"! {args.proposal}: missing {', '.join(missing)} — "
              f"is this a propose_trade.py proposal?", file=sys.stderr)
        return 1

    if args.dry_run:
        for line in summarise(order):
            print(line)
        print("\ndry run — nothing was logged.")
        return 0

    if not approve(order):
        print("not logged.", file=sys.stderr)
        return 1

    path = append_to_log(order)
    print(f"logged to {path}")
    print("No real order was placed and no funds were touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
