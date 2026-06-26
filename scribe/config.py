#!/usr/bin/env python3
"""scribe.config — the per-runtime observation opt-out, read in one place.

Both hooks that observe (events.py for sessions/skills/tasks, observe.py for
scripts) honor the same switch: ~/.claude/scriptorium.local.md frontmatter
`observe: off`. Kept here so the two can never drift — one off, the other still
firing — which is exactly what a duplicated reader invites.
"""
from __future__ import annotations

import re
from pathlib import Path

CONFIG_FILE = Path.home() / ".claude" / "scriptorium.local.md"
_OBSERVE_RE = re.compile(r"^\s*observe\s*:\s*(\w+)\s*$", re.MULTILINE)
_OFF_VALUES = {"off", "false", "no", "0"}


def observe_off() -> bool:
    """True when local frontmatter opts out of all scriptorium observation.

    Only a real YAML frontmatter block counts (file must start with `---` and
    close it) — a body-level `observe: off` is ignored, so prose can mention the
    switch without tripping it.
    """
    try:
        text = CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    m = _OBSERVE_RE.search(parts[1])
    return bool(m) and m.group(1).strip().lower() in _OFF_VALUES


if __name__ == "__main__":
    print("observe: off" if observe_off() else "observe: on")
