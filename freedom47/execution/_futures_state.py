#!/usr/bin/env python3
"""Read/write the paper futures portfolio. Import-only; no CLI, no bridge.

State lives at `.00fitzz/futures.json` and the realised-trade log at
`.00fitzz/futures_closed.log`, both at the repo root — decided 2026-09-04 so
`fitzz trade --futures-*` and the extracted scripts share one portfolio rather
than drifting into two. `_common.check_state_paths()` asserts they still agree.

Nothing here is a trade. Opening and closing positions live in
futures_trade.py and futures_close.py, both of which require a y/N approval.
"""

import json

import _common as C


# --------------------------------------------------------------------------- #
# State -- moved verbatim from fitzz/trading.py (L1389-1401), with the module
# constant swapped for _common's (same resolved path; see check_state_paths).
# --------------------------------------------------------------------------- #

FUTURES_STATE = C.FUTURES_STATE
FUTURES_CLOSED_LOG = C.FUTURES_CLOSED_LOG


def _load_futures():
    if FUTURES_STATE.exists():
        try:
            return json.loads(FUTURES_STATE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"positions": []}


def _save_futures(state):
    FUTURES_STATE.parent.mkdir(parents=True, exist_ok=True)
    FUTURES_STATE.write_text(json.dumps(state, indent=2))


def _mark_price(bridge, symbol):
    """Best-effort current price from the tv bridge; None if unavailable."""
    BridgeError = C.bridge_error()
    try:
        q = bridge.get_quote(symbol)
    except BridgeError:
        return None
    if isinstance(q, dict):
        for k in ("price", "last", "close", "lp"):
            v = q.get(k)
            if v:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
    return None


# --------------------------------------------------------------------------- #
# Helpers the three futures scripts share
# --------------------------------------------------------------------------- #

def log_closed(records):
    """Append realised positions to the closed log, one JSON object per line."""
    FUTURES_CLOSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FUTURES_CLOSED_LOG.open("a") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return FUTURES_CLOSED_LOG


def unrealized(position, mark):
    """Unrealised PnL for a position at `mark`, or None if there is no mark."""
    if not mark:
        return None
    sign = 1 if position["direction"] == "long" else -1
    return sign * (mark - position["entry_price"]) * position["quantity"]


def past_liquidation(position, mark):
    """True when `mark` has crossed the position's estimated liquidation price."""
    if not mark:
        return False
    if position["direction"] == "long":
        return mark <= position["liq_price"]
    return mark >= position["liq_price"]
