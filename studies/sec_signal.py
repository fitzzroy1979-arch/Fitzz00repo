"""Does SEC filing activity predict BTC returns, or only describe the past?

The same test the CFTC feed just failed, on the other feed.

Design notes that matter more than the numbers:

* Counts come from EDGAR's `total` for a one-week date window -- one request
  per week. Paging the filings and bucketing them locally would be fewer
  requests but it cannot work: EDGAR refuses offsets past ~10,000, and a
  broad query over eight years is far past that, so a locally-bucketed
  series would silently be a truncated one. This project has already found
  seven bugs of exactly that shape.

* Alignment: filings dated Mon..Sun of week W are all public by Sunday, so
  the feature is known at the last close <= Sunday. The forward return runs
  from that close to the last close <= the following Sunday. Nothing in the
  feature postdates the entry price.

* The feature is a CHANGE or a z-score, never the raw count. Crypto mentions
  in EDGAR grew by two orders of magnitude over this window and so did the
  price; correlating two rising series measures the trend and nothing else.
  The raw level is reported, flagged, and not counted as a test.

* LOOK COUNT, declared before seeing results: 3 queries x 2 feature forms
  x 2 directions = 12. The 6 forward looks are the hypothesis; the 6
  backward ones are the control. At 0.05, chance delivers 0.3 significant
  forward results, so a single |t| just over 2 is not evidence -- and
  with n ~ 450 the standard error on r is ~0.047, so |r| must exceed about
  0.094 before it clears 2 sigma at all.
"""
import datetime as dt, json, math, os, sys, tempfile, time, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from fitzz.flows import _get_json, SEC_FULLTEXT, SEC_USER_AGENT
from run_sweep_4h import fetch

CACHE = os.path.join(tempfile.gettempdir(), "fitzz_sweep_bars")
# The fetched counts, committed alongside this script: 1,377 weekly
# requests take ten minutes, and the numbers in FINDINGS.md should be
# checkable without them. Delete the file to re-fetch from EDGAR.
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "sec_counts.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

QUERIES = ["bitcoin", '"bitcoin treasury"', "cryptocurrency"]
START, END = "2018-01-01", "2026-10-25"      # whole weeks only
Z_LOOKBACK = 26


def week_total(query, start, end, tries=4):
    """Hits for one query in [start, end]. One request; reads `total` only."""
    params = {"q": query, "dateRange": "custom", "startdt": start,
              "enddt": end}
    for attempt in range(tries):
        try:
            data = _get_json(SEC_FULLTEXT, params, headers={
                "User-Agent": SEC_USER_AGENT, "Accept": "application/json"})
            return ((data.get("hits") or {}).get("total") or {}).get("value")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            if attempt == tries - 1:
                print(f"    ! {query} {start}: {e}", flush=True)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


# ---- weekly windows (Mon..Sun) ------------------------------------------- #
d0 = dt.date.fromisoformat(START)
d0 += dt.timedelta(days=(7 - d0.weekday()) % 7)        # first Monday
weeks = []
cur = d0
last = dt.date.fromisoformat(END)
while cur + dt.timedelta(days=6) <= last:
    weeks.append((cur.isoformat(), (cur + dt.timedelta(days=6)).isoformat()))
    cur += dt.timedelta(days=7)
print(f"{len(weeks)} weeks, {weeks[0][0]} to {weeks[-1][1]}")

# ---- counts (cached; the fetch is the slow part) -------------------------- #
counts = {}
if os.path.exists(OUT):
    counts = json.load(open(OUT))
    print(f"loaded cache: {sum(len(v) for v in counts.values())} week-counts")

for q in QUERIES:
    have = counts.setdefault(q, {})
    todo = [w for w in weeks if w[0] not in have]
    print(f"\n{q}: {len(have)} cached, {len(todo)} to fetch", flush=True)
    for i, (ws, we) in enumerate(todo):
        have[ws] = week_total(q, ws, we)
        if i % 50 == 0:
            print(f"    {ws} -> {have[ws]}", flush=True)
            json.dump(counts, open(OUT, "w"))
        time.sleep(0.12)                   # EDGAR asks for <10 req/s
    json.dump(counts, open(OUT, "w"))

# ---- price --------------------------------------------------------------- #
path, n = fetch("BITSTAMP:BTCUSD", "1d", 5000, CACHE)
bars = json.load(open(path))["bars"]
closes = {}
for b in bars:
    d = dt.datetime.utcfromtimestamp(int(b["time"])).strftime("%Y-%m-%d")
    closes[d] = float(b["close"])
days = sorted(closes)
print(f"\nBTC daily: {len(days)} bars, {days[0]} to {days[-1]}")


