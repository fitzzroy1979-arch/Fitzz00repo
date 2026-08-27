"""fitzz — a combined toolkit for TradingView-data-backed quant work.

Two tools live under one roof:

  * ``fitzz.trading`` — the 00fitzz trading CLI (backtest / learn / research /
    simulate / paper-trade / paper-futures), driven by the local tradingview-mcp
    bridge.
  * ``fitzz.sweep`` — sweep-significance tooling that prices the selection bias
    of a parameter sweep's best config (White Reality Check + Hansen SPA).

Run the unified CLI with ``python -m fitzz <tool> ...`` (or the ``fitzz`` console
script once installed). Each tool keeps its own argument parser, exposed as a
``main(argv)`` function.
"""

__version__ = "0.1.0"
__all__ = ["trading", "sweep"]
