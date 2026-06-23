---
description: Scaffold a fresh scriptorium instance (CANON.md + memory/ + skills/ + data/) at SCRIPTORIUM_HOME so the engine has manuscripts to tend.
---

Run the instance scaffolder, then report what was created and remind the user to
edit `CANON.md` (the agent's identity) before starting:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/scriptorium-init.py" "${SCRIPTORIUM_HOME:-$HOME/.scriptorium}"
```

If `SCRIPTORIUM_HOME` is unset, tell the user to add `export SCRIPTORIUM_HOME=...`
to their shell profile so every runtime points at the same instance.
