# scriptorium

A self-evolving agent layer over **Claude Code** and **Codex**.

CC/Codex give you skills, hooks, and memory — but passive ones. Scriptorium adds
the engine that makes them **grow, sync across devices, and review themselves**,
while keeping **one agent identity** across every runtime.

> A scriptorium was the medieval room where monks copied, archived, and corrected
> manuscripts. Here, four offices tend your agent's manuscripts. See
> [`docs/CHARTER.md`](docs/CHARTER.md).

## Engine vs instance

This repo is the **engine** (public, no personal content). Your agent's
**instance** — `CANON.md`, `memory/`, your skills — lives in *your own* private
repo, located via `SCRIPTORIUM_HOME`.

## Install *(planned — S0/S1)*

```bash
# Claude Code (plugin)
claude plugin marketplace add zyx1121/scriptorium
claude plugin install scriptorium

# point at an instance, or scaffold a fresh one
export SCRIPTORIUM_HOME=~/my-agent
scriptorium init "$SCRIPTORIUM_HOME"

# Codex (doesn't load CC plugins)
bin/codex-bind.sh
```

## Layout

| Dir | Office | Role |
|-----|--------|------|
| `armarium/` | Armarium | persistence · sync · index · canon binding |
| `scribe/` | Scribe | observation → authoring new memory/skills |
| `corrector/` | Corrector | calibrate · consolidate · promote existing |
| `skills/` | — | engine skills (`method`, `dreaming`, `review`) |
| `hooks/` | — | wires the offices to CC/Codex lifecycle events |
| `commands/` | — | `/scriptorium-init`, … |
| `bin/` | — | install + Codex-binding scripts |

---

**Status: S0 — scaffolding the engine.** Migrating the working parts out of
`zyx1121/kilo` (which becomes the first private *instance*).
