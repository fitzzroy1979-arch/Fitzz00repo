"""Does CFTC positioning predict BTC returns, or only describe the past?

Alignment is the whole question. Positions are as of Tuesday and published
the following Friday, so a trader can act no earlier than the release date.
Everything here is measured from the release close forward.
"""
import math, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from fitzz.flows import fetch_cot, cot_net_changes, COT_RELEASE_LAG_DAYS, _add_days
from run_sweep_4h import fetch

CACHE = os.path.join(tempfile.gettempdir(), "fitzz_sweep_bars")

MARKET = "BITCOIN - CHICAGO MERCANTILE EXCHANGE"
rows = fetch_cot(MARKET, since="2015-01-01", exact=True)
rows = [r for r in rows if r.get("comm_net") is not None]
rows = cot_net_changes(rows)
print(f"CME BITCOIN: {len(rows)} weekly reports, "
      f"{rows[0]['date']} to {rows[-1]['date']}")

path, n = fetch("BITSTAMP:BTCUSD", "1d", 5000, CACHE)
import json
bars = json.load(open(path))["bars"]
import datetime as dt
closes = {}
for b in bars:
    d = dt.datetime.utcfromtimestamp(int(b["time"])).strftime("%Y-%m-%d")
    closes[d] = float(b["close"])
days = sorted(closes)
print(f"BTC daily: {len(days)} bars, {days[0]} to {days[-1]}\n")

def close_on_or_after(d):
    for k in days:                      # days is sorted; small enough to scan
        if k >= d:
            return k, closes[k]
    return None, None

def close_on_or_before(d):
    prev = None
    for k in days:
        if k > d:
            break
        prev = k
    return (prev, closes[prev]) if prev else (None, None)

obs = []
for r in rows:
    if r.get("comm_net_change") is None:
        continue
    rel = _add_days(r["date"], COT_RELEASE_LAG_DAYS)
    d0, p0 = close_on_or_after(rel)
    if not d0:
        continue
    d1, p1 = close_on_or_after(_add_days(d0, 7))
    dm1, pm1 = close_on_or_before(_add_days(d0, -7))
    if not d1 or not pm1 or d1 == d0:
        continue
    obs.append({
        "comm_chg": r["comm_net_change"],
        "comm_net": r["comm_net"],
        "noncomm": r.get("noncomm_net"),
        "oi": r.get("open_interest") or 0,
        "fwd": p1 / p0 - 1.0,
        "past": p0 / pm1 - 1.0,
    })
print(f"{len(obs)} aligned observations\n")

def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None, None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None, None
    r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)
    if abs(r) >= 1:
        return r, 0.0
    t = r * math.sqrt((n - 2) / (1 - r * r))
    return r, t

FEATS = [
    ("commercial net change (w/w)", lambda o: o["comm_chg"]),
    ("commercial net level", lambda o: o["comm_net"]),
    ("commercial net / open interest", lambda o: o["comm_net"] / o["oi"] if o["oi"] else 0.0),
    ("non-commercial net level", lambda o: o["noncomm"] if o["noncomm"] is not None else 0.0),
]
print(f"{'feature':<34}{'vs NEXT week':>16}{'t':>8}   {'vs week just past':>18}{'t':>8}")
for name, f in FEATS:
    xs = [f(o) for o in obs]
    rf, tf = pearson(xs, [o["fwd"] for o in obs])
    rp, tp = pearson(xs, [o["past"] for o in obs])
    fmt = lambda v: "n/a" if v is None else f"{v:+.3f}"
    print(f"{name:<34}{fmt(rf):>16}{fmt(tf):>8}   {fmt(rp):>18}{fmt(tp):>8}")

print("\nnext-week return by commercial-net-change quintile:")
s = sorted(obs, key=lambda o: o["comm_chg"])
q = len(s) / 5
for b in range(5):
    chunk = s[int(b * q):int((b + 1) * q)]
    m = sum(o["fwd"] for o in chunk) / len(chunk)
    up = 100.0 * sum(1 for o in chunk if o["fwd"] > 0) / len(chunk)
    print(f"  Δ {chunk[0]['comm_chg']:+8.0f} .. {chunk[-1]['comm_chg']:+8.0f}  "
          f"n={len(chunk):<4} mean next week {100*m:+.2f}%   up {up:4.1f}%")
