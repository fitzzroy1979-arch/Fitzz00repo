---
name: guards-that-fail-open
description: A guard that returns "pass" when it cannot evaluate protects nothing — its blind spot correlates with the fault it checks for.
metadata:
  type: feedback
---

A check that returns **pass** when it cannot evaluate the condition is not a
weak check, it is close to no check. Its blind spot is correlated with the
fault: whatever breaks the thing being verified usually breaks the
verification too.

On 2026-11-03 `fitzz`'s `_prices_agree` compared a bar series against a live
quote to catch the bridge serving one symbol's data for another. It ended
with `if price is None: return True` -- an unverifiable read was treated as
fine. The quote comes through the same bridge as the bars, so when the
bridge degraded, both failed together and the guard waved through BTC's
series labelled as ZBCN. Three earlier bugs had been caught by that guard,
which is exactly why nobody tested what it did when it could not run.

**The check that worked needed no live data at all.** One symbol over one
period has one buy-and-hold return, whatever strategy is traded on it, so
comparing that number for the same symbol across runs is an internal
consistency condition on files already written. Prefer a verification that
reads only the output over one that re-queries the suspect source.

**The empty-input case is the same bug and is easy to miss.** On 2026-11-03
the very checker written to catch the above -- `check_backtest.py`, which
compares buy-and-hold across runs -- printed "nothing to check, this is not
a pass" when its glob matched no files, **and exited 0**. It said in words
that it had verified nothing and reported success to its caller in the same
breath. "Cannot evaluate" and "had nothing to evaluate" are the same
condition as far as the exit status is concerned.

**How to apply:** when writing or reviewing a guard, ask what it returns when
its own input is missing or empty, and whether that case is independent of
the failure it is meant to detect. If it is not independent, fail closed, or retry and
then refuse — never pass silently. And when a guard has a good track record,
that is a reason to test its failure mode, not to trust it. See
[[tv-bridge-data-integrity]] and [[fix-the-pattern-not-the-instance]].
