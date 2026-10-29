# memory

Claude Code's persistent memory for this project — one fact per file, with
frontmatter giving a slug, a one-line description and a type (`user`,
`feedback`, `project`, `reference`). `MEMORY.md` is the index loaded at the
start of each session; the body files are read on demand. `[[slug]]` links
point between them.

These are tracked here rather than left in `~/.claude/` so that the reasoning
behind `FINDINGS.md` travels with the repo. Several are worth reading on
their own — `backtest-evidence-order.md` and `pooled-comparison-composition.md`
are the two that most often change how a result should be read.

## The directory is symlinked

Claude Code reads memory from a path under `~/.claude/`, so the real files
live here and that path is a symlink to this directory:

```
~/.claude/projects/-Users-<user>-Desktop-AI/memory -> <repo>/memory
```

A fresh clone does not have that link. To wire it up, back up anything
already at the target, then point it here:

```bash
TARGET=~/.claude/projects/-Users-$USER-Desktop-AI/memory
mv "$TARGET" "$TARGET.bak" 2>/dev/null
ln -s "$PWD/memory" "$TARGET"
```

Without the link nothing breaks — Claude keeps its own memory at the original
path and this directory is simply a set of markdown files.

## What is deliberately not here

This repo is public. `local-*.md` and `private-*.md` are gitignored for
account and machine specifics, so a memory written during a session can hold
them without publishing them. The files that are tracked use `~` rather than
absolute home paths, which also makes them portable.

If you add a memory with anything account-specific in it, name it
`local-<slug>.md` or move the specifics into `local-workspace.md` and link to
it; the tracked file can reference `[[local-workspace]]` without containing
anything itself.