def close_on_or_before(d):
    lo, hi, prev = 0, len(days) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if days[mid] <= d:
            prev, lo = days[mid], mid + 1
        else:
            hi = mid - 1
    return (prev, closes[prev]) if prev else (None, None)


def pearson(xs, ys):
    n = len(xs)
    if n < 10:
        return None, None, n
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None, None, n
    r = sxy / math.sqrt(sxx * syy)
    r = max(-0.999999, min(0.999999, r))
    t = r * math.sqrt((n - 2) / (1 - r * r))
    return r, t, n


# ---- features and returns ------------------------------------------------ #
print("\n" + "=" * 74)
print("SEC filing activity vs BTC weekly returns")
print("=" * 74)

for q in QUERIES:
    have = counts[q]
    series = [(ws, we, have.get(ws)) for ws, we in weeks]
    good = [s for s in series if s[2] is not None]
    if len(good) < 60:
        print(f"\n{q}: only {len(good)} usable weeks, skipped")
        continue

    # A phrase query is zero for years before the phrase exists. A log-change
    # or z-score over a run of zeros is noise with a number attached, so the
    # series starts where the term is actually in use: the first week whose
    # trailing 26-week sum is non-zero.
    first = 0
    for i in range(len(series)):
        window = [x[2] or 0 for x in series[max(0, i - Z_LOOKBACK):i + 1]]
        if sum(window) > 0:
            first = i
            break
    if first:
        print(f"\n{q}: term unused before {series[first][0]}; "
              f"dropping {first} leading weeks")
    series = series[first:]

    rows = []
    for i, (ws, we, c) in enumerate(series):
        if c is None or i == 0:
            continue
        prev = series[i - 1][2]
        if prev is None:
            continue
        # entry at the last close <= Sunday of week W
        d_in, p_in = close_on_or_before(we)
        d_fw, p_fw = close_on_or_before(
            (dt.date.fromisoformat(we) + dt.timedelta(days=7)).isoformat())
        d_bk, p_bk = close_on_or_before(
            (dt.date.fromisoformat(we) - dt.timedelta(days=7)).isoformat())
        if not (p_in and p_fw and p_bk) or d_fw == d_in or d_bk == d_in:
            continue
        hist = [x[2] for x in series[max(0, i - Z_LOOKBACK):i]
                if x[2] is not None]
        z = None
        if len(hist) >= 12:
            m = sum(hist) / len(hist)
            sd = math.sqrt(sum((h - m) ** 2 for h in hist) / (len(hist) - 1))
            z = (c - m) / sd if sd > 0 else None
        rows.append({
            "week": ws, "count": c,
            "d_log": math.log((c + 1) / (prev + 1)),
            "z26": z,
            "fwd": p_fw / p_in - 1.0,
            "bwd": p_in / p_bk - 1.0,
        })

    cs = [r["count"] for r in rows]
    print(f"\n{q}   n={len(rows)} weeks   "
          f"count: min {min(cs)}, median {sorted(cs)[len(cs)//2]}, max {max(cs)}")
    print(f"  {'feature':<26}{'vs NEXT week':>14}{'t':>8}"
          f"{'vs week just past':>20}{'t':>8}")
    for name, key in (("count change (log w/w)", "d_log"),
                      (f"count z-score ({Z_LOOKBACK}w)", "z26"),
                      ("raw count [trend-confounded]", "count")):
        sub = [r for r in rows if r[key] is not None]
        xs = [r[key] for r in sub]
        rf, tf, nf = pearson(xs, [r["fwd"] for r in sub])
        rb, tb, nb = pearson(xs, [r["bwd"] for r in sub])
        def f(v, w):
            return f"{v:+{w}.3f}" if v is not None else " " * (w - 3) + "n/a"
        print(f"  {name:<26}{f(rf,14)}{f(tf,8)}{f(rb,20)}{f(tb,8)}")

    # quintiles on the primary feature
    sub = sorted([r for r in rows if r["d_log"] is not None],
                 key=lambda r: r["d_log"])
    k = len(sub) // 5
    if k >= 10:
        print(f"  quintiles of count change -> mean next-week return")
        for b in range(5):
            part = sub[b * k:(b + 1) * k] if b < 4 else sub[4 * k:]
            mean = sum(r["fwd"] for r in part) / len(part)
            print(f"    {part[0]['d_log']:+.3f}..{part[-1]['d_log']:+.3f}"
                  f"  n={len(part):<4} next week {mean*100:+.2f}%")

print("\nReminder: 6 forward looks were declared. Chance expectation at 0.05"
      " is 0.3.")
