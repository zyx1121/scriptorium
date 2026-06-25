#!/usr/bin/env python3
"""scriptorium init — scaffold a fresh INSTANCE at SCRIPTORIUM_HOME (or argv[1]).

Creates the manuscript skeleton the engine reads: CANON.md + memory/ + skills/ +
agents/ + data/ + state/ + staged/. Idempotent — never clobbers an existing
CANON.md or memory index. This is what makes "install the engine, then start
using it" true: the engine is empty until an instance exists for it to tend.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import gen_memory_index as gmi  # noqa: E402

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



def instance_home() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser()
    env = os.environ.get("SCRIPTORIUM_HOME")
    return Path(env).expanduser() if env else Path.home() / ".scriptorium"


def ensure_instance(home: Path) -> None:
    for d in ("memory", "skills", "agents", "data/events", "state", "staged"):
        (home / d).mkdir(parents=True, exist_ok=True)

    canon = home / "CANON.md"
    if not canon.exists():
        canon.write_text(CANON_TEMPLATE, encoding="utf-8")
    idx = home / "memory" / "MEMORY.md"
    if not idx.exists():
        # Generate the canonical (empty) index — same format memory-sync rebuilds,
        # so the first sync won't silently rewrite a hand-shaped template.
        rows, _ = gmi.build_rows(home / "memory")
        idx.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    home = instance_home()
    before = {
        "CANON.md": (home / "CANON.md").exists(),
        "memory/MEMORY.md": (home / "memory" / "MEMORY.md").exists(),
    }
    ensure_instance(home)
    created = []
    if not before["CANON.md"]:
        created.append("CANON.md")
    if not before["memory/MEMORY.md"]:
        created.append("memory/MEMORY.md")

    print(f"scriptorium instance ready at {home}")
    print(f"  scaffolded: {', '.join(created) if created else '(already initialized — nothing clobbered)'}")
    print(f"  next: export SCRIPTORIUM_HOME={home} and edit CANON.md to give your agent a soul.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
