#!/usr/bin/env python3
"""scriptorium MCP server — exposes the instance's durable memory as MCP tools so
agents (Codex especially) recall/remember uniformly instead of hand-editing files.

Only the two PORTABLE memory primitives live here — recall + remember — reading and
writing SCRIPTORIUM_HOME/memory. Instance-specific capabilities (Telegram, mail,
schedulers, delegation) belong in that instance's own MCP, not the engine.

Register with Codex:
    codex mcp add scriptorium --env SCRIPTORIUM_HOME=<home> -- \
        python3 <engine>/mcp/scriptorium_mcp.py

stdio transport: NOTHING may be printed to stdout (it carries the MCP protocol).
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # engine root onto path
from armarium import paths  # noqa: E402


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-") or "note"


def _fm_title(txt: str) -> str | None:
    m = re.search(r"^title:\s*(.+)$", txt, re.MULTILINE)
    return m.group(1).strip() if m else None


def _git(home: Path, *args) -> None:
    try:
        subprocess.run(["git", "-C", str(home), *args], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def do_remember(home: Path, slug: str, title: str, body: str, hook: str = "",
                mtype: str = "semantic") -> str:
    """Write a durable memory file + update the index. Pure-ish: filesystem + a
    best-effort git commit (no-op when the instance isn't a repo). Returns a status
    line. The frontmatter carries `description: <hook>` so gen_memory_index rebuilds
    the SAME index row this writes — the two index paths stay consistent."""
    mem = home / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    slug = _slugify(slug)
    title = " ".join(title.split())   # newline would corrupt YAML / split the index row
    hook = " ".join(hook.split())
    path = mem / f"{slug}.md"
    fm = f"---\ntitle: {title}\n"
    if hook:
        fm += f"description: {hook}\n"
    fm += f"type: {mtype}\n---\n\n{body.strip()}\n"
    path.write_text(fm, encoding="utf-8")

    # Flat layout: MEMORY.md sits beside the files; one bullet list, no section headers.
    index = mem / "MEMORY.md"
    marker = f"({slug}.md)"
    link_text = title.replace("[", "").replace("]", "")
    line = f"- [{link_text}]({slug}.md)" + (f" — {hook}" if hook else "")
    try:
        idx_lines = index.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        idx_lines = []
    for i, l in enumerate(idx_lines):
        if marker in l:
            idx_lines[i] = line
            break
    else:
        idx_lines.append(line)
    index.write_text("\n".join(idx_lines) + "\n", encoding="utf-8")

    _git(home, "add", str(path), str(index))
    _git(home, "commit", "-q", "-m", f"mem: remember {slug}")
    return f"remembered → memory/{slug}.md (indexed)"


def do_recall(home: Path, query: str, limit: int = 8) -> str:
    """Case-insensitive substring search over the instance's memory files."""
    q = query.lower()
    hits = []
    for path in sorted(glob.glob(str(home / "memory" / "*.md"))):
        if os.path.basename(path) == "MEMORY.md":
            continue
        try:
            txt = open(path, encoding="utf-8").read()
        except OSError:
            continue
        if q in txt.lower():
            title = _fm_title(txt) or os.path.basename(path)
            rel = os.path.relpath(path, home)
            body = txt.split("---", 2)[-1].strip().replace("\n", " ")
            hits.append(f"[memory] {title} ({rel})\n  {body[:200]}")
    if not hits:
        return f"no memory matches for: {query}"
    return "\n".join(hits[:limit])


def _build_mcp():
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("scriptorium")

    @mcp.tool()
    def remember(slug: str, title: str, body: str, hook: str = "") -> str:
        """Persist a durable fact (preference, convention, project fact) as memory so it
        survives across sessions. `slug` = short kebab-case id (re-using a slug updates it);
        `title` = one-line summary; `body` = the fact in markdown; `hook` = a short phrase
        for the MEMORY.md index so future runs judge relevance from one line."""
        return do_remember(paths.instance_home(), slug, title, body, hook)

    @mcp.tool()
    def recall(query: str, limit: int = 8) -> str:
        """Search durable memory for `query` (case-insensitive substring). Use at the start
        of a task to recall what you already know instead of re-asking."""
        return do_recall(paths.instance_home(), query, limit)

    return mcp


if __name__ == "__main__":
    _build_mcp().run()
