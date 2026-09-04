#!/usr/bin/env python3
"""Shared helpers for the execution/ scripts.

Holds the things every other script needs: .env loading, the workspace paths,
the constants and interval tables lifted from the monolith, and access to the
TradingView bridge that supplies price data.

Nothing here makes an LLM call or writes a deliverable; it is import-only.
"""

import datetime as dt
import json
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

# execution/_common.py -> freedom47/
ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"          # intermediates, always regenerable
OUTPUT = ROOT / "output"     # deliverables
STATE = ROOT / "state"       # persistent local state (portfolio JSON)
ENV_FILE = ROOT / ".env"

# The fitzz package holding the un-migrated code. `freedom47/fitzz` is a symlink
# to the package at the repo root, so this resolves whether a script is run from
# inside freedom47/ or from the repo root.
PACKAGE_PARENT = ROOT


# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #

def load_env(path=ENV_FILE):
    """Read KEY=VALUE lines from .env into os.environ.

    Real environment variables win, so an export in the shell overrides the
    file. Missing file is not an error -- every caller has a default.
    """
    if not Path(path).exists():
        return {}
    loaded = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


def env(key, default=None):
    """Read a config value, loading .env on first use."""
    if not _ENV_LOADED:
        _load_once()
    return os.environ.get(key, default)


def env_float(key, default):
    try:
        return float(env(key, default))
    except (TypeError, ValueError):
        return float(default)


_ENV_LOADED = False


def _load_once():
    global _ENV_LOADED
    load_env()
    _ENV_LOADED = True


def watchlist():
    """Symbols from WATCHLIST in .env, as a list."""
    raw = env("WATCHLIST", "") or ""
    return [s.strip() for s in raw.split(",") if s.strip()]


# --------------------------------------------------------------------------- #
# Constants -- moved verbatim from fitzz/trading.py
# --------------------------------------------------------------------------- #

# Ceiling on a single ohlcv read. The tv bridge enforces its own cap in
# core/data.js (MAX_OHLCV_BARS); keep the two in step.
MAX_BARS = 5000

# Starting cash for backtest and simulation runs when none is given.
DEFAULT_STARTING_CASH = 3000.0

# Map friendly interval values to TradingView resolutions.
INTERVAL_TO_TV = {
    "1m": "1", "1min": "1",
    "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240",
    "1d": "1D", "1day": "1D",
    "1w": "1W", "1week": "1W",
    "1mo": "1M",
}

# Approx minutes per bar, used to turn a period into a bar count.
INTERVAL_MINUTES = {
    "1": 1, "5": 5, "15": 15, "30": 30,
    "60": 60, "120": 120, "240": 240,
    "1D": 1440, "1W": 1440 * 7, "1M": 1440 * 30,
}

# Bars per year per resolution, for annualising backtest metrics.
BARS_PER_YEAR = {
    res: (365 * 24 * 60) / minutes for res, minutes in INTERVAL_MINUTES.items()
}


# --------------------------------------------------------------------------- #
# Period / interval helpers + shared maths -- moved verbatim from
# fitzz/trading.py. `sma` lives here because both run_backtest.py and
# run_simulation.py use it.
# --------------------------------------------------------------------------- #

def resolve_interval(interval):
    key = interval.strip().lower()
    if key in INTERVAL_TO_TV:
        return INTERVAL_TO_TV[key]
    # Allow raw TradingView resolutions to pass through (e.g. "1D", "60").
    if interval in INTERVAL_MINUTES:
        return interval
    raise ValueError(f"Unknown interval '{interval}'. Try one of: "
                     f"{', '.join(sorted(INTERVAL_TO_TV))}")


def period_to_bars(period, tv_resolution):
    """Turn '1y' / '6mo' / '90d' into an approximate bar count for the interval."""
    p = period.strip().lower()
    units = {"y": 525600, "mo": 43200, "w": 10080, "d": 1440, "h": 60}
    # Split leading digits from the trailing unit (e.g. "6mo" -> "6", "mo").
    i = 0
    while i < len(p) and p[i].isdigit():
        i += 1
    num, unit = p[:i], p[i:]
    if not num or unit not in units:
        raise ValueError(f"Unknown period '{period}'. Try 1y, 6mo, 90d, 30d, 48h.")
    total_minutes = int(num) * units[unit]
    per_bar = INTERVAL_MINUTES.get(tv_resolution, 1440)
    bars = max(2, total_minutes // per_bar)
    return min(bars, MAX_BARS), bars


def days_to_bars(days, tv_resolution):
    """Turn a day count into an approximate bar count for the interval."""
    per_bar = INTERVAL_MINUTES.get(tv_resolution, 1440)
    bars = max(2, int(days * 1440 / per_bar))
    return min(bars, MAX_BARS), bars


def fmt_time(t):
    """Bar timestamp -> 'YYYY-MM-DD'. Moved verbatim from fitzz/trading.py."""
    if t is None:
        return None
    try:
        t = float(t)
        if t > 1e12:      # milliseconds
            t /= 1000.0
        return dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return str(t)


def sma(values, window):
    """Simple moving average; None until enough data is present."""
    out = [None] * len(values)
    if window <= 0:
        return out
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= window:
            run -= values[i - window]
        if i >= window - 1:
            out[i] = run / window
    return out


# --------------------------------------------------------------------------- #
# Symbols
# --------------------------------------------------------------------------- #

def normalize_symbol(symbol):
    """Turn a Yahoo-style ticker into one TradingView accepts.

    The watchlist and the directives are written in Yahoo form ('XRP-USD')
    because that is what the framework was drafted against; the price source is
    TradingView, which wants 'XRPUSD'. An already-qualified symbol
    ('BINANCE:XRPUSD') is passed through untouched.
    """
    s = str(symbol).strip().upper()
    if ":" in s:
        return s
    if s.endswith("-USD"):
        return s[:-4] + "USD"
    return s.replace("-", "")


# --------------------------------------------------------------------------- #
# TradingView bridge
# --------------------------------------------------------------------------- #

def get_bridge(tv_repo=None, settle=1.5, verbose=False):
    """Return a TradingViewBridge.

    The bridge is imported from the fitzz package rather than copied in. It is
    ~240 lines carrying two hard-won fixes -- the stale-chart fingerprint check
    and the tempfile-instead-of-pipe stdout read -- and a second copy would drift
    from the one `fitzz trade` still uses. See execution/README.md.
    """
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))
    try:
        from fitzz.trading import DEFAULT_TV_REPO, TradingViewBridge
    except ImportError as e:
        raise SystemExit(
            f"Could not import the fitzz package from {PACKAGE_PARENT}: {e}\n"
            f"freedom47/fitzz should be a symlink to the package at the repo root."
        )
    return TradingViewBridge(repo=tv_repo or DEFAULT_TV_REPO,
                             settle=settle, verbose=verbose)


def bridge_error():
    """The bridge's exception type, importable without pulling in the bridge."""
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))
    from fitzz.trading import BridgeError
    return BridgeError


# --------------------------------------------------------------------------- #
# File I/O
# --------------------------------------------------------------------------- #

def write_json(path, payload):
    """Write JSON to `path`, creating parent directories. Returns the path."""
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_text(path, text):
    """Write text to `path`, creating parent directories. Returns the path."""
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read_json(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    return json.loads(path.read_text(encoding="utf-8"))
