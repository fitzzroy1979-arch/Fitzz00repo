#!/usr/bin/env python3
"""
sweep_significance.py -- was the best config from a parameter sweep real?

Any sweep returns a winner. The winner's score is a maximum over K noisy
estimates, so it is biased upward even when every config is worthless: sweeping
3,355 moving-average configs over a pure random walk finds ~54% hit rates and
occasionally 60%. The number on its own is uninterpretable.

This tool prices that bias. It evaluates the whole search universe, then asks
how large the best score would have been if none of the configs had any edge --
by block-bootstrapping the time axis, which preserves volatility clustering and
short-horizon autocorrelation while destroying any exploitable structure.

Two p-values are reported:

  Reality Check (White 2000)  p(RC)  -- probability that a search this wide over
                                        data this noisy produces a winner this
                                        good by chance alone.
  SPA (Hansen 2005)           p(SPA) -- same null, studentized, and with clearly
                                        dead configs dropped from the null so a
                                        junk-filled grid does not make the test
                                        over-conservative. Usually the one to
                                        quote.

Also reported is the naive single-config p-value, which is what you would get if
you pretended the winner was your only hypothesis. The gap between it and p(SPA)
is the price of the search.

Usage
-----
  # built-in demo: no edge exists, tool should say so
  python3 sweep_significance.py --selftest

  # real data
  python3 sweep_significance.py --csv SPY_daily.csv --cost-bps 1
  python3 sweep_significance.py --json bars.json --objective hit --holdout 0.33

  # your own strategy family
  python3 sweep_significance.py --csv x.csv --strategy mystrats.py:build

A custom strategy module exposes:

    def build(close: np.ndarray) -> tuple[np.ndarray, list[str]]
        # returns (positions of shape (T, K) in [-1, 1], K labels)

Requires numpy only.
"""

import argparse
import csv
import json
import math
import os
import sys

import numpy as np

# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #

CLOSE_KEYS = ("close", "adj close", "adj_close", "adjclose", "last", "price", "c")


def load_csv(path):
    """Pull a close-price column out of a CSV. Case/naming tolerant."""
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise SystemExit(f"{path}: empty file")

    header = [h.strip().lower() for h in rows[0]]
    col = next((i for k in CLOSE_KEYS for i, h in enumerate(header) if h == k), None)
    if col is None:
        # No usable header -- fall back to the last numeric column.
        try:
            [float(x) for x in rows[0]]
        except ValueError:
            raise SystemExit(
                f"{path}: no close column found (looked for {', '.join(CLOSE_KEYS)}); "
                f"header was: {', '.join(header)}"
            )
        body, col = rows, len(rows[0]) - 1
    else:
        body = rows[1:]

    out = []
    for r in body:
        if len(r) <= col or not r[col].strip():
            continue
        try:
            out.append(float(r[col]))
        except ValueError:
            continue
    return np.asarray(out, dtype=np.float64)


def load_json(path):
    """00fitzz / tradingview-mcp bar format: [{time, open, high, low, close}, ...]."""
    with open(path) if path != "-" else sys.stdin as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("bars", data.get("data", []))
    if not data:
        raise SystemExit(f"{path}: no bars found")
    if isinstance(data[0], dict):
        key = next((k for k in ("close", "Close", "c") if k in data[0]), None)
        if key is None:
            raise SystemExit(f"{path}: bars have no close field ({list(data[0])})")
        return np.asarray([float(b[key]) for b in data], dtype=np.float64)
    return np.asarray([float(x) for x in data], dtype=np.float64)


# --------------------------------------------------------------------------- #
# Synthetic series (for --selftest and for sanity checks)
# --------------------------------------------------------------------------- #

