# scriptorium

A self-evolving agent layer for **Claude Code**.

Claude Code gives you skills, hooks, and memory — but passive ones. Scriptorium
adds the engine that makes them **grow, sync across devices, and review
themselves** while keeping one agent identity across Claude Code installations.

> A scriptorium was the medieval room where monks copied, archived, and corrected
> manuscripts. Here, four offices tend your agent's manuscripts. See
> [`docs/CHARTER.md`](docs/CHARTER.md).

## Engine vs instance

This repo is the **engine** (public, no personal content). Your agent's
**instance** — `CANON.md`, `memory/`, your skills — lives in *your own* private
repo, located via `SCRIPTORIUM_HOME`.

## Install

Requires **Claude Code ≥ 2.1.186** (older versions reject the plugin's
root-relative `source`). Check with `claude --version`; `claude update` if needed.

```bash
# Claude Code (plugin)
claude plugin marketplace add zyx1121/scriptorium
claude plugin install scriptorium@scriptorium

# point at an instance, or scaffold and bind a fresh one
/scriptorium-init ~/my-agent

```

## Privacy / observability

Scriptorium is local-first and writes observation data into your private instance
under `SCRIPTORIUM_HOME/data/`. The event hook records Claude Code lifecycle and
Skill/Agent metadata + per-session delegation posture; the script observer records non-noise script writes/runs so
repeated patterns can become candidate skills. For script writes it stores the
path, a short content hash, and up to the first 4096 characters as
`content_preview`.

To disable both event and script observation on a machine, create
`~/.claude/scriptorium.local.md` with frontmatter:

```markdown
---
observe: off
---
```

On macOS, a Stop hook (`hooks/notify.py`) posts a system notification when
Claude Code finishes responding; other platforms no-op. Disable it with
`notify: off` in the same frontmatter.

Memory sync (`armarium/memory-sync.sh`) only commits `memory/` changes in your
instance repo. It uses the configured git upstream when available, otherwise it
falls back to the current branch on the first remote; non-git instances no-op.

## Layout

| Dir | Office | Role | Pieces |
|-----|--------|------|--------|
| `armarium/` | Armarium | persistence · sync · index · path map | `paths.py` · `memory-sync.sh` · `gen_memory_index.py` |
| `scribe/` | Scribe | observe signal → author new memory/skills | `events.py` (session/skill/method-route/delegation-ratio) · `observe.py` (scripts) |
| `corrector/` | Corrector | calibrate · consolidate existing (propose-only) | `skill_review.py` · `skills/dreaming` |
| `skills/` | — | engine skills | `method` · `dreaming` |
| `hooks/` | — | wires offices to Claude Code lifecycle | `hooks.json` · `notify.py` |
| `bin/` | — | instance setup helpers | |
