---
name: fix-the-pattern-not-the-instance
description: A bug that is a property of a pattern recurs in every sibling that shares the pattern — grep for the shape before calling it fixed.
metadata:
  type: feedback
---

When a defect turns out to be a property of a **pattern** rather than of a
line, fixing the instance you tripped over is not fixing the defect. Grep for
the shape across the repo before reporting it fixed.

On 2026-11-03 I found and fixed `run_sweep_4h.py` exiting 0 when it fetched
nothing (bug 9 in `FINDINGS.md`), wrote it up, and committed. Hours later
`fitzz trade --backtest` did exactly the same thing: all seven symbols
refused, five strategies, `exit 0` every time, because `cmd_backtest`
returns its results list instead of a status. Two commands in the same repo
fetch a list of symbols and summarise them; only one could report that it
had failed, and I had just finished writing about the other one.

**Why:** an exit status that lies is worse than no exit status, because
every wrapper, loop and CI step above it believes the run succeeded. The
cost of the grep is seconds; the cost of missing it is a silent failure that
looks like data.

**How to apply:** after fixing a bug, ask what *class* it belongs to, then
search for siblings — other entry points, other callers of the same helper,
other places with the same control-flow shape. Do this before the commit, so
the write-up covers the class rather than the instance. Related:
[[unit-test-not-callsite]], which is the same mistake one level down.
