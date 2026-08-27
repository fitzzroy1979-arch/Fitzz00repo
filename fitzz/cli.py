"""Unified command dispatcher for the fitzz toolkit.

Usage:
    fitzz <tool> [tool arguments...]
    python -m fitzz <tool> [tool arguments...]

Tools:
    trade   Run the 00fitzz trading CLI (backtest/learn/research/simulate/...).
    sweep   Run the sweep-significance analysis (Reality Check / SPA).

The first argument selects the tool; everything after it is forwarded verbatim
to that tool's own argument parser, so every existing flag keeps working, e.g.:

    fitzz trade --simulate --watchlist --days 7 --interval 1h
    fitzz sweep prices.csv --family ma_cross --objective sharpe
"""

import sys

TOOLS = {
    "trade": ("fitzz.trading", "the 00fitzz trading CLI"),
    "sweep": ("fitzz.sweep", "sweep-significance analysis"),
}

# Friendly aliases so muscle memory / old names still route correctly.
ALIASES = {
    "trading": "trade",
    "00fitzz": "trade",
    "significance": "sweep",
    "sweep_significance": "sweep",
}


def _usage(stream=sys.stderr):
    print("fitzz — combined quant toolkit\n", file=stream)
    print("usage: fitzz <tool> [arguments...]\n", file=stream)
    print("tools:", file=stream)
    for name, (_, desc) in TOOLS.items():
        print(f"  {name:7} {desc}", file=stream)
    print("\nRun `fitzz <tool> --help` for a tool's own options.", file=stream)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        _usage(sys.stdout if argv else sys.stderr)
        return 0 if argv else 2

    tool = argv[0]
    tool = ALIASES.get(tool, tool)
    if tool not in TOOLS:
        print(f"fitzz: unknown tool {argv[0]!r}\n", file=sys.stderr)
        _usage()
        return 2

    module_name = TOOLS[tool][0]
    import importlib
    mod = importlib.import_module(module_name)
    # Forward the remaining args to the tool's own main(argv).
    result = mod.main(argv[1:])
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