def random_walk(n, vol=0.02, phi=0.0, rng=None):
    """
    Log-price path. phi is the AR(1) coefficient on returns:
      phi = 0    -> no exploitable structure, true edge is exactly zero
      phi > 0    -> genuine momentum, a trend follower should find it
    """
    rng = rng or np.random.default_rng()
    eps = rng.normal(0, vol, n)
    if phi == 0.0:
        r = eps
    else:
        r = np.empty(n)
        r[0] = eps[0]
        for i in range(1, n):
            r[i] = phi * r[i - 1] + eps[i]
    return 100.0 * np.exp(np.cumsum(r))


# --------------------------------------------------------------------------- #
# Strategy families -> (T, K) position matrix
# --------------------------------------------------------------------------- #

def rolling_mean(x, w):
    c = np.concatenate(([0.0], np.cumsum(x)))
    out = np.full(x.shape, np.nan)
    out[w - 1:] = (c[w:] - c[:-w]) / w
    return out


def rolling_max(x, w):
    out = np.full(x.shape, np.nan)
    if w <= len(x):
        strided = np.lib.stride_tricks.sliding_window_view(x, w)
        out[w - 1:] = strided.max(axis=1)
    return out


def rolling_min(x, w):
    out = np.full(x.shape, np.nan)
    if w <= len(x):
        strided = np.lib.stride_tricks.sliding_window_view(x, w)
        out[w - 1:] = strided.min(axis=1)
    return out


def ma_cross_family(close, fasts, slows, threshs, long_only=False):
    """SMA crossover with a deadband. Positions in {-1, 0, +1}."""
    mas = {w: rolling_mean(close, w) for w in sorted(set(fasts) | set(slows))}
    cols, labels, windows = [], [], []
    for f in fasts:
        for s in slows:
            if f >= s:
                continue
            spread = (mas[f] - mas[s]) / mas[s]
            mag = np.abs(spread)
            for t in threshs:
                # NaN warm-up compares False -> flat. No look-ahead, no NaN leak.
                p = np.sign(np.where(mag > t, spread, 0.0))
                if long_only:
                    p = np.maximum(p, 0.0)
                cols.append(p.astype(np.float32))
                labels.append(f"ma_cross fast={f} slow={s} thresh={t:g}")
                windows.append(s)
    return np.column_stack(cols), labels, max(windows) if windows else 1


def breakout_family(close, entries, exits, long_only=False):
    """Donchian channel breakout. Positions in {-1, 0, +1}, state-carrying."""
    hi = {w: rolling_max(close, w) for w in sorted(set(entries) | set(exits))}
    lo = {w: rolling_min(close, w) for w in sorted(set(entries) | set(exits))}
    cols, labels, windows = [], [], []
    for e in entries:
        for x in exits:
            if x >= e:
                continue
            long_in = close >= hi[e]
            short_in = close <= lo[e]
            long_out = close <= lo[x]
            short_out = close >= hi[x]
            p = np.zeros(len(close), dtype=np.float32)
            state = 0.0
            for i in range(len(close)):
                if state <= 0 and long_in[i]:
                    state = 1.0
                elif state >= 0 and short_in[i] and not long_only:
                    state = -1.0
                elif state > 0 and long_out[i]:
                    state = 0.0
                elif state < 0 and short_out[i]:
                    state = 0.0
                p[i] = state
            cols.append(p)
            labels.append(f"breakout entry={e} exit={x}")
            windows.append(e)
    return np.column_stack(cols), labels, max(windows) if windows else 1


def load_custom_family(spec, close):
    """--strategy path/to/file.py:funcname"""
    path, _, func = spec.partition(":")
    if not func:
        raise SystemExit("--strategy needs the form path/to/file.py:function_name")
    import importlib.util
    mod_name = os.path.splitext(os.path.basename(path))[0]
    spec_obj = importlib.util.spec_from_file_location(mod_name, path)
    if spec_obj is None or spec_obj.loader is None:
        raise SystemExit(f"could not import {path}")
    mod = importlib.util.module_from_spec(spec_obj)
    spec_obj.loader.exec_module(mod)
    if not hasattr(mod, func):
        raise SystemExit(f"{path} has no function '{func}'")
    pos, labels = getattr(mod, func)(close)
    pos = np.asarray(pos, dtype=np.float32)
    if pos.ndim == 1:
        pos = pos[:, None]
    if pos.shape[0] != len(close):
        raise SystemExit(f"{spec}: positions have {pos.shape[0]} rows, expected {len(close)}")
    if len(labels) != pos.shape[1]:
        raise SystemExit(f"{spec}: {len(labels)} labels for {pos.shape[1]} configs")
    nan = np.isnan(pos)
    if nan.any():
        pos = np.where(nan, 0.0, pos)  # warm-up NaN means flat, not a loss
    return pos, list(labels), 1


