#!/usr/bin/env python3
"""scriptorium init — scaffold a fresh INSTANCE at SCRIPTORIUM_HOME (or argv[1]).

Creates the manuscript skeleton the engine reads: CANON.md + memory/ + skills/ +
data/ + state/ + staged/. Idempotent — never clobbers an existing CANON.md or
memory index. This is what makes "install the engine, then start using it" true:
the engine is empty until an instance exists for it to tend.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

CANON_TEMPLATE = """# CANON — <name your agent>

> The unchanging core: who this agent is. Hand-written by you; the engine
> (scriptorium) loads it into every runtime but NEVER rewrites it.

## Identity
<who the agent is — name, role, who it serves>

## Voice
<how it speaks — tone, language, what to skip>

## Guardrails
<hard rules it must never break — safety, scope, what to confirm before doing>
"""

MEMORY_INDEX = (
    "# MEMORY — index\n\n"
    "> One line per memory; the full entry lives in `memory/<name>.md`. "
    "The scribe appends here as it learns; the corrector consolidates.\n"
)


def instance_home() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser()
    env = os.environ.get("SCRIPTORIUM_HOME")
    return Path(env).expanduser() if env else Path.home() / ".scriptorium"


def main() -> int:
    home = instance_home()
    for d in ("memory", "skills", "data/events", "state", "staged"):
        (home / d).mkdir(parents=True, exist_ok=True)

    created = []
    canon = home / "CANON.md"
    if not canon.exists():
        canon.write_text(CANON_TEMPLATE, encoding="utf-8")
        created.append("CANON.md")
    idx = home / "memory" / "MEMORY.md"
    if not idx.exists():
        idx.write_text(MEMORY_INDEX, encoding="utf-8")
        created.append("memory/MEMORY.md")

    print(f"scriptorium instance ready at {home}")
    print(f"  scaffolded: {', '.join(created) if created else '(already initialized — nothing clobbered)'}")
    print(f"  next: export SCRIPTORIUM_HOME={home} and edit CANON.md to give your agent a soul.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
