---
name: claude-commits-separate-from-long-runs
description: Never bundle a git commit into the same turn as a long-running job — the user may interrupt and the commit state becomes unclear.
metadata:
  type: feedback
---

Do not put a `git commit` in the same response as a long-running task (a sweep, a cost scan, a multi-symbol fetch). Commit first and let it land, or run the job and commit after.

**Why:** In the 2026-10 fitzz session I bundled a commit with a sweep. The user interrupted the sweep, and I then told them nothing had run — but commit `ee0526f` had already landed. An interrupt leaves the repository in a state neither of us can see without checking, and I reported it wrongly.

**How to apply:** One turn, one kind of work. If an interrupt happens around a turn that touched git, run `git log -1` and `git status` before saying anything about what did or did not happen.
