#!/usr/bin/env python3
"""Backward-compatible shim.

The trading CLI now lives in the `fitzz` package as `fitzz.trading`. This file
preserves the historical `python3 00fitzz.py ...` entry point; new code should
prefer `python3 -m fitzz trade ...` or the `fitzz trade` console script.
"""

import sys
from pathlib import Path

# Ensure the package is importable when run as a loose script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fitzz.trading import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
