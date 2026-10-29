---
name: node-nvm-setup
description: "Node.js is installed via nvm, not on the default PATH — source it before node/npm commands"
metadata: 
  node_type: memory
  type: reference
  originSessionId: f48fca54-aa36-4352-8327-5932bdc7f573
  modified: 2026-08-06T20:24:41.020Z
---

Node.js on this Mac is installed **only via nvm** (installed 2026-08-06). The default non-login shell PATH does NOT include node/npm — `node`/`npm` will report "command not found" unless nvm is sourced first.

To use node/npm in a Bash call, prefix with:

```bash
export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"; nvm use --lts >/dev/null 2>&1
```

- Version: Node v24.19.0 (npm 11.17.0), aliased `default -> lts/*`.
- Binary path: `~/.nvm/versions/node/v24.19.0/bin/node`.
- `~/.zprofile` sources nvm, but non-login shells may skip it — hence the explicit source above.

Related: [[tradingview-mcp-install]].
