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
  - unquoted-desc : a bare (unquoted) `description:` scalar — Claude Code's memory
                    normalizer truncates these; wrap the value in double quotes

Usage:  gen_memory_index.py [MEMORY_DIR ...]   (1+ dirs; MEMORY.md is written into the
        FIRST dir and every row's link is relative to it, so files in the other dirs — e.g.
        a shared common-memory/memory submodule — get a correct `../…` path. Defaults to
        SCRIPTORIUM_HOME/memory. Missing dirs are skipped, so an instance that hasn't mounted
        the common submodule still builds its index from what's present.)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

KEY_RE = re.compile(r"^(title|description):\s*(.*)$")
# `type:` may sit at the top level OR nested under `metadata:` — match either by
# ignoring leading indentation (instance corpora use both shapes historically).
TYPE_RE = re.compile(r"^\s*type:\s*([A-Za-z]+)\s*$", re.M)
WIKILINK_RE = re.compile(r"\[\[([^\]\|]+?)\]\]")
DESC_RE = re.compile(r"^description:\s*(.*)$", re.M)
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


def build_rows(mem_dirs, index_dir=None) -> tuple[list[str], dict[str, list[str]]]:
    """Return (index rows, lint warnings keyed by category). Pure — reads only.

    mem_dirs: a single dir (Path/str) OR a list of dirs merged into one index — e.g. the
    instance memory/ plus a shared common-memory/memory submodule. index_dir is where
    MEMORY.md lives; each row's link is computed relative to it, so files in the other dirs
    (common) get a correct `../…` path. Defaults to the first dir. Lint (orphan-link etc.)
    is computed over the UNION, so a private→common [[wikilink]] resolves correctly.

    warnings keys: missing-title, bad-type, orphan-link, unquoted-desc (see module docstring)."""
    if isinstance(mem_dirs, (str, Path)):
        mem_dirs = [mem_dirs]
    mem_dirs = [Path(d) for d in mem_dirs]
    index_dir = Path(index_dir) if index_dir is not None else mem_dirs[0]
    files = sorted(
        (p for d in mem_dirs for p in d.glob("*.md") if p.name != "MEMORY.md"),
        key=lambda p: p.name,
    )
    stems = {p.stem for p in files}
    rows: list[str] = []
    warn: dict[str, list[str]] = {"missing-title": [], "bad-type": [], "orphan-link": [], "unquoted-desc": []}
    for p in files:
        text = p.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if not fm.get("title"):
            warn["missing-title"].append(p.name)
        prefix = re.split(r"[_-]", p.stem, maxsplit=1)[0]
        tval = type_of(text)
        if tval not in VALID_TYPES or (prefix in VALID_TYPES and prefix != tval):
            warn["bad-type"].append(f"{p.name}(prefix={prefix}, type={tval})")
        dm = DESC_RE.search(_fm_block(text))
        if dm and dm.group(1).strip() and not dm.group(1).strip().startswith('"'):
            warn["unquoted-desc"].append(p.name)
        for m in WIKILINK_RE.finditer(text):
            tgt = m.group(1).strip()
            if tgt not in stems:
                warn["orphan-link"].append(f"{p.name}→[[{tgt}]]")
        link = os.path.relpath(p, index_dir)
        rows.append(f'- [{fm.get("title") or p.stem}]({link}) — {fm.get("description", "")}')
    return rows, warn


def main() -> int:
    args = [Path(a).expanduser() for a in sys.argv[1:]] or [_default_memory_dir()]
    index_dir = args[0]
    # Skip dirs that don't exist (e.g. the common-memory submodule on an instance that
    # hasn't mounted it) so the index still builds from whatever is present.
    mem_dirs = [d for d in args if d.is_dir()] or [index_dir]
    index = index_dir / "MEMORY.md"
    rows, warn = build_rows(mem_dirs, index_dir=index_dir)
    index.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"gen-memory-index: {len(rows)} entries from {len(mem_dirs)} dir(s) -> {index}")
    total = sum(len(v) for v in warn.values())
    if total:
        print(f"  LINT: {total} convention issue(s) — for the dreaming 規範對齊 step:")
        for cat, items in warn.items():
            if items:
                print(f"    {cat} ({len(items)}): {', '.join(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