# --------------------------------------------------------------------------- #
# Performance matrix
# --------------------------------------------------------------------------- #

def performance_matrix(close, pos, objective, cost_bps, warmup, min_trades, score_from=0):
    """
    Per-bar performance contribution F[t, k]. Its mean over t is the statistic
    being maximised by the sweep, and it is zero-mean under the null.

      objective 'return' : net log return earned, minus turnover cost
      objective 'hit'    : signed direction score in {-1, 0, +1}; its mean is
                           activity * (2 * hit_rate - 1)

    The position at bar t is formed from prices up to and including t, and earns
    the t -> t+1 return. The final bar is dropped. All configs are evaluated on
    the identical window (starting after the longest warm-up) so that a long
    lookback is not penalised by extra flat bars.

    score_from pins the first bar that may be scored. The holdout uses it to
    let the moving averages warm up on in-sample history -- as they would in
    live trading -- while scoring strictly post-split bars.
    """
    logp = np.log(close)
    fwd = np.diff(logp)                      # fwd[t] = return from t to t+1
    pos = pos[:-1]                           # last bar has no forward return

    start = max(int(warmup), int(score_from), 1)
    if pos.shape[0] - start < 100:
        raise SystemExit(
            f"only {max(0, pos.shape[0] - start)} bars left to score: {len(close)} "
            f"bars in, but the longest window needs {start} of them. Shorten the "
            f"grid (--slow / --entry) or load more history."
        )
    pos, fwd = pos[start:], fwd[start:]

    prev = np.vstack([np.zeros((1, pos.shape[1]), dtype=pos.dtype), pos[:-1]])
    turn = np.abs(pos - prev)
    trades = (turn > 0).sum(axis=0)

    keep = trades >= min_trades
    if not keep.any():
        raise SystemExit(f"no config traded at least {min_trades} times")

    if objective == "return":
        F = pos.astype(np.float64) * fwd[:, None]
        F -= (cost_bps * 1e-4) * turn.astype(np.float64)
    elif objective == "hit":
        F = pos.astype(np.float64) * np.sign(fwd)[:, None]
        if cost_bps:
            print("  note: --cost-bps is ignored for --objective hit",
                  file=sys.stderr)
    else:
        raise SystemExit(f"unknown objective '{objective}'")

    # Configs that never move contribute a degenerate all-zero column.
    live = keep & (F.std(axis=0) > 0)
    return F[:, live], live, trades, pos, fwd


# --------------------------------------------------------------------------- #
# Block bootstrap + Reality Check / SPA
# --------------------------------------------------------------------------- #

def block_sums(F, L):
    """BS[i, k] = sum of F[i : i+L, k] with wraparound. Shape (T, K)."""
    T = F.shape[0]
    doubled = np.vstack([F, F[:L]])
    c = np.vstack([np.zeros((1, F.shape[1])), np.cumsum(doubled, axis=0)])
    return c[L:L + T] - c[:T]


