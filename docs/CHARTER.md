# Scriptorium — Charter

Claude Code gives you primitives — skills, hooks, memory — but they are
**passive**: they don't grow, don't sync across machines, don't review themselves.
Scriptorium is the engine that adds the missing **self-evolution** layer on top.

> A *scriptorium* was the room in a medieval monastery where monks copied,
> archived, and corrected manuscripts — distributed, versioned, by hand. Scribes
> in different abbeys tended the same body of text. That is exactly this: your
> agent's manuscripts (persona, memory, skills, agents) tended by four offices.

## Engine vs instance (the core split)

- **Engine** — *this repo, public.* The four offices + the machinery to install
  them onto Claude Code. Ships with **no personal content**.
- **Instance** — *your private repo.* The manuscripts themselves: `CANON.md`,
  `memory/`, your own skills, your delegation `agents/`. Located via the
  `SCRIPTORIUM_HOME` env var.

One engine, many instances. `/scriptorium-init` scaffolds a fresh instance, so
anyone can grow their own agent on the same engine.

## The four offices

### Canon — *identity*
The unchanging core that defines **who the agent is**: persona, voice, guardrails.
Every Claude Code installation loads the same Canon, so Claude-on-Mac and
Claude-on-VM share identity instead of becoming unrelated chatbots.
- Lives in the instance as `CANON.md`. The engine only **binds** it to each
  runtime — it **never rewrites it** (no self-modifying guardrails).

### Armarium — *persistence & versioning*
The library. Keeps every manuscript under **git**, synced across machines, with
rollback and audit. Pure infrastructure — produces nothing, digests nothing.
- sync · index generation · binding the Canon into Claude Code.

### Scribe — *self-authoring*
The copyist. Turns raw signal (sessions, tool usage) into **new** manuscripts —
proposing new skills and agents. From nothing to something.
- observation (events / observe) · authoring (`author.py` → `staged/`, propose-only).

### Corrector — *self-review*
The proof-reader. Tends **existing** manuscripts — calibrating skills and agents,
de-duplicating and merging memory, promoting the most essential facts toward the
Canon. Never silently overwrites hand-written assets (**propose-only**).
- skill / agent calibration · consolidation · promotion.

## The four manuscript types

Claude Code ships these primitives but leaves them **passive** — slots that never
grow, sync, or review themselves. Scriptorium tends four kinds of manuscript:

1. **Canon** — identity. `CANON.md`. Hand-written; the engine binds it, never edits.
2. **Memory** — durable facts. `memory/*.md`, indexed by `MEMORY.md`.
3. **Skills** — behaviours. `skills/<name>/SKILL.md`.
4. **Agents** — the delegation fleet. `agents/*.md` (one subagent per role) plus
   `agents/README.md` (the shared report contract) — the workers a lead delegates
   isolatable coding / survey / review to, so it stays an orchestrator instead of
   doing everything in one context.

Adding a type means teaching every office to tend it: **Armarium** binds & versions
it, **Scribe** authors new ones, **Corrector** calibrates existing ones. Memory,
skills, and agents are all engine-tended; only the Canon is owner-only.

## Boundaries that keep it clean

1. **Scribe creates, Corrector corrects.** Anything doing both is mislocated.
   (This is exactly why the old monolithic review job was the #1 source of mess.)
2. **Engine code carries no personal content; instance data carries no logic.**
3. **The Canon is owner-only.** Growth may *propose*, never auto-edit guardrails.
