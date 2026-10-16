#!/usr/bin/env python3
"""
flows.py — public money-flow data from the SEC and the CFTC.

The rest of the toolkit reads price and volume off TradingView. This module
reads who is actually positioned and who is actually buying, from two free,
keyless government sources:

    fitzz flows --cot BITCOIN            # CFTC commercial positioning, weekly
    fitzz flows --sec "bitcoin treasury" # SEC EDGAR filings mentioning it
    fitzz flows --cot BITCOIN --json

CFTC Commitments of Traders (legacy futures-only report) splits open interest
into *commercial* (hedgers) and *non-commercial* (large speculators) books.
It is published weekly: positions are as of Tuesday, released the following
Friday afternoon. Anything consuming this for a backtest must respect that
lag or it is reading the future -- see COT_RELEASE_LAG_DAYS.

A caution worth repeating, because the label invites the wrong reading:
"commercial" means hedgers and market makers laying off inventory, not firms
acquiring coin. Corporate acquisition shows up in SEC filings (8-K treasury
purchases, 13F holdings), never in the CFTC commercial column.

The book is not structurally one-sided. Measured over 2019-2026 it was net
long most weeks of 2021, 2024 and 2025, and deeply short through 2022 and
2026 -- 2026 being the most extreme short year on record, at the largest
share of open interest commercials have ever held (~13%). Commercials carry
roughly 9% of open interest and track the speculator book at about -0.87,
so treat the series as a thin, regime-dependent read.

Neither endpoint needs an API key. The SEC asks that automated clients
identify themselves with a contact address in the User-Agent, which
SEC_USER_AGENT does.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

CFTC_LEGACY = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
SEC_FULLTEXT = "https://efts.sec.gov/LATEST/search-index"
SEC_USER_AGENT = "fitzz-research (contact: fitzzroy1979@gmail.com)"

# COT positions are as of Tuesday and published Friday ~15:30 ET. A backtest
# may not act on a report until it exists publicly.
COT_RELEASE_LAG_DAYS = 3


def _get_json(url, params=None, headers=None, timeout=30):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
# CFTC
# --------------------------------------------------------------------------- #

def fetch_cot(market="BITCOIN", since=None, limit=None, exact=False,
              page_size=1000, max_rows=200000):
    """
    Weekly commercial / non-commercial positioning. Newest first.

    `market` is a case-insensitive substring unless `exact`. Exact matching
    exists because substrings cannot isolate the headline contract: the full
    name "BITCOIN - CHICAGO MERCANTILE EXCHANGE" is itself a substring of
    "MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE".

    Pages until the server runs out of rows. `limit=None` means every
    matching row; pass an int to stop early. A single request used to cap at
    400, which silently truncated any market with more history than that and
    produced confident statistics over a partial series.

    Paging needs a total order or rows shift between pages: the report date
    alone ties across contracts, so the market name breaks the tie.
    """
    if exact:
        where = f'upper(market_and_exchange_names) = "{market.upper()}"'
    else:
        where = f'upper(market_and_exchange_names) like "%{market.upper()}%"' 
    if since:
        where += f' AND report_date_as_yyyy_mm_dd > "{since}"'
    select = ",".join([
        "market_and_exchange_names", "report_date_as_yyyy_mm_dd",
        "comm_positions_long_all", "comm_positions_short_all",
        "noncomm_positions_long_all", "noncomm_positions_short_all",
        "open_interest_all",
    ])
    rows, offset = [], 0
    while True:
        want = page_size if limit is None else min(page_size, limit - len(rows))
        if want <= 0:
            break
        page = _get_json(CFTC_LEGACY, {
            "$where": where,
            "$select": select,
            "$order": "report_date_as_yyyy_mm_dd DESC, market_and_exchange_names",
            "$limit": want,
            "$offset": offset,
        })
        rows.extend(page)
        if len(page) < want:          # server had nothing more
            break
        offset += len(page)
        if len(rows) >= max_rows:     # runaway guard, not an expected path
            break
    out = []
    for r in rows:
        def _i(k):
            try:
                return int(float(r.get(k) or 0))
            except (TypeError, ValueError):
                return 0
        cl, cs = _i("comm_positions_long_all"), _i("comm_positions_short_all")
        nl, ns = _i("noncomm_positions_long_all"), _i("noncomm_positions_short_all")
        date = (r.get("report_date_as_yyyy_mm_dd") or "")[:10]
        out.append({
            "market": r.get("market_and_exchange_names"),
            "date": date,
            "available_from": _add_days(date, COT_RELEASE_LAG_DAYS),
            "comm_long": cl, "comm_short": cs, "comm_net": cl - cs,
            "noncomm_long": nl, "noncomm_short": ns, "noncomm_net": nl - ns,
            "open_interest": _i("open_interest_all"),
        })
    return out


def _add_days(date_str, days):
    try:
        return (datetime.strptime(date_str, "%Y-%m-%d")
                + timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return date_str


def cot_net_changes(rows):
    """
    Week-over-week change in the commercial net book, oldest first.

    Grouped by market: a query like "BITCOIN" matches several contracts
    (CME Bitcoin, Micro Bitcoin, Coinbase nano...), and differencing across
    them would subtract one contract's book from another's.
    """
    by_market = {}
    for r in rows:
        by_market.setdefault(r["market"], []).append(r)
    out = []
    for market, group in by_market.items():
        chron = sorted(group, key=lambda r: r["date"])
        if chron:
            out.append({**chron[0], "comm_net_change": None})
        for prev, cur in zip(chron, chron[1:]):
            out.append({**cur, "comm_net_change": cur["comm_net"] - prev["comm_net"]})
    return sorted(out, key=lambda r: (r["date"], r["market"] or ""))


# --------------------------------------------------------------------------- #
# SEC
# --------------------------------------------------------------------------- #

def fetch_sec_filings(query, forms=None, since=None, until=None, limit=20,
                      sort="date"):
    """
    EDGAR full-text search. `query` is matched against filing text; wrap it in
    double quotes for a phrase.

    EDGAR returns hits ranked by relevance and ignores every sort parameter it
    is offered, so ordering is done here. That is safe rather than misleading
    because the endpoint returns the whole result set in one response: sorting
    sees every match, not just the first relevance page. Sorting happens before
    `limit` is applied, so --limit really does give the newest N.
    """
    params = {"q": query}
    if forms:
        params["forms"] = forms
    # EDGAR only applies startdt/enddt when the range mode is explicit;
    # without dateRange=custom it silently returns all history.
    if since or until:
        params["dateRange"] = "custom"
        params["startdt"] = since or "2001-01-01"
        params["enddt"] = until or datetime.utcnow().strftime("%Y-%m-%d")
    data = _get_json(SEC_FULLTEXT, params, headers={
        "User-Agent": SEC_USER_AGENT, "Accept": "application/json",
    })
    hits = (data.get("hits") or {}).get("hits") or []
    total = ((data.get("hits") or {}).get("total") or {}).get("value", 0)
    out = []
    for h in hits:
        s = h.get("_source") or {}
        names = s.get("display_names") or []
        # file_type is the exhibit (EX-99.1); root_form is the filing (8-K).
        out.append({
            "company": names[0] if names else "",
            "form": s.get("root_form") or s.get("form") or s.get("file_type") or "",
            "exhibit": s.get("file_type") or "",
            "filed": s.get("file_date") or s.get("period_ending") or "",
            "cik": (s.get("ciks") or [""])[0],
            "doc": h.get("_id", ""),
        })
    if sort == "date":
        out.sort(key=lambda f: f["filed"] or "", reverse=True)
    return {"total": total, "filings": out[:limit], "returned": len(hits)}



# --------------------------------------------------------------------------- #
# Corporate events
# --------------------------------------------------------------------------- #

# Acquisitions by the company behind an asset. Ripple is private, so unlike
# MSTR's bitcoin buys none of this is reachable from EDGAR -- it is compiled
# from the trade press and carried here so an analysis is reproducible rather
# than retyped. Treat it as a curated list with the provenance attached, not
# as a feed.
#
# `precision` says how far the date can be trusted. Only "day" entries are
# aligned to bars by event_study(); "month" and "year" are listed and skipped,
# because sliding an event by three weeks invents a result. `disputed` marks a
# date that sources do not agree on.
CORPORATE_EVENTS = {
    "XRP": [
        {"date": "2023-05-17", "precision": "month", "target": "Metaco",
         "amount_usd": 250e6, "kind": "announced",
         "note": "Swiss digital-asset custody; sources give May 2023"},
        {"date": "2024-06-01", "precision": "month", "target": "Standard Custody & Trust",
         "amount_usd": None, "kind": "closed",
         "note": "regulated trust entity; completed June 2024"},
        {"date": "2025-04-08", "precision": "day", "target": "Hidden Road",
         "amount_usd": 1.25e9, "kind": "announced", "disputed": True,
         "note": "prime broker, now Ripple Prime; some sources say only April 2025"},
        {"date": "2025-08-07", "precision": "day", "target": "Rail",
         "amount_usd": 200e6, "kind": "announced",
         "note": "Toronto stablecoin payments platform"},
        {"date": "2025-10-16", "precision": "day", "target": "GTreasury",
         "amount_usd": 1.0e9, "kind": "announced",
         "note": "treasury management, now Ripple Treasury"},
        {"date": "2025-10-24", "precision": "day", "target": "Hidden Road",
         "amount_usd": None, "kind": "closed", "note": "close of the April deal"},
        {"date": "2025-11-03", "precision": "day", "target": "Palisade",
         "amount_usd": None, "kind": "announced", "note": "custody and wallets"},
        {"date": "2026-01-06", "precision": "day", "target": "Solvexia",
         "amount_usd": None, "kind": "announced",
         "note": "financial automation; dated from Ripple's own release"},
        {"date": "2026-01-01", "precision": "year", "target": "BC Payments Australia",
         "amount_usd": None, "kind": "announced",
         "note": "Banking Circle payments arm; no month reported"},
    ],
}


def fetch_events(asset="XRP", dated_only=False):
    """Curated corporate events for an asset, oldest first."""
    rows = sorted(CORPORATE_EVENTS.get(asset.upper(), []), key=lambda e: e["date"])
    if dated_only:
        rows = [e for e in rows if e["precision"] == "day"]
    return rows


def event_study(events, bars, horizons=(1, 5, 10, 30), window_pad_days=60):
    """
    Forward returns after each event, against a baseline drawn from the same
    stretch of time.

    The baseline matters more than it looks. Events cluster, and a cluster
    sitting inside a drawdown will look bearish against a multi-year average
    that includes a bull run -- which says something about when the company
    was acquisitive, not about what the acquisitions did. So the comparison
    here is every day in the span the events occupy (padded either side),
    not every day on record.

    Only "day"-precision events are used. Returns None if none are usable.
    """
    px = {}
    for b in bars:
        ts = b.get("time")
        if isinstance(ts, (int, float)):
            px[datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")] = float(b["close"])
    days = sorted(px)
    if not days:
        return None
    dated = [e for e in events if e["precision"] == "day"
             and days[0] <= e["date"] <= days[-1]]
    if not dated:
        return None

    def idx_on_or_after(d):
        for i, x in enumerate(days):
            if x >= d:
                return i
        return None

    lo = _add_days(min(e["date"] for e in dated), -window_pad_days)
    hi = _add_days(max(e["date"] for e in dated), window_pad_days)

    per_event, agg = [], {}
    for e in dated:
        i = idx_on_or_after(e["date"])
        rets = {}
        for h in horizons:
            j = i + h
            rets[h] = ((px[days[j]] / px[days[i]] - 1) * 100) if j < len(days) else None
        per_event.append({**e, "price": px[days[i]], "returns": rets})

    for h in horizons:
        ev = [r["returns"][h] for r in per_event if r["returns"][h] is not None]
        win, full = [], []
        for i, d in enumerate(days):
            j = i + h
            if j >= len(days):
                continue
            r = (px[days[j]] / px[d] - 1) * 100
            full.append(r)
            if lo <= d <= hi:
                win.append(r)
        agg[h] = {
            "event_mean": sum(ev) / len(ev) if ev else None,
            "baseline_window_mean": sum(win) / len(win) if win else None,
            "baseline_full_mean": sum(full) / len(full) if full else None,
            "n_events": len(ev),
        }
    return {"events": per_event, "horizons": list(horizons),
            "baseline_window": [lo, hi], "aggregate": agg,
            "skipped": [e["target"] for e in events if e["precision"] != "day"]}


def _print_events(rows, asset):
    print(f"\nCorporate events — {asset}")
    print(f"{'date':<12}{'prec':<7}{'kind':<11}{'amount':>10}  target")
    for e in rows:
        amt = f"${e['amount_usd']/1e9:.2f}B" if e.get("amount_usd") and e["amount_usd"] >= 1e9 \
            else (f"${e['amount_usd']/1e6:.0f}M" if e.get("amount_usd") else "—")
        flag = " (disputed date)" if e.get("disputed") else ""
        print(f"{e['date']:<12}{e['precision']:<7}{e['kind']:<11}{amt:>10}  "
              f"{e['target']}{flag}")
    print("\n  Compiled from trade press, not filings: the company is private, so "
          "there is no\n  EDGAR feed for these. Only day-precision rows can be "
          "aligned to price bars.")


def _print_event_study(res):
    if not res:
        print("\n  no day-precision events inside the price history")
        return
    hs = res["horizons"]
    print(f"\n{'date':<12}{'target':<22}{'price':>10}" + "".join(f"{'+'+str(h)+'d':>9}" for h in hs))
    for e in res["events"]:
        line = f"{e['date']:<12}{e['target'][:21]:<22}{e['price']:>10.4f}"
        for h in hs:
            r = e["returns"][h]
            line += f"{r:>+9.1f}" if r is not None else f"{'-':>9}"
        print(line)
    lo, hi = res["baseline_window"]
    print(f"\n{'horizon':<10}{'events':>12}{'same period':>14}{'full history':>15}")
    for h in hs:
        a = res["aggregate"][h]
        print(f"+{h}d{'':<7}{a['event_mean']:>+11.2f}%{a['baseline_window_mean']:>+13.2f}%"
              f"{a['baseline_full_mean']:>+14.2f}%")
    n = res["aggregate"][hs[0]]["n_events"]
    print(f"\n  n = {n} events, baseline window {lo} -> {hi}")
    if res["skipped"]:
        print(f"  skipped (date not precise enough): {', '.join(res['skipped'])}")
    print(f"  {n} events cannot support a significance test. Read this as "
          f"description,\n  not evidence, and check whether one or two events "
          f"carry the whole pattern.")

# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _print_cot(rows, market, limit=12):
    if not rows:
        print(f"No CFTC rows matching {market!r}.")
        return
    withch = cot_net_changes(rows)
    # Cap per contract, not across them: a loose match like "BITCOIN" pulls in
    # CME, Micro and the Coinbase nanos, and a flat cap would show only a few
    # weeks of each.
    seen, recent = {}, []
    for r in reversed(withch):
        m = r["market"]
        if seen.get(m, 0) >= limit:
            continue
        seen[m] = seen.get(m, 0) + 1
        recent.append(r)
    markets = sorted(seen)
    if len(markets) > 1:
        print(f"\n  note: {len(markets)} contracts matched {market!r} — "
              f"{', '.join(m.split(' - ')[0] for m in markets)}. "
              f"Add --exact to isolate one (the full name is still a "
              f"substring of the Micro contract's).")
    print(f"\nCFTC Commitments of Traders — {market} (weekly, legacy report)")
    print(f"{'as-of':<12}{'public':<12}{'comm_net':>10}{'Δweek':>9}"
          f"{'noncomm_net':>13}{'OI':>9}  market")
    for r in recent:
        ch = r["comm_net_change"]
        ch_s = f"{ch:+}" if ch is not None else "—"
        print(f"{r['date']:<12}{r['available_from']:<12}{r['comm_net']:>+10}"
              f"{ch_s:>9}{r['noncomm_net']:>+13}"
              f"{r['open_interest']:>9}  {(r['market'] or '')[:34]}")
    print("\n  commercial = hedgers/market makers, ~9% of CME Bitcoin open interest.")
    print("  The book flips regime -- net long most weeks of 2021/2024/2025, deeply")
    print("  short through 2026 -- so the sign is a regime read, not a constant.")
    print("  It tracks the speculator book at about -0.87, so it is mostly, but not")
    print("  entirely, the mirror image. 'public' is the actual release date.")


def _print_sec(res, query):
    print(f"\nSEC EDGAR full-text — {query!r}: {res['total']} filing(s) matched")
    if not res["filings"]:
        print("  (nothing returned)")
        return
    print(f"{'filed':<12}{'form':<8}{'cik':<12}company")
    for f in res["filings"]:
        print(f"{(f['filed'] or '')[:10]:<12}{(f['form'] or '')[:7]:<8}"
              f"{f['cik']:<12}{f['company'][:50]}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="fitzz flows",
        description="Public money-flow data: CFTC positioning and SEC filings.")
    p.add_argument("--cot", nargs="?", const="BITCOIN", default=None,
                   metavar="MARKET",
                   help="CFTC Commitments of Traders for markets matching "
                        "MARKET (default BITCOIN).")
    p.add_argument("--sec", default=None, metavar="QUERY",
                   help='SEC EDGAR full-text search, e.g. "bitcoin treasury".')
    p.add_argument("--forms", default=None,
                   help="Restrict --sec to form types, e.g. 8-K or 13F-HR.")
    p.add_argument("--since", default=None,
                   help="Earliest date, YYYY-MM-DD.")
    p.add_argument("--events", nargs="?", const="XRP", default=None, metavar="ASSET",
                   help="Curated corporate events for ASSET (default XRP).")
    p.add_argument("--event-study", action="store_true",
                   help="With --events: pull bars and measure the price response.")
    p.add_argument("--event-symbol", default=None,
                   help="TradingView symbol for --event-study "
                        "(default: COINBASE:<ASSET>USD).")
    p.add_argument("--event-bars", type=int, default=1500,
                   help="Bars to pull for --event-study (default 1500 daily).")
    p.add_argument("--sort", choices=["date", "relevance"], default="date",
                   help="Order --sec results newest-first (default) or by "
                        "EDGAR's relevance ranking.")
    p.add_argument("--exact", action="store_true",
                   help="Match --cot MARKET exactly instead of as a substring.")
    p.add_argument("--limit", type=int, default=20,
                   help="Max rows to show (default 20).")
    p.add_argument("--json", action="store_true", help="Emit raw JSON.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.cot and not args.sec and not args.events:
        args.cot = "BITCOIN"

    payload = {}
    try:
        if args.cot:
            rows = fetch_cot(args.cot, since=args.since, exact=args.exact)
            payload["cot"] = rows
            if not args.json:
                _print_cot(rows, args.cot, limit=args.limit)
        if args.events:
            evs = fetch_events(args.events)
            if not evs:
                raise SystemExit(f"no curated events for {args.events!r}; "
                                 f"known: {', '.join(sorted(CORPORATE_EVENTS))}")
            payload["events"] = evs
            if not args.json:
                _print_events(evs, args.events.upper())
            if args.event_study:
                # imported lazily: the rest of this module needs no bridge
                from fitzz.trading import TradingViewBridge, resolve_interval
                sym = args.event_symbol or f"COINBASE:{args.events.upper()}USD"
                bars = TradingViewBridge().load_bars(sym, resolve_interval("1d"),
                                                     args.event_bars)
                study = event_study(evs, bars)
                payload["event_study"] = study
                if not args.json:
                    _print_event_study(study)
        if args.sec:
            res = fetch_sec_filings(args.sec, forms=args.forms,
                                    since=args.since, limit=args.limit,
                                    sort=args.sort)
            payload["sec"] = res
            if not args.json:
                _print_sec(res, args.sec)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} from {e.url}: {e.reason}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Network error: {e.reason}")

    if args.json:
        print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    main()