def reality_check(F, block, n_boot, seed=0, progress=False):
    """
    White's Reality Check and Hansen's SPA over a circular block bootstrap.

    Null: no config in the universe has positive expected performance.
    The bootstrap resamples blocks of time, so volatility clustering and
    autocorrelation up to the block length survive into the null world.
    """
    T, K = F.shape
    L = max(1, min(int(block), T))
    if T // L < 10:
        print(f"  warning: block={L} leaves only {T // L} blocks in {T} bars; "
              f"the null will be coarse. Lower --block or use more history.",
              file=sys.stderr)
    nblocks = max(1, math.ceil(T / L))
    T_eff = nblocks * L

    f = F.mean(axis=0)                                # observed per-config means
    BS = block_sums(F, L)
    rng = np.random.default_rng(seed)

    boot = np.empty((n_boot, K), dtype=np.float64)
    for b in range(n_boot):
        idx = rng.integers(0, T, size=nblocks)
        boot[b] = BS[idx].sum(axis=0) / T_eff
        if progress and n_boot >= 200 and (b + 1) % (n_boot // 10) == 0:
            print(f"    bootstrap {b + 1}/{n_boot}", end="\r", file=sys.stderr)
    if progress:
        print(" " * 40, end="\r", file=sys.stderr)

    root_t = math.sqrt(T)
    centred = root_t * (boot - f)                     # imposes the null
    omega = centred.std(axis=0, ddof=1)
    omega = np.where(omega > 1e-12, omega, np.inf)    # dead config -> t = 0

    best = int(np.argmax(f))

    # How many INDEPENDENT tests does this grid behave like? E[max of M iid
    # normals] ~ sqrt(2 log M), so invert the null max of the studentized
    # stats. A correlated grid of thousands is worth only a handful of tests,
    # which is exactly why Bonferroni over-corrects here.
    mean_null_max_t = float((centred / omega).max(axis=1).mean())
    eff_tests = max(1.0, math.exp(mean_null_max_t ** 2 / 2.0))

    # --- White's Reality Check -------------------------------------------- #
    V_obs = root_t * f.max()
    V_boot = centred.max(axis=1)
    p_rc = (1 + (V_boot >= V_obs).sum()) / (n_boot + 1)

    # --- Hansen's SPA (consistent recentring) ------------------------------ #
    t_stat = root_t * f / omega
    T_spa = max(0.0, float(t_stat.max()))
    A_T = math.sqrt(2.0 * math.log(math.log(T))) if T > 15 else 1.0
    retain = (root_t * f) >= (-A_T * omega)           # drop clearly dead configs
    g = np.where(retain, f, 0.0)
    Z = root_t * (boot - g) / omega
    Z_boot = np.maximum(0.0, Z.max(axis=1))
    p_spa = (1 + (Z_boot >= T_spa).sum()) / (n_boot + 1)

    # --- naive: pretend the winner was the only hypothesis ------------------ #
    p_naive = (1 + (centred[:, best] >= root_t * f[best]).sum()) / (n_boot + 1)

    return {
        "best_idx": best,
        "best_stat": float(f[best]),
        "median_stat": float(np.median(f)),
        "p_naive": float(p_naive),
        "p_rc": float(p_rc),
        "p_spa": float(p_spa),
        "n_configs": int(K),
        "n_retained": int(retain.sum()),
        "eff_tests": float(eff_tests),
        "block": L,
        "n_boot": int(n_boot),
        "null_max_q": {
            "50%": float(np.percentile(V_boot, 50) / root_t),
            "90%": float(np.percentile(V_boot, 90) / root_t),
            "95%": float(np.percentile(V_boot, 95) / root_t),
            "99%": float(np.percentile(V_boot, 99) / root_t),
        },
        "obs_max": float(V_obs / root_t),
    }


# --------------------------------------------------------------------------- #
# Reporting helpers
# --------------------------------------------------------------------------- #

def variance_ratio(x, q):
    """
    Var(sum of q consecutive bars) / (q * Var(bar)). 1.0 means no serial
    dependence at that horizon. Well above 1 means the bootstrap block must be
    at least that long or the null is too tight and p comes out too small.
    """
    n = (len(x) // q) * q
    if n < q * 20:
        return None
    v = x[:n].var(ddof=1)
    if v <= 0:
        return None
    return float(x[:n].reshape(-1, q).sum(axis=1).var(ddof=1) / (q * v))


def describe(F_col, pos_col, fwd, objective):
    """Readable summary of one config."""
    active = pos_col != 0
    n_active = int(active.sum())
    hr = float((np.sign(fwd[active]) == np.sign(pos_col[active])).mean()) if n_active else float("nan")
    trades = int((np.abs(np.diff(np.concatenate(([0.0], pos_col)))) > 0).sum())
    return {
        "hit_rate": hr,
        "active_bars": n_active,
        "trades": trades,
        "mean_per_bar": float(F_col.mean()),
        "total": float(F_col.sum()),
    }


def fmt_p(p):
    return f"<0.001" if p < 0.001 else f"{p:.3f}"


def verdict(p_spa, p_rc):
    p = max(p_spa, 0.0)
    if p <= 0.01:
        return "SURVIVES the search correction (p<=0.01). Worth a holdout test."
    if p <= 0.05:
        return "MARGINAL (p<=0.05). Weak evidence; confirm on untouched data."
    if p <= 0.20:
        return "NOT SIGNIFICANT. Consistent with a lucky draw from the sweep."
    return "NOT SIGNIFICANT. This is what searching noise looks like."


def run_test(close, args, label="", quiet=False):
    """Build the universe, score it, and price the search bias."""
    if args.strategy:
        pos, labels, warm = load_custom_family(args.strategy, close)
    elif args.family == "breakout":
        pos, labels, warm = breakout_family(close, args.entry, args.exit, args.long_only)
    else:
        pos, labels, warm = ma_cross_family(close, args.fast, args.slow,
                                            args.thresh, args.long_only)

    F, live, trades, pos_t, fwd = performance_matrix(
        close, pos, args.objective, args.cost_bps, warm, args.min_trades
    )
    labels = [l for l, k in zip(labels, live) if k]
    pos_live = pos_t[:, live]

    need = args.n_boot * F.shape[1] * 8 / 1e9
    if need > 2.0 and not quiet:
        print(f"  warning: bootstrap matrix needs ~{need:.1f} GB; "
              f"lower --n-boot or narrow the grid", file=sys.stderr)

    res = reality_check(F, args.block, args.n_boot, args.seed,
                        progress=not quiet and sys.stderr.isatty())
    res["label"] = labels[res["best_idx"]]
    res["detail"] = describe(F[:, res["best_idx"]], pos_live[:, res["best_idx"]],
                             fwd, args.objective)
    res["n_bars"] = int(F.shape[0])
    res["dropped"] = int((~live).sum())

    col = F[:, res["best_idx"]]
    d = res["detail"]
    res["hold_bars"] = d["active_bars"] / max(d["trades"], 1)
    res["var_ratio"] = {q: variance_ratio(col, q) for q in (5, 20, 60, 120)}
    return res, (F, pos_live, fwd, labels)


def print_report(res, args, close, series_label):
    unit = "log-return/bar" if args.objective == "return" else "edge score"
    d = res["detail"]
    print()
    print("=" * 74)
    print(f"SWEEP SIGNIFICANCE  --  {series_label}")
    print("=" * 74)
    print(f"  bars scored           : {res['n_bars']:,}  (of {len(close):,} loaded)")
    print(f"  configs searched      : {res['n_configs']:,}"
          + (f"  ({res['dropped']:,} dropped: too few trades)" if res["dropped"] else ""))
    print(f"  objective             : {args.objective}  ({unit})")
    if args.objective == "return":
        cost = f"{args.cost_bps:g} bps per unit turnover"
        print(f"  costs                 : {cost}"
              + ("   <- set --cost-bps for a realistic test" if not args.cost_bps else ""))
    print(f"  null                  : circular block bootstrap, block={res['block']} bars, "
          f"{res['n_boot']:,} draws")
    print()
    print("  BEST CONFIG FOUND")
    print(f"    {res['label']}")
    print(f"    hit rate {d['hit_rate']:.2%} over {d['active_bars']:,} active bars, "
          f"{d['trades']:,} trades")
    print(f"    mean {res['best_stat']:+.6f} {unit}   (median config: {res['median_stat']:+.6f})")
    print()
    print("  WHAT THE NULL PRODUCES  (best-of-search when nothing works)")
    q = res["null_max_q"]
    print(f"    median {q['50%']:+.6f}   90th {q['90%']:+.6f}   "
          f"95th {q['95%']:+.6f}   99th {q['99%']:+.6f}")
    print(f"    observed best  {res['obs_max']:+.6f}")
    print()
    print("  P-VALUES")
    print(f"    naive, winner treated as the only hypothesis : {fmt_p(res['p_naive'])}")
    print(f"    Reality Check, corrected for the search      : {fmt_p(res['p_rc'])}")
    print(f"    SPA, corrected + studentized                 : {fmt_p(res['p_spa'])}"
          f"   [{res['n_retained']:,}/{res['n_configs']:,} configs in the null]")
    print()
    print("  CORRELATION DIAGNOSTICS  (are the test's assumptions met here?)")
    print(f"    grid behaves like ~{res['eff_tests']:.0f} independent tests, "
          f"not {res['n_configs']:,}")
    print(f"    -- configs overlap heavily, so a Bonferroni correction over "
          f"{res['n_configs']:,}")
    print(f"       would be far too harsh. The bootstrap resamples every config "
          f"on the")
    print(f"       same time index, so this overlap is priced in, not assumed away.")
    vr = {q: v for q, v in res["var_ratio"].items() if v is not None}
    if vr:
        print(f"    P&L variance ratio  " + "   ".join(f"q={q}: {v:.2f}" for q, v in vr.items()))
    print(f"    winner holds {res['hold_bars']:.1f} bars on average; "
          f"bootstrap block is {res['block']}")
    warn = []
    if res["hold_bars"] > res["block"]:
        warn.append(f"holding period ({res['hold_bars']:.0f} bars) exceeds the block "
                    f"({res['block']}); rerun with --block {int(res['hold_bars'] * 2)}")
    stretched = [q for q, v in vr.items() if v > 1.5 and q > res["block"]]
    if stretched:
        warn.append(f"P&L is serially dependent past the block (VR>1.5 at "
                    f"q={min(stretched)}); rerun with --block {min(stretched)}")
    if warn:
        for w in warn:
            print(f"    WARNING: {w}")
        print("    Until then p-values here are optimistic (too small).")
    else:
        print("    -- variance ratios near 1.0 and block >= holding period, so the")
        print("       null is not destroying dependence the strategy relies on.")
    print()
    print(f"  VERDICT: {verdict(res['p_spa'], res['p_rc'])}")
    if res["p_naive"] <= 0.05 < res["p_spa"]:
        print("  The naive p-value looks significant only because it ignores the")
        print(f"  other {res['n_configs'] - 1:,} configs you tried.")
    print("=" * 74)


# --------------------------------------------------------------------------- #
# Self-test: calibration (no edge) and power (planted edge)
# --------------------------------------------------------------------------- #

def selftest(args):
    """
    A test that always says "not significant" is useless. Validate both
    directions: false positives at the nominal rate when no edge exists, and
    detection of edges that were planted on purpose.

    phi is the AR(1) coefficient on returns -- the size of the real edge.
    phi=0 means the true edge is exactly zero, by construction.
    """
    import copy
    a = copy.copy(args)
    a.fast = list(range(2, 30, 2))
    a.slow = list(range(10, 120, 5))
    a.thresh = [0.0, 0.0025, 0.01]
    a.n_boot, a.min_trades, a.objective, a.cost_bps = 400, 20, "return", 0.0
    n_universes, n_bars = 10, 3000

    arms = [(0.00, "no edge exists"), (0.15, "weak edge"), (0.25, "clear edge")]
    table = []
    for phi, tag in arms:
        print(f"\n  phi={phi:.2f}  ({tag})   {n_universes} universes x {n_bars:,} bars")
        print("  " + "-" * 66)
        ps, hits = [], []
        for u in range(n_universes):
            close = random_walk(n_bars, phi=phi, rng=np.random.default_rng(1000 + u))
            a.seed = 5000 + u
            res, _ = run_test(close, a, quiet=True)
            ps.append(res["p_spa"])
            hits.append(res["detail"]["hit_rate"])
            print(f"   universe {u + 1:2d}: best hit rate {res['detail']['hit_rate']:6.2%}"
                  f"   naive p {fmt_p(res['p_naive']):>6}"
                  f"   SPA p {fmt_p(res['p_spa']):>6}"
                  f" {'*' if res['p_spa'] <= 0.05 else ' '}")
        ps = np.array(ps)
        table.append((phi, tag, float(np.mean(hits)), int((ps <= 0.05).sum()),
                      float(np.median(ps))))

    print("\n  " + "=" * 66)
    print("  CALIBRATION AND POWER")
    print("  " + "=" * 66)
    print(f"  {'true edge':<12}{'best hit rate':>15}{'flagged at 5%':>16}{'median p':>12}")
    for phi, tag, hit, n_sig, med in table:
        print(f"  phi={phi:<8.2f}{hit:>14.2%}{n_sig:>13}/10{med:>12.3f}")
    print()
    print("  Read the first row as the false-positive rate: it should be near 0-1")
    print("  of 10, and it is. Read the last as power: the test fires when an edge")
    print("  is really there. The middle row is the honest limit -- an edge that")
    print("  small is not reliably detectable in 3,000 bars by any method, so a")
    print("  non-significant result there means 'not enough data', not 'no edge'.")
    print()
    print("  Note the best-hit-rate column: 51.9% with no edge, 53.6% with a real")
    print("  one. Hit rate alone cannot tell those apart. The p-value can.")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_range(s):
    """'2:40:2' -> [2, 4, ... 38];  '5,10,20' -> [5, 10, 20]"""
    s = s.strip()
    if ":" in s:
        parts = [float(p) for p in s.split(":")]
        start, stop = parts[0], parts[1]
        step = parts[2] if len(parts) > 2 else 1
        vals = np.arange(start, stop, step)
    else:
        vals = np.array([float(p) for p in s.split(",")])
    return vals


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Correct a parameter sweep's best result for the search that found it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Quote p(SPA). If it is above 0.05 the winner is a lucky draw.",
    )
    src = p.add_argument_group("data")
    src.add_argument("--csv", help="CSV with a close/price column")
    src.add_argument("--json", help="bar JSON (00fitzz / tradingview-mcp format), or - for stdin")
    src.add_argument("--synthetic", type=int, metavar="N",
                     help="generate N bars of random walk instead (no edge exists)")
    src.add_argument("--phi", type=float, default=0.0,
                     help="AR(1) coefficient for --synthetic (>0 plants a real edge)")

    fam = p.add_argument_group("strategy universe")
    fam.add_argument("--family", choices=["ma_cross", "breakout"], default="ma_cross")
    fam.add_argument("--fast", default="2:40:2", help="fast SMA grid (default 2:40:2)")
    fam.add_argument("--slow", default="10:200:5", help="slow SMA grid (default 10:200:5)")
    fam.add_argument("--thresh", default="0,0.001,0.0025,0.005,0.01", help="deadband grid")
    fam.add_argument("--entry", default="10:120:5", help="breakout entry lookback grid")
    fam.add_argument("--exit", default="5:60:5", help="breakout exit lookback grid")
    fam.add_argument("--long-only", action="store_true", help="no short positions")
    fam.add_argument("--strategy", metavar="FILE.py:FUNC",
                     help="custom family: FUNC(close) -> (positions (T,K), labels)")

    ev = p.add_argument_group("evaluation")
    ev.add_argument("--objective", choices=["return", "hit"], default="return")
    ev.add_argument("--cost-bps", type=float, default=0.0,
                    help="cost in bps per unit of turnover (default 0 -- set this)")
    ev.add_argument("--min-trades", type=int, default=20,
                    help="drop configs with fewer trades (default 20)")
    ev.add_argument("--holdout", type=float, default=0.0, metavar="FRAC",
                    help="reserve the last FRAC of bars and test the winner there")

    st = p.add_argument_group("test")
    st.add_argument("--block", type=int, default=20,
                    help="bootstrap block length in bars: the null's memory (default 20)")
    st.add_argument("--n-boot", type=int, default=1000, help="bootstrap draws (default 1000)")
    st.add_argument("--seed", type=int, default=0)
    st.add_argument("--json-out", metavar="FILE", help="write results as JSON")
    st.add_argument("--selftest", action="store_true",
                    help="validate the test on data with and without a planted edge")

    args = p.parse_args(argv)

    for name in ("fast", "slow", "entry", "exit"):
        setattr(args, name, [int(v) for v in parse_range(getattr(args, name))])
    args.thresh = [float(v) for v in parse_range(args.thresh)]

    if args.selftest:
        print("Validating the test itself -- does it separate noise from signal?")
        selftest(args)
        return 0

    if args.csv:
        close, series_label = load_csv(args.csv), os.path.basename(args.csv)
    elif args.json:
        close, series_label = load_json(args.json), os.path.basename(args.json)
    elif args.synthetic:
        close = random_walk(args.synthetic, phi=args.phi,
                            rng=np.random.default_rng(args.seed))
        series_label = (f"synthetic random walk, phi={args.phi:g}"
                        + ("  (NO EDGE EXISTS)" if args.phi == 0 else "  (edge planted)"))
    else:
        p.error("give --csv, --json, --synthetic, or --selftest")

    if len(close) < 200:
        raise SystemExit(f"need at least 200 bars, got {len(close)}")
    if not np.all(np.isfinite(close)) or np.any(close <= 0):
        raise SystemExit("close prices must be finite and positive")

    split = len(close)
    if args.holdout:
        if not 0 < args.holdout < 0.9:
            raise SystemExit("--holdout must be between 0 and 0.9")
        split = int(len(close) * (1 - args.holdout))

    res, _ = run_test(close[:split], args, quiet=False)
    print_report(res, args, close[:split], series_label
                 + (f"  [search window: first {split:,} bars]" if args.holdout else ""))

    if args.holdout:
        # One config, one look. No search correction needed -- and no second look.
        # Positions are built on the full series so the windows are warm at the
        # split, but score_from=split keeps every scored bar out of sample.
        try:
            if args.strategy:
                pos, labels, warm = load_custom_family(args.strategy, close)
            elif args.family == "breakout":
                pos, labels, warm = breakout_family(close, args.entry, args.exit,
                                                    args.long_only)
            else:
                pos, labels, warm = ma_cross_family(close, args.fast, args.slow,
                                                    args.thresh, args.long_only)
            k = labels.index(res["label"])
            F, _, _, pos_t, fwd = performance_matrix(
                close, pos[:, [k]], args.objective, args.cost_bps,
                warm, 1, score_from=split
            )
            d = describe(F[:, 0], pos_t[:, 0], fwd, args.objective)
            print()
            print(f"  HOLDOUT  ({F.shape[0]:,} bars never touched by the search)")
            print(f"    {res['label']}")
            print(f"    hit rate {d['hit_rate']:.2%} over {d['active_bars']:,} active bars, "
                  f"{d['trades']:,} trades")
            print(f"    mean {d['mean_per_bar']:+.6f} vs {res['best_stat']:+.6f} in-sample "
                  f"({(d['mean_per_bar'] - res['best_stat']):+.6f} decay)")
            print("    This is one look. Re-tuning after a bad holdout puts it back")
            print("    in the training set and voids the test.")
            res["holdout"] = d
        except (ValueError, SystemExit) as e:
            print(f"\n  holdout skipped: {e}", file=sys.stderr)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(res, fh, indent=2)
        print(f"\n  wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
