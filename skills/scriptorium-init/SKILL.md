---
name: scriptorium-init
description: "Manually set up the scriptorium plugin for this machine: scaffold or reuse an instance, bind instance skills/agents into Claude Code, link CANON.md into Codex as AGENTS.md, and register the recall/remember MCP server. Invoke explicitly with /scriptorium-init [instance-home]."
disable-model-invocation: true
---

# /scriptorium-init — manual setup

Set up this machine for scriptorium. This skill is manual-only; do not invoke it unless the user explicitly runs `/scriptorium-init`.

## Arguments

- `$ARGUMENTS` is the optional instance home.
- If omitted, use `$SCRIPTORIUM_HOME`; if that is unset, use `~/.scriptorium`.

## Workflow

Run the setup script from the plugin root:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/scriptorium-setup.py" $ARGUMENTS
```

This is idempotent and performs the full local wiring:

- scaffold the instance skeleton: `CANON.md`, `memory/`, `skills/`, `agents/`, `data/`, `state/`, `staged/`;
- bind instance skills and agents into Claude Code via symlinks under `~/.claude`;
- link the instance `CANON.md` into Codex as `~/.codex/AGENTS.md`;
- create/update the instance-local MCP venv under `state/` and register the `scriptorium` recall/remember MCP server with Codex when the `codex` CLI is available.

After it finishes, tell the user:

- which instance path was configured;
- whether Claude and Codex binding succeeded or was skipped;
- to edit `CANON.md` before relying on the agent identity;
- to run `/reload-plugins` if they need newly added plugin components in the current Claude Code session.
