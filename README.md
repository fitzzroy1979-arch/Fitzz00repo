# fitzz

A combined toolkit for TradingView-data-backed quant work. Two tools, one CLI.

| Tool | Module | What it does |
|------|--------|--------------|
| **trade** | `fitzz.trading` | The 00fitzz trading CLI — backtest, LLM parameter learning, Perplexity research, walk-forward paper simulation, and paper trade/futures stubs. Reads OHLCV/watchlist data from a running TradingView Desktop via the local `tradingview-mcp` bridge. |
| **sweep** | `fitzz.sweep` | Sweep-significance analysis — prices the selection bias of a parameter sweep's best config with White's Reality Check and Hansen's SPA p-values. |

## Layout

```
.
├── fitzz/                 # the combined package
│   ├── __init__.py
│   ├── __main__.py        # enables `python -m fitzz`
│   ├── cli.py             # unified dispatcher (trade | sweep)
│   ├── trading.py         # the trading CLI (was 00fitzz.py)
│   └── sweep.py           # sweep significance (was sweep_significance.py)
├── 00fitzz.py             # back-compat shim → fitzz.trading
├── sweep_significance.py  # back-compat shim → fitzz.sweep
├── tradingview-mcp/       # the data bridge (separate git repo; not committed here)
├── pyproject.toml
└── requirements.txt
```

## Usage

Unified CLI (no install needed — run from the repo root):

```bash
python3 -m fitzz trade --simulate --watchlist --days 7 --interval 1h
python3 -m fitzz sweep prices.csv --family ma_cross --objective sharpe
```

Or install the `fitzz` console script:

```bash
pip install -e .
fitzz trade --backtest --symbol BTCUSD --period 1y --interval 1d
fitzz sweep prices.csv --family ma_cross
```

The original entry points still work unchanged:

```bash
python3 00fitzz.py --simulate --watchlist --days 7 --interval 1h
python3 sweep_significance.py prices.csv --family ma_cross
```

Each tool keeps its own flags — run `python3 -m fitzz trade --help` or
`python3 -m fitzz sweep --help` for the full option list.

## Data source

The `trade` tool needs **TradingView Desktop** running with the Chrome DevTools
port enabled, plus the sibling `tradingview-mcp` checkout:

```bash
/Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=9222
```

Give the app a few seconds to warm up before the first data read.

## Dedicated agents

Per-domain Claude Code subagents live in `.claude/agents/` — a trading agent, a
sweep/stats agent, and a TradingView-bridge agent — so work can be routed to a
specialist scoped to just that part of the codebase.
