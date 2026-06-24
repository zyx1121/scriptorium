#!/usr/bin/env python3
"""Armarium — generate the instance's memory/MEMORY.md from each file's frontmatter.

Single source of truth = each memory file's frontmatter `title` + `description`.
MEMORY.md is a BUILD ARTIFACT — never hand-edit it; edit the memory file's
frontmatter and rerun. Invoked by memory-sync.sh (pre-commit) and the dreaming skill.

Index row: `- [<title>](<file>) — <description>`, sorted by filename (the
type prefix naturally groups by type). Zero deps (stdlib only) so it runs
identically on macOS / Linux / Windows.

Usage:  gen_memory_index.py [MEMORY_DIR]   (defaults to SCRIPTORIUM_HOME/memory)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KEY_RE = re.compile(r"^(title|description):\s*(.*)$")


def _default_memory_dir() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from armarium import paths
    return paths.memory_dir()


def unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return v


def frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        m = KEY_RE.match(line)
        if m:
            out[m.group(1)] = unquote(m.group(2))
    return out


def build_rows(mem_dir: Path) -> tuple[list[str], list[str]]:
    """Return (index rows, filenames missing a title). Pure — no IO beyond reads."""
    rows, warn = [], []
    for p in sorted(mem_dir.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        fm = frontmatter(p.read_text(encoding="utf-8"))
        title = fm.get("title") or p.stem
        if not fm.get("title"):
            warn.append(p.name)
        rows.append(f'- [{title}]({p.name}) — {fm.get("description", "")}')
    return rows, warn


def main() -> int:
    mem = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else _default_memory_dir()
    index = mem / "MEMORY.md"
    rows, warn = build_rows(mem)
    index.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"gen-memory-index: {len(rows)} entries -> {index}")
    if warn:
        print(f'  WARN missing title ({len(warn)}): {", ".join(warn)}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
