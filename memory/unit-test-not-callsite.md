---
name: unit-test-not-callsite
description: A unit test of a function is not a test of the code that calls it — verify the real invocation
metadata:
  type: feedback
---

On 2026-11-03 I added a fetch counter to `run_sweep_4h.py` so a run that
fetched nothing would stop exiting 0. I unit-tested the new `_exit_status`
helper for all three cases, reported it as tested, and pushed. The next real
run crashed on its second symbol: I had named the counter `ok`, and `ok`
already held the `block ok` column's "yes"/"NO" inside the family loop, so it
became a string and `ok += 1` raised TypeError.

The helper was never wrong. The bug was at the **call site**, in a scope the
test never entered.

**Why:** I chose the unit test deliberately — a real invocation would have
contended with a running sweep for the TradingView chart lock. That was a
correct concern and the wrong conclusion: the answer was to wait for the
sweep and then run it, not to declare the change verified without ever
executing it. Saying "unit-tested for all three cases" was true and
misleading in the same sentence.

**How to apply:** When adding a variable to an existing function, grep the
name in that scope first — in this codebase `ok`, `n`, `res` and `d` are all
reused. Before reporting a change as verified, run the actual entry point
once, even on a single symbol; if something else holds a lock, wait for it.
Reserve "tested" for the path the user will run. See
[[backtest-evidence-order]] and [[claude-commits-separate-from-long-runs]].
