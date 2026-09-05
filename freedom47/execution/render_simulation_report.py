#!/usr/bin/env python3
"""Render a run_simulation.py payload as a report. Computes nothing.

Mirrors render_backtest_report.py: `--format text` reproduces the monolith's
terminal output, `--format md` (default) writes a Markdown deliverable to
`output/`. Every number comes from the input file.

    python execution/run_simulation.py --prices .tmp/xrp.json --out .tmp/sim.json
    python execution/render_simulation_report.py --results .tmp/sim.json
    python execution/render_simulation_report.py --results .tmp/sim.json --format text

The Markdown includes the per-trade blotter, which the terminal format only
prints for a single symbol. Use --no-blotter to leave it out of a long run.
"""

import argparse
import datetime as dt
import sys
from collections import Counter

import _common as C


# --------------------------------------------------------------------------- #
# Terminal format -- moved verbatim from fitzz/trading.py (L1351-1388)
# --------------------------------------------------------------------------- #

def _print_sim(res, blotter=False):
    sym = res["symbol"]
    if "error" in res:
        print(f"\n{sym}: error: {res['error']}")
        return
    halt = "   [HALTED: max-drawdown breached]" if res.get("halted") else ""
    print(f"\n{sym}  {res['strategy']}   {res['from']} → {res['to']}{halt}")
    print(f"  return {res['return_pct']:+.2f}%   buy&hold {res['buy_hold_pct']:+.2f}%   "
          f"trades {res['trades']}   win {res['win_rate_pct']:.1f}%   "
          f"maxDD {res['max_drawdown_pct']:.2f}%")
    if blotter and res.get("blotter"):
        print("  ── trades ──")
        for t in res["blotter"]:
            print(f"    {t['entry_date']} → {t['exit_date']}  size {t['size_pct']:>5.1f}%  "
                  f"{t['pnl_pct']:>+7.2f}%  ({t['reason']})")


def _print_sim_summary(results):
    ok = [r for r in results if "error" not in r]
    if not ok:
        print("\nNo symbols produced results.")
        return
    avg = sum(r["return_pct"] for r in ok) / len(ok)
    halted = sum(1 for r in ok if r.get("halted"))
    print("\n" + "═" * 64)
    print(f"  avg return {avg:+.2f}%   symbols {len(ok)}/{len(results)}   "
          f"halted {halted}")
    print("═" * 64)


# --------------------------------------------------------------------------- #
# Markdown format
# --------------------------------------------------------------------------- #

