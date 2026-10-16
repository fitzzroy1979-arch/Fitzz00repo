#!/usr/bin/env python3
"""Show open simulated futures positions with margin, PnL and liquidation.

Read-only: opens nothing, closes nothing, writes no state. No approval needed
because nothing changes.

    python execution/futures_portfolio.py
    python execution/futures_portfolio.py --json --out .tmp/futures.json

Marks come from the TradingView bridge first. When it gives nothing, the
position falls back to BTCC's public endpoint via fetch_btcc_prices.py — no
account, no key. Instruments BTCC flags `price_suspect` (it quotes zero on
roughly half its book despite real volume) are skipped rather than used, so a
zero never reaches a PnL.

Every mark is tagged with where it came from — `[btcc]` in the table,
`mark_source` in the JSON — because BTCC quotes its own perpetual book while
positions were priced at entry from TradingView, and the basis between the two
lands in unrealised PnL. Mixed marks are indicative, not exact. `--no-fallback`
turns it off; when nothing supplies a mark the position still prints with entry
and liquidation price and the total is reported unavailable rather than
silently understated.
"""

import argparse
import json
import sys

import _common as C
import _futures_state as F


def btcc_marks(symbols):
    """{symbol: price} from BTCC's public endpoint, for symbols it quotes well.

    Used only where the bridge gave nothing. Instruments BTCC flags as
    price_suspect -- it quotes zero on roughly half its book despite real
    volume -- are left out rather than returned as a zero.
    """
    try:
        import fetch_btcc_prices as B
    except ImportError:
        return {}
    try:
        instruments, _ = B.fetch_all()
    except Exception as e:  # network, shape change, anything
        print(f"! BTCC fallback unavailable: {e}", file=sys.stderr)
        return {}

    by_name = {i["name"]: i for i in instruments}
    out = {}
    for sym in symbols:
        name = B.btcc_symbol(sym, instruments)
        if not name:
            continue
        inst = by_name[name]
        if B.is_price_suspect(inst):
            print(f"! BTCC quotes {name} at zero (price_suspect) — not using it "
                  f"as a mark for {sym}.", file=sys.stderr)
            continue
        price = inst.get("last") or inst.get("index")
        if price and price > 0:
            out[sym] = (float(price), name)
    return out


def collect(bridge, fallback=True):
    """[(position, mark, pnl, source)], plus totals. mark/pnl may be None.

    `source` is "tradingview", "btcc" or None, so a mixed portfolio is legible
    rather than silently blended.
    """
    positions = F._load_futures()["positions"]

    marks = {}
    for p in positions:
        marks[p["symbol"]] = (F._mark_price(bridge, p["symbol"]) if bridge else None,
                              "tradingview")

    if fallback:
        need = [s for s, (m, _) in marks.items() if not m]
        if need:
            for sym, (price, name) in btcc_marks(need).items():
                marks[sym] = (price, "btcc")

    rows, total_margin, total_pnl, pnl_complete = [], 0.0, 0.0, True
    for p in positions:
        mark, source = marks.get(p["symbol"], (None, None))
        if not mark:
            source = None
        upnl = F.unrealized(p, mark)
        if upnl is None:
            pnl_complete = False
        else:
            total_pnl += upnl
        total_margin += p["margin"]
        rows.append((p, mark, upnl, source))
    return rows, total_margin, total_pnl, pnl_complete


def print_table(rows, total_margin, total_pnl, pnl_complete):
    """Terminal output -- from cmd_futures_portfolio (L1500-1517)."""
    print("Open paper futures positions:")
    for p, mark, upnl, source in rows:
        head = (f"  {p['id']}  {p['direction'].upper():<5} {p['symbol']:<10} "
                f"{p['leverage']:g}x  margin ${p['margin']:g}")
        if mark is None:
            print(head + f"  entry ${p['entry_price']:g}  "
                         f"liq ${p['liq_price']:g}  (mark n/a)")
            continue
        pnl_pct = upnl / p["margin"] * 100 if p["margin"] else 0.0
        warn = "  ⚠ PAST LIQ" if F.past_liquidation(p, mark) else ""
        tag = "" if source == "tradingview" else f"  [{source}]"
        print(head + f"  mark ${mark:g}{tag}  uPnL ${upnl:+.2f} "
                     f"({pnl_pct:+.1f}% on margin)  liq ${p['liq_price']:g}{warn}")
    tail = f"${total_pnl:+.2f}" if pnl_complete else "n/a (some marks unavailable)"
    print(f"  ── total margin ${total_margin:.2f}   total uPnL {tail}")

    if any(s == "btcc" for *_, s in rows):
        print("\n  [btcc] marks came from BTCC's perpetual book, not TradingView. "
              "Positions\n  priced at entry from a different feed, so basis "
              "between the two shows up\n  in unrealised PnL. Treat these as "
              "indicative.")


def build_parser():
    p = argparse.ArgumentParser(
        description="Show open simulated futures positions. Read-only.")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    p.add_argument("--out", help="Also write the JSON here.")
    p.add_argument("--offline", action="store_true",
                   help="Skip the bridge entirely; show entries and liquidation "
                        "prices with no marks.")
    p.add_argument("--no-fallback", action="store_true",
                   help="Do not fall back to BTCC's public endpoint when the "
                        "bridge gives no mark.")
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

    rows, total_margin, total_pnl, pnl_complete = collect(
        bridge, fallback=not args.no_fallback)

    payload = {
        "positions": [
            {**p, "mark": mk, "mark_source": src,
             "unrealized_pnl": round(u, 2) if u is not None else None,
             "past_liquidation": F.past_liquidation(p, mk)}
            for (p, mk, u, src) in rows
        ],
        "total_margin": round(total_margin, 2),
        "total_unrealized_pnl": round(total_pnl, 2) if pnl_complete else None,
        "marks_complete": pnl_complete,
        "mark_sources": sorted({s for *_, s in rows if s}),
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
