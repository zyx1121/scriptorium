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

## Install

Requires **Claude Code ≥ 2.1.186** (older versions reject the plugin's
root-relative `source`). Check with `claude --version`; `claude update` if needed.

```bash
# Claude Code (plugin)
claude plugin marketplace add zyx1121/scriptorium
claude plugin install scriptorium@scriptorium

# point at an instance, or scaffold and bind a fresh one
/scriptorium-init ~/my-agent

# Codex (doesn't load CC plugins): identity + the recall/remember MCP
# `/scriptorium-init` also links CANON.md into Codex and registers the MCP
# server when the `codex` CLI is available.
```

## Layout

| Dir | Office | Role | Pieces |
|-----|--------|------|--------|
| `armarium/` | Armarium | persistence · sync · index · path map | `paths.py` · `memory-sync.sh` · `gen_memory_index.py` |
| `scribe/` | Scribe | observe signal → author new memory/skills | `events.py` (session/skill/method-route) · `observe.py` (scripts) |
| `corrector/` | Corrector | calibrate · consolidate existing (propose-only) | `skill_review.py` · `skills/dreaming` |
| `mcp/` | — | portable memory MCP | `scriptorium_mcp.py` (recall / remember) |
| `skills/` | — | engine skills | `method` · `dreaming` |
| `hooks/` | — | wires offices to CC/Codex lifecycle | `hooks.json` |
| `bin/` | — | instance setup + Codex binding helpers | |

---

## Status

- **S0 ✅** engine scaffolded — four offices, 41 tests green.
- **Engine feature-complete ✅** — Armarium (memory-sync + index), Scribe (observe
  + events + method-route), Corrector (skill-review + dreaming), MCP (recall /
  remember). **110 tests green.** Migrated out of `kilo` and de-personalized:
  daemon-only MCP tools (Telegram / mail / scheduler) deliberately left in the
  instance, not the public engine.
- **S1 ✅** verified installable on a clean VM — plugin install + `init` + a real
  CC session auto-firing hooks into a fresh instance.
- **S2 ✅** migration verified on a live instance (PVE `kilo`: 21 skills, 63
  memories) — `CANON.md → KILO.md` symlink, engine reads the real persona, hooks
  write to the real `data/`, all additive: old binding (KILO.md, Codex) untouched,
  zero git pollution.
- **S3 — todo:** migrate the Mac core. Pending cleanups surfaced en route:
  drop the duplicate `method` skill from instances (engine ships it); the dead
  `growth/review.py`; converge `nudge.py`.

Migrating the working parts out of `zyx1121/kilo`, which becomes the first
private *instance*.