def render_markdown(payload, include_blotter=True):
    results = payload.get("results", [])
    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    lines = ["# Agent 47 — Paper Simulation Report", ""]

    strategy = payload.get("strategy") or (ok[0]["strategy"] if ok else "—")
    lines += [
        f"**Strategy:** `{strategy}`  ",
        f"**Starting capital:** ${payload.get('starting_capital', 0):,.2f}  ",
    ]
    if ok:
        intervals = sorted({r.get("interval") for r in ok if r.get("interval")})
        if intervals:
            lines.append(f"**Interval:** {', '.join(intervals)}  ")
        lines.append(f"**Window:** {ok[0].get('from')} → {ok[0].get('to')}  ")
    lines += [f"**Run at:** {payload.get('ran_at', '—')}", ""]

    if ok:
        lines += [
            "| Symbol | Return | Buy & hold | vs B&H | Trades | Win rate | Max DD | Final equity | Halted |",
            "|---|---:|---:|---:|---:|---:|---:|---:|:-:|",
        ]
        for r in sorted(ok, key=lambda x: x["return_pct"], reverse=True):
            edge = r["return_pct"] - r["buy_hold_pct"]
            lines.append(
                f"| `{r['symbol']}` | {r['return_pct']:+.2f}% | {r['buy_hold_pct']:+.2f}% | "
                f"{edge:+.2f} pp | {r['trades']} | {r['win_rate_pct']:.1f}% | "
                f"{r['max_drawdown_pct']:.2f}% | ${r['final_equity']:,.2f} | "
                f"{'**yes**' if r.get('halted') else 'no'} |"
            )
        lines.append("")

        avg = sum(r["return_pct"] for r in ok) / len(ok)
        avg_bh = sum(r["buy_hold_pct"] for r in ok) / len(ok)
        best = max(ok, key=lambda r: r["return_pct"])
        worst = min(ok, key=lambda r: r["return_pct"])
        halted = [r for r in ok if r.get("halted")]

        lines += [
            "## Summary", "",
            f"- **Average return:** {avg:+.2f}% vs buy & hold {avg_bh:+.2f}% "
            f"({avg - avg_bh:+.2f} pp)",
            f"- **Best:** `{best['symbol']}` at {best['return_pct']:+.2f}%",
            f"- **Worst:** `{worst['symbol']}` at {worst['return_pct']:+.2f}%",
            f"- **Symbols with results:** {len(ok)}/{len(results)}",
        ]
        if halted:
            names = ", ".join(f"`{r['symbol']}`" for r in halted)
            lines.append(f"- **Circuit breaker fired:** {len(halted)} symbol(s) — {names}. "
                         f"Equity fell past the max-drawdown limit; the position was "
                         f"liquidated and no further entries were taken.")
        else:
            lines.append("- **Circuit breaker:** never fired")

        # Why trades closed, across every symbol -- the simulation's own signal
        # about which risk control is actually doing the work.
        reasons = Counter(t["reason"] for r in ok for t in r.get("blotter", []))
        if reasons:
            lines += ["", "### Exit reasons", ""]
            total = sum(reasons.values())
            for reason, count in reasons.most_common():
                lines.append(f"- `{reason}` — {count} ({count / total * 100:.0f}%)")
        lines.append("")

        if include_blotter:
            for r in ok:
                if not r.get("blotter"):
                    continue
                lines += [f"## Blotter — {r['symbol']}", "",
                          "| Entry | Exit | Size | P&L | Cash | Reason |",
                          "|---|---|---:|---:|---:|---|"]
                for t in r["blotter"]:
                    lines.append(
                        f"| {t['entry_date']} | {t['exit_date']} | {t['size_pct']:.1f}% | "
                        f"{t['pnl_pct']:+.2f}% | ${t['pnl_cash']:+,.2f} | {t['reason']} |")
                lines.append("")

    if failed:
        lines += ["## Errors", ""]
        for r in failed:
            lines.append(f"- `{r.get('symbol', '?')}` — {r['error']}")
        lines.append("")

    if not ok:
        lines += ["No symbols produced results.", ""]

    lines += [
        "---", "",
        "*Walk-forward simulation on historical bars from TradingView. Paper only: "
        "no orders were placed, no exchange was contacted, and no funds were "
        "touched. Past performance of a rule on past data is not a prediction.*",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    p = argparse.ArgumentParser(
        description="Render a run_simulation.py payload as Markdown or a terminal table.")
    p.add_argument("--results", required=True, metavar="FILE",
                   help="JSON payload written by run_simulation.py.")
    p.add_argument("--format", choices=["md", "text"], default="md",
                   help="md writes a deliverable to output/; text prints the "
                        "monolith's output to stdout (default: md).")
    p.add_argument("--out", help="Where to write the Markdown. Default: "
                                 "output/simulation_<interval>_<date>.md")
    p.add_argument("--no-blotter", action="store_true",
                   help="Leave the per-trade blotter out of the Markdown.")
    p.add_argument("--stdout", action="store_true",
                   help="Also print the Markdown to stdout.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        payload = C.read_json(args.results)
    except (OSError, ValueError) as e:
        print(f"! {args.results}: {e}", file=sys.stderr)
        return 1

    results = payload.get("results")
    if results is None:
        print(f"! {args.results}: no 'results' key — is this a run_simulation.py payload?",
              file=sys.stderr)
        return 1

    if args.format == "text":
        # The monolith prints the blotter only for a single symbol.
        single = len(results) == 1
        for res in results:
            _print_sim(res, blotter=single)
        if not single:
            _print_sim_summary(results)
        return 0

    md = render_markdown(payload, include_blotter=not args.no_blotter)

    ok = [r for r in results if "error" not in r]
    intervals = {r.get("interval") for r in ok if r.get("interval")}
    tag = intervals.pop() if len(intervals) == 1 else "simulation"
    out = args.out or f"output/simulation_{tag}_{dt.date.today().isoformat()}.md"

    path = C.write_text(out, md)
    print(f"report -> {path}", file=sys.stderr)
    if args.stdout:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
