# Scriptorium — Charter

Claude Code and Codex give you primitives — skills, hooks, memory — but they are
**passive**: they don't grow, don't sync across machines, don't review themselves.
Scriptorium is the engine that adds the missing **self-evolution** layer on top,
and keeps **one agent identity** across every runtime and device.

> A *scriptorium* was the room in a medieval monastery where monks copied,
> archived, and corrected manuscripts — distributed, versioned, by hand. Scribes
> in different abbeys tended the same body of text. That is exactly this: your
> agent's manuscripts (persona, memory, skills) tended by four offices.

## Engine vs instance (the core split)

- **Engine** — *this repo, public.* The four offices + the machinery to install
  them onto Claude Code / Codex. Ships with **no personal content**.
- **Instance** — *your private repo.* The manuscripts themselves: `CANON.md`,
  `memory/`, your own skills. Located via the `SCRIPTORIUM_HOME` env var.

One engine, many instances. `scriptorium init` scaffolds a fresh instance, so
anyone can grow their own agent on the same engine.

## The four offices

### Canon — *identity*
The unchanging core that defines **who the agent is**: persona, voice, guardrails.
Every runtime loads the same Canon, so Claude-on-Mac and Codex-on-VM are *one
agent*, not separate chatbots.
- Lives in the instance as `CANON.md`. The engine only **binds** it to each
  runtime — it **never rewrites it** (no self-modifying guardrails).

### Armarium — *persistence & versioning*
The library. Keeps every manuscript under **git**, synced across machines, with
rollback and audit. Pure infrastructure — produces nothing, digests nothing.
- sync · index generation · binding the Canon into CC/Codex.

### Scribe — *self-authoring*
The copyist. Turns raw signal (sessions, tool usage) into **new** manuscripts —
proposing or writing new memory and skills. From nothing to something.
- observation (events / observe) · extraction.

### Corrector — *self-review*
The proof-reader. Tends **existing** manuscripts — calibrating skills,
de-duplicating and merging memory, promoting the most essential facts toward the
Canon. Never silently overwrites hand-written assets (**propose-only**).
- skill calibration · consolidation · promotion.

## Boundaries that keep it clean

1. **Scribe creates, Corrector corrects.** Anything doing both is mislocated.
   (This is exactly why the old monolithic review job was the #1 source of mess.)
2. **Engine code carries no personal content; instance data carries no logic.**
3. **The Canon is owner-only.** Growth may *propose*, never auto-edit guardrails.
