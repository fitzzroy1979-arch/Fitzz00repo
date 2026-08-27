#!/usr/bin/env python3
"""Backward-compatible shim.

The sweep-significance tool now lives in the `fitzz` package as `fitzz.sweep`.
This file preserves the historical `python3 sweep_significance.py ...` entry
point; new code should prefer `python3 -m fitzz sweep ...` or `fitzz sweep`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fitzz.sweep import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
