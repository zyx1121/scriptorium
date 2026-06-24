#!/usr/bin/env python3
"""Armarium — generate the instance's memory/MEMORY.md from each file's frontmatter,
and lint the corpus for convention drift.

Single source of truth = each memory file's frontmatter `title` + `description`.
MEMORY.md is a BUILD ARTIFACT — never hand-edit it; edit the memory file's
frontmatter and rerun. Invoked by memory-sync.sh (pre-commit) and the dreaming skill.

Index row: `- [<title>](<file>) — <description>`, sorted by filename (the
type prefix naturally groups by type). Zero deps (stdlib only) so it runs
identically on macOS / Linux / Windows.

Lint — surfaced for the dreaming skill's 規範對齊 (convention-alignment) step,
never auto-mutates (mutating hand-written memory stays human/dreaming-gated):
  - missing-title : no `title:` frontmatter → index falls back to the filename
  - bad-type      : `type:` absent/invalid, or mismatching the filename prefix
  - orphan-link   : a `[[wikilink]]` whose target is not an existing memory file
                    (catches `-`/`_` naming drift as well as truly dangling refs)

Usage:  gen_memory_index.py [MEMORY_DIR]   (defaults to SCRIPTORIUM_HOME/memory)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KEY_RE = re.compile(r"^(title|description):\s*(.*)$")
# `type:` may sit at the top level OR nested under `metadata:` — match either by
# ignoring leading indentation (instance corpora use both shapes historically).
TYPE_RE = re.compile(r"^\s*type:\s*([A-Za-z]+)\s*$", re.M)
WIKILINK_RE = re.compile(r"\[\[([^\]\|]+?)\]\]")
VALID_TYPES = ("feedback", "project", "reference", "user")


def _default_memory_dir() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from armarium import paths
    return paths.memory_dir()


def unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return v


def _fm_block(text: str) -> str:
    """Raw frontmatter block between the leading --- fences, or '' if none."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end >= 0 else ""


def frontmatter(text: str) -> dict:
    out = {}
    for line in _fm_block(text).splitlines():
        m = KEY_RE.match(line)
        if m:
            out[m.group(1)] = unquote(m.group(2))
    return out


def type_of(text: str) -> str | None:
    """The declared `type`, top-level or nested under metadata; None if absent."""
    m = TYPE_RE.search(_fm_block(text))
    return m.group(1) if m else None


def build_rows(mem_dir: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Return (index rows, lint warnings keyed by category). Pure — reads only.

    warnings keys: missing-title, bad-type, orphan-link (see module docstring)."""
    files = [p for p in sorted(mem_dir.glob("*.md")) if p.name != "MEMORY.md"]
    stems = {p.stem for p in files}
    rows: list[str] = []
    warn: dict[str, list[str]] = {"missing-title": [], "bad-type": [], "orphan-link": []}
    for p in files:
        text = p.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if not fm.get("title"):
            warn["missing-title"].append(p.name)
        prefix = re.split(r"[_-]", p.stem, 1)[0]
        tval = type_of(text)
        if tval not in VALID_TYPES or (prefix in VALID_TYPES and prefix != tval):
            warn["bad-type"].append(f"{p.name}(prefix={prefix}, type={tval})")
        for m in WIKILINK_RE.finditer(text):
            tgt = m.group(1).strip()
            if tgt not in stems:
                warn["orphan-link"].append(f"{p.name}→[[{tgt}]]")
        rows.append(f'- [{fm.get("title") or p.stem}]({p.name}) — {fm.get("description", "")}')
    return rows, warn


def main() -> int:
    mem = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else _default_memory_dir()
    index = mem / "MEMORY.md"
    rows, warn = build_rows(mem)
    index.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"gen-memory-index: {len(rows)} entries -> {index}")
    total = sum(len(v) for v in warn.values())
    if total:
        print(f"  LINT: {total} convention issue(s) — for the dreaming 規範對齊 step:")
        for cat, items in warn.items():
            if items:
                print(f"    {cat} ({len(items)}): {', '.join(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
