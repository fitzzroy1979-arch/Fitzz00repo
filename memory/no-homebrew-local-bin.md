---
name: no-homebrew-local-bin
description: No Homebrew on this Mac; install user CLIs as binaries into ~/.local/bin
metadata:
  type: project
---

This Mac (arm64) has no Homebrew — neither `/opt/homebrew` nor `/usr/local/Homebrew` exists, and `brew` is not on PATH. Installing it needs a sudo password, so I can't do it.

Instead, user-level CLI tools go into `~/.local/bin`, which is already on PATH. Pattern: download the official arm64 release tarball/zip, verify its published SHA256, copy the binary in, `chmod +x`.

`gh` 2.98.0 was installed this way on 2026-08-27. Node is separate — see [[node-nvm-setup]].

**Why:** Suggesting `brew install X` here always fails, and the fix is not obvious from the repo.
**How to apply:** When a tool is missing, skip brew — offer the direct-binary-into-`~/.local/bin` route, and ask before downloading.
