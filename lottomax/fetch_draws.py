#!/usr/bin/env python3
"""
fetch_draws.py -- pull Lotto Max draw history into a flat JSON file.

Scrapes the per-year archive pages on lottomaxnumbers.com (unofficial mirror of
the ILC results) and writes one record per draw:

    {"date": "2026-04-14", "main": [4, 13, 20, 31, 37, 43, 51], "bonus": 9}

The trap this script exists to avoid
------------------------------------
Lotto Max has changed its number pool mid-history. Until the 2026-04-10 draw it
was 7 balls from 1-50; from 2026-04-14 it is 7 from 1-52 (the same change took
the ticket from $5 to $6 and the jackpot cap from $80M to $90M). Any frequency
analysis that pools the two eras will report 51 and 52 as freezing cold, for the
sole reason that they did not exist for most of the window.

So the pool size is data, not a constant -- see MATRIX below. On parse, every
number is checked against the pool in force on its own draw date, and anything
out of range is a hard error rather than a silent bad row. If the game changes
again, the fix is one line in MATRIX; until someone makes it, this script
refuses to produce a file that would quietly skew the stats.

Usage
-----
  # last 3 calendar years plus the current one, to lottomax/draws.json
  python3 lottomax/fetch_draws.py

  # explicit years and destination
  python3 lottomax/fetch_draws.py --years 2019:2026 --out /tmp/draws.json

  # keep the raw HTML so analysis can be re-run offline
  python3 lottomax/fetch_draws.py --cache-dir /tmp/lm-html
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = "https://www.lottomaxnumbers.com/numbers/{year}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# (first draw date on which it applied, highest ball number). Keep sorted.
MATRIX = [
    ("1900-01-01", 50),
    ("2026-04-14", 52),
]

BALLS_PER_DRAW = 7

ROW_RE = re.compile(
    r'lotto-max-result-(\d{2})-(\d{2})-(\d{4})".*?<ul class="balls">(.*?)</ul>',
    re.S,
)
MAIN_RE = re.compile(r'class="ball ball">(\d+)<')
BONUS_RE = re.compile(r'class="ball bonus-ball">(\d+)<')


def pool_for(date):
    """Highest legal ball number for a draw on `date` (ISO string)."""
    pool = None
    for start, size in MATRIX:
        if date >= start:
            pool = size
    return pool


def fetch_year(year, cache_dir=None, timeout=30):
    """Return the archive HTML for `year`, using cache_dir when available."""
    path = os.path.join(cache_dir, f"{year}.html") if cache_dir else None
    if path and os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    req = urllib.request.Request(BASE.format(year=year), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    if path:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
    return html


def parse(html):
    """Yield draw dicts from one archive page."""
    for month, day, year, blob in ROW_RE.findall(html):
        main = sorted(int(x) for x in MAIN_RE.findall(blob))
        bonus = [int(x) for x in BONUS_RE.findall(blob)]
        yield {
            "date": f"{year}-{month}-{day}",
            "main": main,
            "bonus": bonus[0] if bonus else None,
        }


def validate(draws):
    """Raise on anything that would silently corrupt the frequency stats."""
    problems = []
    for d in draws:
        pool = pool_for(d["date"])
        if pool is None:
            problems.append(f"{d['date']}: no MATRIX entry covers this date")
            continue
        if len(d["main"]) != BALLS_PER_DRAW:
            problems.append(f"{d['date']}: {len(d['main'])} main balls, want {BALLS_PER_DRAW}")
        if len(set(d["main"])) != len(d["main"]):
            problems.append(f"{d['date']}: duplicate main balls {d['main']}")
        if d["bonus"] is None:
            problems.append(f"{d['date']}: missing bonus ball")
        for n in d["main"] + ([d["bonus"]] if d["bonus"] is not None else []):
            if not 1 <= n <= pool:
                problems.append(
                    f"{d['date']}: ball {n} outside 1-{pool}. If the game's number "
                    f"pool changed, add an entry to MATRIX in {os.path.basename(__file__)}"
                )
    if problems:
        raise SystemExit(
            "refusing to write draws.json -- {} problem(s):\n  {}".format(
                len(problems), "\n  ".join(problems[:20])
            )
        )


def year_range(spec, today):
    if spec:
        lo, _, hi = spec.partition(":")
        return list(range(int(lo), int(hi or lo) + 1))
    return list(range(today.year - 3, today.year + 1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_argument_group("source")
    src.add_argument("--years", help="year or LO:HI range (default: last 3 plus current)")
    src.add_argument("--cache-dir", help="store/reuse raw HTML here for offline re-runs")
    src.add_argument("--timeout", type=float, default=30.0, help="per-request timeout (s)")
    out = p.add_argument_group("output")
    out.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "draws.json"),
                     help="destination JSON (default: lottomax/draws.json)")
    args = p.parse_args(argv)

    today = dt.date.today()
    by_date = {}
    for year in year_range(args.years, today):
        try:
            html = fetch_year(year, args.cache_dir, args.timeout)
        except urllib.error.URLError as exc:
            print(f"  {year}: fetch failed ({exc.reason})", file=sys.stderr)
            continue
        found = 0
        for d in parse(html):
            by_date[d["date"]] = d          # dedupe; later page wins
            found += 1
        print(f"  {year}: {found} draws", file=sys.stderr)

    draws = [by_date[k] for k in sorted(by_date)]
    if not draws:
        raise SystemExit("no draws parsed -- the page layout may have changed")
    validate(draws)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(draws, fh, indent=0)
        fh.write("\n")
    print(f"wrote {len(draws)} draws ({draws[0]['date']} .. {draws[-1]['date']}) "
          f"to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
